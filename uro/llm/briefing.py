"""OWNER: GIANLUCA — der Briefing-Call.

Modell: claude-opus-5, strukturierter Output über output_config.format.

WARUM NICHT messages.parse(): Der SDK-Helfer hing in der Nacht vom 19.09.
reproduzierbar ohne Rückmeldung — derselbe Request per curl antwortete in 18 s.
Wir bauen das Schema deshalb selbst und parsen die Antwort selbst. Das ist die
in der API-Doku dokumentierte "Raw Schema"-Variante und nachweislich stabil.

Zwei Schema-Regeln, die Structured Outputs erzwingt und Pydantic nicht von
allein liefert (beide kosteten uns eine Stunde):
  - jedes object braucht additionalProperties: false  → model_config extra="forbid"
  - maxItems ist NICHT erlaubt                        → keine max_length auf Listen
Längenbegrenzungen stehen deshalb im Prompt und werden im Validator durchgesetzt.
"""

from __future__ import annotations

import json

import anthropic

from uro.llm.prompts import SYSTEM_PROMPT, render_fact_sheet
from uro.models import Briefing, FactSheet

MODEL = "claude-opus-5"
EFFORT = "low"
MAX_TOKENS = 4000

# Harte Obergrenze. Lieber eine ehrliche Fehlermeldung als ein eingefrorenes UI.
TIMEOUT_SECONDS = 45.0
MAX_RETRIES = 1


def _schema() -> dict:
    return Briefing.model_json_schema()


def generate_briefing(fact_sheet: FactSheet, client: anthropic.Anthropic | None = None) -> Briefing:
    client = client or anthropic.Anthropic(timeout=TIMEOUT_SECONDS, max_retries=MAX_RETRIES)

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": render_fact_sheet(fact_sheet)}],
        output_config={"effort": EFFORT,
                       "format": {"type": "json_schema", "schema": _schema()}},
    )

    if response.stop_reason == "refusal":
        raise RuntimeError("Das Modell hat die Anfrage abgelehnt.")
    if response.stop_reason == "max_tokens":
        raise RuntimeError(f"Antwort bei {MAX_TOKENS} Tokens abgeschnitten — max_tokens erhöhen.")

    text = next(b.text for b in response.content if b.type == "text")
    return Briefing.model_validate(json.loads(text))
