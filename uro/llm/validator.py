"""OWNER: GIANLUCA — der Beweis für den Pitch-Satz.

'Unser System kann keine Zahl erfinden, weil es keine Zahl selbst rechnet.'

Prueft jede Aussage. Faellt eine durch, wird sie entfernt und als ValidationIssue
gemeldet. Das Briefing wird trotzdem ausgeliefert — nie ein leerer Screen.
"""

from __future__ import annotations

import re

from uro.llm.prompts import render_fact_sheet
from uro.models import Briefing, FactSheet, ValidationIssue

NUMBER = re.compile(r"-?\d[\d'.,]*")
MIN_WORDS, MAX_WORDS = 120, 260
# Kleine ganze Zahlen sind Zählungen ('drei Positionen'), keine Kennzahlen.
SMALL_INT_CUTOFF = 12


def _parse(token: str) -> float | None:
    cleaned = token.replace("'", "").replace(" ", "")
    if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", cleaned):   # 1,234.56
        cleaned = cleaned.replace(",", "")
    else:
        cleaned = cleaned.replace(",", ".")
    cleaned = cleaned.rstrip(".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _allowed(fact_sheet: FactSheet) -> set[float]:
    values = set(fact_sheet.all_numbers())
    for token in NUMBER.findall(render_fact_sheet(fact_sheet)):
        v = _parse(token)
        if v is not None:
            values.add(v)
    return values


def _covered(value: float, allowed: set[float]) -> bool:
    if value.is_integer() and abs(value) <= SMALL_INT_CUTOFF:
        return True
    return any(abs(value - a) <= max(0.05, abs(a) * 0.01) for a in allowed)


def validate(briefing: Briefing, fact_sheet: FactSheet) -> tuple[Briefing, list[ValidationIssue]]:
    allowed = _allowed(fact_sheet)
    known_ids = {f.id for f in fact_sheet.findings}
    issues: list[ValidationIssue] = []

    for section in briefing.sections:
        kept = []
        for st in section.statements:
            if not st.finding_ids:
                issues.append(ValidationIssue(
                    kind="no_reference", detail="Aussage ohne Finding-Referenz",
                    statement_text=st.text))
                continue

            unknown = [i for i in st.finding_ids if i not in known_ids]
            if unknown:
                issues.append(ValidationIssue(
                    kind="unknown_finding_id", detail=f"Unbekannte IDs: {', '.join(unknown)}",
                    statement_text=st.text))
                continue

            bad = [t for t in NUMBER.findall(st.text)
                   if (v := _parse(t)) is not None and not _covered(v, allowed)]
            if bad:
                issues.append(ValidationIssue(
                    kind="unsupported_number", detail=f"Nicht belegt: {', '.join(bad)}",
                    statement_text=st.text))
                continue

            kept.append(st)
        section.statements = kept

    words = briefing.word_count()
    if not MIN_WORDS <= words <= MAX_WORDS:
        issues.append(ValidationIssue(
            kind="too_long", detail=f"{words} Wörter, Ziel 150-220"))

    return briefing, issues
