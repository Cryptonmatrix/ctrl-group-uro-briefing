"""OWNER: JACOB — Rohdaten laden, normalisieren, PII entfernen, Referenz indizieren.

Kritisch (siehe CLAUDE.md §4): Die Daten enthalten sowohl FEHLENDE Keys als auch
explizite null-Werte. Deshalb überall `get(obj, key, default)` / `lst(obj, key)` aus diesem
Modul statt `obj.get(key)` — das fängt beide Fälle ab.

Muss auch mit den drei neuen Client-Dateien funktionieren, die noch kommen:
kein Dateiname ist hardcodiert, und `load_clients` akzeptiert ein Array, ein
Wrapper-Objekt (`{"clients": [...]}`) oder ein einzelnes Klient-Objekt.

Dieses Modul ist die EINZIGE Stelle, die `FundUnbundlingMappings[].Weight` von 0–100
auf 0–1 umrechnet (ReferenceIndex). Sonst nirgends.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

PII_KEYS = {"IBAN", "Birthday", "FirstName", "LastName"}
CLIENT_WRAPPER_KEYS = ("clients", "Clients", "data", "Data")


# ---------------------------------------------------------------------------
# Defensiver Feldzugriff
# ---------------------------------------------------------------------------


def get(obj: dict[str, Any] | None, key: str, default: Any = None) -> Any:
    """Der einzige erlaubte Feldzugriff auf Case-Daten.

    Fängt drei Fälle ab: obj ist None, key fehlt, key ist explizit null.
    """
    if not obj or not isinstance(obj, dict):
        return default
    value = obj.get(key)
    return default if value is None else value


def lst(obj: dict[str, Any] | None, key: str) -> list[Any]:
    """Wie get(), aber garantiert eine Liste zurück."""
    value = get(obj, key, [])
    return value if isinstance(value, list) else []


def to_float(value: Any, default: float = 0.0) -> float:
    """Zahl aus den Rohdaten. Zahlen-Strings werden geparst, bool und Unlesbares → default.

    bool ist in Python ein int — True als 1.0 zu lesen wäre ein stiller Rechenfehler.
    """
    if value is None or isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


ENGINE_HIDDEN_KEYS = {"_DisplayName"}


def engine_view(client: dict[str, Any]) -> dict[str, Any]:
    """Die Sicht der Engine auf einen Klienten: ohne Klarnamen.

    `_DisplayName` bleibt im geladenen Datensatz für die Oberfläche erhalten (api.py), erreicht
    aber über diese Sicht weder FactSheet noch Prompt. `_Age` (abgeleitet) bleibt.
    Flache Kopie reicht — Unterobjekte sind durch strip_pii bereits PII-frei.
    """
    return {k: v for k, v in client.items() if k not in ENGINE_HIDDEN_KEYS}


# ---------------------------------------------------------------------------
# Datumswerte — die Daten sind zeitlich verschoben, deshalb nie date.today()
# ---------------------------------------------------------------------------


def parse_datetime(value: Any) -> datetime | None:
    """ISO-Datum oder -Zeitstempel (auch mit 'Z') → naive datetime. Sonst None."""
    if not value:
        return None
    text = str(value).strip()
    try:
        if "T" in text or " " in text:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
        return datetime.combine(date.fromisoformat(text[:10]), datetime.min.time())
    except (ValueError, TypeError):
        return None


def parse_date(value: Any) -> date | None:
    dt = parse_datetime(value)
    return dt.date() if dt else None


def client_history_as_of(client: dict[str, Any]) -> date | None:
    """Letztes PerformanceHistory-Datum über alle Portfolios → Anker für Renditen."""
    dates = [
        parse_date(get(h, "Date")) for p in lst(client, "Portfolios") for h in lst(p, "PerformanceHistory")
    ]
    known = [d for d in dates if d]
    return max(known) if known else None


def client_data_as_of(client: dict[str, Any]) -> date | None:
    """Jüngstes Datum aller Klientenfelder → Anker für 'offen seit', Profil-Alter, Notiz-Alter."""
    candidates: list[Any] = [get(client, "ProfilingDateUtc")]
    candidates += [get(n, "CreatedByDateUTC") for n in lst(client, "ClientNotes")]
    for p in lst(client, "Proposals"):
        candidates += [
            get(p, "ProposedDateUTC"),
            get(p, "FinalizedDateUTC"),
            get(p, "TransactionsSubmittedDateUTC"),
        ]
    candidates += [get(v, "LastViolatedDateUTC") for v in lst(client, "SuitabilityViolations")]
    for p in lst(client, "Portfolios"):
        candidates.append(get(p, "FactoryDateUtc"))
        candidates += [get(h, "Date") for h in lst(p, "PerformanceHistory")]
    known = [d for d in (parse_date(c) for c in candidates) if d]
    return max(known) if known else None


def age_years(birthday: Any, as_of: date | None) -> int | None:
    """Alter in vollen Jahren zum Stichtag. Alter ist kein Geburtsdatum und darf ins FactSheet."""
    b = parse_date(birthday)
    if b is None or as_of is None:
        return None
    return as_of.year - b.year - ((as_of.month, as_of.day) < (b.month, b.day))


# ---------------------------------------------------------------------------
# Laden
# ---------------------------------------------------------------------------


def extract_clients(data: Any) -> list[dict[str, Any]] | None:
    """Erkennt die drei Formen einer Klientendatei. None, wenn es keine ist (z. B. reference.json)."""
    if isinstance(data, list):
        return [c for c in data if isinstance(c, dict)]
    if isinstance(data, dict):
        for key in CLIENT_WRAPPER_KEYS:
            if isinstance(data.get(key), list):
                return [c for c in data[key] if isinstance(c, dict)]
        if "ClientRef" in data or "ClientId" in data:
            return [data]
    return None


def clients_from_payload(data: Any) -> list[dict[str, Any]] | None:
    """Erkennt Klientendaten (Array, Wrapper, Einzelobjekt) und entfernt PII. None = keine Klientendatei."""
    clients = extract_clients(data)
    if clients is None:
        return None
    return [strip_pii(c) for c in clients]


def load_clients(path: str | Path) -> list[dict[str, Any]]:
    """Lädt eine Datei in der Form von clients.json (Array, Wrapper oder Einzelobjekt). Beliebiger Dateiname."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    clients = clients_from_payload(data)
    if clients is None:
        raise ValueError(
            f"{path}: not recognised as client data (expected an array of clients, a wrapper object or one client)"
        )
    return clients


