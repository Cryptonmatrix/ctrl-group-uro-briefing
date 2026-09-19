"""Tests für den Upload-Merge im DataStore (Auftrag A4)."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from uro.ingest import clients_from_payload
from uro.store import DataStore

FIXTURES = Path(__file__).parent / "fixtures"


def test_clients_from_payload_direct() -> None:
    raw = _load_raw_mini_clients()
    res = clients_from_payload(raw)
    assert res is not None
    assert len(res) == len(raw)
    assert clients_from_payload({"unknown": 123}) is None


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    shutil.copy(FIXTURES / "mini_clients.json", tmp_path / "clients.json")
    shutil.copy(FIXTURES / "mini_reference.json", tmp_path / "reference.json")
    return DataStore(tmp_path)


def _load_raw_mini_clients() -> list[dict[str, Any]]:
    return json.loads((FIXTURES / "mini_clients.json").read_text(encoding="utf-8"))


def assert_no_pii(obj: Any) -> None:
    if isinstance(obj, dict):
        for k in ("IBAN", "Birthday", "FirstName", "LastName"):
            assert k not in obj, f"PII key '{k}' found in dict"
        for v in obj.values():
            assert_no_pii(v)
    elif isinstance(obj, list):
        for item in obj:
            assert_no_pii(item)


# 1. Array mit neuem Klienten TEST-001
def test_upload_new_client_array(store: DataStore) -> None:
    raw = _load_raw_mini_clients()
    client = copy.deepcopy(raw[0])
    client["ClientRef"] = "TEST-001"
    client["ClientId"] = 99001

    res = store.merge([client], "test_new.json")

    assert res.added_client_refs == ["TEST-001"]
    assert res.updated_client_refs == []
    assert res.errors == []
    first = store.list_clients()[0]
    assert first.client_ref == "TEST-001"
    assert first.is_new is True
    assert store.fact_sheet("TEST-001") is not None


# 2. Bekannte CASE-A01 mit geänderter AssetsUnderManagementInDefaultCurrency
def test_upload_update_existing_client(store: DataStore) -> None:
    orig_fs = store.fact_sheet("CASE-A01")
    assert orig_fs is not None

    raw = _load_raw_mini_clients()
    client = copy.deepcopy(raw[0])
    assert client["ClientRef"] == "CASE-A01"
    client["AssetsUnderManagementInDefaultCurrency"] = 5000000.0
    for p in client.get("Portfolios") or []:
        p["AssetsUnderManagementInDefaultCurrency"] = 5000000.0

    res = store.merge([client], "test_update.json")

    assert res.updated_client_refs == ["CASE-A01"]
    assert res.added_client_refs == []
    assert len(store.clients) == 3
    new_fs = store.fact_sheet("CASE-A01")
    assert new_fs is not None
    assert new_fs.total_aum_chf == 5000000.0


# 3. Alle Formen: {"clients": [...]}, {"Clients": [...]}, einzelnes Objekt mit ClientRef
def test_upload_all_formats(store: DataStore) -> None:
    raw = _load_raw_mini_clients()

    c1 = copy.deepcopy(raw[0])
    c1["ClientRef"] = "TEST-FMT-1"
    c1["ClientId"] = 99101
    res1 = store.merge({"clients": [c1]}, "fmt1.json")
    assert res1.added_client_refs == ["TEST-FMT-1"]

    c2 = copy.deepcopy(raw[0])
    c2["ClientRef"] = "TEST-FMT-2"
    c2["ClientId"] = 99102
    res2 = store.merge({"Clients": [c2]}, "fmt2.json")
    assert res2.added_client_refs == ["TEST-FMT-2"]

    c3 = copy.deepcopy(raw[0])
    c3["ClientRef"] = "TEST-FMT-3"
    c3["ClientId"] = 99103
    res3 = store.merge(c3, "fmt3.json")
    assert res3.added_client_refs == ["TEST-FMT-3"]


# 4. PII: Der Klient bekommt IBAN in AccountPositions, FirstName, LastName, Birthday
def test_upload_pii_stripped(store: DataStore) -> None:
    raw = _load_raw_mini_clients()
    client = copy.deepcopy(raw[0])
    client["ClientRef"] = "TEST-PII"
    client["ClientId"] = 99201
    client["FirstName"] = "Hans"
    client["LastName"] = "Muster"
    client["Birthday"] = "1985-06-15"
    if client.get("Portfolios") and client["Portfolios"][0].get("AccountPositions"):
        client["Portfolios"][0]["AccountPositions"][0]["IBAN"] = "CH9300000000000000000"

    res = store.merge([client], "test_pii.json")
    assert res.added_client_refs == ["TEST-PII"]

    c = store.get_client("TEST-PII")
    assert c is not None
    assert_no_pii(c)

    rec = store.record("TEST-PII")
    assert rec is not None
    assert rec.get("_DisplayName") == "Hans Muster"
