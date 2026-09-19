"""OWNER: GIANLUCA — Follow-up-Chat für den Berater.

Beantwortet Fragen direkt aus dem FactSheet und dem Briefing:
  - Streng quellenbasiert: Zitiert Finding-IDs [conc-nvda] oder Positionszeilen [pos-9108].
  - Wenn eine Information fehlt: "This information is not available in the data."
  - Maximal 120 Wörter.
"""

from __future__ import annotations

import logging
import os
import re

import anthropic

from uro.config import get_settings
from uro.llm.prompts import CHAT_SYSTEM_PROMPT
from uro.llm.transport import post_messages
from uro.models import Briefing, ChatResponse, FactSheet

logger = logging.getLogger(__name__)

CITED_SOURCE_REGEX = re.compile(r"\[([a-zA-Z0-9_-]+)\]")


def extract_sources_from_text(text: str) -> list[str]:
    """Extracts finding-ids or pos-ids from brackets, handling comma-separated lists like [id1, id2]."""
    matches = re.findall(r"\[([a-zA-Z0-9_,\s-]+)\]", text)
    sources: list[str] = []
    for m in matches:
        for part in m.split(","):
            cleaned = part.strip()
            if cleaned and cleaned not in sources:
                sources.append(cleaned)
    return sources


def build_chat_context(fact_sheet: FactSheet, briefing: Briefing | None = None) -> str:
    """Builds the comprehensive context string for the follow-up chat according to Spec §8.2."""
    fs = fact_sheet
    lines: list[str] = [
        f"CLIENT: {fs.client_ref}" + (" (Corporate)" if fs.is_company else " (Private)"),
        f"Total AuM: {fs.total_aum_chf:,.0f} {fs.reporting_currency}",
        f"Liquidity: {fs.total_liquidity_chf:,.0f} {fs.reporting_currency}",
        f"Risk Profile: {fs.risk_profile_name or 'None'}"
        + (f" (Max Volatility {fs.max_volatility * 100:.1f}%)" if fs.max_volatility else ""),
        f"ESG Profile: {fs.esg_profile or 'None'}",
        f"Open Proposals Count: {fs.open_proposals}",
    ]
    if fs.age is not None:
        lines.append(f"Client Age: {fs.age}")

    # Briefing summary and actions if available
    if briefing:
        lines.append(f"\nGENERATED BRIEFING HEADLINE: {briefing.headline}")
        if briefing.next_best_actions:
            lines.append("RECOMMENDED ACTIONS:")
            for a in briefing.next_best_actions:
                lines.append(f"- {a.action}: {a.rationale} (sources: {', '.join(a.finding_ids)})")

    # Multi-dimensional exposures with look-through (Spec §8.2)
    if fs.exposures:
        lines.append("\nPORTFOLIO EXPOSURES (including fund look-through):")
        for dim, items in fs.exposures.items():
            dim_str = ", ".join(f"{it['name']}: {it['weight_pct']:.1f}%" for it in items[:6])
            lines.append(f"  {dim.replace('_', ' ').title()}: {dim_str}")

    # Positions list with [pos-<id>] IDs and full master data
    lines.append("\nPORTFOLIO POSITIONS:")
    for p in fs.portfolios:
        for pos in p.positions:
            ind = pos.industry or pos.sector or ""
            sec_cls = pos.saa_asset_class or pos.asset_class or ""
            vola = f"Vola {pos.volatility * 100:.1f}%" if pos.volatility is not None else ""
            esg = f"ESG {pos.sustainability_score:.1f}" if pos.sustainability_score is not None else ""
            meta = " | ".join(filter(bool, [pos.currency, sec_cls, ind, vola, esg]))
            lines.append(
                f"[pos-{pos.security_id}] {pos.name[:45]} | Weight: {pos.weight_pct:.1f}% | "
                f"Amount: {pos.amount_chf:,.0f} CHF | {meta}"
            )

    # Proposals context
    prop_findings = [
        f
        for f in fs.findings
        if f.type.value in ("open_proposal", "rejected_proposal") or "prop" in f.id or "rej" in f.id
    ]
    if prop_findings:
        lines.append("\nPROPOSALS STATUS:")
        for f in prop_findings:
            lines.append(f"[{f.id}] {f.title}: {f.detail}")

    # All findings
    lines.append("\nALL GROUNDED FINDINGS:")
    for f in fs.findings:
        nums = " ".join(f"{k}={v}" for k, v in f.numbers.items()) if f.numbers else ""
        num_str = f" Numbers: {nums}" if nums else ""
        lines.append(f"[{f.id}] ({f.type.value}/{f.severity.value}) {f.title}. {f.detail}{num_str}")

    # Client Notes and Intents
    if fs.intents:
        lines.append("\nEXTRACTED CLIENT INTENTS:")
        for i in fs.intents:
            lines.append(f"- {i.kind}: {i.subject} ({i.detail}) quote: '{i.source_note}'")

    return "\n".join(lines)


