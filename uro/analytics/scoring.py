"""OWNER: JACOB — Priorisierung. Die Antwort auf 'Wie wählt euer System aus?'

score = severity x materiality x client_relevance
Nur die Top 3-5 kommen ins Briefing, der Rest bleibt im Follow-up-Chat.
"""

from __future__ import annotations

from collections import Counter

from uro.config import MAX_PER_TYPE, TOP_N_FOR_LLM
from uro.models import FactSheet, Finding, FindingType, Severity

ALWAYS_IN_CONTEXT = {FindingType.CLIENT_PROFILE, FindingType.CLIENT_NOTE}


def _note_order(f: Finding) -> int:
    tail = f.id.rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() else 999


def select_for_llm(fs: FactSheet, top_n: int = TOP_N_FOR_LLM) -> tuple[list[Finding], list[Finding], list[Finding]]:
    """Was das Briefing-Modell sieht: (profile, notes, ranked).

    Profil und Notizen sind IMMER dabei — unabhängig vom Score (Contract: "Profil immer im LLM-Kontext").
    `ranked` sind die top_n bestbewerteten übrigen Findings, höchstens MAX_PER_TYPE je Typ (Diversität).
    """
    profile = [f for f in fs.findings if f.type == FindingType.CLIENT_PROFILE]
    notes = sorted((f for f in fs.findings if f.type == FindingType.CLIENT_NOTE), key=_note_order)
    rest = sorted((f for f in fs.findings if f.type not in ALWAYS_IN_CONTEXT), key=lambda f: -f.score)

    ranked: list[Finding] = []
    per_type: Counter[FindingType] = Counter()
    for f in rest:
        if per_type[f.type] >= MAX_PER_TYPE:
            continue
        ranked.append(f)
        per_type[f.type] += 1
        if len(ranked) >= top_n:
            break
    return profile, notes, ranked


SEVERITY_WEIGHT = {
    Severity.ERROR: 3.0,
    Severity.WARNING: 2.0,
    Severity.INFO: 1.0,
    Severity.OPPORTUNITY: 1.0,  # Chancen zaehlen wie Beobachtungen; Feinjustierung kommt mit config.SEVERITY_WEIGHT (A2)
}


def score_findings(findings: list[Finding], total_aum_chf: float) -> list[Finding]:
    base = max(total_aum_chf, 1.0)
    for f in findings:
        materiality = 0.2 + 0.8 * min(1.0, f.materiality_chf / base)
        relevance = 0.5 + 0.5 * f.client_relevance
        f.score = round(SEVERITY_WEIGHT.get(f.severity, 1.0) * materiality * relevance, 3)
    ranked = sorted(findings, key=lambda f: f.score, reverse=True)
    for i, f in enumerate(ranked, start=1):
        f.rank = i
    return ranked
