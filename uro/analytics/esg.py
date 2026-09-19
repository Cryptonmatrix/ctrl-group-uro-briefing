"""OWNER: JACOB — ESG: Positions-Scores gegen das Kundenprofil.

Nur für Klienten mit EsgProfileName "Yes" (17 von 47). Das Profil verlangt (data-notes §7):
  MinimumPositionLevel 5.714 für jede Position, MinimumLevel 5.714 für den gewichteten Schnitt.
SustainabilityScore liegt auf 0–10, höher = besser (Median 7.1).

Die Bank hat genau eine ESG-Regel ("Sustainable investments only"). Meldet sie für den Klienten,
verweist das ESG-Finding per related_ids darauf, statt den Verstoss zu duplizieren.
"""

from __future__ import annotations

from typing import Any

from uro.analytics.format import num, pct, slug, truncate
from uro.analytics.positions import is_cash
from uro.config import ESG_ACTIVE_PROFILE_NAMES, ESG_RULE_KEYWORDS
from uro.ingest import ReferenceIndex, get, lst, to_float
from uro.models import FactSheet, Finding, FindingType, Severity

SOURCE = "reference.json › Securities[].SustainabilityScore vs EsgProfiles[]"


def _weight(p) -> float:
    return p.client_weight_pct if p.client_weight_pct is not None else p.weight_pct


def esg_findings(fs: FactSheet, client: dict[str, Any], ref: ReferenceIndex) -> list[Finding]:
    if not fs.esg_profile or fs.esg_profile not in ESG_ACTIVE_PROFILE_NAMES:
        return []
    profile = ref.esg_profile(get(client, "EsgProfileId")) or {}
    min_position = to_float(get(profile, "MinimumPositionLevel"), 0.0)
    min_level = to_float(get(profile, "MinimumLevel"), 0.0)
    if min_position <= 0 and min_level <= 0:
        return []

    scored = [p for pf in fs.portfolios for p in pf.positions if not is_cash(p) and p.sustainability_score is not None]
    if not scored:
        return []

    esg_violation_ids = [
        f"viol-{slug(str(get(v, 'RuleCode')))}"
        for v in lst(client, "SuitabilityViolations")
        if any(k in str(get(v, "RuleCode", "")).lower() for k in ESG_RULE_KEYWORDS)
    ]
    out: list[Finding] = []

    below = sorted((p for p in scored if p.sustainability_score < min_position), key=lambda p: -_weight(p))
    if below and min_position > 0:
        min_pos = num(min_position)
        worst = num(min(p.sustainability_score for p in below))
        listed = "; ".join(f"{truncate(p.name, 45)} (score {num(p.sustainability_score)}, {pct(num(_weight(p)))} of assets)" for p in below[:3])
        share = num(sum(_weight(p) for p in below))
        out.append(
            Finding(
                id="esg-positions-below-min",
                type=FindingType.ESG,
                severity=Severity.WARNING,
                title=f"ESG preference '{fs.esg_profile}': {len(below)} position(s) below the minimum score {min_pos}",
                detail=f"{listed}. Together {pct(share)} of assets sit below the client's minimum position score of {min_pos} (lowest {worst}).",
                numbers={"min_position_score": min_pos, "lowest_score": worst, "share_pct": share},
                security_ids=sorted({p.security_id for p in below}),
                related_ids=sorted(set(esg_violation_ids)),
                materiality_chf=share / 100 * fs.total_aum_chf,
                source=SOURCE,
            )
        )

    total_w = sum(_weight(p) for p in scored)
    if total_w > 0 and min_level > 0:
        avg = num(sum(_weight(p) * p.sustainability_score for p in scored) / total_w)
        min_lvl = num(min_level)
        if avg < min_lvl:
            out.append(
                Finding(
                    id="esg-portfolio-below-min",
                    type=FindingType.ESG,
                    severity=Severity.WARNING,
                    title=f"Weighted ESG score {avg} is below the portfolio minimum {min_lvl}",
                    detail=f"The weighted sustainability score across {len(scored)} scored positions is {avg}; the client's ESG profile requires at least {min_lvl}.",
                    numbers={"portfolio_score": avg, "min_level": min_lvl},
                    related_ids=sorted(set(esg_violation_ids)),
                    materiality_chf=fs.total_aum_chf * 0.5,
                    source=SOURCE,
                )
            )
    return out
