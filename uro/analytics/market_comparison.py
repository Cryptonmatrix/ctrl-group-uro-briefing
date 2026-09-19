"""OWNER: JACOB — Marktvergleich: ist ein Rückgang titelspezifisch, sektor- oder marktweit?

Rechnet deterministisch aus den 3-Monats-Kursen der Position, des Sektor-Proxys
und des Markt-Proxys (Spec §5.5).
Pure: kein Netz, keine I/O.
"""

from __future__ import annotations

from uro.analytics.format import date_str, num, pct, truncate
from uro.analytics.positions import is_cash
from uro.config import (
    MARKET_PROXIES,
    MARKET_WIDE_RET,
    SECTOR_WIDE_MARKET_RET_FLOOR,
    SECTOR_WIDE_SECTOR_RET,
    STOCK_SPECIFIC_GAP_PP,
)
from uro.models import FactSheet, Finding, FindingType, MarketSnapshot, PositionFact, Severity

SOURCE = "yfinance 3-month closes × clients.json positions"


def proxy_tickers(
    fs: FactSheet,
    tickers: dict[int, str],
    sector_proxies: dict[str, str],
) -> list[str]:
    """Liefert die benötigten Markt- und Sektor-Proxy-Ticker für alle bepreisten Positionen."""
    if not fs.portfolios or not tickers:
        return []

    proxies: set[str] = set()
    positions = [p for pf in fs.portfolios for p in pf.positions if not is_cash(p)]

    for p in positions:
        if p.security_id not in tickers:
            continue

        # Markt-Proxy nach Währung
        mt = MARKET_PROXIES.get(p.currency, MARKET_PROXIES["default"])
        proxies.add(mt)

        # Sektor-Proxy nach Industrie oder Sektor
        st = sector_proxies.get(p.industry) if p.industry else None
        if not st and p.sector:
            st = sector_proxies.get(p.sector)
        if st:
            proxies.add(st)

    return sorted(proxies)


def market_comparison_findings(
    fs: FactSheet,
    market: MarketSnapshot | None,
    drivers: list[Finding],
    sector_proxies: dict[str, str],
) -> list[Finding]:
    """Klassifiziert Rückgänge negativer Treiber in sector-wide, market-wide, stock-specific oder mixed."""
    if market is None or not market.prices or not drivers or not fs.portfolios:
        return []

    negative_drivers = [
        f
        for f in drivers
        if f.type == FindingType.PERFORMANCE_DRIVER
        and f.severity == Severity.WARNING
        and f.id.startswith("drv-")
    ]
    if not negative_drivers:
        return []

    positions = [p for pf in fs.portfolios for p in pf.positions if not is_cash(p)]
    by_sid: dict[int, PositionFact] = {}
    for p in positions:
        if p.security_id not in by_sid:
            by_sid[p.security_id] = p

    out: list[Finding] = []
    d = date_str(market.as_of)

    sector_threshold = SECTOR_WIDE_SECTOR_RET * 100  # -5.0 %
    market_floor = SECTOR_WIDE_MARKET_RET_FLOOR * 100  # -3.0 %
    market_threshold = MARKET_WIDE_RET * 100  # -5.0 %
    stock_gap = STOCK_SPECIFIC_GAP_PP  # -10.0 pp

    for f in negative_drivers:
        sid = f.security_ids[0] if f.security_ids else None
        if sid is None or sid not in by_sid:
            continue
        pos = by_sid[sid]

        # Markt-Proxy
        mt = MARKET_PROXIES.get(pos.currency, MARKET_PROXIES["default"])
        market_ps = market.prices.get(mt)
        mr = market_ps.return_pct() if market_ps else None
        if mr is None:
            # Fehlen die Markt-Proxy-Kurse, entsteht kein mkt-Finding
            continue

        # Sektor-Proxy
        industry = pos.industry or pos.sector or "Sector"
        st = sector_proxies.get(pos.industry) if pos.industry else None
        if not st and pos.sector:
            st = sector_proxies.get(pos.sector)
        sector_ps = market.prices.get(st) if st else None
        sr = sector_ps.return_pct() if sector_ps else None

        # Position return (aus Finding numbers oder PriceSeries)
        r = f.numbers.get("return_3m_pct")
        if r is None:
            ticker = market.tickers.get(sid)
            ps = market.prices.get(ticker) if ticker else None
            r = ps.return_pct() if ps else None
        if r is None:
            continue

        # Klassifikation nach Spec §5.5
        label: str | None
        if sr is not None:
            if sr <= sector_threshold and mr > market_floor:
                label = "sector-wide"
            elif mr <= market_threshold:
                label = "market-wide"
            elif r - sr <= stock_gap:
                label = "stock-specific"
            else:
                label = "mixed"
        else:
            # Fehlen nur die Sektor-Kurse: Regeln 2 und 3, kein mixed
            if mr <= market_threshold:
                label = "market-wide"
            elif r - mr <= stock_gap:
                label = "stock-specific"
            else:
                label = None

        if label is None:
            continue

        name = truncate(pos.name, 60)
        mkt_id = f"mkt-{sid}"
        title = f"{name} decline is {label}"

        if sr is not None and st is not None:
            detail = (
                f"{name} {pct(r, signed=True)} vs. sector proxy {st} ({industry}) "
                f"{pct(sr, signed=True)} and market proxy {mt} {pct(mr, signed=True)} "
                f"over the last 3 months (market data as of {d})."
            )
            numbers = {
                "return_3m_pct": num(r),
                "sector_return_3m_pct": num(sr),
                "market_return_3m_pct": num(mr),
            }
        else:
            detail = (
                f"{name} {pct(r, signed=True)} vs. market proxy {mt} {pct(mr, signed=True)} "
                f"over the last 3 months (market data as of {d})."
            )
            numbers = {
                "return_3m_pct": num(r),
                "market_return_3m_pct": num(mr),
            }

        mkt_finding = Finding(
            id=mkt_id,
            type=FindingType.MARKET_COMPARISON,
            severity=Severity.INFO,
            title=title,
            detail=detail,
            numbers=numbers,
            materiality_chf=f.materiality_chf,
            security_ids=[sid],
            source=SOURCE,
            related_ids=[f.id],
        )

        # Bidirektionale Verknüpfung
        if mkt_id not in f.related_ids:
            f.related_ids.append(mkt_id)

        out.append(mkt_finding)

    return out
