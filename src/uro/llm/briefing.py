"""OWNER: GIANLUCA — der eigentliche Briefing-Call.

Modell: claude-opus-5
Latenz: output_config={"effort": "low"} + Streaming. Ziel < 15 Sekunden.
Output: strukturiertes JSON via output_config.format, nie Fliesstext.
Kein Prefill — gibt auf Opus 5 einen 400er.
"""

from __future__ import annotations

from uro.models import Briefing, FactSheet

MODEL = "claude-opus-5"


def generate_briefing(fact_sheet: FactSheet) -> Briefing:
    raise NotImplementedError
