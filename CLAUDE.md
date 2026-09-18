# URO Briefing Assistant — Projekt-Kontext

> **Diese Datei ist gleichzeitig Team-Briefing und AI-Kontext.** Sie liegt im Repo-Root und wird von
> jeder Claude-Code-Session automatisch geladen. Wer etwas Grundlegendes lernt (Datenfalle, Entscheidung,
> Konvention), trägt es **hier** nach — nicht in einen Chat, den die anderen zwei nicht sehen.

**Team:** Levin, Jacob, Gianluca
**Hackathon:** START Global x Swiss AI Weeks 2026 — UnRiskOmega Challenge „From Ping to Pitch"
**Case-Daten:** https://github.com/START-Hack/unriskomega-2026

---

## 1. Was wir bauen

Ein Briefing-Assistent innerhalb eines nachgebauten **URO Advisor Pro**. Der Berater klickt
**„Generate Briefing"** für einen Klienten und bekommt in **unter 15 Sekunden** ein Briefing, das er in
**~60 Sekunden lesen** kann (150–220 Wörter), bevor er ins Kundengespräch geht.

Das Briefing hat genau drei Abschnitte:

1. **Recent Portfolio Development** — Was ist passiert, und was hat es getrieben?
2. **Portfolio Health Check** — SAA-Abweichung, Verstösse, Klumpenrisiken, Kundenpräferenzen, offene Proposals.
3. **Portfolio Outlook & Next Best Actions** — Marktkontext + House View + konkrete Handlungsempfehlungen.

**Der Kern, der uns von allen anderen unterscheidet:** eine *kohärente, klientenspezifische Storyline*,
keine drei getrennten Daten-Zusammenfassungen. Der Zusammenhang ist das Produkt.

---

## 2. Bewertungskriterien — und was sie für uns konkret heissen

