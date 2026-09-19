"""Tests for the deterministic fallback template briefing."""

from uro.analytics import build_fact_sheet
from uro.ingest import find_client, load_clients, load_reference
from uro.llm.fallback import template_briefing
from uro.llm.validator import validate
from uro.models import FactSheet, Finding, FindingType, Severity


def test_fallback_with_real_client():
    clients = load_clients("data/clients.json")
    reference = load_reference("data/reference.json")
    fs = build_fact_sheet(find_client(clients, "CASE-003"), reference)

    briefing = template_briefing(fs)
    assert briefing.headline
    assert len(briefing.sections) == 3
    assert len(briefing.next_best_actions) >= 1
    assert all(len(a.finding_ids) > 0 for a in briefing.next_best_actions)

    validated_briefing, issues = validate(briefing, fs)
    assert len(validated_briefing.sections) == 3
    # Ensure at least some statements survived validation
    total_statements = sum(len(s.statements) for s in validated_briefing.sections)
    assert total_statements >= 3
    assert len(validated_briefing.next_best_actions) >= 1


def test_fallback_with_empty_fact_sheet():
    fs = FactSheet(client_ref="EMPTY-001")
    # Even with empty findings, template_briefing must not crash
    briefing = template_briefing(fs)
    assert briefing.headline
    assert len(briefing.sections) == 3
    assert len(briefing.next_best_actions) >= 1


def test_fallback_with_synthetic_findings():
    fs = FactSheet(
        client_ref="SYNTH-001",
        findings=[
            Finding(
                id="perf-1",
                type=FindingType.PERFORMANCE,
                severity=Severity.WARNING,
                title="Portfolio down -4.2%",
                detail="3M return is negative.",
                numbers={"perf_3m_pct": -4.2},
            ),
            Finding(
                id="viol-1",
                type=FindingType.SUITABILITY_VIOLATION,
                severity=Severity.ERROR,
                title="Max weight exceeded: ASML at 14.0%",
                detail="Limit is 10.0%.",
                numbers={"weight_pct": 14.0, "limit_pct": 10.0},
            ),
        ],
    )
    briefing = template_briefing(fs)
    assert "Portfolio down -4.2%" in briefing.headline or "Max weight exceeded" in briefing.headline
    assert len(briefing.sections) == 3
    assert any("ASML" in a.action for a in briefing.next_best_actions)
