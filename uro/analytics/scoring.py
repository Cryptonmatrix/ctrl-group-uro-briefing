"""OWNER: JACOB — Priorisierung. Die Antwort auf 'Wie wählt euer System aus?'

    score = severity × materiality × client_relevance × recency          (CLAUDE.md §7, Zahlen: Spec §5.16)

  severity         Grundgewicht je (FindingType, Severity) aus config.SEVERITY_WEIGHT (Verstoss-Error 1.0 … Notiz 0.2)
  materiality      betroffener Betrag / Vermögen, zwischen 0.2 und 1.0
  client_relevance Boost-Multiplikator, max. 1.6; jeder Grund steht in Finding.boost_reasons:
                     risk-averse client · client needs liquidity (notes) · same position as other key finding
                     · overdue follow-up
  recency          1.1 bei grosser Bewegung seit dem letzten Kontakt, 0.9 für Kontext älter als 12 Monate

Finding.client_relevance speichert den Boost normiert auf 0..1 (1.0 = Cap). Idempotent: ein zweiter Aufruf
(z. B. nachdem News und House View angehängt wurden) rechnet alles neu, statt Boosts zu stapeln.
"""

from __future__ import annotations

from collections import Counter

from uro.config import (
    BOOST_CAP,
    BOOST_LIQUIDITY_NEED,
    BOOST_RISK_AVERSE,
    BOOST_SHARED_POSITION,
    CONSERVATIVE_RISK_LEVEL_MAX,
    MATERIALITY_MIN,
    MAX_PER_TYPE,
    RECENCY_MATERIAL_CHANGE,
    RECENCY_STALE_CONTEXT,
    RECENCY_STALE_MONTHS,
    SEVERITY_DEFAULT,
    SEVERITY_WEIGHT,
    TOP_N_FOR_LLM,
)
from uro.models import FactSheet, Finding, FindingType, Severity

REASON_RISK_AVERSE = "risk-averse client"
REASON_LIQUIDITY = "client needs liquidity (notes)"
REASON_SHARED = "same position as other key finding"
REASON_OVERDUE = "overdue follow-up"
REASON_MATERIAL_CHANGE = "material change since last contact"
SCORING_REASONS = {
    REASON_RISK_AVERSE,
    REASON_LIQUIDITY,
    REASON_SHARED,
}  # vom Scoring gesetzt, bei jedem Lauf neu
OVERDUE_BOOST = 1.1  # Spec §5.13: offenes Proposal > 60 Tage → ×1.1
KEY_FINDING_WEIGHT = 0.7  # "anderes Schlüssel-Finding" = Grundgewicht ≥ 0.7
RISK_TYPES = {FindingType.RISK_PROFILE, FindingType.CONCENTRATION, FindingType.MARKET_COMPARISON}
STALE_CONTEXT_TYPES = {FindingType.CLIENT_NOTE, FindingType.REJECTED_PROPOSAL}

ALWAYS_IN_CONTEXT = {FindingType.CLIENT_PROFILE, FindingType.CLIENT_NOTE}


def _note_order(f: Finding) -> int:
    tail = f.id.rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() else 999


def select_for_llm(
    fs: FactSheet, top_n: int = TOP_N_FOR_LLM
) -> tuple[list[Finding], list[Finding], list[Finding]]:
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


def base_weight(f: Finding) -> float:
    return SEVERITY_WEIGHT.get((f.type.value, f.severity.value), SEVERITY_DEFAULT)


def _is_negative_performance(f: Finding) -> bool:
    return (
        f.type in (FindingType.PERFORMANCE, FindingType.PERFORMANCE_DRIVER) and f.severity == Severity.WARNING
    )


def score_findings(findings: list[Finding], fs: FactSheet) -> list[Finding]:
    """Setzt score, client_relevance, boost_reasons und rank; gibt die Findings absteigend sortiert zurück."""
    aum = max(fs.total_aum_chf, 1.0)
    flags = set(fs.note_flags)
    conservative = (fs.risk_level is not None and fs.risk_level <= CONSERVATIVE_RISK_LEVEL_MAX) or (
        "risk_averse" in flags and "risk_tolerant" not in flags
    )
    needs_liquidity = "liquidity_need" in flags

    # Schlüssel-Findings je Wertpapier, mit Typ: der Boost belohnt Bestätigung aus einer ANDEREN Quelle
    # (Bank-Verstoss + unsere Konzentration auf denselben Titel), nicht Einzeltitel- und Sektor-Klumpen,
    # die zwangsläufig dieselbe Aktie enthalten.
    key_by_security: dict[int, set[tuple[str, FindingType]]] = {}
    for f in findings:
        if base_weight(f) >= KEY_FINDING_WEIGHT:
            for sid in f.security_ids:
                key_by_security.setdefault(sid, set()).add((f.id, f.type))

    for f in findings:
        reasons = [r for r in f.boost_reasons if r not in SCORING_REASONS]
        boost = 1.0
        negative_perf = _is_negative_performance(f)
        if conservative and (f.type in RISK_TYPES or negative_perf):
            boost *= BOOST_RISK_AVERSE
            reasons.append(REASON_RISK_AVERSE)
        shares_over_target = (
            f.id.startswith("saa-assetclass-shares") and f.numbers.get("deviation_pp", 0.0) > 0
        )
        if needs_liquidity and (f.type == FindingType.LIQUIDITY or negative_perf or shares_over_target):
            boost *= BOOST_LIQUIDITY_NEED
            reasons.append(REASON_LIQUIDITY)
        if any(
            other_id != f.id and other_type != f.type
            for sid in f.security_ids
            for other_id, other_type in key_by_security.get(sid, ())
        ):
            boost *= BOOST_SHARED_POSITION
            reasons.append(REASON_SHARED)
        if REASON_OVERDUE in reasons:
            boost *= OVERDUE_BOOST
        boost = min(boost, BOOST_CAP)

        recency = 1.0
        if REASON_MATERIAL_CHANGE in reasons:
            recency = RECENCY_MATERIAL_CHANGE
        elif (
            f.type in STALE_CONTEXT_TYPES
            and f.recency_days is not None
            and f.recency_days > RECENCY_STALE_MONTHS * 30
        ):
            recency = RECENCY_STALE_CONTEXT

        materiality = max(MATERIALITY_MIN, min(1.0, f.materiality_chf / aum))
        f.boost_reasons = list(dict.fromkeys(reasons))
        f.client_relevance = round((boost - 1.0) / (BOOST_CAP - 1.0), 3)
        f.score = round(base_weight(f) * materiality * boost * recency, 3)

    ranked = sorted(findings, key=lambda f: f.score, reverse=True)
    for i, f in enumerate(ranked, start=1):
        f.rank = i
    return ranked
