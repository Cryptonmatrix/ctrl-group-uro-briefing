"""Gemeinsame Fixtures: drei handgebaute Klienten, die die echten Fallen abdecken.

  CASE-A01  Vola 20 % gegen Limit 12 %, "No strategy", 2 Titel + Cash, Notizen (Pension, ESG, risikotolerant)
  CASE-B02  echte SAA, Fonds mit Look-through, gebündelte + überschriebene Verstöße, offene/abgelehnte Proposals, ESG "Yes"
  CASE-C03  Firma ohne Risikoprofil, nur Cash (inkl. BTC), null-Felder, zu kurze Historie
"""

from __future__ import annotations

from pathlib import Path

import pytest

from uro.analytics import build_fact_sheet
from uro.ingest import ReferenceIndex, load_clients, load_reference

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def mini_reference() -> dict:
    return load_reference(FIXTURES / "mini_reference.json")


@pytest.fixture(scope="session")
def mini_clients() -> list[dict]:
    return load_clients(FIXTURES / "mini_clients.json")


@pytest.fixture(scope="session")
def ref_index(mini_reference) -> ReferenceIndex:
    return ReferenceIndex(mini_reference)


@pytest.fixture(scope="session")
def fact_sheets(mini_clients, mini_reference) -> dict:
    return {c["ClientRef"]: build_fact_sheet(c, mini_reference) for c in mini_clients}
