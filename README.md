# URO Briefing Assistant

Ein KI-Briefing-Assistent für Vermögensberater, gebaut für die UnRiskOmega-Challenge
„From Ping to Pitch" (START Global × Swiss AI Weeks 2026).

Ein Klick auf **Generate Briefing** verbindet Portfoliodaten, CRM-Kontext, Marktnews und
die Hausmeinung der Bank zu einem Briefing, das ein Berater in etwa 60 Sekunden liest.

## Die Leitidee: die Engine rechnet, die KI erzählt

Eine deterministische Analyse-Engine berechnet **alle** Zahlen und erzeugt daraus
typisierte Befunde mit eindeutiger ID. Das Sprachmodell bekommt nur diese Befunde und darf
sie priorisieren, verknüpfen und formulieren — niemals rechnen. Ein Validator prüft
anschliessend jede Zahl im Text gegen die Befunde und entfernt, was nicht gedeckt ist.

Über alle 47 Klienten gemessen: 47 Briefings erzeugt, fünf ungedeckte Aussagen gefunden
und entfernt, Durchschnitt 13,4 Sekunden und 209 Wörter.

## Einrichten

Voraussetzung ist [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Cryptonmatrix/ctrl-group-uro-briefing.git
cd ctrl-group-uro-briefing
uv sync
cp .env.example .env      # Schlüssel eintragen, siehe unten
```

**Nicht in einem synchronisierten Ordner ablegen** (iCloud, Dropbox, OneDrive). Dort
dauern Dateizugriffe über eine Sekunde, und Python-Importe laufen scheinbar endlos.

### Schlüssel

| Variable | Pflicht | Woher |
|---|---|---|
| `ANTHROPIC_API_KEY` | ja | `console.anthropic.com` → API keys — **einem Workspace zuordnen**, sonst HTTP 400 |
| `GEMINI_API_KEY` | nein | `aistudio.google.com/apikey` — zweite Stufe der Ausfallsicherung |

Das `.env` steht in `.gitignore` und gehört dort hin. Schlüssel in einem öffentlichen
Repository werden binnen Minuten von Bots abgegriffen.

## Starten

```bash
set -a && source .env && set +a
uv run uvicorn uro.api:app --port 8777
```

Dann `http://localhost:8777` öffnen.

Ohne Browser, direkt auf der Kommandozeile:

```bash
uv run python -m uro.demo CASE-003            # vollständiges Briefing
uv run python -m uro.demo CASE-003 --facts    # nur die Engine, kein Schlüssel nötig
```

Batch über alle Klienten — das sind die Zahlen für die Präsentation:

```bash
uv run python -m eval.run_all --briefings --workers 5
```

## Aufbau

```
uro/
├─ models.py       Contracts: FactSheet, Finding, Briefing
├─ ingest.py       laden, normalisieren, PII entfernen
├─ analytics/      die Engine — Performance, SAA, Konzentration, Suitability, Scoring
├─ enrich/         Marktdaten, News, Hausmeinung
├─ llm/            Prompt, Briefing-Aufruf, Validator, Fallback, Chat
├─ report.py       Gesprächsprotokoll zum Ausdrucken
└─ api.py          FastAPI
frontend/index.html   eine Datei, kein Build-Schritt
eval/run_all.py       Batch über alle Klienten
```

`analytics/` ist frei von Netzzugriffen, LLM-Aufrufen und `date.today()`. Das Anthropic-SDK
kommt nur in `llm/` vor, `yfinance` nur in `enrich/`.

## Ausfallsicherung

Drei Stufen, damit der Endpoint immer ein Briefing liefert:

1. Claude (`claude-opus-5`) mit strukturiertem Output
2. Gemini, falls Claude nicht erreichbar ist
3. Ein deterministisches Vorlagen-Briefing aus denselben Befunden

Die Oberfläche kennzeichnet die Herkunft. Fällt eine Marktdatenquelle aus, läuft das
Briefing ohne sie weiter und vermerkt es.

## Daten

Die Falldaten stammen von UnRiskOmega und liegen in `data/`. `docs/data-notes.md` hält
fest, was beim Auswerten wirklich in ihnen steht — unter anderem, dass `PerformanceYTD`
auf allen 57 Portfolios fehlt und dass Felder `null` sein können statt zu fehlen.
