"""OWNER: LEVIN — FastAPI. Die Naht zwischen Engine, LLM und Oberfläche.

Starten:  uv run uvicorn uro.api:app --reload --port 8000
Dann:     http://localhost:8000

Wichtig für die 60-Sekunden-Story: /facts antwortet in Millisekunden und wird
sofort gerendert, waehrend das Briefing noch laeuft. Nie ein leerer Bildschirm.
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from uro.analytics import build_fact_sheet
from uro.ingest import display_name, get, load_clients, load_reference, strip_pii
from uro.models import BriefingResult, ChatRequest

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
FRONTEND = ROOT / "frontend"

_clients: list[dict[str, Any]] = []
_reference: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Einmal beim Start. 17 MB JSON will man nicht pro Request parsen.

    Bewusst lifespan statt @app.on_event: on_event ist veraltet und hing mit
    Starlette 1.6 beim Start, ohne eine Zeile zu loggen.
    """
    global _clients, _reference
    _clients = load_clients(DATA_DIR / "clients.json")
    _reference = load_reference(DATA_DIR / "reference.json")
    yield


app = FastAPI(title="URO Briefing Assistant", lifespan=lifespan)


def _find(ref: str) -> dict[str, Any]:
    for c in _clients:
        if get(c, "ClientRef") == ref:
            return c
    raise HTTPException(status_code=404, detail=f"Kein Klient {ref}")


# Eigener Cache statt lru_cache: der laesst sich beim Upload nicht leeren,
# und dann liefert die API nach dem Hochladen weiter die alten Fact Sheets.
_facts: dict[str, Any] = {}
_new_refs: set[str] = set()
# Letztes Briefing je Klient — der Chat antwortet gegen denselben Kontext,
# aus dem das Briefing entstand. Sonst widersprechen sich die beiden.
_briefings: dict[str, Any] = {}

# Zeitbudget fuer Kurse und News. Lieber ein Briefing ohne Marktkontext als
# eines, das auf der Buehne nicht kommt.
MARKET_BUDGET_SECONDS = 6.0

# Angereicherte Fact Sheets und Notiz-Absichten je Klient. Beide kosten Zeit
# (Netz bzw. ein LLM-Aufruf) und aendern sich zwischen zwei Klicks nicht.
# Beide werden beim Upload und beim Reset mit _facts zusammen geleert.
_enriched: dict[str, Any] = {}
_intents: dict[str, Any] = {}


def _facts_cached(ref: str):
    if ref not in _facts:
        _facts[ref] = build_fact_sheet(_find(ref), _reference)
    return _facts[ref]


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "clients": len(_clients), "llm_ready": bool(os.environ.get("ANTHROPIC_API_KEY"))}