def load_reference(path: str | Path) -> dict[str, Any]:
    """Lädt reference.json. Jede Collection kann komplett fehlen."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected an object with reference collections")
    return data


# ---------------------------------------------------------------------------
# PII
# ---------------------------------------------------------------------------


def strip_pii(obj: Any) -> Any:
    """Entfernt IBANs, Geburtsdaten und Klarnamen — rekursiv, VOR allem anderen. Mutiert nichts.

    Auf Klient-Ebene werden vorher zwei abgeleitete, PII-freie Werte gesichert:
      _DisplayName  Klarname für die Oberfläche (geht nie in den LLM-Kontext)
      _Age          Alter in Jahren zum jüngsten Datum der Klientendaten
    """
    if isinstance(obj, list):
        return [strip_pii(x) for x in obj]
    if not isinstance(obj, dict):
        return obj

    out: dict[str, Any] = {}
    is_client = "ClientRef" in obj or "ClientId" in obj
    if is_client:  # nur auf Client-Ebene
        out["_DisplayName"] = display_name(obj)
        out["_Age"] = age_years(get(obj, "Birthday"), client_data_as_of(obj))
    for key, value in obj.items():
        if key in PII_KEYS:
            continue
        out[key] = strip_pii(value)
    if is_client:
        # Freitext (Notizen, Begründungen) geht in Prompt und Chat: Klarname und IBANs auch DORT entfernen,
        # nicht nur als JSON-Schlüssel (Review P2 #17).
        names = {str(obj.get(k) or "").strip() for k in ("FirstName", "LastName", "Company")}
        names.add(display_name(obj).strip())
        patterns = [
            re.compile(rf"\b{re.escape(n)}\b", re.IGNORECASE)
            for n in sorted((n for n in names if len(n) >= 3), key=len, reverse=True)
        ]
        out = {k: (_scrub_free_text(v, patterns) if k in FREE_TEXT_KEYS else v) for k, v in out.items()}
    return out


FREE_TEXT_KEYS = {"ClientNotes", "Proposals", "Transactions"}
IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,3})?\b")


def _scrub_free_text(obj: Any, patterns: list[re.Pattern[str]]) -> Any:
    if isinstance(obj, str):
        text = IBAN_RE.sub("[IBAN removed]", obj)
        for p in patterns:
            text = p.sub("the client", text)
        return text
    if isinstance(obj, list):
        return [_scrub_free_text(x, patterns) for x in obj]
    if isinstance(obj, dict):
        return {k: _scrub_free_text(v, patterns) for k, v in obj.items()}
    return obj


def display_name(client: dict[str, Any]) -> str:
    """Die 4 Firmenkunden haben kein FirstName/LastName, sondern Company."""
    company = get(client, "Company")
    if company:
        return str(company)
    parts = [str(get(client, "FirstName", "")), str(get(client, "LastName", ""))]
    name = " ".join(p for p in parts if p).strip()
    return name or str(get(client, "ClientRef", "Unknown client"))


def index_by(rows: list[dict[str, Any]], key: str) -> dict[Any, dict[str, Any]]:
    """Kleine Hilfe für die Joins aus DATA.md."""
    return {row[key]: row for row in rows if isinstance(row, dict) and row.get(key) is not None}


def find_client(clients: list[dict[str, Any]], ref: str) -> dict[str, Any]:
    for c in clients:
        if get(c, "ClientRef") == ref:
            return c
    raise KeyError(f"No client with ClientRef={ref!r}")


# ---------------------------------------------------------------------------
# ReferenceIndex — alle Lookups aus reference.json an einer Stelle
# ---------------------------------------------------------------------------


class ReferenceIndex:
    """Indizes über reference.json. Jede Collection darf fehlen (DATA.md)."""

    def __init__(self, reference: dict[str, Any] | None) -> None:
        reference = reference or {}
        securities = lst(reference, "Securities")
        self.securities_by_id: dict[int, dict[str, Any]] = index_by(securities, "Id")

        by_isin: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for s in securities:
            isin = get(s, "Isin")
            if isin:
                by_isin[str(isin)].append(s)
        for tranches in by_isin.values():
            tranches.sort(key=lambda s: get(s, "Currency") != "CHF")  # CHF-Tranche zuerst
        self.securities_by_isin: dict[str, list[dict[str, Any]]] = dict(by_isin)

        self.saa_by_id = index_by(lst(reference, "StrategicAssetAllocations"), "Id")
        self.investment_services_by_id = index_by(lst(reference, "InvestmentServices"), "Id")
        self.rules_by_code: dict[str, dict[str, Any]] = index_by(
            lst(reference, "SuitabilityRules"), "RuleCode"
        )
        self.risk_profiles_by_id = index_by(lst(reference, "RiskProfiles"), "Id")
        self.esg_profiles_by_id = index_by(lst(reference, "EsgProfiles"), "Id")
        self.strategies_by_id = index_by(lst(reference, "Strategies"), "Id")
        self.proposal_status_by_id = index_by(lst(reference, "ProposalStatuses"), "Id")

        # Fonds-Look-through: Weight kommt als 0–100 und wird GENAU HIER zu 0–1.
        unbundling: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in lst(reference, "FundUnbundlingMappings"):
            fund_id = get(row, "FundSecurityId")
            weight = get(row, "Weight")
            if fund_id is None or weight is None:
                continue
            converted = dict(row)
            converted["Weight"] = float(weight) / 100.0
            unbundling[fund_id].append(converted)
        self.unbundling_by_fund_id: dict[int, list[dict[str, Any]]] = dict(unbundling)
        # (fund_id, dimension) → [(SAA-Kategorie, Anteil)], gefüllt von analytics.lookthrough.fund_breakdown
        self.lookthrough_cache: dict[tuple[int, str], list[tuple[str, float]] | None] = {}

        recommended: set[int] = set()
        for rec_list in lst(reference, "RecommendationLists"):
            for s in lst(rec_list, "Securities"):
                sid = get(s, "SecurityId")
                if sid is not None:
                    recommended.add(sid)
        self.recommended_security_ids: set[int] = recommended

    # -- Lookups mit leerem Default, damit Detektoren kein None prüfen müssen --

    def security(self, security_id: Any) -> dict[str, Any]:
        return self.securities_by_id.get(security_id, {})

    def security_by_isin(self, isin: Any) -> dict[str, Any] | None:
        tranches = self.securities_by_isin.get(str(isin)) if isin else None
        return tranches[0] if tranches else None

    def saa(self, saa_id: Any) -> dict[str, Any]:
        return self.saa_by_id.get(saa_id, {})

    def investment_service_name(self, saa_id: Any) -> str | None:
        """Mandatsart eines Portfolios über seine SAA, z. B. 'Execution only' oder 'Investment Advisory'."""
        service = self.investment_services_by_id.get(get(self.saa(saa_id), "InvestmentServiceId"))
        return get(service, "Name") if service else None

    def risk_profile(self, profile_id: Any) -> dict[str, Any] | None:
        return self.risk_profiles_by_id.get(profile_id)

    def esg_profile(self, profile_id: Any) -> dict[str, Any] | None:
        return self.esg_profiles_by_id.get(profile_id)

    def rule(self, rule_code: Any) -> dict[str, Any]:
        return self.rules_by_code.get(rule_code, {})


_INDEX_CACHE: dict[int, tuple[dict[str, Any], ReferenceIndex]] = {}


def reference_index(reference: dict[str, Any] | ReferenceIndex) -> ReferenceIndex:
    """Gecachter ReferenceIndex pro Referenz-Objekt (48'101 Look-through-Zeilen baut man nicht 47-mal)."""
    if isinstance(reference, ReferenceIndex):
        return reference
    key = id(reference)
    cached = _INDEX_CACHE.get(key)
    if cached is not None and cached[0] is reference:
        return cached[1]
    index = ReferenceIndex(reference)
    if len(_INDEX_CACHE) >= 4:
        _INDEX_CACHE.clear()
    _INDEX_CACHE[key] = (reference, index)
    return index
