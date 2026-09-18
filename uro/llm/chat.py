"""OWNER: GIANLUCA — Bonus 1: Follow-up-Chat. Fast gratis, das FactSheet existiert schon.

Beispielfragen aus dem Case (das ist gleichzeitig das Testset):
  - What is the client's total semiconductor exposure?
  - Has the client previously raised concerns about volatility?
  - Which positions contribute most to the current risk?
  - How would a proposed rebalancing affect the portfolio allocation?
  - Which open proposal is most relevant to this conversation?

Pflicht: Liegt eine Information nicht vor, sagt der Chat das explizit.
Kriterium 5 bewertet genau das ("handles unavailable information transparently").
"""

from __future__ import annotations

from uro.models import FactSheet


def answer(question: str, fact_sheet: FactSheet, history: list[dict]) -> str:
    raise NotImplementedError
