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

from typing import Any

from uro.config import EXECUTED_IF_SUBMITTED_STATUSES, OPEN_PROPOSAL_STATUSES, REJECTED_PROPOSAL_STATUSES
from uro.ingest import get, lst


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
