"""OWNER: GIANLUCA — News zu den groessten Positionen, nicht zum Gesamtmarkt.

Zwei Pflichten:
  - Cachen. Die Demo darf nicht an einem Rate Limit scheitern.
  - Offline-Fallback: faellt die Quelle aus, laeuft das Briefing mit dem Hinweis
    "Marktdaten nicht verfuegbar" weiter, statt abzustuerzen.

Bonus fuer die Story: isoliert oder marktweit? Titelrendite vs. Sektor-ETF vs. Index
beantwortet das deterministisch. Das LLM erklaert dann nur noch das Ergebnis.
"""

from __future__ import annotations

from uro.models import Finding, PositionFact


def fetch_news(positions: list[PositionFact], top_n: int = 5) -> list[Finding]:
    raise NotImplementedError
