"""Auswahl für das LLM: Profil und Notizen immer, Rest nach Score mit Typ-Diversität."""

from __future__ import annotations

from collections import Counter

from uro.analytics.scoring import select_for_llm
from uro.config import MAX_PER_TYPE
from uro.llm.prompts import render_fact_sheet
from uro.models import FindingType


def test_profile_and_notes_always_selected_even_when_outranked(fact_sheets):
    fs = fact_sheets["CASE-B02"]
    profile, notes, ranked = select_for_llm(fs, top_n=2)
    assert [f.id for f in profile] == ["profile"]
    assert [f.id for f in notes] == ["note-1", "note-2"]
    assert len(ranked) == 2
    assert all(f.type not in {FindingType.CLIENT_PROFILE, FindingType.CLIENT_NOTE} for f in ranked)
    assert [f.score for f in ranked] == sorted((f.score for f in ranked), reverse=True)


def test_ranked_respects_type_diversity(fact_sheets):
    fs = fact_sheets["CASE-B02"]
    _, _, ranked = select_for_llm(fs, top_n=50)
    counts = Counter(f.type for f in ranked)
    assert all(n <= MAX_PER_TYPE for n in counts.values())


def test_render_includes_profile_and_all_notes_regardless_of_top_n(fact_sheets):
    fs = fact_sheets["CASE-A01"]
    text = render_fact_sheet(fs, max_findings=1)
    assert "[profile]" in text
    assert "[note-1]" in text and "[note-3]" in text
    assert "[risk-breach-CASE-A01-01]" in text  # der eine Platz geht an das wichtigste Finding
    assert "Ron" not in text and "Burgundy" not in text
