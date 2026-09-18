"""OWNER: JACOB — Klumpenrisiken nach Einzeltitel und Sektor (je Portfolio).

Wichtig: auch Klumpenrisiken finden, die KEINE Regel meldet. Ron Burgundy hält
73.5 % Lindt bei null gemeldeten Verstössen.

Stand A1: Levins Logik mit Schwellen aus config.py, englische Texte, Zahlen über format.py,
Konten (Cash/Krypto) zählen nicht als Titel. Auftrag A2 ergänzt Look-through, Währung,
Region und die Spec-Schwellen auf Klientenebene.
"""

from __future__ import annotations

from collections import defaultdict

from uro.analytics.format import chf, num, pct, round_chf, truncate
from uro.analytics.positions import is_cash
from uro.config import (
    CONCENTRATION_LEGACY_SECTOR_WARN_PCT,
    CONCENTRATION_LEGACY_SINGLE_ERROR_PCT,
    CONCENTRATION_LEGACY_SINGLE_WARN_PCT,
)
from uro.models import Finding, FindingType, PositionFact, Severity

SOURCE = "clients.json › Portfolios[].SecurityPositions"


def concentration_findings(portfolio_nr: str, positions: list[PositionFact], aum: float) -> list[Finding]:
    out: list[Finding] = []
    securities = [p for p in positions if not is_cash(p)]
    if not securities:
        return out

    top = max(securities, key=lambda p: p.weight_pct)
    if top.weight_pct >= CONCENTRATION_LEGACY_SINGLE_WARN_PCT:
        severity = Severity.ERROR if top.weight_pct >= CONCENTRATION_LEGACY_SINGLE_ERROR_PCT else Severity.WARNING
        weight = num(top.weight_pct)
        amount = round_chf(top.amount_chf)
        out.append(
            Finding(
                id=f"conc-single-{portfolio_nr}",
                type=FindingType.CONCENTRATION,
                severity=severity,
                title=f"{pct(weight)} of portfolio {portfolio_nr} in a single position: {truncate(top.name, 60)}",
                detail=(
                    f"{truncate(top.name, 60)} is {pct(weight)} of the portfolio ({chf(amount)}). "
                    f"Above {CONCENTRATION_LEGACY_SINGLE_ERROR_PCT:.0f}% a single position counts as a cluster risk."
                ),
                numbers={"weight_pct": weight, "amount_chf": amount},
                portfolio_nr=portfolio_nr,
                security_ids=[top.security_id],
                materiality_chf=top.amount_chf,
                source=SOURCE,
            )
        )

    by_sector: dict[str, float] = defaultdict(float)
    for p in securities:
        if p.sector:
            by_sector[p.sector] += p.weight_pct
    if by_sector:
        sector, weight = max(by_sector.items(), key=lambda kv: kv[1])
        if weight >= CONCENTRATION_LEGACY_SECTOR_WARN_PCT:
            weight = num(weight)
            out.append(
                Finding(
                    id=f"conc-sector-{portfolio_nr}",
                    type=FindingType.CONCENTRATION,
                    severity=Severity.WARNING,
                    title=f"{pct(weight)} of portfolio {portfolio_nr} in sector {sector}",
                    detail=f"Sector concentration: {sector} makes up {pct(weight)} of the portfolio (direct holdings, no fund look-through yet).",
                    numbers={"sector_weight_pct": weight},
                    portfolio_nr=portfolio_nr,
                    security_ids=[p.security_id for p in securities if p.sector == sector],
                    materiality_chf=weight / 100 * aum,
                    source=SOURCE,
                )
            )
    return out
