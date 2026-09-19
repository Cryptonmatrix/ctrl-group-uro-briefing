"""OWNER: GIANLUCA — Deterministisches Template-Briefing (Fallback ohne KI).

Wird verwendet, wenn:
  - Kein API-Key vorhanden ist
  - Der LLM-Aufruf ein Timeout hat oder fehlschlägt
  - Der Validator nach 1 Retry scheitert

Garantiert, dass der Briefing-Endpoint IMMER HTTP 200 mit einem validen Briefing liefert.
"""

from __future__ import annotations

from uro.analytics.suitability import EXECUTION_ONLY_TITLE_PREFIX
from uro.models import (
    ActionKind,
    Briefing,
    ClientFacingEmail,
    FactSheet,
    Finding,
    FindingType,
    FollowUpEmailDraft,
    LikelyQuestion,
    NextBestAction,
    SalesOrientedNotes,
    Section,
    Severity,
    Statement,
    StatementType,
)


def _cut(text: str, limit: int) -> str:
    """An einer Wortgrenze kürzen: nie mitten in einer Zahl ("CHF 11." aus "CHF 11,500" wäre eine erfundene Zahl)."""
    if len(text) <= limit:
        return text
    return text[: limit - 2].rsplit(" ", 1)[0].rstrip(" ,;:(") + " …"


_ACTIONABLE_TYPES = {
    FindingType.SUITABILITY_VIOLATION,
    FindingType.RISK_PROFILE,
    FindingType.SAA_DEVIATION,
    FindingType.CONCENTRATION,
    FindingType.OPEN_PROPOSAL,
    FindingType.LIQUIDITY,
    FindingType.OPEN_ITEM,
    FindingType.ESG,
}


def _actionable(finding: Finding) -> bool:
    """Nur Befunde, aus denen eine Handlung folgt. `saa-none-*` sagt "keine SAA hinterlegt" — daraus
    folgt kein Rebalancing auf SAA-Ziele (CASE-003 bekam früher genau das)."""
    if finding.type not in _ACTIONABLE_TYPES or finding.id.startswith("saa-none-"):
        return False
    return finding.severity != Severity.INFO or finding.type in (
        FindingType.OPEN_PROPOSAL,
        FindingType.OPEN_ITEM,
    )


def _map_action(finding: Finding) -> NextBestAction:
    """Deterministically maps a Finding to a NextBestAction."""
    ft = finding.type
    if ft == FindingType.SUITABILITY_VIOLATION:
        return NextBestAction(
            action=f"Resolve suitability breach: {finding.title}",
            rationale="Eliminate mandate violation and restore regulatory compliance.",
            finding_ids=[finding.id],
            priority=1,
            kind=ActionKind.RESOLVE_VIOLATION,
        )
    if ft == FindingType.RISK_PROFILE and finding.title.startswith(EXECUTION_ONLY_TITLE_PREFIX):
        # Execution-only: kein Verstoss, sondern Verkaufsanlass (analytics/suitability.py)
        return NextBestAction(
            action="Offer the client an advisory conversation on portfolio risk vs. risk profile",
            rationale="Execution-only mandate above the client's own volatility limit: no breach, but a reason to propose advice.",
            finding_ids=[finding.id],
            priority=1,
            kind=ActionKind.CLIENT_FOLLOW_UP,
        )
    if ft == FindingType.RISK_PROFILE:
        return NextBestAction(
            action=f"Address portfolio risk: {finding.title}",
            rationale="Reduce volatility exposure to comply with client risk profile.",
            finding_ids=[finding.id],
            priority=1,
            kind=ActionKind.RESOLVE_VIOLATION,
        )
    if ft == FindingType.SAA_DEVIATION:
        return NextBestAction(
            action=f"Rebalance allocation: {finding.title}",
            rationale="Restore strategic asset allocation targets.",
            finding_ids=[finding.id],
            priority=2,
            kind=ActionKind.REBALANCE,
        )
    if ft == FindingType.CONCENTRATION:
        return NextBestAction(
            action=f"Trim concentration: {finding.title}",
            rationale="Diversify exposure to mitigate cluster risk.",
            finding_ids=[finding.id],
            priority=2,
            kind=ActionKind.REDUCE_CONCENTRATION,
        )
    if ft == FindingType.OPEN_PROPOSAL:
        return NextBestAction(
            action=f"Follow up on proposal: {finding.title}",
            rationale="Review pending investment proposal with the client.",
            finding_ids=[finding.id],
            priority=2,
            kind=ActionKind.FOLLOW_UP_PROPOSAL,
        )
    if ft == FindingType.LIQUIDITY and finding.severity == Severity.ERROR:
        # Ungedeckter Bedarf (liq-need): Liquidität beschaffen, nicht wiederanlegen
        return NextBestAction(
            action=f"Raise liquidity before the need falls due: {finding.title}",
            rationale="The client's stated cash need is not covered by current liquidity.",
            finding_ids=[finding.id],
            priority=1,
            kind=ActionKind.CLIENT_FOLLOW_UP,
        )
    if ft == FindingType.LIQUIDITY:
        return NextBestAction(
            action=f"Review liquidity: {finding.title}",
            rationale="Evaluate cash deployment and reinvestment opportunities.",
            finding_ids=[finding.id],
            priority=3,
            kind=ActionKind.REINVEST_LIQUIDITY,
        )
    if ft == FindingType.OPEN_ITEM:
        return NextBestAction(
            action=f"Follow up: {finding.title}",
            rationale="Open item derived from the client record.",
            finding_ids=[finding.id],
            priority=3,
            kind=ActionKind.UPDATE_PROFILE if "profile" in finding.id else ActionKind.CLIENT_FOLLOW_UP,
        )

    return NextBestAction(
        action=f"Review portfolio: {finding.title}",
        rationale="Align current portfolio holdings with client investment goals.",
        finding_ids=[finding.id],
        priority=2,
        kind=ActionKind.CLIENT_FOLLOW_UP,
    )


