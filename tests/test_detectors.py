"""A2-Detektoren: SAA mit Look-through, Konzentration auf Klientenebene, ESG, Liquidität, Proposals, offene Punkte, Scoring."""

from __future__ import annotations

import copy

from uro.analytics import build_fact_sheet
from uro.models import FindingType, Severity


def _by_id(fs, finding_id: str):
    hits = [f for f in fs.findings if f.id == finding_id]
    assert hits, f"{finding_id!r} fehlt; vorhanden: {sorted(f.id for f in fs.findings)}"
    return hits[0]


def _ids(fs, prefix: str) -> list[str]:
    return sorted(f.id for f in fs.findings if f.id.startswith(prefix))


# --- SAA ---------------------------------------------------------------------------


def test_saa_allocation_uses_fund_lookthrough(fact_sheets):
    pf = fact_sheets["CASE-B02"].portfolios[0]
    by = {(line.dimension, line.category): line for line in pf.allocation}
    # Lindt 20 % + Fonds 70 % (alle Zeilen "Equities …" → Shares) = 90 %
    assert by[("AssetClass", "Shares")].actual_pct == 90.0
    assert by[("AssetClass", "Shares")].target_pct == 45.0
    assert by[("AssetClass", "Shares")].max_pct == 85.0
    assert by[("AssetClass", "Bonds")].actual_pct == 5.0
    assert by[("AssetClass", "Liquidity")].actual_pct == 5.0
    # Währung (Basis: ganzes Portfolio): Fonds 70 % × US-Dollar 70 % = 49 %; Swiss francs = 20 + 5 + 5 + 70 × 20 % = 44 %
    assert by[("CurrencyGroup", "US-Dollar")].actual_pct == 49.0
    assert by[("CurrencyGroup", "Swiss francs")].actual_pct == 44.0
    # Region und Branche (Basis: Aktienanteil 90 %): North America 49 / 90 = 54.4 %; "Raw materials" → Materials 14 / 90 = 15.6 %
    assert by[("CountryGroup", "North America")].actual_pct == 54.4
    assert by[("Industry", "Information Technology")].actual_pct == 31.1
    assert by[("Industry", "Materials")].actual_pct == 15.6
    assert by[("Industry", "Materials")].target_pct is None  # kein Target im Fixture → kein Finding


def test_saa_band_violations_become_findings(fact_sheets):
    fs = fact_sheets["CASE-B02"]
    shares = _by_id(fs, "saa-assetclass-shares")
    assert shares.type == FindingType.SAA_DEVIATION and shares.severity == Severity.WARNING
    assert shares.numbers == {
        "actual_pct": 90.0,
        "target_pct": 45.0,
        "min_pct": 20.0,
        "max_pct": 85.0,
        "deviation_pp": 45.0,
        "amount_chf": 225000.0,
    }
    assert "90.0%" in shares.title and "+45.0 pp" in shares.detail and "CHF 225,000" in shares.detail
    bonds = _by_id(fs, "saa-assetclass-bonds")
    assert bonds.numbers["deviation_pp"] == -42.0 and "-42.0 pp" in bonds.detail
    # Liquidity 5 % liegt im Band 0–60 → kein Finding
    assert "saa-assetclass-liquidity" not in {f.id for f in fs.findings}


def test_saa_other_dimensions_use_target_threshold(fact_sheets):
    fs = fact_sheets["CASE-B02"]
    usd = _by_id(fs, "saa-currencygroup-us-dollar")
    assert usd.severity == Severity.INFO
    assert (
        usd.numbers["actual_pct"] == 49.0
        and usd.numbers["target_pct"] == 30.5
        and usd.numbers["deviation_pp"] == 18.5
    )
    na = _by_id(fs, "saa-countrygroup-north-america")
    assert "of equities" in na.title and "share of the equity allocation" in na.detail
    it = _by_id(fs, "saa-industry-information-technology")
    assert (
        it.numbers["actual_pct"] == 31.1
        and it.numbers["target_pct"] == 10.9
        and it.numbers["deviation_pp"] == 20.2
    )
    # Betrag auf Basis des Aktienanteils: 20.2 pp × 90 % × CHF 500,000 = CHF 90,900
    assert it.numbers["amount_chf"] == 90900.0
    # Euro: 0 % vs 4 % → unter der 10-pp-Schwelle
    assert "saa-currencygroup-euro" not in {f.id for f in fs.findings}


def test_saa_finding_suppressed_when_bank_already_flags_it(mini_clients, mini_reference):
    client = copy.deepcopy(next(c for c in mini_clients if c["ClientRef"] == "CASE-B02"))
    client["SuitabilityViolations"].append(
        {
            "Id": 4,
            "RuleCode": 'Overweight in the equity sector "Information Technology"',
            "RuleDescription": "Übergewicht",
            "ErrorLevel": 1,
            "Severity": "Warning",
            "PortfolioId": 2,
        }
    )
    fs = build_fact_sheet(client, mini_reference)
    ids = {f.id for f in fs.findings}
    assert any(i.startswith("viol-overweight-in-the-equity-sector") for i in ids)
    assert "saa-industry-information-technology" not in ids  # keine Doppelmeldung
    assert "saa-countrygroup-north-america" in ids  # andere Kategorien bleiben


