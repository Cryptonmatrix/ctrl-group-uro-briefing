# Data Notes — verifizierte Feldnamen, Kategorien und Fallen

> **Ergebnis von Schritt 0 („Spike") der Design-Spec (§19).** Alle Zahlen hier wurden am **2026-09-19, 00:20** direkt
> aus `data/clients.json` und `data/reference.json` gemessen — nicht aus `DATA.md` abgeschrieben.
> **Wo DATA.md und Daten widersprechen, gilt dieses Dokument.** Die drei neuen Client-Dateien und der
> unbekannte Testklient können wieder abweichen → der Loader bleibt in jedem Fall defensiv (`obj.get(k) or default`).
>
> Für Coding-Agenten: **Feldnamen und Kategorie-Strings aus diesem Dokument kopieren, nie raten.**

---

## 1. Überblick

| Größe | Wert |
|---|---|
| Klienten | 47 (`CASE-001` … `CASE-047`), 43 Privatpersonen + 4 Firmen (`Company 00x AG`) |
| Portfolios | 57 — 38 Klienten mit 1, 8 mit 2, 1 mit 3 Portfolios |
| Securities (Stammdaten) | 504 |
| FundUnbundlingMappings | 48'101 Zeilen für 141 Fonds |
| SuitabilityViolations | 180 (96 Error / 84 Warning) bei 27 Klienten; 20 Klienten haben `null` |
| Proposals | 206 (Final 125 · Abgelehnt 76 · Entwurf 5) |
| ClientNotes | 153, **alle Englisch**, 1–6 pro Klient, jeder Klient hat welche |
| ReportingCurrency / PortfolioCurrency | **immer CHF** (47/47 bzw. 57/57) → im MVP kein FX nötig; trotzdem nicht hartcodieren |
| PerformanceHistory | 57/57 Portfolios, je 58 Monatspunkte, `2021-10-01` … `2026-07-01` |
| `PerformanceYTD` | **auf 0 von 57 Portfolios vorhanden** → selbst rechnen |

## 2. Wo DATA.md nachweislich NICHT stimmt

| DATA.md behauptet | Gemessene Realität | Konsequenz im Code |
|---|---|---|
| Fehlende Felder sind *abwesend*, nie `null` | Auf Klient-Ebene sind **alle Keys immer vorhanden**, viele mit `null`: `SuitabilityViolations` 20×, `EsgProfileId` 19×, `Transactions` 18×, `Proposals` 17×, `IndividualRuleOverrides` 44×, `RiskProfileId` 4×, `Birthday` 4×, `FirstName/LastName` 4×, `Company` 43× | **Immer `obj.get(k) or []` / `or default`.** Ein `in`-Check oder ein nacktes `.get()` reicht nicht. Pydantic: `Optional[...] = None` **und** `list`-Felder mit Validator `None → []` |
| `ClientNotes[].Note` ist Deutsch oder Französisch | **153/153 Englisch** | Keyword-Listen englisch zuerst; DE/FR-Wörter als billige Zugabe behalten (neue Dateien!) |
| `FundUnbundlingMappings`: genau eine der vier Dimensionen ist pro Zeile „gemeint" | **Jede Zeile trägt alle vier Namen** (`AssetClassName`, `CurrencyGroupName`, `CountryGroupName`, `IndustryName`). Zeilen sind das Kreuzprodukt; `Σ Weight` über **alle** Zeilen eines Fonds = 100.0 (min = max = median = 100.0) | `groupby(<eine Dimension>).sum(Weight)` liefert direkt die Aufteilung in dieser Dimension. **Nicht** je Dimension separat filtern |
| `AccountPositions[].IBAN` ist real und durchgereicht | **0 IBANs in diesem Export**; der Key existiert in keiner Account-Position. Keys: `AccountName`, `Currency`, `PortfolioValuePercentage`, `TotalAmountInPortfolioCurrency` | `strip_pii()` trotzdem bauen (Schema erlaubt IBAN, neue Dateien können sie enthalten). Pitch-Formulierung: „Das Schema führt IBANs, wir entfernen sie im Ingest" — **nicht** „die Daten enthalten echte IBANs" |
| `Proposals[].ProposedDateUTC` vorhanden | **16 von 206 fehlen** | `.get()`, Alter nur berechnen wenn vorhanden |
| `Mappings[]` haben Min/Target/Max | **258 von 333 ohne Min/Max**, 16 ohne Target. Nur `AssetClass`-Zeilen haben Min/Target/Max; `CurrencyGroup`/`CountryGroup`/`Industry` haben **nur Target** | AssetClass: Bandverletzung (`actual < Min` / `> Max`). Andere Dimensionen: Abweichung vs. Target mit fester Schwelle (Vorschlag ≥ 10 pp) |
| `Tags[]` = 17 Einträge | 19 | egal, nur nicht hartcodieren |
| `Securities[].SAA_IndustryName` gesetzt | **`None` bei 290 von 504** (Anleihen, Fonds, Liquidität) | Branchen-Exposure nur mit Fonds-Look-through sinnvoll |

## 3. Exakte Kategorie-Strings (Copy-Paste, inkl. Tippfehler!)

Diese Strings sind die Join-Keys zwischen `Securities[].SAA_*`, `StrategicAssetAllocations[].Mappings[].Category` und `house_view.json`. **Zeichengenau übernehmen.**

| Dimension | Werte (Security-Anzahl) |
|---|---|
| `AssetClass` | `Shares` (324) · `Bonds` (117) · **`Specialties andCommodities`** (50, fehlendes Leerzeichen ist Original!) · `Real estate` (8) · `Liquidity` (5) |
| `CurrencyGroup` | `Swiss francs` (244) · `US-Dollar` (162) · `Euro` (84) · `Andere` (14) |
| `CountryGroup` | `Switzerland` (172) · `Others` (150) · `Rest of Europe` (82) · `North America` (71) · `Great Britain` (19) · `Not classified` (5) · `Japan` (3) · `Asia/Pacific (ex Japan)` (2) |
| `Industry` | `Industrials` (43) · `Health Care` (34) · `Financials` (33) · `Consumer Discretionary` (21) · `Information Technology` (21) · `Consumer Staples` (19) · `Materials` (15) · `Telecommunication Services` (9) · `Real Estate` (7) · `Utilities` (7) · `Energy` (5) |

**Achtung Look-through:** `FundUnbundlingMappings[].IndustryName` nutzt `Raw materials` (statt `Materials`) und `Communication Services` (statt `Telecommunication Services`) → Mapping-Tabelle in `config.py`. `FundUnbundlingMappings[].AssetClassName` ist die **feine** Taxonomie (`Equities EmMa`, `Equities Switzerland`, …), nicht die SAA-Ebene → für AssetClass-Look-through per Präfix mappen: `Equities *` → `Shares`, `Bonds *` → `Bonds`, sonst in `config.py` nachtragen (🔍 vollständige Liste beim Implementieren ausgeben).

`SecurityTypeName`: `Investment fund` (226) · `Shares` (181) · `Bonds, debt register claims` (64) · `Hybrids/certificates with an interest rate component` (17) · `Hybrids/certificates without an interest rate component` (9) · `Time deposit investments` (2) · `Precious metals` · `Strukturierte Produkte/Zertifikate` · `Participation certificate` · `Warrant` · `Dividend right certificates` (je 1).

## 4. Portfolio & Positionen — echte Keys

```
Portfolio:        AccountPositions, AssetsUnderManagementInDefaultCurrency, ExpectedReturn, FactoryDateUtc,
                  InvestmentServiceId, InvestmentServiceName, LiquidityInDefaultCurrency, Name, PerformanceHistory,
                  PortfolioCurrency, PortfolioId, PortfolioNr, PublicGuid, ReferenceCurrency, SecurityPositions,
                  StrategicAssetAllocationId, StrategyId, StrategyName, ValueAtRisk, Volatility
SecurityPosition: ContributionVolatility, Currency, Isin, MarginalContributionToRisk, PortfolioValuePercentage (0–1),
                  PricePerUnit, Quantity, SecurityId, SecurityName, TotalAmountInPortfolioCurrency, Valor
AccountPosition:  AccountName, Currency, PortfolioValuePercentage, TotalAmountInPortfolioCurrency
```

- **Marktwert** = `TotalAmountInPortfolioCurrency` (CHF). Gewicht im Portfolio = `PortfolioValuePercentage` (0–1). Gewicht am Gesamtvermögen des Klienten = `TotalAmountInPortfolioCurrency / Σ AuM aller Portfolios`.
- **Risiko:** `ContributionVolatility` summiert sich über die Positionen zu `Portfolio.Volatility`. Das ist die fertige Risk-Share-Tabelle — nichts selbst modellieren.
- **Liquidität** = `AccountPositions[]` (Summe) bzw. `LiquidityInDefaultCurrency`. Krypto-Konten: `Currency` ∈ {`BTC` 2, `ETH` 2, `SOL` 2, `OZG` 1, `SHIB` 1} bei 123 Kontopositionen. Kategorie „Crypto", nicht als ISO-Währung behandeln.
- `Volatility` fehlt bei 7/57 Portfolios; `StrategicAssetAllocationId` ist bei **57/57** gesetzt.
- 2 Klienten haben **0 Wertpapierpositionen und 100 % Liquidität** (`CASE-001` Yoda, `CASE-046` Tony Montana). Muss ohne Crash laufen → Chance-Finding „Cash uninvested".

## 5. SAA — die wichtigste Falle: „No strategy"

`StrategyName`: **`No strategy` 29×**, `Investor profile 6` 13×, `Investor profile 5` 11×, `Investor profile 7` 3×, `Investor profile 3` 1×.

Die 29 „No strategy"-Portfolios hängen an den SAAs `1`, `31`, `39`, `87`, `96` (Namen: `Execution only / … / Keine Strategie`, `Vorsorgeprodukte / CHF / Keine Strategie`, `Anlageberatung / CHF / Keine Strategie`, `Standard Portfolio / CHF / Keine Strategie`, `Consolidaton Investmentservice / CHF / no strategy`). Deren AssetClass-Mappings sind **Min 0.0 / Target 0.0 / Max 1.0 für alle fünf Klassen** → SAA-Abgleich ist dort **inhaltsleer**.

**Konsequenzen:**
1. `PortfolioFact.has_real_saa = StrategyName != "No strategy"` (bzw. `not all(Max == 1.0)`). SAA-Deviation-Findings nur bei `has_real_saa`.
2. Bei `has_real_saa == False`: **kein** „Target 0 %"-Unsinn erzeugen. Stattdessen ein `INFO`-Finding „No strategic asset allocation assigned — allocation not checked against a target" **und** der Risikoprofil-Check (§7) übernimmt die Rolle des Leitplanken-Vergleichs. Optional: `RiskProfiles[].EquityQuoteInPercent` als weiche Aktien-Obergrenze.
3. Genau das ist der Pitch-Befund aus `CLAUDE.md` §4: bei 11 Portfolios ohne Strategie feuert die Regel-Engine nie, obwohl `Volatility > MaxVola`.

Beispiel einer **echten** SAA (Id 92, `Vorsorge Individuell - Depotberatung / CHF / Anlageprofil 5`):

```
AssetClass:    Shares 0.20/0.45/0.85 · Real estate 0.00/0.05/0.15 · Bonds 0.10/0.47/0.70 · Liquidity 0.00/0.03/0.60 · Specialties andCommodities 0.00/0.00/0.20
CurrencyGroup: Swiss francs T=0.515 · US-Dollar T=0.305 · Euro T=0.04 · Andere T=0.14           (nur Target)
CountryGroup:  Switzerland T=0.5157 · North America T=0.31477 · Asia/Pacific (ex Japan) T=0.06105 · … · Not classified (kein Target)
Industry:      Health Care T=0.24347 · Consumer Staples T=0.15823 · Financials T=0.14375 · Information Technology T=0.10949 · …
```

SAA-Keys: `Id`, `Description`, `InvestmentServiceId`, `StrategyId`, `ReferenceCurrency`, `Mappings`; **`Name` fehlt bei 3 von 16** → `saa.get("Name") or saa.get("Description")`.

**Bezugsbasis der Targets (gemessen 2026-09-19, A2):** In allen 11 echten SAAs summieren sich die Targets **je Dimension** auf 1.000.
Region (`CountryGroup`) und Branche (`Industry`) beziehen sich deshalb auf den **Aktienanteil**, nicht aufs ganze Portfolio; Währung und
Asset-Klasse aufs ganze Portfolio. Gegenprobe an den `ViolationPath`-Werten der Bank (aktienrelativ, mit Fonds-Look-through gerechnet):

| Klient | Regel | Bank `LeftValue` | unsere Rechnung aktienrelativ | portfoliorelativ |
|---|---|---|---|---|
| CASE-002 | Overweight in the equity sector "Industrials" | 0.1576 | **0.1576** | 0.0820 |
| CASE-002 | Underweight in the equity sector "Consumer Staples" | 0.0882 | **0.0882** | 0.0459 |
| CASE-004 | Overweight in the equity sector "Energy" | 0.0771 | 0.0526 | 0.0335 |

Zwei exakte Treffer, ein Ausreisser (CASE-004 Energy — vermutlich andere Branchenzuordnung einzelner Titel; nicht weiter verfolgt).
Die `ViolationPath`-Paare der Über-/Untergewichtsregeln sind (Ist, Obergrenze) und (Ist, Untergrenze) = Target ± 5 pp.

**Look-through-Namen ≠ SAA-Namen:** `CountryGroupName` der Fonds-Zeilen ist `Equities North America`, `Equities Euroland`, `Equities Switzerland`,
`Equities Pacific`, `Equities Japan`, `Aktien UK`, `Equities EmMa` → Mapping in `config.LOOKTHROUGH_COUNTRY_MAP`. `CurrencyGroupName` hat 43 Werte
(`Japanese yen`, `Hong Kong Dollar`, …) → alles ausser Swiss francs / US-Dollar / Euro wird `Andere`. `AssetClassName` der Zeilen ist nur
`Equities EmMa` / `Equities Switzerland`; alle 224 gehaltenen Look-through-Fonds sind laut `SAA_AssetClassName` "Shares" → für die Asset-Klasse
kein Look-through nötig.

## 6. Fonds-Look-through

- 141 der 226 Fonds haben Mappings (1 bis 2'958 Zeilen pro Fonds). `Weight` ist **0–100**, Summe 100 pro Fonds. **Negative Gewichte existieren** (min −15.05) → nicht auf ≥ 0 clampen, einfach summieren.
- Exposure eines Klienten in Branche X = Σ direkte Aktienpositionen mit `SAA_IndustryName == X` + Σ (Fondsgewicht × `Weight/100` der Zeilen mit `IndustryName ↦ X`).
- `Weight/100` **genau einmal** in `ingest.py` / Reference-Index umrechnen (Spec §16.3).

## 7. Risikoprofile, Strategien, ESG

**RiskProfiles** (`Id`, `Name`, `Description`, `RiskLevel`, `MaxVola`, `MaxPRC`, `EquityQuoteInPercent`):

| Id | Name | MaxVola | MaxPRC | EquityQuote | Klienten |
|---|---|---|---|---|---|
| 15 | Anlageprofil 3 | 0.075 | 4 | 0.45 | 1 |
| 16 | Anlageprofil 4 | 0.100 | 6 | 0.65 | 4 |
| 17 | Anlageprofil 5 | 0.120 | 7 | 0.85 | 18 |
| 18 | Anlageprofil 6 | 0.150 | 7 | 1.00 | 15 |
| 19 | Anlageprofil 7 | 0.185 | 7 | 1.00 | 5 |
| — | *kein Profil* | — | — | — | **4** (`CASE-029`…`032`) → `DATA_GAP` |

„Konservativ" für Boosts: `RiskLevel <= 4` (Anlageprofil 3/4). Die Namen enthalten keine Wörter wie „conservative" — die Spec-Heuristik über Namensbestandteile greift **nicht**, `RiskLevel` verwenden.

**Strategies** (`Name`, `RiskLevel`, `VolatilityMinimum`, `VolatilityMaximum`): Investor profile 3 (0.055–0.075) · 4 (0.07–0.10) · 5 (0.085–0.12) · 6 (0.105–0.15) · 7 (0.135–0.185) · **No strategy (0.0–1.0)**.

**EsgProfiles:** `Yes` → `MinimumLevel 5.714`, `MinimumPositionLevel 5.714`, `MaximumLevel 10`; `No` → 0.001. `SustainabilityScore` liegt auf **0–10, höher = besser** (n = 432, Median 7.1). Klienten: `Yes` 17 · `No` 11 · kein Profil 19.

## 8. Suitability-Verstöße

- 180 Verstöße: `Error` 96 / `Warning` 84. `SecurityIsin` nur bei 31, `ViolationPath` bei 177.
- `RuleCode` ist **bereits Englisch** und der Join-Key zu `SuitabilityRules[].RuleCode` (54 Regeln). Top: `Cluster risk of a single financial instrument` 23× · `Underweight in the equity sector "Consumer Staples"` 10× · `Underweight in the equity region "Asia/Pacific (ex Japan)"` 10× · `Volatility range undershot (portfolio risk too low)` 8× · `Underweight in the equity sector "Consumer Discretionary"` 8× · `Compliance with maximum volatility` 7× · `Overweight in the equity sector "Industrials"` 7× · `Foreign currency cluster risk EUR` 6×.
- `RuleDescription` ist Deutsch (Langtext). Für das Briefing reicht `RuleCode`.
- `ViolationPath[].FieldName` ist technisch (z. B. `SimulationVolatilityRuleField\`1`, `RegulatoryClientTypeRuleField\`1`) → **nie roh anzeigen**. `LeftValue`/`RightValue` nur als „actual vs. limit" verwenden, wenn der RuleCode die Semantik eindeutig macht (Volatilitäts- und Gewichtsregeln: Brüche → Prozent formatieren).

## 9. Proposals

`ProposalStatuses`: `Entwurf` (1, kein Submit) · `Final` (3, Submit erlaubt) · `Abgelehnt` (4, archiviert). `AdvisoryTypes`: `Depot meeting` (Review) · `Investment proposal`.

| Status | TransactionsSubmittedDateUTC gesetzt | Anzahl | Bedeutung für uns |
|---|---|---|---|
| Entwurf | nein | 5 | **offen** (Entwurf) |
| Final | nein | 65 | **offen** — finalisiert, aber nie umgesetzt → Follow-up |
| Final | ja | 60 | umgesetzt → Kontext („last time we did …") |
| Abgelehnt | nein | 76 | **vom Kunden abgelehnt** → starke Präferenz-Information, niedrig priorisiertes Kontext-Finding |

`ProposedDateUTC` reicht bis **2026-09-19** (= heute; die Daten sind auf „aktuell" verschoben). Proposal-`SecurityPositions[]` haben `Isin`, `SecurityName`, `Quantity`, `PricePerUnit`, `Currency`, `TotalAmountInProposalCurrency`, `ProposalValuePercentage` (0–1) — **keine `SecurityId`** → Join über `Isin` (Fallback-Index, erste Übereinstimmung in CHF bevorzugen).

## 10. Notizen und Tags

- 153 Notizen, `2024-09-17` … `2026-09-14`, Englisch, kurz (1 Satz). Beispiele: `No direct positions in fossil fuels, please.` · `Plans to retire in the next two years, increasing liquidity needs expected.` · `Prefers to keep a cash reserve on hand for unexpected medical expenses.` · `Needs approximately CHF 15,000 in liquid funds for the Q1 tax payment.` · `Extremely patient investor; unconcerned by short-term volatility`.
- Inhaltstypen: Liquiditätsbedarf mit Betrag, Lebensereignis (Pension, Umzug, Vollmacht), Risikohaltung (beide Richtungen!), ESG/Ausschlüsse, Einkommensfokus, Stil-Präferenzen. **Risikohaltung kann auch „unconcerned by volatility" sein** → kein blinder „risk_averse"-Boost auf das Wort „volatility".
- `Tags` auf Klienten: `Financials` 7 · `Health Care` 6 · `Rest of Europe` 6 · `Japan` 5 · `Consumer Discretionary` 5 · … (`TagTypeName` Region/Industry).

## 11. Zeitachse (Datenzeit ≠ Realzeit, aber fast)

| Quelle | Bereich |
|---|---|
| `PerformanceHistory.Date` | 2021-10-01 … **2026-07-01** (monatlich) |
| `ClientNotes.CreatedByDateUTC` | 2024-09-17 … 2026-09-14 |
| `Proposals.ProposedDateUTC` | 2023-05-22 … 2026-09-19 |
| `ProfilingDateUtc` | 2022-07-31 … 2026-08-22 |

**Entscheidung:** `history_as_of = max(PerformanceHistory.Date)` (Renditen, im UI „data as of 01 Jul 2026"); `data_as_of = max(aller Datumsfelder des Klienten)` für Alters-Berechnungen (Proposal offen seit, Notiz-Alter, Profil-Alter). **Niemals `date.today()` in `analytics/`.** Marktdaten (yfinance) laufen in Realzeit und werden im UI getrennt beschriftet.

## 12. Der Befund: Volatilität über Profil-Limit ohne gemeldeten Verstoß

Gemessen: **14 Portfolios** mit `Portfolio.Volatility > RiskProfile.MaxVola`, davon **11 mit 0 gemeldeten Verstößen** — exakt wie in `CLAUDE.md` §4 behauptet.

| Klient | Portfolio | Strategie | Vola | MaxVola | Faktor | gemeldete Verstöße |
|---|---|---|---|---|---|---|
| CASE-011 Ellen Ripley | -01 | No strategy | 60.6 % | 15.0 % | 4.0× | 0 |
| CASE-021 Holden Caulfield | -01 | No strategy | 21.6 % | 7.5 % | 2.9× | 0 |
| CASE-014 Katniss Everdeen | -02 | No strategy | 22.0 % | 10.0 % | 2.2× | 0 |
| CASE-015 Porky Pig | -01 | No strategy | 29.3 % | 15.0 % | 2.0× | 0 |
| CASE-018 Company 002 AG | -01 | Investor profile 7 | 29.3 % | 15.0 % | 2.0× | 19 |
| CASE-028 Charles Foster Kane | -01 | No strategy | 22.0 % | 12.0 % | 1.8× | 0 |
| CASE-003 Ron Burgundy | -01 | No strategy | 20.0 % | 12.0 % | 1.7× | 0 |
| CASE-023 Frodo Beutlin | -01 | Investor profile 5 | 24.5 % | 18.5 % | 1.3× | 0 |
| CASE-012 Company 001 AG | -01 | Investor profile 6 | 18.4 % | 15.0 % | 1.2× | 21 |
| CASE-013 Thomas | -01 | No strategy | 11.9 % | 10.0 % | 1.2× | 0 |
| CASE-042 Zorro | -01 | Investor profile 6 | 11.9 % | 10.0 % | 1.2× | 6 |
| CASE-010 Son Goku | -01 | No strategy | 12.8 % | 12.0 % | 1.1× | 0 |
| CASE-006 Spock | -01 | No strategy | 12.6 % | 12.0 % | 1.1× | 0 |
| CASE-027 Buzz Lightyear | -01 | No strategy | 12.2 % | 12.0 % | 1.0× | 0 |

Implementierung: `analytics/suitability.py::risk_profile_findings()` → `FindingType.RISK_PROFILE`, `Severity.ERROR` wenn Faktor ≥ 1.2, sonst `WARNING`. Fehlt `Volatility` oder `RiskProfileId` → `DATA_GAP`.

## 13. Demo-Kandidaten (aus den Daten belegt)

Spalten: Portfolios · Positionen · Verstöße (Errors) · offene Proposals · abgelehnte Proposals · Notizen · AuM CHF · Liquidität % · Risikoprofil · ESG · max. Portfolio-Vola / MaxVola

| Ref | Name | Pf | Pos | Viol (E) | offen | abgel. | Notizen | AuM | Liq % | Profil | ESG | Vola/Max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CASE-003 | Ron Burgundy | 1 | 2 | 0 (0) | 0 | 0 | 5 | 140'592 | 3.0 | AP 5 | No | 0.200/0.12 |
| CASE-011 | Ellen Ripley | 1 | 9 | 0 (0) | 0 | 0 | 4 | 100'741 | 7.1 | AP 6 | No | 0.606/0.15 |
| CASE-012 | Company 001 AG | 1 | 5 | 21 (13) | 5 | 12 | 2 | 44'396 | 0.7 | AP 6 | — | 0.184/0.15 |
| CASE-016 | Holly Golightly | 1 | 1 | 0 (0) | 0 | 0 | 3 | 363'825 | 41.4 | AP 5 | Yes | 0.000/0.12 |
| CASE-021 | Holden Caulfield | 2 | 1 | 0 (0) | 0 | 0 | 3 | 759'349 | 34.2 | AP 3 | — | 0.216/0.075 |
| CASE-018 | Company 002 AG | 1 | 8 | 19 (13) | 1 | 3 | 1 | 3'102'393 | 9.4 | AP 6 | — | 0.293/0.15 |
| CASE-038 | Charlie Brown | 2 | 88 | 18 (12) | 7 | 5 | 4 | 1'619'901 | 2.1 | AP 6 | — | 0.114/0.15 |
| CASE-022 | Company 003 AG | 1 | 18 | 13 (6) | 6 | 0 | 1 | 6'381'729 | 14.7 | AP 5 | — | 0.106/0.12 |
| CASE-044 | Ralph Kramden | 1 | 12 | 12 (4) | 0 | 1 | 5 | 172'265 | 22.6 | AP 6 | Yes | 0.106/0.15 |
| CASE-001 | Yoda | 1 | **0** | 5 (5) | 2 | 5 | 6 | 726'485 | **100.0** | AP 5 | Yes | —/0.12 |
| CASE-002 | Joker | 1 | 15 | 3 (1) | 2 | **11** | 2 | 184'753 | 1.7 | AP 5 | — | 0.082/0.12 |
| CASE-017 | Hulk | 1 | 36 | 2 (0) | **9** | 5 | 3 | 1'110'288 | 4.4 | AP 6 | No | 0.107/0.15 |
| CASE-029 | Scarlett O'Hara | 1 | 13 | 0 | 0 | 0 | 4 | 102'188 | 1.8 | **kein Profil** | No | 0.079/— |

**Demo-Reihenfolge (Empfehlung, siehe Strategieplan §7):** CASE-003 (Eröffnung: 97 % in 2 Titeln, Vola-Limit gerissen, 0 Verstöße, Notiz „retire in two years" + „no defense/tobacco" + „high-dividend focus") → CASE-011 (der Hammer, 4×) → CASE-012 vs. CASE-016 (dieselbe Notiz „CHF 15,000 für Q1-Steuern", einmal CHF 328 liquide, einmal CHF 150'625) → Live-Upload.
Edge-Cases für den Robustheitsbeweis: CASE-001 (nur Cash), CASE-029 (kein Risikoprofil → `DATA_GAP`), CASE-038 (88 Positionen, 2 Portfolios).

## 14. Offene Spike-Punkte (noch nicht gemessen)

- **yfinance ISIN→Ticker-Trefferquote** für die Top-20-Aktienpositionen (Gianluca, 08:00, 20 min, `scripts/spike_yfinance.py`). Schweizer Titel brauchen `.SW`. Bei < 50 % Treffern: `data/ticker_overrides.json` für die Demo-Klienten manuell befüllen.
- Vollständige Liste der `FundUnbundlingMappings[].AssetClassName`-Werte für das Präfix-Mapping auf SAA-Klassen (`python3 -c` beim Implementieren von `saa.py`).
- `PriceDateUtc`-Bereich der Securities (laut DATA.md live-refreshed) — nur relevant, falls wir `EndOfDayPrice` gegen yfinance-Kurse prüfen wollen (nicht geplant).

## 15. Abweichungen von der Design-Spec (durch die Daten erzwungen)

| Spec sagt | Daten erzwingen | Betroffene Stelle |
|---|---|---|
| Notizen DE/FR, LLM übersetzt | Englisch; Prompt-Regel bleibt harmlos | §5.14, §7.4 |
| Konservativ-Heuristik über Profilnamen („conserv", „defens" …) | Namen sind `Anlageprofil 3–7` → `RiskLevel <= 4` | §5.16 Boost-Tabelle |
| SAA-Zuordnung unklar (🔍) | `Portfolios[].StrategicAssetAllocationId` immer gesetzt; aber 29 Portfolios haben eine leere „Keine Strategie"-SAA | §5.6 |
| Min/Max pro Mapping | nur AssetClass hat Bänder; andere Dimensionen nur Target | §5.6 |
| Profil-Fact mit Klarname und Alter | PII-Regel aus CLAUDE.md: LLM sieht `CASE-xxx`, kein Name, kein Geburtsdatum; **Alter als Ganzzahl** ist erlaubt | §5.14, §7.3 |
| Positions-Marktwert 🔍 | `TotalAmountInPortfolioCurrency` | §5.2 |
| Risiko-Näherung `weight × volatility` | `ContributionVolatility` liegt fertig vor und summiert sich zu `Portfolio.Volatility` | §5.10 |
| Offene Proposals = ohne `TransactionsSubmittedDateUTC` und Status nicht abgeschlossen | `Entwurf` **oder** (`Final` und kein Submit-Datum); `Abgelehnt` = eigener Typ | §5.12 |
| FundUnbundling: Dimension pro Zeile 🔍 | Kreuzprodukt, alle vier Namen pro Zeile | §5.9 |
| Kandidaten-Filter `InRecommendationList == true` | trifft auf 403/504 Securities zu → zusätzlich: gleiche SAA-Klasse, `Currency == CHF`, nicht bereits gehalten, `SustainabilityScore >= ESG-Minimum`, max. 3 | §5.15 |
