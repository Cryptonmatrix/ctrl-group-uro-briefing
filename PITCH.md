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

Gemessen am 19.09.2026 über **alle 47 Klienten**, mit echten Modellaufrufen
(`uv run python -m eval.run_all --briefings --workers 5`).

| | |
|---|---|
| Fact Sheets erzeugt | **47 / 47** |
| Briefings erzeugt | **47 / 47** |
| Befunde insgesamt | 805 (Schnitt 17,1 je Klient) |
| Klienten mit Datenlücken | 10 — sauber behandelt, kein Absturz |
| Engine-Zeit | Schnitt **2,9 ms**, max 10,1 ms |
| Briefing-Zeit | Schnitt **13,4 s**, max 27,4 s |
| Briefing-Länge | Schnitt **209 Wörter**, max 220, keines darüber |
| Unbelegte Zahlen | **5 gefunden und entfernt** |
| Modus | 44× direkt, 3× nach Wiederholung, 0× Fallback |
| Gesamtdauer | 130 s für alle 47 |

**Die wichtigste Zeile richtig formulieren.** „5 unbelegte Zahlen" klingt nach einem
Mangel, ist aber das Gegenteil: Der Validator hat in 47 Briefings fünf Aussagen gefunden,
deren Zahlen nicht durch ein Finding gedeckt waren, und sie **entfernt**. Keine davon hat
den Berater erreicht.

> „Unser Validator prüft jede Zahl gegen das Fact Sheet. Über alle 47 Klienten hat er
> fünf Aussagen verworfen. Was beim Berater ankommt, ist zu hundert Prozent belegt."

**Zur Wiederholung:** Dreimal hat der erste Modellversuch die Prüfung nicht bestanden, das
System hat selbstständig einen zweiten angefordert und der hielt. Das erklärt auch die
27 Sekunden im Maximum.

**Zur Robustheit, ungeplant belegt:** In der Nacht vor dem Pitch ist mitten im Testlauf das
API-Guthaben ausgegangen. Das System hat trotzdem 47 von 47 Briefings ausgeliefert —
regelbasiert, in 0,4 Sekunden, korrekt gekennzeichnet. Kein Berater stand vor einem leeren
Bildschirm. Das ist kein Gedankenexperiment, das ist gemessen.

**Aus dem Datensatz**, als Beleg dafür, dass wir die Daten wirklich gelesen haben:
47 Klienten · 57 Portfolios · 504 Instrumente · 180 Suitability-Verstösse bei 26 Klienten ·
206 Vorschläge · 153 Beraternotizen · 48'101 Fonds-Look-through-Zeilen.

## 7. Demo-Drehbuch

„From Ping to Pitch" wörtlich nehmen. Die Demo beginnt nicht mit einem Klick auf einen Button,
sondern mit einem **eingehenden Anruf**: Popup „\<Klient\> ruft an", das Briefing startet automatisch,
nach wenigen Sekunden steht es. Das ist der *Ping*. Das Briefing ist der *Pitch*.

Reihenfolge nach der Stärke, die jeder Fall zeigt — **aus den Daten verifiziert**:

**1. CASE-003 Ron Burgundy** — der Eröffnungsfall, weil er drei Dinge gleichzeitig zeigt.
73.4% in Lindt & Sprüngli plus 23.6% Sensirion, also 97% in zwei Schweizer Aktien.
Portfoliovolatilität 20.0% gegen ein Profillimit von 12.0%. **Gemeldete Verstösse: null.**
Dazu die Notiz „Plans to retire in the next two years" bei 3.0% Liquidität.
Klumpenrisiko, Limitverletzung und Lebensereignis in einem einzigen Briefing.

**2. CASE-011 Ellen Ripley** — der Hammer, falls wir Zeit für einen zweiten Fall haben.
Volatilität 60.6% gegen ein Limit von 15.0%. Das Vierfache. Gemeldete Verstösse: null.

**3. CASE-012 Company 001 AG** — zeigt, dass wir Notizen gegen Zahlen prüfen.
Notiz: „Needs approximately CHF 15,000 in liquid funds for the Q1 tax payment."
Tatsächlich liquide: CHF 328. Dazu 21 Verstösse, davon 13 Errors — der Health Check hat Material.
**Kontrast dazu CASE-016 Holly Golightly:** dieselbe Notiz, CHF 150'625 liquide, kein Problem.
Dieselbe Notiz, gegensätzliche Bewertung. Das ist die klientenspezifische Storyline.

**4. Live-Upload des unbekannten Testklienten.**

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

---

## 9. Der Befund, der den Pitch tragen sollte

