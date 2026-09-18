# Pitch-Notizen

> **Lebendes Dokument.** Wer eine Entscheidung trifft, die man auf der Bühne erklären muss,
> trägt sie hier ein — mit der Begründung, nicht nur mit dem Ergebnis. Die Jury fragt nach dem Warum.
>
> Team: Levin, Jacob, Gianluca · Pitch: 15:00

---

## 1. Die Sätze, die sitzen müssen

Drei Formulierungen, die wir auswendig können sollten. Alles andere kann improvisiert werden.

**Zum Grounding (Kriterium 3, 20%):**
> „Unser System kann keine Zahl erfinden, weil es keine Zahl selbst rechnet.
> Eine deterministische Engine berechnet alle Fakten, das Sprachmodell darf sie nur
> priorisieren und formulieren. Ein Validator prüft danach jede Zahl gegen das Fact Sheet."

**Zum Business Value (Kriterium 1, 25%):**
> „Ein Berater betreut 500 Klienten. Wenn einer unangekündigt anruft, hat er keine Minute,
> sondern Sekunden. Wir geben ihm in unter 15 Sekunden das, wofür er sonst vier Systeme
> öffnen müsste — und er liest es in sechzig."

**Zur Robustheit (Kriterium 2, 25%):**
> „Wir haben das gegen alle 47 Klienten laufen lassen, nicht gegen einen Demo-Fall.
> [Zahlen einsetzen] Briefings erzeugt, null unbelegte Zahlen, im Schnitt [X] Sekunden."

---

## 2. Designentscheidungen und ihre Begründung

### Die Engine rechnet, die KI erzählt

**Entscheidung:** Strikte Trennung. Deterministischer Code berechnet alle Kennzahlen und erzeugt
typisierte „Findings". Das LLM bekommt nur diese Findings und formuliert daraus die Storyline.

**Warum:** Die naheliegende Lösung — Rohdaten ins LLM, Briefing raus — verliert in drei
Bewertungskategorien gleichzeitig. Sie halluziniert Zahlen (Kriterium 3), sie ist bei unbekannten
Testdaten unvorhersehbar (Kriterium 2), und man kann der Jury nicht erklären, wie sie auswählt.

**Was das kostet:** Mehr Code. Die Analytik muss wirklich rechnen können, sonst ist das Briefing leer.

### Jede Aussage trägt ihre Quelle

**Entscheidung:** Das LLM liefert strukturiertes JSON, keinen Fliesstext. Jede Aussage hat einen
Typ (Fakt / Markt / House View / Empfehlung / Risiko) und eine Liste von Finding-IDs.

**Warum:** Die Jury fragt explizit „Are facts, interpretations and recommended actions
distinguishable?". Mit Typisierung ist die Antwort sichtbar statt behauptet — im UI als Farbcodierung,
beim Hovern die Quelle. Und der Validator kann Aussagen ohne Referenz automatisch verwerfen.

### Fehlende Daten sind ein Finding, kein Crash

