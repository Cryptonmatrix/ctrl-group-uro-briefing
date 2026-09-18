"""OWNER: JACOB — Performance aus der Historie rechnen.

PerformanceYTD fehlt auf ALLEN 57 Portfolios. Kommt aus PerformanceHistory
(58 Monatspunkte pro Portfolio).

Es gibt KEINE Positions-Historie. Performance-Attribution waere deshalb eine
Näherung und ist hier bewusst noch nicht drin — siehe PITCH.md §10.
"""

from __future__ import annotations

from uro.models import Finding, FindingType, PerformancePoint, Severity


def _pct(new: float, old: float) -> float | None:
    if not old:
        return None
    return round((new / old - 1) * 100, 2)


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


def performance_findings(portfolio_nr: str, returns: dict[str, float | None], aum: float) -> list[Finding]:
    out: list[Finding] = []
    r3 = returns.get("3m")
    r12 = returns.get("12m")
    ytd = returns.get("ytd")

    if r3 is None and r12 is None:
        return [Finding(
            id=f"perf-gap-{portfolio_nr}", type=FindingType.DATA_GAP, severity=Severity.WARNING,
            title="Performance nicht berechenbar",
            detail="Die Kurshistorie reicht für keine Periodenrendite aus.",
            portfolio_nr=portfolio_nr, materiality_chf=aum,
        )]

    numbers = {k: v for k, v in
               {"return_3m_pct": r3, "return_12m_pct": r12, "return_ytd_pct": ytd}.items()
               if v is not None}
    worst = min((v for v in (r3, r12, ytd) if v is not None), default=0.0)
    severity = Severity.WARNING if worst < -5 else Severity.INFO
    direction = "verloren" if worst < 0 else "zugelegt"

    out.append(Finding(
        id=f"perf-{portfolio_nr}", type=FindingType.PERFORMANCE_DRIVER, severity=severity,
        title=f"Portfolio hat über 3 Monate {r3 if r3 is not None else 0:+.2f}% {direction}",
        detail=(f"3 Monate {r3}%, 12 Monate {r12}%, seit Jahresbeginn {ytd}%. "
                "Gerechnet aus der Monatshistorie, da PerformanceYTD im Datensatz fehlt."),
        numbers=numbers, portfolio_nr=portfolio_nr,
        materiality_chf=abs(worst) / 100 * aum,
    ))
    return out
