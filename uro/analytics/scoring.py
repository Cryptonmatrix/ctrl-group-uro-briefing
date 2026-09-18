"""OWNER: JACOB — Priorisierung. Die Antwort auf 'Wie waehlt euer System aus?'

score = severity x materiality x client_relevance
Nur die Top 3-5 kommen ins Briefing, der Rest bleibt im Follow-up-Chat.
"""

from __future__ import annotations

from uro.models import Finding, Severity

SEVERITY_WEIGHT = {Severity.ERROR: 3.0, Severity.WARNING: 2.0, Severity.INFO: 1.0}


def score_findings(findings: list[Finding], total_aum_chf: float) -> list[Finding]:
    base = max(total_aum_chf, 1.0)
    for f in findings:
        materiality = 0.2 + 0.8 * min(1.0, f.materiality_chf / base)
        relevance = 0.5 + 0.5 * f.client_relevance
        f.score = round(SEVERITY_WEIGHT[f.severity] * materiality * relevance, 3)
    return sorted(findings, key=lambda f: f.score, reverse=True)
