"""Regressionstests zu den Review-Befunden (P1 #1–#8, #17): jeder Fall ist ein reproduzierter Fehler."""

from __future__ import annotations

import json
import shutil

from uro.enrich.house_view import house_view_findings, load_house_view
from uro.ingest import strip_pii
from uro.llm.validator import validate
from uro.models import ActionKind, Briefing, LikelyQuestion, NextBestAction, Section, Statement, StatementType
from uro.store import DataStore

FIX = "tests/fixtures"


def _briefing(statements, actions, headline="Portfolio overview", questions=()) -> Briefing:
    return Briefing(
        headline=headline,
        sections=[Section(title="Recent Portfolio Development", statements=statements)],
        likely_questions=list(questions),
        next_best_actions=actions,
    )


def test_invented_buy_action_is_removed(fact_sheets):
    """#1: 'Buy CHF 987654 of an invented security' mit Referenz profile wurde akzeptiert."""
    fs = fact_sheets["CASE-A01"]
    b = _briefing(
        [
            Statement(
                text="Volatility is 20.0% against a 12.0% limit.",
                type=StatementType.RISK,
                finding_ids=["risk-breach-CASE-A01-01"],
            )
        ],
        [
            NextBestAction(
                action="Buy CHF 987654 of Invented Fund",
                rationale="Diversify.",
                finding_ids=["profile"],
                priority=1,
                kind=ActionKind.BUY,
            ),
            NextBestAction(
                action="Buy Invented Fund",
                rationale="Diversify.",
                finding_ids=["profile"],
                priority=2,
                kind=ActionKind.BUY,
            ),
        ],
    )
    b, issues = validate(b, fs)
    assert b.next_best_actions == []
    assert {i.kind for i in issues} >= {"unsupported_number", "unsupported_instrument"}


def test_unit_numbers_and_single_unsupported_number_are_not_waved_through(fact_sheets):
    """#2: '12%' galt als kleine Zahl; eine einzelne unbelegte Zahl blieb im Text; globaler Rückgriff."""
    fs = fact_sheets["CASE-A01"]
    b = _briefing(
        [
            Statement(
                text="Volatility is 9% today.",
                type=StatementType.FACT,
                finding_ids=["risk-breach-CASE-A01-01"],
            ),
            Statement(
                text="Lindt is 73.5% of assets.",
                type=StatementType.FACT,
                finding_ids=["risk-breach-CASE-A01-01"],
            ),
            Statement(
                text="Volatility is 20.0% against a 12.0% limit, 3 months ago.",
                type=StatementType.RISK,
                finding_ids=["risk-breach-CASE-A01-01"],
            ),
        ],
        [
            NextBestAction(
                action="Discuss risk profile",
                rationale="Above limit.",
                finding_ids=["risk-breach-CASE-A01-01"],
                priority=1,
            )
        ],
    )
    b, _ = validate(b, fs)
    kept = [s.text for s in b.sections[0].statements]
    assert kept == [
        "Volatility is 20.0% against a 12.0% limit, 3 months ago."
    ]  # 9% unbelegt; 73.5% aus fremdem Finding


def test_headline_and_questions_are_checked(fact_sheets):
    fs = fact_sheets["CASE-A01"]
    b = _briefing(
        [
            Statement(
                text="Volatility is 20.0%.", type=StatementType.RISK, finding_ids=["risk-breach-CASE-A01-01"]
            )
        ],
        [
            NextBestAction(
                action="Discuss risk profile",
                rationale="Above limit.",
                finding_ids=["risk-breach-CASE-A01-01"],
                priority=1,
            )
        ],
        headline="Portfolio lost 37.7% this year",
        questions=[LikelyQuestion(question="Why 55.5% equities?", answer_hint="Because.")],
    )
    b, _ = validate(b, fs)
    assert "37.7" not in b.headline and b.likely_questions == []


def test_failed_reference_upload_leaves_data_intact(tmp_path, mini_reference):
    """#4: Weight 'invalid' ersetzte die Referenz, danach scheiterte jede Analyse mit ValueError."""
    shutil.copy(f"{FIX}/mini_clients.json", tmp_path / "clients.json")
    shutil.copy(f"{FIX}/mini_reference.json", tmp_path / "reference.json")
    store = DataStore(tmp_path)
    before = store.fact_sheet("CASE-B02")
    row = dict(mini_reference["FundUnbundlingMappings"][0], Weight="invalid")

    res = store.merge({"FundUnbundlingMappings": [row]}, "bad_ref.json")

    assert not res.reference_merged and any("bad_ref.json" in e for e in res.errors)
    store._fact_sheets = {}
    assert store.fact_sheet("CASE-B02").total_aum_chf == before.total_aum_chf  # rechnet weiter


def test_html_in_client_ref_is_rejected(tmp_path):
    """#6: ClientRef landet in innerHTML/Attributen."""
    shutil.copy(f"{FIX}/mini_clients.json", tmp_path / "clients.json")
    shutil.copy(f"{FIX}/mini_reference.json", tmp_path / "reference.json")
    store = DataStore(tmp_path)
    client = json.load(open(f"{FIX}/mini_clients.json"))[0]
    client["ClientRef"] = '<img src=x onerror="alert(1)">'

    res = store.merge(client, "evil.json")

    assert res.added_client_refs == [] and any("invalid ClientRef" in e for e in res.errors)


def test_house_view_invents_no_targets_without_strategy(fact_sheets):
    """#7: ohne SAA wurden 50/30/5-Ziele erfunden."""
    fs = fact_sheets["CASE-A01"]  # "No strategy"
    assert house_view_findings(fs, load_house_view("data/house_view.json")) == []


def test_needed_cash_is_not_offered_as_investable(mini_clients, mini_reference):
    """#8: liq-cash nannte Geld anlegbar, das liq-need als benötigt ausweist; erledigte Zahlungen zählten."""
    import copy

    from uro.analytics import build_fact_sheet

    client = copy.deepcopy(next(c for c in mini_clients if c["ClientRef"] == "CASE-C03"))  # nur Cash
    cash = client["LiquidityInDefaultCurrency"]
    client["ClientNotes"] = [
        {
            "Note": f"Needs CHF {int(cash)} in liquid funds for the tax payment.",
            "CreatedByDateUTC": "2026-09-01T00:00:00Z",
        }
    ]
    fs = build_fact_sheet(client, mini_reference)
    assert "liq-cash" not in fs.by_id()  # alles reserviert

    client["ClientNotes"] = [
        {
            "Note": f"Tax payment of CHF {int(cash)} was already paid from the cash account.",
            "CreatedByDateUTC": "2026-09-01T00:00:00Z",
        }
    ]
    fs = build_fact_sheet(client, mini_reference)
    assert "liq-need" not in fs.by_id()


def test_names_and_ibans_are_scrubbed_from_free_text():
    """#17: strip_pii entfernte nur JSON-Schlüssel; Klarnamen/IBANs in Notizen gingen an den Anbieter."""
    out = strip_pii(
        {
            "ClientRef": "X-1",
            "FirstName": "Ron",
            "LastName": "Burgundy",
            "ClientNotes": [{"Note": "Ron Burgundy asked to pay IBAN CH93 0076 2011 6238 5295 7."}],
        }
    )
    note = out["ClientNotes"][0]["Note"]
    assert "Ron" not in note and "Burgundy" not in note and "CH93" not in note