def test_currency_deviation_suppressed_when_bank_flags_currency_rules(mini_clients, mini_reference):
    client = copy.deepcopy(next(c for c in mini_clients if c["ClientRef"] == "CASE-B02"))
    client["SuitabilityViolations"] += [
        {
            "Id": 5,
            "RuleCode": "Foreign currency cluster risk USD",
            "RuleDescription": "x",
            "ErrorLevel": 2,
            "Severity": "Error",
            "PortfolioId": 2,
        },
        {
            "Id": 6,
            "RuleCode": "Foreign currency exposure exceeds 50%",
            "RuleDescription": "y",
            "ErrorLevel": 2,
            "Severity": "Error",
            "PortfolioId": 2,
        },
    ]
    ids = {f.id for f in build_fact_sheet(client, mini_reference).findings}
    assert "saa-currencygroup-us-dollar" not in ids  # Bank meldet USD-Klumpen
    assert "saa-currencygroup-swiss-francs" not in ids  # Spiegelbild: Fremdwährung > 50 %


def test_no_strategy_portfolio_gets_context_not_deviations(fact_sheets):
    fs = fact_sheets["CASE-A01"]
    assert _ids(fs, "saa-") == ["saa-none-CASE-A01-01"]
    none = _by_id(fs, "saa-none-CASE-A01-01")
    assert none.type == FindingType.SAA_DEVIATION and none.severity == Severity.INFO
    assert "No strategy" in none.title
    lines = fs.portfolios[0].allocation
    assert lines  # Ist-Allokation ist trotzdem da (für UI/Chat)
    assert all(line.target_pct is None for line in lines)  # 0 %-Targets der leeren SAA werden nicht gezeigt


# --- Konzentration ---------------------------------------------------------------------


def test_single_position_concentration_on_client_level(fact_sheets):
    fs = fact_sheets["CASE-B02"]
    fund = _by_id(fs, "conc-single-global-equity-fund-chf")
    assert fund.severity == Severity.ERROR  # 70 % ≥ 25 %
    assert fund.numbers["weight_pct"] == 70.0 and fund.numbers["amount_chf"] == 350000.0
    lindt = _by_id(fs, "conc-single-chocoladefabriken-lindt-spruengli-ag-n")
    assert lindt.severity == Severity.WARNING  # 20 % ≥ 10 %, < 25 %
    fs_a = fact_sheets["CASE-A01"]
    assert len(_ids(fs_a, "conc-single-")) == 2  # Lindt 73.5 % (ERROR) und Sensirion 23.5 % (WARNING)


def test_sector_currency_region_concentration_with_lookthrough(fact_sheets):
    fs = fact_sheets["CASE-B02"]
    it = _by_id(fs, "conc-sector-information-technology")
    assert it.numbers == {"exposure_pct": 28.0, "direct_pct": 0.0, "via_funds_pct": 28.0}
    assert "28.0%" in it.title and "via fund look-through" in it.detail
    assert it.security_ids == [103]
    usd = _by_id(fs, "conc-currency-us-dollar")
    assert usd.numbers["exposure_pct"] == 49.0
    na = _by_id(fs, "conc-region-north-america")
    assert na.numbers["exposure_pct"] == 49.0
    # Heimatwährung und -region werden nicht als Konzentration gemeldet
    assert "conc-currency-swiss-francs" not in {f.id for f in fs.findings}
    assert "conc-region-switzerland" not in {f.id for f in fact_sheets["CASE-A01"].findings}


def test_exposures_are_exposed_for_chat(fact_sheets):
    fs = fact_sheets["CASE-B02"]
    assert set(fs.exposures) == {"asset_class", "currency_group", "country_group", "industry"}
    industry = {row["name"]: row for row in fs.exposures["industry"]}
    assert industry["Information Technology"]["via_funds_pct"] == 28.0
    assert industry["Consumer Staples"]["direct_pct"] == 20.0
    assert fact_sheets["CASE-C03"].exposures["asset_class"][0]["name"] in {"Liquidity", "Crypto"}


# --- ESG ---------------------------------------------------------------------------------


def test_esg_findings_only_for_esg_clients(fact_sheets):
    fs = fact_sheets["CASE-B02"]  # ESG "Yes", Fonds Score 4.0 < 5.714
    below = _by_id(fs, "esg-positions-below-min")
    assert below.numbers["min_position_score"] == 5.7 and below.numbers["lowest_score"] == 4.0
    assert below.security_ids == [103]
    portfolio = _by_id(fs, "esg-portfolio-below-min")
    assert portfolio.numbers["portfolio_score"] == 4.9 and portfolio.numbers["min_level"] == 5.7
    assert _ids(fact_sheets["CASE-A01"], "esg-") == []  # ESG "No"
    assert _ids(fact_sheets["CASE-C03"], "esg-") == []  # kein Profil


