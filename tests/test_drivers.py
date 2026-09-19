from __future__ import annotations

from datetime import datetime

import pytest

from uro.analytics.format import num, pct, pp
from uro.analytics.market_comparison import market_comparison_findings, proxy_tickers
from uro.analytics.performance import driver_findings
from uro.enrich import enrich_fact_sheet
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


@pytest.mark.parametrize(
    ("pos_ret", "sector_ret", "market_ret", "expected_label"),
    [
        (-12.0, -8.0, -1.0, "sector-wide"),
        (-10.0, -2.0, -6.0, "market-wide"),
        (-20.0, -2.0, -1.0, "stock-specific"),
        (-8.0, -4.0, -2.0, "mixed"),
    ],
)
def test_market_comparison_classification(fact_sheets, pos_ret, sector_ret, market_ret, expected_label):
    fs = fact_sheets["CASE-A01"]
    # Lindt is 101, CHF, Consumer Staples
    snap = MarketSnapshot(
        source="live",
        as_of=datetime(2026, 9, 19),
        tickers={101: "LISN.SW"},
        prices={
            "LISN.SW": PriceSeries(ticker="LISN.SW", closes=[100.0, 100.0 * (1.0 + pos_ret / 100)]),
            "XLP": PriceSeries(ticker="XLP", closes=[100.0, 100.0 * (1.0 + sector_ret / 100)]),
            "^SSMI": PriceSeries(ticker="^SSMI", closes=[100.0, 100.0 * (1.0 + market_ret / 100)]),
        },
    )
    drivers = driver_findings(fs, snap)
    assert any(f.id == "drv-101" for f in drivers)

    sector_proxies = {"Consumer Staples": "XLP"}
    comps = market_comparison_findings(fs, snap, drivers, sector_proxies)
    assert len(comps) == 1
    mkt = comps[0]
    assert mkt.id == "mkt-101"
    assert f"decline is {expected_label}" in mkt.title
    assert mkt.security_ids == [101]


def test_market_comparison_negative_only_and_related_ids(fact_sheets):
    fs = fact_sheets["CASE-A01"]
    sector_proxies = {"Consumer Staples": "XLP"}

    # 1. Negative driver -> creates mkt-101 and sets related_ids in both directions
    snap_neg = MarketSnapshot(
        source="live",
        as_of=datetime(2026, 9, 19),
        tickers={101: "LISN.SW"},
        prices={
            "LISN.SW": PriceSeries(ticker="LISN.SW", closes=[100.0, 90.0]),  # -10%
            "XLP": PriceSeries(ticker="XLP", closes=[100.0, 92.0]),  # -8%
            "^SSMI": PriceSeries(ticker="^SSMI", closes=[100.0, 99.0]),  # -1%
        },
    )
    drivers_neg = driver_findings(fs, snap_neg)
    drv_neg = next(f for f in drivers_neg if f.id == "drv-101")
    comps_neg = market_comparison_findings(fs, snap_neg, drivers_neg, sector_proxies)
    assert len(comps_neg) == 1
    mkt = comps_neg[0]
    assert mkt.id == "mkt-101"
    assert mkt.security_ids == [101]
    assert mkt.related_ids == ["drv-101"]
    assert "mkt-101" in drv_neg.related_ids

    # 2. Positive driver -> no mkt finding
    snap_pos = MarketSnapshot(
        source="live",
        as_of=datetime(2026, 9, 19),
        tickers={101: "LISN.SW"},
        prices={
            "LISN.SW": PriceSeries(ticker="LISN.SW", closes=[100.0, 110.0]),  # +10%
            "XLP": PriceSeries(ticker="XLP", closes=[100.0, 105.0]),
            "^SSMI": PriceSeries(ticker="^SSMI", closes=[100.0, 102.0]),
        },
    )
    drivers_pos = driver_findings(fs, snap_pos)
    comps_pos = market_comparison_findings(fs, snap_pos, drivers_pos, sector_proxies)
    assert comps_pos == []


def test_proxy_tickers(fact_sheets):
    fs = fact_sheets["CASE-A01"]
    # CASE-A01 has Lindt (101): currency CHF, industry "Consumer Staples"
    tickers = {101: "LISN.SW"}
    sector_proxies = {"Consumer Staples": "XLP", "Information Technology": "XLK"}
    pt = proxy_tickers(fs, tickers, sector_proxies)
    assert set(pt) == {"^SSMI", "XLP"}


def test_enrich_fact_sheet_with_drivers(fact_sheets):
    fs = fact_sheets["CASE-A01"]
    # 1. With market=None -> no exception, no drv-*, coverage is no_data
    fs_none = enrich_fact_sheet(fs.model_copy(deep=True), market=None)
    assert not any(f.id.startswith("drv-") for f in fs_none.findings)
    assert fs_none.coverage.get("drivers") == "no_data"

    # 2. With market snapshot -> drv-* and coverage is ok
    snap = MarketSnapshot(
        source="live",
        as_of=datetime(2026, 9, 19),
        tickers={101: "LISN.SW"},
        prices={"LISN.SW": PriceSeries(ticker="LISN.SW", closes=[100.0, 90.0])},
    )
    fs_enriched = enrich_fact_sheet(fs.model_copy(deep=True), market=snap)
    assert any(f.id.startswith("drv-") for f in fs_enriched.findings)
    assert fs_enriched.coverage.get("drivers") == "ok"