@app.get("/api/clients")
def list_clients() -> list[dict[str, Any]]:
    out = []
    for c in _clients:
        out.append(
            {
                "ref": get(c, "ClientRef"),
                "name": c.get("_DisplayName") or display_name(c),
                "aum": get(c, "AssetsUnderManagementInDefaultCurrency", 0.0),
                "currency": get(c, "ReportingCurrency", "CHF"),
                "risk_profile": get(c, "RiskProfileName"),
                "is_company": bool(get(c, "IsClientACompany", False)),
            "is_new": get(c, "ClientRef") in _new_refs,
            }
        )
    # Hochgeladene zuerst — der unbekannte Testklient soll oben stehen.
    return sorted(out, key=lambda x: (not x["is_new"], x["ref"]))


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
    """Der Generate-Briefing-Knopf.

    Reihenfolge ist Absicht: /facts hat die Befunde schon geliefert und steht
    auf dem Schirm. Erst hier werden Kurse, News und Hausmeinung geholt — mit
    Zeitbudget, damit die Demo nicht an einer langsamen Quelle haengt.
    """
    from uro.enrich import build_snapshot, enrich_fact_sheet
    from uro.llm.briefing import generate_briefing
    from uro.llm.extract_notes import extract_intents
    from uro.llm.transport import (
        LLMAuthError, LLMBadRequest, LLMError, LLMRateLimit, LLMServerError, LLMTimeout,
    )
    from uro.llm.validator import validate

    record = _find(ref)

    # --- Anreicherung. Jede Stufe darf ausfallen, keine darf blockieren. ---
    t_enrich = time.perf_counter()
    if ref in _enriched:
        fs = _enriched[ref]
    else:
        fs = _facts_cached(ref)
        snapshot = None
        try:
            snapshot = build_snapshot(fs, budget_s=MARKET_BUDGET_SECONDS)
        except Exception as exc:  # noqa: BLE001
            fs.warnings.append(f"Marktdaten nicht verfuegbar ({type(exc).__name__})")

        if ref not in _intents:
            try:
                notes = [str(get(n, "Note", "")) for n in (get(record, "ClientNotes") or [])]
                _intents[ref] = extract_intents(notes) if notes else []
            except Exception:  # noqa: BLE001 — Notizen sind ein Bonus, kein Muss
                _intents[ref] = []

        try:
            fs = enrich_fact_sheet(fs, market=snapshot, intents=_intents[ref], client=record)
        except Exception as exc:  # noqa: BLE001
            fs.warnings.append(f"Anreicherung fehlgeschlagen ({type(exc).__name__})")
        _enriched[ref] = fs
    enrich_ms = int((time.perf_counter() - t_enrich) * 1000)

    # --- Briefing. generate_briefing faellt intern auf ein Template zurueck,
    #     deshalb liefert der Endpoint praktisch immer etwas. ---
    t_llm = time.perf_counter()
    try:
        briefing, mode = generate_briefing(fs)
        briefing, issues = validate(briefing, fs)
    except LLMTimeout as exc:
        raise HTTPException(status_code=504, detail=f"{exc} Die Befunde der Engine stehen unten — "
                            "sie stammen aus echten Daten und sind unabhaengig vom Modell.") from None
    except LLMAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from None
    except LLMRateLimit as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from None
    except (LLMServerError, LLMBadRequest, LLMError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    except Exception as exc:  # noqa: BLE001 — nichts darf als Haenger beim Berater ankommen
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from None
    llm_ms = int((time.perf_counter() - t_llm) * 1000)

    _briefings[ref] = briefing
    result = BriefingResult(
        client_ref=ref,
        briefing=briefing,
        fact_sheet=fs,
        issues=issues,
        mode=mode,
        display_name=record.get("_DisplayName", ref),
        timings_ms={"enrich": enrich_ms, "llm": llm_ms, "total": enrich_ms + llm_ms},
        generation_seconds=round((enrich_ms + llm_ms) / 1000, 2),
    )
    return result.model_dump(mode="json")


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict[str, Any]:
    """Neue Klienten- oder Referenzdatei einspielen.

    Der Jury-Testklient kommt als Datei in der Form von clients.json. Deshalb
    darf nirgends ein Dateiname hardcodiert sein — diese Route ist der Beweis.

    Uebergangsloesung in api.py, bis store.merge() (Auftrag A4) fertig ist.
    """
    import json

    raw = await file.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Keine gueltige JSON-Datei: {exc}") from None

    added, updated, errors = [], [], []

    if isinstance(payload, list):
        by_ref = {get(c, "ClientRef"): i for i, c in enumerate(_clients)}
        for entry in payload:
            if not isinstance(entry, dict):
                errors.append("Eintrag ist kein Objekt, uebersprungen.")
                continue
            ref = get(entry, "ClientRef")
            if not ref:
                errors.append("Eintrag ohne ClientRef, uebersprungen.")
                continue
            clean = strip_pii(entry)
            if ref in by_ref:
                _clients[by_ref[ref]] = clean
                updated.append(ref)
            else:
                _clients.append(clean)
                added.append(ref)
            _new_refs.add(ref)
            _facts.pop(ref, None)
            _enriched.pop(ref, None)
            _intents.pop(ref, None)
        reference_merged = False
    elif isinstance(payload, dict):
        for name, rows in payload.items():
            if isinstance(rows, list):
                _reference.setdefault(name, []).extend(rows)
        _facts.clear()
        _enriched.clear()
        _intents.clear()
        reference_merged = True
    else:
        raise HTTPException(status_code=400, detail="Erwartet wird ein Array oder ein Objekt.")

    if not added and not updated and not reference_merged:
        raise HTTPException(status_code=400, detail="Die Datei enthielt keine verwertbaren Klienten.")

    return {
        "added": len(added), "refs": added,
        "added_client_refs": added, "updated_client_refs": updated,
        "reference_merged": reference_merged, "errors": errors,
        "filename": file.filename,
    }


@app.post("/api/reset")
def reset() -> dict[str, Any]:
    """Zurueck auf die ausgelieferten Daten. Fuer den Fall, dass ein Upload die Demo stoert."""
    global _clients, _reference
    _clients = load_clients(DATA_DIR / "clients.json")
    _reference = load_reference(DATA_DIR / "reference.json")
    _facts.clear()
    _enriched.clear()
    _intents.clear()
    _new_refs.clear()
    return {"status": "ok", "clients": len(_clients)}


@app.post("/api/clients/{ref}/chat")
def chat(ref: str, request: ChatRequest) -> dict[str, Any]:
    """Follow-up-Fragen gegen dasselbe Fact Sheet, aus dem das Briefing entstand."""
    fs = _facts_cached(ref)
    if not request.messages:
        raise HTTPException(status_code=400, detail="Keine Frage uebergeben.")

    from uro.llm.chat import answer

    question = request.messages[-1].content
    history = [m.model_dump() for m in request.messages[:-1]]
    try:
        response = answer(question, fs, briefing=_briefings.get(ref), history=history)
    except Exception as exc:  # noqa: BLE001 — eine Frage darf nie die Sitzung beenden
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from None
    return response.model_dump(mode="json")


app.mount("/assets", StaticFiles(directory=ROOT / "assets"), name="assets")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")
