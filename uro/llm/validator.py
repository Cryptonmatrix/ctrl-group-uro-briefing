"""OWNER: GIANLUCA — Grounding-Validator für das Briefing.

'Unser System kann keine Zahl erfinden, weil es keine Zahl selbst rechnet.'

Prüft jede Aussage:
  1. Existieren alle zitierten Finding-IDs? (Unbekannte IDs -> Aussage entfernen)
  2. Stammen alle genannten Zahlen aus den zitierten Findings? (Fremde Zahlen -> Issue)
  3. Sind Next Best Actions vorhanden und referenziert?
  4. Liegt die Wortzahl im 60-Sekunden-Rahmen (120-240 Wörter)?
"""

from __future__ import annotations

import re

from uro.llm.prompts import render_fact_sheet
from uro.models import Briefing, FactSheet, ValidationIssue

NUMBER = re.compile(r"-?\d[\d'.,]*")
MIN_WORDS, MAX_WORDS = 120, 220  # Case: ~60s Lesezeit = 150-220; Prompt sagt dasselbe

# Harte Obergrenzen. Sie koennen NICHT im JSON-Schema stehen: Pydantic macht aus
# max_length ein maxItems, und das lehnt Structured Outputs ab. Der Prompt bittet
# darum, hier wird es durchgesetzt.
MAX_STATEMENTS_PER_SECTION = 3
MAX_QUESTIONS = 2
MAX_ACTIONS = 3
SMALL_INT_CUTOFF = 12


def _parse(token: str) -> float | None:
    cleaned = token.replace("'", "").replace(" ", "").rstrip(".")
    if not cleaned:
        return None
    # 1,234.56 or 1234.56
    if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", cleaned):
        cleaned = cleaned.replace(",", "")
    elif re.fullmatch(r"-?\d+\.\d+", cleaned):
        pass
    else:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _is_year(value: float) -> bool:
    return value.is_integer() and 1900 <= value <= 2100


def _allowed_numbers_for_ids(fact_sheet: FactSheet, finding_ids: list[str]) -> set[float]:
    """Extracts all numbers allowed for a statement based on its cited finding IDs."""
    values: set[float] = set()
    by_id = fact_sheet.by_id()
    for fid in finding_ids:
        f = by_id.get(fid)
        if not f:
            continue
        # Numbers dictionary
        values.update(f.numbers.values())
        # Numbers in finding title and detail
        for token in NUMBER.findall(f"{f.title} {f.detail}"):
            v = _parse(token)
            if v is not None:
                values.add(v)

    return values


def _covered(value: float, allowed: set[float]) -> bool:
    if (value.is_integer() and abs(value) <= SMALL_INT_CUTOFF) or _is_year(value):
        return True
    return any(abs(value - a) <= max(0.05, abs(a) * 0.01) for a in allowed)