**14 Portfolios im Datensatz reissen das Volatilitätslimit ihres Risikoprofils.
Bei 11 davon meldet die Suitability-Engine der Bank null Verstösse.**

Die Ursache ist systematisch: Diesen Portfolios ist keine Strategie zugewiesen
(`StrategyName: "No strategy"`). Ohne Strategie greifen die SAA-Regeln nicht, also feuert die
Verstoss-Prüfung nie. Das Risiko ist real und exakt messbar — es meldet nur niemand.

Extremfall: **Ellen Ripley, 60.6% Volatilität gegen ein Limit von 15.0%.** Das Vierfache.
Null gemeldete Verstösse.

**Warum das der stärkste Punkt ist:** Es ist kein besseres Briefing über bekannte Probleme.
Es ist ein Problem, das das bestehende System strukturell nicht sieht — gefunden in den Daten,
die der Case-Owner selbst geliefert hat. Das lässt sich in einem Satz sagen und in einer Zeile beweisen.

**Formulierungsvorschlag:**
> „Wir haben Ihren Datensatz durchgerechnet. Elf Ihrer 47 Klienten halten ein Portfolio, das
> ihr eigenes Risikoprofil verletzt — und für keinen davon meldet die Regel-Engine etwas,
> weil keine Strategie hinterlegt ist. Unser System rechnet das unabhängig davon."

**Vorsicht im Ton.** Das ist ein Befund, kein Vorwurf. Sachlich vortragen, nicht triumphierend —
es ist ihr Produkt, und sie haben uns die Daten gegeben. Formulierung als „strukturelle Lücke,
die eine zweite Prüfebene rechtfertigt", nicht als „Ihr System ist kaputt".

---

## 10. Was der Datensatz NICHT hergibt

Geprüft und verworfen, damit niemand Zeit darauf verschwendet oder es auf der Bühne behauptet:

- **ESG-Ausschlusskonflikte sind schwach.** Die Notiz „no fossil fuels" klingt nach einem starken
  Feature, aber nachgerechnet inklusive Fonds-Durchsicht: Mary Poppins hält 0.56% fossile Energie,
  Joker 0.11%, Ron Burgundy 0.00% Rüstung/Tabak. Das als Verstoss zu melden, wirkt alarmistisch.
  Ausschlüsse erst ab ~2% des Vermögens als Finding melden.
- **Keine Positions-Historie.** Performance-Attribution bleibt eine deklarierte Näherung.
- **`PerformanceYTD` existiert nirgends.** Auf allen 57 Portfolios abwesend, wird selbst gerechnet.

---

## 11. UI-Vorgaben aus den Original-Screenshots

Aus `assets/GUI-screenshots/`. Je näher das Mockup daran liegt, desto natürlicher wirkt das Feature
als Teil des Produkts — Kriterium 4 fragt wörtlich, ob das Design „fits naturally into the
URO Advisor Pro environment".

**Layout:** Drei Kopfzeilen. Oben ein durchgehend blaues Band mit dem UNRISKOMEGA-Schriftzug links,
Suche und Benutzermenü rechts. Darunter weiss: Klientenname mit ID links, **Aktionsleiste rechts**.
Darunter ein hellgrauer Streifen mit Metadaten links und dem Gesamtvermögen gross und rechtsbündig.

**Der Button gehört in diese Aktionsleiste.** Dort stehen bereits „Telefonberatung", „Beratermappe",
„Notizen", „Analyse", „Kundeninformation", „Portfolio" — alle als Icon plus Label, klein, grau.
„Generate Briefing" setzt sich links daneben, hervorgehoben. Das ist exakt die Stelle, an der ein
Berater es im echten Produkt erwarten würde.

**Farbsprache — die benutzen wir, statt eine eigene zu erfinden:**

| Element | Bedeutung im Original |
|---|---|
| Rote Kachel (voll ausgefüllt) | Problem, das Aufmerksamkeit braucht — im Screenshot die SAA-Kachel |
| Rotes Kreissymbol | Regelverstoss (Error) |
| Gelbes Warndreieck | Warnung |
| Blau | Normalzustand, Standard-Datenvisualisierung |
| Grün/Türkis | positiver Wert, Zielerreichung |

Unsere Statement-Farben sollten sich daran anlehnen: Risiko rot, Fakt neutral/grau,
Markt blau, Empfehlung grün. House View braucht eine eigene Farbe, die im Original nicht vorkommt —
Violett ist frei.

