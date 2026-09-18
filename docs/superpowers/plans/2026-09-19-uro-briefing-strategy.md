# URO Briefing Assistant — Strategieplan für die Umsetzung mit Coding Agents

> **Für Coding-Agenten (Claude Code):** Dieser Plan ist die Arbeitsanweisung. Vor jedem Auftrag lesen:
> (1) `CLAUDE.md` im Repo-Root, (2) den Auftrag in §5 dieses Plans, (3) den referenzierten Spec-Abschnitt in
> `docs/superpowers/specs/2026-09-18-uro-briefing-assistant-design.md`, (4) `docs/data-notes.md` für echte Feldnamen.
> Aufträge sind als Checkboxen (`- [ ]`) geführt. Ein Auftrag = ein Commit-Paket mit eigenem Verify-Schritt.

**Stand:** 2026-09-19, 00:55 · **Pitch:** heute 15:00 · **Feature-Freeze:** 13:30 · **Team:** Levin (C), Jacob (A), Gianluca (B)

> **Revision 00:55 — eingearbeitet: Levins Commit `b1e5d1c` „Durchstich" (00:18).** Layout ist jetzt `uro/` (flach, Ausführung als Modul vom Root:
> `uv run python -m uro.demo CASE-003 --facts`, `uv run python -m eval.run_all`). Implementiert und hier auf 47/47 Klienten verifiziert (297 Findings,
> Engine < 1 ms): `ingest.py` (PII-Strip, `get`/`lst`), `analytics/__init__.py::build_fact_sheet`, `performance.py`, `concentration.py`,
> `suitability.py` (inkl. Vola-vs-MaxVola), `scoring.py`, `llm/prompts.py`, `llm/briefing.py` (`messages.parse`), `llm/validator.py`, `demo.py`,
> `eval/run_all.py`. **Ungetestet:** der LLM-Call (kein API-Key). **Noch Skelett:** `saa.py`, `notes.py`, `enrich/*`, `chat.py`, `extract_notes.py`,
> `api.py` (nur `/health`). **Nicht vorhanden:** Frontend, Tests, Upload, Fallback, `config.py`. Aufträge A1/B1/C1 sind entsprechend revidiert;
> Levins Finding-IDs (`perf-<pnr>`, `conc-single-<pnr>`, `risk-breach-<pnr>`, `gap-*`) sind übernommen.
**Repo:** `https://github.com/Cryptonmatrix/ctrl-group-uro-briefing.git` · ein Branch `main` · **Sprache:** Doku Deutsch, Code/UI/LLM Englisch

**Goal:** Ein Klick auf „Generate Briefing" in einem nachgebauten URO Advisor Pro liefert in < 15 s ein in 60 s lesbares, quellenbelegtes Briefing für **jeden** Klienten, inklusive eines per Upload hinzugefügten, unbekannten Testklienten, plus Follow-up-Chat.

**Architektur:** „Die Engine rechnet, die KI erzählt." Deterministische Analytik erzeugt typisierte `Finding`s mit IDs und vorformatierten Zahlen; Claude schreibt daraus ein strukturiertes Briefing-JSON, in dem jede Aussage Finding-IDs zitiert; ein Validator prüft IDs und Zahlen; bei Fehlschlag ein Retry, dann ein deterministisches Template-Briefing. Der Endpoint liefert **immer** ein Briefing.

**Tech Stack:** Python 3.12 · uv · FastAPI · Pydantic v2 · pandas · yfinance · `anthropic` SDK (`claude-opus-5`) · Vite + React 18 + TypeScript + Tailwind · pytest · ruff

**Spec:** `docs/superpowers/specs/2026-09-18-uro-briefing-assistant-design.md` (Detail-Bauanleitung: Formeln, Schwellen, Prompts, UI-Layout). **Daten:** `docs/data-notes.md`.

---

## Inhalt