def validate(
    briefing: Briefing | tuple[Briefing, str], fact_sheet: FactSheet
) -> tuple[Briefing, list[ValidationIssue]]:
    """Validates Briefing against FactSheet. Removes invalid statements and returns issues."""
    if isinstance(briefing, tuple):
        briefing = briefing[0]
    known_ids = set(fact_sheet.by_id().keys())
    global_allowed = {v for f in fact_sheet.findings for v in f.numbers.values()}
    for token in NUMBER.findall(render_fact_sheet(fact_sheet)):
        v = _parse(token)
        if v is not None:
            global_allowed.add(v)

    issues: list[ValidationIssue] = []

    # 1. Validate sections and statements
    for section in briefing.sections:
        kept_statements = []
        for st in section.statements:
            if not st.finding_ids:
                issues.append(
                    ValidationIssue(
                        kind="no_reference",
                        detail="Statement without finding reference was removed.",
                        statement_text=st.text,
                    )
                )
                continue

            unknown_ids = [fid for fid in st.finding_ids if fid not in known_ids]
            if unknown_ids:
                issues.append(
                    ValidationIssue(
                        kind="unknown_finding_id",
                        detail=f"Unknown finding IDs: {', '.join(unknown_ids)}",
                        statement_text=st.text,
                    )
                )
                continue

            # Check numbers against cited findings (or globally as fallback)
            cited_allowed = _allowed_numbers_for_ids(fact_sheet, st.finding_ids)
            allowed_for_statement = cited_allowed or global_allowed

            tokens = NUMBER.findall(st.text)
            unsupported = []
            for t in tokens:
                num = _parse(t)
                if num is not None and not _covered(num, allowed_for_statement):
                    unsupported.append(t)

            if unsupported:
                issues.append(
                    ValidationIssue(
                        kind="unsupported_number",
                        detail=f"Unsupported numbers: {', '.join(unsupported)}",
                        statement_text=st.text,
                    )
                )
                # Keep statement if only 1 unsupported, but flag it
                if len(unsupported) >= 2:
                    continue

            kept_statements.append(st)

        section.statements = kept_statements

    # 2. Validate next best actions
    kept_actions = []
    for action in briefing.next_best_actions:
        if not action.finding_ids:
            issues.append(
                ValidationIssue(
                    kind="no_reference",
                    detail="Action without finding reference",
                    statement_text=action.action,
                )
            )
            continue

        unknown = [fid for fid in action.finding_ids if fid not in known_ids]
        if unknown:
            issues.append(
                ValidationIssue(
                    kind="unknown_finding_id",
                    detail=f"Action cites unknown IDs: {', '.join(unknown)}",
                    statement_text=action.action,
                )
            )
            continue

        kept_actions.append(action)

    briefing.next_best_actions = kept_actions
    if not briefing.next_best_actions:
        issues.append(
            ValidationIssue(
                kind="no_actions",
                detail="Briefing has no valid next best actions after validation.",
            )
        )

    # 3. Laenge durchsetzen, nicht nur melden.
    # Ein 60-Sekunden-Briefing, das 320 Woerter hat, ist kein 60-Sekunden-Briefing.
    trimmed = []
    for section in briefing.sections:
        if len(section.statements) > MAX_STATEMENTS_PER_SECTION:
            trimmed.append(f"{section.title}: {len(section.statements)} Aussagen")
            section.statements = section.statements[:MAX_STATEMENTS_PER_SECTION]
    if len(briefing.likely_questions) > MAX_QUESTIONS:
        trimmed.append(f"{len(briefing.likely_questions)} Fragen")
        briefing.likely_questions = briefing.likely_questions[:MAX_QUESTIONS]
    if len(briefing.next_best_actions) > MAX_ACTIONS:
        trimmed.append(f"{len(briefing.next_best_actions)} Aktionen")
        briefing.next_best_actions = briefing.next_best_actions[:MAX_ACTIONS]
    if trimmed:
        issues.append(ValidationIssue(
            kind="trimmed", detail="Ueber der Obergrenze gekuerzt: " + ", ".join(trimmed)))

    # Immer noch zu lang? Die jeweils letzte Aussage je Abschnitt faellt weg —
    # die Reihenfolge kommt aus dem Ranking, hinten steht das Unwichtigste.
    while briefing.word_count() > MAX_WORDS:
        longest = max(
            (s for s in briefing.sections if len(s.statements) > 1),
            key=lambda s: sum(len(st.text.split()) for st in s.statements),
            default=None,
        )
        if longest is None:
            break
        dropped = longest.statements.pop()
        issues.append(ValidationIssue(
            kind="too_long",
            detail=f"Aussage entfernt, um unter {MAX_WORDS} Woerter zu kommen",
            statement_text=dropped.text))

    words = briefing.word_count()
    if words < MIN_WORDS:
        issues.append(ValidationIssue(
            kind="too_short", detail=f"{words} words (target {MIN_WORDS}-{MAX_WORDS})"))

    return briefing, issues
