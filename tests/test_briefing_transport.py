"""Merge gianluca + levin/frontend-api: Gianlucas Kette (Claude → Gemini → Template) läuft über Levins
Standardbibliotheks-Transport. Ohne Netz: post_messages wird ersetzt."""

from __future__ import annotations

import json
from unittest.mock import patch

from uro.llm import briefing as briefing_module
from uro.llm.briefing import generate_briefing
from uro.llm.client import LLMUnavailable
from uro.llm.transport import LLMTimeout
from uro.models import Briefing


def _api_response(briefing: dict) -> dict:
    return {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(briefing)}]}


def _valid_briefing(fs) -> dict:
    """Ein Briefing, das nur existierende IDs und keine Zahlen enthält — besteht den Validator."""
    fid = fs.findings[0].id
    stmt = {"text": "The portfolio needs a review.", "type": "risk", "finding_ids": [fid]}
    return {
        "headline": "Review the portfolio risk with the client.",
        "sections": [{"title": t, "statements": [stmt]} for t in ("Development", "Health", "Outlook")],
        "likely_questions": [],
        "next_best_actions": [
            {"action": "Discuss the risk limit.", "rationale": "The limit is exceeded.", "finding_ids": [fid],
             "priority": 1, "kind": "client_follow_up"}
        ],
    }


def test_transport_path_returns_ai_briefing(fact_sheets):
    fs = fact_sheets["CASE-A01"]
    with patch.object(briefing_module, "_anthropic_key_configured", return_value=True), patch.object(
        briefing_module, "post_messages", return_value=_api_response(_valid_briefing(fs))
    ) as post, patch.object(briefing_module, "log_llm"):
        result, mode = generate_briefing(fs)
    assert mode == "ai"
    assert isinstance(result, Briefing) and result.next_best_actions
    payload = post.call_args.args[0]
    assert payload["output_config"]["format"]["type"] == "json_schema"
    assert "maxItems" not in json.dumps(payload["output_config"]["format"]["schema"])


def test_transport_timeout_falls_through_to_template(fact_sheets):
    """Levins Punkt: ein Timeout darf die Demo nicht einfrieren — die Kette muss weiterlaufen."""
    fs = fact_sheets["CASE-A01"]
    with patch.object(briefing_module, "_anthropic_key_configured", return_value=True), patch.object(
        briefing_module, "post_messages", side_effect=LLMTimeout("Keine Antwort innerhalb von 45 Sekunden.")
    ), patch("uro.llm.gemini.get_gemini_api_key", side_effect=LLMUnavailable("no key")), patch.object(
        briefing_module, "log_llm"
    ):
        result, mode = generate_briefing(fs)
    assert mode == "fallback"
    assert len(result.sections) == 3
