from __future__ import annotations

from datetime import datetime

from uro.analytics.format import num, pct, pp
from uro.analytics.performance import driver_findings
from uro.models import FindingType, MarketSnapshot, PriceSeries, Severity


def test_driver_calculation_and_text(fact_sheets):
    fs = fact_sheets["CASE-A01"]
    # Lindt is security 101 with ~73.5% client weight
    p101 = next(p for pf in fs.portfolios for p in pf.positions if p.security_id == 101)
    weight = p101.client_weight_pct if p101.client_weight_pct is not None else p101.weight_pct

    snap = MarketSnapshot(
        source="live",
        as_of=datetime(2026, 9, 19),
        tickers={101: "LISN.SW"},
        prices={"LISN.SW": PriceSeries(ticker="LISN.SW", closes=[100.0, 90.0])},
    )

    findings = driver_findings(fs, snap)
    drv = next((f for f in findings if f.id == "drv-101"), None)
    assert drv is not None, "drv-101 must be found"
    assert drv.type == FindingType.PERFORMANCE_DRIVER
    assert drv.severity == Severity.WARNING
    expected_c = num(weight * -10.0 / 100)
    assert drv.numbers["contribution_pp"] == expected_c
    assert "≈" in drv.title
    assert "approximation" in drv.detail.lower()
    assert drv.security_ids == [101]

    # Check that all numbers appear formatted in title or detail
    w_str = pct(drv.numbers["weight_pct"])
    r_str = pct(drv.numbers["return_3m_pct"], signed=True)
    c_str = pp(drv.numbers["contribution_pp"])

    assert w_str in drv.detail
    assert r_str in drv.detail
    assert c_str in drv.title


def test_positive_driver_and_threshold(fact_sheets):
    fs = fact_sheets["CASE-A01"]
    # Positive driver (+10%) -> OPPORTUNITY
    snap_pos = MarketSnapshot(
        source="live",
        as_of=datetime(2026, 9, 19),
        tickers={101: "LISN.SW"},
        prices={"LISN.SW": PriceSeries(ticker="LISN.SW", closes=[100.0, 110.0])},
    )
    findings = driver_findings(fs, snap_pos)
    drv = next((f for f in findings if f.id == "drv-101"), None)
    assert drv is not None
    assert drv.severity == Severity.OPPORTUNITY

    # Small contribution (< 0.3 pp) -> no finding
    # Lindt has 73.5% weight. Return of 0.1% -> 73.5 * 0.1 / 100 = 0.07 pp -> rounded 0.1 pp < 0.3 pp
    snap_small = MarketSnapshot(
        source="live",
        as_of=datetime(2026, 9, 19),
        tickers={101: "LISN.SW"},
        prices={"LISN.SW": PriceSeries(ticker="LISN.SW", closes=[1000.0, 1001.0])},
    )
    findings_small = driver_findings(fs, snap_small)
    assert not any(f.id == "drv-101" for f in findings_small)


def test_robustness_empty_and_no_positions(fact_sheets):
    fs_a = fact_sheets["CASE-A01"]
    fs_c = fact_sheets["CASE-C03"]  # Has no securities (only cash/crypto)

    snap_valid = MarketSnapshot(
        source="live",
        as_of=datetime(2026, 9, 19),
        tickers={101: "LISN.SW"},
        prices={"LISN.SW": PriceSeries(ticker="LISN.SW", closes=[100.0, 90.0])},
    )
    snap_empty_prices = MarketSnapshot(
        source="live",
        as_of=datetime(2026, 9, 19),
        tickers={},
        prices={},
    )

    # market is None -> []
    assert driver_findings(fs_a, None) == []
    # market.prices is empty -> []
    assert driver_findings(fs_a, snap_empty_prices) == []
    # client with 0 securities (CASE-C03) -> []
    assert driver_findings(fs_c, snap_valid) == []


def test_gap_prices_coverage(fact_sheets):
    fs = fact_sheets["CASE-B02"]
    # CASE-B02 has:
    # 101: 100,000 CHF
    # 103: 350,000 CHF
    # 104: 25,000 CHF
    # Cash: 25,000 CHF
    # Total invested = 475,000 CHF

    # Only 101 is priced -> 375k / 475k = ~78.9% uncovered > 20%
    snap_partial = MarketSnapshot(
        source="live",
        as_of=datetime(2026, 9, 19),
        tickers={101: "LISN.SW"},
        prices={"LISN.SW": PriceSeries(ticker="LISN.SW", closes=[100.0, 90.0])},
    )
    findings_partial = driver_findings(fs, snap_partial)
    gap = next((f for f in findings_partial if f.id == "gap-prices"), None)
    assert gap is not None
    assert gap.type == FindingType.DATA_GAP
    assert gap.severity == Severity.INFO
    assert gap.numbers["uncovered_pct"] > 20.0
    assert gap.materiality_chf == 375000.0

    # All priced -> 0% uncovered -> no gap-prices
    snap_all = MarketSnapshot(
        source="live",
        as_of=datetime(2026, 9, 19),
        tickers={101: "LISN.SW", 103: "FUND.SW", 104: "BOND.SW"},
        prices={
            "LISN.SW": PriceSeries(ticker="LISN.SW", closes=[100.0, 90.0]),
            "FUND.SW": PriceSeries(ticker="FUND.SW", closes=[100.0, 102.0]),
            "BOND.SW": PriceSeries(ticker="BOND.SW", closes=[100.0, 100.5]),
        },
    )
    findings_all = driver_findings(fs, snap_all)
    assert not any(f.id == "gap-prices" for f in findings_all)
