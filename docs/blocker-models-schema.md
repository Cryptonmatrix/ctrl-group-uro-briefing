# Blocker auf `main`: `uro/models.py` erzeugt ein Schema, das die Anthropic-API ablehnt

> **Status: behoben auf `main`** (Commit „CONTRACT CHANGE: Briefing-Schema Structured-Outputs-konform", 2026-09-19).
> Schritte 1–3 zeilengleich wie auf `gianluca` (`f64985c`), damit der Merge konfliktfrei bleibt. Schritt 4 anders als
> hier vorgeschlagen: Die Grenzen setzt `Briefing.model_post_init` durch statt des Validators — das greift bei jedem Weg,
> auf dem ein Briefing entsteht, auch bei rohem JSON aus `messages.create`. Konstanten `MAX_STATEMENTS_PER_SECTION`,
> `MAX_LIKELY_QUESTIONS`, `MAX_NEXT_BEST_ACTIONS` in `uro/models.py`. Regressionstest: `tests/test_briefing_schema.py`.
> Offline verifiziert (Reproduktion aus §2 liefert `[]` und `False`); ein Live-Aufruf steht noch aus, weil auf dem Rechner
> kein API-Schlüssel liegt.

**Betrifft:** `uro/models.py` auf `origin/main`, Stand Commit `0398323`
**Wirkung:** Jeder Briefing-Aufruf scheitert mit HTTP 400. Der LLM-Pfad ist auf `main` komplett tot.
**Aufwand für den Fix:** unter fünf Minuten.
**Dringlichkeit:** blockiert beide anderen Branches beim Merge.

---

## 1. Symptom

Ein Aufruf an `POST https://api.anthropic.com/v1/messages` mit
`output_config.format.type = "json_schema"` und dem aus `Briefing` erzeugten Schema
antwortet mit HTTP 400. Zwei Fehlermeldungen, nacheinander:

```
output_config.format.schema: For 'object' type, 'additionalProperties'
must be explicitly set to false
```

Nach Behebung der ersten:

```
output_config.format.schema: For 'array' type, property 'maxItems' is not supported
```

Beide kommen in unter 0,3 Sekunden zurück. Es ist **kein** Netzwerk- oder Latenzproblem.

---

## 2. Reproduktion ohne Netzaufruf

```python
import json
from uro.models import Briefing

schema = Briefing.model_json_schema()

fehlend = [
    name for name, d in schema.get("$defs", {}).items()
    if d.get("type") == "object" and d.get("additionalProperties") is not False
]
if schema.get("additionalProperties") is not False:
    fehlend.append("Briefing (root)")

print("ohne additionalProperties:false:", fehlend)
print("maxItems im Schema:", "maxItems" in json.dumps(schema))
```

Aktuelle Ausgabe auf `main`:

```
ohne additionalProperties:false: ['LikelyQuestion', 'NextBestAction', 'Section', 'Statement', 'Briefing (root)']
maxItems im Schema: True
```

Erwartet nach dem Fix: leere Liste und `False`.

---

## 3. Ursache

Structured Outputs stellt zwei Anforderungen an das JSON-Schema, die Pydantic
standardmässig **nicht** erfüllt:

**Regel 1 — jedes `object` braucht `additionalProperties: false`.**
Pydantic setzt das nur, wenn das Modell `extra="forbid"` konfiguriert hat.
Ohne diese Konfiguration fehlt das Feld im erzeugten Schema komplett, und die API
lehnt ab. Betroffen ist jedes Modell, das im Briefing-Schema vorkommt.

**Regel 2 — `maxItems` ist nicht erlaubt.**
Pydantic übersetzt `Field(max_length=N)` auf einer Liste zu `maxItems: N`.
Die API weist das zurück. Längenbegrenzungen müssen deshalb ausserhalb des Schemas
durchgesetzt werden: im Prompt als Anweisung und im Validator als harte Kürzung.

Enums (`StatementType`, `ActionKind`) sind nicht betroffen — sie erzeugen kein `object`.

---

## 4. Exakte Fundstellen auf `main`

### Regel 1 — diesen fünf Klassen fehlt `model_config`

| Zeile | Klasse |
|---|---|
| 271 | `Statement` |
| 279 | `Section` |
| 284 | `LikelyQuestion` |
| 302 | `NextBestAction` |
| 310 | `Briefing` |

### Regel 2 — diese drei Zeilen enthalten `max_length` auf einer Liste

```
281:    statements: list[Statement] = Field(max_length=3, description="Max 3 — 60-Sekunden-Regel")
318:    likely_questions: list[LikelyQuestion] = Field(default_factory=list, max_length=2)
319:    next_best_actions: list[NextBestAction] = Field(default_factory=list, max_length=3)
```

---

## 5. Der Fix

**Schritt 1** — Import ergänzen:

```python
from pydantic import BaseModel, ConfigDict, Field
```

**Schritt 2** — in `Statement`, `Section`, `LikelyQuestion`, `NextBestAction` und `Briefing`
jeweils als erste Zeile des Klassenkörpers (nach dem Docstring):

```python
    model_config = ConfigDict(extra="forbid")
```

**Schritt 3** — die drei `max_length`-Angaben entfernen. Die Beschreibung bleibt:

```python
    statements: list[Statement] = Field(
        description="Hoechstens 3 — Grenze setzt der Validator durch")
    ...
    likely_questions: list[LikelyQuestion] = Field(default_factory=list)
    next_best_actions: list[NextBestAction] = Field(default_factory=list)
```

**Schritt 4** — sicherstellen, dass die Grenzen woanders greifen. Der System-Prompt sagt
bereits „pro Abschnitt höchstens drei Aussagen". Ergänzend muss der Validator kürzen:

```python
MAX_STATEMENTS, MAX_QUESTIONS, MAX_ACTIONS = 3, 2, 3

for section in briefing.sections:
    section.statements = section.statements[:MAX_STATEMENTS]
briefing.likely_questions = briefing.likely_questions[:MAX_QUESTIONS]
briefing.next_best_actions = briefing.next_best_actions[:MAX_ACTIONS]
```

Ohne Schritt 4 sind die Grenzen nirgends mehr durchgesetzt und das Briefing kann zu lang werden.

---

## 6. Warum die vorhandenen Tests das nicht gefunden haben

Die Tests in `tests/` prüfen die Analytik: Fact Sheets, Findings, Scoring, Ingest.
Kein Test erzeugt das JSON-Schema und prüft es gegen die Regeln der API. Der Fehler
tritt erst beim echten Aufruf auf — und der braucht einen API-Schlüssel, läuft also
in keinem der bestehenden Tests.

Das ist kein Vorwurf an die Testabdeckung, sondern ein Hinweis darauf, welcher Test fehlt.

---

## 7. Vorschlag: Regressionstest ohne Netzaufruf

Der Fix ist eine stille Eigenschaft des Schemas. Er wird bei der nächsten Überarbeitung
von `models.py` genauso leicht wieder verloren gehen, wie er es diesmal ist. Ein Test,
der ohne API-Schlüssel läuft, verhindert das:

```python
# tests/test_briefing_schema.py
import json
from uro.models import Briefing


def test_schema_erfuellt_die_regeln_der_structured_outputs_api():
    """Beide Regeln sind stille Anforderungen — ohne Test gehen sie beim
    naechsten Umbau von models.py wieder verloren."""
    schema = Briefing.model_json_schema()

    def objekte_ohne_forbid(node, pfad="root"):
        treffer = []
        if isinstance(node, dict):
            if node.get("type") == "object" and node.get("additionalProperties") is not False:
                treffer.append(pfad)
            for key, value in node.items():
                treffer += objekte_ohne_forbid(value, f"{pfad}.{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                treffer += objekte_ohne_forbid(value, f"{pfad}[{i}]")
        return treffer

    assert objekte_ohne_forbid(schema) == [], (
        "Jedes object im Schema braucht additionalProperties: false. "
        "In Pydantic heisst das model_config = ConfigDict(extra='forbid')."
    )
    assert "maxItems" not in json.dumps(schema), (
        "maxItems ist in Structured Outputs nicht erlaubt. "
        "Kein max_length auf Listen, die ins LLM-Schema gehen."
    )
```

---

## 8. Kontext zum Merge

Der Fix existiert bereits zweimal ausserhalb von `main`:

- `levin/frontend-api` — enthält ihn seit Commit `aff40ff`
- `gianluca` — Commit `f64985c` („Structured Outputs extra=forbid and messages.create raw schema")

Beide Branches sind unabhängig voneinander auf dieselbe Ursache gestossen. Wer `main`
in seinen Branch merged, holt sich die kaputte Fassung zurück, wenn `models.py` von
`main` gewinnt. Deshalb sollte der Fix **auf `main`** landen, bevor gemerged wird.

---

## 9. Zweiter Befund, unabhängig davon

Beim Debuggen derselben Kette sind zwei weitere Umgebungsprobleme aufgefallen. Sie
betreffen `models.py` nicht, sind aber für den Pitch relevant:

**`client.messages.parse()` und der SDK-Transport hängen.** Auf dem Demo-Rechner kam das
`anthropic`-SDK auch mit `timeout=60, max_retries=0` nach über 280 Sekunden nicht zurück.
Derselbe Request: curl 19,5 s, `urllib` aus der Standardbibliothek 19,1 s. Die Ursache
liegt im `httpx2`-Transport, dessen Timeout in dieser Umgebung nicht auslöst.
Ein Timeout, der nicht auslöst, friert auf der Bühne das UI ein. Auf `levin/frontend-api`
liegt als Ausweichlösung `uro/llm/transport.py` (Standardbibliothek, ~90 Zeilen,
Timeout löst nachweislich aus, eigene Fehlerklasse je Ursache).

**`@app.on_event("startup")` ist mit Starlette 1.6 veraltet** und hing beim Serverstart,
ohne eine einzige Logzeile zu schreiben. Ersetzt durch `lifespan`.
