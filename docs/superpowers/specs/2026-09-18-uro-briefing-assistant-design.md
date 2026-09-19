# URO Briefing Assistant — Design-Spezifikation

> **Zweck dieses Dokuments:** Vollständige, eigenständige Bauanleitung für den Hackathon-Prototyp „From Ping to Pitch“ (START Hack, Challenge von UnRiskOmega AG). Ein Coding-Agent (z. B. Claude Code in einem neuen Chat) soll das Projekt allein anhand dieses Dokuments 1:1 umsetzen können.
>
> **Stand:** 2026-09-18 · **Team:** 3 Personen · **Budget:** ca. 10 Stunden Arbeitszeit
>
> **Status der Abschnitte:**
> - Abschnitte 1–5 (Aufgabe, Entscheidungen, Daten, Architektur, Analyse-Engine) → **mit dem Team besprochen und freigegeben**
> - Abschnitt 6 (Marktdaten/News/House View) → Grundentscheidungen besprochen (live yfinance, House View als JSON), Details sind Vorschlag
> - Abschnitte 7–11 (LLM/Validator, Chat, Frontend, API, Fehlerbehandlung) sowie 12–18 (Struktur, Setup, Tests, Zeitplan, Regeln, Scope, Pitch) → **Vorschlag, noch nicht gemeinsam reviewt** — beim Lesen kritisch prüfen
>
> **Sprachregel:** Dieses Dokument ist auf Deutsch. **Code, Kommentare, Bezeichner, UI-Texte und LLM-Ausgaben sind auf Englisch.**

---

## Inhaltsverzeichnis

