"""OWNER: JACOB — Proposals einordnen: offen, umgesetzt, abgelehnt.

Aus den Daten (docs/data-notes.md §9): ProposalStatuses = Entwurf (1) · Final (3) · Abgelehnt (4).
  offen      = Entwurf  ODER  Final ohne TransactionsSubmittedDateUTC   (5 + 65 von 206)
  umgesetzt  = Final mit TransactionsSubmittedDateUTC                   (60)
  abgelehnt  = Abgelehnt — ein Präferenz-Signal des Kunden              (76)

16 von 206 Proposals haben kein ProposedDateUTC → Alter nur berechnen, wenn vorhanden.
Die Findings dazu (prop-<id>, rej-proposals) kommen in Auftrag A2; hier stehen die Helfer,
die schon jetzt FactSheet.open_proposals und ClientSummary brauchen.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from uro.analytics.format import date_str, pct, truncate
from uro.config import (
    EXECUTED_IF_SUBMITTED_STATUSES,
    OPEN_PROPOSAL_STATUSES,
    PROPOSAL_FOLLOW_UP_DAYS,
    REJECTED_PROPOSAL_STATUSES,
)
from uro.ingest import ReferenceIndex, get, lst, parse_date, to_float
from uro.models import FactSheet, Finding, FindingType, Severity

SOURCE = "clients.json › Proposals"
MAX_OPEN_PROPOSAL_FINDINGS = 3


def is_open(proposal: dict[str, Any]) -> bool:
    status = get(proposal, "ProposalStatusName")
    if status in OPEN_PROPOSAL_STATUSES:
        return True
    return status in EXECUTED_IF_SUBMITTED_STATUSES and not get(proposal, "TransactionsSubmittedDateUTC")


def is_executed(proposal: dict[str, Any]) -> bool:
    return get(proposal, "ProposalStatusName") in EXECUTED_IF_SUBMITTED_STATUSES and bool(
        get(proposal, "TransactionsSubmittedDateUTC")
    )


def is_rejected(proposal: dict[str, Any]) -> bool:
    return get(proposal, "ProposalStatusName") in REJECTED_PROPOSAL_STATUSES


def open_proposals(client: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for p in lst(client, "Proposals") if is_open(p)]


def rejected_proposals(client: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for p in lst(client, "Proposals") if is_rejected(p)]


def executed_proposals(client: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for p in lst(client, "Proposals") if is_executed(p)]


def _proposed(p: dict[str, Any]) -> date | None:
    return parse_date(get(p, "ProposedDateUTC"))


def _top_positions(p: dict[str, Any], ref: ReferenceIndex, n: int = 3) -> str:
    """Die grössten vorgeschlagenen Positionen: 'Swiss Confederation 1.5% 2027 8.0%'. Join über ISIN (keine SecurityId)."""
    rows = sorted(lst(p, "SecurityPositions"), key=lambda s: -abs(to_float(get(s, "ProposalValuePercentage"))))[:n]
    parts = []
    for s in rows:
        sec = ref.security_by_isin(get(s, "Isin")) or {}
        name = truncate(str(get(s, "SecurityName") or get(sec, "Name") or get(s, "Isin") or "position"), 45)
        share = to_float(get(s, "ProposalValuePercentage")) * 100
        parts.append(f"{name} {pct(share)}" if share else name)
    return ", ".join(parts)


def proposal_findings(
    fs: FactSheet, client: dict[str, Any], ref: ReferenceIndex, portfolio_nr_by_id: dict[Any, str]
) -> list[Finding]:
    """prop-<id> für offene Proposals (neueste zuerst, max. 3) und rej-proposals für abgelehnte."""
    out: list[Finding] = []
    as_of = fs.data_as_of

    opens = sorted(open_proposals(client), key=lambda p: _proposed(p) or date.min, reverse=True)
    for p in opens[:MAX_OPEN_PROPOSAL_FINDINGS]:
        pid = get(p, "ProposalId")
        proposed = _proposed(p)
        age = (as_of - proposed).days if (as_of and proposed) else None
        status = str(get(p, "ProposalStatusName") or "open")
        reason = truncate(str(get(p, "Reason") or "no reason recorded"), 80)
        notes = get(p, "Notes")
        positions = _top_positions(p, ref)
        overdue = age is not None and age > PROPOSAL_FOLLOW_UP_DAYS

        when = f"from {date_str(proposed)}" if proposed else "(undated)"
        age_part = f", {age} days open" if age is not None else ""
        detail_parts = [f"Status '{status}'."]
        if positions:
            detail_parts.append(f"Proposed positions: {positions}.")
        if notes:
            detail_parts.append(f"Notes: '{truncate(str(notes), 160)}'.")
        if overdue:
            detail_parts.append(f"Open for more than {PROPOSAL_FOLLOW_UP_DAYS} days — follow up in the conversation.")

        out.append(
            Finding(
                id=f"prop-{pid}",
                type=FindingType.OPEN_PROPOSAL,
                severity=Severity.INFO,
                title=f"Open proposal {when}{age_part}: {reason}",
                detail=" ".join(detail_parts),
                numbers={"age_days": float(age)} if age is not None else {},
                portfolio_nr=portfolio_nr_by_id.get(get(p, "PortfolioId")),
                recency_days=age,
                boost_reasons=["overdue follow-up"] if overdue else [],
                materiality_chf=fs.total_aum_chf * 0.1,
                source=SOURCE,
            )
        )

    rejected = rejected_proposals(client)
    if rejected:
        latest = max(rejected, key=lambda p: _proposed(p) or date.min)
        proposed = _proposed(latest)
        reason = truncate(str(get(latest, "Reason") or "no reason recorded"), 80)
        age = (as_of - proposed).days if (as_of and proposed) else None
        out.append(
            Finding(
                id="rej-proposals",
                type=FindingType.REJECTED_PROPOSAL,
                severity=Severity.INFO,
                title=f"Client declined {len(rejected)} proposal(s); latest {date_str(proposed)}: {reason}",
                detail="Declined proposals show what the client does not want — avoid repeating the same pitch and ask what held them back.",
                numbers={"declined_count": float(len(rejected))},
                recency_days=age,
                materiality_chf=fs.total_aum_chf * 0.05,
                source=SOURCE,
            )
        )
    return out
