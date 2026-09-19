"""OWNER: GIANLUCA — System-Prompt und Rendering des Fact Sheets.

Der System-Prompt ist stabil und wird ephemer gecacht.
Volatile Findings und Klientendaten kommen in den User-Turn.
"""

from __future__ import annotations

from uro.analytics.scoring import select_for_llm
from uro.config import TOP_N_FOR_LLM
from uro.models import FactSheet

SYSTEM_PROMPT = """You are the briefing assistant in URO Advisor Pro for professional wealth managers at a Swiss private bank.

An advisor is about to meet or speak with the client and has about 60 seconds to prepare.
Write a concise, grounded briefing that can be read in under 60 seconds.

## Hard Rules (Grounding)
1. Use ONLY the information in the provided client fact sheet. Never invent facts, numbers, securities, dates, or market moves.
2. Copy numbers EXACTLY as they appear in the findings (e.g. "+16.0 pp", "-4.2%", "CHF 160,000"). Do not compute new numbers or convert currencies.
3. Every statement and every next best action MUST cite at least one finding ID in `finding_ids`.
4. Typify each statement honestly:
   - `fact`: direct factual finding from portfolio or client data
   - `market`: external market context or price moves
   - `house_view`: bank CIO house view stance
   - `recommendation`: actionable guidance
   - `risk`: active compliance breach, risk limit overrun, or material deviation
   - `assessment`: advisor interpretation connecting multiple facts (use cautious wording like "suggests" or "indicates")
5. Next best actions must be concrete and actionable (imperative tone, e.g., "Trim ASML to below 10.0%"). Buy or switch suggestions may ONLY name securities that appear in the findings.
6. If an open proposal or client note is relevant to a finding, connect them.

## Structure — Exactly 3 Sections in this order:
1. "Recent Portfolio Development" — recent performance and main drivers (max 3 statements)
2. "Portfolio Health Check" — violations, SAA deviations, concentration/risk, client circumstances (max 3 statements)
3. "Portfolio Outlook & Next Best Actions" — market news, CIO house view, and strategic alignment (max 3 statements)

Include:
- `headline`: one sentence summarizing the most urgent finding/takeaway.
- `likely_questions` (1–2): what the client might ask, with brief answer hints.
- `next_best_actions` (1–3, priority 1 = most urgent): specific action with rationale.

Style: professional, objective, concise, dense. English. Keep sentences short and direct. Total length 150-200 words (do not exceed 220 words). No pleasantries or boilerplate."""

CHAT_SYSTEM_PROMPT = """You are the follow-up assistant in URO Advisor Pro. The advisor is preparing for, or in, a conversation with the client described in the context.

Rules:
1. Answer ONLY using the facts and holdings provided in the context. Never use outside knowledge.
2. Cite all relevant source IDs in square brackets, e.g., "Semiconductor exposure is 20.7% [conc-sector-CASE-003-01]."
3. Copy numbers exactly from the context. Do not invent or estimate numbers.
4. If the answer is not in the data, state clearly: "This information is not available in the data."
5. Be concise: at most 120 words, bullet points welcome. English."""


