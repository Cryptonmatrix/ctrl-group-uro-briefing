"""OWNER: JACOB — Exposure je Dimension mit Fonds-Look-through.

Eine Funktion für SAA-Vergleich (Portfolio-Gewichte) und Konzentration (Klienten-Gewichte):
`exposures(positions, ref, weight_of, dims)` liefert je Dimension {Kategorie: Exposure(direct, via_funds)}.

Look-through (data-notes §6): `FundUnbundlingMappings` ist ein Kreuzprodukt — jede Zeile trägt alle
vier Dimensionsnamen, Σ Weight über alle Zeilen eines Fonds = 1.0 (der ReferenceIndex hat bereits
durch 100 geteilt). Für eine Dimension reicht deshalb groupby(<Name>).sum(Weight) × Fondsgewicht.
Die Look-through-Zeilen nutzen teils andere Namen als die SAA; das Mapping steht in config.py.

Look-through gilt für Währung, Region und Branche. Die Asset-Klasse kommt aus der eigenen
SAA-Klasse des Fonds (alle gehaltenen Look-through-Fonds sind "Shares", siehe config.py).

Konten (Cash/Krypto) zählen als Liquidity bzw. Crypto in der Asset-Klasse und mit ihrer
Währungsgruppe; Branche und Region haben sie nicht.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from uro.config import (
    LOOKTHROUGH_COUNTRY_DEFAULT,
    LOOKTHROUGH_COUNTRY_MAP,
    LOOKTHROUGH_CURRENCY_DEFAULT,
    LOOKTHROUGH_CURRENCY_GROUPS,
    LOOKTHROUGH_INDUSTRY_MAP,
)
from uro.ingest import ReferenceIndex, get, to_float
from uro.models import PositionFact

DIMENSIONS = ("asset_class", "currency_group", "country_group", "industry")
LOOKTHROUGH_DIMENSIONS = ("currency_group", "country_group", "industry")
UNCLASSIFIED = "Not classified"


@dataclass
class Exposure:
    direct: float = 0.0  # Prozent
    via_funds: float = 0.0  # Prozent

    @property
    def total(self) -> float:
        return self.direct + self.via_funds


def position_category(p: PositionFact, dim: str) -> str | None:
    """SAA-Kategorie einer Position ohne Look-through."""
    if dim == "asset_class":
        return p.saa_asset_class
    if dim == "currency_group":
        return p.currency_group
    if dim == "country_group":
        return p.country_group
    return p.industry


def row_category(row: dict[str, Any], dim: str) -> str | None:
    """SAA-Kategorie einer Look-through-Zeile (Namen der Fonds-Zeilen → Namen der SAA)."""
    if dim == "currency_group":
        name = get(row, "CurrencyGroupName")
        if not name:
            return None
        return name if name in LOOKTHROUGH_CURRENCY_GROUPS else LOOKTHROUGH_CURRENCY_DEFAULT
    if dim == "country_group":
        name = get(row, "CountryGroupName")
        if not name:
            return None
        return LOOKTHROUGH_COUNTRY_MAP.get(name, LOOKTHROUGH_COUNTRY_DEFAULT)
    if dim == "industry":
        name = get(row, "IndustryName")
        return LOOKTHROUGH_INDUSTRY_MAP.get(name, name) if name else None
    return None


def fund_breakdown(ref: ReferenceIndex, fund_id: int, dim: str) -> list[tuple[str, float]] | None:
    """Aufteilung eines Fonds in einer Dimension: [(Kategorie, Anteil 0–1)]. Gecacht im ReferenceIndex
    (ein Fonds hat bis zu 2'958 Zeilen und steckt in vielen Portfolios). None ohne Look-through-Daten."""
    key = (fund_id, dim)
    if key in ref.lookthrough_cache:
        return ref.lookthrough_cache[key]
    rows = ref.unbundling_by_fund_id.get(fund_id)
    result: list[tuple[str, float]] | None = None
    if rows and dim in LOOKTHROUGH_DIMENSIONS:
        acc: dict[str, float] = defaultdict(float)
        for row in rows:
            cat = row_category(row, dim)
            share = to_float(get(row, "Weight"))
            if cat is not None and share != 0.0:
                acc[cat] += share
        result = list(acc.items()) or None
    ref.lookthrough_cache[key] = result
    return result


def exposures(
    positions: Iterable[PositionFact],
    ref: ReferenceIndex,
    weight_of: Callable[[PositionFact], float | None],
    dims: Iterable[str] = DIMENSIONS,
) -> dict[str, dict[str, Exposure]]:
    """Je Dimension: Kategorie → Exposure in Prozent (Gewichtsbasis bestimmt `weight_of`)."""
    dims = tuple(dims)
    out: dict[str, dict[str, Exposure]] = {dim: defaultdict(Exposure) for dim in dims}
    for p in positions:
        weight = float(weight_of(p) or 0.0)
        if weight == 0.0:
            continue
        for dim in dims:
            breakdown = (
                fund_breakdown(ref, p.security_id, dim)
                if p.is_fund_unbundlable and p.security_id > 0 and dim in LOOKTHROUGH_DIMENSIONS
                else None
            )
            if breakdown:
                distributed = 0.0
                for cat, share in breakdown:
                    out[dim][cat].via_funds += weight * share
                    distributed += weight * share
                remainder = weight - distributed
                if remainder > 1e-9:  # Zeilen ohne Kategorie in dieser Dimension → Fonds selbst
                    out[dim][position_category(p, dim) or UNCLASSIFIED].direct += remainder
                continue
            cat = position_category(p, dim)
            if cat is None and dim in ("country_group", "industry") and p.security_id < 0:
                continue  # Konten haben keine Region/Branche
            out[dim][cat or UNCLASSIFIED].direct += weight
    return {dim: dict(cats) for dim, cats in out.items()}


def contributors(positions: Iterable[PositionFact], ref: ReferenceIndex, dim: str, category: str) -> list[int]:
    """SecurityIds, die zu einer Kategorie beitragen — direkt oder über Fonds-Zeilen."""
    ids: set[int] = set()
    for p in positions:
        if p.security_id <= 0:
            continue
        breakdown = fund_breakdown(ref, p.security_id, dim) if p.is_fund_unbundlable else None
        if breakdown:
            if any(cat == category for cat, _ in breakdown):
                ids.add(p.security_id)
        elif position_category(p, dim) == category:
            ids.add(p.security_id)
    return sorted(ids)


def top_exposures(by_category: dict[str, Exposure], n: int) -> list[dict[str, float | str]]:
    """Für FactSheet.exposures: die n grössten Kategorien einer Dimension."""
    rows = sorted(by_category.items(), key=lambda kv: -kv[1].total)[:n]
    return [
        {
            "name": cat,
            "weight_pct": round(e.total, 1),
            "direct_pct": round(e.direct, 1),
            "via_funds_pct": round(e.via_funds, 1),
        }
        for cat, e in rows
    ]
