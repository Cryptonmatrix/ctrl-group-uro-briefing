"""build_fact_sheet über die drei Fixtures: kein Crash, richtige Findings, Coverage sauber."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from uro.analytics import build_fact_sheet
from uro.analytics.positions import is_cash
from uro.ingest import load_clients, load_reference
from uro.models import FindingType, Severity

NUMBER = re.compile(r"-?\d[\d,]*\.?\d*")


def _find(fs, prefix: str):
    hits = [f for f in fs.findings if f.id.startswith(prefix)]
    assert hits, f"kein Finding mit Präfix {prefix!r}; vorhanden: {[f.id for f in fs.findings]}"
    return hits


def test_all_fixtures_build_without_error(fact_sheets):
    assert set(fact_sheets) == {"CASE-A01", "CASE-B02", "CASE-C03"}
    for ref, fs in fact_sheets.items():
        errors = {k: v for k, v in fs.coverage.items() if v.startswith("error")}
        assert not errors, f"{ref}: Detektor-Fehler {errors}"
        assert fs.findings, f"{ref}: keine Findings"
        ids = [f.id for f in fs.findings]
        assert len(ids) == len(set(ids)), f"{ref}: doppelte IDs {ids}"


def test_ranks_are_set_and_sorted(fact_sheets):
    fs = fact_sheets["CASE-A01"]
    scores = [f.score for f in fs.findings]
    assert scores == sorted(scores, reverse=True)
    assert [f.rank for f in fs.findings] == list(range(1, len(fs.findings) + 1))


def test_time_anchors_and_profile_fields(fact_sheets):
    fs = fact_sheets["CASE-A01"]
    assert str(fs.history_as_of) == "2026-07-01"
    assert str(fs.data_as_of) == "2026-09-18"
    assert fs.age == 58
    assert fs.risk_level == 5
    assert fs.max_volatility == 0.12


# --- CASE-A01: der Pitch-Befund ------------------------------------------------


def test_vola_breach_is_risk_profile_error(fact_sheets):
    fs = fact_sheets["CASE-A01"]
    (breach,) = _find(fs, "risk-breach-")
    assert breach.type == FindingType.RISK_PROFILE
    assert breach.severity == Severity.ERROR  # 20 % / 12 % = 1.67 ≥ 1.2
    assert breach.numbers["volatility_pct"] == 20.0
    assert breach.numbers["max_volatility_pct"] == 12.0
    assert "20.0%" in breach.title and "12.0%" in breach.title
    assert "0 violations" in breach.detail or "no violation" in breach.detail.lower()
    assert breach.rank == 1


def test_no_strategy_portfolio_has_no_real_saa(fact_sheets):
    fs = fact_sheets["CASE-A01"]
    assert fs.portfolios[0].has_real_saa is False
    assert fs.portfolios[0].max_volatility == 0.12


def test_notes_are_verbatim_findings_newest_first(fact_sheets):
    fs = fact_sheets["CASE-A01"]
    notes = _find(fs, "note-")
    assert [n.id for n in notes] == ["note-1", "note-2", "note-3"]
    assert notes[0].type == FindingType.CLIENT_NOTE
    assert "ESG-compliant" in notes[0].detail  # jüngste Notiz zuerst
    assert "10 Sep 2026" in notes[0].title
    assert set(fs.note_flags) >= {"retirement", "esg_interest", "risk_tolerant"}
    assert "risk_averse" not in fs.note_flags  # "unconcerned by volatility" ist kein Risikoaversions-Signal


def test_profile_finding_is_pii_free(fact_sheets):
    fs = fact_sheets["CASE-A01"]
    (profile,) = _find(fs, "profile")
    assert profile.type == FindingType.CLIENT_PROFILE
    assert "CASE-A01" in profile.title
    assert "Ron" not in profile.title and "Burgundy" not in profile.detail
    assert "58" in profile.title
    assert profile.numbers["age"] == 58
    assert profile.numbers["max_volatility_pct"] == 12.0


def test_performance_finding_uses_history(fact_sheets):
    fs = fact_sheets["CASE-A01"]
    (perf,) = _find(fs, "perf-CASE-A01-01")
    assert perf.type == FindingType.PERFORMANCE
    assert perf.severity == Severity.OPPORTUNITY  # +6.1 % über 3 Monate
    assert perf.numbers["return_3m_pct"] == 6.1
    assert "+6.1%" in perf.title
    assert "01 Jul 2026" in perf.detail


def test_concentration_ignores_cash(fact_sheets):
    fs = fact_sheets["CASE-C03"]
    assert not [f for f in fs.findings if f.id.startswith("conc-")]
    fs_a = fact_sheets["CASE-A01"]
    (single,) = _find(fs_a, "conc-single-")
    assert single.numbers["weight_pct"] == 73.5
    assert "73.5%" in single.title
    assert single.numbers["amount_chf"] == 102900.0
    assert "CHF 102,900" in single.detail


# --- CASE-B02: Verstöße, Proposals, Positionen ---------------------------------


def test_violations_are_bundled_and_overrides_filtered(fact_sheets):
    fs = fact_sheets["CASE-B02"]
    viols = _find(fs, "viol-")
    assert len(viols) == 1, [v.id for v in viols]
    (v,) = viols
    assert v.id == "viol-cluster-risk-of-a-single-financial-instr"
    assert v.severity == Severity.ERROR  # ein Error + eine Warnung → Error
    assert v.portfolio_nr == "CASE-B02-01"
    assert "Global Equity Fund (CHF)" in v.detail  # ISIN → CHF-Tranche
    assert v.numbers["actual_pct"] == 60.0 and v.numbers["limit_pct"] == 50.0
    assert "60.0%" in v.detail and "50.0%" in v.detail
    assert sorted(v.security_ids) == [101, 103]


def test_open_proposals_follow_status_rules(fact_sheets):
    fs = fact_sheets["CASE-B02"]
    assert fs.open_proposals == 2  # Entwurf + Final ohne Umsetzung; Abgelehnt und umgesetzt zählen nicht


def test_positions_carry_master_data_and_cash(fact_sheets):
    fs = fact_sheets["CASE-B02"]
    positions = fs.portfolios[0].positions
    by_id = {p.security_id: p for p in positions}
    fund = by_id[103]
    assert fund.is_fund_unbundlable is True
    assert fund.security_type == "Investment fund"
    assert fund.industry is None
    assert fund.sustainability_score == 4.0
    bond = by_id[104]
    assert str(bond.maturity_date) == "2027-01-15"
    lindt = by_id[101]
    assert str(lindt.maturity_date) == "None"  # Jahr 2299 = perpetual
    assert lindt.industry == "Consumer Staples" and lindt.country_group == "Switzerland"
    cash = [p for p in positions if is_cash(p)]
    assert len(cash) == 1 and cash[0].saa_asset_class == "Liquidity" and cash[0].weight_pct == 5.0
    assert abs(sum(p.weight_pct for p in positions) - 100.0) < 1e-6
    assert abs(sum(p.client_weight_pct for p in positions) - 100.0) < 1e-6


def test_real_saa_flag_and_names(fact_sheets):
    fs = fact_sheets["CASE-B02"]
    p = fs.portfolios[0]
    assert p.has_real_saa is True
    assert p.saa_name.startswith("Vorsorge Individuell")
    (perf,) = _find(fs, "perf-CASE-B02-01")
    assert perf.severity == Severity.WARNING  # -3.8 % über 3 Monate
    assert perf.numbers["return_3m_pct"] == -3.8


# --- CASE-C03: Lücken statt Crash -----------------------------------------------


def test_company_without_profile_yields_data_gaps(fact_sheets):
    fs = fact_sheets["CASE-C03"]
    assert fs.is_company is True
    assert fs.age is None and fs.risk_level is None
    gap_ids = {f.id for f in fs.findings if f.type == FindingType.DATA_GAP}
    assert "gap-profile-CASE-C03-01" in gap_ids
    assert "perf-gap-CASE-C03-01" in gap_ids
    assert fs.coverage["risk_profile"] == "ok"  # Lücke ist ein Finding, kein Fehler


def test_cash_only_client_has_crypto_and_cash_positions(fact_sheets):
    fs = fact_sheets["CASE-C03"]
    positions = fs.portfolios[0].positions
    assert all(is_cash(p) for p in positions)
    classes = sorted(p.saa_asset_class for p in positions)
    assert classes == ["Crypto", "Liquidity"]


# --- Zahlen-Konsistenz: was in numbers steht, steht formatiert im Text -------------


def test_every_number_appears_in_text(fact_sheets):
    for fs in fact_sheets.values():
        for f in fs.findings:
            text_numbers = {float(t.replace(",", "")) for t in NUMBER.findall(f.title + " " + f.detail) if t not in {"-", "."}}
            for key, value in f.numbers.items():
                assert any(abs(value - t) <= max(0.05, abs(t) * 0.01) for t in text_numbers), (
                    f"{fs.client_ref} {f.id}: numbers[{key}]={value} fehlt im Text: {f.title} | {f.detail}"
                )


# --- Integration über die echten Daten (falls vorhanden) -------------------------


REAL = Path(__file__).resolve().parents[1] / "data"


@pytest.mark.skipif(not (REAL / "clients.json").exists(), reason="Case-Daten nicht im Checkout")
def test_all_real_clients_build_without_detector_errors():
    clients = load_clients(REAL / "clients.json")
    reference = load_reference(REAL / "reference.json")
    assert len(clients) >= 47
    for c in clients:
        fs = build_fact_sheet(c, reference)
        errors = {k: v for k, v in fs.coverage.items() if v.startswith("error")}
        assert not errors, f"{c['ClientRef']}: {errors}"
        assert fs.findings