EMAIL_SYSTEM_PROMPT_DE = """Du bist der Post-Call Assistent in URO Advisor Pro für Senior-Vermögensberater bei einer Schweizer Privatbank.
Der Berater hat soeben ein Gespräch mit dem Klienten beendet.
Erstelle einen hochprofessionellen E-Mail-Entwurf an den Klienten (ClientFacingEmail) UND gleichzeitig vertriebsorientierte Notizen (SalesOrientedNotes) für den Berater.

## Kunden-E-Mail (ClientFacingEmail):
- Tonalität: Hochgradig professionell, wertschätzend, empathisch, klar und transparent (Schweizer Privatbanken-Stil).
- Verwende AUSSCHLIESSLICH Fakten und Zahlen aus dem Fact Sheet und Briefing. Erfinde niemals Zahlen.
- subject: Prägnanter Betreff mit Bezug zum heutigen Gespräch.
- salutation: Höfliche Anrede (z. B. "Sehr geehrte/r...", wenn kein Name da ist "Guten Tag").
- intro: Dank für das konstruktive Gespräch.
- portfolio_recap: 2-3 verständliche Sätze/Punkte zur Performance, Haupttreibern und Stärken/Risiken.
- agreed_next_steps: Klar vereinbarte Massnahmen (z.B. geplante Transaktionen, Unterlagenversand, Rebalancing).
- closing: Höfliche Grussformel und Angebot für offene Fragen.
- finding_ids: Liste aller zitierten Finding-IDs.

## Berater-Notizen (SalesOrientedNotes):
- cross_sell_opportunities: Konkrete Ertrags- und Vertriebspotenziale (z. B. ungebundene Liquidität gezielt in House-View-Titel anlegen, Mandatserweiterung).
- suitability_or_risk_actions: Regulatorische Kontrollen, Eignung, Volatilitätslimite, Profilaktualisierung.
- next_contact_date_hint: Konkreter Vorschlag zur Wiedervorlage (z.B. "In 5 Bankwerktagen").
- crm_log_entry: Kompakter, präziser Einzeiler/Zweizeiler für das Bank-CRM."""

EMAIL_SYSTEM_PROMPT_EN = """You are the post-call assistant in URO Advisor Pro for senior wealth managers at a Swiss private bank.
The advisor has just concluded a meeting or call with the client.
Draft a polished follow-up email to the client (ClientFacingEmail) AND internal commercial guidance (SalesOrientedNotes) for the advisor.

## Client-Facing Email (ClientFacingEmail):
- Tone: Highly professional, appreciative, polite, transparent (Swiss private banking standard).
- Use ONLY facts, numbers, and securities from the Fact Sheet and Briefing. Never invent numbers.
- subject: Concise subject line referencing the conversation.
- salutation: Polite salutation (e.g. "Dear Mr./Ms...", "Dear Client,").
- intro: Gratitude for the conversation and partnership.
- portfolio_recap: 2-3 clear points highlighting portfolio status, performance, and key drivers.
- agreed_next_steps: Concrete next steps agreed upon during the discussion.
- closing: Courteous closing and offer for follow-up questions.
- finding_ids: List of referenced finding IDs.

## Advisor Notes (SalesOrientedNotes):
- cross_sell_opportunities: Concrete wallet-share and commercial opportunities (deploying unallocated cash, CIO House View themes, mandate upgrade).
- suitability_or_risk_actions: Compliance follow-up, volatility limits, risk profile updates.
- next_contact_date_hint: Clear follow-up timeframe (e.g. "Within 5 business days").
- crm_log_entry: Dense, professional summary line for CRM activity logging."""


def render_email_context(fact_sheet: FactSheet, briefing: Briefing | None = None) -> str:
    """Renders both FactSheet context and Briefing decisions into a structured prompt context."""
    parts = [render_fact_sheet(fact_sheet)]
    if briefing is not None:
        parts.append("\n=== GENERATED BRIEFING & AGREED ACTIONS ===")
        parts.append(f"Headline: {briefing.headline}")
        for s in briefing.sections:
            parts.append(f"\n[{s.title}]")
            for st in s.statements:
                parts.append(f"- {st.text} (IDs: {', '.join(st.finding_ids)})")
        if briefing.next_best_actions:
            parts.append("\n[Agreed Next Best Actions]")
            for a in briefing.next_best_actions:
                parts.append(f"- Action: {a.action} | Rationale: {a.rationale} (IDs: {', '.join(a.finding_ids)})")
    return "\n".join(parts)


