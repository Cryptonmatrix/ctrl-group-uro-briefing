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


# 5. Referenz: Security 101 mit neuem Name und neue Security 106; SuitabilityRules Dedupe
def test_upload_reference_securities_and_rules(store: DataStore) -> None:
    raw_ref = json.loads((FIXTURES / "mini_reference.json").read_text(encoding="utf-8"))
    sec101 = copy.deepcopy(raw_ref["Securities"][0])
    assert sec101["Id"] == 101
    sec101["Name"] = "Lindt Spruengli AG Neu"

    sec106 = copy.deepcopy(sec101)
    sec106["Id"] = 106
    sec106["Isin"] = "CH0010570799"
    sec106["Name"] = "New Security 106"

    rule_dup = {
        "Id": 1,
        "RuleCode": "Cluster risk of a single financial instrument",
        "Description": "Aktualisierte Beschreibung",
        "Level": 2,
        "IsIndividual": False,
    }

    res = store.merge(
        {"Securities": [sec101, sec106], "SuitabilityRules": [rule_dup]},
        "ref_update.json",
    )
    assert res.reference_merged is True
    assert res.errors == []
    assert store.ref.security(106)["Name"] == "New Security 106"
    assert store.ref.security(101)["Name"] == "Lindt Spruengli AG Neu"

    rules = [
        r
        for r in store.reference.get("SuitabilityRules", [])
        if r.get("RuleCode") == "Cluster risk of a single financial instrument"
    ]
    assert len(rules) == 1
    assert rules[0].get("Description") == "Aktualisierte Beschreibung"


# 6. Look-through: Zwei neue Zeilen für Fonds 103 mit Weight 60 und 40
def test_upload_reference_lookthrough_replaces_all_fund_rows(store: DataStore) -> None:
    row1 = {
        "FundSecurityId": 103,
        "FundSecurityIsin": "LU0000000001",
        "AssetClassName": "Equities North America",
        "CurrencyGroupName": "US-Dollar",
        "CountryGroupName": "Equities North America",
        "IndustryName": "Information Technology",
        "Weight": 60.0,
    }
    row2 = {
        "FundSecurityId": 103,
        "FundSecurityIsin": "LU0000000001",
        "AssetClassName": "Equities Switzerland",
        "CurrencyGroupName": "Swiss francs",
        "CountryGroupName": "Equities Switzerland",
        "IndustryName": "Raw materials",
        "Weight": 40.0,
    }

    res = store.merge({"FundUnbundlingMappings": [row1, row2]}, "lookthrough.json")
    assert res.reference_merged is True
    assert res.errors == []

    fund103_rows = store.ref.unbundling_by_fund_id[103]
    assert len(fund103_rows) == 2
    assert sum(r["Weight"] for r in fund103_rows) == pytest.approx(1.0)

    raw_rows = [r for r in store.reference["FundUnbundlingMappings"] if r["FundSecurityId"] == 103]
    assert len(raw_rows) == 2
    assert {r["Weight"] for r in raw_rows} == {60.0, 40.0}


