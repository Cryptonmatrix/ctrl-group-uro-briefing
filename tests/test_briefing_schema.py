"""Das Briefing-Schema muss die Regeln der Structured-Outputs-API erfüllen — sonst endet jeder LLM-Aufruf mit HTTP 400.

Beide Regeln sind stille Eigenschaften des Schemas und gehen beim nächsten Umbau von models.py leicht
wieder verloren (docs/blocker-models-schema.md). Diese Tests laufen ohne API-Schlüssel und ohne Netz.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from uro.models import (
    MAX_LIKELY_QUESTIONS,
    MAX_NEXT_BEST_ACTIONS,
    MAX_STATEMENTS_PER_SECTION,
    Briefing,
)


def _objects_without_forbid(node, path="root") -> list[str]:
    hits: list[str] = []
    if isinstance(node, dict):
        if node.get("type") == "object" and node.get("additionalProperties") is not False:
            hits.append(path)
        for key, value in node.items():
            hits += _objects_without_forbid(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            hits += _objects_without_forbid(value, f"{path}[{i}]")
    return hits


def test_every_object_forbids_additional_properties():
    schema = Briefing.model_json_schema()
    assert _objects_without_forbid(schema) == [], (
        "Jedes object im Schema braucht additionalProperties: false. "
        "In Pydantic heisst das model_config = ConfigDict(extra='forbid')."
    )


def test_schema_has_no_max_items():
    assert "maxItems" not in json.dumps(Briefing.model_json_schema()), (
        "maxItems ist in Structured Outputs nicht erlaubt. Kein max_length auf Listen, die ins LLM-Schema gehen — "
        "Grenzen gehören in Briefing.model_post_init."
    )


def _statement(i: int) -> dict:
    return {"text": f"Statement {i}", "type": "fact", "finding_ids": ["profile"]}


def _raw_briefing(n_statements: int, n_questions: int, n_actions: int) -> dict:
    return {
        "headline": "Headline",
        "sections": [{"title": f"Section {s}", "statements": [_statement(i) for i in range(n_statements)]} for s in range(3)],
        "likely_questions": [{"question": f"Q{i}?", "answer_hint": "A"} for i in range(n_questions)],
        "next_best_actions": [
            {"action": f"Action {i}", "rationale": "R", "finding_ids": ["profile"], "priority": 1, "kind": "rebalance"}
            for i in range(n_actions)
        ],
    }


def test_limits_are_enforced_after_parsing_raw_json():
    """So kommt das Briefing aus der API: rohes JSON → model_validate(_json). Die Grenzen greifen trotzdem."""
    b = Briefing.model_validate_json(json.dumps(_raw_briefing(5, 4, 6)))
    assert all(len(s.statements) == MAX_STATEMENTS_PER_SECTION for s in b.sections)
    assert len(b.likely_questions) == MAX_LIKELY_QUESTIONS
    assert len(b.next_best_actions) == MAX_NEXT_BEST_ACTIONS
    assert [a.action for a in b.next_best_actions] == ["Action 0", "Action 1", "Action 2"]  # Reihenfolge bleibt


def test_short_briefings_are_untouched():
    b = Briefing.model_validate(_raw_briefing(1, 0, 1))
    assert [len(s.statements) for s in b.sections] == [1, 1, 1]
    assert b.likely_questions == [] and len(b.next_best_actions) == 1


def test_unknown_fields_are_rejected():
    raw = _raw_briefing(1, 0, 1)
    raw["confidence"] = 0.9
    with pytest.raises(ValidationError):
        Briefing.model_validate(raw)
