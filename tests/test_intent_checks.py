"""Tests for intent checking (B3) and enrich_fact_sheet orchestration."""

from uro.analytics import build_fact_sheet
from uro.analytics.notes import check_intents
from uro.enrich import enrich_fact_sheet
from uro.ingest import ReferenceIndex, load_clients, load_reference
from uro.llm.chat import build_chat_context
from uro.models import (
    ClientIntent,
    FactSheet,
    Finding,
    FindingType,
    MarketSnapshot,
    PortfolioFact,
    PositionFact,
    Severity,
)


def test_check_intents_liquidity_shortfall_case_012():
    clients = load_clients("data/clients.json")
    ref_data = load_reference("data/reference.json")
    ref = ReferenceIndex(ref_data)

    c12 = next(c for c in clients if c["ClientRef"] == "CASE-012")
    fs12 = build_fact_sheet(c12, ref)

    intents = [
        ClientIntent(
            kind="liquidity_need",
            subject="tax payment",
            detail="Needs approximately CHF 15,000 in liquid funds for the Q1 tax payment.",
            source_note="Needs approximately CHF 15,000 in liquid funds for the Q1 tax payment.",
        )
    ]

    findings = check_intents(intents, fs12, ref)
    assert len(findings) == 1
    f = findings[0]
    assert f.type == FindingType.LIQUIDITY
    assert f.severity == Severity.ERROR
    assert "shortfall" in f.id
    assert f.numbers["need_chf"] == 15000.0
    assert f.numbers["available_chf"] == 328.0
    assert f.numbers["shortfall_chf"] == 14672.0


def test_check_intents_liquidity_covered_case_016():
    clients = load_clients("data/clients.json")
    ref_data = load_reference("data/reference.json")
    ref = ReferenceIndex(ref_data)

    c16 = next(c for c in clients if c["ClientRef"] == "CASE-016")
    fs16 = build_fact_sheet(c16, ref)

    intents = [
        ClientIntent(
            kind="liquidity_need",
            subject="tax payment",
            detail="Needs approximately CHF 15,000 in liquid funds for the Q1 tax payment.",
            source_note="Needs approximately CHF 15,000 in liquid funds for the Q1 tax payment.",
        )
    ]

    findings = check_intents(intents, fs16, ref)
    assert len(findings) == 1
    f = findings[0]
    assert f.type == FindingType.LIQUIDITY
    assert f.severity == Severity.INFO
    assert "covered" in f.id
    assert f.numbers["need_chf"] == 15000.0
    assert f.numbers["available_chf"] >= 150000.0


def test_check_intents_exclusion_threshold_rule():
    """Conflict only emitted if exposure >= 2.0% (CLAUDE.md §4)."""
    p_high = PortfolioFact(
        portfolio_nr="P1",
        name="High Energy",
        currency="CHF",
        aum_chf=100000.0,
        liquidity_chf=5000.0,
        positions=[
            PositionFact(
                security_id=1,
                name="Shell plc",
                currency="EUR",
                amount_chf=3500.0,
                weight_pct=3.5,
                industry="Energy",
            )
        ],
    )
    fs_high = FactSheet(
        client_ref="CASE-EXCL-HIGH",
        total_aum_chf=100000.0,
        total_liquidity_chf=5000.0,
        portfolios=[p_high],
        exposures={
            "industry": [{"name": "Energy", "weight_pct": 3.5, "direct_pct": 3.5, "via_funds_pct": 0.0}]
        },
    )

    p_low = PortfolioFact(
        portfolio_nr="P2",
        name="Low Energy",
        currency="CHF",
        aum_chf=100000.0,
        liquidity_chf=5000.0,
        positions=[
            PositionFact(
                security_id=2,
                name="Tiny Oil",
                currency="CHF",
                amount_chf=1200.0,
                weight_pct=1.2,
                industry="Energy",
            )
        ],
    )
    fs_low = FactSheet(
        client_ref="CASE-EXCL-LOW",
        total_aum_chf=100000.0,
        total_liquidity_chf=5000.0,
        portfolios=[p_low],
        exposures={
            "industry": [{"name": "Energy", "weight_pct": 1.2, "direct_pct": 1.2, "via_funds_pct": 0.0}]
        },
    )

    intents = [
        ClientIntent(
            kind="exclusion",
            subject="fossil fuels",
            detail="No direct positions in fossil fuels, please.",
            source_note="No direct positions in fossil fuels, please.",
        )
    ]

    # High exposure (3.5% >= 2.0%) -> triggers PREFERENCE_CONFLICT
    findings_high = check_intents(intents, fs_high)
    assert len(findings_high) == 1
    assert findings_high[0].type == FindingType.PREFERENCE_CONFLICT
    assert findings_high[0].severity == Severity.WARNING
    assert findings_high[0].numbers["conflict_weight_pct"] == 3.5

    # Low exposure (1.2% < 2.0%) -> ignored (immaterial per CLAUDE.md)
    findings_low = check_intents(intents, fs_low)
    assert len(findings_low) == 0