def template_briefing(fs: FactSheet) -> Briefing:
    """Constructs a deterministic, valid Briefing entirely from the FactSheet."""
    findings = fs.findings
    by_type: dict[FindingType, list[Finding]] = {}
    for f in findings:
        by_type.setdefault(f.type, []).append(f)

    # 1. Headline
    top_findings = fs.top_findings(3)
    if top_findings:
        headline = f"Portfolio overview: {top_findings[0].title}."
    else:
        headline = f"Portfolio overview for client {fs.client_ref}."

    # Helper to create statement
    def make_stmt(f: Finding, st_type: StatementType) -> Statement:
        return Statement(text=_cut(f"{f.title}. {f.detail}".strip(), 220), type=st_type, finding_ids=[f.id])

    # 2. Section 1: Recent Portfolio Development
    dev_findings = (
        by_type.get(FindingType.PERFORMANCE, [])
        + by_type.get(FindingType.PERFORMANCE_DRIVER, [])
        + by_type.get(FindingType.MARKET_EVENT, [])
    )
    s1_statements: list[Statement] = []
    for f in dev_findings[:3]:
        s1_statements.append(make_stmt(f, StatementType.FACT))

    # If empty, fill with any top finding or profile
    if not s1_statements and findings:
        s1_statements.append(make_stmt(findings[0], StatementType.FACT))

    # 3. Section 2: Portfolio Health Check
    health_findings = (
        by_type.get(FindingType.SUITABILITY_VIOLATION, [])
        + by_type.get(FindingType.RISK_PROFILE, [])
        + by_type.get(FindingType.SAA_DEVIATION, [])
        + by_type.get(FindingType.CONCENTRATION, [])
        + by_type.get(FindingType.DATA_GAP, [])
    )
    s2_statements: list[Statement] = []
    for f in health_findings[:3]:
        st_type = StatementType.RISK if f.severity == Severity.ERROR else StatementType.FACT
        s2_statements.append(make_stmt(f, st_type))

    if not s2_statements and findings:
        fallback_f = findings[1] if len(findings) > 1 else findings[0]
        s2_statements.append(make_stmt(fallback_f, StatementType.FACT))

    # 4. Section 3: Portfolio Outlook & Next Best Actions
    outlook_findings = (
        by_type.get(FindingType.HOUSE_VIEW, [])
        + by_type.get(FindingType.OPEN_PROPOSAL, [])
        + by_type.get(FindingType.LIQUIDITY, [])
        + by_type.get(FindingType.OPEN_ITEM, [])
    )
    s3_statements: list[Statement] = []
    for f in outlook_findings[:3]:
        st_type = (
            StatementType.HOUSE_VIEW if f.type == FindingType.HOUSE_VIEW else StatementType.RECOMMENDATION
        )
        s3_statements.append(make_stmt(f, st_type))

    if not s3_statements and findings:
        fallback_f = findings[2] if len(findings) > 2 else findings[0]
        s3_statements.append(make_stmt(fallback_f, StatementType.RECOMMENDATION))

    sections = [
        Section(title="Recent Portfolio Development", statements=s1_statements),
        Section(title="Portfolio Health Check", statements=s2_statements),
        Section(title="Portfolio Outlook & Next Best Actions", statements=s3_statements),
    ]

    # 5. Next Best Actions (1–3 actions)
    actions: list[NextBestAction] = []
    seen_action_ids: set[str] = set()

    # Nach Dringlichkeit (Engine-Score), nicht nach fester Typ-Reihenfolge — sonst verdrängt z. B. bei CASE-012
    # eine Verstoss-Liste den ungedeckten Liquiditätsbedarf. Nur handlungsfähige Befunde, je Typ höchstens einer.
    action_candidates = sorted((f for f in findings if _actionable(f)), key=lambda f: f.score, reverse=True)
    seen_types: set[FindingType] = set()
    for f in action_candidates:
        if f.id in seen_action_ids or f.type in seen_types:
            continue
        actions.append(_map_action(f))
        seen_action_ids.add(f.id)
        seen_types.add(f.type)
        if len(actions) >= 3:
            break
    for i, a in enumerate(actions, start=1):
        a.priority = i

    if not actions and findings:
        actions.append(_map_action(findings[0]))
    elif not actions:
        actions.append(
            NextBestAction(
                action="Review portfolio allocation with client",
                rationale="Confirm strategic alignment and discuss upcoming cash needs.",
                finding_ids=[],
                priority=1,
                kind=ActionKind.CLIENT_FOLLOW_UP,
            )
        )

    # 6. Likely Questions (up to 2)
    questions: list[LikelyQuestion] = []
    if top_findings:
        q_f = top_findings[0]
        questions.append(
            LikelyQuestion(
                question=f"What is driving {q_f.title}?",
                answer_hint=f"Refer to {_cut(q_f.detail, 100)}",
            )
        )
    if len(top_findings) > 1:
        q_f2 = top_findings[1]
        questions.append(
            LikelyQuestion(
                question=f"How should we address {q_f2.title}?",
                answer_hint=f"Evaluate rebalancing or adjustments based on {q_f2.id}.",
            )
        )

    return Briefing(
        headline=headline,
        sections=sections,
        likely_questions=questions[:2],
        next_best_actions=actions[:3],
    )


