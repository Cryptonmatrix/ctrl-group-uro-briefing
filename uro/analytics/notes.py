"""OWNER: JACOB (Prüfung) + GIANLUCA (Extraktion) — der Goldschatz.

Jeder der 47 Klienten hat ClientNotes, z.B.:
  "No direct positions in fossil fuels, please."
  "Plans to retire in the next two years, increasing liquidity needs expected."

Ablauf: LLM extrahiert ClientIntent[] (siehe llm/extract_notes.py)
        -> diese Funktion prueft DETERMINISTISCH gegen die Positionen
        -> PREFERENCE_CONFLICT-Findings

Beispiel-Output: "Klientin schliesst fossile Energien aus, haelt aber 4.1% Energiesektor."
Das ist die Verknuepfung, die die Jury 'coherent storyline' nennt.
"""

from __future__ import annotations

from uro.models import ClientIntent, Finding


def check_intents(intents: list[ClientIntent], portfolios, reference) -> list[Finding]:
    raise NotImplementedError
