"""OWNER: GIANLUCA — Der Briefing-Call mit Claude Opus 5 und 1-Retry/Fallback-Absicherung.

Modell: claude-opus-5 (oder sonnet-5 bei Notfall über config.py).
Strukturierter Output via output_config.format={"type": "json_schema", ...}.
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


def generate_briefing(
    fact_sheet: FactSheet, client: anthropic.Anthropic | None = None
) -> tuple[Briefing, str]:
    """Generates a structured, grounded briefing for the client.

    Returns:
        tuple[Briefing, str]: (Briefing, mode) where mode is "ai", "ai_retry", or "fallback".
    """
    settings = get_settings()

    try:
        if client is None:
            client = get_client()
    except LLMUnavailable as exc:
        logger.warning("LLM unavailable (%s). Using deterministic template fallback.", exc)
        return template_briefing(fact_sheet), "fallback"

    user_content = render_fact_sheet(fact_sheet)
    system_blocks = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
    messages = [{"role": "user", "content": user_content}]

    try:
        # 1. Primary AI Call
        draft, raw_content = _call_structured_briefing(
            client=client,
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            effort=settings.llm_effort,
            system=system_blocks,
            messages=messages,
        )
        validated_briefing, issues = validate(draft, fact_sheet)

        # Check if retry is required
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

        # 2. Exactly 1 Retry Turn
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

        # If retry still has no actions, populate them via fallback
        if not final_briefing.next_best_actions:
            fb = template_briefing(fact_sheet)
            final_briefing.next_best_actions = fb.next_best_actions

        log_llm(
            "briefing_ai_retry",
            fact_sheet.client_ref,
            {"messages": retry_messages, "model": settings.llm_model},
            final_briefing,
        )
        return final_briefing, "ai_retry"

    except Exception as exc:
        logger.exception(
            "Failed to generate briefing via Anthropic API for %s: %s. Using template fallback.",
            fact_sheet.client_ref,
            exc,
        )
        fallback = template_briefing(fact_sheet)
        log_llm("briefing_fallback", fact_sheet.client_ref, {"error": str(exc)}, fallback)
        return fallback, "fallback"