def template_followup_email(
    fs: FactSheet,
    briefing: Briefing | None = None,
    lang: str = "de",
    display_name: str = "",
) -> FollowUpEmailDraft:
    """Deterministically generates a post-call follow-up email and internal sales guidance.

    Zero external LLM calls or internet connection needed. 100% grounded in FactSheet.
    """
    name = display_name.strip() or fs.client_ref
    findings = fs.findings
    top_findings = fs.top_findings(3)
    referenced_ids: list[str] = []

    # 1. Client Facing Email
    if lang == "de":
        subject = f"Zusammenfassung unseres Gesprächs & nächste Schritte — Portfolio {fs.client_ref}"
        if fs.is_company:
            salutation = f"Sehr geehrte Damen und Herren ({name}),"
        else:
            salutation = f"Sehr geehrte/r Frau/Herr {name}," if " " in name else f"Sehr geehrte/r {name},"
        intro = (
            "herzlichen Dank für das konstruktive und offene Gespräch über die aktuelle Entwicklung "
            "Ihres Vermögens und die strategische Ausrichtung Ihres Portfolios."
        )
    else:
        subject = f"Summary of our conversation & next steps — Portfolio {fs.client_ref}"
        salutation = f"Dear Ladies and Gentlemen ({name})," if fs.is_company else f"Dear {name},"
        intro = (
            "thank you very much for our open and constructive discussion regarding the current "
            "development and strategic positioning of your portfolio."
        )

    # Portfolio Recap points
    recap_points: list[str] = []
    for f in top_findings:
        referenced_ids.append(f.id)
        if lang == "de":
            recap_points.append(_cut(f"{f.title}: {f.detail}", 220))
        else:
            recap_points.append(_cut(f"{f.title}: {f.detail}", 220))

    if not recap_points:
        if lang == "de":
            recap_points.append(f"Gesamtvermögen: CHF {fs.total_aum_chf:,.0f} im vereinbarten Mandat geführt.")
        else:
            recap_points.append(f"Total AuM: CHF {fs.total_aum_chf:,.0f} managed within the agreed mandate.")

    # Agreed Next Steps
    next_steps: list[str] = []
    if briefing and briefing.next_best_actions:
        for a in briefing.next_best_actions[:3]:
            referenced_ids.extend(a.finding_ids)
            next_steps.append(f"{a.action} ({a.rationale})")
    elif findings:
        for f in findings:
            if _actionable(f):
                act = _map_action(f)
                referenced_ids.extend(act.finding_ids)
                next_steps.append(f"{act.action} ({act.rationale})")
                if len(next_steps) >= 2:
                    break

    if not next_steps:
        if lang == "de":
            next_steps.append("Gemeinsame Überprüfung der Vermögensaufteilung und Feinjustierung der Anlagepositionen.")
        else:
            next_steps.append("Joint review of portfolio asset allocation and fine-tuning of existing positions.")

    if lang == "de":
        closing = (
            "Für allfällige Fragen oder weitere Präzisierungen stehe ich Ihnen jederzeit gerne zur Verfügung. "
            "Wir werden die besprochenen Massnahmen zeitnah für Sie vorbereiten.\n\n"
            "Mit freundlichen Grüssen,\n"
            "Ihr Vermögensberatungsteam"
        )
    else:
        closing = (
            "Please do not hesitate to contact me should you have any questions or require further details. "
            "We will prepare the agreed steps for you promptly.\n\n"
            "Best regards,\n"
            "Your Wealth Management Team"
        )

    email = ClientFacingEmail(
        subject=subject,
        salutation=salutation,
        intro=intro,
        portfolio_recap=recap_points,
        agreed_next_steps=next_steps,
        closing=closing,
        finding_ids=sorted(set(referenced_ids)),
    )

    # 2. Sales Oriented Notes (Advisor Facing)
    cross_sell: list[str] = []
    if fs.total_liquidity_chf > 100_000:
        if lang == "de":
            cross_sell.append(
                f"Hohe Liquiditätsquote: CHF {fs.total_liquidity_chf:,.0f} ungebunden. "
                "Konkretes Re-Investment in House-View-Fokusse oder Geldmarktinstrumente vorschlagen."
            )
        else:
            cross_sell.append(
                f"High cash balance: CHF {fs.total_liquidity_chf:,.0f} unallocated. "
                "Propose re-investment into CIO House View focus themes or yield enhancement."
            )

    hv_findings = [f for f in findings if f.type == FindingType.HOUSE_VIEW and f.severity == Severity.OPPORTUNITY]
    for hv in hv_findings[:2]:
        cross_sell.append(f"House View Opportunität: {hv.title} — {hv.detail}")

    if fs.open_proposals > 0:
        if lang == "de":
            cross_sell.append(f"{fs.open_proposals} offene Anlagevorschläge im System: Zeitnahe Zeichnung forcieren.")
        else:
            cross_sell.append(f"{fs.open_proposals} pending investment proposal(s): follow up for client execution.")

    if not cross_sell:
        if lang == "de":
            cross_sell.append("Regelmässige Mandatsprüfung zur Erweiterung der Beratungsvereinbarung nutzen.")
        else:
            cross_sell.append("Utilize regular portfolio review to evaluate advisory mandate extension.")

    risk_actions: list[str] = []
    if fs.max_volatility:
        for p in fs.portfolios:
            if p.volatility is not None and p.volatility > fs.max_volatility:
                if lang == "de":
                    risk_actions.append(
                        f"Volatilität ({p.volatility*100:.1f}%) liegt über Kundenlimit ({fs.max_volatility*100:.1f}%): "
                        "Profilaktualisierung oder defensive Umschichtung erforderlich."
                    )
                else:
                    risk_actions.append(
                        f"Volatility ({p.volatility*100:.1f}%) exceeds client limit ({fs.max_volatility*100:.1f}%): "
                        "Profile update or defensive rebalancing required."
                    )

    violations = [f for f in findings if f.type == FindingType.SUITABILITY_VIOLATION]
    if violations:
        if lang == "de":
            risk_actions.append(f"{len(violations)} Eignungsverstoss/-verstösse aktiv — Bereinigung vor Monatsultimo.")
        else:
            risk_actions.append(f"{len(violations)} suitability violation(s) active — remediation prior to month end.")

    if not risk_actions:
        if lang == "de":
            risk_actions.append("Keine kritischen Risikoverstösse aktiv. Reguläre Portfolio-Überwachung.")
        else:
            risk_actions.append("No active compliance breaches. Standard risk monitoring.")

    if lang == "de":
        deadline_hint = "Binnen 5 Bankwerktagen zur Überprüfung der Umsetzung"
        actions_str = ", ".join(next_steps[:2]) if next_steps else "Portfolio-Besprechung"
        crm_log = (
            f"Telefonberatung mit {name} ({fs.client_ref}) durchgeführt. "
            f"Themen: Portfolioentwicklung und Allokation. Vereinbart: {actions_str}. "
            f"Follow-up terminiert."
        )
    else:
        deadline_hint = "Within 5 business days to verify implementation"
        actions_str = ", ".join(next_steps[:2]) if next_steps else "Portfolio review"
        crm_log = (
            f"Advisory call completed with {name} ({fs.client_ref}). "
            f"Topics: Portfolio development and allocation. Agreed: {actions_str}. "
            f"Follow-up scheduled."
        )

    sales_notes = SalesOrientedNotes(
        cross_sell_opportunities=cross_sell,
        suitability_or_risk_actions=risk_actions,
        next_contact_date_hint=deadline_hint,
        crm_log_entry=crm_log,
    )

    return FollowUpEmailDraft(email=email, sales_notes=sales_notes)

