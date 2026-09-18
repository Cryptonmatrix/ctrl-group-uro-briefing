"""Tests for House View loading and portfolio comparison."""

from uro.enrich.house_view import house_view_findings, load_house_view
from uro.models import (
    AllocationLine,
    FactSheet,
    PortfolioFact,
    Severity,
)


def test_load_house_view():
    hv = load_house_view("data/house_view.json")
    assert "views" in hv
    assert len(hv["views"]) >= 10
    categories = {v["category"] for v in hv["views"]}
    assert "Bonds" in categories
    assert "Shares" in categories
    assert "Specialties andCommodities" in categories


def test_house_view_contrary_and_aligned_findings():
    hv = {
        "as_of": "2026-09-01",
        "views": [
            {
                "dimension": "AssetClass",
                "category": "Bonds",
                "stance": "overweight",
                "rationale": "High yields",
            },
            {
                "dimension": "AssetClass",
                "category": "Shares",
                "stance": "underweight",
                "rationale": "High valuations",
            },
        ],
    }

    # Portfolio is underweight Bonds (10% vs 40% target -> tilt -30 pp)
    # Portfolio is underweight Shares (20% vs 50% target -> tilt -30 pp, which aligns with CIO underweight)
    p = PortfolioFact(
        portfolio_nr="P1",
        name="Test Portfolio",
        currency="CHF",
        aum_chf=100000.0,
        liquidity_chf=5000.0,
        allocation=[
            AllocationLine(dimension="AssetClass", category="Bonds", actual_pct=10.0, target_pct=40.0),
            AllocationLine(dimension="AssetClass", category="Shares", actual_pct=20.0, target_pct=50.0),
        ],
    )
    fs = FactSheet(client_ref="CASE-HV", portfolios=[p])

    findings = house_view_findings(fs, hv)
    assert len(findings) == 2

    bonds_f = next(f for f in findings if "bonds" in f.id)
    # Underweight while CIO is overweight -> contrary -> WARNING
    assert bonds_f.severity == Severity.WARNING
    assert "UNDERWEIGHT" in bonds_f.title.upper() or "OVERWEIGHT" in bonds_f.title.upper()

    shares_f = next(f for f in findings if "shares" in f.id)
    # Underweight while CIO is underweight -> aligned -> OPPORTUNITY
    assert shares_f.severity == Severity.OPPORTUNITY
