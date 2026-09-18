"""OWNER: JACOB — Priorisierung. Das ist die Antwort auf die Jury-Frage
'Wie waehlt euer System aus?'

score = severity x materiality x client_relevance x recency

Nur die Top 3-5 kommen ins Briefing. Der Rest bleibt im Follow-up-Chat abrufbar.
"""

from __future__ import annotations

from uro.models import Finding


def score_findings(findings: list[Finding], total_aum_chf: float) -> list[Finding]:
    """Setzt .score auf jedem Finding und gibt sie sortiert zurueck."""
    raise NotImplementedError
