"""OWNER: JACOB — Verstösse und Risikoprofil-Abgleich.

Hier sitzt der stärkste Befund des Projekts (siehe CLAUDE.md §4):
14 Portfolios reissen das Volatilitätslimit ihres Risikoprofils, bei 11 davon
meldet die Suitability-Engine null Verstösse — weil ihnen keine Strategie
zugewiesen ist und die SAA-Regeln deshalb nie feuern.

Wir rechnen unabhaengig davon.
"""

from __future__ import annotations

from typing import Any

from uro.ingest import get, lst
from uro.models import Finding, FindingType, Severity


def violation_findings(client: dict[str, Any], aum: float) -> list[Finding]:
    """Aus SuitabilityViolations[]. Feld ist bei 20 von 47 Klienten null."""
    out: list[Finding] = []
    for i, v in enumerate(lst(client, "SuitabilityViolations")):
        is_error = get(v, "Severity") == "Error"
        out.append(Finding(
            id=f"viol-{i}", type=FindingType.SUITABILITY_VIOLATION,
            severity=Severity.ERROR if is_error else Severity.WARNING,
            title=str(get(v, "RuleCode", "Regelverstoss")),
            detail=str(get(v, "RuleDescription", "")),
            portfolio_nr=str(get(v, "PortfolioId", "")),
            materiality_chf=aum * (0.3 if is_error else 0.1),
        ))
    return out


def risk_profile_findings(
    client: dict[str, Any], portfolio: dict[str, Any], profile: dict[str, Any] | None, aum: float
) -> list[Finding]:
    """Volatilität gegen RiskProfiles[].MaxVola — unabhaengig von der Regel-Engine."""
    pnr = str(get(portfolio, "PortfolioNr", "?"))
    vola = get(portfolio, "Volatility")
    max_vola = get(profile, "MaxVola") if profile else None

    if profile is None:
        return [Finding(
            id=f"gap-profile-{pnr}", type=FindingType.DATA_GAP, severity=Severity.WARNING,
            title="Kein Risikoprofil hinterlegt",
            detail="Ohne Risikoprofil lässt sich die Angemessenheit nicht prüfen.",
            portfolio_nr=pnr, materiality_chf=aum,
        )]
    if vola is None:
        return [Finding(
            id=f"gap-vola-{pnr}", type=FindingType.DATA_GAP, severity=Severity.WARNING,
            title="Volatilität nicht berechnet",
            detail=f"Für {pnr} liegt keine Volatilität vor, Limitprüfung nicht möglich.",
            portfolio_nr=pnr, materiality_chf=aum,
        )]
    if max_vola is None or vola <= max_vola:
        return []

    over = (vola / max_vola - 1) * 100
    reported = len(lst(client, "SuitabilityViolations"))
    blind = " Die Regel-Engine meldet dazu keinen Verstoss." if reported == 0 else ""
    return [Finding(
        id=f"risk-breach-{pnr}", type=FindingType.SUITABILITY_VIOLATION, severity=Severity.ERROR,
        title=(f"Volatilität {vola * 100:.1f}% überschreitet das Profillimit "
               f"von {max_vola * 100:.1f}%"),
        detail=(f"Das Portfolio liegt {over:.0f}% über der Obergrenze des Profils "
                f"{get(profile, 'Name', '')}.{blind}"),
        numbers={"volatility_pct": round(vola * 100, 1),
                 "max_volatility_pct": round(max_vola * 100, 1),
                 "overshoot_pct": round(over, 0)},
        portfolio_nr=pnr, materiality_chf=aum,
    )]
