"""OWNER: JACOB — baut aus Rohdaten das FactSheet. Der Einstiegspunkt der Engine.

Alles Berechnete entsteht hier. Das LLM sieht nur das Ergebnis.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from uro.analytics.concentration import concentration_findings
from uro.analytics.performance import compute_returns, performance_findings
from uro.analytics.scoring import score_findings
from uro.analytics.suitability import risk_profile_findings, violation_findings
from uro.ingest import get, index_by, lst
from uro.models import FactSheet, PerformancePoint, PortfolioFact, PositionFact


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _positions(portfolio: dict[str, Any], securities: dict[int, dict]) -> list[PositionFact]:
    out: list[PositionFact] = []
    for sp in lst(portfolio, "SecurityPositions"):
        sec = securities.get(get(sp, "SecurityId"), {})
        out.append(PositionFact(
            security_id=int(get(sp, "SecurityId", 0)),
            name=str(get(sp, "SecurityName", "Unbenannt")),
            isin=get(sp, "Isin"),
            currency=str(get(sp, "Currency", "CHF")),
            amount_chf=float(get(sp, "TotalAmountInPortfolioCurrency", 0.0)),
            # Rohdaten sind Bruch 0-1, wir rechnen intern in Prozent
            weight_pct=float(get(sp, "PortfolioValuePercentage", 0.0)) * 100,
            asset_class=get(sec, "AssetClassName"),
            saa_asset_class=get(sec, "SAA_AssetClassName"),
            sector=get(sec, "IndustryName"),
            contribution_volatility=get(sp, "ContributionVolatility"),
            in_recommendation_list=bool(get(sec, "InRecommendationList", False)),
        ))
    return out


def build_fact_sheet(client: dict[str, Any], reference: dict[str, Any]) -> FactSheet:
    securities = index_by(lst(reference, "Securities"), "Id")
    profiles = index_by(lst(reference, "RiskProfiles"), "Id")
    profile = profiles.get(get(client, "RiskProfileId"))

    aum = float(get(client, "AssetsUnderManagementInDefaultCurrency", 0.0))

    fs = FactSheet(
        client_ref=str(get(client, "ClientRef", "?")),
        is_company=bool(get(client, "IsClientACompany", False)),
        reporting_currency=str(get(client, "ReportingCurrency", "CHF")),
        risk_profile_name=get(client, "RiskProfileName"),
        max_volatility=get(profile, "MaxVola") if profile else None,
        max_prc=get(profile, "MaxPRC") if profile else None,
        esg_profile=get(client, "EsgProfileName"),
        total_aum_chf=aum,
        total_liquidity_chf=float(get(client, "LiquidityInDefaultCurrency", 0.0)),
        tags=[str(get(t, "TagName", "")) for t in lst(client, "Tags")],
        open_proposals=len(lst(client, "Proposals")),
    )

    # Letzter Kontakt: juengste Notiz oder juengster Vorschlag
    stamps = [_parse_dt(get(n, "CreatedByDateUTC")) for n in lst(client, "ClientNotes")]
    stamps += [_parse_dt(get(p, "ProposedDateUTC")) for p in lst(client, "Proposals")]
    known = [s for s in stamps if s]
    fs.last_contact = max(known) if known else None

    findings = violation_findings(client, aum)

    for p in lst(client, "Portfolios"):
        pnr = str(get(p, "PortfolioNr", "?"))
        history = [
            PerformancePoint(date=h["Date"], value=float(get(h, "Value", 0.0)))
            for h in lst(p, "PerformanceHistory") if get(h, "Date")
        ]
        returns = compute_returns(history)
        positions = _positions(p, securities)
        p_aum = float(get(p, "AssetsUnderManagementInDefaultCurrency", 0.0))

        fs.portfolios.append(PortfolioFact(
            portfolio_nr=pnr,
            name=str(get(p, "Name", "")),
            currency=str(get(p, "PortfolioCurrency", "CHF")),
            aum_chf=p_aum,
            liquidity_chf=float(get(p, "LiquidityInDefaultCurrency", 0.0)),
            perf_1m_pct=returns["1m"], perf_3m_pct=returns["3m"],
            perf_12m_pct=returns["12m"], perf_ytd_pct=returns["ytd"],
            volatility=get(p, "Volatility"),
            value_at_risk=get(p, "ValueAtRisk"),
            expected_return=get(p, "ExpectedReturn"),
            strategy_name=get(p, "StrategyName"),
            investment_service=get(p, "InvestmentServiceName"),
            positions=positions,
            history=history,
        ))

        findings += performance_findings(pnr, returns, p_aum)
        findings += concentration_findings(pnr, positions, p_aum)
        findings += risk_profile_findings(client, p, profile, p_aum)

    fs.findings = score_findings(findings, aum)
    return fs
