"""OWNER: JACOB — Verstoesse und Risikoprofil-Abgleich.

180 Verstoesse bei 26 Klienten. ABER: 20 Klienten haben SuitabilityViolations: null,
4 haben RiskProfileId: null. 7 Portfolios haben kein Volatility-Feld.

Fehlende Daten werden zu einem DATA_GAP-Finding, niemals zu einer Exception
und niemals zu einem stillen Fallback.
"""

from __future__ import annotations

from uro.models import Finding


def violation_findings(client, reference) -> list[Finding]:
    raise NotImplementedError


def risk_profile_findings(client, portfolio, reference) -> list[Finding]:
    """Volatilitaet gegen RiskProfiles[].MaxVola. Fehlt eins von beiden -> DATA_GAP."""
    raise NotImplementedError