1. [Die Aufgabe in Kürze](#1-die-aufgabe-in-kürze)
2. [Getroffene Entscheidungen](#2-getroffene-entscheidungen)
3. [Die Daten (was wir wirklich haben)](#3-die-daten-was-wir-wirklich-haben)
4. [Architektur & Datenfluss](#4-architektur--datenfluss)
5. [Analyse-Engine (Detektoren + Priorisierung)](#5-analyse-engine)
6. [Externe Quellen: Marktdaten, News, House View](#6-externe-quellen-marktdaten-news-house-view)
7. [LLM-Schicht: Briefing-Generierung & Validierung](#7-llm-schicht-briefing-generierung--validierung)
8. [Follow-up-Chat (Bonus)](#8-follow-up-chat-bonus)
9. [Frontend (URO Advisor Pro Mock)](#9-frontend-uro-advisor-pro-mock)
10. [API-Vertrag](#10-api-vertrag)
11. [Fehlerbehandlung & fehlende Daten](#11-fehlerbehandlung--fehlende-daten)
12. [Projektstruktur (Dateibaum)](#12-projektstruktur-dateibaum)
13. [Tech-Stack & Setup](#13-tech-stack--setup)
14. [Testing & Qualitätssicherung](#14-testing--qualitätssicherung)
15. [Arbeitsteilung & Zeitplan (10 h)](#15-arbeitsteilung--zeitplan-10-h)
16. [Coding-Regeln für Agentic Coding](#16-coding-regeln-für-agentic-coding)
17. [Scope: Was wir NICHT bauen](#17-scope-was-wir-nicht-bauen)
18. [Präsentation & Demo](#18-präsentation--demo)
19. [Offene Punkte (🔍 im Spike klären)](#19-offene-punkte--im-spike-klären)
20. [Anhang A: CLAUDE.md-Vorlage](#anhang-a-claudemd-vorlage)
21. [Anhang B: Glossar Finanzbegriffe](#anhang-b-glossar-finanzbegriffe)

---

## 1. Die Aufgabe in Kürze

**Challenge:** Einen funktionierenden Prototyp eines KI-gestützten **Briefing-Assistenten für Wealth Manager** bauen, eingebettet in eine nachgebaute Oberfläche von **URO Advisor Pro** (UnRiskOmegas Beratungssoftware).

**User Story:** Ein Kundenberater bekommt einen spontanen Anruf oder hat gleich ein Meeting. Er öffnet den Kunden in URO Advisor Pro, klickt **„Generate Briefing“** und erhält innerhalb weniger Sekunden ein Briefing, das er in **ca. 60 Sekunden** lesen kann und das vier Fragen beantwortet:

| # | Frage | Inhalt |
|---|---|---|
| 1 | **What happened?** | Portfolio-Entwicklung und ihre Haupttreiber |
| 2 | **What is the current situation?** | Allokationsabweichungen, Risiken, Suitability-/Regelverstöße, Konzentrationen, offene Proposals |
| 3 | **What could happen next?** | Verknüpfung mit Marktnews und der House View (CIO-Sicht) der Bank |
| 4 | **What should the advisor do?** | Konkrete Next Best Actions, belegt mit Daten |

**Datenquellen, die kombiniert werden müssen:**
1. Kunden-, Portfolio- und Positionsdaten (Mock-Daten als JSON, von UnRiskOmega)
2. CRM-Kontext (Notizen, Tags, Profil — ebenfalls in den JSON-Daten)
3. Aktuelle Finanzmarkt-News (wir: Yahoo Finance via `yfinance`)
4. House View / CIO-Sicht einer Bank (wir: selbst erstellte JSON aus einem öffentlichen CIO-Report)

**Kritische Rahmenbedingung:** Kurz vor dem Pitch erhalten wir **neue, unbekannte Kundendaten** (laut README drei zusätzliche Dateien). Der Prototyp muss per **Upload** neue Daten aufnehmen und daraus ein sinnvolles Briefing erzeugen. **Nichts darf auf einen bestimmten Demo-Kunden hartcodiert sein.**

**Bewertung (100 %):**

| Kategorie | Gewicht | Worauf wir achten |
|---|---|---|
| Problem Fit & Business Value | 25 % | 60-Sekunden-Fokus, kohärente Storyline, konkrete Actions |
| Implementation Quality & Robustness | 25 % | End-to-end stabil, neuer Kunde klappt, fehlende Daten sauber behandelt, modular, schnell |
| AI Quality, Relevance & Grounding | 20 % | Keine Halluzinationen, Fakten vs. Interpretation vs. Aktion unterscheidbar, Ranking erklärbar |
| User Experience | 15 % | Ein Klick, scanbar, Risiken/Actions visuell unterscheidbar, URO-Look |
| Bonus & Creativity | 15 % | Wir machen: **Follow-up-Chat** |

**Datenrepository:** https://github.com/START-Hack/unriskomega-2026

---

## 2. Getroffene Entscheidungen

Diese Entscheidungen wurden mit dem Team getroffen und sind **nicht** neu zu diskutieren:

| Thema | Entscheidung | Begründung |
|---|---|---|
| Zeitbudget | ~10 h Arbeitszeit, 3 Personen | → strikte Scope-Disziplin |
| Backend | **Python + FastAPI** | Team kann Python am besten |
| Frontend | **React + TypeScript + Tailwind (Vite)** | URO-Look glaubwürdig nachbauen |
| Bonus | **Nur Follow-up-Chat** | Nutzt denselben Datenkontext, günstig, starke Demo |
| Marktnews | **Live über `yfinance`**, kein Datei-Cache | Echtheit; bei Ausfall: Briefing ohne News + Hinweis |
| KI-Architektur | **Ansatz A: „Deterministisch rechnen, LLM erzählt“** | Grounding, Robustheit, Erklärbarkeit |
| LLM-Anbieter | **Anthropic Claude** (API-Key wird organisiert) | — |
| House View | Handgepflegte `house_view.json` aus öffentlichem CIO-Report | Kein freier API-Zugang zu CIO-Views |
| Sprache | UI, Briefing, Code: **Englisch** | Aufgabe & Daten sind englisch |
| Speicher | **In-Memory**, keine Datenbank | Hackathon-Scope |

### Das Kernprinzip von Ansatz A (unbedingt verstehen)

```
┌────────────────────────────────────────────────────────────────────┐
│  PYTHON rechnet ALLE Zahlen, erkennt ALLE Probleme, priorisiert.   │
│  Ergebnis: eine Liste von "Facts" mit IDs (F1, F2, N1, H1, C1 …).  │
│                                                                    │
│  CLAUDE bekommt NUR diese Facts und schreibt daraus die Storyline. │
│  Jede Aussage MUSS auf Fact-IDs verweisen.                         │
│                                                                    │
│  Ein VALIDATOR prüft: existieren die IDs? stammen die Zahlen       │
│  aus den Facts? → sonst Retry → sonst Template-Fallback.           │
└────────────────────────────────────────────────────────────────────┘
```

Das LLM **rechnet nie**, **erkennt keine Verstöße selbst** und **erfindet keine Wertpapiere**. Es verknüpft und formuliert.

---

## 3. Die Daten (was wir wirklich haben)

Quelle: `core-case/portfolio-data/` im Repo (`clients.json`, `reference.json`, `DATA.md`). Die folgende Beschreibung stammt aus `DATA.md`. **Genaue Feldnamen müssen beim Spike (Schritt 0) gegen die echten Dateien geprüft werden** — siehe [Abschnitt 19](#19-offene-punkte--im-spike-klären).

### 3.1 Wichtige Konventionen aus dem README (Stolperfallen!)

| Regel | Konsequenz im Code |
|---|---|
| Fehlende Felder werden **weggelassen**, nicht `null` gesetzt | Immer `.get("Field")` bzw. Pydantic-Felder `Optional[...] = None` |
| Joins immer über **`SecurityId`**, nicht ISIN (gleiche ISIN existiert pro Währung mehrfach) | Index `securities_by_id`; ISIN nur als Fallback-Index |
| Prozente sind **Brüche 0–1** … | intern überall 0–1 |
| … **außer** `FundUnbundlingMappings.Weight` → **0–100** | Beim Laden **einmal** durch 100 teilen, an genau einer Stelle |
| Für Allokationsvergleiche **`SAA_*`-Felder** der Securities verwenden | nicht `Assetclass` (hat ~200 Werte) |
| Datumswerte sind um einen **konstanten Offset in die Zukunft verschoben** | Datenzeit ≠ Realzeit! Siehe 5.3 |
| Kontowährungen können **Krypto-Ticker** sein (`BTC`, `ETH`, `SOL`, …) | Nicht als ISO-Währung behandeln; als eigene Kategorie „Crypto“ |

### 3.2 `clients.json` — Array von 47 Kunden

| Bereich | Felder |
|---|---|
| Identität | `ClientId`, `ClientRef`, `FirstName`, `LastName`, `Company`, `IsClientACompany`, `IsEmployee` |
| Profil | `RegulatoryClientTypeId`/`Name`, `RiskProfileId`/`RiskProfileName`, `EsgProfileId`/`EsgProfileName`, `Birthday`, `ProfilingDateUtc` |
| Finanzen | `ReportingCurrency`, `AssetsUnderManagementInDefaultCurrency`, `LiquidityInDefaultCurrency` |
| Collections | `Portfolios[]`, `Proposals[]`, `Transactions[]`, `SuitabilityViolations[]`, `IndividualRuleOverrides[]`, `Tags[]`, `ClientNotes[]` |

**`Portfolios[]`** enthält u. a. Positionen und `PerformanceHistory[]` = `[{ "Date": "yyyy-MM-01", "Value": <NAV> }, …]` (monatlich, ca. 5 Jahre). 🔍 Genaue Positionsfelder (Menge, Marktwert, Währung, SecurityId, Valor, Isin) im Spike prüfen. 🔍 Wie ist einem Portfolio die SAA/Strategie zugeordnet?

**`SuitabilityViolations[]`** (nur aktive Verstöße):
`Id`, `RuleCode` (→ `reference.SuitabilityRules[].RuleCode`), `RuleDescription` (Originalsprache DE/FR), `ErrorLevel` (1 = Warning, sonst Error), `Severity` (`"Warning"`/`"Error"`), `PortfolioId`, `LastViolatedDateUTC`, `SecurityIsin` (fehlt, wenn nicht titelspezifisch), `ViolationPath` (optional): `[{ "FieldName", "LeftValue", "RightValue", "Operator" }, …]`

**`IndividualRuleOverrides[]`**: `RuleCode`, `RuleDescription` → Regeln, die für diesen Kunden bewusst deaktiviert sind.

**`Proposals[]`**: `ProposalId`, `PublicGuid`, `PortfolioId`, `ProposalStatusId`/`ProposalStatusName`, `AdvisoryTypeId`/`AdvisoryTypeName`, `Currency`, `StrategicAssetAllocationId`, `ProposedDateUTC`, `FinalizedDateUTC` (optional), `TransactionsSubmittedDateUTC` (optional), `Reason`, `Notes`, `ExpectedReturn`, `Volatility`, `ValueAtRisk`, `SecurityPositions[]` (`Isin`, `SecurityName`, `Quantity`, `PricePerUnit`, `Currency`, `TotalAmountInProposalCurrency`, `ProposalValuePercentage`), `AccountPositions[]`, `Contracts[]`, `StandingOrders[]`

**`ClientNotes[]`**: `Note` (Freitext **Deutsch oder Französisch**), `CreatedByDateUTC`

**`Tags[]`**: `TagName`, `TagTypeName` (`"Region"`/`"Industry"`), `Scope` (immer `"Client"`)

**⚠️ Es gibt KEINE Tasks/To-dos in den Daten.** Offene Punkte werden aus Proposals und Profildaten abgeleitet (siehe 5.10).

### 3.3 `reference.json` — Lookup-Collections

`Securities[]`, `FundUnbundlingMappings[]`, `SuitabilityRules[]`, `RiskProfiles[]`, `EsgProfiles[]`, `InvestmentServices[]`, `Strategies[]`, `StrategicAssetAllocations[]`, `Tags[]`, `RecommendationLists[]`, `ProposalStatuses[]`, `AdvisoryTypes[]`

**`Securities[]`** (Stammdaten):
`SecurityId`, `Isin`, `Valor`, `SecurityTypeId`/`SecurityTypeName` („Shares“, „Investment fund“, „Bond“ …), `Assetclass`/`AssetClassName`, `Industry`/`IndustryName`, `CountryId`/`CountryName`, `CurrencyGroupName`, `CountryGroupName`, **`SAA_AssetClassName`, `SAA_CurrencyGroupName`, `SAA_CountryGroupName`, `SAA_IndustryName`**, `IsMoneyMarket`, `IsTreasury`, `EndOfDayPrice`, `PriceDateUtc`, `Volatility`, `ExpectedReturn`, `SustainabilityRatingId`, `SustainabilityScore`, `IsUnbundlingEnabled`, `MaturityDateUtc`, `PRC` (Produktrisikoklasse), `YieldToMaturity`, `SecurityInvestRatingId`/`Name` (optional), `InRecommendationList`, `ProductClassId`/`ProductClassName`

**⚠️ Keine Ticker-Symbole** — nur `SecurityId`, `Isin`, `Valor`. → ISIN→Yahoo-Ticker-Auflösung nötig (siehe 6.1).
**⚠️ Nur EIN aktueller Preis pro Wertpapier** (`EndOfDayPrice`) — keine Kurshistorie. → Positions-Performance über `yfinance` (siehe 5.3).

**`StrategicAssetAllocations[]`**: `Id`, `Name`, `Description`, `InvestmentServiceId`, `StrategyId`, `ReferenceCurrency`, `Mappings[]` mit `Dimension` (`"AssetClass"` | `"CurrencyGroup"` | `"CountryGroup"` | `"Industry"`), `Category`, `MinPercentage`, `TargetPercentage`, `MaxPercentage` (0–1)

**`EsgProfiles[]`**: `Id`, `Name` (`"Yes"`/`"No"`), `Level`, `ProfileType`, `MinimumLevel`, `MaximumLevel`, `MinimumPositionLevel`

**`FundUnbundlingMappings[]`**: Fonds-Durchschau; `Weight` in **0–100**. 🔍 Genaue Felder (Fonds-SecurityId, Dimension/Kategorie?) prüfen.

**`Tags[]`**: 17 Tags (6 Regionen + 11 Industrien).

### 3.4 Weitere Assets im Repo

- `assets/logos/uro-light.svg`, `uro-dark.svg`, `partners-light.png`, `partners-dark.png`
- `core-case/GUI-screenshots/` → Vorlage für den URO-Look (Farben, Layout, Typografie)
- `side-challenge/` → PDF-Reports für Ex-Custody-Bonus (**wir bauen das nicht**)

---

## 4. Architektur & Datenfluss

### 4.1 Überblick

```
React (Vite + TS + Tailwind)                   FastAPI (Python 3.12)
┌──────────────────────────────┐              ┌──────────────────────────────────────────┐
│ ClientListPage  (+ Upload)   │──GET/POST───▶│ api/        Routen, keine Logik          │
│ ClientDetailPage (URO-Look)  │              │ data/       Laden, Validieren, Indizes   │
│   [Generate Briefing]        │──POST───────▶│ analytics/  Positionstabelle, Detektoren,│
│ BriefingPanel                │◀──JSON───────│             Ranking  (PURE, kein I/O)    │
│ ChatPanel                    │──POST───────▶│ market/     yfinance: Ticker, Kurse, News│
└──────────────────────────────┘              │ houseview/  house_view.json laden+matchen│
                                              │ llm/        Prompts, Claude-Calls,       │
                                              │             Validator, Fallback, Chat    │
                                              │ services/   Orchestrierung (Pipeline)    │
                                              └──────────────────────────────────────────┘
                                                        │ In-Memory DataStore
                                                        ▼
                                              data/clients.json, reference.json,
                                              data/house_view.json, data/sector_proxies.json
```

### 4.2 Pipeline beim Klick auf „Generate Briefing“ (Ziel: < 15 s gesamt)

```
POST /api/clients/{id}/briefing
  │
  ├─ 1. DataStore.get_client(id)                        (~0 ms)
  ├─ 2. analytics.build_position_table(client, ref)     (~10 ms)
  ├─ 3. market.resolve_tickers(top_positions)  ┐
  │     market.fetch_price_history(tickers)    ├─ parallel, Budget 8 s, jeder Call Timeout 5 s
  │     market.fetch_news(tickers, sectors)    ┘
  ├─ 4. analytics.run_detectors(ctx)  → list[Fact]      (~50 ms)
  ├─ 5. houseview.compare(ctx)        → list[Fact] (H*)
  ├─ 6. analytics.rank(facts, ctx)    → FactBundle (top 12 + rest)
  ├─ 7. llm.generate_briefing(bundle) → BriefingDraft   (~5–10 s, 1 Call)
  ├─ 8. llm.validate(draft, bundle)   → ok | Fehler → 1 Retry → sonst Fallback
  └─ 9. Response: Briefing (+ alle Facts, News, Coverage, Timings)
```

Das Ergebnis wird im `BriefingCache` (In-Memory, Key = client_id) abgelegt, damit der Chat denselben Kontext nutzen kann.

### 4.3 Schichten-Regeln (Abhängigkeitsrichtung)

```
api  →  services  →  analytics, market, houseview, llm  →  models, data
```

- `analytics/` ist **pure**: bekommt Daten rein, gibt Facts raus. **Kein** Netzwerk, **kein** Dateizugriff, **kein** LLM. → trivial testbar.
- `market/` ist die **einzige** Stelle mit `yfinance`.
- `llm/` ist die **einzige** Stelle mit dem Anthropic-SDK.
- `data/` ist die **einzige** Stelle, die JSON-Dateien liest.
- `api/` enthält **keine** Geschäftslogik, nur Request/Response-Mapping.

---

## 5. Analyse-Engine

### 5.1 Das zentrale Datenobjekt: `Fact`

```python
# backend/app/models/facts.py
from enum import StrEnum
from pydantic import BaseModel, Field

class FactCategory(StrEnum):
    PERFORMANCE = "performance"
    MARKET_COMPARISON = "market_comparison"
    SAA_DEVIATION = "saa_deviation"
    VIOLATION = "violation"
    ESG = "esg"
    CONCENTRATION = "concentration"
    RISK = "risk"
    LIQUIDITY = "liquidity"
    PROPOSAL = "proposal"
    OPEN_ITEM = "open_item"          # abgeleitete "Tasks"
    CLIENT_PROFILE = "client_profile"
    CLIENT_NOTE = "client_note"      # IDs C1..Cn
    NEWS = "news"                    # IDs N1..Nn
    HOUSE_VIEW = "house_view"        # IDs H1..Hn

class Polarity(StrEnum):
    NEGATIVE = "negative"   # Problem / Risiko
    POSITIVE = "positive"   # gute Nachricht
    NEUTRAL = "neutral"     # Info / Kontext
    OPPORTUNITY = "opportunity"

class Fact(BaseModel):
    id: str                          # "F1", "N2", "H1", "C3" — wird vom Ranking vergeben
    category: FactCategory
    polarity: Polarity
    base_severity: float             # 0..1, fest je Typ (Tabelle 5.13)
    magnitude: float = 1.0           # 0..1, Größenfaktor
    boost: float = 1.0               # Kunden-Boost-Multiplikator
    score: float = 0.0               # base_severity * magnitude * boost
    text: str                        # 1 Satz, Englisch, enthält die Kernzahlen
    data: dict = Field(default_factory=dict)   # Rohzahlen für UI/Chat
    source: str                      # z.B. "clients.json › SuitabilityViolations[3]"
    related_security_ids: list[int] = Field(default_factory=list)
    related_fact_ids: list[str] = Field(default_factory=list)
    boost_reasons: list[str] = Field(default_factory=list)  # für Transparenz im UI
```

**ID-Präfixe:**

| Präfix | Herkunft |
|---|---|
| `F` | Portfolio-/Kundenfakten aus Detektoren |
| `N` | News-Artikel |
| `H` | House-View-Abgleiche |
| `C` | Kundennotizen (wörtlich) |

**Regel für `text`:** Enthält bereits alle Zahlen, die das LLM verwenden darf, **formatiert** (z. B. `"-4.2%"`, `"+16.0 pp"`, `"CHF 160,000"`). Das LLM soll Zahlen **wörtlich übernehmen** — das macht die Validierung einfach.

**Zahlenformatierung (zentral in `app/analytics/format.py`):**
- Prozent: 1 Nachkommastelle, mit Vorzeichen bei Veränderungen: `+3.1%`, `-4.2%`, Gewichte ohne Vorzeichen: `9.5%`
- Prozentpunkte: `+16.0 pp`
- Beträge: Währung + Tausendertrennzeichen, gerundet auf 1000: `CHF 160,000`
- Datumsangaben: `12 Jun 2026`

### 5.2 Schritt 0: Vorbereitung — `AnalysisContext`

```python
# backend/app/analytics/context.py
@dataclass
class AnalysisContext:
    client: Client                       # Pydantic-Modell
    ref: ReferenceIndex                  # Indizes über reference.json
    positions: pd.DataFrame              # Positionstabelle (siehe unten), über ALLE Portfolios
    total_value: float                   # Summe Marktwerte in ReportingCurrency
    reporting_currency: str
    data_as_of: date                     # letztes Datum in PerformanceHistory (Datenzeit!)
    last_interaction: date | None        # jüngstes Datum aus Notes/Proposals
    market: MarketSnapshot | None        # Kurse/News von yfinance (None wenn offline)
    house_view: HouseView | None
    config: AnalysisConfig               # Schwellenwerte
```

**a) Referenz-Indizes** (`app/data/reference_index.py`):
```python
securities_by_id: dict[int, Security]
securities_by_isin: dict[str, list[Security]]    # Fallback
rules_by_code: dict[str, SuitabilityRule]
saa_by_id: dict[int, StrategicAssetAllocation]
esg_profiles_by_id: dict[int, EsgProfile]
risk_profiles_by_id: dict[int, RiskProfile]
unbundling_by_fund_id: dict[int, list[FundUnbundlingRow]]   # Weight bereits /100 !
recommended_security_ids: set[int]
```

**b) Positionstabelle** (`app/analytics/positions.py`): Ein pandas-DataFrame mit einer Zeile pro Position über **alle Portfolios** des Kunden:

| Spalte | Quelle | Bemerkung |
|---|---|---|
| `portfolio_id` | Portfolio | |
| `security_id` | Position | Join-Key |
| `isin`, `valor`, `name` | Security | |
| `security_type` | `SecurityTypeName` | |
| `market_value` | Position (🔍) | in `ReportingCurrency`; falls nicht vorhanden: `Quantity × EndOfDayPrice` (+ FX 🔍) |
| `weight` | berechnet | `market_value / total_value` (0–1) |
| `saa_asset_class`, `saa_currency_group`, `saa_country_group`, `saa_industry` | `SAA_*` | für SAA-Vergleich |
| `industry`, `country`, `currency` | Security | für Konzentration |
| `volatility`, `expected_return`, `prc` | Security | |
| `sustainability_score` | Security | |
| `maturity_date`, `ytm` | Security | nur Anleihen |
| `is_fund_unbundlable` | `IsUnbundlingEnabled` | |
| `in_recommendation_list` | Security | |
| `ticker` | später von `market/` gefüllt | `None` wenn nicht auflösbar |

Liquidität (Cash) kommt als **synthetische Position** mit `saa_asset_class = <Liquiditäts-Kategorie der SAA>` hinzu (Wert: `LiquidityInDefaultCurrency` bzw. Kontopositionen 🔍). Krypto-Kontopositionen erhalten `saa_asset_class = "Crypto"` (bzw. Alternative 🔍).

**Mehrere Portfolios:** Das Briefing betrachtet den **Kunden als Ganzes** (Gewichte relativ zum Gesamtvermögen). SAA-Abweichungen werden **pro Portfolio** geprüft (jedes Portfolio hat ggf. eigene SAA), im Fact wird das Portfolio genannt, wenn der Kunde > 1 Portfolio hat.

**c) Datenzeit vs. Realzeit (wichtig!):** Die Daten-Daten sind in die Zukunft verschoben. Deshalb:
- `data_as_of` = letztes `Date` der `PerformanceHistory` → Bezugspunkt für **Datenanalysen** (Portfolio-Rendite, Proposal-Alter, Notiz-Alter, Fälligkeiten, Profilalter).
- Marktdaten (`yfinance`) laufen auf **echter Zeit** (`period="3mo"` bis heute).
- Im UI/Briefing klar trennen: „Portfolio (data as of …)“ vs. „Market (live, last 3 months)“.

**d) Letzte Interaktion:** `last_interaction = max(ClientNotes[].CreatedByDateUTC, Proposals[].ProposedDateUTC)` (falls vorhanden).

### 5.3 Detektor-Schnittstelle

Jeder Detektor ist eine **pure Funktion** in einer eigenen Datei:

```python
# backend/app/analytics/detectors/base.py
from typing import Protocol

class Detector(Protocol):
    name: str
    def __call__(self, ctx: AnalysisContext) -> list[Fact]: ...

# backend/app/analytics/detectors/__init__.py
DETECTORS: list[Detector] = [
    detect_performance,
    detect_market_comparison,
    detect_saa_deviation,
    detect_violations,
    detect_esg,
    detect_concentration,
    detect_risk,
    detect_liquidity,
    detect_proposals,
    detect_open_items,
    detect_client_profile,
]
```

```python
# backend/app/analytics/engine.py
def run_detectors(ctx: AnalysisContext) -> DetectorRun:
    facts: list[Fact] = []
    coverage: dict[str, str] = {}      # detector name -> "ok" | "no_data" | "error: <msg>"
    for det in DETECTORS:
        try:
            result = det(ctx)
            facts.extend(result)
            coverage[det.name] = "ok" if result else "no_data"
        except Exception as exc:        # ein Detektor darf nie die Pipeline killen
            logger.exception("Detector %s failed", det.name)
            coverage[det.name] = f"error: {exc.__class__.__name__}"
    return DetectorRun(facts=facts, coverage=coverage)
```

Detektoren vergeben **keine** IDs (`id=""`), das macht das Ranking am Ende (stabile Nummerierung F1, F2, … nach Score).

### 5.4 Detektor 1 — `performance` („What happened?“)

**Teil A: Portfolio-Rendite** (aus `PerformanceHistory`, Datenzeit)
- Summiere die `Value`-Reihen aller Portfolios je `Date` (nur Daten, die in allen Reihen existieren; sonst pro Portfolio separat).
- Berechne: `ret_3m`, `ret_12m`, `ret_ytd`, `ret_since_last_interaction` (nächster Monatswert ≤ `last_interaction`).
- Formel: `ret = value_now / value_then - 1`
- **Fact:** `"Portfolio -4.2% over 3 months (data as of 01 Sep 2026); +6.1% over 12 months."`
- `polarity`: negativ wenn `ret_3m < -2%`, positiv wenn `> +2%`, sonst neutral.
- `magnitude = min(1, abs(ret_3m) / 0.05)`
- Hinweis im `data`: `"includes_flows": True` (Ein-/Auszahlungen sind nicht bereinigt — im UI als Fußnote).

**Teil B: Positions-Treiber** (aus yfinance, Realzeit)
- Nur Positionen mit `ticker` und Kurshistorie.
- `pos_ret_3m = close_last / close_first - 1`
- `contribution = weight × pos_ret_3m` (Näherung mit **aktuellem** Gewicht → im Text mit „≈“)
- Top-3 negative und Top-3 positive Beiträge (nur wenn `abs(contribution) >= 0.3 pp`).
- **Fact je Treiber:** `"ASML Holding (9.5% weight) -30.0% in 3 months → ≈ -2.9 pp contribution."`
- Zusätzlich 1 Coverage-Fact, wenn > 20 % des Vermögens ohne Kursdaten: `"Price history unavailable for 28% of the portfolio (mainly funds/bonds); driver analysis covers 72%."` (polarity neutral, niedrige Severity)
- `related_security_ids` setzen (wichtig für Boosts).

### 5.5 Detektor 2 — `market_comparison` („isolated or market-wide?“)

- Für jeden **negativen** Top-Treiber aus Detektor 1B:
  - Sektor-Proxy aus `data/sector_proxies.json` über `SAA_IndustryName`/`IndustryName` → z. B. `"Semiconductors" → "SOXX"`.
  - Markt-Proxy nach Wertpapierwährung: `{"CHF": "^SSMI", "USD": "^GSPC", "EUR": "^STOXX50E", "GBP": "^FTSE", default: "URTH"}`.
  - Renditen 3M von Sektor- und Markt-Proxy (yfinance).
- Klassifikation:
  - `sector_ret <= -5%` **und** `market_ret > -3%` → **sector-wide**
  - `market_ret <= -5%` → **market-wide**
  - sonst, wenn `pos_ret - sector_ret <= -10 pp` → **stock-specific**
  - sonst → **mixed**
- **Fact:** `"ASML decline is sector-wide: semiconductor ETF SOXX -22.0%, S&P 500 +1.0% (3 months)."`
- `related_fact_ids` = ID des Treiber-Facts (wird nach dem Ranking aufgelöst; intern über Objektreferenz).

`data/sector_proxies.json` (Beispiel; an echte `IndustryName`-Werte aus den Daten anpassen 🔍):
```json
{
  "Semiconductors": "SOXX",
  "Information Technology": "XLK",
  "Technology": "XLK",
  "Health Care": "XLV",
  "Pharmaceuticals": "IHE",
  "Financials": "XLF",
  "Banks": "KBE",
  "Energy": "XLE",
  "Consumer Staples": "XLP",
  "Consumer Discretionary": "XLY",
  "Industrials": "XLI",
  "Materials": "XLB",
  "Utilities": "XLU",
  "Real Estate": "XLRE",
  "Communication Services": "XLC"
}
```

### 5.6 Detektor 3 — `saa_deviation` („Is the portfolio positioned as agreed?“)

- SAA des Portfolios ermitteln (🔍 Verknüpfung; Reihenfolge der Versuche: Feld am Portfolio → `StrategicAssetAllocationId` des jüngsten Proposals für dieses Portfolio → überspringen).
- Für jede `Dimension` ∈ {AssetClass, CurrencyGroup, CountryGroup, Industry}:
  - `actual = positions[positions.portfolio_id == pid].groupby(<saa_col>)["weight_in_portfolio"].sum()`
  - Für jede `Mapping`-Zeile: vergleiche `actual[Category]` (0 wenn fehlt) mit `Min/Target/Max`.
- **Nur** Zeilen mit `actual < Min` oder `actual > Max` → Fact.
- `deviation_pp = (actual - target) * 100`
- `magnitude = min(1, abs(deviation_pp) / 15)`
- `base_severity`: AssetClass 0.80, andere Dimensionen 0.60.
- Rebalancing-Betrag: `amount = abs(actual - target) * portfolio_value`
- **Fact:** `"Equities 66.0% vs SAA target 50.0% (max 60.0%): +16.0 pp over target, ≈ CHF 160,000 above target."`
- `data`: `{dimension, category, actual, min, target, max, deviation_pp, amount, portfolio_id}`
- **Zusätzlich** (für das UI-Chart, nicht als Fact): die komplette Ist-vs-Ziel-Tabelle der Dimension `AssetClass` in `BriefingResponse.allocation` (siehe 10).

### 5.7 Detektor 4 — `violations` (Compliance)

- Quelle: `client.SuitabilityViolations[]` (bereits von URO berechnet — **wir erkennen nichts selbst**).
- Filter: `RuleCode` in `IndividualRuleOverrides[].RuleCode` → ignorieren.
- Anreichern:
  - Regel: `ref.rules_by_code[RuleCode]` (Name/Beschreibung)
  - Wertpapier: `SecurityIsin` → `securities_by_isin` → Name (erste Übereinstimmung; im Portfolio vorhandene bevorzugen)
  - `ViolationPath`: jedes Element → `"<FieldName> <LeftValue> <Operator> <RightValue>"`; Brüche als Prozent formatieren, wenn `FieldName` nach Gewicht/Anteil aussieht (🔍).
- `base_severity`: `Severity == "Error"` → 1.00, sonst 0.75. `magnitude = 1`.
- **Fact:** `"Suitability ERROR – max single-position weight: ASML Holding 14.0% (limit 10.0%). Rule text (DE): 'Maximales Gewicht Einzeltitel überschritten'."`
- `RuleDescription` bleibt in Originalsprache im Fact (das LLM übersetzt sinngemäß in der Storyline).
- Mehrere gleichartige Verstöße (gleicher RuleCode) → **ein** Fact mit Liste der betroffenen Titel.

### 5.8 Detektor 5 — `esg`

- Nur wenn Kunde `EsgProfileId` hat **und** `EsgProfile.Name == "Yes"`.
- Pro Position: `sustainability_score < MinimumPositionLevel` → betroffen.
- Portfolio: `Σ(weight × score) / Σ(weight für Positionen mit Score) < MinimumLevel` → betroffen.
- 🔍 Skalenrichtung prüfen (höher = besser?).
- **Dedupe:** Wenn bereits ein Violation-Fact dieselbe ISIN mit ESG-bezogenem RuleCode enthält → kein zusätzlicher Fact.
- **Fact:** `"ESG preference 'Yes': 2 positions below minimum position score 45 (Glencore 31, TotalEnergies 38); portfolio average 58 (min 50)."`
- `base_severity = 0.65`

### 5.9 Detektor 6 — `concentration`

**Look-through für Fonds:** Für Positionen mit `is_fund_unbundlable` und Einträgen in `unbundling_by_fund_id`: Fondsgewicht auf die Unterkategorien verteilen: `exposure = fund_weight × row.weight` (row.weight bereits 0–1!). 🔍 Welche Dimension(en) die Mappings abdecken (Industry? AssetClass? Country?).

**Ebenen und Schwellen** (in `config.py`, `AnalysisConfig`):

| Ebene | Schlüssel | Schwelle (Default) | Referenz für magnitude |
|---|---|---|---|
| Einzeltitel | `security_id` | > 10 % | 15 % |
| Branche (inkl. Look-through) | `saa_industry` bzw. `industry` | > 20 % | 30 % |
| Währung ≠ ReportingCurrency | `currency` | > 30 % | 50 % |
| Land/Region | `saa_country_group` | > 40 % | 60 % |

- **Fact:** `"Semiconductor exposure 20.7% of assets (direct 16.5% + 4.2% via UBS Tech Fund look-through)."`
- `data`: `{level, key, weight, direct, via_funds: [{fund, weight}], threshold}`
- `base_severity = 0.70`
- **Immer** (auch unter Schwelle) die Top-5-Branchen- und Währungs-Exposures in `ctx`/`FactBundle.exposures` ablegen → für den Chat („What is the total semiconductor exposure?“).

### 5.10 Detektor 7 — `risk`

- `risk_contrib_i = weight_i × volatility_i`; `risk_share_i = risk_contrib_i / Σ risk_contrib`
- Portfolio-Volatilitäts-Näherung (Obergrenze, ohne Korrelationen): `Σ risk_contrib`
- Fact, wenn die Top-3 Positionen zusammen > 40 % des Risikos tragen **oder** Risk-Share einer Position > 2 × ihr Gewichtsanteil.
- **Fact:** `"ASML and NVIDIA are 16.5% of assets but ≈45% of portfolio risk (volatility 38% / 45%)."`
- Wenn `RiskProfiles[]` eine Max-Volatilität/Risikoklasse enthält (🔍) → zusätzlicher Vergleich.
- Positionen mit `PRC` über dem, was das Risikoprofil erlaubt (🔍 ob ableitbar) → nur wenn eindeutig, sonst weglassen.
- `base_severity = 0.60`
- Die komplette Risk-Share-Tabelle geht in `FactBundle.risk_table` (für den Chat).

### 5.11 Detektor 8 — `liquidity`

**a) Überschüssige Liquidität:** `cash_ratio = LiquidityInDefaultCurrency / AssetsUnderManagementInDefaultCurrency`; vergleichen mit SAA-Ziel Liquidität (falls vorhanden, sonst Default-Schwelle 10 %).
- **Fact:** `"Cash 12.0% vs SAA target 5.0%: ≈ CHF 70,000 available to invest."` → `polarity = opportunity`, `base_severity = 0.45`

**b) Fällige Anleihen:** `maturity_date` innerhalb von 180 Tagen ab `data_as_of` → Wiederanlage-Chance.
- **Fact:** `"Swiss Confederation 2026 (15.0%, CHF 150,000) matures 15 Nov 2026 – reinvestment needed."`

### 5.12 Detektor 9 — `proposals`

- **Offen** = `TransactionsSubmittedDateUTC` fehlt **und** Status nicht in einer „abgeschlossen/abgelehnt“-Liste (🔍 `ProposalStatuses` sichten; Liste in `config.py`).
- Pro offenem Proposal: Alter in Tagen (ab `data_as_of`), `Reason`, `Notes`, die 3 größten `SecurityPositions` (Kauf/Verkauf anhand Vorzeichen der `Quantity` 🔍).
- **Proposal-Impact (vorberechnet für Chat & Boost):** Wende `SecurityPositions` auf die Positionstabelle an (Gewichte verschieben um `ProposalValuePercentage` bzw. Beträge), rechne die AssetClass-Allokation neu → `impact = {category: (before, after, target)}`. Wenn das zu fehleranfällig ist: weglassen (Soll, nicht Muss).
- **Relevanz-Check:** Reduziert das Proposal eine bestehende SAA-Abweichung oder Konzentration? → `boost` (siehe 5.14) und `related_fact_ids`.
- **Fact:** `"Open proposal from 12 Jun 2026 (98 days, status 'Created'): switch 8% equities into bonds; reason: 'Rebalancing'. Would cut equity overweight from +16.0 pp to +8.0 pp."`
- `base_severity = 0.55`
- Die jüngsten 1–2 **abgeschlossenen** Proposals → als niedrig priorisierte Kontext-Facts (für den Chat: „What did we propose last time?“).

### 5.13 Detektor 10 — `open_items` (Ersatz für fehlende Tasks)

Abgeleitete To-dos, klar als abgeleitet gekennzeichnet:
- `ProfilingDateUtc` älter als 24 Monate (ab `data_as_of`) → `"Risk profile last assessed 14 Mar 2024 (30 months ago) – reassessment due."` (`base_severity 0.50`)
- Offenes Proposal > 60 Tage ohne Umsetzung → `"Follow up on proposal from 12 Jun 2026 (98 days open)."` (nur wenn nicht schon durch Proposal-Fact abgedeckt → dann stattdessen Proposal-Fact `boost ×1.1`)
- Kunde ≥ 60 Jahre (aus `Birthday`) und Aktienquote > SAA-Ziel → Kontext-Hinweis (niedrig)

### 5.14 Detektor 11 — `client_profile` + Notizen

**Profil-Fact** (immer genau 1, `category=client_profile`, `polarity=neutral`, `base_severity=0.50`, wird **immer** ans LLM gegeben, unabhängig vom Ranking):
`"Client: Anna Muster, 62, private client, risk profile 'Balanced', ESG preference 'Yes', reporting currency CHF, AuM CHF 1,000,000. Interest tags: Technology, Asia."`

**Notizen** → **keine** Python-Interpretation. Die **letzten 5** Notizen (nach `CreatedByDateUTC` absteigend) werden **wörtlich** als Facts `C1..C5` weitergegeben:
`text = "[12 Jun 2026] <Originaltext der Notiz>"` (max. 600 Zeichen, sonst abschneiden mit „…“).
Das LLM erkennt daraus Ziele/Sorgen/Präferenzen und **muss** beim Verwenden auf `C*` verweisen.

**Keyword-Boost-Hilfe** (einfach, mehrsprachig, in `config.py`): Wenn eine Notiz Stichworte enthält, setze Flags im Kontext:

```python
NOTE_KEYWORDS = {
    "risk_averse":  ["volatil", "schwank", "angst", "nervös", "sorge", "risque", "inquiet", "prudent", "sicherheit"],
    "liquidity_need": ["haus", "immobil", "wohnung", "kauf", "maison", "achat", "appartement", "liquid", "entnahme", "retrait"],
    "retirement":   ["pension", "rente", "retraite", "ruhestand"],
    "esg_interest": ["nachhaltig", "esg", "durable", "klima", "climat"],
}
```

Diese Flags dienen **nur** dem Boost im Ranking (5.16) — sie werden nie als Fakten dargestellt.

### 5.15 House-View-Abgleich (`houseview/compare.py`, IDs `H*`)

Siehe [6.3](#63-house-view) für das Dateiformat.
- Für jede Kategorie in `house_view.asset_classes` (Keys **müssen** den `SAA_AssetClassName`-Werten entsprechen):
  - `tilt = actual - saa_target` (in pp) aus Detektor 3 (bzw. direkt berechnet)
  - Bewertung:

| House View | Portfolio vs SAA | Ergebnis | polarity |
|---|---|---|---|
| overweight | ≤ −3 pp | **contrary** → Handlungsbedarf | negative |
| underweight | ≥ +3 pp | **contrary** | negative |
| overweight | ≥ +3 pp | aligned | positive |
| underweight | ≤ −3 pp | aligned | positive |
| neutral | \|tilt\| ≥ 10 pp | Hinweis (Abweichung ohne CIO-Deckung) | neutral |
| sonst | | kein Fact | |

- Dasselbe für `regions` (gegen `saa_country_group`) und `sectors` (gegen die Top-Branchen-Exposures).
- **Fact:** `"Portfolio is -13.0 pp underweight bonds vs SAA while the CIO view is OVERWEIGHT bonds ('attractive yields, rate cuts expected')."`
- `base_severity`: contrary 0.60, aligned 0.30, Hinweis 0.35
- **Kaufideen:** Für jede „contrary underweight“-Kategorie: bis zu 3 Wertpapiere aus `ref.Securities` mit `InRecommendationList == true` und passender `SAA_AssetClassName` (bzw. Region) als `data.candidates = [{security_id, name, isin}]` anhängen. **Das LLM darf Kauf-/Switch-Vorschläge NUR aus diesen Kandidaten oder aus bestehenden Positionen machen.**

### 5.16 Priorisierung (`analytics/ranking.py`)

**Schritt 1 — Grundgewicht (`base_severity`) je Typ:**

| Typ | base_severity |
|---|---|
| Violation „Error“ | 1.00 |
| SAA-Abweichung AssetClass | 0.80 |
| Violation „Warning“ | 0.75 |
| Performance-Gesamt (Teil A) | 0.70 |
| Performance-Treiber (Teil B) | 0.70 |
| Konzentration | 0.70 |
| ESG | 0.65 |
| Market comparison | 0.60 |
| SAA-Abweichung andere Dimensionen | 0.60 |
| House View contrary | 0.60 |
| Risiko-Konzentration | 0.60 |
| Proposal offen | 0.55 |
| Open items | 0.50 |
| Liquidität / Fälligkeit | 0.45 |
| House View Hinweis / aligned | 0.35 / 0.30 |
| Abgeschlossene Proposals, Coverage-Hinweise | 0.20 |

**Schritt 2 — `magnitude`** (vom Detektor gesetzt, 0..1; Referenzgrößen siehe Detektoren; Minimum 0.2 für jeden erzeugten Fact).

**Schritt 3 — `boost`** (multiplikativ, Gründe in `boost_reasons` speichern):

| Bedingung | Faktor | boost_reason |
|---|---|---|
| Risikoprofil konservativ/defensiv (Name enthält „conserv“, „defens“, „low“, „income“, „einkommen“, „sicher“ 🔍) **oder** Flag `risk_averse` — und Fact ∈ {risk, concentration, performance negativ, market_comparison} | ×1.3 | "risk-averse client" |
| Flag `liquidity_need` — und Fact ∈ {liquidity, performance negativ, saa_deviation AssetClass Shares über Ziel} | ×1.3 | "client needs liquidity (notes)" |
| Fact teilt `related_security_ids` mit einem anderen Fact mit base_severity ≥ 0.7 | ×1.2 | "same position as other key finding" |
| Proposal reduziert eine bestehende SAA-Abweichung/Konzentration | ×1.3 | "proposal addresses current deviation" |
| Performance-Fact und `last_interaction` vorhanden und Bewegung seit Kontakt > 3 % | ×1.1 | "material change since last contact" |

`boost` wird auf max. 1.6 begrenzt.

**Schritt 4 — Score & Auswahl:**
```python
score = base_severity * magnitude * boost
```
1. Alle `F`/`H`-Facts nach `score` absteigend sortieren.
2. **Diversität:** max. 3 Facts pro `category` in der Top-Auswahl.
3. **Top 12** → `bundle.top_facts`; alle weiteren → `bundle.other_facts` (gehen an den Chat, nicht ans Briefing).
4. **Immer dabei** (zusätzlich zu den Top 12): Profil-Fact, alle `C*`-Notizen, die ausgewählten News `N*` (max. 6).
5. IDs vergeben: `F1..Fn` in Score-Reihenfolge (Top zuerst, dann Rest), `H1..`, `N1..`, `C1..`.
6. `related_fact_ids` von Objektreferenzen auf IDs umschreiben.

```python
class FactBundle(BaseModel):
    client_id: int
    data_as_of: date
    profile_fact: Fact
    top_facts: list[Fact]          # max 12 (F*/H*)
    other_facts: list[Fact]        # Rest, für Chat
    news: list[Fact]               # N*
    notes: list[Fact]              # C*
    exposures: dict                # Top Branchen/Währungen/Regionen inkl. Look-through
    risk_table: list[dict]         # pro Position risk share
    allocation: list[dict]         # AssetClass Ist/Min/Target/Max je Portfolio (für Chart)
    coverage: dict[str, str]       # detector -> status
    warnings: list[str]            # z.B. "Market data unavailable"

    def all_facts(self) -> list[Fact]: ...
    def by_id(self) -> dict[str, Fact]: ...
```

---

## 6. Externe Quellen: Marktdaten, News, House View

Alle yfinance-Aufrufe **nur** in `app/market/`. Jeder Aufruf: `try/except`, Timeout, Logging. **Nie** eine Exception nach oben durchreichen — bei Fehlern `None`/leere Liste + Warnung.

### 6.1 Ticker-Auflösung (`market/tickers.py`)

- Nur für die **Top 15 Positionen nach Gewicht** mit `security_type` ∈ {Shares, ETF/Fund 🔍} — Anleihen überspringen.
- Reihenfolge:
  1. Manuelle Override-Datei `data/ticker_overrides.json` (`{ "ISIN": "TICKER" }`) — für Demo-Fälle, die Yahoo nicht findet.
  2. `yf.Search(isin, max_results=5).quotes` → erstes Ergebnis mit `quoteType` ∈ {EQUITY, ETF, MUTUALFUND}; bevorzugt Börse passend zur Wertpapierwährung (CHF → `.SW`, EUR → `.DE`/`.AS`/`.PA`, USD → ohne Suffix).
  3. Fallback: `yf.Search(name)` mit gleicher Logik.
- In-Memory-Memo (dict) für die Laufzeit des Prozesses (**kein** Datei-Cache — Teamentscheidung).
- Alle Suchen parallel (`concurrent.futures.ThreadPoolExecutor(max_workers=8)`).

### 6.2 Kurse & News (`market/prices.py`, `market/news.py`)

**Kurse:** `yf.download(tickers + proxies, period="3mo", interval="1d", group_by="ticker", progress=False, threads=True)` — **ein** Batch-Call für alle Ticker inkl. Sektor- und Markt-Proxies. Ergebnis: `dict[ticker, pd.Series]` (Close).

**News:**
- Pro aufgelöstem Ticker der Top-8-Positionen: `yf.Ticker(t).news`
- Pro Top-3-Branche (nach Exposure): `yf.Search(f"{industry} stocks", news_count=5).news`
- **Format-Robustheit:** Das yfinance-News-Format hat sich geändert. Parser muss beide Varianten können:
  - neu: `item["content"]["title"]`, `item["content"]["pubDate"]`, `item["content"]["provider"]["displayName"]`, `item["content"]["summary"]`, `item["content"]["canonicalUrl"]["url"]`
  - alt: `item["title"]`, `item["providerPublishTime"]` (Unix), `item["publisher"]`, `item["link"]`
- Filter: nur letzte **14 Tage** (Realzeit); Duplikate nach normalisiertem Titel entfernen.
- Relevanz: direkte Ticker-News = 1.0 × Positionsgewicht-Rang-Faktor; Branchen-News = 0.6. Sortieren, **max. 6** News.
- **News-Fact:** `id="N1"`, `text = "[15 Sep 2026, Reuters] <Title> — <Summary max 200 chars>"`, `data = {ticker, related_position, url, published, relevance}`, `related_security_ids` setzen.
- Keine News verfügbar → `bundle.warnings.append("No current market news available")`; das LLM bekommt „No news available“ und darf dann **keine** Marktkausalität behaupten.

**Zeitbudget:** Gesamter Market-Schritt max. **8 s** (`concurrent.futures.wait(timeout=8)`); was bis dahin nicht fertig ist, wird verworfen.

### 6.3 House View

Datei `data/house_view.json`, einmalig manuell erstellt aus einem öffentlichen CIO-Report (z. B. UBS „House View“, Julius Bär „Investment Outlook“, Pictet „Horizon“ — Quelle & Datum im File vermerken). **Als Mock kennzeichnen.**

```json
{
  "source": "Based on publicly available <Bank> CIO Outlook, <Month Year> (mock input)",
  "as_of": "2026-09-01",
  "summary": "Moderately positive on equities, prefer quality bonds, expect gradual rate cuts.",
  "asset_classes": {
    "<SAA_AssetClassName exakt wie in Daten, z.B. Bonds>":   {"stance": "overweight",  "rationale": "Attractive yields; rate cuts expected."},
    "<z.B. Shares>":                                          {"stance": "neutral",     "rationale": "Valuations stretched, earnings growth intact."},
    "<z.B. Liquidity>":                                       {"stance": "underweight", "rationale": "Falling cash rates."},
    "<z.B. Alternative investments>":                         {"stance": "overweight",  "rationale": "Gold as a hedge."}
  },
  "regions": {
    "<SAA_CountryGroupName, z.B. North America>": {"stance": "neutral", "rationale": "..."},
    "<z.B. Emerging Markets>":                    {"stance": "overweight", "rationale": "..."}
  },
  "sectors": {
    "<SAA_IndustryName, z.B. Semiconductors>": {"stance": "neutral", "rationale": "Cyclical slowdown, structural AI demand intact."}
  },
  "currencies": {
    "USD": {"stance": "underweight", "rationale": "..."}
  }
}
```

**Regeln:** `stance` ∈ {`overweight`, `neutral`, `underweight`}. Keys **exakt** wie die Kategorienamen in den Daten (im Spike ermitteln!). Loader validiert gegen Pydantic-Modell und loggt Keys, die in keiner SAA vorkommen.

---

## 7. LLM-Schicht: Briefing-Generierung & Validierung

> ⚠️ **Vorschlag, noch nicht gemeinsam reviewt.**

### 7.1 Modell & Aufruf

- SDK: `anthropic` (Python). **Vor dem Implementieren die `claude-api`-Skill bzw. aktuelle Anthropic-Doku konsultieren** für exakte Syntax (Structured Output / Tool-Use, Modell-IDs).
- Modell (in `config.py`, per Env überschreibbar): Default **`claude-sonnet-5`** (gute Balance aus Qualität und Geschwindigkeit). Alternative für mehr Speed: `claude-haiku-4-5-20251001`.
- Key über Env-Variable `ANTHROPIC_API_KEY` (`backend/.env`, **nie committen**).
- **Structured Output über erzwungenen Tool-Call:** ein Tool `submit_briefing` mit JSON-Schema = `BriefingDraft.model_json_schema()`, `tool_choice={"type": "tool", "name": "submit_briefing"}`. Ergebnis mit Pydantic `BriefingDraft.model_validate(tool_input)` parsen.
- `max_tokens` ≈ 2000, Timeout 45 s. Temperature niedrig (0.2), falls vom Modell unterstützt.

```python
# backend/app/llm/briefing.py (Skizze)
resp = client.messages.create(
    model=settings.llm_model,
    max_tokens=2000,
    system=load_prompt("briefing_system.md"),
    tools=[{
        "name": "submit_briefing",
        "description": "Submit the finished 60-second client briefing.",
        "input_schema": BriefingDraft.model_json_schema(),
    }],
    tool_choice={"type": "tool", "name": "submit_briefing"},
    messages=[{"role": "user", "content": render_bundle_for_llm(bundle)}],
)
tool_use = next(b for b in resp.content if b.type == "tool_use")
draft = BriefingDraft.model_validate(tool_use.input)
```

Falls das Schema mit `$defs`/`$ref` Probleme macht: Schema vor dem Senden inlinen (Hilfsfunktion `inline_refs(schema)`).

### 7.2 Output-Schema `BriefingDraft`

```python
# backend/app/models/briefing.py
class StatementType(StrEnum):
    FACT = "fact"                    # direkt aus Portfolio-/Kundendaten
    MARKET = "market"                # aus News / Marktdaten / House View (externer Kontext)
    INTERPRETATION = "interpretation"  # Schlussfolgerung/Einschätzung des Assistenten

class Tone(StrEnum):
    CRITICAL = "critical"   # Verstoß, großes Problem
    WARNING = "warning"     # Abweichung, Risiko
    INFO = "info"           # neutral
    POSITIVE = "positive"   # gute Nachricht / Chance

class Statement(BaseModel):
    type: StatementType
    tone: Tone
    text: str = Field(max_length=220)       # ~max 30 Wörter
    sources: list[str] = Field(min_length=1)  # Fact-IDs: F*, N*, H*, C*

class ActionType(StrEnum):
    RESOLVE_VIOLATION = "resolve_violation"
    REBALANCE = "rebalance"
    REDUCE_CONCENTRATION = "reduce_concentration"
    REINVEST_LIQUIDITY = "reinvest_liquidity"
    FOLLOW_UP_PROPOSAL = "follow_up_proposal"
    BUY = "buy"
    SELL = "sell"
    SWITCH = "switch"
    CLIENT_FOLLOW_UP = "client_follow_up"     # Präferenz/Ziel/Sorge ansprechen
    UPDATE_PROFILE = "update_profile"

class Action(BaseModel):
    priority: int = Field(ge=1, le=3)
    type: ActionType
    title: str = Field(max_length=80)        # Imperativ: "Trim ASML to below 10%"
    rationale: str = Field(max_length=220)   # warum, mit Zahlen
    sources: list[str] = Field(min_length=1)

class LikelyQuestion(BaseModel):
    question: str = Field(max_length=120)    # was der Kunde fragen könnte
    answer_hint: str = Field(max_length=220) # Kernaussage für die Antwort
    sources: list[str] = Field(min_length=1)

class BriefingDraft(BaseModel):
    headline: str = Field(max_length=160)    # TL;DR in 1 Satz
    what_happened: list[Statement] = Field(max_length=3)
    current_situation: list[Statement] = Field(max_length=4)
    outlook: list[Statement] = Field(max_length=3)
    next_best_actions: list[Action] = Field(min_length=1, max_length=3)
    likely_questions: list[LikelyQuestion] = Field(max_length=3)
```

**Wortbudget:** Headline + 3 Abschnitte + Actions zusammen **≤ 200 Wörter** (≈ 60 s Lesezeit). `likely_questions` sind einklappbar und zählen nicht zum 60-s-Budget.

### 7.3 LLM-Input: `render_bundle_for_llm(bundle)`

Kompaktes, deterministisches Textformat (kein riesiges JSON):

```
CLIENT PROFILE
[F0] Client: Anna Muster, 62, private client, risk profile 'Balanced', ESG 'Yes', CHF, AuM CHF 1,000,000. Tags: Technology, Asia.

PORTFOLIO DATA AS OF: 01 Sep 2026   |   MARKET DATA: live, last 3 months to 18 Sep 2026

KEY FINDINGS (ranked, most important first)
[F1] (violation, score 1.20) Suitability ERROR – max single-position weight: ASML Holding 14.0% (limit 10.0%). …
[F2] (saa_deviation, score 1.04; boosted: proposal addresses current deviation) Equities 66.0% vs SAA target 50.0% …
…
[H1] (house_view) Portfolio is -13.0 pp underweight bonds vs SAA while the CIO view is OVERWEIGHT bonds … Recommended candidates: Swiss Confederation 2034 (CH…), …

MARKET NEWS (external, filtered to holdings)
[N1] [15 Sep 2026, Reuters] Chip stocks slide after … — related position: ASML
…  (oder: "No current market news available.")

CLIENT NOTES (verbatim, may be German/French)
[C1] [12 Jun 2026] Kunde plant Hauskauf im Frühling 2027, braucht ca. 300k …
…

HOUSE VIEW SUMMARY
Based on publicly available … (mock input): Moderately positive on equities, prefer quality bonds …
```

Hinweis: Der Profil-Fact bekommt im LLM-Input die ID `F0` (fester Anker), alle anderen wie im Ranking.

### 7.4 System-Prompt (`backend/app/llm/prompts/briefing_system.md`)

```markdown
You are the briefing assistant inside URO Advisor Pro, used by wealth managers at a Swiss private bank.
An advisor is about to speak with a client and has about 60 seconds to prepare.
Write a briefing that they can read in 60 seconds and use directly in the conversation.

## Hard rules (grounding)
1. Use ONLY the information in the user message. Never add facts, numbers, securities, dates or events from your own knowledge.
2. Every statement, action and likely question MUST cite at least one source ID in `sources` (F*, H*, N*, C*). Cite every ID you rely on.
3. Copy numbers EXACTLY as they appear in the findings (same rounding, same units). Do not calculate new numbers. Do not convert currencies.
4. Mark each statement's `type` honestly:
   - "fact": directly stated in portfolio/client findings (F*, C*).
   - "market": external context from news (N*) or the CIO house view (H*).
   - "interpretation": your conclusion that connects several sources. Use cautious language ("likely", "suggests").
5. Only claim a causal link between market news and portfolio moves if a news item (N*) and a finding (F*) refer to the same position or sector. If no news is available, say nothing about market causes.
6. Buy/switch suggestions may ONLY name securities that appear in the findings (existing positions or listed "Recommended candidates"). Otherwise describe the action generically ("add high-quality CHF bonds from the recommendation list").
7. Client notes may be in German or French. Paraphrase them in English and cite the C* ID.
8. If something important is unknown (e.g. no market data), you may state that briefly, but never guess.

## What to write
- `headline`: one sentence, the single most important thing the advisor must know.
- `what_happened` (≤3): recent performance and its main drivers; sector-wide vs stock-specific if known.
- `current_situation` (≤4): violations first, then SAA deviations, concentrations/risk, ESG, open proposals, relevant client circumstances.
- `outlook` (≤3): link the portfolio to news and the CIO view — why it matters for THIS client.
- `next_best_actions` (1–3, priority 1 = most urgent): concrete, specific, with size where available ("Trim ASML from 14.0% to below the 10.0% limit"). Prefer actions that solve several findings at once. Consider open proposals and client goals from the notes.
- `likely_questions` (≤3): what this client will probably ask, with a short answer hint.

## Style
- English, professional, concise. Short sentences. No filler, no disclaimers, no greetings.
- Total length of headline + sections + actions: at most 200 words.
- Prioritise: the findings are pre-ranked; follow the ranking unless the client context (notes, profile) clearly makes something more relevant.
- Tell a coherent story: connect performance → situation → outlook → action. Do not list unrelated summaries.

Submit the result with the `submit_briefing` tool.
```

### 7.5 Validator (`llm/validator.py`)

Prüft `BriefingDraft` gegen `FactBundle`. Gibt `ValidationResult(ok: bool, errors: list[str], cleaned: BriefingDraft)` zurück.

| # | Prüfung | Bei Fehler |
|---|---|---|
| 1 | Pydantic-Validierung (Schema, Längen) | Retry |
| 2 | Jede `sources`-ID existiert im Bundle (inkl. `F0`) | Statement entfernen, Fehler notieren |
| 3 | **Zahlencheck:** alle Zahlen im Text (Regex `-?\d[\d,]*\.?\d*\s?(%|pp)?`) müssen in den Texten der zitierten Facts vorkommen (Normalisierung: Kommas entfernen, `+`/`−` vereinheitlichen; Toleranz: exakter String oder numerisch ±0.05). Ausgenommen: Zahlen 1–3 bei „priority“, Jahreszahlen, die im Fact-Datum vorkommen. | Statement als `unverified` markieren; ≥ 2 solcher → Retry |
| 4 | Wertpapiernamen in Actions vom Typ buy/switch kommen in zitierten Facts vor | Action entfernen |
| 5 | Wortzahl ≤ 230 (Toleranz) | nur Warnung |
| 6 | `next_best_actions` nicht leer nach Bereinigung | Retry |

**Retry:** genau **1** zweiter Call; die Fehlerliste wird als zusätzliche User-Nachricht angehängt: `"Your previous output had these problems: … Fix them and resubmit."`

**Fallback** (`llm/fallback.py`): Wenn LLM nicht erreichbar, Timeout, oder Retry scheitert → **deterministisches Template-Briefing** aus den Top-Facts:
- headline = Text des Top-Facts
- what_happened = Performance-/Treiber-Facts (type fact)
- current_situation = Top-4 negative Facts
- outlook = H*-Facts + erster News-Fact
- next_best_actions = regelbasiert aus Fact-Kategorie (Mapping-Tabelle: violation → resolve_violation „Resolve: <text>“, saa_deviation → rebalance, concentration → reduce_concentration, proposal → follow_up_proposal, liquidity → reinvest_liquidity)
- `BriefingResponse.mode = "fallback"` → UI zeigt dezentes Badge „Rule-based briefing (AI unavailable)“.

**Damit liefert der Endpoint IMMER ein Briefing.**

### 7.6 Endgültige Response `BriefingResponse`

```python
class BriefingResponse(BaseModel):
    client_id: int
    client_name: str
    generated_at: datetime
    mode: Literal["ai", "ai_retry", "fallback"]
    briefing: BriefingDraft
    unverified_statement_indices: list[str] = []   # z.B. ["current_situation.2"]
    facts: list[Fact]              # ALLE Facts (top + other + news + notes + F0), für Source-Popover
    allocation: list[dict]         # für Mini-Chart
    coverage: dict[str, str]
    warnings: list[str]
    timings_ms: dict[str, int]     # load, market, analytics, llm, validate, total
    data_as_of: date
```

---

## 8. Follow-up-Chat (Bonus)

> ⚠️ **Vorschlag, noch nicht gemeinsam reviewt.**

### 8.1 Verhalten

- Erscheint unter dem Briefing, sobald ein Briefing existiert.
- Advisor stellt Fragen; Antworten sind **kurz (≤ 120 Wörter)**, **zitieren Fact-IDs** und sagen klar **„This information is not available in the data.“**, wenn etwas fehlt.
- Vorgeschlagene Fragen als Klick-Chips (aus `likely_questions` + feste Beispiele):
  - „What is the client's total semiconductor exposure?“
  - „Has the client raised concerns about volatility before?“
  - „Which positions contribute most to risk?“
  - „Which open proposal is most relevant?“
  - „How would the open proposal change the allocation?“

### 8.2 Kontext für den Chat

Der Chat bekommt **mehr** als das Briefing — den ganzen `FactBundle`:
- alle Facts (`top_facts` + `other_facts` + News + **alle** Notizen, nicht nur 5)
- `exposures` (Branche/Währung/Region inkl. Look-through, Top 10)
- `risk_table`
- `allocation`
- kompakte Positionsliste (Name, Gewicht, AssetClass, Branche, Währung, Volatilität, ESG-Score) als Textzeilen, IDs `P1..Pn` (neue Präfix-Kategorie nur für den Chat)
- Proposal-Details inkl. vorberechnetem Impact
- das generierte Briefing selbst

Quelle: `BriefingCache[client_id]` (wird beim Briefing befüllt). Existiert keins → Endpoint baut das Bundle ohne LLM-Briefing neu (Detektoren laufen schnell; Market-Schritt wird mitgemacht).

### 8.3 API & Aufruf

- `POST /api/clients/{id}/chat` mit `{ "messages": [{"role": "user"|"assistant", "content": "..."}] }` (Frontend hält den Verlauf).
- Backend: System-Prompt `chat_system.md` + Kontext als erste User-Nachricht (Prompt Caching nutzen, wenn einfach möglich) + Verlauf.
- Antwort: `{ "answer": "...", "sources": ["F3", "P2"] }` — Quellen per Regex `\[(F|N|H|C|P)\d+\]` aus der Antwort extrahiert.
- Kein Streaming nötig (Stretch: Streaming via SSE).

### 8.4 Chat-System-Prompt (`llm/prompts/chat_system.md`)

```markdown
You are the follow-up assistant in URO Advisor Pro. The advisor is preparing for, or is in, a conversation with the client described in the context.

Rules:
1. Answer ONLY from the context provided. Never use outside knowledge about markets, companies or the client.
2. Cite the source IDs you used in square brackets, e.g. "Semiconductor exposure is 20.7% [F4]."
3. Copy numbers exactly from the context. Do not compute new figures, except simple sums or differences of numbers that are all in the context — then show the inputs ("16.5% direct + 4.2% via funds = 20.7% [F4]").
4. If the answer is not in the context, say: "This information is not available in the data." and, if useful, what data would be needed.
5. Be concise: at most 120 words, bullet points welcome. English unless the advisor writes in another language.
6. Distinguish facts from your interpretation ("Data shows… / This suggests…").
```

---

## 9. Frontend (URO Advisor Pro Mock)

> ⚠️ **Vorschlag, noch nicht gemeinsam reviewt.**

### 9.1 Visuelle Vorgaben

- **Zuerst** die Screenshots in `core-case/GUI-screenshots/` ansehen und daraus ableiten: Primärfarbe, Hintergrund, Schrift, Sidebar-Aufbau, Tabellenstil, Button-Stil. In `tailwind.config` als Tokens anlegen (`uro-primary`, `uro-bg`, `uro-surface`, `uro-border`, `uro-text`, `uro-muted`).
- Logo: `assets/logos/uro-light.svg` bzw. `uro-dark.svg` nach `frontend/public/` kopieren.
- Semantische Farben für Briefing:
  - `critical` → Rot (Verstöße)
  - `warning` → Amber (Abweichungen/Risiken)
  - `info` → Grau/Blau (neutral)
  - `positive` → Grün (gute Entwicklung, Chancen)
- Statement-Typen visuell unterscheiden (Jury-Kriterium „facts vs interpretation distinguishable“):
  - `fact` → normale Schrift, kleines Label „DATA“
  - `market` → Globus-Icon, Label „MARKET“
  - `interpretation` → kursiv, Label „ASSESSMENT“
- Icons: `lucide-react`. Schrift: die aus den Screenshots, sonst Inter.
- Professionell und ruhig, keine verspielten Animationen. Desktop first (1440 px); muss bis 1280 px funktionieren.

### 9.2 Seiten & Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [URO logo]  URO Advisor Pro                        Advisor: Demo User  ⚙      │  TopBar
├────────┬─────────────────────────────────────────────────────────────────────┤
│ Clients│  ClientListPage:                                                    │
│ Portf. │   [Search…]                                     [⬆ Upload data]     │
│ Propos.│   Name          Ref     Risk profile   AuM         Violations  NEW   │
│ (mock) │   Anna Muster   C-0012  Balanced       CHF 1.0M    ⛔ 2              │
│        │   …                                                                 │
└────────┴─────────────────────────────────────────────────────────────────────┘

ClientDetailPage:
┌────────┬───────────────────────────────────────────┬─────────────────────────┐
│Sidebar │ ← Clients / Anna Muster                   │  BRIEFING PANEL         │
│        │ Anna Muster · Balanced · ESG Yes · CHF    │  (rechts, 520 px,       │
│        │ AuM CHF 1.0M   Liquidity 12%              │   erscheint nach Klick) │
│        │                  [✦ Generate Briefing]    │                         │
│        │ ┌ Tabs: Overview | Positions | Proposals ┐│                         │
│        │ │ Allocation vs SAA (Balken)              ││                         │
│        │ │ Positions table (Top 15)                ││                         │
│        │ │ Notes (letzte 3)                        ││                         │
│        │ └─────────────────────────────────────────┘│                         │
└────────┴───────────────────────────────────────────┴─────────────────────────┘
```

- Die Overview/Positions/Proposals-Tabs sind **einfache Darstellungen der Rohdaten** (Mock des URO-Kontexts). Keine Bearbeitung.
- **„Generate Briefing“**: primärer Button, oben rechts im Client-Header, gut sichtbar (zusätzlich Tastenkürzel `G`).

### 9.3 Briefing-Panel (Kernstück der UX)

```
┌──────────────────────────────────────────────┐
│ ✦ Client Briefing · Anna Muster        [×]   │
│ Generated 14:32 · ~60 sec read · AI ✓        │
│ Portfolio data as of 01 Sep 2026 · Market live│
├──────────────────────────────────────────────┤
│ ▌ ASML breach and a 16 pp equity overweight  │  ← Headline, groß, fett
│ ▌ drive risk ahead of the 2027 house purchase│
├──────────────────────────────────────────────┤
│ 1 WHAT HAPPENED                              │
│ ● DATA  Portfolio -4.2% in 3 months… [F3]    │  ← linker Farbbalken = tone
│ ● MARKET Decline sector-wide: SOXX -22%… [F5][N1]
│ 2 CURRENT SITUATION                          │
│ ⛔ DATA  Suitability error: ASML 14.0%… [F1] │
│ ▲ DATA  Equities +16.0 pp over SAA… [F2]     │
│ ◇ ASSESSMENT Risk is too high for a client   │
│          planning a purchase in 2027 [F2][C1]│
│ 3 OUTLOOK                                    │
│ 🌐 MARKET CIO overweights bonds… [H1]        │
├──────────────────────────────────────────────┤
│ NEXT BEST ACTIONS                            │
│ ┌──────────────────────────────────────────┐ │
│ │ 1  RESOLVE VIOLATION                     │ │
│ │    Trim ASML from 14.0% to below 10.0%   │ │
│ │    Fixes breach and cuts semis risk [F1] │ │
│ └──────────────────────────────────────────┘ │
│ ┌ 2  FOLLOW UP PROPOSAL … ┐                  │
│ ┌ 3  REBALANCE … ┐                           │
├──────────────────────────────────────────────┤
│ ▸ Likely client questions (3)                │  ← einklappbar
│ ▸ Allocation vs SAA  [mini bar chart]        │  ← einklappbar
│ ▸ Data coverage: 10/11 analyses · 6 news     │  ← einklappbar, Warnungen
├──────────────────────────────────────────────┤
│ 💬 Ask a follow-up…                  [Send]  │  ← ChatPanel
│ [Total semis exposure?] [Volatility concerns?]│
└──────────────────────────────────────────────┘
```

- **Source-Chips** `[F1]`: klickbar → Popover mit Fact-Text, Kategorie, Score + Boost-Gründe, `source`-Pfad, bei News Link zum Artikel. → **Das ist unser sichtbarer Grounding-Beweis.**
- `unverified` Statements → kleines ⚠-Icon mit Tooltip „Could not be fully verified against data“.
- **Ladezustand** (während der Request läuft): Schritt-Liste mit Häkchen, zeitgesteuert rein kosmetisch: „Loading client data → Analysing portfolio → Fetching market news → Writing briefing → Checking facts“. Nach Antwort: tatsächliche `timings_ms` klein anzeigen („Prepared in 9.8 s“).
- Fehler: freundliche Meldung + „Retry“-Button. Nie weißer Screen.

### 9.4 Upload

- Button „Upload data“ auf der ClientListPage → Dialog mit Drag & Drop, mehrere `.json`-Dateien.
- Backend erkennt Dateityp am Inhalt (siehe 10), mergt, antwortet mit Liste neuer Client-IDs.
- Neue Kunden bekommen in der Liste ein Badge „NEW“ und stehen oben.
- Fehlerhafte Datei → konkrete Fehlermeldung („File X: not recognised as clients or reference data“).

### 9.5 Frontend-Technik

- Vite + React 18 + TypeScript (strict) + Tailwind CSS + `react-router-dom` + `lucide-react` + `recharts` (nur für Mini-Chart).
- Kein globaler State-Store; `useState`/`useEffect` + ein kleiner `api/client.ts` (fetch-Wrapper).
- `src/types/api.ts` spiegelt die Pydantic-Modelle **1:1** (manuell gepflegt; bei jeder Schemaänderung beide Seiten anpassen).
- Vite-Proxy: `/api` → `http://localhost:8000`.
- Mock-Modus für parallele Entwicklung: `VITE_USE_FIXTURES=true` → `api/client.ts` lädt `src/fixtures/*.json` statt Backend.

---

## 10. API-Vertrag

Basis-Pfad `/api`. Alle Responses JSON. Fehler: `{ "detail": "..." }` mit passendem Statuscode.

| Methode | Pfad | Request | Response |
|---|---|---|---|
| GET | `/api/health` | – | `{ "status": "ok", "clients": 47, "llm_configured": true }` |
| GET | `/api/clients` | `?q=` (optional Suche) | `ClientSummary[]` |
| GET | `/api/clients/{id}` | – | `ClientDetail` |
| POST | `/api/clients/{id}/briefing` | – | `BriefingResponse` (7.6) |
| POST | `/api/clients/{id}/chat` | `{ messages: ChatMessage[] }` | `{ answer: string, sources: string[] }` |
| POST | `/api/upload` | `multipart/form-data`, Feld `files` (1..n JSON) | `{ added_client_ids: int[], updated_client_ids: int[], reference_merged: bool, errors: string[] }` |
| POST | `/api/reset` | – | Setzt auf Originaldaten zurück (für Demo) |

```python
class ClientSummary(BaseModel):
    client_id: int
    display_name: str          # "First Last" oder Company
    client_ref: str | None
    risk_profile: str | None
    aum: float | None
    currency: str | None
    violation_count: int
    open_proposal_count: int
    is_new: bool               # via Upload hinzugefügt

class ClientDetail(ClientSummary):
    esg_profile: str | None
    birthday: date | None
    liquidity: float | None
    tags: list[str]
    portfolios: list[PortfolioView]     # id, name, value, positions (Top 50: name, isin, weight, asset class, currency, value)
    allocation: list[dict]              # AssetClass Ist/Min/Target/Max
    proposals: list[ProposalView]       # id, status, date, reason
    notes: list[NoteView]               # date, text (neueste zuerst)
    performance_history: list[dict]     # Date, Value (summiert)
```

**Upload-Erkennung:**
- JSON ist **Array** und Elemente haben `ClientId` → Kunden-Datei. Kunden mit bekannter `ClientId` → ersetzen (`updated`), sonst hinzufügen (`added`).
- JSON ist **Objekt** mit mind. einem Key aus {`Securities`, `SuitabilityRules`, `StrategicAssetAllocations`} → Referenz-Datei. Pro Collection mergen (Dedupe über `SecurityId` / `RuleCode` / `Id`; neue Einträge gewinnen).
- JSON ist **Objekt** mit `ClientId` → einzelner Kunde.
- Sonst → Fehler in `errors`.
- Nach dem Merge: `ReferenceIndex` neu bauen, `BriefingCache` leeren.
- 🔍 Die „drei zusätzlichen Dateien“ beim Pitch: Format im Spike aus README ableiten; der Uploader muss robust genug sein, um Varianten (z. B. `{ "clients": [...] }`) zu erkennen → zusätzliche Regel: Objekt mit Key `clients`/`Clients` (Array) → Kunden-Datei.

---

## 11. Fehlerbehandlung & fehlende Daten

**Grundsatz:** Der Briefing-Endpoint liefert **immer** HTTP 200 mit einem Briefing (AI oder Fallback), außer der Kunde existiert nicht (404).

| Situation | Verhalten | Sichtbar im UI |
|---|---|---|
| Feld fehlt im JSON | Pydantic `Optional`, `.get()` | – |
| Kunde ohne `PerformanceHistory` | Detektor 1A → `no_data` | Coverage: „No performance history“ |
| Kein Ticker für Position | Position ohne Treiberanalyse | Coverage-Fact „Price history unavailable for x%“ |
| yfinance down / Timeout | Market-Snapshot `None`; Detektoren 1B, 2 + News entfallen | Warnung „Market data unavailable“ |
| Keine News | News-Liste leer | „No current market news“ |
| Kein ESG-Profil / ESG = No | ESG-Detektor `no_data` | – |
| Keine SAA zuordenbar | SAA + House-View-AssetClass-Vergleich entfallen | „No target allocation found“ |
| Detektor wirft Exception | Loggen, `coverage[name] = "error"`, weiter | Coverage zeigt Fehler |
| LLM-Key fehlt / API-Fehler / Timeout | Fallback-Briefing | Badge „Rule-based briefing“ |
| LLM-Output invalid | 1 Retry, dann Fallback | Badge |
| Upload-Datei kaputt | 400 nur für diese Datei, andere werden verarbeitet | Fehlermeldung pro Datei |
| Unbekannte Kategorie-Namen (z. B. House-View-Keys) | Log-Warnung, ignorieren | – |
| Inkonsistente Daten (Gewichte summieren nicht auf ~100 %) | Log-Warnung, normalisieren auf Summe der Marktwerte | Coverage-Hinweis |

**Logging:** Python `logging`, Level INFO, Format mit Zeitstempel und Modul. LLM-Prompts und -Antworten zusätzlich nach `backend/logs/llm/<timestamp>_<client>.json` schreiben (für Debugging und Prompt-Tuning; `logs/` in `.gitignore`).

---

## 12. Projektstruktur (Dateibaum)

```
uro-briefing/
├── CLAUDE.md                          # Agent-Regeln (Anhang A)
├── README.md                          # Setup & Start in 5 Zeilen
├── Makefile                           # make dev / test / lint / smoke
├── .gitignore                         # .env, logs/, node_modules/, __pycache__/, .venv/, dist/
├── docs/
│   ├── superpowers/specs/2026-09-18-uro-briefing-assistant-design.md   # dieses Dokument
│   └── data-notes.md                  # Ergebnisse des Spikes (echte Feldnamen, Kategorien)
├── data/
│   ├── clients.json                   # aus Repo kopiert
│   ├── reference.json                 # aus Repo kopiert
│   ├── house_view.json                # selbst erstellt (Mock)
│   ├── sector_proxies.json
│   └── ticker_overrides.json          # {} zu Beginn
├── backend/
│   ├── pyproject.toml
│   ├── .env.example                   # ANTHROPIC_API_KEY=, LLM_MODEL=claude-sonnet-5
│   ├── app/
│   │   ├── main.py                    # FastAPI-App, CORS, Router einbinden, Startup lädt Daten
│   │   ├── config.py                  # Settings (pydantic-settings) + AnalysisConfig (Schwellen)
│   │   ├── models/
│   │   │   ├── domain.py              # Client, Portfolio, Position, Security, SAA, … (Pydantic)
│   │   │   ├── facts.py               # Fact, FactCategory, Polarity, FactBundle
│   │   │   ├── briefing.py            # BriefingDraft, Statement, Action, BriefingResponse
│   │   │   └── api.py                 # ClientSummary, ClientDetail, ChatRequest/Response, UploadResult
│   │   ├── data/
│   │   │   ├── loader.py              # JSON lesen → Pydantic; Weight/100-Konvertierung
│   │   │   ├── reference_index.py     # ReferenceIndex (alle Lookups)
│   │   │   ├── store.py               # DataStore (In-Memory, merge, reset)
│   │   │   └── upload.py              # Dateityp-Erkennung & Merge
│   │   ├── analytics/
│   │   │   ├── context.py             # AnalysisContext bauen
│   │   │   ├── positions.py           # Positionstabelle (DataFrame)
│   │   │   ├── format.py              # Zahlen-/Datumsformatierung (zentral!)
│   │   │   ├── engine.py              # run_detectors
│   │   │   ├── ranking.py             # Score, Boosts, Auswahl, ID-Vergabe → FactBundle
│   │   │   └── detectors/
│   │   │       ├── __init__.py        # DETECTORS-Registry
│   │   │       ├── performance.py
│   │   │       ├── market_comparison.py
│   │   │       ├── saa_deviation.py
│   │   │       ├── violations.py
│   │   │       ├── esg.py
│   │   │       ├── concentration.py
│   │   │       ├── risk.py
│   │   │       ├── liquidity.py
│   │   │       ├── proposals.py
│   │   │       ├── open_items.py
│   │   │       └── client_profile.py
│   │   ├── market/
│   │   │   ├── tickers.py             # ISIN → Ticker
│   │   │   ├── prices.py              # Batch-Kurse
│   │   │   ├── news.py                # News holen, parsen, filtern
│   │   │   └── snapshot.py            # MarketSnapshot + parallele Orchestrierung mit Zeitbudget
│   │   ├── houseview/
│   │   │   ├── loader.py
│   │   │   └── compare.py             # → H*-Facts inkl. Kandidaten
│   │   ├── llm/
│   │   │   ├── client.py              # Anthropic-Client-Factory, Logging
│   │   │   ├── render.py              # render_bundle_for_llm, render_chat_context
│   │   │   ├── briefing.py            # generate_briefing (Call + Retry)
│   │   │   ├── validator.py
│   │   │   ├── fallback.py
│   │   │   ├── chat.py
│   │   │   └── prompts/
│   │   │       ├── briefing_system.md
│   │   │       └── chat_system.md
│   │   ├── services/
│   │   │   ├── briefing_service.py    # Pipeline aus 4.2, Timings, Cache
│   │   │   └── cache.py               # BriefingCache
│   │   └── api/
│   │       ├── clients.py
│   │       ├── briefing.py
│   │       ├── chat.py
│   │       └── upload.py
│   ├── scripts/
│   │   ├── inspect_data.py            # Spike: Felder/Kategorien ausgeben → docs/data-notes.md
│   │   ├── spike_yfinance.py          # Spike: Ticker/News/Kurse testen
│   │   └── smoke_all_clients.py       # Engine über alle Kunden (ohne LLM), optional --llm N
│   └── tests/
│       ├── conftest.py                # Fixtures: kleiner synthetischer Kunde + Referenz
│       ├── fixtures/
│       │   ├── mini_clients.json
│       │   └── mini_reference.json
│       ├── test_loader.py
│       ├── test_positions.py
│       ├── test_detectors_*.py        # je Detektor
│       ├── test_ranking.py
│       ├── test_validator.py
│       ├── test_fallback.py
│       ├── test_upload.py
│       └── test_api.py                # FastAPI TestClient, LLM + market gemockt
└── frontend/
    ├── package.json
    ├── vite.config.ts                 # Proxy /api → :8000
    ├── tailwind.config.ts             # URO-Tokens
    ├── index.html
    ├── public/uro-logo.svg
    └── src/
        ├── main.tsx
        ├── App.tsx                    # Router
        ├── api/client.ts              # fetch-Wrapper + Fixture-Modus
        ├── types/api.ts               # spiegelt Pydantic-Modelle
        ├── fixtures/                  # sample_clients.json, sample_briefing.json
        ├── pages/
        │   ├── ClientListPage.tsx
        │   └── ClientDetailPage.tsx
        └── components/
            ├── layout/{AppShell,TopBar,Sidebar}.tsx
            ├── client/{ClientHeader,AllocationChart,PositionsTable,ProposalsList,NotesList}.tsx
            ├── briefing/{BriefingPanel,BriefingHeader,BriefingSection,StatementRow,ActionCard,
            │             SourceChip,FactPopover,LikelyQuestions,CoverageInfo,LoadingSteps}.tsx
            ├── chat/{ChatPanel,ChatMessage,SuggestedQuestions}.tsx
            └── upload/UploadDialog.tsx
```

---

## 13. Tech-Stack & Setup

| Bereich | Tool | Version |
|---|---|---|
| Python | CPython | 3.12 |
| Paketmanager | `uv` | aktuell |
| Web | `fastapi`, `uvicorn[standard]`, `python-multipart` | aktuell |
| Modelle | `pydantic` v2, `pydantic-settings` | |
| Daten | `pandas` | |
| Markt | `yfinance` | aktuell (Format-Änderungen beachten) |
| LLM | `anthropic` | aktuell |
| Tests/Lint | `pytest`, `ruff` | |
| Node | Node.js 20+, npm | |
| Frontend | `vite`, `react`, `react-dom`, `typescript`, `tailwindcss`, `react-router-dom`, `lucide-react`, `recharts` | |

**Setup (für README):**
```bash
# Backend
cd backend && uv sync && cp .env.example .env   # ANTHROPIC_API_KEY eintragen
uv run uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev        # http://localhost:5173
```

**Makefile-Targets:** `dev-backend`, `dev-frontend`, `test` (`uv run pytest -q`), `lint` (`uv run ruff check . && uv run ruff format --check .` + `npm run typecheck`), `smoke` (`uv run python scripts/smoke_all_clients.py`).

**Datenpfad:** `DATA_DIR` in Settings, Default `../data` relativ zu `backend/`.

---

## 14. Testing & Qualitätssicherung

### 14.1 Unit-Tests (pytest)

- **Fixtures:** `tests/fixtures/mini_clients.json` + `mini_reference.json` — **handgebaut**, 2–3 Kunden mit bekannten Werten (z. B. einer mit Violation + Überallokation + Halbleiter-Fonds, einer fast leer mit fehlenden Feldern). Struktur exakt wie die echten Daten.
- Pro Detektor mindestens: (1) Normalfall mit erwartetem Fact-Text/Zahlen, (2) fehlende Daten → leere Liste, keine Exception.
- `test_ranking.py`: Reihenfolge, Diversitätsregel, Boosts, ID-Vergabe.
- `test_validator.py`: erfundene ID → entfernt; erfundene Zahl → unverified; korrekte Zahl mit anderer Formatierung → ok.
- `test_fallback.py`: Fallback erzeugt gültigen `BriefingDraft` aus beliebigem Bundle (auch fast leer).
- `test_api.py`: `TestClient`; `llm` und `market` per Dependency-Override/Monkeypatch gemockt; `/briefing` liefert 200 auch bei LLM-Exception.
- **Keine echten Netzwerkcalls in Unit-Tests.**

### 14.2 Smoke-Test über alle Kunden

`scripts/smoke_all_clients.py`:
- Lädt echte Daten, baut für **jeden** der 47 Kunden Context + Detektoren + Ranking (ohne LLM, Market optional via `--market`).
- Gibt Tabelle aus: Kunde, #Facts, Top-3-Fact-Texte, Coverage-Fehler, Laufzeit.
- **Exit-Code ≠ 0**, wenn irgendein Detektor bei irgendeinem Kunden `error` hat.
- `--llm 5`: erzeugt echte Briefings für 5 zufällige Kunden und speichert sie nach `logs/smoke/` zur manuellen Sichtung.

→ Das ist unsere Versicherung für den **unbekannten Testkunden**.

### 14.3 Manuelle Qualitätsprüfung eines Briefings (Checkliste)

- [ ] In 60 s lesbar (≤ 200 Wörter)?
- [ ] Headline = wirklich das Wichtigste?
- [ ] Jede Zahl per Source-Chip auffindbar?
- [ ] Storyline verbindet Performance → Situation → Outlook → Action?
- [ ] Actions konkret (was, wie viel, warum)?
- [ ] Kundenkontext (Notizen) berücksichtigt?
- [ ] Keine erfundenen Wertpapiere/News?
- [ ] Antwortzeit < 15 s?

---

## 15. Arbeitsteilung & Zeitplan (10 h)

### 15.1 Rollen

| Person | Verantwortung | Verzeichnisse |
|---|---|---|
| **A — Analytics** | Datenmodell, Loader, Positionstabelle, alle Detektoren, Ranking, Smoke-Test | `backend/app/{models/domain.py,data,analytics}`, `tests/` |
| **B — AI & Market** | yfinance (Ticker/Kurse/News), House View JSON + Compare, LLM-Briefing, Validator, Fallback, Chat, Pipeline-Service, API | `backend/app/{market,houseview,llm,services,api}` |
| **C — Frontend & Pitch** | URO-Mock-UI, Briefing-Panel, Chat-UI, Upload-UI, Präsentation | `frontend/`, Slides |

Jede Person arbeitet mit einer eigenen Claude-Code-Session in **ihrem** Verzeichnisbereich → minimale Merge-Konflikte.

### 15.2 Zeitplan

| Zeit | Alle / A / B / C |
|---|---|
| **0:00–1:00** | **Alle:** Repo-Setup (Git, Struktur, Makefile, CLAUDE.md). **Spike** (Abschnitt 19): `inspect_data.py` + `spike_yfinance.py` → `docs/data-notes.md`. **Verträge einfrieren:** `models/facts.py`, `models/briefing.py`, `models/api.py`, `frontend/src/types/api.ts`, `fixtures/sample_briefing.json`. |
| **1:00–4:30** | **A:** Loader, Index, Positionstabelle, Detektoren (Muss-Liste zuerst), Ranking, Tests. **B:** market/, house_view.json + compare, LLM-Briefing mit Fixture-Bundle, Validator, Fallback. **C:** AppShell, Client-Liste, Client-Detail, Briefing-Panel gegen `sample_briefing.json`. |
| **4:30–5:30** | **Integration:** `briefing_service` verbindet alles; Frontend auf echtes Backend umstellen; erster End-to-end-Durchlauf. |
| **5:30–7:30** | **A:** Smoke-Test über alle Kunden, Bugs fixen, Soll-Detektoren. **B:** Chat-Endpoint + Prompt-Tuning mit 5 echten Kunden. **C:** Chat-UI, Upload-UI, Source-Popover, Loading-States, Politur URO-Look. |
| **7:30–8:30** | **Alle:** Demo-Kunden auswählen (1 mit klarer Story wie Beispiel-Szenario), Upload-Probe mit einer umbenannten Kopie eines Kunden als „unbekannter Kunde“, Performance prüfen (< 15 s). |
| **8:30–10:00** | **C (+A):** Slides. **B:** letzte Prompt-Feinheiten. **Alle:** Demo zweimal durchspielen, Fallback-Szenario testen (WLAN aus → Briefing kommt trotzdem). |

**Priorität bei Zeitnot (streichen in dieser Reihenfolge):** Proposal-Impact-Berechnung → Risk-Detektor → ESG-Detektor → Likely Questions → Mini-Chart → Chat-Suggested-Questions. **Nie streichen:** Upload, Validator, Fallback, Source-Chips.

---

## 16. Coding-Regeln für Agentic Coding

Diese Regeln gelten für jeden Coding-Agenten (und Menschen) im Projekt. Eine Kurzfassung steht in `CLAUDE.md` (Anhang A).

### 16.1 Arbeitsweise des Agenten

1. **Erst lesen, dann schreiben.** Vor jeder Aufgabe: `CLAUDE.md`, den relevanten Abschnitt dieser Spec und `docs/data-notes.md` lesen. Bestehende Dateien im Zielbereich lesen, bevor neue angelegt werden.
2. **Kleine Schritte.** Eine Aufgabe = ein klar abgegrenztes Ergebnis (z. B. „Detektor `saa_deviation` + Tests“). Nach jedem Schritt: Tests laufen lassen, dann committen.
3. **Verifizieren statt behaupten.** Nach jeder Änderung: `make test` und `make lint` (bzw. `npm run typecheck && npm run build` im Frontend). Bei UI-Änderungen: App starten und im Browser prüfen. „Sollte funktionieren“ gilt nicht.
4. **Daten nicht raten.** Unklare Feldnamen/Kategorien → mit `scripts/inspect_data.py` in den echten Daten nachsehen und in `docs/data-notes.md` dokumentieren. Nie Feldnamen erfinden.
5. **Spec ist die Quelle der Wahrheit.** Abweichungen von der Spec nur, wenn die Daten es erzwingen — dann in `docs/data-notes.md` unter „Abweichungen von der Spec“ mit Begründung notieren.
6. **YAGNI.** Nichts bauen, was nicht in dieser Spec steht (siehe Abschnitt 17). Keine „vielleicht später nützlichen“ Abstraktionen.
7. **Verträge sind heilig.** `models/facts.py`, `models/briefing.py`, `models/api.py` und `frontend/src/types/api.ts` werden nur gemeinsam geändert — immer Backend-Modell **und** TS-Typen **und** Fixture im selben Commit. Im Commit-Text `CONTRACT CHANGE:` voranstellen und das Team informieren.
8. **Keine Demo-Hacks.** Niemals `if client_id == 12:` o. ä. Kein Hartcodieren von Kundennamen, Wertpapieren oder erwarteten Texten außerhalb von Tests/Fixtures. Der unbekannte Testkunde muss funktionieren.
9. **Bei Unsicherheit fragen**, statt große Umbauten eigenmächtig durchzuführen.

### 16.2 Git

- `git init` zu Beginn; `main` bleibt lauffähig.
- Kleine Commits, Conventional-Commit-Stil: `feat(analytics): add saa deviation detector`, `fix(market): handle new yfinance news format`, `test(...)`, `chore(...)`.
- Jede Person arbeitet in ihrem Verzeichnisbereich (15.1); häufig `git pull --rebase`, um Konflikte klein zu halten.
- Niemals committen: `.env`, `logs/`, `node_modules/`, `.venv/`, `dist/`.

### 16.3 Python-Regeln

- **Type Hints überall**, `from __future__ import annotations` wo sinnvoll. Pydantic-Modelle an allen Grenzen (Dateien, API, LLM).
- **Pure Functions in `analytics/`**: keine I/O, kein globaler Zustand, keine Zeit-Abfragen (`date.today()` verboten — `ctx.data_as_of` verwenden).
- **Eine Verantwortung pro Datei**, Dateien < ~250 Zeilen, Funktionen < ~50 Zeilen.
- **Optionalität explizit:** `field: X | None = None`; Zugriff auf Rohdicts nur mit `.get()`.
- **Einheiten:** intern Brüche 0–1; Umrechnung `Weight/100` ausschließlich in `data/loader.py`; Formatierung ausschließlich über `analytics/format.py`.
- **Datumswerte:** timezone-aware parsen, intern `date` für Tagesvergleiche.
- **Fehler:** Keine nackten `except:`. Detektoren/Market/LLM fangen Exceptions an ihrer Grenze, loggen mit `logger.exception`, liefern definierte Leer-/Fallback-Werte. Innerhalb von Funktionen nicht defensiv jeden Schritt einpacken.
- **Logging statt `print`** (außer in `scripts/`).
- **Konfiguration** (Schwellen, Modellname, Timeouts, Keyword-Listen) nur in `config.py`, keine Magic Numbers in Detektoren.
- **Formatierung:** `ruff format`; Lint: `ruff check` (Regeln: E, F, I, B, UP).
- **Naming:** Module/Funktionen `snake_case`, Klassen `PascalCase`, Detektoren `detect_<name>`, Konstanten `UPPER_CASE`.
- **Docstring** (1–3 Zeilen) für jede öffentliche Funktion: was sie tut, was sie zurückgibt, wann sie leer zurückgibt.

### 16.4 LLM-Regeln

- Prompts liegen als `.md`-Dateien in `llm/prompts/`, **nicht** als Strings im Code.
- Das LLM **rechnet nie**. Jede Zahl, die im Output erscheinen darf, steht vorformatiert in einem Fact.
- Immer strukturierter Output (Tool-Call mit Schema) + Pydantic-Validierung + Validator.
- Jeder LLM-Call hat Timeout, max. 1 Retry, und einen deterministischen Fallback.
- Alle Prompts/Antworten werden nach `logs/llm/` geloggt.
- Modellname nur aus `config.py`.
- Prompt-Änderungen immer an ≥ 3 verschiedenen Kunden testen (`smoke_all_clients.py --llm 3`), nicht nur am Demo-Kunden.

### 16.5 Frontend-Regeln

- TypeScript `strict`, keine `any` (außer an der fetch-Grenze mit sofortigem Cast auf Typ aus `types/api.ts`).
- Funktionale Komponenten, eine Komponente pro Datei, < ~150 Zeilen.
- Alle API-Aufrufe über `src/api/client.ts`; Komponenten rufen nie direkt `fetch`.
- Farben/Abstände über Tailwind-Tokens (`uro-*`, semantische `tone-*`), keine Hex-Werte in Komponenten.
- Jeder async-Zustand hat Loading, Error (mit Retry) und Empty State.
- Nach Änderungen: `npm run typecheck` und `npm run build` müssen grün sein.

### 16.6 Definition of Done (für jede Aufgabe)

- [ ] Funktion implementiert gemäß Spec-Abschnitt
- [ ] Tests geschrieben und grün (`make test`)
- [ ] Lint/Typecheck grün (`make lint`)
- [ ] Bei Backend-Analytics: `make smoke` ohne Fehler
- [ ] Bei UI: im Browser geprüft
- [ ] Commit mit aussagekräftiger Message

---

## 17. Scope: Was wir NICHT bauen

- ❌ Ex-Custody-PDF-Import (Bonus 1)
- ❌ Voice-Briefing, separate Action-Card-Ansichten als eigenes Bonus-Feature
- ❌ Login/Auth, Mehrbenutzer
- ❌ Datenbank, persistente Speicherung
- ❌ Datei-Cache für yfinance (Teamentscheidung; nur In-Memory-Memo)
- ❌ Echte Trades, Order-Erstellung, Proposal-Bearbeitung
- ❌ Bereinigung der Performance um Ein-/Auszahlungen (Transactions) — als Einschränkung dokumentiert
- ❌ Korrelationsbasierte Risikomodelle
- ❌ Eigene ESG-Ausschlusslisten (Waffen etc.) — Daten enthalten nur Scores
- ❌ Streaming-Antworten (nur Stretch, wenn Zeit übrig)
- ❌ Mobile Layout
- ❌ Deployment in die Cloud (lokale Demo)

---

## 18. Präsentation & Demo

### 18.1 Folien (max. 8, kurz — „get to the point“)

1. **Problem:** Advisor hat 60 Sekunden, Infos in 5 Systemen verteilt.
2. **Live-Demo** (Hauptteil, ~4 min) — siehe 18.2.
3. **Wie es funktioniert:** Pipeline-Diagramm (4.2) — „Python rechnet, Claude erzählt, Validator prüft“.
4. **Ranking-Logik:** Tabelle base_severity × magnitude × boost mit Beispiel (5.16).
5. **Grounding:** Source-IDs, Validator, Fallback; Fakt vs. Market vs. Assessment.
6. **Datenquellen:** Mock (Kunden/Portfolio/CRM, House View) vs. Live (Yahoo Finance).
7. **Produktionsweg in URO:** URO-API statt JSON, professionelle News (Bloomberg/Refinitiv), interne CIO-Publikationen, ESG-Datenfeed (MSCI), Performance-Attribution aus dem Portfolio-System, Audit-Log.
8. **Pilot-Vorschlag:** 5–10 Advisor, gemessen: Vorbereitungszeit, Nutzungsrate, Feedback zu Actions.

### 18.2 Demo-Ablauf

1. Client-Liste → Demo-Kunde mit klarer Story öffnen (vorher per Smoke-Test ausgewählt: Violation + negative Performance + Notiz mit Lebensereignis).
2. „Generate Briefing“ → Ladeschritte → Briefing (< 15 s).
3. Source-Chip anklicken → zeigt Fact + Datenquelle („keine Halluzination“).
4. Chat: „What is the client's total semiconductor exposure?“ → Antwort mit Look-through.
5. **Upload des unbekannten Testkunden** → neuer Kunde erscheint mit „NEW“ → Briefing generieren.
6. (Optional) Robustheit: Hinweis auf Fallback-Modus.

---

## 19. Offene Punkte (🔍 im Spike klären)

Der Spike ist **Schritt 0** der Umsetzung (max. 45 min). Ergebnis: `docs/data-notes.md`.

**`scripts/inspect_data.py` soll ausgeben:**
1. Alle Keys eines Beispiel-Portfolios und einer Beispiel-Position (Marktwert-Feld? Währung? SecurityId?).
2. Wie Portfolio ↔ SAA/Strategie verknüpft sind.
3. Alle distinct Werte von `SAA_AssetClassName`, `SAA_CountryGroupName`, `SAA_IndustryName`, `SAA_CurrencyGroupName`, `IndustryName`, `SecurityTypeName`.
4. Alle `Dimension`/`Category`-Kombinationen in `StrategicAssetAllocations[].Mappings`.
5. Felder von `FundUnbundlingMappings` (welche Dimension, welcher Fonds-Key).
6. Alle `RuleCode` + Beschreibung aus `SuitabilityRules`; Beispiele für `ViolationPath`; welche RuleCodes ESG-bezogen sind.
7. `EsgProfiles` komplett; Wertebereich `SustainabilityScore` (min/max/Median) — Skalenrichtung.
8. `RiskProfiles` komplett (gibt es Volatilitätsgrenzen?).
9. `ProposalStatuses` komplett → welche gelten als offen?
10. Pro Kunde: #Portfolios, #Positionen, #Violations, #offene Proposals, #Notizen, hat PerformanceHistory? → Kandidaten für Demo-Kunden.
11. Min/Max-Datum in `PerformanceHistory` → Offset zur Realzeit.
12. Sprache/Beispiele der `ClientNotes`.

**`scripts/spike_yfinance.py` soll testen:**
1. ISIN → Ticker via `yf.Search` für die 20 größten Aktienpositionen über alle Kunden → Trefferquote.
2. `yf.Ticker(t).news` für 3 Ticker → Format (neu/alt), Anzahl, Aktualität.
3. `yf.download` Batch für 10 Ticker + Proxies → Dauer.
4. `yf.Search("semiconductor stocks", news_count=5).news` → brauchbar?
5. Gesamtdauer eines realistischen Market-Schritts (Ziel < 8 s).

**Entscheidungen nach dem Spike:**
- Wenn Ticker-Trefferquote < 50 %: `ticker_overrides.json` für die Top-Positionen der Demo-Kunden manuell befüllen **und** Treiberanalyse auf Asset-Klassen-Ebene ergänzen (Proxy-ETF je `SAA_AssetClassName`).
- House-View-Keys an echte Kategorienamen anpassen.
- `sector_proxies.json` an echte `IndustryName`-Werte anpassen.

---

## Anhang A: CLAUDE.md-Vorlage

In das Projekt-Root als `CLAUDE.md` kopieren:

```markdown
# URO Briefing Assistant — Agent Guide

Hackathon prototype (START Hack, UnRiskOmega "From Ping to Pitch"). 60-second AI client briefing for wealth managers inside a mocked URO Advisor Pro UI.

**Full spec:** docs/superpowers/specs/2026-09-18-uro-briefing-assistant-design.md — read the relevant section before every task.
**Data findings:** docs/data-notes.md — real field names and categories. Never invent field names; inspect data with backend/scripts/inspect_data.py.

## Core principle
Python computes every number and finding (analytics/ → Facts with IDs F*/N*/H*/C*). Claude only writes the storyline from those Facts and must cite IDs. A validator checks IDs and numbers; on failure 1 retry, then a deterministic fallback briefing. The briefing endpoint always returns a briefing.

## Commands
- Backend: `cd backend && uv run uvicorn app.main:app --reload --port 8000`
- Frontend: `cd frontend && npm run dev`
- Tests: `make test` · Lint/types: `make lint` · All clients smoke test: `make smoke`

## Rules
- Small steps. After every change: `make test` + `make lint` (frontend: `npm run typecheck && npm run build`). UI changes: check in browser.
- Layering: api → services → analytics|market|houseview|llm → models|data. analytics/ is pure (no I/O, no network, no LLM, no date.today()).
- yfinance only in market/, Anthropic SDK only in llm/, JSON file reading only in data/.
- Missing fields are omitted in the data: use Optional fields / .get(). Join on SecurityId, not ISIN. Fractions 0–1 everywhere; FundUnbundlingMappings.Weight is 0–100 → converted once in data/loader.py. Use SAA_* fields for allocation comparisons. Data dates are shifted: use ctx.data_as_of, not today.
- All number formatting via analytics/format.py. All thresholds in config.py.
- Contracts (models/facts.py, models/briefing.py, models/api.py, frontend/src/types/api.ts, fixtures) change together in one commit prefixed "CONTRACT CHANGE:".
- No demo hacks: never special-case a client ID/name. An unseen client will be uploaded at the pitch.
- Prompts live in llm/prompts/*.md. Test prompt changes on ≥3 clients.
- No new features beyond the spec (see "Scope: what we do NOT build").
- Code, comments, UI and LLM output in English.
- Never commit .env or logs/.
- Commit style: feat(scope): …, fix(scope): …, test(scope): …
```

---

## Anhang B: Glossar Finanzbegriffe

| Begriff | Bedeutung |
|---|---|
| **AuM** | Assets under Management — verwaltetes Vermögen des Kunden |
| **Position** | Ein einzelnes Wertpapier im Depot |
| **Gewicht** | Anteil einer Position am Gesamtvermögen (0–1) |
| **Asset-Klasse** | Grobe Anlagekategorie: Liquidität, Anleihen, Aktien, Alternative |
| **SAA** | Strategic Asset Allocation — vereinbarte Ziel-Mischung mit Min/Ziel/Max je Kategorie |
| **Rebalancing** | Umschichten, um wieder zur SAA zurückzukehren |
| **Contribution / Beitrag** | Gewicht × Rendite einer Position = ihr Anteil an der Portfolio-Rendite (in Prozentpunkten, pp) |
| **pp** | Prozentpunkte — Differenz zweier Prozentwerte (66 % vs 50 % = 16 pp) |
| **Suitability** | Eignung: passt ein Produkt zu Risikoprofil, Wissen, Erfahrung des Kunden (FIDLEG/MiFID II) |
| **Investment-Rule** | Regel der Bank oder des Kunden, z. B. max. 10 % pro Einzeltitel |
| **Violation** | Verstoß gegen eine Suitability-/Investment-Regel (in den Daten vorberechnet) |
| **Konzentration** | Zu großer Anteil in einem Titel/Sektor/Währung/Land |
| **Look-through** | Fonds in ihre Bestandteile zerlegen, um verstecktes Exposure zu sehen |
| **Volatilität** | Typische jährliche Schwankungsbreite eines Kurses (0.38 = 38 %) |
| **Risikobeitrag** | Hier vereinfacht Gewicht × Volatilität |
| **PRC** | Product Risk Class — Risikoklasse eines Produkts |
| **ESG** | Environmental, Social, Governance — Nachhaltigkeit; hier über `SustainabilityScore` und Kunden-Mindestwerte |
| **Proposal** | Anlagevorschlag des Beraters an den Kunden (offen oder umgesetzt) |
| **House View / CIO View** | Offizielle Marktmeinung der Bank: welche Anlageklassen/Regionen/Sektoren über-/untergewichten |
| **Overweight / Underweight** | Mehr / weniger als die neutrale Gewichtung halten |
| **Fälligkeit (Maturity)** | Datum, an dem eine Anleihe zurückgezahlt wird → Geld muss neu angelegt werden |
| **Next Best Action** | Konkrete, priorisierte Handlungsempfehlung für den Berater |
