"""OWNER: JACOB — In-Memory-Datenhaltung: laden, nachschlagen, Fact Sheets cachen, Upload mergen.

Der DataStore ist der eine Ort, der die JSON-Dateien liest (neben ingest.py, das er benutzt).
api.py und eval/ bekommen von hier PII-freie Klienten, den ReferenceIndex und gecachte FactSheets.

Zwei Sichten auf einen Klienten:
  - `get_client(ref)`        → das PII-freie Dict (mit _DisplayName und _Age); Basis für die Engine
  - `display_name_for(ref)`  → der Klarname, nur für die Oberfläche, nie im LLM-Pfad

`merge()` (Upload der drei neuen Dateien) wird in Auftrag A4 ausgefüllt.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from uro.analytics import build_fact_sheet
from uro.analytics.proposals import open_proposals
from uro.config import settings
from uro.ingest import (
    CLIENT_WRAPPER_KEYS,
    ReferenceIndex,
    clients_from_payload,
    display_name,
    engine_view,
    get,
    load_clients,
    load_reference,
    lst,
)
from uro.models import ClientSummary, FactSheet, UploadResult

CLIENT_REF_PATTERN = re.compile(r"[A-Za-z0-9_.\-]{1,64}")

REFERENCE_KEYS: frozenset[str] = frozenset(
    {
        "Securities",
        "FundUnbundlingMappings",
        "SuitabilityRules",
        "RiskProfiles",
        "InvestmentServices",
        "Strategies",
        "StrategicAssetAllocations",
        "ProposalStatuses",
        "AdvisoryTypes",
        "RecommendationLists",
        "EsgProfiles",
        "Tags",
    }
)


CLIENT_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {
        "ClientId",
        "ClientRef",
        "FirstName",
        "LastName",
        "Company",
        "IsClientACompany",
        "IsEmployee",
        "RegulatoryClientTypeId",
        "RegulatoryClientTypeName",
        "ReportingCurrency",
        "RiskProfileId",
        "RiskProfileName",
        "EsgProfileId",
        "EsgProfileName",
        "Birthday",
        "ProfilingDateUtc",
        "AssetsUnderManagementInDefaultCurrency",
        "LiquidityInDefaultCurrency",
        "Portfolios",
        "Proposals",
        "Transactions",
        "SuitabilityViolations",
        "IndividualRuleOverrides",
        "ClientNotes",
    }
)


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

    @property
    def new_refs(self) -> set[str]:
        """Per Upload hinzugefügte ClientRefs (Badge NEW); leer nach reset()."""
        return set(self._new_refs)

    def record(self, client_ref: str) -> dict[str, Any] | None:
        """Der geladene Datensatz inkl. _DisplayName — nur für die Oberfläche (Klientenliste, Kopfzeile)."""
        for c in self._clients:
            if get(c, "ClientRef") == client_ref:
                return c
        return None

    def get_client(self, client_ref: str) -> dict[str, Any] | None:
        """Die Engine-Sicht: ohne Klarnamen. Alles, was Richtung FactSheet, Prompt oder Chat geht, nimmt diese."""
        rec = self.record(client_ref)
        return engine_view(rec) if rec is not None else None

    def display_name_for(self, client_ref: str) -> str:
        rec = self.record(client_ref)
        if rec is None:
            return client_ref
        return str(rec.get("_DisplayName") or display_name(rec))

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
        client = self.get_client(client_ref)  # Engine-Sicht, ohne Klarnamen
        if client is None:
            return None
        fs = build_fact_sheet(client, self._reference)
        self._fact_sheets[client_ref] = fs
        return fs

    # -- Upload ------------------------------------------------------------
    def merge(self, payload: object, filename: str) -> UploadResult:
        """Neue Klienten- oder Referenzdatei einspielen. Auftrag A4."""
        added_client_refs: list[str] = []
        updated_client_refs: list[str] = []
        errors: list[str] = []
        reference_merged = False

        # 1. Referenz-Merge (wenn payload Dict mit Mindestens einem Key aus REFERENCE_KEYS)
        if isinstance(payload, dict):
            is_client_obj = "ClientRef" in payload or "ClientId" in payload
            ref_keys = {k for k in payload.keys() if k in REFERENCE_KEYS}
            if is_client_obj:
                ref_keys.discard("Tags")

            if ref_keys:
                merged_ref: dict[str, Any] = {
                    k: list(v) if isinstance(v, list) else v for k, v in self._reference.items()
                }
                for key, val in payload.items():
                    if key in CLIENT_WRAPPER_KEYS or key in CLIENT_TOP_LEVEL_KEYS:
                        continue
                    if is_client_obj and key == "Tags":
                        continue

                    if not isinstance(val, list):
                        errors.append(f"{filename}: collection {key} must be a list")
                        continue

                    if key == "SuitabilityRules":
                        current_list = list(merged_ref.get("SuitabilityRules") or [])
                        code_to_idx = {
                            r.get("RuleCode"): i
                            for i, r in enumerate(current_list)
                            if isinstance(r, dict) and "RuleCode" in r
                        }
                        for item in val:
                            if not isinstance(item, dict):
                                continue
                            code = item.get("RuleCode")
                            if code and code in code_to_idx:
                                current_list[code_to_idx[code]] = item
                            else:
                                code_to_idx[code] = len(current_list)
                                current_list.append(item)
                        merged_ref["SuitabilityRules"] = current_list

                    elif key == "FundUnbundlingMappings":
                        current_list = list(merged_ref.get("FundUnbundlingMappings") or [])
                        new_fund_ids = {
                            row.get("FundSecurityId")
                            for row in val
                            if isinstance(row, dict) and "FundSecurityId" in row
                        }
                        kept_list = [
                            row
                            for row in current_list
                            if isinstance(row, dict) and row.get("FundSecurityId") not in new_fund_ids
                        ]
                        kept_list.extend(val)
                        merged_ref["FundUnbundlingMappings"] = kept_list

                    else:
                        current_list = list(merged_ref.get(key) or [])
                        id_to_idx = {
                            r.get("Id"): i
                            for i, r in enumerate(current_list)
                            if isinstance(r, dict) and r.get("Id") is not None
                        }
                        for item in val:
                            if isinstance(item, dict) and item.get("Id") is not None:
                                iid = item.get("Id")
                                if iid in id_to_idx:
                                    current_list[id_to_idx[iid]] = item
                                else:
                                    id_to_idx[iid] = len(current_list)
                                    current_list.append(item)
                            else:
                                current_list.append(item)
                        merged_ref[key] = current_list

                # Erst den Index auf dem neuen Stand bauen, dann übernehmen: scheitert er (z. B. Weight "invalid"),
                # bleibt der laufende Datenbestand unberührt, statt danach jede Analyse mit ValueError zu kippen.
                try:
                    new_index = ReferenceIndex(merged_ref)
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        f"{filename}: reference data rejected, nothing changed ({type(exc).__name__}: {exc})"
                    )
                else:
                    self._reference = merged_ref
                    self.ref = new_index
                    self._fact_sheets = {}
                    reference_merged = True

        # 2. Klienten-Merge
        clients = clients_from_payload(payload)
        if clients is not None:
            new_clients = list(self._clients)
            for client in clients:
                ref = get(client, "ClientRef")
                cid = get(client, "ClientId")
                if not ref and cid is None:
                    errors.append(f"{filename}: client entry missing both ClientRef and ClientId")
                    continue
                if ref is not None and (not isinstance(ref, str) or not CLIENT_REF_PATTERN.fullmatch(ref)):
                    # ClientRef landet in URLs und im HTML — nur harmlose Zeichen (CASE-003, TEST_01, …)
                    errors.append(
                        f"{filename}: invalid ClientRef {str(ref)[:40]!r} (allowed: letters, digits, - _ .)"
                    )
                    continue

                # Suche existierenden Klienten in new_clients
                existing_idx = None
                if ref:
                    for idx, c in enumerate(new_clients):
                        if get(c, "ClientRef") == ref:
                            existing_idx = idx
                            break
                elif cid is not None:
                    for idx, c in enumerate(new_clients):
                        if get(c, "ClientId") == cid:
                            existing_idx = idx
                            ref = get(c, "ClientRef")
                            client["ClientRef"] = ref
                            break

                if not ref:
                    errors.append(
                        f"{filename}: client with ClientId {cid} has no ClientRef and is not an existing client"
                    )
                    continue

                # Plausibilitätscheck
                try:
                    build_fact_sheet(engine_view(client), self._reference)
                except Exception as exc:
                    errors.append(f"{filename}: invalid client {ref}: {exc}")
                    continue

                if existing_idx is not None:
                    new_clients[existing_idx] = client
                    if ref not in added_client_refs and ref not in updated_client_refs:
                        updated_client_refs.append(ref)
                else:
                    new_clients.append(client)
                    if ref not in added_client_refs:
                        added_client_refs.append(ref)
                    self._new_refs.add(ref)

            self._clients = new_clients
            self._fact_sheets = {}

        if clients is None and not reference_merged:
            errors.append(f"{filename}: not recognised as client or reference data")

        return UploadResult(
            added_client_refs=added_client_refs,
            updated_client_refs=updated_client_refs,
            reference_merged=reference_merged,
            errors=errors,
        )

    def merge_files(self, files: list[tuple[str, bytes]]) -> UploadResult:
        """Für die Route: dekodiert, Fehler pro Datei, sammelt ein Ergebnis."""
        added_client_refs: list[str] = []
        updated_client_refs: list[str] = []
        reference_merged = False
        errors: list[str] = []

        for filename, content in files:
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                errors.append(f"{filename}: invalid UTF-8 encoding ({exc})")
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                errors.append(f"{filename}: invalid JSON ({exc.msg}, line {exc.lineno})")
                continue

            try:
                res = self.merge(payload, filename)
            except Exception as exc:  # noqa: BLE001 — eine kaputte Datei darf den Upload der anderen nicht kippen
                errors.append(f"{filename}: could not be merged ({type(exc).__name__}: {exc})")
                continue
            for ref in res.added_client_refs:
                if ref not in added_client_refs:
                    added_client_refs.append(ref)
            for ref in res.updated_client_refs:
                if ref not in updated_client_refs:
                    updated_client_refs.append(ref)
            if res.reference_merged:
                reference_merged = True
            errors.extend(res.errors)

        return UploadResult(
            added_client_refs=added_client_refs,
            updated_client_refs=updated_client_refs,
            reference_merged=reference_merged,
            errors=errors,
        )
