"""Loader, PII-Strip, ReferenceIndex — die Stellen, an denen die Datenfallen zuschlagen."""

from __future__ import annotations

import json
from datetime import date

import pytest

from uro.ingest import (
    ReferenceIndex,
    age_years,
    client_data_as_of,
    client_history_as_of,
    display_name,
    extract_clients,
    get,
    load_clients,
    lst,
    parse_date,
    strip_pii,
)


def test_get_and_lst_treat_null_like_missing():
    obj = {"a": None, "b": [1], "c": "x"}
    assert get(obj, "a", "d") == "d"
    assert get(obj, "missing", "d") == "d"
    assert get(None, "a", "d") == "d"
    assert lst(obj, "a") == []
    assert lst(obj, "b") == [1]
    assert lst(obj, "c") == []  # kein Listentyp → leere Liste, keine Exception


def test_parse_date_accepts_date_and_datetime_strings():
    assert parse_date("2026-07-01") == date(2026, 7, 1)
    assert parse_date("2026-06-12T10:00:00Z") == date(2026, 6, 12)
    assert parse_date(None) is None
    assert parse_date("not a date") is None


def test_extract_clients_accepts_array_wrapper_and_single_object():
    one = {"ClientRef": "CASE-X", "ClientId": 1}
    assert extract_clients([one]) == [one]
    assert extract_clients({"clients": [one]}) == [one]
    assert extract_clients({"Clients": [one]}) == [one]
    assert extract_clients(one) == [one]
    assert extract_clients({"Securities": []}) is None  # Referenzdatei ist keine Klientendatei
    assert extract_clients("nonsense") is None


def test_load_clients_wrapper_file(tmp_path):
    path = tmp_path / "upload.json"
    path.write_text(json.dumps({"clients": [{"ClientRef": "CASE-U1", "ClientId": 7, "FirstName": "A", "LastName": "B"}]}))
    clients = load_clients(path)
    assert [c["ClientRef"] for c in clients] == ["CASE-U1"]
    assert "FirstName" not in clients[0]  # strip_pii lief


def test_load_clients_rejects_reference_file(tmp_path):
    path = tmp_path / "reference.json"
    path.write_text(json.dumps({"Securities": []}))
    with pytest.raises(ValueError):
        load_clients(path)


def test_strip_pii_removes_keys_and_keeps_display_name_and_age(mini_clients):
    ron = next(c for c in mini_clients if c["ClientRef"] == "CASE-A01")
    for key in ("FirstName", "LastName", "Birthday", "IBAN"):
        assert key not in ron
    assert ron["_DisplayName"] == "Ron Burgundy"
    assert ron["_Age"] == 58  # geboren 1968-05-01, data_as_of 2026-09-10 (jüngste Notiz)


def test_strip_pii_handles_company_without_names(mini_clients):
    company = next(c for c in mini_clients if c["ClientRef"] == "CASE-C03")
    assert company["_DisplayName"] == "Company 009 AG"
    assert company["_Age"] is None


def test_strip_pii_is_recursive_and_does_not_mutate_input():
    raw = {"ClientRef": "CASE-Z", "FirstName": "X", "LastName": "Y", "Portfolios": [{"AccountPositions": [{"IBAN": "CH93 0000", "Currency": "CHF"}]}]}
    out = strip_pii(raw)
    assert "IBAN" not in out["Portfolios"][0]["AccountPositions"][0]
    assert raw["Portfolios"][0]["AccountPositions"][0]["IBAN"] == "CH93 0000"


def test_display_name_falls_back_to_client_ref():
    assert display_name({"ClientRef": "CASE-9"}) == "CASE-9"
    assert display_name({"ClientRef": "CASE-9", "Company": "ACME AG"}) == "ACME AG"


def test_age_years():
    assert age_years("1968-05-01", date(2026, 9, 10)) == 58
    assert age_years("1968-09-11", date(2026, 9, 10)) == 57  # Geburtstag noch nicht erreicht
    assert age_years(None, date(2026, 9, 10)) is None
    assert age_years("1968-05-01", None) is None


def test_time_anchors(mini_clients):
    ron = next(c for c in mini_clients if c["ClientRef"] == "CASE-A01")
    assert client_history_as_of(ron) == date(2026, 7, 1)
    assert client_data_as_of(ron) == date(2026, 9, 18)  # FactoryDateUtc ist das jüngste Datum


def test_reference_index_divides_unbundling_weight_exactly_once(ref_index: ReferenceIndex):
    rows = ref_index.unbundling_by_fund_id[103]
    assert len(rows) == 4
    assert abs(sum(r["Weight"] for r in rows) - 1.0) < 1e-9  # 40+30+20+10 = 100 → 1.0


def test_reference_index_lookups(ref_index: ReferenceIndex):
    assert ref_index.security(101)["Name"].startswith("Chocoladefabriken")
    assert ref_index.security(999) == {}
    assert ref_index.rules_by_code["Compliance with maximum volatility"]["Level"] == 2
    assert ref_index.risk_profile(17)["MaxVola"] == 0.12
    assert ref_index.esg_profile(1)["MinimumLevel"] == 5.714
    assert ref_index.recommended_security_ids == {101, 104}


def test_reference_index_isin_prefers_chf_tranche(ref_index: ReferenceIndex):
    tranches = ref_index.securities_by_isin["LU0000000001"]
    assert [t["Currency"] for t in tranches] == ["CHF", "USD"]
    assert ref_index.security_by_isin("LU0000000001")["Id"] == 103


def test_to_float_rejects_bool_and_garbage():
    from uro.ingest import to_float

    assert to_float("12.5") == 12.5
    assert to_float(3) == 3.0
    assert to_float(True) == 0.0  # bool ist keine Zahl
    assert to_float("abc", 1.0) == 1.0
    assert to_float(None, 2.0) == 2.0


def test_engine_view_hides_display_name_but_keeps_age(mini_clients):
    from uro.ingest import engine_view

    ron = next(c for c in mini_clients if c["ClientRef"] == "CASE-A01")
    view = engine_view(ron)
    assert "_DisplayName" not in view
    assert view["_Age"] == 58
    assert "_DisplayName" in ron  # das Original (UI-Datensatz) bleibt unverändert


def test_reference_index_tolerates_missing_collections():
    idx = ReferenceIndex({})
    assert idx.securities_by_id == {}
    assert idx.unbundling_by_fund_id == {}
    assert idx.security_by_isin("X") is None