**Visuelle Sprache:** Weisse Karten auf hellgrauem Hintergrund, dünne Ränder, kaum Rundungen.
Rechts ein Raster kleiner quadratischer Kacheln mit Donut-Charts: Label klein und grau oben links,
Wert gross in der Mitte. Dichte Tabellen, kleine Schrift, serifenlos. Insgesamt sachlich und
informationsdicht — kein Consumer-Look, keine grossen Schatten, keine verspielten Animationen.

**Ein Detail, das Verständnis zeigt:** Das Berater-Dashboard hat vorgefertigte Filter-Tabs —
„01 - Liquidity > 10%", „03 - Last Consultation > 12 Months", „04 - Rule Violations (urgent)",
„05 - Birthdays". Der Berater denkt bereits in diesen Kategorien. Wenn unser Briefing dieselbe
Sprache spricht, fügt es sich ein, statt danebenzustehen.


---

## 12. Sprech-Drehbuch — 6 Minuten plus 1 Minute Fragen

**Aufteilung:** Fünf Folien, eine Demo von drei Minuten — also die Hälfte der Zeit. Das ist
Absicht: Bei einem laufenden Prototyp will die Jury sehen, nicht hören.

| | | | | |
|---|---|---|---|---|
| Titel 0:00 | Problem 0:15 | **Demo 0:50–3:50** | Funktionsweise 3:50 | Beweis 4:35 · Produktion 5:20–6:00 |

Der vollständige Sprechtext mit Begründung je Folie liegt ausserhalb des Repos in
`KONTEXT-was-wir-sagen.md` — darin auch das Kontrastpaar CASE-012 gegen CASE-016, der Beat, für
den die sechste Minute da ist.
Die Jury will sehen, dass es läuft, nicht hören, dass es laufen würde.

**Vorher zwingend:** Server läuft aus `~/dev/uro-briefing`, `.env` geladen, Demo-Klienten
vorgewärmt, Browser auf `localhost:8777`, zweites Fenster mit dem Terminal für den Fall
der Fälle. Seite **nicht** neu laden während des Pitches.

---

### Folie 1 — Titel (0:00–0:15)

Nur Produktname, Team, Case. Kein Text zum Vorlesen.

> „Wir sind [Namen]. Wir haben einen Briefing-Assistenten für Vermögensberater gebaut."

---

### Folie 2 — Das Problem (0:15–0:50)

Auf der Folie: **500 Klienten je Berater · 4 Systeme · 60 Sekunden Vorbereitung**

> „Ein Berater betreut fünfhundert Klienten. Wenn einer unangekündigt anruft, hat er keine
> Stunde Vorbereitung — er hat Sekunden. Die Informationen existieren: Portfolio, CRM,
> Marktnews, die Hausmeinung der Bank. Nur liegen sie in vier verschiedenen Systemen, und
> niemand öffnet vier Systeme, während das Telefon klingelt."

Überleitung, ohne Pause:

> „Wir zeigen es Ihnen direkt."

**Nicht sagen:** „Wir haben ein Tool gebaut, das…" — zeigt, statt anzukündigen.

---

### Demo (0:50–3:10) — der Hauptteil

**Klient 1: Ron Burgundy (CASE-003)** — bereits ausgewählt, Chart sichtbar.

> „Ron Burgundy. Bevor wir irgendetwas erzeugen, sehen Sie schon die Kennzahlen: Vermögen,
> Volatilität gegen das Profillimit, Liquidität. Die Engine rechnet in Millisekunden — der
> Berater sieht nie einen leeren Bildschirm."

Klick auf **Generate Briefing**. Während es lädt:

> „Was jetzt läuft: Kursdaten, News zu den grössten Positionen, die Hausmeinung. Die Chips
> unten leuchten erst, wenn eine Quelle im Briefing tatsächlich belegt ist — nicht nach
> Zeitplan."

Briefing erscheint. **Auf die Headline zeigen:**

> „Zweihundert Wörter, in sechzig Sekunden lesbar. Und jede Aussage trägt ihre Quelle."

**Auf eine Finding-ID zeigen** — das ist der wichtigste Moment des Pitches:

> „Dieses Kürzel ist keine Dekoration. Unsere Analytik hat die Zahl berechnet, das
> Sprachmodell durfte sie nur formulieren. Ein Validator prüft danach jede Zahl im Text
> gegen die Datenbasis und entfernt, was nicht gedeckt ist."

**Auf den Volatilitäts-Befund zeigen** — hier die Formulierung genau einhalten:

> „Zwanzig Prozent Volatilität gegen ein Profillimit von zwölf. Die Bank meldet hier keinen
> Verstoss — völlig zu Recht, denn es ist ein Execution-only-Mandat, und dort findet keine
> Eignungsprüfung statt. Wir zeigen dem Berater trotzdem, was ausserhalb des Prüfumfangs
> liegt. Nicht als Vorwurf, sondern als Verkaufsanlass: Das ist der perfekte Moment, ein
> Beratungsmandat anzubieten."

