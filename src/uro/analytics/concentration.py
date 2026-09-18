"""OWNER: JACOB — Klumpenrisiken nach Einzeltitel, Sektor und Waehrung.

Haeufigster Verstoss im Datensatz: 'Cluster risk of a single financial instrument' (23x).
Wichtig: auch Klumpenrisiken finden, die KEINE Regel meldet — das zeigt Urteilsvermoegen.

ContributionVolatility (nicht MarginalContributionToRisk) summiert sich zu Portfolio.Volatility.
Krypto-Konten haben keinen ISO-Waehrungscode (BTC, ETH, SOL, SHIB, OZG).
"""

from __future__ import annotations

from uro.models import Finding


def concentration_findings(portfolio) -> list[Finding]:
    raise NotImplementedError
