"""OWNER: LEVIN — FastAPI. Die Naht zwischen Engine, LLM und Frontend.

Endpoints:
  GET  /api/clients                  Liste fuer die Klientenauswahl
  GET  /api/clients/{ref}/facts      FactSheet allein — rendert sofort, < 1s
  POST /api/clients/{ref}/briefing   Der Generate-Briefing-Button
  POST /api/chat/{ref}               Follow-up-Chat
  POST /api/upload                   Neue Client-Datei (die 3 von morgen!)

Wichtig fuer die 60-Sekunden-Story: /facts kommt sofort und wird gerendert,
waehrend das Briefing noch laeuft. Der Berater sieht nie einen leeren Screen.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="URO Briefing Assistant")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