# 7. Veralteter Index: Client mit Position auf Security 999, dann Referenz mit 999 nachladen
def test_upload_reference_updates_cached_index_and_fact_sheets(store: DataStore) -> None:
    raw_clients = _load_raw_mini_clients()
    client = copy.deepcopy(raw_clients[0])
    client["ClientRef"] = "TEST-002"
    client["ClientId"] = 99002
    port = client["Portfolios"][0]
    port["SecurityPositions"].append(
        {
            "SecurityId": 999,
            "Isin": "CH9999999999",
            "Valor": "9999999",
            "SecurityName": "Unknown Corp",
            "Quantity": 10.0,
            "PricePerUnit": 100.0,
            "Currency": "CHF",
            "TotalAmountInPortfolioCurrency": 1000.0,
            "PortfolioValuePercentage": 0.01,
            "MarginalContributionToRisk": 0.0,
            "ContributionVolatility": 0.0,
        }
    )

    res_client = store.merge([client], "client_999.json")
    assert res_client.added_client_refs == ["TEST-002"]

    fs_before = store.fact_sheet("TEST-002")
    assert fs_before is not None
    pos_before = next(p for port in fs_before.portfolios for p in port.positions if p.security_id == 999)
    assert pos_before.saa_asset_class is None

    # Nun Referenz mit Security 999 hochladen
    raw_ref = json.loads((FIXTURES / "mini_reference.json").read_text(encoding="utf-8"))
    sec999 = copy.deepcopy(raw_ref["Securities"][0])
    sec999["Id"] = 999
    sec999["Isin"] = "CH9999999999"
    sec999["Name"] = "Known Corp 999"
    sec999["SAA_AssetClassName"] = "Shares"

    res_ref = store.merge({"Securities": [sec999]}, "ref_999.json")
    assert res_ref.reference_merged is True

    fs_after = store.fact_sheet("TEST-002")
    assert fs_after is not None
    pos_after = next(p for port in fs_after.portfolios for p in port.positions if p.security_id == 999)
    assert pos_after.saa_asset_class == "Shares"


# 8. Fehlerfälle: {"foo": 1}, Klient ohne Ref/Id, merge_files mit bad.json und good.json
def test_upload_error_handling(store: DataStore) -> None:
    # A. Unbekannte Payload-Struktur
    res1 = store.merge({"foo": 1}, "unknown.json")
    assert len(res1.errors) == 1
    assert "unknown.json: not recognised as client or reference data" in res1.errors[0]
    assert len(store.clients) == 3

    # B. Klient ohne ClientRef und ohne ClientId; zweiter Klient ist gültig
    raw_clients = _load_raw_mini_clients()
    bad_client = {"SomeField": "Value"}
    good_client = copy.deepcopy(raw_clients[0])
    good_client["ClientRef"] = "TEST-GOOD-01"
    good_client["ClientId"] = 99401

    res2 = store.merge([bad_client, good_client], "partial.json")
    assert any("partial.json" in e and "missing both" in e for e in res2.errors)
    assert res2.added_client_refs == ["TEST-GOOD-01"]
    assert store.get_client("TEST-GOOD-01") is not None

    # C. merge_files mit ungültigem JSON und gültigem Klienten
    good_client2 = copy.deepcopy(raw_clients[0])
    good_client2["ClientRef"] = "TEST-GOOD-02"
    good_client2["ClientId"] = 99402
    files = [
        ("bad.json", b"{not json"),
        ("good.json", json.dumps(good_client2).encode("utf-8")),
    ]
    res3 = store.merge_files(files)
    assert len(res3.errors) == 1
    assert "bad.json: invalid JSON" in res3.errors[0]
    assert res3.added_client_refs == ["TEST-GOOD-02"]
    assert store.get_client("TEST-GOOD-02") is not None


# 9. Reset: reset() stellt Originalzustand wieder her
def test_upload_reset_restores_original_state(store: DataStore) -> None:
    raw_clients = _load_raw_mini_clients()
    client = copy.deepcopy(raw_clients[0])
    client["ClientRef"] = "TEST-RESET"
    client["ClientId"] = 99501
    store.merge([client], "new_client.json")

    raw_ref = json.loads((FIXTURES / "mini_reference.json").read_text(encoding="utf-8"))
    sec106 = copy.deepcopy(raw_ref["Securities"][0])
    sec106["Id"] = 106
    sec106["Isin"] = "CH0010570799"
    sec106["Name"] = "Sec 106"
    store.merge({"Securities": [sec106]}, "ref_new.json")

    assert store.get_client("TEST-RESET") is not None
    assert store.ref.security(106)["Name"] == "Sec 106"
    assert any(c.is_new for c in store.list_clients())

    # Reset
    store.reset()

    assert len(store.clients) == 3
    assert store.get_client("TEST-RESET") is None
    assert store.ref.security(106) == {}
    assert all(not c.is_new for c in store.list_clients())
