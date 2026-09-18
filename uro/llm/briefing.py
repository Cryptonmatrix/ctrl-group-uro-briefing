"""OWNER: GIANLUCA — Der Briefing-Call mit 3-Stufen-Resilienz (Claude -> Gemini -> Template).

Resilienz-Kette:
  1. Primär: Anthropic Claude (Opus 5 / Sonnet 5 via config.py) mit Structured Outputs.
  2. Sekundär (Failover): Google Gemini (z.B. gemini-3.5-flash-lite) via REST & JSON-Schema.
  3. Tertiär (Fallback): Deterministisches Template-Briefing (garantiert immer HTTP 200).
"""

from __future__ import annotations

import json
import logging

import anthropic

from uro.config import get_settings
from uro.llm.client import LLMUnavailable, get_client, log_llm
from uro.llm.fallback import template_briefing
from uro.llm.prompts import SYSTEM_PROMPT, render_fact_sheet
from uro.llm.validator import validate
from uro.models import Briefing, FactSheet

logger = logging.getLogger(__name__)


def _call_structured_briefing(
    client: anthropic.Anthropic,
    model: str,
    max_tokens: int,
    effort: str | None,
    system: list[dict],
    messages: list[dict],
) -> tuple[Briefing, list[anthropic.types.ContentBlock]]:
    output_cfg: dict = {"format": {"type": "json_schema", "schema": Briefing.model_json_schema()}}
    if effort:
        output_cfg["effort"] = effort

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
        output_config=output_cfg,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Model refused the request.")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Response truncated at max_tokens.")

    text = next(b.text for b in response.content if b.type == "text")
    return Briefing.model_validate(json.loads(text)), response.content


def _try_gemini_failover(fact_sheet: FactSheet) -> tuple[Briefing, str] | None:
    """Attempts Tier 2 failover using Google Gemini (e.g. gemini-3.5-flash-lite)."""
    try:
        from uro.llm.gemini import generate_briefing_gemini

        logger.info("Attempting Tier 2 LLM failover with Google Gemini for %s", fact_sheet.client_ref)
        draft = generate_briefing_gemini(fact_sheet)
        validated, issues = validate(draft, fact_sheet)
        if validated.next_best_actions:
            return validated, "ai_gemini"
    except LLMUnavailable:
        logger.debug("Gemini failover skipped: no Gemini API key configured.")
    except Exception as exc:
        logger.warning("Gemini failover attempt failed: %s", exc)
    return None


def generate_briefing(
    fact_sheet: FactSheet, client: anthropic.Anthropic | None = None
) -> tuple[Briefing, str]:
    """Generates a structured, grounded briefing with a 3-tier resilience cascade.

    Returns:
        tuple[Briefing, str]: (Briefing, mode) where mode is "ai", "ai_retry", "ai_gemini", or "fallback".
    """
    settings = get_settings()

    # 1. Check Anthropic Client
    try:
        if client is None:
            client = get_client()
    except LLMUnavailable:
        logger.info("Anthropic API key not configured. Checking Tier 2 failover (Gemini).")
        gemini_result = _try_gemini_failover(fact_sheet)
        if gemini_result is not None:
            return gemini_result
        return template_briefing(fact_sheet), "fallback"

    user_content = render_fact_sheet(fact_sheet)
    system_blocks = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
    messages = [{"role": "user", "content": user_content}]

    # 2. Execute Primary Anthropic Call
    try:
        draft, raw_content = _call_structured_briefing(
            client=client,
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            effort=settings.llm_effort,
            system=system_blocks,
            messages=messages,
        )
        validated_briefing, issues = validate(draft, fact_sheet)

        needs_retry = any(i.kind == "no_actions" for i in issues) or (
            sum(1 for i in issues if i.kind == "unsupported_number") >= 2
        )

        if not needs_retry:
            log_llm(
                "briefing_ai",
                fact_sheet.client_ref,
                {"messages": messages, "model": settings.llm_model},
                validated_briefing,
            )
            return validated_briefing, "ai"

        # Exactly 1 Retry Turn for Anthropic
        logger.info(
            "Validation issues for %s: %s. Attempting 1 retry.",
            fact_sheet.client_ref,
            [i.detail for i in issues],
        )
        issue_texts = "\n".join(f"- {i.kind}: {i.detail}" for i in issues)
        retry_messages = [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": raw_content},
            {
                "role": "user",
                "content": (
                    f"Your previous briefing had the following grounding/validation issues:\n"
                    f"{issue_texts}\n\n"
                    f"Please correct these issues, ensure all numbers exist in the cited findings, "
                    f"and provide valid next_best_actions. Resubmit the briefing."
                ),
            },
        ]

        retry_draft, _ = _call_structured_briefing(
            client=client,
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            effort=settings.llm_effort,
            system=system_blocks,
            messages=retry_messages,
        )
        final_briefing, final_issues = validate(retry_draft, fact_sheet)

        if final_briefing.next_best_actions:
            log_llm(
                "briefing_ai_retry",
                fact_sheet.client_ref,
                {"messages": retry_messages, "model": settings.llm_model},
                final_briefing,
            )
            return final_briefing, "ai_retry"

    except Exception as exc:
        logger.warning(
            "Primary Anthropic call failed for %s: %s. Attempting Tier 2 failover (Gemini).",
            fact_sheet.client_ref,
            exc,
        )

    # 3. Tier 2: Google Gemini Failover
    gemini_result = _try_gemini_failover(fact_sheet)
    if gemini_result is not None:
        return gemini_result

    # 4. Tier 3: Deterministic Template Fallback
    logger.info("Falling back to deterministic rule-based template briefing for %s", fact_sheet.client_ref)
    fallback = template_briefing(fact_sheet)
    log_llm("briefing_fallback", fact_sheet.client_ref, {"note": "all LLM tiers unavailable"}, fallback)
    return fallback, "fallback"
