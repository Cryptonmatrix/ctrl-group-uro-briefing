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


@pytest.fixture(autouse=True)
def _no_real_llm_keys(monkeypatch):
    """Tests rufen nie die echte API: Schlüssel aus .env und Umgebung werden für jeden Test ausgeblendet.

    Ohne das schickten die Failover-Tests echte Requests, sobald ein Key in .env steht (kostet, dauert,
    und "Anthropic fehlt" war dann nicht mehr simuliert). Tests, die einen Key brauchen, setzen ihn selbst.
    """
    from uro.config import get_settings

    settings = get_settings()
    for name in ("anthropic_api_key", "gemini_api_key", "google_api_key"):
        if hasattr(settings, name):
            monkeypatch.setattr(settings, name, None)
    for var in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)


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
