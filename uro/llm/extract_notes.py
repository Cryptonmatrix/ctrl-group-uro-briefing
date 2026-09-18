"""OWNER: GIANLUCA — ClientNotes (Freitext) -> ClientIntent[] (strukturiert).

Einmal pro Klient, cachebar. Ergebnis geht an analytics/notes.py, das
deterministisch gegen die Positionen prueft.

Das LLM extrahiert nur Absichten. Es prueft nichts und rechnet nichts.
"""

from __future__ import annotations

from uro.models import ClientIntent


def extract_intents(notes: list[str]) -> list[ClientIntent]:
    raise NotImplementedError
