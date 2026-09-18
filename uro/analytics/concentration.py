"""OWNER: JACOB — Klumpenrisiken nach Einzeltitel und Sektor.

Wichtig: auch Klumpenrisiken finden, die KEINE Regel meldet. Ron Burgundy haelt
73.4% Lindt bei null gemeldeten Verstoessen.
"""

from __future__ import annotations

from collections import defaultdict

from uro.models import Finding, FindingType, PositionFact, Severity

SINGLE_WARN = 20.0
SINGLE_ERROR = 40.0
SECTOR_WARN = 35.0


def concentration_findings(portfolio_nr: str, positions: list[PositionFact], aum: float) -> list[Finding]:
    out: list[Finding] = []
    if not positions:
        return out

    top = max(positions, key=lambda p: p.weight_pct)
    if top.weight_pct >= SINGLE_WARN:
        severity = Severity.ERROR if top.weight_pct >= SINGLE_ERROR else Severity.WARNING
        out.append(Finding(
            id=f"conc-single-{portfolio_nr}", type=FindingType.CONCENTRATION, severity=severity,
            title=f"{top.weight_pct:.1f}% des Portfolios in einem einzigen Titel: {top.name}",
            detail=(f"{top.name} macht {top.weight_pct:.1f}% aus "
                    f"(CHF {top.amount_chf:,.0f}). Ab {SINGLE_ERROR:.0f}% gilt das als Klumpenrisiko."),
            numbers={"weight_pct": round(top.weight_pct, 1), "amount_chf": round(top.amount_chf, 0)},
            portfolio_nr=portfolio_nr, security_ids=[top.security_id],
            materiality_chf=top.amount_chf,
        ))

    by_sector: dict[str, float] = defaultdict(float)
    for p in positions:
        if p.sector:
            by_sector[p.sector] += p.weight_pct
    if by_sector:
        sector, weight = max(by_sector.items(), key=lambda kv: kv[1])
        if weight >= SECTOR_WARN:
            out.append(Finding(
                id=f"conc-sector-{portfolio_nr}", type=FindingType.CONCENTRATION,
                severity=Severity.WARNING,
                title=f"{weight:.1f}% im Sektor {sector}",
                detail=f"Sektorkonzentration {sector}: {weight:.1f}% des Portfolios.",
                numbers={"sector_weight_pct": round(weight, 1)},
                portfolio_nr=portfolio_nr, materiality_chf=weight / 100 * aum,
            ))
    return out
