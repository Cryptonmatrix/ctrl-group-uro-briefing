"""OWNER: GIANLUCA — Externe Datenquellen & Anreicherung des FactSheets.

Bündelt:
  - Marktdaten & News (yfinance via market.py, news.py)
  - House View / CIO Outlook (house_view.py)
  - FactSheet-Anreicherung (enrich_fact_sheet)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from uro.analytics.market_comparison import market_comparison_findings
from uro.analytics.notes import check_intents
from uro.analytics.performance import driver_findings
from uro.analytics.scoring import score_findings
from uro.enrich.house_view import house_view_findings, load_house_view
from uro.enrich.market import build_snapshot, fetch_prices, load_sector_proxies, resolve_tickers
from uro.enrich.news import fetch_news
from uro.ingest import ReferenceIndex
from uro.models import ClientIntent, FactSheet, MarketSnapshot

logger = logging.getLogger(__name__)

__all__ = [
    "build_snapshot",
    "check_intents",
    "enrich_fact_sheet",
    "fetch_news",
    "fetch_prices",
    "house_view_findings",
    "load_house_view",
    "resolve_tickers",
]


def enrich_fact_sheet(
    fs: FactSheet,
    market: MarketSnapshot | None = None,
    house_view: dict[str, Any] | None = None,
    ref: ReferenceIndex | None = None,
    intents: list[ClientIntent] | None = None,
    client: dict[str, Any] | None = None,
) -> FactSheet:
    """Enriches a pure FactSheet with external market news, house view findings, and CRM intent findings.

    Orchestration:
      1. House View: compares portfolio allocation with CIO stance -> adds hv-* findings.
      2. Market Data & News: attaches news-1..6 (MARKET_EVENT) and propagates warnings.
      3. Client Intents: checks CRM intents deterministically (liquidity shortfall, exclusions >= 2%).
      4. Re-scores all findings using `score_findings` so the LLM gets correctly prioritized items.
    """
    # 1. House View Findings
    try:
        if house_view is None:
            hv_path = Path("data/house_view.json")
            if hv_path.exists():
                house_view = load_house_view(hv_path)

        if house_view:
            hv_items = house_view_findings(fs, house_view, ref)
            fs.findings.extend(hv_items)
            fs.coverage["house_view"] = "ok"
        else:
            fs.coverage["house_view"] = "no_data"
    except Exception as exc:
        logger.warning("House view enrichment failed for %s: %s", fs.client_ref, exc)
        fs.coverage["house_view"] = f"error: {type(exc).__name__}"

    # 2. Market Snapshot & News
    try:
        if market:
            if market.news:
                fs.findings.extend(market.news)
            for w in market.warnings:
                if w not in fs.warnings:
                    fs.warnings.append(w)
            fs.coverage["market"] = market.source
        else:
            fs.coverage["market"] = "not_provided"
    except Exception as exc:
        logger.warning("Market enrichment failed for %s: %s", fs.client_ref, exc)
        fs.coverage["market"] = f"error: {type(exc).__name__}"

    # 2b. Performance drivers & market comparison (A3)
    try:
        if market and market.prices:
            proxies_map = load_sector_proxies()
            drivers = driver_findings(fs, market)
            comps = market_comparison_findings(fs, market, drivers, proxies_map)
            fs.findings.extend(drivers)
            fs.findings.extend(comps)
            fs.coverage["drivers"] = "ok" if (drivers or comps) else "no_data"
        else:
            fs.coverage["drivers"] = "no_data"
    except Exception as exc:
        logger.warning("Driver & market comparison enrichment failed for %s: %s", fs.client_ref, exc)
        fs.coverage["drivers"] = f"error: {type(exc).__name__}"

    # 3. Intent Findings
    try:
        if intents:
            fs.intents = intents
            intent_items = check_intents(intents, fs, ref, client)
            fs.findings.extend(intent_items)
            fs.coverage["intents"] = "ok"
    except Exception as exc:
        logger.warning("Intent enrichment failed for %s: %s", fs.client_ref, exc)
        fs.coverage["intents"] = f"error: {type(exc).__name__}"

    # 4. Re-score & Re-rank all findings
    try:
        fs.findings = score_findings(fs.findings, fs)
    except Exception as exc:
        logger.warning("Re-scoring findings failed for %s: %s", fs.client_ref, exc)

    return fs
