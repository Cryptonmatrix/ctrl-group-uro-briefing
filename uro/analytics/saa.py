"""OWNER: JACOB — Soll-Ist-Vergleich gegen die Strategic Asset Allocation (Spec §5.6).

Fallen, alle an den echten Daten geprüft (docs/data-notes.md §5):
  - Vergleich über die SAA_*-Felder, nicht über die feineren AssetClassName-Felder.
  - Nur AssetClass-Mappings haben Min/Max-Bänder. Währung, Region und Branche haben nur ein Target
    → dort melden wir erst ab ±SAA_OTHER_DIM_THRESHOLD_PP Prozentpunkten.
  - Die Region- und Branchen-Targets summieren sich je SAA auf 100 % — sie beziehen sich auf den
    AKTIENANTEIL, nicht auf das ganze Portfolio. Geprüft an den Bank-Regeln: CASE-002 "Overweight in the
    equity sector Industrials" nennt 0.1576, unsere aktienrelative Rechnung mit Look-through ergibt 0.1576.
    Währungs-Targets beziehen sich auf das ganze Portfolio.
  - 29 von 57 Portfolios hängen an einer "Keine Strategie"-SAA (Min 0 / Target 0 / Max 1). Dort gibt es
    keinen Soll-Ist-Vergleich, nur ein Kontext-Finding saa-none-<pnr>.

Doppelmeldungen: Meldet die Regel-Engine der Bank schon einen Verstoss für dieselbe Region/Branche
(RuleCode enthält die Kategorie in Anführungszeichen), unterdrücken wir unser eigenes Finding.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from uro.analytics.format import chf, num, pct, pp, round_chf, slug
from uro.analytics.lookthrough import exposures
from uro.config import SAA_MAGNITUDE_REF_PP, SAA_OTHER_DIM_THRESHOLD_PP
from uro.ingest import ReferenceIndex, get, lst, to_float
from uro.models import AllocationLine, FactSheet, Finding, FindingType, PositionFact, Severity

SOURCE = "clients.json › Portfolios[] vs reference.json › StrategicAssetAllocations[].Mappings"
SAA_DIMENSIONS = {
    "AssetClass": "asset_class",
    "CurrencyGroup": "currency_group",
    "CountryGroup": "country_group",
    "Industry": "industry",
}
EQUITY_RELATIVE = {"CountryGroup", "Industry"}
EQUITY_CLASS = "Shares"
LABELS = {"AssetClass": "", "CurrencyGroup": "Currency ", "CountryGroup": "Equity region ", "Industry": "Equity sector "}
_QUOTED = re.compile(r'"([^"]+)"')
# Währungsregeln der Bank nennen ISO-Codes ("Foreign currency cluster risk USD"), die SAA Gruppennamen
ISO_TO_CURRENCY_GROUP = {"USD": "US-Dollar", "EUR": "Euro", "CHF": "Swiss francs"}
HOME_CURRENCY_GROUP = {"CHF": "Swiss francs", "EUR": "Euro", "USD": "US-Dollar"}


def _bank_flagged_categories(client: dict[str, Any], portfolio_nr_by_id: dict[Any, str]) -> dict[str, set[str]]:
    """Kategorien je Portfolio, die die Regel-Engine der Bank schon meldet — dort melden wir nicht doppelt.

    'Overweight in the equity sector "Industrials"' → Industrials
    'Foreign currency cluster risk USD'             → US-Dollar
    'Foreign currency exposure exceeds 50%'         → Heimatwährung (Spiegelbild: zu wenig CHF)
    """
    home = HOME_CURRENCY_GROUP.get(str(get(client, "ReportingCurrency", "CHF")), "Swiss francs")
    flagged: dict[str, set[str]] = defaultdict(set)
    for v in lst(client, "SuitabilityViolations"):
        code = str(get(v, "RuleCode", ""))
        pnr = portfolio_nr_by_id.get(get(v, "PortfolioId"), "")
        m = _QUOTED.search(code)
        if m:
            flagged[pnr].add(m.group(1))
        if "currency" in code.lower():
            for iso, group in ISO_TO_CURRENCY_GROUP.items():
                if re.search(rf"\b{iso}\b", code):
                    flagged[pnr].add(group)
            if "exceeds" in code.lower() or "foreign currency exposure" in code.lower():
                flagged[pnr].add(home)
    return flagged


def _pct_of(mapping: dict[str, Any] | None, key: str) -> float | None:
    if not mapping or get(mapping, key) is None:
        return None
    return num(to_float(get(mapping, key)) * 100)


def _mappings(saa: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for m in lst(saa, "Mappings"):
        dim, cat = get(m, "Dimension"), get(m, "Category")
        if dim and cat:
            out[str(dim)][str(cat)] = m
    return out


def equity_share_pct(positions: list[PositionFact]) -> float:
    """Aktienanteil des Portfolios in Prozent (Basis für Region und Branche)."""
    return sum(p.weight_pct for p in positions if p.saa_asset_class == EQUITY_CLASS)


def build_allocation(
    positions: list[PositionFact], saa: dict[str, Any], ref: ReferenceIndex, has_real_saa: bool
) -> list[AllocationLine]:
    """Ist-Allokation je Dimension (mit Look-through), mit Target/Min/Max nur bei echter SAA."""
    if not positions:
        return []

    def weight(p: PositionFact) -> float:
        return p.weight_pct

    base = exposures(positions, ref, weight, dims=("asset_class", "currency_group"))
    equity = [p for p in positions if p.saa_asset_class == EQUITY_CLASS]
    eq_total = sum(p.weight_pct for p in equity)
    eq = exposures(equity, ref, weight, dims=("country_group", "industry")) if eq_total > 0 else {}
    targets = _mappings(saa) if has_real_saa else {}

    lines: list[AllocationLine] = []
    for dimension, dim in SAA_DIMENSIONS.items():
        if dimension in EQUITY_RELATIVE:
            actual = {c: e.total / eq_total * 100 for c, e in eq.get(dim, {}).items()} if eq_total > 0 else {}
        else:
            actual = {c: e.total for c, e in base.get(dim, {}).items()}
        dim_targets = targets.get(dimension, {})
        for cat in list(dim_targets) + sorted(c for c in actual if c not in dim_targets):
            m = dim_targets.get(cat)
            lines.append(
                AllocationLine(
                    dimension=dimension,
                    category=cat,
                    actual_pct=num(actual.get(cat, 0.0)),
                    target_pct=_pct_of(m, "TargetPercentage"),
                    min_pct=_pct_of(m, "MinPercentage"),
                    max_pct=_pct_of(m, "MaxPercentage"),
                )
            )
    return lines


def saa_findings(fs: FactSheet, client: dict[str, Any], portfolio_nr_by_id: dict[Any, str]) -> list[Finding]:
    """saa-<dim>-<slug> je Abweichung; saa-none-<pnr> für Portfolios ohne echte SAA."""
    flagged = _bank_flagged_categories(client, portfolio_nr_by_id)

    multi = len(fs.portfolios) > 1
    out: list[Finding] = []
    for pf in fs.portfolios:
        if not pf.has_real_saa:
            out.append(
                Finding(
                    id=f"saa-none-{pf.portfolio_nr}",
                    type=FindingType.SAA_DEVIATION,
                    severity=Severity.INFO,
                    title=f"No strategic asset allocation for portfolio {pf.portfolio_nr} (strategy '{pf.strategy_name or 'none'}')",
                    detail=(
                        f"The portfolio is linked to '{pf.saa_name or 'no SAA'}', which allows every asset class from zero to "
                        "the full portfolio. Neither this check nor the bank's SAA-based rules can flag deviations; "
                        "the risk-profile check still applies."
                    ),
                    portfolio_nr=pf.portfolio_nr,
                    materiality_chf=pf.aum_chf * 0.3,
                    source=SOURCE,
                )
            )
            continue

        eq_pct = equity_share_pct(pf.positions)
        where = f" in portfolio {pf.portfolio_nr}" if multi else ""
        suffix = f"-{slug(pf.portfolio_nr)}" if multi else ""
        for line in pf.allocation:
            if line.target_pct is None:
                continue
            dev = num(line.actual_pct - line.target_pct)
            if line.dimension == "AssetClass":
                below = line.min_pct is not None and line.actual_pct < line.min_pct
                above = line.max_pct is not None and line.actual_pct > line.max_pct
                if not (below or above):
                    continue
                severity = Severity.WARNING
                basis_value = pf.aum_chf
            else:
                if abs(dev) < SAA_OTHER_DIM_THRESHOLD_PP or line.category in flagged.get(pf.portfolio_nr, set()):
                    continue
                severity = Severity.INFO
                basis_value = pf.aum_chf * (eq_pct / 100 if line.dimension in EQUITY_RELATIVE else 1.0)

            amount = round_chf(abs(dev) / 100 * basis_value)
            direction = "above" if dev > 0 else "below"
            numbers = {"actual_pct": line.actual_pct, "target_pct": line.target_pct}
            of_equities = " of equities" if line.dimension in EQUITY_RELATIVE else ""
            title = f"{LABELS[line.dimension]}{line.category} {pct(line.actual_pct)}{of_equities} vs SAA target {pct(line.target_pct)}{where}"
            if line.dimension == "AssetClass":
                if line.min_pct is not None:
                    numbers["min_pct"] = line.min_pct
                if line.max_pct is not None:
                    numbers["max_pct"] = line.max_pct
                band = (
                    f"Outside the agreed band {pct(line.min_pct)}–{pct(line.max_pct)}: "
                    if line.min_pct is not None and line.max_pct is not None
                    else ""
                )
                detail = f"{band}{pp(dev)} vs target, ≈ {chf(amount)} {direction} target."
            else:
                basis = " (share of the equity allocation)" if line.dimension in EQUITY_RELATIVE else ""
                detail = (
                    f"{pp(dev)} vs target{basis}, ≈ {chf(amount)} {direction} target. These targets have no "
                    f"tolerance band in the data; flagged from ±{SAA_OTHER_DIM_THRESHOLD_PP:.0f} pp."
                )
            numbers.update(deviation_pp=dev, amount_chf=amount)
            out.append(
                Finding(
                    id=f"saa-{line.dimension.lower()}-{slug(line.category)}{suffix}",
                    type=FindingType.SAA_DEVIATION,
                    severity=severity,
                    title=title,
                    detail=detail,
                    numbers=numbers,
                    portfolio_nr=pf.portfolio_nr,
                    materiality_chf=min(1.0, abs(dev) / SAA_MAGNITUDE_REF_PP) * pf.aum_chf,
                    source=SOURCE,
                )
            )
    return out