**Entscheidung:** Jede Datenlücke wird zu einem `DATA_GAP`-Finding („Kein Risikoprofil hinterlegt",
„Volatilität nicht berechnet") und erscheint im Briefing, statt abzustürzen oder still zu verschwinden.

**Warum:** Kriterium 2 fragt wörtlich nach „handles missing, incomplete or inconsistent data sensibly".
Und der unbekannte Testklient wird garantiert Lücken haben — wir haben im Datensatz nachgezählt:
20 von 47 Klienten haben gar keine Suitability-Verstösse hinterlegt, 4 kein Risikoprofil,
7 Portfolios keine Volatilität.

**Bühnenwert:** Ein Berater, dem auffällt, dass ein Risikoprofil fehlt, ist wertvoller als einer,
der es nicht merkt. Die Lücke ist Information.

### PII wird in der Ingest-Schicht entfernt

**Entscheidung:** IBANs, Geburtsdaten und Klarnamen werden beim Einlesen gestrippt und erreichen
niemals einen Prompt. Der LLM-Kontext enthält `CASE-001`, nicht den Namen.

**Warum:** Der Datensatz enthält laut UnRiskOmegas eigener Dokumentation **echte, durchgereichte
IBANs**. Eine IBAN allein ist zwar unkritisch — sie steht auf jeder Rechnung, und Geld abheben kann
man damit nicht. Problematisch ist die Kombination: IBAN plus Vermögen plus Depotinhalt plus
Beraternotizen über Pensionierung, Scheidung oder Immobilienkauf. Das ist Personendatenbearbeitung
nach Schweizer DSG.

**Der Pitch-Punkt ist nicht das private Repo**, sondern die Architektur: Wir haben eine definierte
Stelle, an der PII die Pipeline verlässt. Eine Bank, die das in Produktion nimmt, muss genau diese
eine Stelle prüfen, nicht die ganze Codebase. Schweizer Banken fragen das als erstes — wir sollten
es von selbst ansprechen, bevor sie fragen.

### Ein privates Repo

**Entscheidung:** Repo privat, Daten nicht öffentlich gespiegelt.

**Warum:** UnRiskOmega schreibt ausdrücklich „don't publish it further". Die Anweisung des
Case-Owners zur Datenhandhabung zu ignorieren, wäre vor einer Jury aus Bankleuten ein Eigentor —
unabhängig davon, wie gross das tatsächliche Risiko ist.

### Priorisierung mit einer sichtbaren Formel

**Entscheidung:** `score = severity × materiality × client_relevance × recency`.
Nur die Top 3–5 Findings kommen ins Briefing, der Rest bleibt im Follow-up-Chat abrufbar.

**Warum:** Die Jury fragt „Can the team explain how the system selects, ranks and summarizes
information?". Eine Formel auf einer Slide beantwortet das in fünf Sekunden. „Das Modell entscheidet"
beantwortet es nicht.

### Fakten sofort, Erzähltext danach

**Entscheidung:** Die Analytik läuft in unter einer Sekunde und wird sofort gerendert. Der Erzähltext
streamt danach abschnittsweise nach.

**Warum:** Kriterium 2 fragt nach Antwortzeit „suitable for use immediately before a client
interaction". Der Berater sieht nie einen Ladebalken auf leerem Bildschirm — er sieht sofort Zahlen
und liest schon, während das Briefing entsteht.

---

## 3. Mock vs. Produktion — die Grenze sauber ziehen

Kriterium 2 fragt wörtlich: „Are the boundaries between mock components and potential production
integrations clearly explained?" Das ist eine geschenkte Frage, wenn wir vorbereitet sind.

| Komponente | Bei uns | In Produktion |
|---|---|---|
| Client-, Portfolio-, CRM-Daten | Flat Files von UnRiskOmega | URO-Advisor-Pro-API |
| House View / CIO-Sicht | Einmalig kodiertes JSON aus einem öffentlichen Bank-Ausblick | Die Bank liefert dieses JSON aus ihrem eigenen CIO-Prozess |
| Marktnews | Yahoo Finance, gecacht | Bloomberg / Reuters, lizenziert |
| Performance-Attribution | Näherung: Gewicht × Kursveränderung | Echte Positions-Historie aus dem Kernbanksystem |
| Oberfläche | Nachgebaut nach den URO-Screenshots | Feature innerhalb von URO Advisor Pro |
| LLM-Hosting | Anthropic API | Je nach Bank: EU/CH-Hosting oder On-Premise |

**Wichtig bei der Attribution:** Der Datensatz enthält **keine Positions-Historie**. Welche Position
die Performance getrieben hat, steht nirgends. Unsere Näherung muss im UI als Näherung gekennzeichnet
sein, und wir sagen das auf der Bühne selbst. Eine sauber deklarierte Näherung wirkt kompetent,
eine stillschweigende wirkt schlampig — und in dieser Jury sitzt jemand, der es merkt.

---

## 4. Was uns von den anderen Teams unterscheidet

Die meisten Teams werden Portfolio-Daten plus News plus LLM bauen. Drei Dinge, die vermutlich
kaum jemand hat:

**Die Client Notes als Prüfquelle.** Jeder der 47 Klienten hat Freitext-Notizen: „No direct positions
in fossil fuels, please", „Plans to retire in the next two years". Wir extrahieren daraus strukturierte
Absichten und prüfen sie *deterministisch* gegen die Positionen. Ergebnis: „Klient schliesst fossile
Energien aus, hält aber 4,1% Energiesektor." Das ist genau die Verknüpfung, die der Case
„coherent storyline" nennt — und sie kommt aus einer Datenquelle, die viele übersehen werden.

**Risiken erkennen, die keine Regel meldet.** Ein Klient kann null Suitability-Verstösse haben und
trotzdem 68% in einem einzigen Titel halten. Wer nur die Verstoss-Liste ausliest, sieht ein sauberes
Portfolio. Wir rechnen Konzentration selbst.

**Der Batch-Lauf über alle 47.** Statt einer polierten Demo mit einem Klienten zeigen wir, dass es
für alle funktioniert. Das beantwortet die Frage nach dem unbekannten Testklienten, bevor sie
gestellt wird.

---

## 5. Fragen, die kommen werden

| Frage | Unsere Antwort |
|---|---|
| „Woher wisst ihr, dass das Modell nichts erfindet?" | Der Validator prüft jede Zahl im Text gegen das Fact Sheet. Findet er eine ungedeckte Zahl, fliegt die Aussage raus. Im Batch über alle 47: [Zahl] Verstösse. |
| „Wie wählt euer System aus, was wichtig ist?" | Formel zeigen: severity × materiality × client_relevance × recency. Top 3–5 ins Briefing, Rest im Chat. |
| „Funktioniert das mit einem Klienten, den ihr nie gesehen habt?" | Upload live vorführen. Plus: wir haben es gegen alle 47 laufen lassen, nicht gegen einen. |
| „Was passiert, wenn Daten fehlen?" | Die Lücke wird selbst zu einem Befund im Briefing. Beispiel live zeigen — wir haben 4 Klienten ohne Risikoprofil im Datensatz. |
| „Wie kommt das in URO Advisor Pro?" | Die Engine ist ein Service mit klarer Schnittstelle. Der Button sitzt in der Aktionsleiste, wo im echten Produkt schon Telefonberatung und Notizen stehen. |
| „Was ist mit Datenschutz?" | PII verlässt die Pipeline in der Ingest-Schicht. Eine definierte Stelle, prüfbar. Das LLM sieht `CASE-001`, keine Namen, keine IBANs. |
| „Wie lange dauert das?" | Fakten unter einer Sekunde, vollständiges Briefing unter [X] Sekunden. Der Berater liest schon, während der Rest streamt. |
| „Wie viel Zeit spart das wirklich?" | Ehrlich bleiben: Wir haben keine Zeitmessung mit echten Beratern. Was wir sagen können: vier Datenquellen in einem Blick statt vier Systemen. Die Zahl müsste ein Pilot liefern. |

---

## 6. Zahlen für die Slides

Nach dem Batch-Lauf eintragen — leere Platzhalter sind auf der Bühne peinlicher als fehlende Slides.

- Briefings erzeugt: `__ / __`
- Unbelegte Zahlen nach Validierung: `__`
- Durchschnittliche Generierungszeit: `__ s`
- Längste Generierungszeit: `__ s`
- Durchschnittliche Briefing-Länge: `__ Wörter` (Ziel: 150–220)
- Klienten mit Datenlücken, die sauber behandelt wurden: `__`

Aus dem Datensatz, als Beleg dafür, dass wir die Daten wirklich gelesen haben:
47 Klienten · 57 Portfolios · 504 Instrumente · 180 Suitability-Verstösse bei 26 Klienten ·
206 Vorschläge · 153 Beraternotizen · 48'101 Fonds-Look-through-Zeilen.

---

## 7. Demo-Drehbuch

„From Ping to Pitch" wörtlich nehmen. Die Demo beginnt nicht mit einem Klick auf einen Button,
sondern mit einem **eingehenden Anruf**: Popup „\<Klient\> ruft an", das Briefing startet automatisch,
nach wenigen Sekunden steht es. Das ist der *Ping*. Das Briefing ist der *Pitch*.

Reihenfolge nach der Stärke, die jeder Fall zeigt:

1. **Klient mit Liquiditätsbedarf und Präferenz** — das Beispielszenario aus dem Case, eins zu eins.
2. **Klient mit Klumpenrisiko ohne formalen Verstoss** — wir sehen, was keine Regel meldet.
3. **Klient, der Vorschläge grundsätzlich ablehnt** — wir respektieren Präferenzen statt Standardempfehlung.
4. **Live-Upload des unbekannten Testklienten.**

Im Ausblick: In Produktion getriggert per Anruferkennung oder Kalendereintrag — Briefings für
geplante Termine liegen morgens schon bereit.

---

## 8. Was wir nicht behaupten

Drei Stellen, an denen Übertreibung uns mehr kostet als Zurückhaltung. Diese Jury besteht aus
Leuten, die das Produkt bauen — sie erkennen eine überverkaufte Demo sofort.

- **Keine gemessene Zeitersparnis.** Wir haben keine Berater beobachtet. Wir zeigen, was das Briefing
  enthält, und sagen, dass die Zahl aus einem Piloten kommen müsste.
- **Die Performance-Attribution ist eine Näherung.** Keine Positions-Historie im Datensatz.
  Wir kennzeichnen es im UI und sagen es selbst.
- **Keine Anlageberatung.** Das Briefing ist ein internes Vorbereitungsdokument für den Berater,
  kein Dokument für den Endkunden. Das steht so im Case und ist regulatorisch nicht egal.
