"""OWNER: JACOB — In-Memory-Datenhaltung: laden, nachschlagen, Fact Sheets cachen, Upload mergen.

Der DataStore ist der eine Ort, der die JSON-Dateien liest (neben ingest.py, das er benutzt).
api.py und eval/ bekommen von hier PII-freie Klienten, den ReferenceIndex und gecachte FactSheets.

Zwei Sichten auf einen Klienten:
  - `get_client(ref)`        → das PII-freie Dict (mit _DisplayName und _Age); Basis für die Engine
  - `display_name_for(ref)`  → der Klarname, nur für die Oberfläche, nie im LLM-Pfad

`merge()` (Upload der drei neuen Dateien) wird in Auftrag A4 ausgefüllt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from uro.analytics import build_fact_sheet
from uro.analytics.proposals import open_proposals
from uro.config import settings
from uro.ingest import ReferenceIndex, display_name, get, load_clients, load_reference, lst
from uro.models import ClientSummary, FactSheet, UploadResult


class DataStore:
    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.data_dir = Path(data_dir or settings.data_dir)
        self._clients: list[dict[str, Any]] = []
        self._reference: dict[str, Any] = {}
        self._new_refs: set[str] = set()
        self._fact_sheets: dict[str, FactSheet] = {}
        self.ref: ReferenceIndex = ReferenceIndex({})
        self.reload()

    # -- Laden -------------------------------------------------------------

    def reload(self) -> None:
        """Originaldaten von Platte lesen (auch für POST /api/reset)."""
        self._clients = load_clients(self.data_dir / "clients.json")
        self._reference = load_reference(self.data_dir / "reference.json")
        self._new_refs = set()
        self._rebuild()

    def reset(self) -> None:
        self.reload()

    def _rebuild(self) -> None:
        self.ref = ReferenceIndex(self._reference)
        self._fact_sheets = {}

    # -- Nachschlagen ------------------------------------------------------

    @property
    def clients(self) -> list[dict[str, Any]]:
        return self._clients

    @property
    def reference(self) -> dict[str, Any]:
        return self._reference

    def get_client(self, client_ref: str) -> dict[str, Any] | None:
        for c in self._clients:
            if get(c, "ClientRef") == client_ref:
                return c
        return None

    def display_name_for(self, client_ref: str) -> str:
        c = self.get_client(client_ref)
        if c is None:
            return client_ref
        return str(c.get("_DisplayName") or display_name(c))

    def summary(self, client: dict[str, Any]) -> ClientSummary:
        ref = str(get(client, "ClientRef", "?"))
        aum = float(get(client, "AssetsUnderManagementInDefaultCurrency", 0.0) or 0.0)
        liq = float(get(client, "LiquidityInDefaultCurrency", 0.0) or 0.0)
        violations = lst(client, "SuitabilityViolations")
        return ClientSummary(
            client_ref=ref,
            display_name=str(client.get("_DisplayName") or display_name(client)),
            is_company=bool(get(client, "IsClientACompany", False)),
            risk_profile=get(client, "RiskProfileName"),
            esg_profile=get(client, "EsgProfileName"),
            aum_chf=aum,
            liquidity_pct=round(liq / aum * 100, 1) if aum > 0 else 0.0,
            violation_count=len(violations),
            error_count=sum(1 for v in violations if get(v, "Severity") == "Error"),
            open_proposal_count=len(open_proposals(client)),
            portfolio_count=len(lst(client, "Portfolios")),
            is_new=ref in self._new_refs,
        )

    def list_clients(self, query: str | None = None) -> list[ClientSummary]:
        """Neue (hochgeladene) Klienten zuerst, dann nach ClientRef."""
        rows = [self.summary(c) for c in self._clients]
        if query:
            q = query.lower()
            rows = [r for r in rows if q in r.display_name.lower() or q in r.client_ref.lower()]
        return sorted(rows, key=lambda r: (not r.is_new, r.client_ref))

    # -- Engine ------------------------------------------------------------

    def fact_sheet(self, client_ref: str) -> FactSheet | None:
        """Gecachtes FactSheet; Cache wird bei reload/merge geleert."""
        if client_ref in self._fact_sheets:
            return self._fact_sheets[client_ref]
        client = self.get_client(client_ref)
        if client is None:
            return None
        fs = build_fact_sheet(client, self._reference)
        self._fact_sheets[client_ref] = fs
        return fs

    # -- Upload ------------------------------------------------------------

    def merge(self, payload: object, filename: str) -> UploadResult:
        """Neue Klienten- oder Referenzdatei einspielen. Auftrag A4."""
        raise NotImplementedError("Upload-Merge kommt in Auftrag A4")