| Gewicht | Kriterium | Was wir dafür tun |
|---|---|---|
| **25%** | Problem Fit & Business Value | 60-Sekunden-Story konsequent durchziehen. Next Best Actions müssen *konkret* sein („Position X um Y CHF reduzieren"), nicht generisch. |
| **25%** | Implementation Quality & Robustness | Läuft mit **unbekannten Testdaten**. Upload statt Hardcoding. Fehlende Daten werden zu Findings, nicht zu Crashes. Batch-Lauf über alle 47 Klienten als Beweis. |
| **20%** | AI Quality & Grounding | **Die Engine rechnet, die KI erzählt.** Jede Aussage referenziert eine Finding-ID. Validator prüft jede Zahl gegen das Fact Sheet. |
| **15%** | UX | URO-Look, Farbcodierung Fakt/Markt/House-View/Empfehlung/Risiko, scanbar in Sekunden. |
| **15%** | Bonus & Kreativität | Prio 1: Follow-up-Chat. Prio 2: Ex-Custody-PDF-Import. Prio 3: Anruf-Trigger als Demo-Einstieg. |

**Der Satz, der den Pitch trägt:**
> „Unser System kann keine Zahl erfinden, weil es keine Zahl selbst rechnet."

---

## 3. Architektur-Prinzip: Die Engine rechnet, die KI erzählt

Das ist die wichtigste Entscheidung des Projekts. Jede Abweichung davon muss im Team besprochen werden.

```
clients.json ──┐
reference.json ┼→ Ingest → Analytics → Findings[]  (typisiert, ID, Score)
Client Notes ──┘   (deterministisch, keine LLM-Zahlen)   │
                                                          │
News + House View ────────────────────────────────────────┤
                                                          ▼
                              LLM (claude-opus-5) → Briefing-JSON
                                     jede Aussage trägt finding_ids
                                                          ▼
                              Validator: jede Zahl im Text ⊆ Fact Sheet?
                                     Referenz existiert?  sonst: raus
                                                          ▼
                                              Briefing-Karte im UI
```

**Harte Regeln:**

- Das LLM bekommt **nie** Rohdaten zum Rechnen. Es bekommt fertige Findings und formuliert.
- Jede Aussage im Briefing-JSON hat `type` (`fact` | `market` | `house_view` | `recommendation` | `risk`)
  und `finding_ids: []`. Ohne Referenz wird die Aussage verworfen.
- Fehlende Daten sind **selbst ein Finding** („Kein Risikoprofil hinterlegt", „Volatilität nicht
  berechnet"), niemals ein stiller Fallback und niemals eine Exception.
- **IBANs, Geburtsdaten und Klarnamen gehen nie in einen Prompt.** Im Ingest strippen. (Die IBANs im
  Datensatz sind laut UnRiskOmega *echt durchgereicht* — das ist auch ein Pitch-Punkt: Schweizer Banken
  fragen als erstes nach Datenschutz.)

---

## 4. Die Daten — und die Fallen

47 Klienten · 57 Portfolios · 504 Securities · 48'101 Fonds-Look-through-Zeilen · 180 Suitability-Verstösse
(bei 26 Klienten) · 206 Proposals · 1'274 Transaktionen · 153 Client Notes (jeder Klient hat welche).
Performance-Historie: 58 Monatspunkte pro Portfolio, Ende `2026-07-01`. Klientennamen sind Filmfiguren.

### Die fünf Fallen — geprüft, nicht vermutet

| Falle | Realität | Konsequenz |
|---|---|---|
| `PerformanceYTD` | **Fehlt auf allen 57 Portfolios** | Selbst aus `PerformanceHistory` rechnen (1M / 3M / 12M / YTD) |
| „Absent, not null" (DATA.md) | **Stimmt nicht.** 20 Klienten haben `SuitabilityViolations: null`, 19 `EsgProfileId: null`, 18 `Transactions: null`, 17 `Proposals: null`, 4 `RiskProfileId: null`, 44 `IndividualRuleOverrides: null` | Immer `obj.get(k) or []` bzw. `or default` — nie nur `in`-Check, nie nur `.get()` |
| Risikokennzahlen | 7 Portfolios ohne `Volatility`, 6 ohne `ValueAtRisk`, 6 ohne `ExpectedReturn` | MaxVola-Abgleich nicht möglich → Finding „Kennzahl nicht verfügbar", kein Crash |
| Krypto-Konten | `AccountPositions[].Currency` enthält `BTC`, `ETH`, `SOL`, `SHIB`, `OZG` | Kein ISO-Code. `TotalAmountInPortfolioCurrency` ist trotzdem CHF und summierbar |
| 4 Firmenkunden | Kein `FirstName`/`LastName`/`Birthday`, dafür `Company` | Anzeigename-Helper zentral, nicht an 12 Stellen |

### Weitere Konventionen aus DATA.md (gelten wirklich)

- Join auf **`SecurityId`**, nie auf `Isin` — dieselbe ISIN existiert mehrfach (eine Zeile pro Währungstranche).
- Prozente in Positionen und SAA-Targets sind **Brüche 0–1**. `FundUnbundlingMappings[].Weight` ist
  dagegen **0–100**. Diese Inkonsistenz ist der wahrscheinlichste stille Rechenfehler im ganzen Projekt.
- Für SAA-Vergleiche die **`SAA_*`-Felder** benutzen (`SAA_AssetClassName` etc.), nicht die feineren
  `AssetClassName`-Felder — die matchen die Target-Kategorien nicht.
- `ContributionVolatility` (nicht `MarginalContributionToRisk`) summiert sich zu `Portfolio.Volatility`.
- Daten sind um einen konstanten Offset nach vorn geschoben. Relative Abstände stimmen, absolute Daten nicht.

### Der Goldschatz: `ClientNotes`

Jeder der 47 Klienten hat Notizen, im Klartext, z. B.:

> „No direct positions in fossil fuels, please."
> „Plans to retire in the next two years, increasing liquidity needs expected."
> „Prefers ESG-compliant investments, no defense or tobacco holdings."

**Pipeline dafür:** LLM extrahiert strukturierte Intentionen (`exclusion`, `liquidity_need`,
`preference`, `concern`) → Engine prüft *deterministisch* gegen die Positionen → eigene Finding-Klasse
`preference_conflict`. Beispiel-Output: „Kundin schliesst fossile Energien aus, hält aber 4,1% Energiesektor."

Das ist die Verknüpfung, die die Jury „coherent storyline" nennt — und die kaum ein anderes Team bauen wird.

### Häufigste Verstösse (Material für Abschnitt 2)

`Cluster risk of a single financial instrument` (23×) · `Underweight in the equity sector "Consumer Staples"` (10×)
· `Underweight in the equity region "Asia/Pacific (ex Japan)"` (10×) · `Volatility range undershot` (8×)
· `Compliance with maximum volatility` (7×) · `Foreign currency cluster risk EUR` (6×)

---

## 5. Repo-Struktur und Ownership

```
uro-briefing/
├─ CLAUDE.md              ← diese Datei
├─ data/                  ← clients.json, reference.json, house_view.json (selbst gebaut)
├─ src/uro/
│  ├─ models.py           ← FactSheet, Finding, Briefing  [gemeinsam, Stunde 1]
│  ├─ ingest.py           ← laden, normalisieren, PII strippen        │ JACOB
│  ├─ analytics/          ← performance, saa, concentration,          │ JACOB
│  │                        suitability, notes, scoring               │
│  ├─ enrich/             ← news.py, house_view.py                    │ GIANLUCA
│  ├─ llm/                ← prompts.py, briefing.py, validator.py,    │ GIANLUCA
│  │                        chat.py, extract_notes.py                 │
│  └─ api.py              ← FastAPI                                   │ LEVIN
├─ frontend/              ← Vite + React + Tailwind, URO-Look         │ LEVIN
└─ eval/run_all.py        ← Batch über alle 47 Klienten               │ LEVIN
```

| | Wer | Ownership | Erstes Deliverable |
|---|---|---|---|
| **A** | **Jacob** | `models.py`, `ingest.py`, `analytics/` | `build_fact_sheet(client) → FactSheet` mit Performance, SAA-Abweichung, Konzentration, Verstössen |
| **B** | **Gianluca** | `llm/`, `enrich/` | Briefing-Prompt + Validator gegen ein **handgeschriebenes** Beispiel-FactSheet |
| **C** | **Levin** | `api.py`, `frontend/`, `eval/`, Pitch | URO-Mockup + Generate-Briefing-Flow gegen eine Mock-Response |

**Der Unlock für paralleles Arbeiten:** In Stunde 1 definieren wir gemeinsam `models.py` und committen es.
Danach arbeitet Gianluca gegen ein Fake-FactSheet und Levin gegen eine Fake-Briefing-Response.
Niemand wartet auf jemanden. **Wer die Contracts ändert, sagt es im Teamchat, bevor er committet.**

---

## 6. Setup

```bash
uv init --python 3.12
uv add fastapi uvicorn anthropic pydantic python-dateutil pdfplumber httpx
uv add --dev pytest
```

**Python 3.12, nicht 3.14** — ein paar Libs hinken noch hinterher, und wir wollen nachts um drei keine
Wheel-Build-Fehler debuggen.

**Git-Workflow:** ein Branch (`main`), oft committen, `git pull --rebase` vor jedem Push. Bei drei Leuten
mit klarer Modul-Ownership ist das schneller als Feature-Branches — Merge-Hölle um Stunde 20 ist ein
reales Risiko, kein theoretisches.

---

## 7. LLM-Setup

- **Modell:** `claude-opus-5` für Briefing-Generierung *und* Notiz-Extraktion.
- **Latenz:** `output_config={"effort": "low"}` + Streaming. Die Analytik ist in <1s fertig und wird
  sofort gerendert — der Berater sieht nie einen leeren Screen, während der Erzähltext nachläuft.
- **Kosten/Speed:** Prompt-Caching auf dem System-Prompt (`cache_control={"type": "ephemeral"}`).
  Der System-Prompt ist stabil, die Findings variieren → stabiler Teil zuerst, volatiler danach.
- **Output:** strukturiertes JSON via `output_config.format`, nie Fliesstext. Pro Abschnitt max. 3 Aussagen.
- **Kein Prefill.** Auf Opus 5 gibt das einen 400er.

### Briefing-Output-Contract

```python
{
  "headline": str,                      # ein Satz, die Kernaussage
  "sections": [
    {"title": "Recent Portfolio Development", "statements": [
       {"text": str, "type": "fact"|"market"|"house_view"|"recommendation"|"risk",
        "finding_ids": [str]}
    ]}, ...
  ],
  "likely_questions": [{"question": str, "answer_hint": str}],   # max 2
  "next_best_actions": [{"action": str, "rationale": str, "finding_ids": [str]}]
}
```

### Findings-Scoring (die „Wie wählt euer System aus?"-Antwort der Jury)

`score = severity × materiality × client_relevance × recency`

- **severity:** Error > Warning > Beobachtung
- **materiality:** betroffener CHF-Betrag
- **client_relevance:** Treffer in Notes/Tags?
- **recency:** wie frisch

Nur die **Top 3–5** kommen ins Briefing. Der Rest bleibt im Follow-up-Chat abrufbar.

---

## 8. Meilensteine

| | Ziel |
|---|---|
| **22:00–22:15** | ✅ Erledigt: Repo, venv, Case-Daten, `models.py`, Modul-Skelette. |
| **22:15–01:00** | Alle drei parallel: Jacob `analytics/`, Gianluca `llm/`, Levin Frontend gegen Mock-Response. |
| **01:00–02:00** | **Hässlicher Durchstich**: Klient wählen → echtes FactSheet → echter LLM-Call → Briefing im Browser. Hässlich ist okay, durchgängig ist Pflicht. **Erst danach schlafen.** |
| **02:00–08:00** | Schlafen. Sechs Stunden, alle drei. Wer um 5 Uhr Code schreibt, produziert morgen die Bugs. |
| **08:00–11:00** | Findings-Scoring, Präferenzkonflikte aus Notes, House-View-JSON, URO-Look. **Die 3 neuen Client-Dateien kommen heute** → Upload testen. |
| **11:00–12:30** | Bonus 1: Follow-up-Chat (fast gratis — das FactSheet existiert schon). |
| **12:30–13:30** | Batch-Lauf über alle 47 Klienten + die neuen Dateien. Kennzahlen für den Pitch. |
| **13:30** | **Feature-Freeze.** Ab hier nur noch Stabilität, Demo-Probe, Slides. Keine neuen Features, egal wie verlockend. |
| **15:00** | **Pitch.** |

**Die grösste strategische Gefahr:** sich ins Mockup-Design verlieben, bevor die Pipeline läuft.
UX ist 15%. Implementation + AI Quality sind zusammen 45%.

---

## 9. Robustheit — die Testdaten kommen erst später

Drei weitere Client-Dateien in derselben Form kommen am Folgetag, plus ein unbekannter Testklient kurz
vor der Präsentation. Daraus folgt:

- **Nie einen Dateinamen hardcoden.** Loader nimmt jede Datei dieser Form, Upload-Button im UI.
- **News und Kursdaten cachen**, plus Offline-Fallback: fällt Yahoo während der Live-Demo aus, läuft das
  Briefing mit dem Hinweis „Marktdaten nicht verfügbar" weiter, statt abzustürzen.
- **`eval/run_all.py`** läuft über alle Klienten und gibt aus: erzeugte Briefings, gescheiterte,
  unbelegte Zahlen, Ø-Latenz. Diese Zahlen kommen auf eine Slide. Sie beantworten die Jury-Frage nach dem
  unbekannten Testklienten, bevor sie gestellt wird.

---

## 10. Demo-Drehbuch

„From Ping to Pitch" wörtlich nehmen: Die Demo startet mit einem **eingehenden Anruf** — Popup
„\<Klient\> ruft an", das Briefing startet automatisch, nach ~12 Sekunden steht es. Das ist der *Ping*.
Das Briefing, mit dem der Berater ins Gespräch geht, ist der *Pitch*.

Im Zukunftsteil: in Produktion getriggert per Anruferkennung oder Kalendereintrag — Briefings für
geplante Termine liegen morgens schon bereit.

**Klienten-Reihenfolge für die Demo** (nach Stärke, die sie zeigen):
1. Ein Klient mit Liquiditätsbedarf + Präferenz → das Beispielszenario aus dem Case.
2. Ein Klient mit Klumpenrisiko **ohne** formalen Verstoss → wir erkennen Risiken, die keine Regel meldet.
3. Ein Klient, der Vorschläge ablehnt → wir respektieren Präferenzen statt Standardempfehlung.
4. **Live-Upload des unbekannten Testklienten.**

---

## 11. Offene Fragen an die Mentoren

- Welche House-View-Quelle sehen sie gern? (Wir kodieren einen öffentlichen CIO-Ausblick einmalig als JSON.)
- Wie oft scheitert ISIN→Ticker bei Yahoo, vor allem bei Schweizer Fonds? Fallback auf Index-/Sektorproxy einplanen.
- Sind Positionen im Execution-only-Depot bewusst ohne Regelverstoss?
- Es gibt **keine Positions-Historie** — welche Position die Performance getrieben hat, steht nicht in den
  Daten. Unsere Näherung: Kursverläufe der grössten Positionen via Yahoo holen, Gewicht × Kursveränderung.
  Das muss im UI als **Näherung** gekennzeichnet sein. Ist das so akzeptiert?

---

## 12. Checkliste für jede AI-Session

Bevor du Code schreibst:

1. Diese Datei gelesen — besonders **§4 Die Fallen** und **§3 Harte Regeln**.
2. Geprüft, ob du in **deinem Modul** arbeitest (§5). Fremde Module nicht anfassen ohne Absprache.
3. Keine Zahl im LLM-Pfad berechnen. Zahlen kommen aus `analytics/`, Punkt.
4. Jeder Feldzugriff auf Case-Daten defensiv: `obj.get("X") or []` — die Daten enthalten `null`,
   nicht nur fehlende Keys.
5. Neue Erkenntnis über die Daten? **Hier eintragen**, nicht im Chat lassen.
