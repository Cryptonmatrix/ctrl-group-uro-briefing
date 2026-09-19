"""OWNER: JACOB — Performance aus der Historie rechnen.

PerformanceYTD fehlt auf ALLEN 57 Portfolios. Kommt aus PerformanceHistory
(58 Monatspunkte pro Portfolio, Ende 2026-07-01 = `history_as_of`).

Die NAV-Historie enthält Ein- und Auszahlungen — das ist keine reine Anlagerendite.
Steht so im Finding, damit das LLM es sagen kann.

Es gibt KEINE Positions-Historie. Die Treiber-Analyse (welche Position hat es getrieben)
kommt in Auftrag A3 als gekennzeichnete Näherung über yfinance-Kurse.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from uro.analytics.format import date_str, num, pct, pp, round_chf, truncate
from uro.analytics.positions import is_cash
from uro.config import (
    DRIVER_MIN_CONTRIBUTION_PP,
    DRIVER_TOP_N,
    PERF_NEGATIVE_3M,
    PERF_POSITIVE_3M,
    PRICE_COVERAGE_WARN,
)
from uro.models import (
    FactSheet,
    Finding,
    FindingType,
    MarketSnapshot,
    PerformancePoint,
    PositionFact,
    Severity,
)

SOURCE = "clients.json › Portfolios[].PerformanceHistory"
MATERIAL_CHANGE_SINCE_CONTACT_PCT = 3.0  # Spec §5.16: Bewegung seit letztem Kontakt > 3 % → Boost ×1.1


def _pct(new: float, old: float) -> float | None:
    """Rendite in Prozent, bewusst NICHT vorgerundet: gerundet wird genau einmal, in format.num()."""
    if not old:
        return None
    return round((new / old - 1) * 100, 6)


def compute_returns(history: list[PerformancePoint]) -> dict[str, float | None]:
    """Gibt {'1m','3m','12m','ytd'} in Prozent. None wo die Historie zu kurz ist — nicht 0.0."""
    if len(history) < 2:
        return {"1m": None, "3m": None, "12m": None, "ytd": None}

    points = sorted(history, key=lambda p: p.date)
    last = points[-1]

    def back(n: int) -> float | None:
        return _pct(last.value, points[-1 - n].value) if len(points) > n else None

    # YTD: letzter Punkt des Vorjahres als Basis
    prior_year = [p for p in points if p.date.year < last.date.year]
    ytd = _pct(last.value, prior_year[-1].value) if prior_year else None

    return {"1m": back(1), "3m": back(3), "12m": back(12), "ytd": ytd}


def return_since(history: list[PerformancePoint], since: date | None) -> float | None:
    """Rendite in Prozent vom letzten Monatspunkt <= `since` bis zum jüngsten Punkt. None, wenn nicht bestimmbar."""
    if since is None or len(history) < 2:
        return None
    points = sorted(history, key=lambda p: p.date)
    base = [p for p in points if p.date <= since]
    if not base or base[-1] is points[-1]:
        return None
    return _pct(points[-1].value, base[-1].value)


def performance_findings(
    portfolio_nr: str,
    returns: dict[str, float | None],
    aum: float,
    as_of: date | None = None,
    since_contact_pct: float | None = None,
    last_contact: date | None = None,
) -> list[Finding]:
    """Ein Finding je Portfolio: perf-<pnr>. Zu kurze Historie → perf-gap-<pnr> (DATA_GAP)."""
    r3 = returns.get("3m")
    r12 = returns.get("12m")
    ytd = returns.get("ytd")

    if r3 is None and r12 is None:
        return [
            Finding(
                id=f"perf-gap-{portfolio_nr}",
                type=FindingType.DATA_GAP,
                severity=Severity.WARNING,
                title=f"Performance not computable for portfolio {portfolio_nr}",
                detail="The NAV history is too short for any period return (fewer than two monthly points).",
                portfolio_nr=portfolio_nr,
                materiality_chf=aum,
                source=SOURCE,
            )
        ]

    numbers = {
        key: num(value)
        for key, value in {"return_3m_pct": r3, "return_12m_pct": r12, "return_ytd_pct": ytd}.items()
        if value is not None
    }
    lead = r3 if r3 is not None else r12
    lead_label = "3 months" if r3 is not None else "12 months"
    if lead > PERF_POSITIVE_3M * 100:
        severity = Severity.OPPORTUNITY
    elif lead < PERF_NEGATIVE_3M * 100:
        severity = Severity.WARNING
    else:
        severity = Severity.INFO

    parts = []
    if r3 is not None:
        parts.append(f"3 months {pct(r3, signed=True)}")
    if r12 is not None:
        parts.append(f"12 months {pct(r12, signed=True)}")
    if ytd is not None:
        parts.append(f"year-to-date {pct(ytd, signed=True)}")

    boost_reasons: list[str] = []
    contact_part = ""
    if since_contact_pct is not None and last_contact is not None:
        numbers["return_since_contact_pct"] = num(since_contact_pct)
        contact_part = f" Since the last client contact ({date_str(last_contact)}): {pct(since_contact_pct, signed=True)}."
        if abs(since_contact_pct) > MATERIAL_CHANGE_SINCE_CONTACT_PCT:
            boost_reasons.append("material change since last contact")

    return [
        Finding(
            id=f"perf-{portfolio_nr}",
            type=FindingType.PERFORMANCE,
            severity=severity,
            title=f"Portfolio {portfolio_nr} {pct(lead, signed=True)} over {lead_label}",
            detail=(
                f"{', '.join(parts)} (portfolio data as of {date_str(as_of)})."
                + contact_part
                + " Computed from the monthly NAV history; it includes cash flows, so it is not a pure investment return."
            ),
            numbers=numbers,
            portfolio_nr=portfolio_nr,
            boost_reasons=boost_reasons,
            materiality_chf=abs(lead) / 100 * aum,
            source=SOURCE,
        )
    ]


def _weight(p: PositionFact) -> float:
    return p.client_weight_pct if p.client_weight_pct is not None else p.weight_pct


def driver_findings(fs: FactSheet, market: MarketSnapshot | None) -> list[Finding]:
    """Berechnet Positions-Treiber (drv-*) und Kursabdeckung (gap-prices) aus einem MarketSnapshot."""
    if market is None or not market.prices or not fs.portfolios:
        return []

    positions = [p for pf in fs.portfolios for p in pf.positions]
    securities = [p for p in positions if not is_cash(p)]
    if not securities:
        return []

    # Aggregation je security_id über Portfolios hinweg
    agg: dict[int, dict] = defaultdict(lambda: {"weight": 0.0, "amount": 0.0, "name": "", "pos": None})
    for p in securities:
        a = agg[p.security_id]
        a["weight"] += _weight(p)
        a["amount"] += p.amount_chf
        a["name"] = a["name"] or p.name
        if a["pos"] is None:
            a["pos"] = p

    total_invested = sum(a["amount"] for a in agg.values())
    uncovered_amount = 0.0
    priced_drivers: list[tuple[int, dict, float, float, float]] = []

    for sid, a in agg.items():
        ticker = market.tickers.get(sid)
        ps = market.prices.get(ticker) if ticker else None
        r = ps.return_pct() if ps else None
        if r is not None:
            w = a["weight"]
            c = num(w * r / 100)
            priced_drivers.append((sid, a, w, r, c))
        else:
            uncovered_amount += a["amount"]

    candidates = [item for item in priced_drivers if abs(item[4]) >= DRIVER_MIN_CONTRIBUTION_PP]
    negatives = sorted([item for item in candidates if item[4] < 0], key=lambda x: x[4])[:DRIVER_TOP_N]
    positives = sorted([item for item in candidates if item[4] > 0], key=lambda x: -x[4])[:DRIVER_TOP_N]

    out: list[Finding] = []
    d = date_str(market.as_of)
    driver_source = "yfinance 3-month closes × clients.json positions"

    for sid, a, w, r, c in negatives:
        name = truncate(a["name"], 60)
        weight_val = num(w)
        ret_val = num(r)
        contrib_val = num(c)
        out.append(
            Finding(
                id=f"drv-{sid}",
                type=FindingType.PERFORMANCE_DRIVER,
                severity=Severity.WARNING,
                title=f"{name}: ≈ {pp(contrib_val)} contribution over the last 3 months",
                detail=(
                    f"{name} ({pct(weight_val)} of client assets) {pct(ret_val, signed=True)} "
                    f"over the last 3 months (market data as of {d}). "
                    "Approximation: current weight × price change, flows not included."
                ),
                numbers={"weight_pct": weight_val, "return_3m_pct": ret_val, "contribution_pp": contrib_val},
                materiality_chf=round_chf(a["amount"]),
                security_ids=[sid],
                source=driver_source,
            )
        )

    for sid, a, w, r, c in positives:
        name = truncate(a["name"], 60)
        weight_val = num(w)
        ret_val = num(r)
        contrib_val = num(c)
        out.append(
            Finding(
                id=f"drv-{sid}",
                type=FindingType.PERFORMANCE_DRIVER,
                severity=Severity.OPPORTUNITY,
                title=f"{name}: ≈ {pp(contrib_val)} contribution over the last 3 months",
                detail=(
                    f"{name} ({pct(weight_val)} of client assets) {pct(ret_val, signed=True)} "
                    f"over the last 3 months (market data as of {d}). "
                    "Approximation: current weight × price change, flows not included."
                ),
                numbers={"weight_pct": weight_val, "return_3m_pct": ret_val, "contribution_pp": contrib_val},
                materiality_chf=round_chf(a["amount"]),
                security_ids=[sid],
                source=driver_source,
            )
        )

    if total_invested > 0:
        u = num((uncovered_amount / total_invested) * 100)
        if u > num(PRICE_COVERAGE_WARN * 100):
            covered = num(100.0 - u)
            out.append(
                Finding(
                    id="gap-prices",
                    type=FindingType.DATA_GAP,
                    severity=Severity.INFO,
                    title=f"Price history unavailable for {pct(u)} of invested assets",
                    detail=f"Driver analysis covers {pct(covered)} of invested assets (holdings with a resolvable ticker and price history).",
                    numbers={"uncovered_pct": u, "covered_pct": covered},
                    materiality_chf=round_chf(uncovered_amount),
                    source=driver_source,
                )
            )

    return out
