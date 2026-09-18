"""OWNER: GIANLUCA — Hausmeinung als JSON, einmalig aus einem oeffentlichen CIO-Ausblick.

Format (data/house_view.json):
  {"as_of": "...", "source": "...",
   "views": [{"dimension": "AssetClass", "category": "Shares",
              "stance": "overweight|neutral|underweight", "rationale": "..."}]}

Der Abgleich Portfolio <-> House View ist damit deterministisch.
Pitch-Satz: "In Produktion liefert die Bank dieses JSON aus ihrem CIO-Prozess."
"""

from __future__ import annotations

from uro.models import AllocationLine, Finding


def load_house_view(path: str = "data/house_view.json") -> dict:
    raise NotImplementedError


def house_view_findings(allocation: list[AllocationLine], house_view: dict) -> list[Finding]:
    raise NotImplementedError