**Chat** — eine Frage, nicht mehr:

> „Während des Gesprächs kann der Berater nachfragen." — Frage eintippen, Antwort zeigen.
> „Dieselbe Datenbasis wie das Briefing. Der Chat kann dem Briefing nicht widersprechen."

**Protokoll:**

> „Nach dem Gespräch: ein Protokoll zum Ausdrucken, mit den vereinbarten Schritten und
> Feldern für Verantwortlichkeit und Frist."

**Upload — der Moment für die Robustheit:**

> „Und jetzt der Klient, den wir nie gesehen haben."

Datei laden, neuer Klient erscheint oben mit NEU, Briefing erzeugen.

---

### Folie 3 — Wie es funktioniert (3:10–3:50)

Auf der Folie das Pipeline-Diagramm aus `CLAUDE.md` §3.

> „Der Kern ist eine Arbeitsteilung. Eine deterministische Engine berechnet **alle** Zahlen
> und erzeugt typisierte Befunde mit eindeutiger ID. Das Sprachmodell bekommt nur diese
> Befunde — es darf priorisieren, verknüpfen und formulieren, aber nicht rechnen. Danach
> prüft ein Validator jede Zahl gegen die Befunde."

Der Satz, der sitzen muss — langsam:

> **„Unser System kann keine Zahl erfinden, weil es keine Zahl selbst rechnet."**

Wenn Zeit bleibt, die Auswahlformel in einem Satz:

> „Welche Befunde es ins Briefing schaffen, entscheidet eine Formel: Schweregrad mal
> betroffener Betrag mal Kundenrelevanz mal Aktualität. Top drei bis fünf, der Rest bleibt
> im Chat abrufbar."

---

### Folie 4 — Der Beweis (3:50–4:30)

Auf der Folie nur diese Zahlen, gross:

| | |
|---|---|
| Briefings erzeugt | **47 / 47** |
| Unbelegte Zahlen | **5 gefunden und entfernt** |
| Durchschnitt | **13,4 s · 209 Wörter** |

> „Wir haben das nicht an einem geprobten Demo-Fall gemessen, sondern an allen
> siebenundvierzig Klienten des Datensatzes. Siebenundvierzig Briefings, im Schnitt
> dreizehn Sekunden, zweihundertneun Wörter. Der Validator hat fünf Aussagen verworfen,
> deren Zahlen nicht gedeckt waren. **Was beim Berater ankommt, ist zu hundert Prozent
> belegt.**"

Und der ungeplante Robustheitsbeweis — der wirkt, weil er echt ist:

> „Heute Nacht ist uns mitten im Testlauf das API-Guthaben ausgegangen. Das System hat
> trotzdem siebenundvierzig von siebenundvierzig Briefings ausgeliefert — regelbasiert, in
> vier Zehntelsekunden, und in der Oberfläche als solche gekennzeichnet. Kein Berater steht
> vor einem leeren Bildschirm."

---

### Folie 5 — Produktionsweg (4:30–5:00)

Links **Mock**, rechts **Produktion** — die Tabelle aus §3 dieser Datei.

> „Was heute Mock ist und was in Produktion daran kommt, haben wir sauber getrennt: Statt
> der Flat Files die URO-API, statt Yahoo Finance ein lizenzierter Feed, statt unseres
> kodierten CIO-Ausblicks Ihre eigene Hausmeinung aus dem CIO-Prozess. Die Architektur ist
> darauf ausgelegt — die Analytik kennt kein Netz, das Sprachmodell nur eine Schicht."

Abschluss, direkt:

> „Wir würden das gern mit fünf bis zehn Beratern pilotieren und messen, was es an
> Vorbereitungszeit spart. Danke."

**Nicht** mit „Habt ihr Fragen?" enden — das gibt die Bühne ab. Mit dem Pilot-Angebot enden
und schweigen.

---

### Wenn die Zeit knapp wird

In dieser Reihenfolge streichen: die Auswahlformel auf Folie 3, das Protokoll in der Demo,
den Chat in der Demo. **Niemals streichen:** die Finding-ID, den Volatilitäts-Befund und
den Upload — das sind die drei Momente, die euch von den anderen Teams unterscheiden.

### Rollenverteilung

Einer redet, einer bedient. Nicht wechseln. Wer bedient, sagt nichts — zwei Stimmen in
fünf Minuten wirken unruhig. Der Bedienende hat das zweite Terminalfenster offen und
startet im Notfall neu, ohne dass der Redende stoppt.
