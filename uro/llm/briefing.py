"""OWNER: GIANLUCA — Der Briefing-Call mit Claude Opus 5 und 1-Retry/Fallback-Absicherung.

Modell: claude-opus-5 (oder sonnet-5 bei Notfall über config.py).
Strukturierter Output via messages.parse() direkt auf unser Pydantic-Briefing.
"""

from __future__ import annotations

import logging

import anthropic

from uro.config import get_settings
from uro.llm.client import LLMUnavailable, get_client, log_llm
from uro.llm.fallback import template_briefing
from uro.llm.prompts import SYSTEM_PROMPT, render_fact_sheet
from uro.llm.validator import validate
from uro.models import Briefing, FactSheet

logger = logging.getLogger(__name__)


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

    kwargs: dict = {
        "model": settings.llm_model,
        "max_tokens": settings.llm_max_tokens,
        "system": system_blocks,
        "messages": [{"role": "user", "content": user_content}],
        "output_format": Briefing,
    }
    if settings.llm_effort:
        kwargs["output_config"] = {"effort": settings.llm_effort}

    try:
        # 1. Primary AI Call
        response = client.messages.parse(**kwargs)
        draft: Briefing = response.parsed_output
        validated_briefing, issues = validate(draft, fact_sheet)

        # Check if retry is required
        needs_retry = any(i.kind == "no_actions" for i in issues) or (
            sum(1 for i in issues if i.kind == "unsupported_number") >= 2
        )

        if not needs_retry:
            log_llm(
                "briefing_ai",
                fact_sheet.client_ref,
                {"messages": kwargs["messages"], "model": kwargs["model"]},
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
            {"role": "assistant", "content": response.content},
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
        retry_kwargs = dict(kwargs)
        retry_kwargs["messages"] = retry_messages

        retry_response = client.messages.parse(**retry_kwargs)
        retry_draft: Briefing = retry_response.parsed_output
        final_briefing, final_issues = validate(retry_draft, fact_sheet)

        # If retry still has no actions, populate them via fallback
        if not final_briefing.next_best_actions:
            fb = template_briefing(fact_sheet)
            final_briefing.next_best_actions = fb.next_best_actions

        log_llm(
            "briefing_ai_retry",
            fact_sheet.client_ref,
            {"messages": retry_messages, "model": kwargs["model"]},
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
