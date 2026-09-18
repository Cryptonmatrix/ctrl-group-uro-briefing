"""OWNER: LEVIN — FastAPI. Die Naht zwischen Engine, LLM und Oberfläche.

Starten:  uv run uvicorn uro.api:app --reload --port 8000
Dann:     http://localhost:8000

Wichtig für die 60-Sekunden-Story: /facts antwortet in Millisekunden und wird
sofort gerendert, waehrend das Briefing noch laeuft. Nie ein leerer Bildschirm.
"""

from __future__ import annotations

import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from uro.analytics import build_fact_sheet
from uro.ingest import display_name, get, load_clients, load_reference
from uro.models import BriefingResult

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
FRONTEND = ROOT / "frontend"

app = FastAPI(title="URO Briefing Assistant")

_clients: list[dict[str, Any]] = []
_reference: dict[str, Any] = {}


@app.on_event("startup")
def _load() -> None:
    """Einmal beim Start. 17 MB JSON will man nicht pro Request parsen."""
    global _clients, _reference
    _clients = load_clients(DATA_DIR / "clients.json")
    _reference = load_reference(DATA_DIR / "reference.json")


def _find(ref: str) -> dict[str, Any]:
    for c in _clients:
        if get(c, "ClientRef") == ref:
            return c
    raise HTTPException(status_code=404, detail=f"Kein Klient {ref}")


@lru_cache(maxsize=128)
def _facts_cached(ref: str):
    return build_fact_sheet(_find(ref), _reference)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "clients": len(_clients), "llm_ready": bool(os.environ.get("ANTHROPIC_API_KEY"))}


@app.get("/api/clients")
def list_clients() -> list[dict[str, Any]]:
    out = []
    for c in _clients:
        out.append({
            "ref": get(c, "ClientRef"),
            "name": c.get("_DisplayName") or display_name(c),
            "aum": get(c, "AssetsUnderManagementInDefaultCurrency", 0.0),
            "currency": get(c, "ReportingCurrency", "CHF"),
            "risk_profile": get(c, "RiskProfileName"),
            "is_company": bool(get(c, "IsClientACompany", False)),
        })
    return sorted(out, key=lambda x: x["ref"])


@app.get("/api/clients/{ref}/facts")
def client_facts(ref: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    fs = _facts_cached(ref)
    return {
        "display_name": _find(ref).get("_DisplayName", ref),
        "engine_ms": round((time.perf_counter() - t0) * 1000, 1),
        "fact_sheet": fs.model_dump(mode="json"),
    }


@app.post("/api/clients/{ref}/briefing")
def client_briefing(ref: str) -> dict[str, Any]:
    fs = _facts_cached(ref)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY fehlt. Die Engine laeuft, der Briefing-Text braucht einen Schlüssel.",
        )
    from uro.llm.briefing import generate_briefing
    from uro.llm.validator import validate

    t0 = time.perf_counter()
    briefing, issues = validate(generate_briefing(fs), fs)
    result = BriefingResult(
        client_ref=ref, briefing=briefing, fact_sheet=fs, issues=issues,
        generation_seconds=round(time.perf_counter() - t0, 2),
    )
    return result.model_dump(mode="json")


app.mount("/assets", StaticFiles(directory=ROOT / "assets"), name="assets")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")