0. [Quellenhierarchie — welches Dokument gewinnt](#0-quellenhierarchie)
1. [Entscheidungslog — zwei Pläne, ein Plan](#1-entscheidungslog)
2. [Was die Daten heute Nacht gezeigt haben (Kurzfassung)](#2-datenbefunde)
3. [Zielarchitektur und Dateibaum mit Ownership](#3-zielarchitektur)
4. [Contract-Änderung — einmalig, vor dem Parallelisieren](#4-contract-änderung)
5. [Arbeitspakete als Agenten-Aufträge](#5-arbeitspakete)
6. [Zeitplan mit Uhrzeiten und Streichliste](#6-zeitplan)
7. [Demo-Drehbuch und Pitch-Zahlen](#7-demo)
8. [Betriebsregeln für Coding-Agenten](#8-agentenregeln)
9. [Risiken und Gegenmaßnahmen](#9-risiken)
10. [Offene Team-Entscheidungen (je 1 Minute)](#10-offene-entscheidungen)
11. [Anhang: Session-Start-Prompts pro Rolle](#anhang-session-start-prompts)

---

## 0. Quellenhierarchie

Es gibt jetzt vier Dokumente. Damit kein Agent zwischen ihnen hängen bleibt:

| Rang | Dokument | Was es entscheidet | Bei Widerspruch |
|---|---|---|---|
| 1 | **Dieser Plan, §1 Entscheidungslog** | Alle Stellen, an denen `CLAUDE.md` und Spec sich widersprachen | gewinnt |
| 2 | **`CLAUDE.md`** (Repo) | Team-Entscheidungen, Datenfallen, Ownership, Zeitplan, Pitch-Kern | gewinnt gegen Spec |
| 3 | **`docs/data-notes.md`** | Echte Feldnamen, Kategorie-Strings, gemessene Zahlen | gewinnt gegen Spec und `DATA.md` |
| 4 | **Design-Spec** (`docs/superpowers/specs/…`) | Das *Wie* im Detail: Detektor-Formeln, Schwellen, Ranking, Prompts, Validator, UI-Layout, API-Vertrag | gilt überall, wo 1–3 nichts anderes sagen |

Faustregel für Agenten: **Struktur, Namen und Verträge aus dem Repo; Rechenlogik, Prompts und UI-Details aus der Spec; Feldnamen aus data-notes.** Die Spec beschreibt einen Dateibaum `backend/app/…` — der ist **nicht** maßgeblich, die Abbildung auf `uro/…` steht in §3.

---

## 1. Entscheidungslog

Alle Konflikte zwischen `CLAUDE.md`/Repo-Skeletten (Levins Plan, committed) und der Design-Spec (Jacobs Plan). Entscheidungen sind so getroffen, dass **nichts Committetes umgebaut** werden muss und die Spec-Substanz trotzdem einfließt.

| # | Thema | Repo / CLAUDE.md | Design-Spec | **Entscheidung** | Warum |
|---|---|---|---|---|---|
| D1 | Verzeichnisstruktur | `uro/` flach: `models.py`, `ingest.py`, `analytics/`, `enrich/`, `llm/`, `api.py`, `eval/` | `backend/app/{models,data,analytics/detectors,market,houseview,llm,services,api}` | **`uro/` flach bleibt** (Levin hat um 00:18 von `src/uro/` auf `uro/` umgestellt, weil der Editable-Install nicht griff; Ausführung als Modul vom Root). Spec-Module werden abgebildet (§3). Neu dazu: `config.py`, `store.py`, `service.py`, `analytics/format.py`, `enrich/market.py`, `llm/fallback.py`; `build_fact_sheet` bleibt in `analytics/__init__.py` | Läuft nachweislich auf 47/47; drei Leute arbeiten dagegen. Umbau kostet eine Stunde und bringt nichts |
| D2 | Datenmodell | `Finding` (sprechende IDs, `numbers: dict`, `severity/materiality/relevance/recency`), `FactSheet`, `Briefing` mit `sections[]` | `Fact` (IDs `F1/N1/H1/C1`, vorformatierter `text`), `FactBundle`, `BriefingDraft` mit festen Abschnitten | **Repo-Modelle bleiben**, plus **eine additive Contract-Änderung** (§4): neue `FindingType`s, `Severity.OPPORTUNITY`, `StatementType.ASSESSMENT`, `Finding.related_ids/boost_reasons`, `FactSheet.coverage/warnings/data_as_of/age/exposures`, `NextBestAction.priority/kind`, `BriefingResult.mode/timings_ms`, API-Modelle | `models.py` ist der Vertrag, gegen den bereits parallel gearbeitet wird. Additiv statt Ersatz |
| D3 | Finding-IDs | sprechend (`conc-nvda`) | nummeriert nach Rang (`F1…`) | **Sprechend mit Präfix je Quelle** (Tabelle §3.3). Rang steht im LLM-Rendering als Zusatz (`[saa-shares] (rank 2, score 1.04)`) | Stabil über Läufe, debugbar, Chips im UI lesbar |
| D4 | Statement-Typen | 5: `fact/market/house_view/recommendation/risk` | 3 Typen × 4 Töne, davon `interpretation` | **Repo-Typen + `assessment`** (= Interpretation, kursiv, Label „ASSESSMENT") | Jury-Kriterium „facts vs. interpretations distinguishable" braucht die Interpretation als eigenen Typ; Rest ist vorhanden |
| D5 | Scoring | `score = severity × materiality × client_relevance × recency` (steht auf der Slide) | `base_severity × magnitude × boost` mit Zahlentabellen | **Repo-Formel und -Namen**, **Spec-Zahlen** als Belegung: `severity` = Tabelle §5.16 der Spec, `materiality` = `magnitude` (0.2–1), `client_relevance` = Boost-Tabelle (max 1.6), `recency` = 1.0 / 1.1 bei Bewegung seit letztem Kontakt / 0.9 bei Kontext älter 12 Monate | Eine Formel für Slide und Code |
| D6 | LLM-Modell | `claude-opus-5`, `effort: low`, Streaming | `claude-sonnet-5` | **`claude-opus-5`**, `output_config={"effort": "low"}`, Modell-ID nur in `config.py`, per Env `LLM_MODEL` auf `claude-sonnet-5` umschaltbar, falls die Latenz um 08:30 über 12 s liegt | Team-Entscheidung; Qualität zuerst, Schalter für den Notfall |
| D7 | Strukturierter Output | `output_config.format`, kein Prefill | erzwungener Tool-Call `submit_briefing` | **Structured Outputs**: `client.messages.parse(..., output_format=Briefing)` (SDK-Helfer) bzw. `output_config={"format": {"type": "json_schema", "schema": …}}`. **Kein** forced `tool_choice`, **kein** Prefill | Aktuelle API-Empfehlung (`claude-api`-Skill, Stand 2026); forced `tool_choice` ist auf den neuesten Modellen (Fable 5.1) bereits entfernt, Structured Outputs funktioniert auf Opus 5 und Sonnet 5 gleich |
| D8 | Latenz-UX | `/facts` sofort (< 1 s), Briefing streamt nach | ein Endpoint, kosmetische Ladeschritte | **Beides:** `GET /api/clients/{ref}/facts` rendert Key Findings sofort, `POST …/briefing` liefert das vollständige Briefing (intern `messages.stream()` + `get_final_message()` gegen Timeouts). Echtes Token-Streaming ans UI = Stretch nach 13:30 nicht mehr | Strukturiertes JSON lässt sich nicht sinnvoll partiell rendern; die Facts füllen die Wartezeit |
| D9 | PII | IBAN, Geburtsdatum, Klarname nie im Prompt; LLM sieht `CASE-001` | Profil-Fact mit Name und Alter | **CLAUDE.md gilt.** `FactSheet` ist PII-frei; `age: int` (abgeleitet) ist erlaubt. Klarname nur in `ClientSummary`/UI-Pfad, nie im LLM-Pfad | Pitch-Punkt Datenschutz; Alter ist kein Geburtsdatum |
| D10 | Performance-Treiber | Näherung Gewicht × Kursveränderung (yfinance), als Näherung gekennzeichnet | identisch, plus Sektor/Markt-Vergleich | **Übernehmen inkl. Sektor/Markt-Klassifikation** (Spec §5.5) — das ist die „isoliert oder marktweit?"-Antwort aus dem Case-Beispiel | Beide Pläne einig; Spec liefert die Formel |
| D11 | News-/Kurs-Cache | „cachen" | „live, kein Datei-Cache — Teamentscheidung" | **Live zuerst, In-Memory-Memo pro Prozess, plus Disk-Fallback** `data/cache/market_<date>.json`, das bei jedem erfolgreichen Abruf geschrieben und **nur** gelesen wird, wenn live scheitert (UI-Badge „market data cached from HH:MM"). **→ Team-OK nötig (§10.1)** | Der WLAN-Ausfall auf der Bühne ist das größte Demo-Risiko; „live" bleibt der Normalfall |
| D12 | Fehlende Daten | `DATA_GAP`-Finding, nie stiller Fallback | `coverage: dict[detector → ok/no_data/error]` + Warnungen | **Beides:** `DATA_GAP` für klientenrelevante Lücken (kein Risikoprofil, keine Volatilität, keine SAA) — erscheinen im Briefing; `coverage`/`warnings` für technische Lücken (Markt offline, Detektor-Exception) — erscheinen im UI-Footer | Lücke als Information für den Berater (Pitch), Technik als Transparenz (Jury Robustheit) |
| D13 | Fallback ohne LLM | nicht vorgesehen | deterministisches Template-Briefing, `mode="fallback"` | **Übernehmen** (`llm/fallback.py`, Spec §7.5). Badge „Rule-based briefing (AI unavailable)" | Endpoint liefert immer ein Briefing; Robustheit ist 25 % |
| D14 | Bonus | Prio 1 Chat, Prio 2 Ex-Custody-PDF, Prio 3 Anruf-Trigger | nur Chat | **Chat (Pflicht, 11:00) + Anruf-Popup als Demo-Einstieg (UI-only, ≤ 30 min, Levin)**. Ex-Custody-PDF: **nicht bauen**, auf der Ausblick-Slide erwähnen. `pdfplumber` bleibt harmlos in den Deps | Zeitbudget; der Ping-Einstieg ist billig und trägt die Story |
| D15 | Notizen | LLM extrahiert `ClientIntent[]`, Python prüft deterministisch | Notizen wörtlich als `C*`-Facts + Keyword-Flags für Boosts | **Phase 1:** wörtlich (`note-N`) + Keyword-Flags. **Phase 2:** `extract_notes.py` (Structured Output, 1× pro Klient, im Prozess gecacht) → `PREFERENCE_CONFLICT`/`LIQUIDITY` via `analytics/notes.py` | Wörtlich ist sofort da und halluzinationsfrei; Extraktion liefert den „CHF 15'000 vs. CHF 328"-Befund |
| D16 | Python-Version | 3.12 („nicht 3.14") | 3.12 | **3.13 bleibt.** `.python-version` = 3.13, `uv sync` und der Batch über 47 Klienten laufen damit; alle geplanten Libs (yfinance, pandas) haben 3.13-Wheels. Nicht anfassen | Läuft nachweislich; ein Pin-Wechsel um 1 Uhr bringt nur Risiko |
| D17 | Dependencies | fastapi uvicorn anthropic pydantic python-dateutil pdfplumber httpx; dev pytest | + pandas yfinance python-multipart pydantic-settings ruff | **Ergänzen:** `yfinance pandas python-multipart pydantic-settings`, dev `ruff` | Ohne `python-multipart` kein Upload, ohne `yfinance` keine News |
| D18 | Git | ein Branch, oft committen, `pull --rebase`, beschreibende deutsche Commit-Texte | Conventional Commits `feat(scope): …` | **Repo-Stil bleibt.** Einzige Pflicht-Konvention: Commits, die `models.py` oder `frontend/src/types/api.ts` ändern, beginnen mit **`CONTRACT CHANGE:`** und werden im Teamchat angekündigt | Konsistenz mit dem, was schon im Log steht |
| D19 | Zeitplan | Uhrzeiten: 01:00 Durchstich, 02:00–08:00 Schlaf, 13:30 Freeze, 15:00 Pitch | relative 10-h-Marken | **Uhrzeiten aus CLAUDE.md sind verbindlich** (§6) | Sind mit dem Team abgestimmt |
| D20 | Zeitanker | — | `data_as_of` = letztes PerformanceHistory-Datum | **Zwei Anker:** `history_as_of` (= 2026-07-01, für Renditen) und `data_as_of` (= max. Datum aller Klientenfelder, für „offen seit"/„Profil alt"). Nie `date.today()` in `analytics/` | Proposals reichen bis 2026-09-19; die Historie endet zwei Monate früher |
| D21 | House-View-Format | flache Liste `views: [{dimension, category, stance, rationale}]` (im Skelett dokumentiert) | verschachtelt `asset_classes/regions/sectors/currencies` | **Flache Liste** (Repo). `category`-Strings **exakt** wie SAA-Kategorien in data-notes §3 | Spiegelt die Form der SAA-Mappings; ein Vergleichs-Loop für alle Dimensionen |
| D22 | Ownership `service.py` (Pipeline) | nicht vorgesehen | `services/briefing_service.py` bei Person B | **Levin** (C): er besitzt `api.py` und die Integration; die Pipeline ruft nur Funktionen mit den in §4/§5 fixierten Signaturen | Wer den Durchstich baut, besitzt die Naht |

---

## 2. Datenbefunde

Kurzfassung der Messung von heute Nacht (Details, Tabellen und exakte Strings: `docs/data-notes.md`). Diese Punkte ändern konkret, was gebaut wird:

1. **`null` statt „abwesend".** Alle Top-Level-Keys sind vorhanden, viele `null` (`SuitabilityViolations` 20×, `Proposals` 17×, `RiskProfileId` 4×). `DATA.md` ist hier falsch. → `obj.get(k) or []` überall; Pydantic-Listen mit `None → []`-Validator.
2. **29 von 57 Portfolios haben „No strategy".** Ihre SAA hat Min 0 / Target 0 / Max 1 für alle Klassen → der SAA-Vergleich ist dort leer. Genau diese Portfolios haben 0 gemeldete Verstöße, obwohl 11 davon das Volatilitätslimit des Risikoprofils reißen (CASE-011: 60.6 % vs. 15 %). → `has_real_saa`-Flag; `risk_profile_findings()` ist der Leitplanken-Check für alle; das ist der Pitch-Befund.
3. **Nur `AssetClass`-Mappings haben Min/Max**; Währung, Region, Branche nur Target (258 von 333 Zeilen ohne Bänder). → Bandverletzung bei AssetClass, feste ±10-pp-Schwelle sonst.
4. **Kategorie-Strings mit Tippfehlern sind Join-Keys:** `Specialties andCommodities`, `Andere`, `Not classified`. Look-through nutzt andere Namen (`Raw materials` vs. `Materials`). → Mapping-Tabelle in `config.py`, `house_view.json` mit exakt diesen Strings.
5. **Fund-Look-through-Zeilen tragen alle vier Dimensionen** (Kreuzprodukt, Σ = 100 pro Fonds, negative Gewichte möglich). → `groupby(<Dimension>).sum(Weight)/100`.
6. **Notizen sind Englisch (153/153)**, kurz, und enthalten Beträge („CHF 15,000"), Lebensereignisse, Risikohaltung in **beide** Richtungen („unconcerned by short-term volatility"). → Keyword-Boosts vorsichtig; „volatility" allein ist kein Risikoaversions-Signal.
7. **Keine IBANs in diesem Export** (Key existiert nicht). → `strip_pii()` bleibt (Schema, neue Dateien); Pitch-Formulierung anpassen („das Schema führt IBANs").
8. **Proposals:** `Entwurf` 5 · `Final` ohne Umsetzung 65 · `Final` umgesetzt 60 · `Abgelehnt` 76. → „offen" = Entwurf oder Final ohne Submit-Datum; „abgelehnt" ist ein eigenes, niedrig priorisiertes Präferenz-Finding. 16 Proposals ohne `ProposedDateUTC`; Proposal-Positionen haben **keine `SecurityId`** (nur `Isin`).
9. **`ContributionVolatility` summiert sich zu `Portfolio.Volatility`** → die Risk-Share-Tabelle liegt fertig vor; nichts selbst modellieren.
10. **Alles CHF** (Reporting und Portfolio). → Kein FX im MVP; aber `PortfolioCurrency != ReportingCurrency` als `DATA_GAP` abfangen, falls die neuen Dateien abweichen.
11. **Edge-Cases, die ohne Crash laufen müssen:** 2 Klienten mit 0 Positionen und 100 % Cash (CASE-001, CASE-046); 4 Klienten ohne Risikoprofil (CASE-029–032); 7 Portfolios ohne Volatilität; 1 Klient mit 88 Positionen in 2 Portfolios (CASE-038).
12. **`InRecommendationList == true` bei 403 von 504 Securities** → als Kandidatenfilter fast wertlos; zusätzlich SAA-Klasse, CHF, nicht gehalten, ESG-Score ≥ Kundenminimum.

---

## 3. Zielarchitektur

### 3.1 Datenfluss

```
clients.json ─┐                                       GET /facts  (< 1 s, sofort gerendert)
reference.json┼→ ingest/store ─→ analytics.build_fact_sheet ─→ FactSheet ┬─────────────────────────────▶ UI: Key Findings
house_view.json┘   (PII raus,      (positions, detectors,           │
                    Weight/100)     look-through, scoring)          │
                                                                    ▼
                    enrich/market + enrich/news ──(≤ 8 s Budget)──▶ Findings news-*, mkt-*, hv-*
                                                                    │
                                                                    ▼
                    llm/briefing (claude-opus-5, structured output) → Briefing
                    llm/validator (IDs, Zahlen)  → ok | 1 Retry | llm/fallback (Template)
                                                                    │
                                          POST /briefing ◀──────────┘  BriefingResult (mode, timings, issues)
                                          POST /chat      ◀── llm/chat gegen gecachtes FactSheet + Briefing
                                          POST /upload    ◀── store.merge → neue ClientRefs, Badge NEW
```

**Schichtenregel (Spec §4.3, angepasst):** `api.py → service.py → analytics | enrich | llm → models | ingest/store | config`.
`analytics/` ist **pure** (kein I/O, kein Netz, kein LLM, kein `date.today()`). `yfinance` nur in `enrich/`. Anthropic-SDK nur in `llm/`. JSON-Dateien liest nur `ingest.py`/`store.py`/`enrich/house_view.py`.

### 3.2 Dateibaum mit Ownership (Spec → Repo abgebildet)

```
ctrl-group-uro-briefing/
├─ CLAUDE.md                         Team-Kontext (Anpassungen: Auftrag A0)
├─ PITCH.md                          Pitch-Notizen (Levin)
├─ Makefile                          dev-backend / dev-frontend / test / lint / smoke / eval        [A0]
├─ pyproject.toml · uv.lock · .python-version (3.12) · .env.example · .gitignore (+ logs/, data/cache/)
├─ data/
│  ├─ clients.json · reference.json · DATA.md          (Case-Daten)
│  ├─ house_view.json                                   GIANLUCA  [B2]
│  ├─ sector_proxies.json · ticker_overrides.json       GIANLUCA  [B2]
│  └─ cache/                                            Laufzeit, gitignored
├─ docs/
│  ├─ data-notes.md                                     verifizierte Datenfakten
│  └─ superpowers/{specs,plans}/…                       Spec + dieser Plan
├─ uro/
│  ├─ models.py            Contracts (Finding, FactSheet, Briefing, API-Modelle)     GEMEINSAM, Änderungen nur via Jacob + Teamchat
│  ├─ config.py            Settings (Env) + AnalysisConfig (alle Schwellen, Mappings, Modellname)   JACOB  [A0]
│  ├─ ingest.py            load_clients / load_reference / strip_pii / display_name / ReferenceIndex JACOB  [A1]
│  ├─ store.py             DataStore in-memory: load, get, list, merge(upload), reset                JACOB  [A1, A4]
│  ├─ analytics/
│  │  ├─ format.py         pct / pp / chf / date_str — die EINZIGE Zahlenformatierung               JACOB  [A1]
│  │  ├─ positions.py      Positionstabelle (pandas) über alle Portfolios, inkl. Cash/Crypto         JACOB  [A1]
│  │  ├─ performance.py    Renditen 1M/3M/12M/YTD (Spec §5.4 A) + Treiber (§5.4 B, braucht Kurse)   JACOB  [A1, A3]
│  │  ├─ saa.py            Ist/Soll je Dimension inkl. Look-through, has_real_saa (§5.6)           JACOB  [A2]
│  │  ├─ concentration.py  Titel/Branche/Währung/Region inkl. Look-through (§5.9), exposures        JACOB  [A2]
│  │  ├─ suitability.py    violation_findings (§5.7) + risk_profile_findings (Vola vs MaxVola)      JACOB  [A1]
│  │  ├─ esg.py            ESG-Score vs Profil-Minimum (§5.8)                                       JACOB  [A2]
│  │  ├─ liquidity.py      Cash vs Ziel, Fälligkeiten (§5.11), Cash-only-Fall                       JACOB  [A2]
│  │  ├─ proposals.py      offen / abgelehnt / umgesetzt (§5.12, data-notes §9)                     JACOB  [A2]
│  │  ├─ open_items.py     Profil > 24 Monate, Proposal > 60 Tage, Alter ≥ 60 (§5.13)               JACOB  [A2]
│  │  ├─ notes.py          Keyword-Flags (§5.14) + check_intents gegen Positionen                    JACOB  [A1, A3]
│  │  ├─ scoring.py        score_findings (D5), Diversität, Top-N, related_ids                      JACOB  [A2]
│  │  └─ __init__.py       build_fact_sheet(client, reference) → FactSheet — EXISTIERT (Levin), wird in A1 gehärtet  JACOB  [A1]
│  ├─ enrich/
│  │  ├─ market.py         resolve_tickers (ISIN→Ticker), fetch_prices (Batch), Zeitbudget, Cache   GIANLUCA [B2]
│  │  ├─ news.py           fetch_news (beide yfinance-Formate), Filter 14 Tage, max 6 → news-*      GIANLUCA [B2]
│  │  └─ house_view.py     load_house_view, house_view_findings (§5.15) → hv-* + Kandidaten         GIANLUCA [B2]
│  ├─ llm/
│  │  ├─ client.py         Anthropic-Client-Factory, Timeout 45 s, Logging nach logs/llm/           GIANLUCA [B1]
│  │  ├─ prompts.py        SYSTEM_PROMPT (§7.4), CHAT_SYSTEM_PROMPT (§8.4), render_fact_sheet (§7.3) GIANLUCA [B1]
│  │  ├─ briefing.py       generate_briefing(fact_sheet) → Briefing | Retry                          GIANLUCA [B1]
│  │  ├─ validator.py      validate(briefing, fact_sheet) → (cleaned, issues) (§7.5)                GIANLUCA [B1]
│  │  ├─ fallback.py       template_briefing(fact_sheet) → Briefing (§7.5 Fallback)                 GIANLUCA [B1]
│  │  ├─ extract_notes.py  extract_intents(notes) → list[ClientIntent] (Structured Output)          GIANLUCA [B3]
│  │  └─ chat.py           answer(question, fact_sheet, briefing, history) → ChatResponse (§8)      GIANLUCA [B3]
│  ├─ service.py           Pipeline (§3.1), Timings, BriefingCache, Market-Budget 8 s               LEVIN    [C1, C3]
│  ├─ api.py               Routen ohne Logik: health, clients, facts, briefing, chat, upload, reset LEVIN    [C1, C2]
│  └─ demo.py              CLI-Durchstich (EXISTIERT): python -m uro.demo CASE-003 [--facts]           LEVIN    Testwerkzeug, bleibt
├─ eval/run_all.py         Batch über alle Klienten (EXISTIERT; --briefings, --file; C4 ergänzt --limit, --market)  LEVIN   [C4]
├─ scripts/spike_yfinance.py  Ticker-Trefferquote, News-Format, Dauer                                GIANLUCA [B2]
├─ tests/                  je Owner für sein Modul; fixtures/mini_clients.json + mini_reference.json JACOB legt Fixtures an [A1]
└─ frontend/               Vite + React + TS + Tailwind (Spec §9), src/types/api.ts spiegelt models  LEVIN    [C1–C3]
```

### 3.3 Finding-ID-Schema (D3)

| Präfix | Quelle | Beispiel |
|---|---|---|
| `profile` | Klientenprofil (immer genau eines) | `profile` |
| `perf-<pnr>`, `perf-gap-<pnr>`, `drv-<secid>` | Portfolio-Rendite je Portfolio (Levin, existiert), Datenlücke, Positions-Treiber | `perf-CASE-003-01`, `drv-9108` |
| `mkt-<secid>` | Sektor-/Marktvergleich zu einem Treiber | `mkt-9108` |
| `saa-<dim>-<slug>` | SAA-Abweichung | `saa-assetclass-shares` |
| `conc-single-<pnr>`, `conc-sector-<pnr>` (Levin, existieren), `conc-currency-<slug>`, `conc-region-<slug>` | Konzentration Titel / Branche je Portfolio; Währung / Region auf Klientenebene | `conc-single-CASE-003-01` |
| `viol-<slug(rulecode)>` | Suitability-Verstoß (gleicher RuleCode → ein Finding). Ersetzt Levins `viol-<i>` (Index ist über Läufe instabil) | `viol-cluster-risk-single-instrument` |
| `risk-breach-<pnr>` (Levin, existiert) | Volatilität vs. MaxVola | `risk-breach-CASE-011-01` |
| `esg-<slug>` | ESG | `esg-positions-below-min` |
| `liq-cash`, `liq-maturity-<secid>` | Liquidität, Fälligkeit | |
| `prop-<proposalid>`, `rej-proposals` | offene / abgelehnte Proposals | |
| `item-<slug>` | abgeleitete To-dos | `item-profile-review-due` |
| `note-<n>` | Notiz wörtlich (neueste = 1) | `note-1` |
| `intent-<slug>` | aus Notizen extrahierte, geprüfte Absicht | `intent-liquidity-need` |
| `news-<n>` | News-Artikel | `news-2` |
| `hv-<dim>-<slug>` | House-View-Abgleich | `hv-assetclass-bonds` |
| `gap-profile-<pnr>`, `gap-vola-<pnr>` (Levin, existieren), `gap-<slug>` | Datenlücke | `gap-profile-CASE-029-01`, `gap-no-saa-CASE-003-01` |
| `pos-<secid>` | **nur Chat-Kontext**: Positionszeile | `pos-9108` |

Slug: lowercase, `[^a-z0-9]+ → -`, max 40 Zeichen. IDs sind innerhalb eines FactSheets eindeutig (Kollision → Suffix `-2`).

---

## 4. Contract-Änderung

**Wer:** Jacob · **Wann:** Auftrag A0, **vor** dem parallelen Arbeiten (00:45) · **Commit:** `CONTRACT CHANGE: Findings-Typen, Severity/Statement-Erweiterung, Coverage, API-Modelle` · **Teamchat-Ankündigung Pflicht.**

Alle Änderungen sind **additiv** — bestehende Felder und Enum-Werte bleiben, damit Gianlucas und Levins Fake-Daten weiter validieren.

```python
# uro/models.py — NUR ERGÄNZUNGEN. Bestehendes bleibt unverändert.

from datetime import date, datetime
from typing import Literal

class FindingType(str, Enum):
    PERFORMANCE = "performance"                     # NEU: Gesamtrendite 1M/3M/12M/YTD (Spec §5.4 A)
    PERFORMANCE_DRIVER = "performance_driver"
    MARKET_COMPARISON = "market_comparison"         # NEU: isoliert / sektor- / marktweit (Spec §5.5)
    SAA_DEVIATION = "saa_deviation"
    CONCENTRATION = "concentration"
    SUITABILITY_VIOLATION = "suitability_violation"
    RISK_PROFILE = "risk_profile"                   # NEU: Portfolio-Vola vs RiskProfile.MaxVola — der Differenzierer
    ESG = "esg"                                     # NEU (Spec §5.8)
    PREFERENCE_CONFLICT = "preference_conflict"
    LIQUIDITY = "liquidity"
    OPEN_PROPOSAL = "open_proposal"
    REJECTED_PROPOSAL = "rejected_proposal"         # NEU: Kunde hat abgelehnt → Präferenz (data-notes §9)
    OPEN_ITEM = "open_item"                         # NEU: abgeleitete To-dos (Spec §5.13)
    CLIENT_PROFILE = "client_profile"               # NEU: genau ein Finding "profile", immer im LLM-Kontext
    CLIENT_NOTE = "client_note"                     # NEU: Notiz wörtlich, note-N (Spec §5.14)
    HOUSE_VIEW = "house_view"
    MARKET_EVENT = "market_event"
    DATA_GAP = "data_gap"


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    OPPORTUNITY = "opportunity"                     # NEU: Chance (Cash anlegen, Fälligkeit, House View aligned) → grün


class Finding(BaseModel):
    # … bestehende Felder …
    related_ids: list[str] = Field(default_factory=list, description="Andere Finding-IDs, die dasselbe Thema betreffen")
    boost_reasons: list[str] = Field(default_factory=list, description="Warum client_relevance/recency > 1 — für das Popover im UI")
    rank: int | None = Field(default=None, description="1 = wichtigstes Finding; vom Scoring gesetzt")
    # Regel: Jede Zahl in `numbers` steht FORMATIERT (analytics/format.py) auch in `title` oder `detail`.
    # Das LLM kopiert die Zahl wörtlich; der Validator prüft String UND Zahl.


class PositionFact(BaseModel):
    # … bestehende Felder …
    security_type: str | None = None                # SecurityTypeName
    industry: str | None = None                     # SAA_IndustryName (None bei Anleihen/Fonds)
    country_group: str | None = None                # SAA_CountryGroupName
    currency_group: str | None = None               # SAA_CurrencyGroupName
    volatility: float | None = None                 # Security.Volatility (Bruch)
    prc: int | None = None
    sustainability_score: float | None = None       # 0–10
    maturity_date: date | None = None               # Anleihen; Jahr 2299 = perpetual → None
    is_fund_unbundlable: bool = False
    ticker: str | None = None                       # von enrich/market gesetzt, None wenn nicht auflösbar
    portfolio_nr: str | None = None
    client_weight_pct: float | None = None          # Gewicht am Gesamtvermögen des Klienten (0–100); weight_pct bleibt Levins Portfolio-Gewicht


class PortfolioFact(BaseModel):
    # … bestehende Felder …
    has_real_saa: bool = True                       # False bei "No strategy" (Min 0 / Target 0 / Max 1)
    max_volatility: float | None = None             # RiskProfile.MaxVola des Klienten, zur Anzeige neben volatility


class FactSheet(BaseModel):
    # … bestehende Felder …
    age: int | None = None                          # aus Birthday abgeleitet; Birthday selbst wird gestrippt
    risk_level: int | None = None                   # RiskProfile.RiskLevel (3–7); <= 4 gilt als konservativ
    history_as_of: date | None = None               # letztes PerformanceHistory-Datum → Renditen
    data_as_of: date | None = None                  # max. Datum aller Klientenfelder → Alter/offen seit
    exposures: dict[str, list[dict]] = Field(default_factory=dict, description="industry/currency/region → Top-10 [{name, weight_pct, direct_pct, via_funds_pct}]")
    coverage: dict[str, str] = Field(default_factory=dict, description="detector → 'ok' | 'no_data' | 'error: <Name>'")
    warnings: list[str] = Field(default_factory=list, description="z.B. 'Market data unavailable'")
    note_flags: list[str] = Field(default_factory=list, description="Keyword-Flags aus Notizen: risk_averse, liquidity_need, retirement, esg_interest — nur für Boosts")

    def by_id(self) -> dict[str, "Finding"]:
        return {f.id: f for f in self.findings}


class StatementType(str, Enum):
    FACT = "fact"
    MARKET = "market"
    HOUSE_VIEW = "house_view"
    RECOMMENDATION = "recommendation"
    RISK = "risk"
    ASSESSMENT = "assessment"                       # NEU: Interpretation/Schlussfolgerung — kursiv, Label "ASSESSMENT"


class ActionKind(str, Enum):                         # NEU
    RESOLVE_VIOLATION = "resolve_violation"
    REBALANCE = "rebalance"
    REDUCE_CONCENTRATION = "reduce_concentration"
    REINVEST_LIQUIDITY = "reinvest_liquidity"
    FOLLOW_UP_PROPOSAL = "follow_up_proposal"
    BUY = "buy"
    SELL = "sell"
    SWITCH = "switch"
    CLIENT_FOLLOW_UP = "client_follow_up"
    UPDATE_PROFILE = "update_profile"


class NextBestAction(BaseModel):
    # … bestehende Felder …
    priority: int = Field(default=1, ge=1, le=3)
    kind: ActionKind = ActionKind.CLIENT_FOLLOW_UP


class BriefingResult(BaseModel):
    # … bestehende Felder …
    display_name: str = ""                          # UI-Pfad, nicht LLM-Pfad
    mode: Literal["ai", "ai_retry", "fallback"] = "ai"
    timings_ms: dict[str, int] = Field(default_factory=dict)   # load, analytics, market, llm, validate, total
    generated_at: datetime = Field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# Markt-Snapshot — Vertrag zwischen enrich/ (Gianluca, erzeugt) und analytics/ (Jacob, konsumiert).
# Liegt in models.py, damit analytics/ nichts aus enrich/ importieren muss (Schichtenregel §3.1).
# ---------------------------------------------------------------------------

class PriceSeries(BaseModel):
    ticker: str
    dates: list[date]
    closes: list[float]

    def return_pct(self) -> float | None:            # (last / first − 1) × 100, None bei < 2 Punkten
        if len(self.closes) < 2 or not self.closes[0]:
            return None
        return (self.closes[-1] / self.closes[0] - 1) * 100


class MarketSnapshot(BaseModel):
    as_of: datetime
    source: Literal["live", "cache", "unavailable"] = "unavailable"
    tickers: dict[int, str] = Field(default_factory=dict, description="security_id → Yahoo-Ticker (nur aufgelöste)")
    prices: dict[str, PriceSeries] = Field(default_factory=dict, description="Ticker (Positionen UND Proxies) → 3-Monats-Schlusskurse")
    news: list[Finding] = Field(default_factory=list, description="news-1..6, Typ MARKET_EVENT")
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# API-Modelle (UI-Pfad; enthalten Klarnamen, gehen NIE ins LLM)
# ---------------------------------------------------------------------------

class ClientSummary(BaseModel):
    client_ref: str
    display_name: str
    is_company: bool = False
    risk_profile: str | None = None
    esg_profile: str | None = None
    aum_chf: float = 0.0
    liquidity_pct: float = 0.0                      # 0–100
    violation_count: int = 0
    error_count: int = 0
    open_proposal_count: int = 0
    portfolio_count: int = 1
    is_new: bool = False                            # via Upload hinzugefügt


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)


class ChatResponse(BaseModel):
    answer: str
    sources: list[str] = Field(default_factory=list)   # per Regex \[(\w+-[\w-]+|profile)\] extrahiert


class UploadResult(BaseModel):
    added_client_refs: list[str] = Field(default_factory=list)
    updated_client_refs: list[str] = Field(default_factory=list)
    reference_merged: bool = False
    errors: list[str] = Field(default_factory=list)
```

**Frontend-Spiegel:** `frontend/src/types/api.ts` wird im selben Commit angelegt/angepasst (Levin liefert die Datei, Jacob committet beides zusammen; bis dahin arbeitet Levin gegen `fixtures/sample_briefing.json`, das Gianluca aus dem Fake-FactSheet erzeugt).

---

## 5. Arbeitspakete

Jeder Auftrag ist so geschrieben, dass eine **frische Claude-Code-Session** ihn mit `CLAUDE.md` + diesem Abschnitt + dem Spec-Verweis ausführen kann. **Interfaces** sind verbindlich (Nachbar-Aufträge programmieren dagegen). Zeitfenster siehe §6.

### Phase 0 — Fundament (00:30–01:00, Jacob; die anderen ziehen um 01:00)

#### Auftrag A0 — Repo-Hygiene, Config, Contract-Änderung
**Owner:** Jacob · **Files:** `pyproject.toml`, `.gitignore`, `Makefile`, `uro/config.py`, `uro/models.py`, `CLAUDE.md` · **Zeit:** 01:00–01:30
**Spec:** §13 (Setup), §16 (Regeln), Anhang A

- [ ] `uv add yfinance pandas python-multipart pydantic-settings && uv add --dev ruff && uv sync` — Verify: `uv run python -c "import yfinance, pandas, fastapi, anthropic; print('ok')"` und danach `uv run python -m eval.run_all` weiterhin 47/47. (Python bleibt 3.13, D16.)
- [ ] `.gitignore` ergänzen: `logs/`, `data/cache/`, `frontend/node_modules/`
- [ ] `Makefile` anlegen:
  ```makefile
  dev-backend:  ; uv run uvicorn uro.api:app --reload --port 8000
  dev-frontend: ; cd frontend && npm run dev
  test:         ; uv run pytest -q
  lint:         ; uv run ruff check uro tests eval && uv run ruff format --check uro tests eval
  smoke:        ; uv run python -m eval.run_all
  eval-llm:     ; uv run python -m eval.run_all --briefings --limit 5
  demo:         ; uv run python -m uro.demo CASE-003
  ```
- [ ] `uro/config.py` anlegen — **alle** Schwellen an einer Stelle:
  ```python
  from pydantic_settings import BaseSettings

  class Settings(BaseSettings):
      anthropic_api_key: str | None = None
      llm_model: str = "claude-opus-5"              # Env LLM_MODEL=claude-sonnet-5 als Latenz-Notfall (D6)
      llm_effort: str = "low"
      llm_timeout_s: float = 45.0
      llm_max_tokens: int = 4000
      data_dir: str = "data"
      market_budget_s: float = 8.0
      market_cache_enabled: bool = True             # D11
      model_config = {"env_file": ".env", "extra": "ignore"}

  # AnalysisConfig: Schwellen aus Spec §5 + data-notes
  TOP_N_FOR_LLM = 10
  MAX_PER_TYPE = 3
  CONCENTRATION = {"security": (0.10, 0.15), "industry": (0.20, 0.30), "currency": (0.30, 0.50), "region": (0.40, 0.60)}  # (threshold, magnitude_ref)
  SAA_OTHER_DIM_THRESHOLD_PP = 10.0
  VOLA_ERROR_FACTOR = 1.2
  CONSERVATIVE_RISK_LEVEL_MAX = 4
  OPEN_PROPOSAL_STATUSES = {"Entwurf"}; EXECUTED_IF_SUBMITTED = {"Final"}; REJECTED_STATUSES = {"Abgelehnt"}
  PROFILE_REVIEW_MONTHS = 24; PROPOSAL_FOLLOW_UP_DAYS = 60; MATURITY_WINDOW_DAYS = 180
  NOTE_KEYWORDS = {"risk_averse": ["nervous", "worried", "concern", "cautious", "safety", "capital preservation", "angst", "sorge", "prudent", "inquiet"],
                   "risk_tolerant": ["unconcerned", "patient", "long view", "long-term", "comfortable with risk"],
                   "liquidity_need": ["liquid", "cash", "withdraw", "tax payment", "property", "house", "apartment", "purchase", "haus", "immobil", "achat"],
                   "retirement": ["retire", "pension", "rente", "retraite"], "esg_interest": ["esg", "sustainab", "fossil", "climate", "nachhaltig"]}
  SEVERITY_WEIGHT = {("suitability_violation", "error"): 1.00, ("risk_profile", "error"): 1.00, ("saa_deviation", "warning"): 0.80,
                     ("suitability_violation", "warning"): 0.75, ("risk_profile", "warning"): 0.75, ("performance", "warning"): 0.70,
                     ("performance_driver", "warning"): 0.70, ("concentration", "warning"): 0.70, ("esg", "warning"): 0.65,
                     ("market_comparison", "info"): 0.60, ("house_view", "warning"): 0.60, ("preference_conflict", "warning"): 0.70,
                     ("liquidity", "warning"): 0.60, ("open_proposal", "info"): 0.55, ("open_item", "info"): 0.50,
                     ("liquidity", "opportunity"): 0.45, ("data_gap", "info"): 0.45, ("house_view", "opportunity"): 0.30,
                     ("rejected_proposal", "info"): 0.25, ("client_note", "info"): 0.20, ("client_profile", "info"): 0.50}
  SEVERITY_DEFAULT = 0.40
  LOOKTHROUGH_INDUSTRY_MAP = {"Raw materials": "Materials", "Communication Services": "Telecommunication Services"}
  LOOKTHROUGH_ASSETCLASS_PREFIX = {"Equities": "Shares", "Bonds": "Bonds", "Real estate": "Real estate", "Liquidity": "Liquidity"}  # Rest → "Specialties andCommodities"
  MARKET_PROXIES = {"CHF": "^SSMI", "USD": "^GSPC", "EUR": "^STOXX50E", "GBP": "^FTSE", "default": "URTH"}
  ```
- [ ] Contract-Änderung aus §4 in `models.py` einbauen; Verify: `uv run python -c "from uro.models import *; print(FactSheet(client_ref='X').model_dump_json()[:80])"`
- [ ] `CLAUDE.md` ergänzen (nicht umschreiben): unter §1 eine Zeile „**Umsetzungsplan:** `docs/superpowers/plans/2026-09-19-uro-briefing-strategy.md` — Quellenhierarchie in dessen §0"; unter §4 den Hinweis „Verifizierte Feldnamen: `docs/data-notes.md` (dort steht auch, wo DATA.md nicht stimmt)"; unter §7 Modellaufruf auf Structured Outputs (`messages.parse` / `output_config.format`) präzisieren; unter §12 Punkt 6: „Finding-IDs nach Schema §3.3 des Plans".
- [ ] Commit 1: `Setup: Deps (yfinance, pandas, multipart, settings, ruff), Makefile, config.py` · Commit 2: `CONTRACT CHANGE: Findings-Typen, Severity/Statement-Erweiterung, Coverage, API-Modelle` · Commit 3: `Doku: Strategieplan, data-notes, Spec ins Repo; CLAUDE.md verweist darauf` · `git push`

### Phase 1 — Durchstich härten (01:00–02:30, alle drei parallel; hartes Ende 02:30)

**Stand 00:55:** Der Engine-Durchstich existiert bereits (Levin, `b1e5d1c`): `uv run python -m uro.demo CASE-003 --facts` zeigt 47/47 Fact Sheets. Der **LLM-Teil ist noch nie gelaufen** (kein Key). Die drei Aufträge dieser Phase bauen deshalb nicht neu, sondern **härten und schließen Lücken**, jeder in seinem Modul.

**Ziel um 02:30:** `make demo` liefert für CASE-003 ein echtes, validiertes Claude-Briefing mit `mode` und Timing; `curl -X POST localhost:8000/api/clients/CASE-003/briefing` liefert dasselbe als JSON. Frontend ist **nicht** Teil des 02:30-Ziels (ab 08:00, C2).

#### Auftrag A1 (revidiert) — Durchstich härten: ReferenceIndex, Positionen, Coverage, Profil/Notizen, Fixtures
**Owner:** Jacob · **Zeit:** 01:30–02:30 · **Files:** `uro/ingest.py`, `uro/store.py` (neu), `uro/analytics/{__init__,format,positions,performance,suitability,notes}.py` (`format`, `positions` neu), `tests/fixtures/mini_clients.json`, `tests/fixtures/mini_reference.json`, `tests/test_ingest.py`, `tests/test_fact_sheet.py`
**Spec:** §3.1, §5.1–5.4 A, §5.7, §5.14, §14.1 · **Daten:** data-notes §2, §4, §7, §8, §11, §12

**Was Levin schon hat — nicht neu schreiben, Signaturen behalten:** `ingest.get/lst/load_clients/load_reference/strip_pii/display_name/index_by/find_client`; `analytics.build_fact_sheet(client, reference)` (Positionen je Portfolio, `last_contact`); `performance.compute_returns/performance_findings(pnr, returns, aum)`; `concentration.concentration_findings(pnr, positions, aum)` (Einzeltitel ≥ 20 %, Sektor ≥ 35 %); `suitability.violation_findings(client, aum)` und `risk_profile_findings(client, portfolio, profile, aum)` (Vola vs MaxVola, DATA_GAP bei fehlendem Profil/Vola); `scoring.score_findings(findings, aum)`. **Läuft 47/47, < 1 ms.**

**Lücken, die A1 schließt (Reihenfolge = Priorität):**
1. **`ReferenceIndex`** in `ingest.py`: `securities_by_id`, `securities_by_isin` (Liste; CHF-Tranche zuerst), `saa_by_id`, `rules_by_code`, `risk_profiles_by_id`, `esg_profiles_by_id`, `unbundling_by_fund_id` (**`Weight/100` genau hier, sonst nirgends**), `recommended_security_ids`. `build_fact_sheet(client, reference)` behält seine Signatur und baut den Index intern; der `DataStore` (Punkt 5) cached ihn.
2. **Upload-Robustheit im Loader:** `load_clients` akzeptiert zusätzlich `{"clients": [...]}` / `{"Clients": [...]}` und ein einzelnes Klient-Objekt (Spec §10). `strip_pii` berechnet **vor** dem Entfernen `_Age` (Jahre zu `data_as_of`) aus `Birthday`, analog zu `_DisplayName`.
3. **`analytics/format.py`** (`pct`, `pp`, `chf`, `date_str`) und Umstellung der bestehenden Finding-Texte darauf. Texte gemäß Sprachentscheidung §10.1 (Default Englisch). Regel: jede Zahl aus `numbers` steht formatiert in `title`/`detail`.
4. **`analytics/positions.py::build_positions`:** Cash aus `AccountPositions` als synthetische Position (`saa_asset_class="Liquidity"`, Krypto-Konten `"Crypto"`); alle neuen `PositionFact`-Felder aus §4 füllen (`security_type`, `industry` = `SAA_IndustryName`, `country_group`, `currency_group`, `volatility`, `prc`, `sustainability_score`, `maturity_date` mit Jahr ≥ 2200 → `None`, `is_fund_unbundlable`, `portfolio_nr`, `client_weight_pct`). `weight_pct` bleibt Levins Portfolio-Gewicht.
5. **`store.py::DataStore`** (Interfaces unten) — der eine Ort, der Dateien liest; `list_clients()` liefert `ClientSummary` mit Klarnamen aus `_DisplayName`, `get_client()` die PII-freie Kopie.
6. **`coverage` + Zeitanker in `build_fact_sheet`:** jeden Detektor-Aufruf in `try/except` → `fs.coverage[name] = "ok" | "no_data" | "error: <ExcName>"`; `history_as_of` (max `PerformanceHistory.Date`), `data_as_of` (max aller Datumsfelder), `risk_level`, `age`, `note_flags` füllen; `open_proposals` = Entwurf **oder** Final ohne `TransactionsSubmittedDateUTC` (data-notes §9) statt `len(Proposals)`.
7. **`suitability.py` schärfen:** IDs `viol-<slug(RuleCode)>` statt `viol-<i>`; `IndividualRuleOverrides` filtern; gleicher RuleCode → ein Finding mit Titel-Liste; `portfolio_nr` über `PortfolioId → PortfolioNr` auflösen; `ViolationPath` nur bei Vola-/Gewichtsregeln als „actual vs limit" (data-notes §8). `risk_profile_findings`: `type=FindingType.RISK_PROFILE` (aus A0), ERROR ab Faktor `VOLA_ERROR_FACTOR`, sonst WARNING; ID `risk-breach-<pnr>` bleibt.
8. **`notes.py`:** `note_findings` (note-1..5 wörtlich, max 600 Zeichen, `CLIENT_NOTE`/INFO) und `note_flags` (`config.NOTE_KEYWORDS`, inkl. Gegenflag `risk_tolerant`). **Profil-Finding** `profile` (`CLIENT_PROFILE`/INFO, PII-frei): `"Client CASE-003, 58, private client, risk profile 'Anlageprofil 5' (max volatility 12.0%), ESG preference 'No', reporting currency CHF, AuM CHF 141,000, liquidity 3.0%. Interest tags: —."`
9. Levins Konzentrationsschwellen (`SINGLE_WARN` 20, `SINGLE_ERROR` 40, `SECTOR_WARN` 35) nach `config.py` ziehen, Werte vorerst behalten; die Spec-Schwellen (10 % Titel, 20 % Branche mit Look-through, Währung, Region) kommen in **A2**.

**Interfaces (verbindlich für Nachbarn):**
```python
# ingest.py — bestehend + neu
def load_clients(path) -> list[dict]                      # Array | {"clients": [...]} | einzelnes Objekt; strip_pii angewandt
class ReferenceIndex:
    def __init__(self, reference: dict) -> None
    securities_by_id: dict[int, dict]; securities_by_isin: dict[str, list[dict]]; saa_by_id: dict[int, dict]
    rules_by_code: dict[str, dict]; risk_profiles_by_id: dict[int, dict]; esg_profiles_by_id: dict[int, dict]
    unbundling_by_fund_id: dict[int, list[dict]]          # Weight bereits 0–1
    recommended_security_ids: set[int]
# store.py — neu
class DataStore:
    def __init__(self, data_dir: str) -> None             # lädt clients.json + reference.json, baut ReferenceIndex
    def list_clients(self) -> list[ClientSummary]
    def get_client(self, client_ref: str) -> dict | None  # PII-freie Kopie (enthält _DisplayName, _Age)
    def display_name_for(self, client_ref: str) -> str
    def merge(self, payload: object, filename: str) -> UploadResult   # A4; bis dahin NotImplementedError → API 501
    def reset(self) -> None
    reference: dict; ref: ReferenceIndex
# analytics/__init__.py — Signatur bleibt
def build_fact_sheet(client: dict, reference: dict) -> FactSheet   # PURE; Markt/News/House View hängt service.enrich_fact_sheet an (C1)
# analytics/format.py — neu
def pct(x: float, signed: bool = False) -> str            # 0.042 → "4.2%" / "+4.2%"   (Eingabe Bruch 0–1)
def pp(x_pp: float) -> str                                # 16.0 → "+16.0 pp"
def chf(x: float, currency: str = "CHF") -> str           # 160000 → "CHF 160,000" (ab 10'000 auf 1'000 gerundet)
def date_str(d: date) -> str                              # "12 Jun 2026"
# analytics/positions.py — neu
def build_positions(client: dict, ref: ReferenceIndex) -> list[PositionFact]
# analytics/notes.py — neu
def note_findings(client: dict, fs: FactSheet) -> list[Finding]
def note_flags(client: dict) -> list[str]
```
Hinweis: `scoring.score_findings(findings, total_aum_chf)` bleibt in A1 unangetastet; in **A2** wird die Signatur zu `score_findings(findings, fs: FactSheet)` (braucht `risk_level`, `note_flags`), eigenes Modul, keine Contract-Änderung.

- [ ] Fixtures handbauen: `mini_clients.json` mit 3 Klienten — (a) Vola-Bruch + 2 Positionen + Notiz „retire", (b) echte SAA + Fonds mit Look-through + 2 Verstöße + offenes und abgelehntes Proposal + ESG Yes, (c) fast leer: `null`-Felder, 0 Positionen, 100 % Cash, kein Risikoprofil. `mini_reference.json` mit passenden Securities/SAA/RiskProfiles/EsgProfiles/FundUnbundling (Weight 0–100!).
- [ ] Tests zuerst: `test_ingest.py` (`null`→`[]`, `Weight/100` genau einmal, `strip_pii` entfernt Keys und setzt `_Age`/`_DisplayName`, `load_clients` mit allen drei Formen) · `test_fact_sheet.py` (alle 3 Fixtures ohne Exception; Klient (c) liefert `gap-profile-*` und `coverage` ohne `error`; Klient (a) liefert `risk-breach-*` mit `type == risk_profile`).
- [ ] Punkte 1–9 umsetzen, nach jedem Punkt `make smoke` (Levins `run_all` muss 47/47 bleiben) und `uv run python -m uro.demo CASE-003 --facts`.
- [ ] Verify: `make test && make lint && make smoke` · Commit: `Engine gehärtet: ReferenceIndex, Cash-Positionen, Coverage, Profil- und Notiz-Findings, Fixtures; 47/47 unverändert`

#### Auftrag B1 (revidiert) — LLM-Call härten: Key, `effort`, Timeout/Retry, Fallback, Prompt, Rendering
**Owner:** Gianluca · **Zeit:** 01:00–02:30 · **Files:** `uro/llm/{client,prompts,briefing,validator,fallback}.py` (`client`, `fallback` neu), `tests/fixtures/sample_briefing.json`, `tests/test_validator.py`, `tests/test_fallback.py`
**Spec:** §7.1–7.6 (Prompt §7.4, IDs nach Schema §3.3), §16.4 · **API-Referenz:** `claude-api`-Skill (Structured Outputs, Prompt Caching, Effort)

**Was Levin schon hat:** `prompts.SYSTEM_PROMPT` (deutsch, Grounding-Regel, 3 Abschnitte, 5 Statement-Typen), `render_fact_sheet` (Profil, Portfolios mit Top-5-Positionen, Top-6-Findings mit `numbers`, Intents), `briefing.generate_briefing` via `messages.parse(output_format=Briefing)` mit `cache_control` (aber `EFFORT=None`, `max_tokens=16000`, kein Timeout, kein Retry), `validator.validate` (IDs, Zahlen gegen `all_numbers()` ∪ alle Zahlen im Rendering, Wortzahl 120–260, entfernt Aussagen). **Noch nie gegen die API gelaufen.**

**Schritte:**
1. **Sofort, blockiert alles andere:** `ANTHROPIC_API_KEY` in `.env` (bei allen dreien). `set -a && source .env && set +a && uv run python -m uro.demo CASE-003` → erster echter Call. Sekunden, Wortzahl, Validator-Issues in den Teamchat.
2. `llm/client.py`: `get_client()` → `anthropic.Anthropic(timeout=settings.llm_timeout_s, max_retries=1)`; `LLMUnavailable` ohne Key; `log_llm()` schreibt Prompt + Antwort nach `logs/llm/<ts>_<ref>_<kind>.json`.
3. `briefing.py`: `output_config={"effort": settings.llm_effort}` (Default `low` — Opus 5 denkt sonst adaptiv, das kostet Sekunden), `max_tokens=settings.llm_max_tokens` (4000 reichen für ≤ 260 Wörter JSON), Modell aus `config.py`; Rückgabe `(Briefing, mode)`; **ein** Retry mit Fehlerliste als zweiter User-Turn; API-/Parse-Fehler → `LLMUnavailable`/`LLMInvalid`.
4. `fallback.py::template_briefing(fs)` deterministisch nach Spec §7.5 — damit `service.py` und Frontend auch ohne Key oder Netz ein Briefing bekommen.
5. `prompts.py`: System-Prompt auf Spec §7.4 heben (Sprache gemäß §10.1, Default Englisch; Typ `assessment`; `next_best_actions` mit `priority`/`kind`; Kauf-/Switch-Vorschläge nur aus Findings). `render_fact_sheet` ergänzen: Rang + Score je Finding (`[risk-breach-CASE-003-01] (rank 1, score 2.85, risk_profile/error)`), **Notizen wörtlich** (`note-*`), `coverage`/`warnings` als Block „DATA GAPS", `data_as_of`/`history_as_of`, `TOP_N_FOR_LLM` aus `config.py`. Stabiler Teil (System) zuerst, volatiler danach — Cache.
6. `validator.py` behalten; ergänzen: Wertpapiernamen in `buy/switch`-Actions müssen in zitierten Findings vorkommen; leere `next_best_actions` → Issue `no_actions` (löst in `briefing.py` den Retry aus).
7. `tests/fixtures/sample_briefing.json` aus einem echten Lauf für CASE-003 speichern (Levins Frontend-Fixture ab 08:00).

**Interfaces (verbindlich für `service.py`):**
```python
# llm/client.py — neu
class LLMUnavailable(Exception): ...
class LLMInvalid(Exception): ...
def get_client() -> anthropic.Anthropic
def log_llm(kind: str, client_ref: str, request: dict, response: object) -> None
# llm/prompts.py — bestehend, erweitert
SYSTEM_PROMPT: str; CHAT_SYSTEM_PROMPT: str
def render_fact_sheet(fs: FactSheet, max_findings: int = TOP_N_FOR_LLM) -> str
# llm/briefing.py — Rückgabe erweitert
def generate_briefing(fs: FactSheet, client: anthropic.Anthropic | None = None) -> tuple[Briefing, str]   # mode ∈ {"ai","ai_retry"}
# llm/validator.py — bestehend
def validate(briefing: Briefing, fs: FactSheet) -> tuple[Briefing, list[ValidationIssue]]
# llm/fallback.py — neu
def template_briefing(fs: FactSheet) -> Briefing
```

- [ ] Aufrufmuster (aus dem `claude-api`-Skill, Stand 2026; Levins Call entspricht dem bereits bis auf `effort`, Timeout und Retry): **Structured Output + Caching**, kein Prefill, kein forced `tool_choice`:
  ```python
  client = get_client()
  response = client.messages.parse(
      model=settings.llm_model,                       # "claude-opus-5"
      max_tokens=settings.llm_max_tokens,
      system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
      messages=[{"role": "user", "content": render_fact_sheet(fs)}],
      output_format=Briefing,                         # Pydantic-Modell → response.parsed_output
      output_config={"effort": settings.llm_effort},
  )
  briefing: Briefing = response.parsed_output
  ```
  Retry: bei `LLMInvalid` oder ≥ 2 `unsupported_number`-Issues **ein** zweiter Call mit angehängter User-Nachricht `"Your previous output had these problems: …. Fix them and resubmit."` → `mode = "ai_retry"`. Danach `template_briefing`.
- [ ] Validator (Spec §7.5, Tabelle): (1) jede `finding_ids`-Referenz existiert in `fs.by_id()` — sonst Statement entfernen, Issue `unknown_finding_id`; (2) jede Zahl im Text (Regex `-?\d[\d,']*\.?\d*\s?(%|pp)?`) kommt als String in `title`/`detail` **oder** numerisch (±0.05) in `numbers` der zitierten Findings vor — sonst Issue `unsupported_number`, Statement bleibt aber mit Markierung; Jahreszahlen und Prioritäten 1–3 ausgenommen; (3) Wertpapiernamen in `buy/switch`-Actions kommen in zitierten Findings vor; (4) `word_count()` > 240 → Issue `too_long` (nur Warnung); (5) leere `next_best_actions` → Issue `no_actions` → Retry.
- [ ] Tests: erfundene ID → entfernt; erfundene Zahl → Issue; korrekte Zahl anders formatiert (`4.2%` vs `4.2 %`) → ok; Fallback aus fast leerem FactSheet liefert gültiges `Briefing` mit ≥ 1 Action.
- [ ] Verify: `make test && make lint`; `make demo` < 12 s (Timing in den Teamchat). Commit: `LLM-Call gehärtet: effort low, Timeout, Retry, Template-Fallback, Prompt nach Spec; sample_briefing.json`

#### Auftrag C1 — API und Pipeline (Frontend-Skelett nur, wenn Zeit bleibt)
**Owner:** Levin · **Zeit:** 01:30–02:30 · **Files:** `uro/service.py` (neu), `uro/api.py` (hat nur `/health`), `tests/test_api.py`; optional `frontend/**`, `frontend/src/types/api.ts`
**Voraussetzung:** A0 gepusht (Contract, `config.py`); bis A1 fertig ist, `DataStore` durch `load_clients`/`load_reference` + `find_client` aus `ingest.py` ersetzen und danach umstellen.
**Spec:** §4.2 (Pipeline), §9.2/9.5 (Layout, Technik), §10 (API-Vertrag; Pfade siehe unten), §11 · **UI-Vorgaben:** `PITCH.md` §11 (Screenshots)

**Interfaces:**
```python
# service.py
class BriefingService:
    def __init__(self, store: DataStore, settings: Settings) -> None
    def facts(self, client_ref: str) -> FactSheet                    # build_fact_sheet ohne Markt (< 1 s); cached bis reset/upload
    def briefing(self, client_ref: str) -> BriefingResult            # Pipeline §3.1 inkl. Markt (Budget 8 s), LLM, Validator, Fallback; Timings; BriefingCache[ref]
    def chat(self, client_ref: str, req: ChatRequest) -> ChatResponse # Auftrag C3 verdrahtet llm.chat.answer

def enrich_fact_sheet(fs: FactSheet, market: MarketSnapshot | None, house_view: dict | None, ref: ReferenceIndex) -> FactSheet
    # Hängt an fs.findings an: market.news (B2), house_view_findings(fs, house_view, ref) (B2),
    # driver_findings(fs, market) + market_comparison_findings(fs, market) (A3, ab 11:00; bis dahin übersprungen),
    # übernimmt market.warnings/source in fs.warnings, ruft score_findings(fs.findings, fs) erneut. Jeder Schritt in try/except → coverage.
# api.py — Pfade (endgültig):
GET  /api/health                      → {"status","clients","llm_configured"}
GET  /api/clients?q=                  → list[ClientSummary]
GET  /api/clients/{ref}               → {"summary": ClientSummary, "fact_sheet": FactSheet}   (Detailseite: Positionen, Allocation, Notizen aus dem FactSheet)
GET  /api/clients/{ref}/facts         → FactSheet
POST /api/clients/{ref}/briefing      → BriefingResult   (immer 200, außer 404 unbekannter Klient)
POST /api/clients/{ref}/chat          → ChatResponse
POST /api/upload  (multipart "files") → UploadResult
POST /api/reset                       → {"status":"ok"}
```
- [ ] `service.py`: Markt-Schritt in `ThreadPoolExecutor`, `concurrent.futures.wait(timeout=settings.market_budget_s)`; LLM-Ausnahmen → `template_briefing`, `mode="fallback"`, `warnings.append("AI unavailable — rule-based briefing")`. Bis B2 fertig ist: `market=None`.
- [ ] `tests/test_api.py`: `TestClient`; `generate_briefing` per Monkeypatch auf Exception → `/briefing` liefert 200 mit `mode == "fallback"`; unbekannter Klient → 404.
- [ ] **Optional heute Nacht, sonst C2 ab 08:00:** Frontend: `npm create vite@latest frontend -- --template react-ts`, Tailwind, `react-router-dom`, `lucide-react`, `recharts`; Vite-Proxy `/api → http://localhost:8000`; `VITE_USE_FIXTURES=true` lädt `src/fixtures/sample_briefing.json`. Seiten: `ClientListPage` (Tabelle: Name, Ref, Risikoprofil, AuM, Verstöße, NEW-Badge, Suche), `ClientDetailPage` (Header mit **Generate Briefing** in der Aktionsleiste rechts, Tastenkürzel `G`; Tabs Overview/Positions/Proposals als Rohdaten-Ansicht), `BriefingPanel` rechts (erst mal: Headline + 3 Sections + Actions als Liste, Source-Chips als Text).
- [ ] Verify: `npm run typecheck && npm run build`; im Browser: Liste → Detail → Generate → Briefing erscheint (Fixture oder echt). Commit: `API, Pipeline mit Fallback, Frontend-Skelett mit Generate-Briefing-Flow`

**Meilenstein 02:30 (alle):** `make demo` → echtes Briefing im Terminal mit Validator-Ergebnis und Sekunden; `make dev-backend` + `curl -X POST localhost:8000/api/clients/CASE-003/briefing | head -c 600`. Terminal-Screenshot in den Teamchat. Push. **Dann schlafen.** Was fehlt, ist erster Punkt um 08:00.

### Phase 2 — Substanz (08:00–11:00)

#### Auftrag A2 — Restliche Detektoren, Look-through, Scoring, Tests
**Owner:** Jacob · **Files:** `analytics/{saa,concentration,esg,liquidity,proposals,open_items,scoring}.py`, `tests/test_detectors_*.py`, `tests/test_scoring.py`
**Spec:** §5.6, §5.8–5.13, §5.16 · **Daten:** data-notes §3, §5, §6, §7, §9, §15

**Interfaces:**
```python
def build_allocation(fs: FactSheet, client: dict, ref: ReferenceIndex) -> list[AllocationLine]   # je Portfolio, 4 Dimensionen, inkl. Look-through; füllt PortfolioFact.allocation
def saa_findings(fs: FactSheet) -> list[Finding]            # nur has_real_saa; AssetClass: < Min / > Max; andere Dims: |dev| >= SAA_OTHER_DIM_THRESHOLD_PP; sonst INFO "no SAA assigned"
def concentration_findings(fs: FactSheet, ref: ReferenceIndex) -> list[Finding]   # 4 Ebenen aus config.CONCENTRATION; füllt fs.exposures (Top 10 je Ebene)
def esg_findings(fs: FactSheet, client: dict, ref: ReferenceIndex) -> list[Finding]
def liquidity_findings(fs: FactSheet) -> list[Finding]      # liq-cash (OPPORTUNITY wenn cash_pct > Ziel+5pp bzw. > 10%), liq-maturity-*, Cash-only-Fall
def proposal_findings(fs: FactSheet, client: dict, ref: ReferenceIndex) -> list[Finding]   # prop-<id> offen (Alter ab data_as_of, Reason, Top-3 Positionen via Isin), rej-proposals (Anzahl, letzter Reason)
def open_item_findings(fs: FactSheet, client: dict) -> list[Finding]
def score_findings(findings: list[Finding], fs: FactSheet) -> list[Finding]   # setzt score, rank, boost_reasons; sortiert; Diversität MAX_PER_TYPE in den Top TOP_N_FOR_LLM
```
- [ ] Pro Detektor: Test Normalfall (erwarteter Text mit Zahl) + Test „fehlende Daten → [] oder DATA_GAP, keine Exception".
- [ ] `score_findings`: `score = SEVERITY_WEIGHT[(type, severity)] × max(0.2, materiality) × relevance × recency`; Boost-Regeln aus Spec §5.16 Schritt 3 mit `fs.risk_level <= 4 or "risk_averse" in fs.note_flags` (und **nicht** wenn `"risk_tolerant"` gesetzt), Cap 1.6; `related_ids` über gemeinsame `security_ids`.
- [ ] `eval/run_all.py` (falls C4 noch nicht da) minimal: Schleife über alle Klienten, Tabelle `ref | #findings | top-3 IDs | coverage-Fehler`, Exit 1 bei `error:` in coverage.
- [ ] Verify: `make test && make lint && make smoke` (47/47 ohne `error`). Commit: `SAA mit Look-through, Konzentration, ESG, Liquidität, Proposals, Open Items, Scoring mit Boosts`

#### Auftrag B2 — Marktdaten, News, House View
**Owner:** Gianluca · **Files:** `scripts/spike_yfinance.py`, `enrich/{market,news,house_view}.py`, `data/{house_view,sector_proxies,ticker_overrides}.json`, `analytics/performance.py` (Treiber-Teil B, **mit Jacob abstimmen**: Gianluca liefert `MarketSnapshot`, Jacob konsumiert), `tests/test_news_parser.py`, `tests/test_house_view.py`
**Spec:** §5.4 B, §5.5, §5.15, §6.1–6.3 · **Daten:** data-notes §3 (exakte Strings für house_view), §14

**Interfaces** (`MarketSnapshot`/`PriceSeries` sind in `models.py` definiert, §4):
```python
def resolve_tickers(positions: list[PositionFact], max_positions: int = 15) -> dict[int, str]   # overrides → yf.Search(isin) → yf.Search(name); Memo pro Prozess
def fetch_prices(tickers: list[str], proxies: list[str]) -> dict[str, PriceSeries]               # ein yf.download Batch, period 3mo; pandas nur intern
def fetch_news(tickers: dict[int, str], top_industries: list[str]) -> list[Finding]              # news-1..6, beide Formate, 14 Tage, dedupe
def build_snapshot(fs: FactSheet, budget_s: float) -> MarketSnapshot                              # parallel, Budget, Disk-Cache-Fallback (D11); nie Exception nach oben
def load_house_view(path) -> dict
def house_view_findings(fs: FactSheet, house_view: dict, ref: ReferenceIndex) -> list[Finding]   # hv-*, contrary/aligned/hint, Kandidaten (max 3, Filter data-notes §15)
```
- [ ] **Spike zuerst (20 min):** `scripts/spike_yfinance.py` — Trefferquote ISIN→Ticker für die 20 größten Aktienpositionen über alle Klienten, News-Format, Batch-Dauer. Ergebnis als Kommentar in `docs/data-notes.md` §14 eintragen. Bei < 50 %: `ticker_overrides.json` für die Positionen der Demo-Klienten (CASE-003: Lindt & Sprüngli, Sensirion; CASE-011; CASE-012) manuell füllen.
- [ ] `house_view.json` aus einem öffentlichen CIO-Ausblick (UBS House View / Julius Bär / Pictet), Quelle + Datum im File, `"mock": true`. `category`-Strings **exakt** aus data-notes §3 (`Shares`, `Bonds`, `Liquidity`, `Real estate`, `Specialties andCommodities`; Regionen; 11 Branchen; `Swiss francs`/`US-Dollar`/`Euro`/`Andere`). Loader loggt Kategorien, die in keiner SAA vorkommen.
- [ ] Verify: `make test`; `uv run python -c "…build_snapshot…"` für CASE-003 < 8 s; WLAN aus → `source == "cache"` oder `warnings` gefüllt, kein Traceback. Commit: `yfinance Ticker/Kurse/News mit Zeitbudget und Cache-Fallback, House View JSON + Abgleich`

#### Auftrag C2 — URO-Look, Briefing-Panel, Upload
**Owner:** Levin · **Files:** `frontend/src/components/**`, `uro/api.py` (Upload-Route), `uro/store.py::merge` (**Jacob liefert die Merge-Logik in A4, Levin die Route und den Dialog**)
**Spec:** §9.1, §9.3, §9.4, §10 (Upload-Erkennung), §11 · **UI:** `PITCH.md` §11

- [ ] Tailwind-Tokens aus den Screenshots (`uro-primary` = das Blau der Kopfzeile, `uro-bg` hellgrau, weiße Karten, dünne Ränder, kaum Rundungen, dichte Tabellen). Semantik: `risk` rot · `fact` grau · `market` blau · `house_view` violett · `recommendation` grün · `assessment` kursiv mit Label „ASSESSMENT".
- [ ] `BriefingPanel`: Headline groß; 3 Sections mit Statement-Zeilen (linker Farbbalken = Typ, Label DATA/MARKET/HOUSE VIEW/ASSESSMENT); `ActionCard`s nummeriert mit `kind`-Badge; `SourceChip` `[risk-breach-CASE-003-01]` → Popover: `title`, `detail`, `type`, `severity`, `score`, `boost_reasons`, `source`, bei News Link. Einklappbar: Likely questions, Allocation vs. SAA (Mini-Balken aus `PortfolioFact.allocation`), Data coverage (`coverage`, `warnings`, `timings_ms`). Badges: `mode == "fallback"` → „Rule-based briefing (AI unavailable)"; `market.source == "cache"` → „Market data cached".
- [ ] Ladezustand: Key Findings aus `/facts` sofort; Schrittliste „Analysing portfolio → Fetching market news → Writing briefing → Checking facts" bis `/briefing` antwortet; „Prepared in 9.8 s" aus `timings_ms.total`. Fehler → Meldung + Retry, nie weißer Screen.
- [ ] `UploadDialog` (Drag & Drop, mehrere `.json`) → `POST /api/upload` → neue Klienten oben mit Badge NEW; Fehlermeldung pro Datei.
- [ ] **Anruf-Popup (≤ 30 min):** Button „Simulate incoming call" (nur in der Demo sichtbar, z. B. Tastenkürzel `P`) → Modal „CASE-003 Ron Burgundy is calling…" → Klick startet Briefing automatisch. Kein Backend nötig.
- [ ] Verify: `npm run typecheck && npm run build`; Upload einer umbenannten Kopie von CASE-003 mit `ClientRef: "TEST-001"` → erscheint, Briefing funktioniert. Commit: `URO-Look, Briefing-Panel mit Source-Chips, Upload-Dialog, Anruf-Popup`

#### Auftrag A4 — Upload-Merge im DataStore
**Owner:** Jacob · **Files:** `uro/store.py`, `tests/test_upload.py` · **Spec:** §10 Upload-Erkennung
- [ ] `merge(payload, filename)`: Array mit `ClientId`/`ClientRef` → Klienten (bekannte `ClientRef` ersetzen → `updated`, sonst `added`, `is_new=True`); Objekt mit Key `clients`/`Clients` → Klienten; Objekt mit `ClientRef` → einzelner Klient; Objekt mit `Securities`/`SuitabilityRules`/`StrategicAssetAllocations`/… → Referenz mergen (Dedupe `Id`/`RuleCode`, neue Einträge gewinnen, `Weight/100` beachten!) → `ReferenceIndex` neu bauen; sonst `errors.append(f"{filename}: not recognised …")`. Danach FactSheet- und Briefing-Cache leeren.
- [ ] Tests: jede Erkennungsregel; kaputte Datei → nur diese in `errors`. Commit: `Upload-Merge für Klienten- und Referenzdateien`

### Phase 3 — Chat und Feinschliff (11:00–12:30)

#### Auftrag B3 — Follow-up-Chat + Notiz-Extraktion
**Owner:** Gianluca · **Files:** `llm/chat.py`, `llm/extract_notes.py`, `llm/prompts.py` (Chat-Prompt §8.4, Chat-Kontext §8.2), `analytics/notes.py::check_intents` (**mit Jacob**), `tests/test_chat_sources.py`
- [ ] `answer(question, fs, briefing, history) -> ChatResponse`: Kontext = **alle** Findings + `exposures` + Positionsliste `pos-<secid>` (Name, Gewicht, Klasse, Branche, Währung, Vola, ESG) + Proposals + Briefing; System-Prompt gecacht; Antwort ≤ 120 Wörter; Quellen per Regex `\[([a-z]+-[a-z0-9-]+|profile)\]`. Testset = die 5 Fragen aus dem Case (Skelett-Docstring).
- [ ] `extract_intents(notes) -> list[ClientIntent]` via `messages.parse(output_format=IntentList)`; `check_intents` prüft deterministisch: `liquidity_need` mit Betrag vs. `total_liquidity_chf` → `LIQUIDITY` (ERROR wenn nicht gedeckt) mit `numbers={"need_chf", "available_chf"}`; `exclusion` (fossil/defense/tobacco) vs. Branchen-Exposure inkl. Look-through → `PREFERENCE_CONFLICT` **nur ab 2 % des Vermögens** (CLAUDE.md §4).
- [ ] Verify: die 5 Case-Fragen gegen CASE-003 und CASE-012; „What is the total semiconductor exposure?" → Antwort mit Look-through oder „not available in the data". Commit: `Follow-up-Chat mit Quellen; Notiz-Extraktion mit deterministischer Prüfung`

#### Auftrag C3 — Chat-UI, Integration, Performance
**Owner:** Levin · **Files:** `frontend/src/components/chat/*`, `service.py::chat`
- [ ] `ChatPanel` unter dem Briefing: Verlauf im Frontend-State, Klick-Chips aus `likely_questions` + 5 feste Fragen, Antworten mit Source-Chips (gleiches Popover).
- [ ] End-to-end-Messung für 5 Klienten: `timings_ms.total` < 15 s; sonst `LLM_MODEL=claude-sonnet-5` testen und Team informieren.
- [ ] Commit: `Chat-Panel, Integration, Latenzmessung`

#### Auftrag A3 — Treiber-Analyse, Boost-Feinschliff, Smoke grün
**Owner:** Jacob · **Files:** `analytics/performance.py` (Teil B mit `MarketSnapshot`), `analytics/market_comparison.py` (Spec §5.5), `scoring.py`
- [ ] `driver_findings(fs: FactSheet, market: MarketSnapshot) -> list[Finding]` (perf-<secid>: `contribution_pp = weight × PriceSeries.return_pct()`, ≈-Kennzeichnung im Text, Coverage-Finding wenn > 20 % des Vermögens ohne Kurse) und `market_comparison_findings(fs: FactSheet, market: MarketSnapshot, drivers: list[Finding]) -> list[Finding]` (mkt-<secid>: sector-wide / market-wide / stock-specific / mixed nach Spec §5.5; Proxy-Ticker aus `config.MARKET_PROXIES` und `data/sector_proxies.json`, deren Kurse Gianlucas `build_snapshot` mitliefert). Beide werden von `service.enrich_fact_sheet` aufgerufen.
- [ ] `make smoke` über 47 Klienten grün; `make eval-llm` (5 Klienten) manuell gegen Checkliste Spec §14.3 lesen. Commit: `Positions-Treiber und Marktvergleich aus yfinance-Kursen; Smoke grün`

### Phase 4 — Beweisführung (12:30–13:30)

#### Auftrag C4 — `eval/run_all.py` und Pitch-Zahlen
**Owner:** Levin (+ Jacob für Smoke-Teil)
- [ ] `python -m eval.run_all [--briefings] [--limit N] [--market] [--file <pfad>]` (Levins Version erweitern, nicht neu schreiben; `--briefings` und `--file` existieren): Tabelle pro Klient (`ref`, `#findings`, `top-3`, `coverage`-Fehler, `mode`, `issues`, `words`, `seconds`); Summary: „47 von 47 Briefings, 0 unbelegte Zahlen nach Validierung, Ø 9.4 s, max 13.8 s, Ø 187 Wörter, 6 Klienten mit sauber behandelten Datenlücken". Exit ≠ 0 bei Detektor-`error`. Zahlen in `PITCH.md` §6 eintragen.
- [ ] **Neue Dateien** (falls angekommen): per Upload einspielen, `run_all.py` erneut, Auffälligkeiten in `docs/data-notes.md` nachtragen.
- [ ] Robustheitsproben: `.env` ohne Key → Fallback-Badge; WLAN aus → Briefing ohne News + Warnung; CASE-001 (nur Cash), CASE-029 (kein Profil), CASE-038 (88 Positionen).

### Phase 5 — Freeze (13:30–15:00)
- [ ] **Kein neues Feature.** Nur: Bugfix, Demo-Probe ×2 (Levin präsentiert, Gianluca Backend-Log offen, Jacob Upload-Datei bereit), Slides (max. 8, Spec §18.1 + `PITCH.md`), Pitch-Sätze auswendig.

---

## 6. Zeitplan

| Uhrzeit | Jacob (A — Analytics) | Gianluca (B — AI & Markt) | Levin (C — API, Frontend, Pitch) |
|---|---|---|---|
| **bis 01:00** | ✅ Levin: Engine-Durchstich gepusht (`b1e5d1c`). Jacob: Plan + data-notes ins Repo | | |
| **01:00–01:30** | **A0** Deps, `config.py`, `CONTRACT CHANGE`, Makefile, CLAUDE.md-Verweise, push | **API-Key organisieren** (`.env`), dann `make demo` → erster echter LLM-Call, Zeit und Wortzahl notieren | Sprachentscheidung (§10.1) im Chat klären; Spec §9/§10 + `PITCH.md` §11 lesen |
| **01:30–02:30** | **A1 (rev.)** Härten: `ReferenceIndex`, `Weight/100`, Cash-Positionen, `coverage`, Profil- und Notiz-Findings, Fixtures + erste Tests | **B1 (rev.)** `client.py` (Timeout, Logging), `effort: low`, Retry, `fallback.py`, Prompt auf Englisch, `render_fact_sheet` mit Notizen/Coverage | **C1** `service.py` + `api.py` (`/clients`, `/facts`, `/briefing`); Vite-Skelett nur, wenn Zeit bleibt |
| **02:30 hart** | **Durchstich-Kriterium:** `make demo` liefert ein validiertes Briefing mit `mode` und Timing; `curl POST /api/clients/CASE-003/briefing` liefert dasselbe als JSON. Push. Dann Schlaf. | | |
| **02:30–08:00** | **Schlaf. Nicht verhandelbar** (CLAUDE.md §8). | | |
| **08:00–08:20** | Stand-up 10 min: Durchstich-Bugs verteilen, D11 (§10.1) entscheiden | **Spike** yfinance (20 min) | Bugs aus dem Durchstich |
| **08:20–11:00** | **A2** restliche Detektoren, Scoring, Tests · **A4** Upload-Merge | **B2** Markt, News, House View | **C2** URO-Look, Panel, Chips, Upload, Anruf-Popup |
| **11:00–12:30** | **A3** Treiber, Marktvergleich, Smoke grün | **B3** Chat, Notiz-Extraktion | **C3** Chat-UI, Integration, Latenz |
| **12:30–13:30** | Smoke-Teil von C4, neue Dateien einspielen | Prompt-Feinschliff an ≥ 3 Klienten (`make eval-llm`) | **C4** `run_all.py`, Zahlen in `PITCH.md`, Robustheitsproben |
| **13:30** | **Feature-Freeze** | | |
| **13:30–14:45** | Demo-Probe ×2, Upload-Datei bereit | Backend-Log, Fallback-Szenario geprobt | Slides, Pitch |
| **15:00** | **Pitch** | | |

**Streichliste bei Zeitnot — in dieser Reihenfolge streichen:** Notiz-Extraktion per LLM (B3, Flags reichen) → Marktvergleich `mkt-*` (A3) → Proposal-Impact → ESG-Detektor → Likely Questions → Mini-Chart → Anruf-Popup → Chat-Klick-Chips.
**Nie streichen:** Upload, Validator, Fallback, Source-Chips, `run_all.py`, Vola-vs-MaxVola-Check.

---

## 7. Demo

Drehbuch nach `PITCH.md` §7, mit den heute Nacht verifizierten Klienten (data-notes §13):

1. **Ping:** Popup „CASE-003 Ron Burgundy is calling" → Briefing startet automatisch. Key Findings stehen nach < 1 s, Briefing nach ~10 s.
   Erwartete Story: 97 % in zwei Schweizer Aktien (Lindt & Sprüngli 73 %, Sensirion 24 %), Volatilität 20.0 % gegen Profil-Limit 12.0 %, **0 gemeldete Verstöße** (keine Strategie hinterlegt), Notizen: Pensionierung in 2 Jahren bei 3 % Liquidität, ESG-Wunsch ohne Rüstung/Tabak, Fokus Dividenden. Actions: Konzentration abbauen, Liquidität für Pensionierung aufbauen, Risikoprofil-Gespräch.
2. **Source-Chip** auf `[risk-breach-CASE-003-01]` → Popover mit Rechnung und Quelle → „keine Zahl erfunden".
3. **Chat:** „Has the client raised concerns about volatility?" → Antwort zitiert `note-*` oder sagt, dass nichts vorliegt.
4. **CASE-011 Ellen Ripley** (falls Zeit): 60.6 % gegen 15 %, 0 Verstöße — der Hammer, sachlich vorgetragen.
5. **CASE-012 vs. CASE-016:** dieselbe Notiz „CHF 15,000 für Q1-Steuern", einmal CHF 328 liquide (Finding ERROR), einmal CHF 150'625 (kein Finding). Das ist die klientenspezifische Storyline.
6. **Live-Upload des unbekannten Testklienten** → Badge NEW → Generate → Briefing.
7. Falls gefragt: **Fallback** (Key entfernt) und **Datenlücke** (CASE-029 ohne Risikoprofil → `gap-no-risk-profile` im Briefing).

Slides (max. 8, Spec §18.1): Problem · Live-Demo · Pipeline „Engine rechnet, KI erzählt, Validator prüft" · Scoring-Formel mit Beispiel · Grounding (Chips, Validator, Fallback, Statement-Typen) · Mock vs. Produktion (`PITCH.md` §3) · Der Befund (11 von 47) · Pilot-Vorschlag. Zahlen aus `run_all.py` — **keine leeren Platzhalter**.

---

## 8. Agentenregeln

Ergänzend zu `CLAUDE.md` §12 und Spec §16 — die Punkte, die bei Coding-Agenten in der Praxis am häufigsten schiefgehen:

1. **Eine Session pro Owner, nur im eigenen Verzeichnisbereich (§3.2).** Fremde Module nicht anfassen; braucht man eine Änderung dort, im Teamchat anfragen und weiterarbeiten (Mock/Stub lokal).
2. **Session-Start** (Anhang): `CLAUDE.md` → Auftrag → Spec-Abschnitt → `data-notes.md` → bestehende Dateien im Zielbereich lesen → erst dann schreiben.
3. **Verifizieren, nicht behaupten.** Jeder Auftrag endet mit `make test && make lint` (Frontend: `npm run typecheck && npm run build`), bei Analytics zusätzlich `make smoke`, bei UI mit Browser-Check. „Sollte funktionieren" zählt nicht.
4. **Feldnamen nur aus `data-notes.md`.** Bei Unklarheit: `uv run python -c "import json; …"` gegen die echten Daten, Ergebnis in `data-notes.md` eintragen, **nicht** raten.
5. **Kein `date.today()` in `analytics/`**, keine Netz- oder Dateizugriffe dort. Zeit kommt aus `fs.history_as_of` / `fs.data_as_of`.
6. **Keine Demo-Hacks:** kein `if client_ref == "CASE-003"`, keine hartcodierten Namen, Wertpapiere oder erwarteten Texte außerhalb von `tests/fixtures/`.
7. **Zahlen:** intern Brüche 0–1; `Weight/100` genau einmal in `ingest.py`; Formatierung nur über `analytics/format.py`; jede Zahl in `Finding.numbers` steht formatiert in `title`/`detail`.
8. **Defensiv an der Grenze, nicht innen:** `obj.get(k) or []` beim Lesen der Rohdaten; Detektoren, Markt und LLM fangen Exceptions an ihrer Grenze (`logger.exception`) und liefern definierte Leerwerte; innerhalb einer Funktion nicht jeden Schritt einpacken.
9. **LLM:** Modellname nur aus `config.py`; kein Prefill; Structured Output + Pydantic; jeder Call mit Timeout, max. 1 Retry, deterministischer Fallback; Prompt-Änderungen an ≥ 3 Klienten testen (`make eval-llm`); Prompts/Antworten nach `logs/llm/`.
10. **Contracts:** `models.py` und `frontend/src/types/api.ts` nur gemeinsam, nur additiv, Commit-Präfix `CONTRACT CHANGE:`, Teamchat vorher.
11. **Git:** kleine Commits, `git pull --rebase` vor jedem Push, `main` bleibt lauffähig; nie `.env`, `logs/`, `data/cache/`, `node_modules/`.
11a. **Ausführung als Modul vom Repo-Root** (CLAUDE.md §6): `uv run python -m uro.demo`, `uv run python -m eval.run_all`, `uv run uvicorn uro.api:app`. Kein `python pfad/datei.py`, kein `sys.path`-Gefrickel. Neue ausführbare Datei → `__init__.py` daneben. Imports immer absolut (`from uro.models import …`).
11b. **Bestehenden Code erweitern, nicht ersetzen.** Levins Durchstich läuft auf 47/47. Wer einen Detektor härtet, behält die existierenden Finding-IDs (`perf-<pnr>`, `conc-single-<pnr>`, `risk-breach-<pnr>`, `gap-*`) und die Signatur von `build_fact_sheet(client, reference)`; interne Helfer (`ReferenceIndex`) kommen dazu, ohne dass `demo.py` oder `run_all.py` angepasst werden müssen.
12. **Scope:** Nichts bauen, was nicht in §5 steht (Spec §17: kein PDF-Import, keine DB, kein Auth, kein Mobile, kein Cloud-Deploy). Bei „das wäre noch cool" → in `PITCH.md` unter Ausblick notieren, nicht bauen.
13. **Bei Unsicherheit fragen** (Teamchat), statt große Umbauten eigenmächtig zu machen. Kleine Entscheidungen selbst treffen und im Commit-Text begründen.

**Definition of Done je Auftrag:** implementiert gemäß Spec-Abschnitt · Tests grün · Lint/Typecheck grün · (Analytics) Smoke grün · (UI) im Browser geprüft · Commit mit aussagekräftigem Text · Push.

---

## 9. Risiken

| Risiko | Wahrscheinlichkeit | Gegenmaßnahme | Wer/Wann |
|---|---|---|---|
| yfinance findet Schweizer ISINs nicht | hoch | Spike 08:00; `ticker_overrides.json` für Demo-Klienten; Treiber-Analyse degradiert sauber zu „Price history unavailable for x %" | Gianluca 08:00 |
| WLAN/yfinance fällt auf der Bühne aus | mittel | Disk-Cache-Fallback (D11), Warnung statt Crash; Demo-Probe mit WLAN aus | Gianluca B2, alle 13:30 |
| LLM-Latenz > 15 s mit Opus 5 | mittel | `effort: low`, `max_tokens 4000`, Caching; Schalter `LLM_MODEL=claude-sonnet-5`; Facts rendern sofort | Levin C3 misst um 11:30 |
| **API-Key fehlt** (Stand 00:55: der LLM-Call ist geschrieben, aber noch nie gelaufen) | **akut** | Key jetzt organisieren, in `.env` bei allen dreien (`ANTHROPIC_API_KEY=…`), `make demo` als ersten echten Test; bis dahin liefert `fallback.py` das Template-Briefing, damit API und Frontend nicht blockieren | Gianluca sofort |
| Rate Limit / 5xx während der Demo | niedrig | SDK-Retry `max_retries=1`, Timeout 45 s, danach Fallback-Badge | Gianluca B1 |
| Die 3 neuen Dateien haben ein anderes Format | mittel | Upload-Erkennung für Array / `{clients: […]}` / Einzelobjekt / Referenz; Fehler pro Datei; `run_all.py` sofort darüber laufen lassen | Jacob A4, Levin C4 |
| Unbekannter Testklient trifft einen Edge-Case | mittel | Fixture (c) „fast leer", Smoke über 47 inkl. CASE-001/029/038, `DATA_GAP` statt Exception | Jacob A1/A2 |
| Merge-Konflikte in `models.py` | mittel | Nur Jacob ändert sie, additiv, angekündigt; alle anderen `pull --rebase` vor jedem Commit | alle |
| Durchstich um 02:00 nicht geschafft | mittel | Hartes Ende 02:30; was fehlt, ist erster Punkt um 08:00; Frontend läuft notfalls gegen Fixture | alle |
| Verliebtheit ins UI vor laufender Pipeline | hoch (laut CLAUDE.md) | UI-Politur erst ab C2 (08:20), nach dem Durchstich | Levin |
| Halluzinierte Zahl im Live-Briefing | niedrig | Validator + Chips; `run_all.py --llm` zählt `unsupported_number` — die Zahl steht auf der Slide | Gianluca, Levin |

---

## 10. Offene Entscheidungen

Punkt 1 **jetzt im Chat** (bevor um 01:30 weitere Detektoren und Prompts geschrieben werden), der Rest beim 08:00-Stand-up, je eine Minute; Default gilt, wenn keiner widerspricht:

1. **Sprache von Findings, Prompt und Briefing: Englisch oder Deutsch?** Levins Durchstich schreibt Finding-Texte und Prompt auf **Deutsch** („Deutsch." im System-Prompt); Spec §2 hält **Englisch** als Teamentscheidung fest, CLAUDE.md schweigt. Case, Daten, RuleCodes und Notizen sind Englisch; die Original-URO-Screenshots sind Deutsch. Default-Empfehlung: **Englisch** (START-Hack-Pitch ist Englisch, Zahlenformat einheitlich `1,234.5`, Validator ohne Umlaut-Sonderfälle). Wer Deutsch will, entscheidet das jetzt; ein Wechsel nach 08:00 kostet jeden Detektor einmal anfassen.
2. **Markt-Disk-Cache als Fallback (D11)?** Default: **ja**, nur lesen wenn live scheitert, mit Badge.
3. **Alter als Ganzzahl im PII-freien FactSheet (D9)?** Default: **ja** (kein Geburtsdatum, keine Namen). Levins `strip_pii` entfernt `Birthday` bereits rekursiv; das Alter wird vorher berechnet und als `_Age` gesichert, analog zu `_DisplayName`.
4. **`service.py` bei Levin (D22)?** Default: **ja**.
5. **Zwei Zeitanker `history_as_of` / `data_as_of` (D20)?** Default: **ja**; UI beschriftet „Portfolio data as of 01 Jul 2026 · Market live".
6. **Anruf-Popup als Demo-Einstieg (D14)?** Default: **ja**, ≤ 30 min, UI-only.

---

## Anhang: Session-Start-Prompts

Zum Kopieren in eine frische Claude-Code-Session im Repo-Root. Platzhalter `<AUFTRAG>` durch `A1`, `B2` usw. ersetzen.

**Jacob (A):**
```
Lies CLAUDE.md, dann docs/superpowers/plans/2026-09-19-uro-briefing-strategy.md §0, §3, §4, §8 und den Auftrag <AUFTRAG> in §5,
dann die dort referenzierten Spec-Abschnitte in docs/superpowers/specs/2026-09-18-uro-briefing-assistant-design.md
und docs/data-notes.md vollständig. Ich bin Jacob, Owner von models.py, ingest.py, store.py, analytics/ und tests/fixtures.
Arbeite nur in diesen Dateien. Setze Auftrag <AUFTRAG> um: erst die Tests aus dem Auftrag, dann die Implementierung, dann
`make test && make lint && make smoke`. Feldnamen ausschließlich aus docs/data-notes.md; bei Unklarheit die echten Daten
mit einem kurzen Python-Einzeiler prüfen und den Befund in docs/data-notes.md eintragen. Kein date.today() in analytics/,
keine Demo-Hacks. Am Ende: Commit-Text vorschlagen (Repo-Stil, Deutsch, beschreibend), nicht pushen, Ergebnis zusammenfassen.
```

**Gianluca (B):**
```
Lies CLAUDE.md, dann docs/superpowers/plans/2026-09-19-uro-briefing-strategy.md §0, §1 (D6, D7, D11, D15, D21), §3, §8
und den Auftrag <AUFTRAG> in §5, dann die referenzierten Spec-Abschnitte (§6–§8) und docs/data-notes.md §3, §9, §10, §14, §15.
Lade vor dem ersten Anthropic-Call die Skill `claude-api` und halte dich an deren Structured-Output-, Caching- und
Streaming-Syntax (kein Prefill, kein forced tool_choice, Modell nur aus config.py). Ich bin Gianluca, Owner von llm/, enrich/,
data/house_view.json, data/sector_proxies.json, data/ticker_overrides.json und scripts/spike_yfinance.py. Arbeite nur dort.
Jeder externe Call: Timeout, try/except an der Grenze, definierter Leerwert, Logging. Setze <AUFTRAG> um, dann
`make test && make lint`; Prompt-Änderungen an ≥ 3 Klienten mit `make eval-llm` prüfen. Commit-Text vorschlagen, nicht pushen.
```

**Levin (C):**
```
Lies CLAUDE.md, PITCH.md §11, dann docs/superpowers/plans/2026-09-19-uro-briefing-strategy.md §0, §1 (D8, D12, D13, D14, D22),
§3, §4 (API-Modelle), §8 und den Auftrag <AUFTRAG> in §5, dann Spec §4.2, §9, §10, §11. Ich bin Levin, Owner von service.py,
api.py, frontend/, eval/run_all.py und PITCH.md. Arbeite nur dort; frontend/src/types/api.ts spiegelt uro/models.py 1:1.
Komponenten rufen nie direkt fetch (nur src/api/client.ts), keine Hex-Farben in Komponenten (Tailwind-Tokens uro-*), jeder
async-Zustand hat Loading/Error/Empty. Setze <AUFTRAG> um, dann `npm run typecheck && npm run build` und bei Backend-Änderungen
`make test && make lint`; UI im Browser prüfen (Screenshot). Commit-Text vorschlagen, nicht pushen.
```
