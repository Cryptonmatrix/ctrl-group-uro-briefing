"""Tests for Briefing validation logic."""

from uro.llm.validator import validate
from uro.models import (
    Briefing,
    FactSheet,
    Finding,
    FindingType,
    NextBestAction,
    Section,
    Severity,
    Statement,
    StatementType,
)


def _make_fs():
    return FactSheet(
        client_ref="TEST-001",
        findings=[
            Finding(
                id="conc-asml",
                type=FindingType.CONCENTRATION,
                severity=Severity.WARNING,
                title="ASML holding at 14.0%",
                detail="Position exceeds 10.0% guideline.",
                numbers={"weight_pct": 14.0, "guideline_pct": 10.0},
            ),
            Finding(
                id="perf-q3",
                type=FindingType.PERFORMANCE,
                severity=Severity.INFO,
                title="Performance Q3 -4.2%",
                detail="Quarterly drop of -4.2%.",
                numbers={"perf_pct": -4.2},
            ),
        ],
    )


def test_validator_accepts_valid_numbers():
    fs = _make_fs()
    briefing = Briefing(
        headline="Portfolio review headline",
        sections=[
            Section(
                title="Recent Portfolio Development",
                statements=[
                    Statement(
                        text="Portfolio dropped -4.2% over Q3.",
                        type=StatementType.FACT,
                        finding_ids=["perf-q3"],
                    )
                ],
            ),
            Section(
                title="Portfolio Health Check",
                statements=[
                    Statement(
                        text="ASML weight is 14.0% against 10.0% guideline.",
                        type=StatementType.RISK,
                        finding_ids=["conc-asml"],
                    )
                ],
            ),
            Section(title="Portfolio Outlook & Next Best Actions", statements=[]),
        ],
        next_best_actions=[
            NextBestAction(
                action="Trim ASML to 10.0%",
                rationale="Bring position back to 10.0% limit",
                finding_ids=["conc-asml"],
            )
        ],
    )

    validated, issues = validate(briefing, fs)
    unsupported = [i for i in issues if i.kind == "unsupported_number"]
    assert len(unsupported) == 0
    assert len(validated.sections[0].statements) == 1
    assert len(validated.sections[1].statements) == 1


def test_validator_drops_unknown_ids():
    fs = _make_fs()
    briefing = Briefing(
        headline="Portfolio review headline",
        sections=[
            Section(
                title="Recent Portfolio Development",
                statements=[
                    Statement(
                        text="This statement cites an unknown ID.",
                        type=StatementType.FACT,
                        finding_ids=["fake-id-999"],
                    )
                ],
            ),
            Section(title="Portfolio Health Check", statements=[]),
            Section(title="Portfolio Outlook & Next Best Actions", statements=[]),
        ],
        next_best_actions=[
            NextBestAction(
                action="Review portfolio",
                rationale="Follow up",
                finding_ids=["conc-asml"],
            )
        ],
    )

    validated, issues = validate(briefing, fs)
    unknown = [i for i in issues if i.kind == "unknown_finding_id"]
    assert len(unknown) == 1
    # Statement was dropped
    assert len(validated.sections[0].statements) == 0


def test_validator_flags_unsupported_numbers():
    fs = _make_fs()
    briefing = Briefing(
        headline="Portfolio review headline",
        sections=[
            Section(
                title="Recent Portfolio Development",
                statements=[
                    Statement(
                        text="Portfolio gained 99.8% and inflation was 55.4%.",
                        type=StatementType.FACT,
                        finding_ids=["perf-q3"],
                    )
                ],
            ),
            Section(title="Portfolio Health Check", statements=[]),
            Section(title="Portfolio Outlook & Next Best Actions", statements=[]),
        ],
        next_best_actions=[
            NextBestAction(
                action="Review portfolio",
                rationale="Follow up",
                finding_ids=["conc-asml"],
            )
        ],
    )

    validated, issues = validate(briefing, fs)
    unsupported = [i for i in issues if i.kind == "unsupported_number"]
    assert len(unsupported) == 1
    # Because there are >= 2 unsupported numbers, statement is dropped
    assert len(validated.sections[0].statements) == 0
