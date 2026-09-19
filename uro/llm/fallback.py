"""OWNER: GIANLUCA — Deterministisches Template-Briefing (Fallback ohne KI).

Wird verwendet, wenn:
  - Kein API-Key vorhanden ist
  - Der LLM-Aufruf ein Timeout hat oder fehlschlägt
  - Der Validator nach 1 Retry scheitert

Garantiert, dass der Briefing-Endpoint IMMER HTTP 200 mit einem validen Briefing liefert.
"""

from __future__ import annotations

from uro.models import (
    ActionKind,
    Briefing,
    FactSheet,
    Finding,
    FindingType,
    LikelyQuestion,
    NextBestAction,
    Section,
    Severity,
    Statement,
    StatementType,
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
    if ft == FindingType.LIQUIDITY:
        return NextBestAction(
            action=f"Review liquidity: {finding.title}",
            rationale="Evaluate cash deployment and reinvestment opportunities.",
            finding_ids=[finding.id],
            priority=3,
            kind=ActionKind.REINVEST_LIQUIDITY,
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
        text = f"{f.title}. {f.detail}".strip()
        if len(text) > 220:
            text = text[:217] + "..."
        return Statement(text=text, type=st_type, finding_ids=[f.id])

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

    action_candidates = (
        by_type.get(FindingType.SUITABILITY_VIOLATION, [])
        + by_type.get(FindingType.RISK_PROFILE, [])
        + by_type.get(FindingType.SAA_DEVIATION, [])
        + by_type.get(FindingType.CONCENTRATION, [])
        + by_type.get(FindingType.OPEN_PROPOSAL, [])
        + by_type.get(FindingType.LIQUIDITY, [])
        + top_findings
    )
    for f in action_candidates:
        if f.id in seen_action_ids:
            continue
        actions.append(_map_action(f))
        seen_action_ids.add(f.id)
        if len(actions) >= 3:
            break

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
                answer_hint=f"Refer to {q_f.detail[:100]}.",
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
