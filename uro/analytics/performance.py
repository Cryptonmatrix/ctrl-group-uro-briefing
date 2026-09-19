"""OWNER: JACOB — Performance aus der Historie rechnen.

PerformanceYTD fehlt auf ALLEN 57 Portfolios. Kommt aus PerformanceHistory
(58 Monatspunkte pro Portfolio, Ende 2026-07-01 = `history_as_of`).

Die NAV-Historie enthält Ein- und Auszahlungen — das ist keine reine Anlagerendite.
Steht so im Finding, damit das LLM es sagen kann.

Es gibt KEINE Positions-Historie. Die Treiber-Analyse (welche Position hat es getrieben)
kommt in Auftrag A3 als gekennzeichnete Näherung über yfinance-Kurse.
"""

from __future__ import annotations

from datetime import date

from uro.analytics.format import date_str, num, pct
from uro.config import PERF_NEGATIVE_3M, PERF_POSITIVE_3M
from uro.models import Finding, FindingType, PerformancePoint, Severity

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
