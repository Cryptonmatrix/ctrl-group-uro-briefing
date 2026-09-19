"""OWNER: JACOB — baut aus Rohdaten das FactSheet. Der Einstiegspunkt der Engine.

Alles Berechnete entsteht hier. Das LLM sieht nur das Ergebnis.

Signatur bleibt `build_fact_sheet(client, reference)` — demo.py, api.py und eval/run_all.py
rufen sie so auf. Der ReferenceIndex wird intern gebaut und pro Referenz-Objekt gecacht.

Robustheit (Ziel: unbekannte Testdaten führen zu DATA_GAP, nie zu einem Crash):
  - Der Klient wird zuerst auf die Engine-Sicht reduziert (`engine_view`: kein Klarname).
  - Jeder Detektor läuft in `_run()`: Exception → geloggt, `coverage[name] = "error: <Name>"`, weiter.
  - Jedes Portfolio wird in `_portfolio()` gelesen: unlesbare Werte (Text statt Zahl, kaputtes Datum)
    werden übersprungen oder ergeben ein `gap-portfolio-<pnr>`-Finding, die anderen Portfolios laufen weiter.

Pure: kein Netz, keine Dateien, kein date.today(). Zeitanker sind history_as_of / data_as_of.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from uro.analytics.concentration import concentration_findings
from uro.analytics.esg import esg_findings
from uro.analytics.liquidity import liquidity_findings
from uro.analytics.notes import note_findings, note_flags, profile_findings
from uro.analytics.open_items import open_item_findings
from uro.analytics.performance import compute_returns, performance_findings, return_since
from uro.analytics.positions import build_positions, total_aum
from uro.analytics.proposals import open_proposals, proposal_findings
from uro.analytics.saa import build_allocation, saa_findings
from uro.analytics.scoring import score_findings
from uro.analytics.suitability import risk_profile_findings, violation_findings
from uro.config import NO_STRATEGY_NAMES
from uro.ingest import (
    ReferenceIndex,
    client_data_as_of,
    client_history_as_of,
    engine_view,
    get,
    lst,
    parse_date,
    parse_datetime,
    reference_index,
    to_float,
)
from uro.models import (
    FactSheet,
    Finding,
    FindingType,
    PerformancePoint,
    PortfolioFact,
    PositionFact,
    Severity,
)

logger = logging.getLogger(__name__)


def saa_is_real(saa: dict[str, Any] | None, strategy_name: str | None) -> bool:
    """False für die 29 'Keine Strategie'-Portfolios: deren SAA hat Min 0 / Target 0 / Max 1 für alles."""
    if strategy_name in NO_STRATEGY_NAMES or not saa:
        return False
    asset_rows = [m for m in lst(saa, "Mappings") if get(m, "Dimension") == "AssetClass"]
    if not asset_rows:
        return False
    empty = all(
        to_float(get(m, "MaxPercentage"), 1.0) >= 0.999 and to_float(get(m, "TargetPercentage"), 0.0) == 0.0
        for m in asset_rows
    )
    return not empty


def _run(coverage: dict[str, str], name: str, fn: Callable[..., list[Finding]], *args: Any) -> list[Finding]:
    """Detektor ausführen, Coverage pflegen, Exceptions an der Grenze fangen."""
    try:
        result = list(fn(*args) or [])
    except Exception as exc:  # noqa: BLE001 — genau hier soll jede Exception enden
        logger.exception("Detector %s failed", name)
        coverage[name] = f"error: {type(exc).__name__}"
        return []
    if coverage.get(name, "").startswith("error"):
        return result
    coverage[name] = "ok" if (result or coverage.get(name) == "ok") else "no_data"
    return result


def _history(portfolio: dict[str, Any]) -> list[PerformancePoint]:
    """PerformanceHistory lesen; Punkte mit kaputtem Datum oder Wert werden übersprungen, nicht geworfen."""
    points: list[PerformancePoint] = []
    for h in lst(portfolio, "PerformanceHistory"):
        d = parse_date(get(h, "Date"))
        raw = get(h, "Value")
        value = to_float(raw, default=float("nan"))
        if d is None or value != value:  # NaN-Check
            continue
        points.append(PerformancePoint(date=d, value=value))
    return points


def _optional_float(value: Any) -> float | None:
    """Kennzahl aus dem Portfolio: None bleibt None, Unlesbares wird None (→ DATA_GAP im Detektor)."""
    if value is None:
        return None
    parsed = to_float(value, default=float("nan"))
    return None if parsed != parsed else parsed


def _portfolio(
    p: dict[str, Any], ref: ReferenceIndex, positions: list[PositionFact], fs: FactSheet
) -> tuple[PortfolioFact, dict[str, float | None], float, dict[str, Any]]:
    """Ein Portfolio in PortfolioFact übersetzen. Wirft bei strukturell kaputten Daten — der Aufrufer fängt."""
    pnr = str(get(p, "PortfolioNr") or get(p, "PortfolioId") or "?")
    history = _history(p)
    returns = compute_returns(history)
    p_aum = to_float(get(p, "AssetsUnderManagementInDefaultCurrency"))
    saa = ref.saa(get(p, "StrategicAssetAllocationId"))
    strategy_name = get(p, "StrategyName")
    volatility = _optional_float(get(p, "Volatility"))
    clean = dict(p)
    clean["Volatility"] = volatility  # der Risikoprofil-Detektor liest das bereinigte Portfolio

    pf = PortfolioFact(
        portfolio_nr=pnr,
        name=str(get(p, "Name", "")),
        currency=str(get(p, "PortfolioCurrency", "CHF")),
        aum_chf=p_aum,
        liquidity_chf=to_float(get(p, "LiquidityInDefaultCurrency")),
        perf_1m_pct=returns["1m"],
        perf_3m_pct=returns["3m"],
        perf_12m_pct=returns["12m"],
        perf_ytd_pct=returns["ytd"],
        volatility=volatility,
        value_at_risk=_optional_float(get(p, "ValueAtRisk")),
        expected_return=_optional_float(get(p, "ExpectedReturn")),
        strategy_name=str(strategy_name) if strategy_name is not None else None,
        investment_service=get(p, "InvestmentServiceName"),
        saa_name=get(saa, "Name") or get(saa, "Description"),
        has_real_saa=saa_is_real(saa, strategy_name),
        max_volatility=fs.max_volatility,
        positions=positions,
        history=history,
    )
    return pf, returns, p_aum, clean


def _unique_ids(findings: list[Finding]) -> list[Finding]:
    seen: dict[str, int] = defaultdict(int)
    for f in findings:
        seen[f.id] += 1
        if seen[f.id] > 1:
            f.id = f"{f.id}-{seen[f.id]}"
    return findings


def build_fact_sheet(client: dict[str, Any], reference: dict[str, Any]) -> FactSheet:
    client = engine_view(client)  # ab hier: kein Klarname mehr im Spiel
    ref: ReferenceIndex = reference_index(reference)
    profile = ref.risk_profile(get(client, "RiskProfileId"))
    aum = total_aum(client)
    coverage: dict[str, str] = {}

    fs = FactSheet(
        client_ref=str(get(client, "ClientRef", "?")),
        is_company=bool(get(client, "IsClientACompany", False)),
        reporting_currency=str(get(client, "ReportingCurrency", "CHF")),
        risk_profile_name=get(client, "RiskProfileName") or (get(profile, "Name") if profile else None),
        max_volatility=_optional_float(get(profile, "MaxVola")) if profile else None,
        max_prc=int(to_float(get(profile, "MaxPRC"))) if profile and get(profile, "MaxPRC") is not None else None,
        esg_profile=get(client, "EsgProfileName"),
        total_aum_chf=aum,
        total_liquidity_chf=to_float(get(client, "LiquidityInDefaultCurrency")),
        tags=[str(get(t, "TagName", "")) for t in lst(client, "Tags") if get(t, "TagName")],
        open_proposals=len(open_proposals(client)),
        age=get(client, "_Age"),
        risk_level=int(to_float(get(profile, "RiskLevel"))) if profile and get(profile, "RiskLevel") is not None else None,
        history_as_of=client_history_as_of(client),
        data_as_of=client_data_as_of(client),
        note_flags=note_flags(client),
    )

    # Letzter Kontakt: jüngste Notiz oder jüngster Vorschlag
    stamps = [parse_datetime(get(n, "CreatedByDateUTC")) for n in lst(client, "ClientNotes")]
    stamps += [parse_datetime(get(p, "ProposedDateUTC")) for p in lst(client, "Proposals")]
    known = [s for s in stamps if s]
    fs.last_contact = max(known) if known else None
    last_contact = fs.last_contact.date() if fs.last_contact else None

    # Positionstabelle über alle Portfolios (inkl. Konten), dann je Portfolio gruppieren
    try:
        positions = build_positions(client, ref)
        coverage["positions"] = "ok" if positions else "no_data"
    except Exception as exc:  # noqa: BLE001
        logger.exception("build_positions failed")
        positions, coverage["positions"] = [], f"error: {type(exc).__name__}"
    by_portfolio: dict[str, list[PositionFact]] = defaultdict(list)
    for pos in positions:
        by_portfolio[pos.portfolio_nr or "?"].append(pos)

    portfolio_nr_by_id: dict[Any, str] = {
        get(p, "PortfolioId"): str(get(p, "PortfolioNr") or get(p, "PortfolioId") or "?") for p in lst(client, "Portfolios")
    }

    findings: list[Finding] = []
    findings += _run(coverage, "profile", profile_findings, client, fs)
    findings += _run(coverage, "violations", violation_findings, client, ref, portfolio_nr_by_id, aum)

    for p in lst(client, "Portfolios"):
        pnr = str(get(p, "PortfolioNr") or get(p, "PortfolioId") or "?")
        try:
            pf, returns, p_aum, clean = _portfolio(p, ref, by_portfolio.get(pnr, []), fs)
        except Exception as exc:  # noqa: BLE001 — kaputtes Portfolio wird zur Lücke, nicht zum Absturz
            logger.exception("Portfolio %s could not be read", pnr)
            coverage["portfolios"] = f"error: {type(exc).__name__}"
            findings.append(
                Finding(
                    id=f"gap-portfolio-{pnr}",
                    type=FindingType.DATA_GAP,
                    severity=Severity.WARNING,
                    title=f"Portfolio {pnr} could not be read — excluded from the analysis",
                    detail=f"The portfolio record is malformed ({type(exc).__name__}). Its positions, performance and risk figures are not part of this briefing.",
                    portfolio_nr=pnr,
                    materiality_chf=aum,
                    source="clients.json › Portfolios[]",
                )
            )
            continue
        if not coverage.get("portfolios", "").startswith("error"):
            coverage["portfolios"] = "ok"
        fs.portfolios.append(pf)

        # Ist-Allokation vs. SAA (mit Look-through) — Fehler hier kostet nur die Allokation, nicht das Portfolio
        try:
            pf.allocation = build_allocation(pf.positions, ref.saa(get(p, "StrategicAssetAllocationId")), ref, pf.has_real_saa)
            if not coverage.get("allocation", "").startswith("error"):
                coverage["allocation"] = "ok"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Allocation for %s failed", pnr)
            coverage["allocation"] = f"error: {type(exc).__name__}"

        since = return_since(pf.history, last_contact)
        findings += _run(
            coverage, "performance", performance_findings, pnr, returns, p_aum, fs.history_as_of, since, last_contact
        )
        findings += _run(coverage, "risk_profile", risk_profile_findings, client, clean, profile, p_aum)

    coverage.setdefault("portfolios", "no_data")
    coverage.setdefault("allocation", "no_data")

    # Klientenebene: alle Portfolios zusammen
    findings += _run(coverage, "saa", saa_findings, fs, client, portfolio_nr_by_id)
    findings += _run(coverage, "concentration", concentration_findings, fs, ref)
    findings += _run(coverage, "esg", esg_findings, fs, client, ref)
    findings += _run(coverage, "liquidity", liquidity_findings, fs, client)
    findings += _run(coverage, "proposals", proposal_findings, fs, client, ref, portfolio_nr_by_id)
    findings += _run(coverage, "open_items", open_item_findings, fs, client)
    findings += _run(coverage, "notes", note_findings, client, fs.data_as_of)

    fs.findings = score_findings(_unique_ids(findings), fs)
    fs.coverage = coverage
    return fs
