"""OWNER: GIANLUCA — Follow-up-Chat für den Berater.

Beantwortet Fragen direkt aus dem FactSheet und dem Briefing:
  - Streng quellenbasiert: Zitiert Finding-IDs [conc-nvda] oder Positionszeilen [pos-9108].
  - Wenn eine Information fehlt: "This information is not available in the data."
  - Maximal 120 Wörter.
"""

from __future__ import annotations

import logging
import re

import anthropic

from uro.config import get_settings
from uro.llm.client import LLMUnavailable, get_client
from uro.llm.prompts import CHAT_SYSTEM_PROMPT
from uro.models import Briefing, ChatResponse, FactSheet

logger = logging.getLogger(__name__)

CITED_SOURCE_REGEX = re.compile(r"\[([a-zA-Z0-9_-]+)\]")


def build_chat_context(fact_sheet: FactSheet, briefing: Briefing | None = None) -> str:
    """Builds the comprehensive context string for the follow-up chat."""
    fs = fact_sheet
    lines: list[str] = [
        f"CLIENT: {fs.client_ref}",
        f"Total AuM: {fs.total_aum_chf:,.0f} {fs.reporting_currency}",
        f"Liquidity: {fs.total_liquidity_chf:,.0f} {fs.reporting_currency}",
        f"Risk Profile: {fs.risk_profile_name or 'None'}",
        f"ESG Profile: {fs.esg_profile or 'None'}",
    ]

    # Briefing summary if available
    if briefing:
        lines.append(f"\nGENERATED BRIEFING HEADLINE: {briefing.headline}")
        lines.append("RECOMMENDED ACTIONS:")
        for a in briefing.next_best_actions:
            lines.append(f"- {a.action}: {a.rationale} (sources: {', '.join(a.finding_ids)})")

    # Positions list with [pos-<id>] IDs
    lines.append("\nPORTFOLIO POSITIONS:")
    for p in fs.portfolios:
        for pos in p.positions:
            sec_info = f"{pos.sector or ''} {pos.asset_class or ''}".strip()
            lines.append(
                f"[pos-{pos.security_id}] {pos.name[:45]} | Weight: {pos.weight_pct:.1f}% | "
                f"Amount: {pos.amount_chf:,.0f} CHF | {sec_info}"
            )

    # All findings
    lines.append("\nALL FINDINGS:")
    for f in fs.findings:
        nums = " ".join(f"{k}={v}" for k, v in f.numbers.items())
        lines.append(f"[{f.id}] ({f.type.value}) {f.title}. {f.detail} Numbers: {nums}")

    # Client Notes
    if fs.intents:
        lines.append("\nCLIENT INTENTS & NOTES:")
        for i in fs.intents:
            lines.append(f"- {i.kind}: {i.subject} ({i.detail}) quote: '{i.source_note}'")

    return "\n".join(lines)


def _rule_based_fallback_answer(question: str, fact_sheet: FactSheet) -> str:
    """Provides a deterministic grounded response when the LLM API is unavailable."""
    q_lower = question.lower()

    # Question about largest / top holding
    if any(w in q_lower for w in ["largest", "biggest", "top holding", "main position"]):
        all_pos = [pos for p in fact_sheet.portfolios for pos in p.positions]
        if all_pos:
            top_pos = max(all_pos, key=lambda x: x.weight_pct)
            return (
                f"The largest holding is {top_pos.name} at {top_pos.weight_pct:.1f}% of the portfolio "
                f"(amount: CHF {top_pos.amount_chf:,.0f}) [pos-{top_pos.security_id}]."
            )

    # Question about exposure / sector
    for p in fact_sheet.portfolios:
        for pos in p.positions:
            if pos.sector and pos.sector.lower() in q_lower:
                return f"{pos.sector} exposure is concentrated in {pos.name} at {pos.weight_pct:.1f}% of portfolio [{pos.security_id}]."
            if pos.name.lower() in q_lower:
                return f"{pos.name} constitutes {pos.weight_pct:.1f}% of the portfolio (amount: CHF {pos.amount_chf:,.0f}) [pos-{pos.security_id}]."

    # Question about volatility / risk
    if "volatil" in q_lower or "risk" in q_lower:
        vola_findings = [f for f in fact_sheet.findings if "vola" in f.id or "risk" in f.id]
        if vola_findings:
            f = vola_findings[0]
            return f"Portfolio risk finding: {f.title} [{f.id}]."

    # Question about proposals
    if "proposal" in q_lower:
        prop_findings = [f for f in fact_sheet.findings if "prop" in f.id]
        if prop_findings:
            f = prop_findings[0]
            return f"Proposal status: {f.title} [{f.id}]."

    # Default honest missing info response
    return "This information is not available in the data."


def answer(
    question: str,
    fact_sheet: FactSheet,
    briefing: Briefing | None = None,
    history: list[dict] | None = None,
    client: anthropic.Anthropic | None = None,
) -> ChatResponse:
    """Answers an advisor follow-up question, citing source IDs and remaining strictly grounded."""
    settings = get_settings()

    try:
        if client is None:
            client = get_client()
    except LLMUnavailable:
        ans_text = _rule_based_fallback_answer(question, fact_sheet)
        sources = CITED_SOURCE_REGEX.findall(ans_text)
        return ChatResponse(answer=ans_text, sources=sources)

    context_str = build_chat_context(fact_sheet, briefing)

    messages = [
        {"role": "user", "content": f"CLIENT DATA CONTEXT:\n{context_str}\n\nPlease answer the question below."},
        {"role": "assistant", "content": "I have reviewed the client context and will answer based strictly on the facts provided."},
    ]
    if history:
        for h in history[-4:]:
            messages.append({"role": h["role"], "content": h["content"]})

    messages.append({"role": "user", "content": question})

    kwargs: dict = {
        "model": settings.llm_model,
        "max_tokens": 1000,
        "system": [{"type": "text", "text": CHAT_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        "messages": messages,
    }
    if settings.llm_effort:
        kwargs["output_config"] = {"effort": settings.llm_effort}

    try:
        resp = client.messages.create(**kwargs)
        answer_text = ""
        for block in resp.content:
            if hasattr(block, "text"):
                answer_text += block.text

        sources = list(dict.fromkeys(CITED_SOURCE_REGEX.findall(answer_text)))
        return ChatResponse(answer=answer_text.strip(), sources=sources)
    except Exception as exc:
        logger.warning("Chat generation failed: %s. Falling back to rule-based answer.", exc)
        ans_text = _rule_based_fallback_answer(question, fact_sheet)
        sources = list(dict.fromkeys(CITED_SOURCE_REGEX.findall(ans_text)))
        return ChatResponse(answer=ans_text, sources=sources)