# --- Liquidität ------------------------------------------------------------------------------


def test_cash_only_client_gets_invest_opportunity(fact_sheets):
    fs = fact_sheets["CASE-C03"]
    cash = _by_id(fs, "liq-cash")
    assert cash.severity == Severity.OPPORTUNITY
    assert cash.numbers["cash_pct"] == 90.0 and cash.numbers["cash_chf"] == 45000.0
    need = _by_id(fs, "liq-need")
    assert need.severity == Severity.INFO  # CHF 15,000 Bedarf, CHF 45,000 Cash → gedeckt
    assert need.numbers == {"need_chf": 15000.0, "cash_chf": 45000.0}
    assert need.related_ids == ["note-1"]


def test_liquidity_need_shortfall_is_error(mini_clients, mini_reference):
    client = copy.deepcopy(next(c for c in mini_clients if c["ClientRef"] == "CASE-B02"))
    client["LiquidityInDefaultCurrency"] = 328.0
    fs = build_fact_sheet(client, mini_reference)
    need = _by_id(fs, "liq-need")
    assert need.severity == Severity.ERROR
    assert need.numbers == {"need_chf": 15000.0, "cash_chf": 328.0, "shortfall_chf": 14672.0}
    assert "CHF 14,672" in need.detail and "CHF 328" in need.title
    assert need.related_ids == ["note-2"]  # die Notiz vom 15 Jan 2026 ist die zweitjüngste
    assert "client needs liquidity (notes)" in need.boost_reasons
    # Gewicht über den ungedeckten Anteil des Bedarfs (98 %), nicht über Lücke / Vermögen (3 %)
    assert need.score > 0.9


def test_maturity_within_window_is_reinvestment_opportunity(fact_sheets):
    fs = fact_sheets["CASE-B02"]
    mat = _by_id(fs, "liq-maturity-104")
    assert mat.severity == Severity.OPPORTUNITY
    assert mat.numbers["days_to_maturity"] == 119.0  # 2026-09-18 → 2027-01-15
    assert "15 Jan 2027" in mat.title and "CHF 25,000" in mat.title


# --- Proposals und offene Punkte ----------------------------------------------------------------


def test_open_and_rejected_proposals(fact_sheets):
    fs = fact_sheets["CASE-B02"]
    draft = _by_id(fs, "prop-503")
    assert draft.type == FindingType.OPEN_PROPOSAL and draft.numbers["age_days"] == 17.0
    stale = _by_id(fs, "prop-501")
    assert stale.numbers["age_days"] == 98.0
    assert "follow up" in stale.detail and "overdue follow-up" in stale.boost_reasons
    assert "Swiss Confederation 1.5% 2027 8.0%" in stale.detail
    assert "prop-504" not in {f.id for f in fs.findings}  # umgesetzt
    rejected = _by_id(fs, "rej-proposals")
    assert rejected.type == FindingType.REJECTED_PROPOSAL and rejected.numbers["declined_count"] == 1.0
    assert "Reduce fund concentration" in rejected.title


def test_profile_review_due(fact_sheets):
    fs = fact_sheets["CASE-B02"]  # profiliert 2023-06-01, data_as_of 2026-09-18 → 39 Monate
    item = _by_id(fs, "item-profile-review-due")
    assert item.numbers["months_since_profiling"] == 39.0 and "39 months" in item.title
    assert "item-profile-review-due" not in {
        f.id for f in fact_sheets["CASE-A01"].findings
    }  # 2025-07 → 14 Monate


# --- Scoring -------------------------------------------------------------------------------


def test_scoring_boosts_are_transparent(fact_sheets):
    fs = fact_sheets["CASE-B02"]
    need = _by_id(fs, "liq-need")
    assert "client needs liquidity (notes)" in need.boost_reasons  # Notiz "liquid funds" → Flag
    assert 0.0 < need.client_relevance <= 1.0
    fund = _by_id(fs, "conc-single-global-equity-fund-chf")
    assert "same position as other key finding" in fund.boost_reasons  # Fonds steckt auch im Cluster-Verstoss
    scores = [f.score for f in fs.findings]
    assert scores == sorted(scores, reverse=True)
    assert all(f.rank == i for i, f in enumerate(fs.findings, start=1))


def test_conservative_client_boosts_risk_findings(mini_clients, mini_reference):
    client = copy.deepcopy(next(c for c in mini_clients if c["ClientRef"] == "CASE-A01"))
    client["RiskProfileId"], client["RiskProfileName"] = 15, "Anlageprofil 3"  # RiskLevel 3 → konservativ
    client["ClientNotes"] = [
        {"Note": "Worried about market swings.", "CreatedByDateUTC": "2026-09-01T00:00:00Z"}
    ]
    fs = build_fact_sheet(client, mini_reference)
    breach = _by_id(fs, "risk-breach-CASE-A01-01")
    assert "risk-averse client" in breach.boost_reasons
    assert fs.note_flags == ["risk_averse"]
