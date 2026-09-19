"""OWNER: JACOB — abgeleitete To-dos. Die Daten enthalten keine Tasks, also leiten wir sie ab (Spec §5.13).

  item-profile-review-due   ProfilingDateUtc älter als 24 Monate (ab data_as_of)
  item-senior-equity        Klient ≥ 60 und Aktienquote über dem SAA-Ziel bzw. über 60 %

Überfällige Proposals (> 60 Tage offen) stehen im Proposal-Finding selbst (boost "overdue follow-up").
"""

from __future__ import annotations

from typing import Any

from uro.analytics.format import date_str, num, pct
from uro.config import PROFILE_REVIEW_MONTHS, SENIOR_AGE
from uro.ingest import get, parse_date
from uro.models import FactSheet, Finding, FindingType, Severity

SOURCE = "clients.json › ProfilingDateUtc, Birthday (as age) vs allocation"


def open_item_findings(fs: FactSheet, client: dict[str, Any]) -> list[Finding]:
    out: list[Finding] = []
    as_of = fs.data_as_of

    profiled = parse_date(get(client, "ProfilingDateUtc"))
    if as_of and profiled:
        months = (as_of.year - profiled.year) * 12 + (as_of.month - profiled.month)
        if months >= PROFILE_REVIEW_MONTHS:
            out.append(
                Finding(
                    id="item-profile-review-due",
                    type=FindingType.OPEN_ITEM,
                    severity=Severity.INFO,
                    title=f"Risk profile last assessed {date_str(profiled)} ({months} months ago) — reassessment due",
                    detail=f"Profiles older than {PROFILE_REVIEW_MONTHS} months should be reconfirmed with the client, especially before changing the allocation.",
                    numbers={"months_since_profiling": float(months)},
                    materiality_chf=fs.total_aum_chf * 0.2,
                    source=SOURCE,
                )
            )

    if fs.age is not None and fs.age >= SENIOR_AGE and fs.total_aum_chf > 0:
        equity = 0.0
        target = None
        for pf in fs.portfolios:
            for p in pf.positions:
                if p.saa_asset_class == "Shares":
                    equity += p.client_weight_pct if p.client_weight_pct is not None else p.weight_pct
            for line in pf.allocation:
                if line.dimension == "AssetClass" and line.category == "Shares" and line.target_pct is not None:
                    target = line.target_pct
        threshold = target if target is not None else 60.0
        equity = num(equity)
        if equity > threshold:
            ref_text = f"SAA target {pct(num(threshold))}" if target is not None else f"{pct(num(threshold))}"
            out.append(
                Finding(
                    id="item-senior-equity",
                    type=FindingType.OPEN_ITEM,
                    severity=Severity.INFO,
                    title=f"Client is {fs.age}; equities are {pct(equity)} of assets, above the {ref_text}",
                    detail="Age and equity share together suggest revisiting the risk capacity and the time horizon in the conversation.",
                    numbers={"age": float(fs.age), "equity_pct": equity, "reference_pct": num(threshold)},
                    materiality_chf=equity / 100 * fs.total_aum_chf * 0.3,
                    source=SOURCE,
                )
            )
    return out
