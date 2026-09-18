"""OWNER: GIANLUCA — System-Prompt und Rendering des Fact Sheets.

Caching: Der System-Prompt ist stabil und wird gecacht (cache_control ephemeral).
Stabiler Teil zuerst, volatile Findings danach — sonst greift der Cache nicht.

Harte Regel im Prompt: das Modell darf keine Zahl produzieren, die nicht in den
uebergebenen Findings steht. Jede Aussage traegt finding_ids.
"""

from __future__ import annotations

from uro.models import FactSheet

SYSTEM_PROMPT = """TODO: hier der stabile System-Prompt.
Zielgruppe: erfahrener Berater unter Zeitdruck. 150-220 Woerter.
Genau drei Abschnitte. Jede Aussage mit finding_ids."""


def render_fact_sheet(fact_sheet: FactSheet) -> str:
    """Findings + Kontext als kompakter Text fuer den User-Turn. Keine PII."""
    raise NotImplementedError
