"""OWNER: JACOB — Performance aus der Historie rechnen.

PerformanceYTD fehlt auf ALLEN 57 Portfolios. Muss aus PerformanceHistory kommen
(58 Monatspunkte pro Portfolio, Ende 2026-07-01).

Es gibt KEINE Positions-Historie. Performance-Attribution ist deshalb eine
Naeherung (Gewicht x Kursveraenderung via Yahoo) und muss im UI so heissen.
"""

from __future__ import annotations

from uro.models import Finding, PerformancePoint


def compute_returns(history: list[PerformancePoint]) -> dict[str, float | None]:
    """Gibt {'1m': ..., '3m': ..., '12m': ..., 'ytd': ...} in Prozent zurueck.

    None wo die Historie nicht weit genug zurueckreicht — nicht 0.0.
    """
    raise NotImplementedError


def performance_findings(portfolio, history: list[PerformancePoint]) -> list[Finding]:
    raise NotImplementedError
