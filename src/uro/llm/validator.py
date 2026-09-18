"""OWNER: GIANLUCA — der Beweis fuer den Pitch-Satz.

"Unser System kann keine Zahl erfinden, weil es keine Zahl selbst rechnet."

Prueft:
  1. Jede Zahl im Text kommt in fact_sheet.all_numbers() vor (mit Toleranz fuer Rundung).
  2. Jede finding_id existiert.
  3. Jede Aussage hat mindestens eine Referenz.
  4. Gesamtlaenge 150-220 Woerter.

Faellt eine Pruefung durch: Aussage entfernen und als ValidationIssue melden.
Das Briefing wird trotzdem ausgeliefert — nie ein leerer Screen.
"""

from __future__ import annotations

from uro.models import Briefing, FactSheet, ValidationIssue


def validate(briefing: Briefing, fact_sheet: FactSheet) -> tuple[Briefing, list[ValidationIssue]]:
    raise NotImplementedError
