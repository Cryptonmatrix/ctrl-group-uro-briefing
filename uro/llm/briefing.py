"""OWNER: GIANLUCA — Der Briefing-Call mit 3-Stufen-Resilienz (Claude -> Gemini -> Template).

Resilienz-Kette:
  1. Primär: Anthropic Claude (Opus 5 / Sonnet 5 via config.py) mit Structured Outputs.
  2. Sekundär (Failover): Google Gemini (z.B. gemini-3.5-flash-lite) via REST & JSON-Schema.
  3. Tertiär (Fallback): Deterministisches Template-Briefing (garantiert immer HTTP 200).

Transport für Stufe 1 (Merge gianluca + levin/frontend-api):
  Standardmässig über uro/llm/transport.py (Standardbibliothek, Levin). Das anthropic-SDK hing auf dem
  Demo-Rechner reproduzierbar über 280 s trotz timeout=60 — ein Aufruf, der nie zurückkommt, würde die
  Kette blockieren, bevor Gemini oder das Template greifen. Wer explizit einen SDK-Client übergibt
  (z. B. in Tests), bekommt weiterhin den SDK-Weg.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import anthropic

from uro.config import get_settings
from uro.llm.client import LLMUnavailable, log_llm
from uro.llm.fallback import template_briefing
from uro.llm.prompts import SYSTEM_PROMPT, render_fact_sheet
from uro.llm.transport import post_messages
from uro.llm.validator import validate
from uro.models import Briefing, FactSheet

logger = logging.getLogger(__name__)


def _anthropic_key_configured() -> bool:
    """Schlüssel aus .env (Settings) oder Umgebung — dieselbe Quelle, die transport.post_messages nutzt."""
    key = get_settings().anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
    return bool(key and key.strip())


def _call_structured_briefing(
    client: anthropic.Anthropic | None,
    model: str,
    max_tokens: int,
    effort: str | None,
    system: list[dict],
    messages: list[dict],
) -> tuple[Briefing, list[Any]]:
    output_cfg: dict = {"format": {"type": "json_schema", "schema": Briefing.model_json_schema()}}
    if effort:
        output_cfg["effort"] = effort

    if client is not None:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            output_config=output_cfg,
        )
        stop_reason = response.stop_reason
        content: list[Any] = list(response.content)
        text = next((b.text for b in response.content if b.type == "text"), None)
    else:
        settings = get_settings()
        data = post_messages(
            {
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": messages,
                "output_config": output_cfg,
            },
            timeout=settings.llm_timeout_s,
            retries=settings.llm_max_retries,
        )
        stop_reason = data.get("stop_reason")
        content = data.get("content") or []
        text = next((b.get("text") for b in content if b.get("type") == "text"), None)

    if stop_reason == "refusal":
        raise RuntimeError("Model refused the request.")
    if stop_reason == "max_tokens":
        raise RuntimeError("Response truncated at max_tokens.")
    if text is None:
        raise RuntimeError("Response contained no text block.")
    return Briefing.model_validate(json.loads(text)), content


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

    # 1. Check Anthropic access (explicit SDK client, or a key for the stdlib transport)
    if client is None and not _anthropic_key_configured():
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
