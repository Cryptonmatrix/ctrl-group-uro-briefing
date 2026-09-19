"""OWNER: JACOB — Klumpenrisiken auf Klientenebene: Einzeltitel, Branche, Fremdwährung, Region.

Wichtig: auch Klumpenrisiken finden, die KEINE Regel meldet. Ron Burgundy hält 73.5 % Lindt
bei null gemeldeten Verstössen.

Basis ist das Gewicht am Gesamtvermögen des Klienten (client_weight_pct), damit Klienten mit
mehreren Portfolios als Ganzes gesehen werden. Branche, Währung und Region inklusive
Fonds-Look-through (analytics/lookthrough.py). Schwellen in config.CONCENTRATION.

Nebenprodukt: FactSheet.exposures (Top-10 je Dimension, direkt vs. via Fonds) — für den Chat
("What is the total semiconductor exposure?") und die Oberfläche.
"""

from __future__ import annotations

from collections import defaultdict

from uro.analytics.format import chf, num, pct, round_chf, slug, truncate
from uro.analytics.lookthrough import Exposure, contributors, exposures, top_exposures
from uro.analytics.positions import is_cash
from uro.config import (
    CONCENTRATION,
    CONCENTRATION_MAX_SINGLE_FINDINGS,
    CONCENTRATION_SINGLE_ERROR,
    EXPOSURE_TOP_N,
    HOME_COUNTRY_GROUP,
    IGNORED_REGION_BUCKETS,
    REPORTING_CURRENCY_GROUP,
)
from uro.ingest import ReferenceIndex
from uro.models import FactSheet, Finding, FindingType, PositionFact, Severity

SOURCE = "clients.json › Portfolios[].SecurityPositions + reference.json › FundUnbundlingMappings"


def _weight(p: PositionFact) -> float:
    return p.client_weight_pct if p.client_weight_pct is not None else p.weight_pct


def _materiality(weight_pct: float, reference: float, aum: float) -> float:
    """Spec §5.9: magnitude = weight / Referenzgrösse, gedeckelt bei 1 → als CHF-Materialität für das Scoring."""
    return min(1.0, (weight_pct / 100) / reference) * aum


def concentration_findings(fs: FactSheet, ref: ReferenceIndex) -> list[Finding]:
    positions = [p for pf in fs.portfolios for p in pf.positions]
    securities = [p for p in positions if not is_cash(p)]
    aum = fs.total_aum_chf
    multi = len(fs.portfolios) > 1
    out: list[Finding] = []

    exp = exposures(positions, ref, _weight)
    fs.exposures = {dim: top_exposures(cats, EXPOSURE_TOP_N) for dim, cats in exp.items()}
    if not securities:
        return out

    # 1) Einzeltitel — über Portfolios hinweg je SecurityId aggregiert
    threshold, reference = CONCENTRATION["security"]
    agg: dict[int, dict] = defaultdict(
        lambda: {"weight": 0.0, "amount": 0.0, "name": "", "portfolios": set()}
    )
    for p in securities:
        a = agg[p.security_id]
        a["weight"] += _weight(p)
        a["amount"] += p.amount_chf
        a["name"] = a["name"] or p.name
        a["portfolios"].add(p.portfolio_nr or "?")
    singles = sorted(agg.items(), key=lambda kv: -kv[1]["weight"])
    for sid, a in singles[:CONCENTRATION_MAX_SINGLE_FINDINGS]:
        weight = num(a["weight"])
        if weight / 100 < threshold:
            break
        amount = round_chf(a["amount"])
        name = truncate(a["name"], 60)
        where = f" (portfolio {', '.join(sorted(a['portfolios']))})" if multi else ""
        severity = Severity.ERROR if weight / 100 >= CONCENTRATION_SINGLE_ERROR else Severity.WARNING
        out.append(
            Finding(
                id=f"conc-single-{slug(a['name'])}",
                type=FindingType.CONCENTRATION,
                severity=severity,
                title=f"{pct(weight)} of assets in a single position: {name}",
                detail=(
                    f"{name} is {pct(weight)} of the client's assets ({chf(amount)}){where}. "
                    f"Above {threshold:.0%} a single position counts as a cluster risk"
                    + (
                        f", above {CONCENTRATION_SINGLE_ERROR:.0%} as severe."
                        if severity == Severity.ERROR
                        else "."
                    )
                ),
                numbers={"weight_pct": weight, "amount_chf": amount},
                security_ids=[sid],
                portfolio_nr=", ".join(sorted(a["portfolios"])),
                materiality_chf=_materiality(weight, reference, aum),
                source=SOURCE,
            )
        )

    # 2) Branche (inkl. Look-through)
    out += _bucket_findings(
        fs, ref, positions, exp["industry"], "industry", "conc-sector", "in sector", exclude=set()
    )

    # 3) Fremdwährung (ohne Reporting-Währung)
    home_ccy = REPORTING_CURRENCY_GROUP.get(fs.reporting_currency, "")
    out += _bucket_findings(
        fs,
        ref,
        positions,
        exp["currency_group"],
        "currency_group",
        "conc-currency",
        "in currency",
        exclude={home_ccy},
    )

    # 4) Region (ohne Heimatregion und Sammelbuckets)
    home_region = HOME_COUNTRY_GROUP.get(fs.reporting_currency, "")
    out += _bucket_findings(
        fs,
        ref,
        positions,
        exp["country_group"],
        "country_group",
        "conc-region",
        "in region",
        exclude=IGNORED_REGION_BUCKETS | {home_region},
    )
    return out


def _bucket_findings(
    fs: FactSheet,
    ref: ReferenceIndex,
    positions: list[PositionFact],
    by_category: dict[str, Exposure],
    dim: str,
    id_prefix: str,
    phrase: str,
    exclude: set[str],
) -> list[Finding]:
    level = {"industry": "industry", "currency_group": "currency", "country_group": "region"}[dim]
    threshold, reference = CONCENTRATION[level]
    out: list[Finding] = []
    for category, e in sorted(by_category.items(), key=lambda kv: -kv[1].total):
        if category in exclude or category == "Not classified":
            continue
        total = num(e.total)
        if total / 100 < threshold:
            break
        direct, via = num(e.direct), num(e.via_funds)
        numbers = {"exposure_pct": total}
        if via > 0:
            breakdown = f"direct {pct(direct)} + {pct(via)} via fund look-through"
            numbers.update(direct_pct=direct, via_funds_pct=via)
        else:
            breakdown = "all direct holdings"
        out.append(
            Finding(
                id=f"{id_prefix}-{slug(category)}",
                type=FindingType.CONCENTRATION,
                severity=Severity.WARNING,
                title=f"{pct(total)} of assets {phrase} {category}",
                detail=f"{category} exposure is {pct(total)} of the client's assets ({breakdown}); the threshold is {threshold:.0%}.",
                numbers=numbers,
                security_ids=contributors(positions, ref, dim, category),
                materiality_chf=_materiality(total, reference, fs.total_aum_chf),
                source=SOURCE,
            )
        )
    return out
