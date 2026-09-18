"""OWNER: GIANLUCA — der Briefing-Call.

Modell: claude-opus-5. Strukturierter Output via messages.parse() direkt auf
unser Pydantic-Briefing — kein JSON-Parsing von Hand, keine Prefills.
"""

from __future__ import annotations

import anthropic

from uro.llm.prompts import SYSTEM_PROMPT, render_fact_sheet
from uro.models import Briefing, FactSheet

MODEL = "claude-opus-5"

# Latenz-Stellschraube. Noch nicht gemessen — sobald ein API-Key da ist, hier
# low/medium/high durchprobieren und die Zeit in PITCH.md §6 eintragen.
EFFORT: str | None = None


def generate_briefing(fact_sheet: FactSheet, client: anthropic.Anthropic | None = None) -> Briefing:
    client = client or anthropic.Anthropic()
    kwargs = {}
    if EFFORT:
        kwargs["output_config"] = {"effort": EFFORT}

    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": render_fact_sheet(fact_sheet)}],
        output_format=Briefing,
        **kwargs,
    )
    return response.parsed_output
