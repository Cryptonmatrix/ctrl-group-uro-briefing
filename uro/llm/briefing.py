"""OWNER: GIANLUCA — der Briefing-Call.

Modell: claude-opus-5, strukturierter Output über output_config.format.
Transport: uro/llm/transport.py (Standardbibliothek statt SDK — Begründung dort).

Zwei Schema-Regeln, die Structured Outputs erzwingt und Pydantic nicht von
allein liefert (beide kosteten uns eine Stunde):
  - jedes object braucht additionalProperties: false  → model_config extra="forbid"
  - maxItems ist NICHT erlaubt                        → keine max_length auf Listen
Längenbegrenzungen stehen deshalb im Prompt und werden im Validator durchgesetzt.
"""

from __future__ import annotations

import json

from uro.llm.prompts import SYSTEM_PROMPT, render_fact_sheet
from uro.llm.transport import LLMError, post_messages
from uro.models import Briefing, FactSheet

MODEL = "claude-opus-5"
EFFORT = "low"
MAX_TOKENS = 4000
TIMEOUT_SECONDS = 60.0
RETRIES = 1


def build_payload(fact_sheet: FactSheet) -> dict:
    """Getrennt, damit man den Request ohne Netzaufruf inspizieren kann."""
    return {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": [{"type": "text", "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": render_fact_sheet(fact_sheet)}],
        "output_config": {
            "effort": EFFORT,
            "format": {"type": "json_schema", "schema": Briefing.model_json_schema()},
        },
    }


def generate_briefing(fact_sheet: FactSheet) -> Briefing:
    data = post_messages(build_payload(fact_sheet),
                         timeout=TIMEOUT_SECONDS, retries=RETRIES)

    stop = data.get("stop_reason")
    if stop == "refusal":
        raise LLMError("Das Modell hat die Anfrage abgelehnt.")
    if stop == "max_tokens":
        raise LLMError(f"Antwort bei {MAX_TOKENS} Tokens abgeschnitten — max_tokens erhöhen.")

    text = next(b["text"] for b in data["content"] if b["type"] == "text")
    return Briefing.model_validate(json.loads(text))
