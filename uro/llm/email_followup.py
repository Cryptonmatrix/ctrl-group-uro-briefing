"""OWNER: GIANLUCA — Post-Call Follow-up Email & Sales Guidance Generation.

3-Stufen-Resilienz:
  1. Primär: Anthropic Claude (Opus 5 / Sonnet 5 via config.py) mit Structured Outputs.
  2. Sekundär (Failover): Google Gemini via REST & OpenAPI-Schema.
  3. Tertiär (Fallback): Deterministische Vorlage (garantiert immer HTTP 200).

Validierung:
  Prüft alle in der Kunden-E-Mail genannten Zahlen gegen die Befunde im FactSheet.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import anthropic

from uro.config import get_settings
from uro.llm.client import LLMUnavailable, log_llm
from uro.llm.fallback import template_followup_email
from uro.llm.gemini import generate_email_gemini
from uro.llm.prompts import (
    EMAIL_SYSTEM_PROMPT_DE,
    EMAIL_SYSTEM_PROMPT_EN,
    render_email_context,
)
from uro.llm.transport import post_messages
from uro.llm.validator import _allowed_numbers_for_ids, _unsupported
from uro.models import (
    Briefing,
    FactSheet,
    FollowUpEmailDraft,
    ValidationIssue,
)

logger = logging.getLogger(__name__)


def _anthropic_key_configured() -> bool:
    key = get_settings().anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
    return bool(key and key.strip())


def _call_structured_email(
    client: anthropic.Anthropic | None,
    model: str,
    max_tokens: int,
    effort: str | None,
    system: list[dict],
    messages: list[dict],
) -> tuple[FollowUpEmailDraft, list[Any]]:
    output_cfg: dict = {
        "format": {
            "type": "json_schema",
            "schema": FollowUpEmailDraft.model_json_schema(),
        }
    }
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

    return FollowUpEmailDraft.model_validate(json.loads(text)), content


def validate_email_draft(
    draft: FollowUpEmailDraft, fact_sheet: FactSheet
) -> tuple[FollowUpEmailDraft, list[ValidationIssue]]:
    """Prüft Zahlen in der Kunden-E-Mail gegen FactSheet und zitierte Findings."""
    issues: list[ValidationIssue] = []
    finding_ids = draft.email.finding_ids
    allowed = _allowed_numbers_for_ids(fact_sheet, finding_ids) if finding_ids else fact_sheet.all_numbers()

    # Prüfe portfolio_recap Sätze
    for text in draft.email.portfolio_recap:
        unsupported = _unsupported(text, allowed)
        for num in unsupported:
            issues.append(
                ValidationIssue(
                    kind="unsupported_number",
                    detail=f"Zahl '{num}' in E-Mail-Rückblick ist nicht durch Befunde belegt.",
                    statement_text=text,
                )
            )

    # Prüfe agreed_next_steps Sätze
    for text in draft.email.agreed_next_steps:
        unsupported = _unsupported(text, allowed)
        for num in unsupported:
            issues.append(
                ValidationIssue(
                    kind="unsupported_number",
                    detail=f"Zahl '{num}' in vereinbarten Schritten ist nicht belegt.",
                    statement_text=text,
                )
            )

    return draft, issues


def _try_gemini_email(
    fact_sheet: FactSheet, briefing: Briefing | None, lang: str
) -> tuple[FollowUpEmailDraft, str] | None:
    try:
        logger.info("Attempting Tier 2 LLM failover with Google Gemini for email on %s", fact_sheet.client_ref)
        draft = generate_email_gemini(fact_sheet, briefing=briefing, lang=lang)
        validated, _ = validate_email_draft(draft, fact_sheet)
        return validated, "ai_gemini"
    except LLMUnavailable:
        logger.debug("Gemini email failover skipped: no Gemini key.")
    except Exception as exc:
        logger.warning("Gemini email failover failed: %s", exc)
    return None


def generate_followup_email(
    fact_sheet: FactSheet,
    briefing: Briefing | None = None,
    lang: str = "de",
    display_name: str = "",
    client: anthropic.Anthropic | None = None,
) -> tuple[FollowUpEmailDraft, str, list[ValidationIssue]]:
    """Generates post-call client email and internal sales guidance with 3-tier cascade.

    Returns:
        tuple[FollowUpEmailDraft, str, list[ValidationIssue]]: (draft, mode, issues)
    """
    settings = get_settings()
    system_prompt = EMAIL_SYSTEM_PROMPT_DE if lang == "de" else EMAIL_SYSTEM_PROMPT_EN

    # 1. Check Anthropic availability
    if client is None and not _anthropic_key_configured():
        gemini_result = _try_gemini_email(fact_sheet, briefing, lang)
        if gemini_result is not None:
            draft, mode = gemini_result
            draft, issues = validate_email_draft(draft, fact_sheet)
            return draft, mode, issues

        fallback = template_followup_email(fact_sheet, briefing, lang=lang, display_name=display_name)
        return fallback, "fallback", []

    user_content = render_email_context(fact_sheet, briefing)
    system_blocks = [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]
    messages = [{"role": "user", "content": user_content}]

    # 2. Try primary Anthropic call
    try:
        draft, _ = _call_structured_email(
            client=client,
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            effort=settings.llm_effort,
            system=system_blocks,
            messages=messages,
        )
        validated, issues = validate_email_draft(draft, fact_sheet)
        log_llm(
            "email_ai",
            fact_sheet.client_ref,
            {"model": settings.llm_model, "lang": lang},
            validated,
        )
        return validated, "ai", issues
    except Exception as exc:
        logger.warning(
            "Primary Anthropic email generation failed for %s: %s. Trying Gemini failover.",
            fact_sheet.client_ref,
            exc,
        )

    # 3. Tier 2: Gemini
    gemini_result = _try_gemini_email(fact_sheet, briefing, lang)
    if gemini_result is not None:
        draft, mode = gemini_result
        draft, issues = validate_email_draft(draft, fact_sheet)
        return draft, mode, issues

    # 4. Tier 3: Template Fallback
    logger.info("Using template fallback for post-call email on %s", fact_sheet.client_ref)
    fallback = template_followup_email(fact_sheet, briefing, lang=lang, display_name=display_name)
    log_llm("email_fallback", fact_sheet.client_ref, {"note": "LLM tiers unavailable"}, fallback)
    return fallback, "fallback", []
