"""OWNER: JACOB — Soll-Ist-Vergleich gegen die Strategic Asset Allocation.

Zwei Fallen:
  - Für den Vergleich die SAA_*-Felder benutzen (SAA_AssetClassName etc.),
    nicht die feineren AssetClassName-Felder. Die matchen die Targets nicht.
  - Prozente in Positionen und SAA-Targets sind Brueche 0-1.
    FundUnbundlingMappings[].Weight ist dagegen 0-100.
"""

from __future__ import annotations

from uro.models import AllocationLine, Finding


def build_allocation(portfolio, reference) -> list[AllocationLine]:
    """Ist-Allokation vs. Target, über alle 4 Dimensionen, inkl. Fonds-Look-through."""
    raise NotImplementedError


def saa_findings(allocation: list[AllocationLine]) -> list[Finding]:
    raise NotImplementedError
