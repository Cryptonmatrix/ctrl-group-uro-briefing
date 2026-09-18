"""OWNER: JACOB — baut aus Rohdaten das FactSheet. Der Einstiegspunkt der Engine.

Alles Berechnete entsteht hier. Das LLM sieht nur das Ergebnis.

Signatur bleibt `build_fact_sheet(client, reference)` — demo.py, api.py und eval/run_all.py
rufen sie so auf. Der ReferenceIndex wird intern gebaut und pro Referenz-Objekt gecacht.

Robustheit: Jeder Detektor läuft in `_run()`. Wirft er eine Exception, wird sie geloggt,
`coverage[name] = "error: <Name>"` gesetzt und die Pipeline läuft weiter. Ein Detektor darf
nie das Briefing verhindern. Fehlende Daten sind Findings (DATA_GAP), keine Fehler.

Pure: kein Netz, keine Dateien, kein date.today(). Zeitanker sind history_as_of / data_as_of.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from uro.analytics.concentration import concentration_findings
from uro.analytics.notes import note_findings, note_flags, profile_findings
from uro.analytics.performance import compute_returns, performance_findings
from uro.analytics.positions import build_positions, is_cash, total_aum
from uro.analytics.proposals import open_proposals
from uro.analytics.scoring import score_findings
from uro.analytics.suitability import risk_profile_findings, violation_findings
from uro.config import NO_STRATEGY_NAMES
from uro.ingest import (
    ReferenceIndex,
    client_data_as_of,
    client_history_as_of,
    get,
    lst,
    parse_datetime,
    reference_index,
)
from uro.models import FactSheet, Finding, PerformancePoint, PortfolioFact

logger = logging.getLogger(__name__)


def saa_is_real(saa: dict[str, Any] | None, strategy_name: str | None) -> bool:
    """False für die 29 'Keine Strategie'-Portfolios: deren SAA hat Min 0 / Target 0 / Max 1 für alles."""
    if strategy_name in NO_STRATEGY_NAMES or not saa:
        return False
    asset_rows = [m for m in lst(saa, "Mappings") if get(m, "Dimension") == "AssetClass"]
    if not asset_rows:
        return False
    empty = all(
        float(get(m, "MaxPercentage", 1.0) or 0.0) >= 0.999 and float(get(m, "TargetPercentage", 0.0) or 0.0) == 0.0
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


def _unique_ids(findings: list[Finding]) -> list[Finding]:
    seen: dict[str, int] = defaultdict(int)
    for f in findings:
        seen[f.id] += 1
        if seen[f.id] > 1:
            f.id = f"{f.id}-{seen[f.id]}"
    return findings


def build_fact_sheet(client: dict[str, Any], reference: dict[str, Any]) -> FactSheet:
    ref: ReferenceIndex = reference_index(reference)
    profile = ref.risk_profile(get(client, "RiskProfileId"))
    aum = total_aum(client)
    coverage: dict[str, str] = {}

    fs = FactSheet(
        client_ref=str(get(client, "ClientRef", "?")),
        is_company=bool(get(client, "IsClientACompany", False)),
        reporting_currency=str(get(client, "ReportingCurrency", "CHF")),
        risk_profile_name=get(client, "RiskProfileName") or (get(profile, "Name") if profile else None),
        max_volatility=get(profile, "MaxVola") if profile else None,
        max_prc=get(profile, "MaxPRC") if profile else None,
        esg_profile=get(client, "EsgProfileName"),
        total_aum_chf=aum,
        total_liquidity_chf=float(get(client, "LiquidityInDefaultCurrency", 0.0) or 0.0),
        tags=[str(get(t, "TagName", "")) for t in lst(client, "Tags") if get(t, "TagName")],
        open_proposals=len(open_proposals(client)),
        age=get(client, "_Age"),
        risk_level=get(profile, "RiskLevel") if profile else None,
        history_as_of=client_history_as_of(client),
        data_as_of=client_data_as_of(client),
        note_flags=note_flags(client),
    )

    # Letzter Kontakt: jüngste Notiz oder jüngster Vorschlag
    stamps = [parse_datetime(get(n, "CreatedByDateUTC")) for n in lst(client, "ClientNotes")]
    stamps += [parse_datetime(get(p, "ProposedDateUTC")) for p in lst(client, "Proposals")]
    known = [s for s in stamps if s]
    fs.last_contact = max(known) if known else None

    # Positionstabelle über alle Portfolios (inkl. Konten), dann je Portfolio gruppieren
    try:
        positions = build_positions(client, ref)
        coverage["positions"] = "ok" if positions else "no_data"
    except Exception as exc:  # noqa: BLE001
        logger.exception("build_positions failed")
        positions, coverage["positions"] = [], f"error: {type(exc).__name__}"
    by_portfolio: dict[str, list] = defaultdict(list)
    for pos in positions:
        by_portfolio[pos.portfolio_nr or "?"].append(pos)

    portfolio_nr_by_id: dict[Any, str] = {
        get(p, "PortfolioId"): str(get(p, "PortfolioNr", "?")) for p in lst(client, "Portfolios")
    }

    findings: list[Finding] = []
    findings += _run(coverage, "profile", profile_findings, client, fs)
    findings += _run(coverage, "violations", violation_findings, client, ref, portfolio_nr_by_id, aum)

    for p in lst(client, "Portfolios"):
        pnr = str(get(p, "PortfolioNr", "?"))
        history = [
            PerformancePoint(date=h["Date"], value=float(get(h, "Value", 0.0) or 0.0))
            for h in lst(p, "PerformanceHistory")
            if get(h, "Date")
        ]
        returns = compute_returns(history)
        p_aum = float(get(p, "AssetsUnderManagementInDefaultCurrency", 0.0) or 0.0)
        saa = ref.saa(get(p, "StrategicAssetAllocationId"))
        strategy_name = get(p, "StrategyName")
        portfolio_positions = by_portfolio.get(pnr, [])

        fs.portfolios.append(
            PortfolioFact(
                portfolio_nr=pnr,
                name=str(get(p, "Name", "")),
                currency=str(get(p, "PortfolioCurrency", "CHF")),
                aum_chf=p_aum,
                liquidity_chf=float(get(p, "LiquidityInDefaultCurrency", 0.0) or 0.0),
                perf_1m_pct=returns["1m"],
                perf_3m_pct=returns["3m"],
                perf_12m_pct=returns["12m"],
                perf_ytd_pct=returns["ytd"],
                volatility=get(p, "Volatility"),
                value_at_risk=get(p, "ValueAtRisk"),
                expected_return=get(p, "ExpectedReturn"),
                strategy_name=strategy_name,
                investment_service=get(p, "InvestmentServiceName"),
                saa_name=get(saa, "Name") or get(saa, "Description"),
                has_real_saa=saa_is_real(saa, strategy_name),
                max_volatility=fs.max_volatility,
                positions=portfolio_positions,
                history=history,
            )
        )

        findings += _run(coverage, "performance", performance_findings, pnr, returns, p_aum, fs.history_as_of)
        findings += _run(
            coverage, "concentration", concentration_findings, pnr, [x for x in portfolio_positions if not is_cash(x)], p_aum
        )
        findings += _run(coverage, "risk_profile", risk_profile_findings, client, p, profile, p_aum)

    findings += _run(coverage, "notes", note_findings, client, fs.data_as_of)

    fs.findings = score_findings(_unique_ids(findings), aum)
    fs.coverage = coverage
    return fs
