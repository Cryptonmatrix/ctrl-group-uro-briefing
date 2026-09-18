"""OWNER: JACOB — Rohdaten laden, normalisieren, PII entfernen.

Kritisch (siehe CLAUDE.md §4): Die Daten enthalten sowohl FEHLENDE Keys als auch
explizite null-Werte. Deshalb ueberall `get(obj, key, default)` aus diesem Modul
statt `obj.get(key)` — das faengt beide Faelle ab.

Muss auch mit den drei neuen Client-Dateien funktionieren, die noch kommen.
Kein Dateiname ist hardcodiert.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PII_KEYS = {"IBAN", "Birthday", "FirstName", "LastName"}


def get(obj: dict[str, Any] | None, key: str, default: Any = None) -> Any:
    """Der einzige erlaubte Feldzugriff auf Case-Daten.

    Faengt drei Faelle ab: obj ist None, key fehlt, key ist explizit null.
    """
    if not obj:
        return default
    value = obj.get(key)
    return default if value is None else value


def lst(obj: dict[str, Any] | None, key: str) -> list[Any]:
    """Wie get(), aber garantiert eine Liste zurueck."""
    value = get(obj, key, [])
    return value if isinstance(value, list) else []


def load_clients(path: str | Path) -> list[dict[str, Any]]:
    """Laedt eine Datei in der Form von clients.json. Beliebiger Dateiname."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path}: erwartet wird ein Array von Client-Objekten")
    return [strip_pii(c) for c in data]


def load_reference(path: str | Path) -> dict[str, Any]:
    """Laedt reference.json. Jede Collection kann komplett fehlen."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: erwartet wird ein Objekt")
    return data


def strip_pii(obj: Any) -> Any:
    """Entfernt IBANs, Geburtsdaten und Klarnamen — rekursiv, VOR allem anderen.

    Der Anzeigename wird vorher als _DisplayName gesichert, damit das UI ihn
    zeigen kann. In den LLM-Kontext geht er nicht.
    """
    if isinstance(obj, list):
        return [strip_pii(x) for x in obj]
    if not isinstance(obj, dict):
        return obj

    out = {}
    if "ClientRef" in obj:  # nur auf Client-Ebene
        out["_DisplayName"] = display_name(obj)
    for key, value in obj.items():
        if key in PII_KEYS:
            continue
        out[key] = strip_pii(value)
    return out


def display_name(client: dict[str, Any]) -> str:
    """Die 4 Firmenkunden haben kein FirstName/LastName, sondern Company."""
    company = get(client, "Company")
    if company:
        return str(company)
    parts = [str(get(client, "FirstName", "")), str(get(client, "LastName", ""))]
    name = " ".join(p for p in parts if p).strip()
    return name or str(get(client, "ClientRef", "Unbekannt"))


def index_by(rows: list[dict[str, Any]], key: str) -> dict[Any, dict[str, Any]]:
    """Kleine Hilfe fuer die Joins aus DATA.md."""
    return {row[key]: row for row in rows if key in row}


def find_client(clients: list[dict[str, Any]], ref: str) -> dict[str, Any]:
    for c in clients:
        if get(c, "ClientRef") == ref:
            return c
    raise KeyError(f"Kein Klient mit ClientRef={ref!r}")
