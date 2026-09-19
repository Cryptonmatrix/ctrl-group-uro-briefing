"""OWNER: GIANLUCA — ClientNotes (Freitext) -> ClientIntent[] (strukturiert).

Extrahiert strukturierte Kundenabsichten:
  - liquidity_need: z.B. Hauskauf, Steuerzahlung mit Betrag
  - exclusion: z.B. keine Waffen, kein Tabak, keine fossilen Energien
  - concern / preference / life_event

Ergebnis geht an analytics/notes.py, das deterministisch gegen das Depot prüft.
"""

from __future__ import annotations

import logging
import re

import anthropic
from pydantic import BaseModel

from uro.config import NOTE_KEYWORDS, get_settings
from uro.llm.client import LLMUnavailable, get_client
from uro.models import ClientIntent

logger = logging.getLogger(__name__)


class IntentList(BaseModel):
    intents: list[ClientIntent]


EXTRACT_PROMPT = """You are an intent extraction engine for private banking CRM notes.
Extract structured intents from the notes.
Categories:
- exclusion: negative ethical/ESG filter (e.g. tobacco, defense, fossil fuels)
- liquidity_need: upcoming cash requirements (e.g. tax payment, real estate purchase)
- preference: style or asset class preference (e.g. high dividends, Swiss equities)
- concern: expressed worries (e.g. market volatility, inflation)
- life_event: retirement, relocation, power of attorney

Rules:
1. Copy the verbatim note sentence into `source_note`.
2. Extract specific amounts or time horizons if mentioned.
3. If a note expresses no actionable intent, do not extract anything."""


def _keyword_fallback_extract(notes: list[str]) -> list[ClientIntent]:
    """Fallback extraction using keywords when LLM API is unavailable."""
    intents: list[ClientIntent] = []
    amount_re = re.compile(r"(?:CHF|EUR|USD|\$)\s*([\d,']+)")

    for n in notes:
        n_lower = n.lower()
        amt_match = amount_re.search(n)
        amt_str = f" Amount: {amt_match.group(0)}" if amt_match else ""

        # Liquidity need
        if any(kw in n_lower for kw in NOTE_KEYWORDS.get("liquidity_need", [])):
            intents.append(
                ClientIntent(
                    kind="liquidity_need",
                    subject="Upcoming cash requirement",
                    detail=f"Client expressed liquidity need.{amt_str}",
                    source_note=n,
                )
            )
            continue

        # Exclusions / ESG
        if (
            any(kw in n_lower for kw in ["fossil", "tobacco", "weapon", "defense", "oil"])
            or "no direct positions" in n_lower
        ):
            intents.append(
                ClientIntent(
                    kind="exclusion",
                    subject="Ethical / ESG exclusion",
                    detail="Client requested exclusion of specific industries/issuers.",
                    source_note=n,
                )
            )
            continue

        # Retirement / life event
        if any(kw in n_lower for kw in NOTE_KEYWORDS.get("retirement", [])):
            intents.append(
                ClientIntent(
                    kind="life_event",
                    subject="Retirement planning",
                    detail="Client planning retirement.",
                    source_note=n,
                )
            )
            continue

        # Volatility / risk concerns
        if any(kw in n_lower for kw in NOTE_KEYWORDS.get("risk_averse", [])):
            intents.append(
                ClientIntent(
                    kind="concern",
                    subject="Volatility sensitivity",
                    detail="Client noted concern regarding market fluctuations.",
                    source_note=n,
                )
            )

    return intents


def extract_intents(notes: list[str], client: anthropic.Anthropic | None = None) -> list[ClientIntent]:
    """Extracts structured client intents from raw CRM notes."""
    if not notes:
        return []

    settings = get_settings()

    try:
        if client is None:
            client = get_client()
    except LLMUnavailable:
        return _keyword_fallback_extract(notes)

    numbered_notes = "\n".join(f"{i + 1}. {note}" for i, note in enumerate(notes))

    try:
        resp = client.messages.parse(
            model=settings.llm_model,
            max_tokens=2000,
            system=[{"type": "text", "text": EXTRACT_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": f"CRM NOTES:\n{numbered_notes}"}],
            output_format=IntentList,
            output_config={"effort": "low"} if settings.llm_effort else None,
        )
        return resp.parsed_output.intents
    except Exception as exc:
        logger.warning("Intent extraction via LLM failed (%s). Falling back to keywords.", exc)
        return _keyword_fallback_extract(notes)
