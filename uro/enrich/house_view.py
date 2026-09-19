"""OWNER: GIANLUCA — Hausmeinung als JSON laden und mit Portfolio vergleichen.

Vergleicht Allokations-Abweichungen (Ist vs. SAA-Ziel) mit der CIO-Meinung:
  - contrary (z.B. Klient untergewichtet vs. CIO overweight) -> Handlungsbedarf (Severity.WARNING)
  - aligned (z.B. Klient übergewichtet vs. CIO overweight) -> Chance/Bestätigung (Severity.OPPORTUNITY)
  - neutral mit großer Abweichung (>= 10 pp) -> Hinweis (Severity.INFO)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from uro.config import SEVERITY_WEIGHT
from uro.models import FactSheet, Finding, FindingType, Severity

logger = logging.getLogger(__name__)


def load_house_view(path: str = "data/house_view.json") -> dict:
    """Loads house view JSON from data directory."""
    p = Path(path)
    if not p.exists():
        logger.warning("House view file not found at %s. Returning empty views.", path)
        return {"as_of": "", "source": "", "views": []}
    return json.loads(p.read_text(encoding="utf-8"))


def house_view_findings(
    fact_sheet: FactSheet,
    house_view: dict,
    reference: dict | None = None,
) -> list[Finding]:
    """Generates Findings comparing portfolio allocations against the CIO House View."""
    views = house_view.get("views", [])
    if not views:
        return []

    # Map views by (dimension, category)
    view_map = {(v["dimension"], v["category"]): v for v in views}

    findings: list[Finding] = []
    seen_ids: set[str] = set()

    # Recommended securities pool for buy suggestions
    rec_securities = []
    if reference and "Securities" in reference:
        for s in reference["Securities"]:
            if s.get("InRecommendationList") and s.get("EndOfDayPrice"):
                rec_securities.append(s)

    for p in fact_sheet.portfolios:
        # Check explicit allocation lines if present
        allocation_lines = p.allocation

        # If allocation lines are empty, compute asset class weights from positions
        if not allocation_lines and p.positions:
            total_amt = sum(pos.amount_chf for pos in p.positions) or 1.0
            cat_weights: dict[str, float] = {}
            for pos in p.positions:
                cat = pos.saa_asset_class or pos.asset_class or "Shares"
                cat_weights[cat] = cat_weights.get(cat, 0.0) + pos.amount_chf

            # Build synthetic allocation lines for checking against house view
            class _MockLine:
                def __init__(self, dim: str, cat: str, act: float):
                    self.dimension = dim
                    self.category = cat
                    self.actual_pct = act
                    self.target_pct = 50.0 if cat == "Shares" else 30.0 if cat == "Bonds" else 5.0
                    self.deviation_pp = self.actual_pct - self.target_pct

            allocation_lines = [  # type: ignore[assignment]
                _MockLine("AssetClass", cat, (amt / total_amt) * 100)
                for cat, amt in cat_weights.items()
            ]

        for line in allocation_lines:
            view = view_map.get((line.dimension, line.category))
            if not view:
                continue

            stance = view.get("stance", "neutral").lower()
            rationale = view.get("rationale", "")
            tilt = line.deviation_pp if line.deviation_pp is not None else 0.0

            fid = f"hv-{line.dimension.lower()}-{line.category.lower().replace(' ', '-')}"
            if fid in seen_ids:
                continue

            finding: Finding | None = None

            # Case 1: CIO Overweight
            if stance == "overweight":
                if tilt <= -3.0:
                    # Contrary: Portfolio is underweight, but CIO likes it -> Opportunity to buy/rebalance
                    cands = [
                        s.get("SecurityName", "")
                        for s in rec_securities
                        if s.get("SAA_AssetClassName") == line.category
                    ][:3]
                    cand_hint = f" Candidates: {', '.join(cands)}." if cands else ""
                    finding = Finding(
                        id=fid,
                        type=FindingType.HOUSE_VIEW,
                        severity=Severity.WARNING,
                        title=f"Underweight {line.category} ({tilt:+.1f} pp) while CIO is OVERWEIGHT",
                        detail=f"CIO view: '{rationale}'. Portfolio holds {line.actual_pct:.1f}% vs target {line.target_pct or 0.0:.1f}%.{cand_hint}",
                        numbers={
                            "actual_pct": round(line.actual_pct, 1),
                            "target_pct": round(line.target_pct or 0.0, 1),
                            "tilt_pp": round(tilt, 1),
                        },
                        source="house_view",
                        portfolio_nr=p.portfolio_nr,
                    )
                elif tilt >= 3.0:
                    # Aligned
                    finding = Finding(
                        id=fid,
                        type=FindingType.HOUSE_VIEW,
                        severity=Severity.OPPORTUNITY,
                        title=f"Overweight {line.category} ({tilt:+.1f} pp) aligns with CIO OVERWEIGHT",
                        detail=f"CIO view: '{rationale}'. Current weight is {line.actual_pct:.1f}%.",
                        numbers={"actual_pct": round(line.actual_pct, 1), "tilt_pp": round(tilt, 1)},
                        source="house_view",
                        portfolio_nr=p.portfolio_nr,
                    )

            # Case 2: CIO Underweight
            elif stance == "underweight":
                if tilt >= 3.0:
                    # Contrary: Portfolio is overweight, but CIO is underweight -> Risk/rebalance need
                    finding = Finding(
                        id=fid,
                        type=FindingType.HOUSE_VIEW,
                        severity=Severity.WARNING,
                        title=f"Overweight {line.category} ({tilt:+.1f} pp) while CIO is UNDERWEIGHT",
                        detail=f"CIO view: '{rationale}'. Portfolio holds {line.actual_pct:.1f}% vs target {line.target_pct or 0.0:.1f}%.",
                        numbers={
                            "actual_pct": round(line.actual_pct, 1),
                            "target_pct": round(line.target_pct or 0.0, 1),
                            "tilt_pp": round(tilt, 1),
                        },
                        source="house_view",
                        portfolio_nr=p.portfolio_nr,
                    )
                elif tilt <= -3.0:
                    # Aligned
                    finding = Finding(
                        id=fid,
                        type=FindingType.HOUSE_VIEW,
                        severity=Severity.OPPORTUNITY,
                        title=f"Underweight {line.category} ({tilt:+.1f} pp) aligns with CIO UNDERWEIGHT",
                        detail=f"CIO view: '{rationale}'. Current weight is {line.actual_pct:.1f}%.",
                        numbers={"actual_pct": round(line.actual_pct, 1), "tilt_pp": round(tilt, 1)},
                        source="house_view",
                        portfolio_nr=p.portfolio_nr,
                    )

            # Case 3: CIO Neutral with large deviation
            elif stance == "neutral" and abs(tilt) >= 10.0:
                finding = Finding(
                    id=fid,
                    type=FindingType.HOUSE_VIEW,
                    severity=Severity.INFO,
                    title=f"{line.category} deviation of {tilt:+.1f} pp lacks CIO tilt",
                    detail=f"CIO stance is neutral: '{rationale}'. Allocation is {line.actual_pct:.1f}% vs target {line.target_pct or 0.0:.1f}%.",
                    numbers={"actual_pct": round(line.actual_pct, 1), "tilt_pp": round(tilt, 1)},
                    source="house_view",
                    portfolio_nr=p.portfolio_nr,
                )

            if finding:
                # Score computation
                weight = SEVERITY_WEIGHT.get(
                    (finding.type.value, finding.severity.value),
                    0.60 if finding.severity == Severity.WARNING else 0.30,
                )
                finding.score = round(weight * min(1.0, max(0.2, abs(tilt) / 10.0)), 2)
                findings.append(finding)
                seen_ids.add(fid)

    return findings