def test_enrich_fact_sheet_orchestration():
    clients = load_clients("data/clients.json")
    ref_data = load_reference("data/reference.json")
    ref = ReferenceIndex(ref_data)

    c = next(x for x in clients if x["ClientRef"] == "CASE-003")
    fs = build_fact_sheet(c, ref)
    initial_count = len(fs.findings)

    mock_news = [
        Finding(
            id="news-1",
            type=FindingType.MARKET_EVENT,
            severity=Severity.INFO,
            title="Swiss Central Bank cuts rate",
            detail="SNB lowers policy rate by 25 bps.",
            source="yfinance news",
        )
    ]
    mock_market = MarketSnapshot(
        as_of=fs.data_as_of or "2026-09-18",
        source="cache",
        tickers={188: "LISN.SW"},
        prices={},
        news=mock_news,
        warnings=["Test market warning"],
    )

    intents = [
        ClientIntent(
            kind="concern",
            subject="volatility concern",
            detail="Client is worried about short-term market volatility.",
            source_note="Client is worried about short-term market volatility.",
        )
    ]

    enriched = enrich_fact_sheet(fs, market=mock_market, ref=ref, intents=intents)

    assert len(enriched.findings) > initial_count
    assert any(f.id == "news-1" for f in enriched.findings)
    assert any(f.id.startswith("hv-") for f in enriched.findings)
    assert any(f.id.startswith("intent-") for f in enriched.findings)
    assert "Test market warning" in enriched.warnings
    assert enriched.coverage["house_view"] == "ok"
    assert enriched.coverage["market"] == "cache"
    assert enriched.coverage["intents"] == "ok"

    # Verify findings are sorted by score descending
    scores = [f.score for f in enriched.findings]
    assert scores == sorted(scores, reverse=True)


def test_chat_build_context_contains_exposures_and_proposals():
    p = PortfolioFact(
        portfolio_nr="P1",
        name="Test Portfolio",
        currency="CHF",
        aum_chf=100000.0,
        liquidity_chf=5000.0,
        positions=[
            PositionFact(
                security_id=4673,
                name="Sensirion Holding AG",
                currency="CHF",
                amount_chf=24000.0,
                weight_pct=24.0,
                industry="Information Technology",
                volatility=0.28,
                sustainability_score=7.5,
            )
        ],
    )
    fs = FactSheet(
        client_ref="CASE-CHAT",
        total_aum_chf=100000.0,
        total_liquidity_chf=5000.0,
        portfolios=[p],
        exposures={
            "industry": [
                {
                    "name": "Information Technology",
                    "weight_pct": 24.0,
                    "direct_pct": 24.0,
                    "via_funds_pct": 0.0,
                }
            ]
        },
        findings=[
            Finding(
                id="prop-101",
                type=FindingType.OPEN_PROPOSAL,
                severity=Severity.INFO,
                title="Proposal 101 open",
                detail="Proposed rebalance.",
            )
        ],
    )

    ctx = build_chat_context(fs)
    assert "[pos-4673]" in ctx
    assert "Sensirion Holding AG" in ctx
    assert "Information Technology: 24.0%" in ctx
    assert "[prop-101]" in ctx
    assert "Vola 28.0%" in ctx
    assert "ESG 7.5" in ctx