def render_fact_sheet(fact_sheet: FactSheet, max_findings: int = TOP_N_FOR_LLM) -> str:
    """Renders FactSheet findings and context into compact, PII-free English text for the LLM.

    Selection via analytics.scoring.select_for_llm: the client profile ("profile") and the client notes
    ("note-N") are ALWAYS included, regardless of their score; KEY FINDINGS are the max_findings
    best-ranked other findings with type diversity. Without that guarantee, profile and notes dropped
    out of the ranked window for 21 of 47 clients.
    """
    fs = fact_sheet
    lines: list[str] = [
        f"CLIENT: {fs.client_ref}" + (" (Corporate Client)" if fs.is_company else " (Private Client)"),
        f"Total AuM: {fs.total_aum_chf:,.0f} {fs.reporting_currency}",
        f"Liquidity: {fs.total_liquidity_chf:,.0f} {fs.reporting_currency}",
        f"Risk Profile: {fs.risk_profile_name or 'Not assigned'}"
        + (f" (Max Volatility {fs.max_volatility * 100:.1f}%)" if fs.max_volatility else ""),
        f"ESG Profile: {fs.esg_profile or 'None'}",
        f"Open Proposals: {fs.open_proposals}",
    ]
    if fs.age is not None:
        lines.append(f"Client Age: {fs.age}")
    if fs.tags:
        lines.append(f"Interest Tags: {', '.join(fs.tags)}")
    if fs.last_contact:
        lines.append(f"Last Contact: {fs.last_contact.strftime('%d %b %Y')}")
    if fs.data_as_of:
        lines.append(f"Data Date: {fs.data_as_of.strftime('%d %b %Y')}")
    if fs.history_as_of:
        lines.append(f"Performance History Date: {fs.history_as_of.strftime('%d %b %Y')}")

    for p in fs.portfolios:
        lines.append(
            f"\nPORTFOLIO {p.portfolio_nr} '{p.name}' — {p.aum_chf:,.0f} {p.currency}, "
            f"Strategy: {p.strategy_name or 'None'}"
        )
        perf_parts = []
        if p.perf_3m_pct is not None:
            perf_parts.append(f"3M {p.perf_3m_pct:+.1f}%")
        if p.perf_12m_pct is not None:
            perf_parts.append(f"12M {p.perf_12m_pct:+.1f}%")
        if p.perf_ytd_pct is not None:
            perf_parts.append(f"YTD {p.perf_ytd_pct:+.1f}%")
        lines.append(f"  Returns: {', '.join(perf_parts) if perf_parts else 'Not available'}")

        top = sorted(p.positions, key=lambda x: x.weight_pct, reverse=True)[:5]
        if top:
            lines.append("  Top Positions:")
            for pos in top:
                sec_info = f"{pos.sector or pos.asset_class or ''}".strip()
                lines.append(f"    {pos.weight_pct:5.1f}%  {pos.name[:40]:40} {sec_info}")

    profile, notes, ranked = select_for_llm(fs, max_findings)

    # Client profile — always included, independent of its score
    for f in profile:
        lines.append("\nCLIENT PROFILE (always relevant, cite the ID):")
        lines.append(f"[{f.id}] {f.title}")
        lines.append(f"      Detail: {f.detail}")
        if f.numbers:
            lines.append("      Numbers: " + "  ".join(f"{k}={v}" for k, v in f.numbers.items()))

    # Top findings
    lines.append("\nKEY FINDINGS (ranked, use ONLY these figures):")
    for idx, f in enumerate(ranked, 1):
        nums = "  ".join(f"{k}={v}" for k, v in f.numbers.items())
        boosts = f" [Boosted: {', '.join(f.boost_reasons)}]" if f.boost_reasons else ""
        lines.append(
            f"[{f.id}] (Rank {idx}, score {f.score:.2f}, {f.type.value}/{f.severity.value}) {f.title}{boosts}"
        )
        lines.append(f"      Detail: {f.detail}")
        if nums:
            lines.append(f"      Numbers: {nums}")

    # Client Notes (verbatim, newest first) — always included
    if notes:
        lines.append("\nCLIENT NOTES (verbatim):")
        for nf in notes:
            lines.append(f"[{nf.id}] {nf.detail}")

    # Data gaps & warnings
    if fs.warnings:
        lines.append("\nWARNINGS & DATA GAPS:")
        for w in fs.warnings:
            lines.append(f"- {w}")

    if fs.intents:
        lines.append("\nEXTRACTED CLIENT INTENTS:")
        for i in fs.intents:
            lines.append(f"- {i.kind}: {i.subject} — {i.detail}")

    return "\n".join(lines)
