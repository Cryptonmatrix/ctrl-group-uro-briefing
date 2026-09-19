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
# Zahl mit Kontext: Währung davor, Einheit danach. Kleine ganze Zahlen ("3 months", "Anlageprofil 5", "Q1")
# sind nur OHNE Einheit ausgenommen — "12%" oder "CHF 5" muss belegt sein.
NUMBER_IN_CONTEXT = re.compile(r"(CHF|USD|EUR|GBP)?\s?(-?\d[\d'.,]*)\s?(%|pp|bps)?", re.IGNORECASE)
MIN_WORDS, MAX_WORDS = 120, 220  # Case: ~60s Lesezeit = 150-220; Prompt sagt dasselbe
# Kauf-/Switch-Vorschläge dürfen nur Instrumente nennen, die ein Befund als Kandidat trägt
# (House View mit Empfehlungsliste, offene Proposals mit Positionen) — nie aus dem Profil allein.
BUY_SOURCE_TYPES = {"house_view", "open_proposal"}

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
    """Zahlen, die eine Aussage nennen darf: die der zitierten Findings und ihrer related_ids (ein Schritt).

    Bewusst KEIN Rückgriff auf den ganzen Faktenbestand: Eine Zahl muss aus der Quelle kommen, die zitiert wird.
    """
    values: set[float] = set()
    by_id = fact_sheet.by_id()
    ids = list(finding_ids)
    for fid in finding_ids:
        f = by_id.get(fid)
        if f:
            ids += f.related_ids
    for fid in ids:
        f = by_id.get(fid)
        if not f:
            continue
        values.update(f.numbers.values())
        for token in NUMBER.findall(f"{f.title} {f.detail}"):
            v = _parse(token)
            if v is not None:
                values.add(v)
    return values


def _covered(value: float, allowed: set[float], has_unit: bool = False) -> bool:
    if _is_year(value) and not has_unit:
        return True
    if value.is_integer() and abs(value) <= SMALL_INT_CUTOFF and not has_unit:
        return True
    return any(abs(value - a) <= max(0.05, abs(a) * 0.01) for a in allowed)


def _unsupported(text: str, allowed: set[float]) -> list[str]:
    """Alle Zahlen im Text, die nicht in `allowed` belegt sind (Einheit/Währung heben die Kleinzahl-Ausnahme auf)."""
    out = []
    for m in NUMBER_IN_CONTEXT.finditer(text):
        value = _parse(m.group(2))
        if value is None:
            continue
        has_unit = bool(m.group(1) or m.group(3))
        if not _covered(value, allowed, has_unit):
            out.append(m.group(0).strip())
    return out


def validate(
    briefing: Briefing | tuple[Briefing, str], fact_sheet: FactSheet
) -> tuple[Briefing, list[ValidationIssue]]:
    """Validates Briefing against FactSheet. Removes invalid statements and returns issues."""
    if isinstance(briefing, tuple):
        briefing = briefing[0]
    by_id = fact_sheet.by_id()
    known_ids = set(by_id)
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

            # Jede Zahl muss aus den zitierten Findings stammen — sonst fliegt die Aussage raus (auch bei nur einer)
            unsupported = _unsupported(st.text, _allowed_numbers_for_ids(fact_sheet, st.finding_ids))
            if unsupported:
                issues.append(
                    ValidationIssue(
                        kind="unsupported_number",
                        detail=f"Statement removed, unsupported numbers: {', '.join(unsupported)}",
                        statement_text=st.text,
                    )
                )
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

        # Betrag und Begründung: dieselbe Zahlenprüfung wie bei Aussagen
        unsupported = _unsupported(
            f"{action.action} {action.rationale}", _allowed_numbers_for_ids(fact_sheet, action.finding_ids)
        )
        if unsupported:
            issues.append(
                ValidationIssue(
                    kind="unsupported_number",
                    detail=f"Action removed, unsupported numbers: {', '.join(unsupported)}",
                    statement_text=action.action,
                )
            )
            continue

        # Instrument: Kauf/Switch nur mit einer Quelle, die Kandidaten trägt (House View, offenes Proposal)
        if action.kind.value in ("buy", "switch") and not any(
            by_id[fid].type.value in BUY_SOURCE_TYPES for fid in action.finding_ids
        ):
            issues.append(
                ValidationIssue(
                    kind="unsupported_instrument",
                    detail="Buy/switch action removed: no cited finding names a candidate instrument.",
                    statement_text=action.action,
                )
            )
            continue

        kept_actions.append(action)

    briefing.next_best_actions = kept_actions

    # 2b. Headline und Fragen haben keine finding_ids: ihre Zahlen müssen irgendwo im Fact Sheet belegt sein.
    if _unsupported(briefing.headline, global_allowed):
        issues.append(
            ValidationIssue(
                kind="unsupported_number",
                detail="Headline replaced by the top finding: it contained unsupported numbers.",
                statement_text=briefing.headline,
            )
        )
        top = fact_sheet.top_findings(1)
        briefing.headline = top[0].title if top else "Portfolio overview"
    kept_questions = []
    for lq in briefing.likely_questions:
        if _unsupported(f"{lq.question} {lq.answer_hint}", global_allowed):
            issues.append(
                ValidationIssue(
                    kind="unsupported_number",
                    detail="Likely question removed: unsupported numbers in question or answer hint.",
                    statement_text=lq.question,
                )
            )
            continue
        kept_questions.append(lq)
    briefing.likely_questions = kept_questions
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
        issues.append(
            ValidationIssue(kind="trimmed", detail="Ueber der Obergrenze gekuerzt: " + ", ".join(trimmed))
        )

    # Immer noch zu lang? Die jeweils letzte Aussage je Abschnitt faellt weg —
    # die Reihenfolge kommt aus dem Ranking, hinten steht das Unwichtigste.
    while briefing.word_count() > MAX_WORDS:
        longest = max(
            (s for s in briefing.sections if len(s.statements) > 1),
            key=lambda s: sum(len(st.text.split()) for st in s.statements),
            default=None,
        )
        if longest is not None:
            dropped = longest.statements.pop()
            issues.append(
                ValidationIssue(
                    kind="too_long",
                    detail=f"Aussage entfernt, um unter {MAX_WORDS} Woerter zu kommen",
                    statement_text=dropped.text,
                )
            )
            continue
        # Keine Aussage mehr entbehrlich: Fragen und Aktionen tragen ebenfalls
        # zur Wortzahl bei. Zuerst die letzte Frage, dann die letzte Aktion —
        # die Empfehlungen sind das Wertvollste und gehen zuletzt.
        if len(briefing.likely_questions) > 1:
            briefing.likely_questions.pop()
            issues.append(
                ValidationIssue(
                    kind="too_long", detail=f"Frage entfernt, um unter {MAX_WORDS} Woerter zu kommen"
                )
            )
            continue
        if len(briefing.next_best_actions) > 1:
            briefing.next_best_actions.pop()
            issues.append(
                ValidationIssue(
                    kind="too_long", detail=f"Aktion entfernt, um unter {MAX_WORDS} Woerter zu kommen"
                )
            )
            continue
        break

    words = briefing.word_count()
    if words < MIN_WORDS:
        issues.append(
            ValidationIssue(kind="too_short", detail=f"{words} words (target {MIN_WORDS}-{MAX_WORDS})")
        )

    return briefing, issues
