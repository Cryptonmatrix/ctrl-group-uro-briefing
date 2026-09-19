"""Upload und Reset über die echte Route: der Weg, den der unbekannte Testklient der Jury nimmt."""

from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

import uro.api as api


@pytest.fixture(scope="module")
def tc():
    with TestClient(api.app) as client:
        yield client


@pytest.fixture(autouse=True)
def _reset(tc):
    tc.post("/api/reset")
    yield
    tc.post("/api/reset")


@pytest.fixture(scope="module")
def test_client_record() -> dict:
    raw = json.load(open("data/clients.json", encoding="utf-8"))
    record = copy.deepcopy(next(c for c in raw if c["ClientRef"] == "CASE-003"))
    record["ClientRef"], record["ClientId"] = "TEST-001", 99001
    return record


def _upload(tc, name: str, payload) -> object:
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return tc.post("/api/upload", files={"file": (name, body, "application/json")})


@pytest.mark.parametrize("shape", ["object", "array", "wrapper"])
def test_every_client_file_shape_adds_the_client(tc, test_client_record, shape):
    payload = {
        "object": test_client_record,
        "array": [test_client_record],
        "wrapper": {"clients": [test_client_record]},
    }[shape]

    r = _upload(tc, "new_client.json", payload)

    assert r.status_code == 200
    assert r.json()["added_client_refs"] == ["TEST-001"]
    assert r.json()["reference_merged"] is False
    first = tc.get("/api/clients").json()[0]
    assert first["ref"] == "TEST-001" and first["is_new"] is True
    assert tc.get("/api/clients/TEST-001/facts").status_code == 200
    assert "Portfolios" not in api._reference  # Klientendaten landen nie in der Referenz


def test_reference_reupload_does_not_double_fund_weights(tc):
    ref = json.load(open("data/reference.json", encoding="utf-8"))
    fund = ref["FundUnbundlingMappings"][0]["FundSecurityId"]
    rows = [row for row in ref["FundUnbundlingMappings"] if row["FundSecurityId"] == fund]

    r = _upload(tc, "reference_update.json", {"FundUnbundlingMappings": rows})

    assert r.status_code == 200 and r.json()["reference_merged"] is True
    total = sum(
        row["Weight"] for row in api._reference["FundUnbundlingMappings"] if row["FundSecurityId"] == fund
    )
    assert total == pytest.approx(100.0, abs=0.01)


def test_broken_file_is_reported_and_reset_restores(tc, test_client_record):
    r = _upload(tc, "broken.json", b"{oops")
    assert r.status_code == 400 and "broken.json" in r.json()["detail"]

    _upload(tc, "new_client.json", [test_client_record])
    assert tc.post("/api/reset").json()["clients"] == 47
    assert all(c["ref"] != "TEST-001" for c in tc.get("/api/clients").json())