def _rule_based_fallback_answer(
    question: str, fact_sheet: FactSheet, briefing: Briefing | None = None
) -> str:
    """Provides a deterministic grounded response when the LLM API is unavailable."""
    q_lower = question.lower()

    # Question 1: Volatility vs positive performance
    if "volatil" in q_lower and ("positive" in q_lower or "performance" in q_lower or "breach" in q_lower):
        risk_breaches = [f for f in fact_sheet.findings if "risk-breach" in f.id]
        if risk_breaches:
            # Nur aus geprüften Fakten zusammensetzen: keine unbedingte Behauptung "performance is positive"
            # oder "due to concentration" — beides wird nur genannt, wenn ein Finding es belegt.
            rb = risk_breaches[0]
            parts = [f"{rb.title} [{rb.id}]."]
            perf = next((f for f in fact_sheet.findings if f.id.startswith("perf-") and f.numbers), None)
            if perf:
                parts.append(f"Performance: {perf.title} [{perf.id}].")
            conc = next((f for f in fact_sheet.findings if f.id.startswith("conc-single-")), None)
            if conc:
                parts.append(f"Largest concentration: {conc.title} [{conc.id}].")
            return " ".join(parts)

    # Question 2: Semiconductor or specific sector exposure
    if "semiconductor" in q_lower or "chip" in q_lower:
        ind_exp = fact_sheet.exposures.get("industry", [])
        semi = next((e for e in ind_exp if "semi" in e.get("name", "").lower()), None)
        if semi:
            return (
                f"Total semiconductor exposure is {semi['weight_pct']:.1f}% of assets "
                f"({semi.get('direct_pct', 0.0):.1f}% direct, {semi.get('via_funds_pct', 0.0):.1f}% via fund look-through)."
            )
        tech = next((e for e in ind_exp if "tech" in e.get("name", "").lower()), None)
        if tech:
            return (
                f"Direct semiconductor breakdown is not separately classified; total Technology exposure is {tech['weight_pct']:.1f}% "
                f"({tech.get('direct_pct', 0.0):.1f}% direct, {tech.get('via_funds_pct', 0.0):.1f}% via look-through)."
            )
        return "This information is not available in the data."

    # Question 3: Open proposals
    if "proposal" in q_lower:
        prop_findings = [f for f in fact_sheet.findings if "prop-" in f.id or f.type.value == "open_proposal"]
        if prop_findings:
            pf = prop_findings[0]
            return f"Open proposal on file: {pf.title} [{pf.id}]."
        return f"There are currently {fact_sheet.open_proposals} open proposals on file [profile]."

    # Question 4: Ethical exclusions / ESG
    if any(w in q_lower for w in ["ethical", "exclusion", "fossil", "esg", "tobacco", "weapon"]):
        excl_findings = [
            f for f in fact_sheet.findings if "exclusion" in f.id or f.type.value == "preference_conflict"
        ]
        if excl_findings:
            ef = excl_findings[0]
            return f"Client exclusion finding: {ef.title} [{ef.id}]."
        notes = [f for f in fact_sheet.findings if f.type.value == "client_note"]
        for n in notes:
            if any(w in n.detail.lower() for w in ["fossil", "esg", "defense", "tobacco"]):
                return f"Client note states: '{n.detail}' [{n.id}]."
        return "This information is not available in the data."

    # Question 5: Recommended actions
    if any(w in q_lower for w in ["recommend", "action", "next best", "should do"]):
        if briefing and briefing.next_best_actions:
            acts = "; ".join(
                f"{a.action} (sources: {', '.join(a.finding_ids)})" for a in briefing.next_best_actions[:2]
            )
            return f"Key recommended actions: {acts}."
        err_findings = [f for f in fact_sheet.findings if f.severity.value == "error"]
        if err_findings:
            return f"Primary priority: resolve {err_findings[0].title} [{err_findings[0].id}]."

    # Question about largest / top holding
    if any(w in q_lower for w in ["largest", "biggest", "top holding", "main position"]):
        all_pos = [pos for p in fact_sheet.portfolios for pos in p.positions]
        if all_pos:
            top_pos = max(all_pos, key=lambda x: x.weight_pct)
            return (
                f"The largest holding is {top_pos.name} at {top_pos.weight_pct:.1f}% of the portfolio "
                f"(amount: CHF {top_pos.amount_chf:,.0f}) [pos-{top_pos.security_id}]."
            )

    # General sector match
    for p in fact_sheet.portfolios:
        for pos in p.positions:
            sec = pos.industry or pos.sector
            if sec and sec.lower() in q_lower:
                return f"{sec} exposure includes {pos.name} at {pos.weight_pct:.1f}% of portfolio [pos-{pos.security_id}]."
            if pos.name.lower() in q_lower:
                return f"{pos.name} constitutes {pos.weight_pct:.1f}% of the portfolio (amount: CHF {pos.amount_chf:,.0f}) [pos-{pos.security_id}]."

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
    context_str = build_chat_context(fact_sheet, briefing)

    # 1. Try Primary: Anthropic
    anthropic_available = bool(
        (settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    )
    if client is not None or anthropic_available:
        try:
            messages = [
                {
                    "role": "user",
                    "content": f"CLIENT DATA CONTEXT:\n{context_str}\n\nPlease answer the question below.",
                },
                {
                    "role": "assistant",
                    "content": "I have reviewed the client context and will answer based strictly on the facts provided.",
                },
            ]
            if history:
                for h in history[-4:]:
                    messages.append({"role": h["role"], "content": h["content"]})
            messages.append({"role": "user", "content": question})

            kwargs: dict = {
                "model": settings.llm_model,
                "max_tokens": 1000,
                "system": [
                    {"type": "text", "text": CHAT_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
                ],
                "messages": messages,
            }
            if settings.llm_effort:
                kwargs["output_config"] = {"effort": settings.llm_effort}

            if client is not None:
                resp = client.messages.create(**kwargs)
                answer_text = "".join(block.text for block in resp.content if hasattr(block, "text"))
            else:
                # Standardweg wie im Briefing: stdlib-Transport, dessen Timeout nachweislich greift
                # (das SDK hing auf dem Demo-Rechner > 280 s, siehe llm/transport.py).
                data = post_messages(kwargs, timeout=settings.llm_timeout_s, retries=settings.llm_max_retries)
                answer_text = "".join(
                    b.get("text", "") for b in data.get("content") or [] if b.get("type") == "text"
                )
            if not answer_text.strip():
                raise RuntimeError("Empty chat answer")

            return ChatResponse(answer=answer_text.strip(), sources=_known_sources(answer_text, fact_sheet))
        except Exception as exc:
            logger.warning("Anthropic chat failed (%s). Attempting Gemini failover.", exc)

    # 2. Try Tier-2: Gemini
    gemini_key = settings.gemini_api_key or settings.google_api_key
    if gemini_key:
        try:
            from uro.llm.gemini import ask_chat_gemini

            answer_text = ask_chat_gemini(context_str, question, history)
            return ChatResponse(answer=answer_text.strip(), sources=_known_sources(answer_text, fact_sheet))
        except Exception as exc:
            logger.warning("Gemini chat failed (%s). Falling back to rule-based answer.", exc)

    # 3. Tier-3: Deterministic Rule-Based Fallback
    ans_text = _rule_based_fallback_answer(question, fact_sheet, briefing)
    return ChatResponse(answer=ans_text, sources=_known_sources(ans_text, fact_sheet))


def _known_sources(text: str, fact_sheet: FactSheet) -> list[str]:
    """Nur zitierte IDs, die es im Fact Sheet wirklich gibt (Findings oder pos-<secid>) — sonst zeigt die UI tote Chips."""
    known = set(fact_sheet.by_id()) | {
        f"pos-{p.security_id}" for pf in fact_sheet.portfolios for p in pf.positions
    }
    return [s for s in extract_sources_from_text(text) if s in known]


def main(argv: list[str]) -> int:
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    from uro.analytics import build_fact_sheet
    from uro.ingest import find_client, load_clients, load_reference

    ref = next((a for a in argv if not a.startswith("-")), "CASE-003")
    query_args = [a for a in argv if not a.startswith("-") and a != ref]
    one_shot_query = " ".join(query_args) if query_args else None

    clients = load_clients("data/clients.json")
    reference = load_reference("data/reference.json")
    client_data = find_client(clients, ref)
    fs = build_fact_sheet(client_data, reference)

    briefing = None
    try:
        from uro.llm.briefing import generate_briefing

        briefing, _ = generate_briefing(fs)
    except Exception:
        pass

    print("\n=======================================================")
    print(f"  URO Advisor Follow-up Chat · Client: {ref}")
    print(
        f"  AuM: {fs.total_aum_chf:,.0f} {fs.reporting_currency} | Profile: {fs.risk_profile_name or 'None'}"
    )
    if briefing:
        print(f"  Briefing: {briefing.headline[:65]}...")
    print("=======================================================\n")

    if one_shot_query:
        print(f"Advisor: {one_shot_query}\n")
        resp = answer(one_shot_query, fs, briefing=briefing)
        print(f"Assistant: {resp.answer}\n")
        if resp.sources:
            print(f"Sources cited: {', '.join(resp.sources)}\n")
        return 0

    print("Type your questions below (or 'exit' / 'q' to quit).\n")
    history: list[dict] = []
    while True:
        try:
            user_input = input("Advisor > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("Exiting chat.")
                break

            resp = answer(user_input, fs, briefing=briefing, history=history)
            print(f"\nAssistant:\n{resp.answer}\n")
            if resp.sources:
                print(f"Sources: {', '.join(resp.sources)}\n")

            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": resp.answer})

        except (KeyboardInterrupt, EOFError):
            print("\nExiting chat.")
            break

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
