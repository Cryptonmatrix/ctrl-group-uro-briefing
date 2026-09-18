"""OWNER: JACOB — Rohdaten laden, normalisieren, PII entfernen.

Kritisch (siehe CLAUDE.md §4): Die Daten enthalten sowohl FEHLENDE Keys als auch
explizite null-Werte. Immer `obj.get("X") or default`, nie nur `.get("X")`.

Muss auch mit den drei neuen Client-Dateien funktionieren, die morgen kommen.
Kein Dateiname darf hardcodiert sein.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

PII_KEYS = {"IBAN", "Birthday", "FirstName", "LastName"}


def load_clients(path: str | Path) -> list[dict[str, Any]]:
    """Laedt eine Datei in der Form von clients.json. Beliebiger Dateiname."""
    raise NotImplementedError


def load_reference(path: str | Path) -> dict[str, Any]:
    """Laedt reference.json. Jede Collection kann komplett fehlen."""
    raise NotImplementedError


def strip_pii(client: dict[str, Any]) -> dict[str, Any]:
    """Entfernt IBANs, Geburtsdaten und Klarnamen. Laeuft VOR allem anderen."""
    raise NotImplementedError


def display_name(client: dict[str, Any]) -> str:
    """4 Firmenkunden haben kein FirstName/LastName, sondern Company."""
    raise NotImplementedError
