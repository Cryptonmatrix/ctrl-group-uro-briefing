"""OWNER: JACOB — die Positionstabelle: eine Zeile pro Position über ALLE Portfolios des Klienten.

Was hier passiert:
  - Wertpapierpositionen werden über `SecurityId` mit den Stammdaten verknüpft (nie über ISIN,
    dieselbe ISIN existiert pro Währungstranche mehrfach).
  - Kontopositionen werden zu synthetischen Positionen mit `saa_asset_class = "Liquidity"`
    (Krypto-Konten: "Crypto"), damit Allokation und Konzentration die Liquidität sehen.
  - `weight_pct` bleibt das Portfolio-Gewicht (Levins Konvention, 0–100); `client_weight_pct`
    ist zusätzlich das Gewicht am Gesamtvermögen des Klienten — für Klienten mit mehreren Portfolios.

Pure: keine Dateizugriffe, kein Netz, keine Zeitabfragen.
"""

from __future__ import annotations

from typing import Any

from uro.config import CRYPTO_ASSET_CLASS, CRYPTO_CURRENCIES, PERPETUAL_MATURITY_YEAR
from uro.ingest import ReferenceIndex, get, lst, parse_date, to_float
from uro.models import PositionFact

CASH_SECURITY_ID = -1
CRYPTO_SECURITY_ID = -2


def is_cash(p: PositionFact) -> bool:
    """Synthetische Konto-Positionen haben negative security_id."""
    return p.security_id < 0


def total_aum(client: dict[str, Any]) -> float:
    """Gesamtvermögen des Klienten in ReportingCurrency; Fallback: Summe der Portfolios."""
    aum = to_float(get(client, "AssetsUnderManagementInDefaultCurrency"))
    if aum > 0:
        return aum
    return float(
        sum(to_float(get(p, "AssetsUnderManagementInDefaultCurrency")) for p in lst(client, "Portfolios"))
    )


def _maturity(sec: dict[str, Any]):
    d = parse_date(get(sec, "MaturityDateUtc"))
    if d is None or d.year >= PERPETUAL_MATURITY_YEAR:
        return None
    return d


def _client_weight(amount: float, total: float) -> float | None:
    return round(amount / total * 100, 4) if total > 0 else None


def security_positions(portfolio: dict[str, Any], ref: ReferenceIndex, total: float) -> list[PositionFact]:
    pnr = str(get(portfolio, "PortfolioNr", "?"))
    out: list[PositionFact] = []
    for sp in lst(portfolio, "SecurityPositions"):
        sid = get(sp, "SecurityId")
        sec = ref.security(sid)
        amount = to_float(get(sp, "TotalAmountInPortfolioCurrency"))
        prc = get(sec, "PRC")
        out.append(
            PositionFact(
                security_id=int(to_float(sid, 0.0)),
                name=str(get(sp, "SecurityName") or get(sec, "Name") or "Unnamed position"),
                isin=get(sp, "Isin") or get(sec, "Isin"),
                currency=str(get(sp, "Currency") or get(sec, "Currency") or "CHF"),
                amount_chf=amount,
                weight_pct=to_float(get(sp, "PortfolioValuePercentage")) * 100,
                asset_class=get(sec, "AssetClassName"),
                saa_asset_class=get(sec, "SAA_AssetClassName"),
                sector=get(sec, "IndustryName"),
                contribution_volatility=get(sp, "ContributionVolatility"),
                in_recommendation_list=bool(get(sec, "InRecommendationList", False)),
                portfolio_nr=pnr,
                client_weight_pct=_client_weight(amount, total),
                security_type=get(sec, "SecurityTypeName"),
                industry=get(sec, "SAA_IndustryName"),
                country_group=get(sec, "SAA_CountryGroupName"),
                currency_group=get(sec, "SAA_CurrencyGroupName"),
                volatility=to_float(get(sec, "Volatility"), default=None)
                if get(sec, "Volatility") is not None
                else None,
                prc=int(to_float(prc)) if prc is not None else None,
                sustainability_score=to_float(get(sec, "SustainabilityScore"), default=None)
                if get(sec, "SustainabilityScore") is not None
                else None,
                maturity_date=_maturity(sec),
                is_fund_unbundlable=bool(get(sec, "IsUnbundlingEnabled", False)),
            )
        )
    return out


def account_positions(portfolio: dict[str, Any], total: float) -> list[PositionFact]:
    """Konten als synthetische Positionen. Krypto-Ticker (BTC, ETH, …) sind keine ISO-Währungen."""
    pnr = str(get(portfolio, "PortfolioNr", "?"))
    out: list[PositionFact] = []
    for ap in lst(portfolio, "AccountPositions"):
        currency = str(get(ap, "Currency") or "CHF")
        crypto = currency.upper() in CRYPTO_CURRENCIES
        amount = to_float(get(ap, "TotalAmountInPortfolioCurrency"))
        asset_class = CRYPTO_ASSET_CLASS if crypto else "Liquidity"
        out.append(
            PositionFact(
                security_id=CRYPTO_SECURITY_ID if crypto else CASH_SECURITY_ID,
                name=str(get(ap, "AccountName") or ("Crypto account" if crypto else "Cash account")),
                isin=None,
                currency=currency,
                amount_chf=amount,
                weight_pct=to_float(get(ap, "PortfolioValuePercentage")) * 100,
                asset_class=asset_class,
                saa_asset_class=asset_class,
                sector=None,
                contribution_volatility=get(ap, "ContributionVolatility"),
                portfolio_nr=pnr,
                client_weight_pct=_client_weight(amount, total),
                security_type="Crypto account" if crypto else "Cash account",
                currency_group=None if crypto else _currency_group(currency),
            )
        )
    return out


def _currency_group(currency: str) -> str:
    """Kontowährung → SAA_CurrencyGroupName-Bucket (data-notes §3)."""
    return {"CHF": "Swiss francs", "USD": "US-Dollar", "EUR": "Euro"}.get(currency.upper(), "Andere")


def build_positions(client: dict[str, Any], ref: ReferenceIndex) -> list[PositionFact]:
    """Alle Positionen aller Portfolios inkl. Konten, mit Stammdaten und Klienten-Gewicht."""
    total = total_aum(client)
    out: list[PositionFact] = []
    for p in lst(client, "Portfolios"):
        out.extend(security_positions(p, ref, total))
        out.extend(account_positions(p, total))
    return out
