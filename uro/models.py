"""Die Contracts des Projekts. Änderungen hier betreffen alle drei — vorher im Team absprechen.

Datenfluss:  Ingest -> FactSheet -> Finding[] -> LLM -> Briefing -> Validator
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Findings — das, was die Engine deterministisch berechnet
# ---------------------------------------------------------------------------


class FindingType(str, Enum):
    """Welche Art von Beobachtung. Steuert Farbe im UI und Abschnitt im Briefing."""

    PERFORMANCE = "performance"  # Portfolio-Rendite 1M/3M/12M/YTD
    PERFORMANCE_DRIVER = "performance_driver"  # Position X trug -2.1pp bei
    MARKET_COMPARISON = "market_comparison"  # Rueckgang isoliert / sektor- / marktweit?
    SAA_DEVIATION = "saa_deviation"  # Aktien 62% vs. Ziel 45%
    CONCENTRATION = "concentration"  # 68% in einem Titel
    SUITABILITY_VIOLATION = "suitability_violation"  # aus SuitabilityViolations[]
    RISK_PROFILE = "risk_profile"  # Portfolio-Vola vs RiskProfile.MaxVola — der Differenzierer
    ESG = "esg"  # Score unter Profil-Minimum
    PREFERENCE_CONFLICT = "preference_conflict"  # Notiz sagt X, Depot haelt Y
    LIQUIDITY = "liquidity"  # Bedarf laut Notiz vs. Cash, Faelligkeiten, Cash-Ueberschuss
    OPEN_PROPOSAL = "open_proposal"  # nicht abgeschlossener Vorschlag
    REJECTED_PROPOSAL = "rejected_proposal"  # vom Kunden abgelehnt → Praeferenz-Signal
    OPEN_ITEM = "open_item"  # abgeleitete To-dos (Profil alt, Proposal ueberfaellig)
    CLIENT_PROFILE = "client_profile"  # genau ein Finding "profile", immer im LLM-Kontext
    CLIENT_NOTE = "client_note"  # Notiz woertlich, note-N
    HOUSE_VIEW = "house_view"  # Abgleich mit CIO-Meinung
    MARKET_EVENT = "market_event"  # News zu einer Position
    DATA_GAP = "data_gap"  # fehlende Daten sind ein Finding!


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    OPPORTUNITY = "opportunity"  # Chance (Cash anlegen, Faelligkeit, House View aligned) → gruen


class Finding(BaseModel):
    """Eine berechnete Beobachtung. Jede Zahl im Briefing muss aus einem Finding stammen.

    Das LLM darf Findings priorisieren, verknuepfen und formulieren — niemals rechnen.
    """

    id: str = Field(description="Stabil und sprechend, z.B. 'conc-nvda' oder 'saa-shares'")
    type: FindingType
    severity: Severity
    title: str = Field(description="Eine Zeile, sachlich, ohne Bewertung")
    detail: str = Field(description="Ein bis zwei Sätze Kontext für das LLM")

    # Die Zahlen. Alles, was im Briefing als Zahl auftauchen darf, steht hier drin.
    # Der Validator prueft den generierten Text gegen genau diese Werte.
    numbers: dict[str, float] = Field(
        default_factory=dict,
        description="z.B. {'weight_pct': 68.2, 'amount_chf': 412000.0}",
    )

    # Scoring — siehe CLAUDE.md §7. score = severity x materiality x relevance x recency
    materiality_chf: float = 0.0
    client_relevance: float = Field(default=0.0, ge=0.0, le=1.0)
    recency_days: int | None = None
    score: float = 0.0

    portfolio_nr: str | None = None
    security_ids: list[int] = Field(default_factory=list)
    source: str = Field(default="analytics", description="analytics | notes | news | house_view")

    # Verknuepfung und Transparenz (fuer Boosts, Popover im UI, Chat)
    related_ids: list[str] = Field(default_factory=list, description="Andere Finding-IDs zum selben Thema")
    boost_reasons: list[str] = Field(default_factory=list, description="Warum relevance/recency > 1")
    rank: int | None = Field(default=None, description="1 = wichtigstes Finding; vom Scoring gesetzt")
    # Regel: Jede Zahl in `numbers` steht FORMATIERT auch in `title` oder `detail`.
    # Das LLM kopiert sie woertlich; der Validator prueft String und Zahl.


# ---------------------------------------------------------------------------
# FactSheet — alles, was die Engine über einen Klienten weiss
# ---------------------------------------------------------------------------


class PerformancePoint(BaseModel):
    date: date
    value: float


class PositionFact(BaseModel):
    security_id: int
    name: str
    isin: str | None = None
    currency: str
    amount_chf: float
    weight_pct: float = Field(description="0-100, NICHT der 0-1 Bruch aus den Rohdaten")
    asset_class: str | None = None
    saa_asset_class: str | None = None
    sector: str | None = None
    contribution_volatility: float | None = None
    in_recommendation_list: bool = False

    # Stammdaten fuer SAA-Vergleich, Konzentration, ESG, Faelligkeiten (Securities[] via SecurityId)
    portfolio_nr: str | None = None
    client_weight_pct: float | None = Field(
        default=None,
        description="Gewicht am Gesamtvermoegen des Klienten, 0-100; weight_pct bleibt Portfolio-Gewicht",
    )
    security_type: str | None = None  # SecurityTypeName
    industry: str | None = None  # SAA_IndustryName (None bei Anleihen/Fonds)
    country_group: str | None = None  # SAA_CountryGroupName
    currency_group: str | None = None  # SAA_CurrencyGroupName
    volatility: float | None = None  # Security.Volatility, Bruch
    prc: int | None = None
    sustainability_score: float | None = None  # 0-10, hoeher = besser
    maturity_date: date | None = None  # Anleihen; Jahr >= 2200 bedeutet perpetual → None
    is_fund_unbundlable: bool = False
    ticker: str | None = None  # von enrich/market gesetzt, None wenn nicht aufloesbar


class AllocationLine(BaseModel):
    """Eine Zeile des Soll-Ist-Vergleichs."""

    dimension: str = Field(description="AssetClass | CurrencyGroup | CountryGroup | Industry")
    category: str
    actual_pct: float
    target_pct: float | None = None
    min_pct: float | None = None
    max_pct: float | None = None

    @property
    def deviation_pp(self) -> float | None:
        if self.target_pct is None:
            return None
        return self.actual_pct - self.target_pct


class ClientIntent(BaseModel):
    """Aus ClientNotes extrahiert. Der Goldschatz — siehe CLAUDE.md §4."""

    kind: str = Field(description="exclusion | liquidity_need | preference | concern | life_event")
    subject: str = Field(description="z.B. 'fossile Energie', 'Immobilienkauf'")
    detail: str
    horizon_months: int | None = None
    source_note: str = Field(description="Originalzitat, für Nachvollziehbarkeit im UI")


class PortfolioFact(BaseModel):
    portfolio_nr: str
    name: str
    currency: str
    aum_chf: float
    liquidity_chf: float

    # Selbst gerechnet — PerformanceYTD fehlt in ALLEN Rohdaten (siehe CLAUDE.md §4)
    perf_1m_pct: float | None = None
    perf_3m_pct: float | None = None
    perf_12m_pct: float | None = None
    perf_ytd_pct: float | None = None

    # Koennen fehlen: 7 Portfolios ohne Volatility, 6 ohne ValueAtRisk
    volatility: float | None = None
    value_at_risk: float | None = None
    expected_return: float | None = None

    strategy_name: str | None = None
    investment_service: str | None = None
    saa_name: str | None = None

    positions: list[PositionFact] = Field(default_factory=list)
    allocation: list[AllocationLine] = Field(default_factory=list)
    history: list[PerformancePoint] = Field(default_factory=list)

    # 29 von 57 Portfolios haengen an einer "Keine Strategie"-SAA mit Min 0 / Target 0 / Max 1 —
    # dort ist der Soll-Ist-Vergleich leer (data-notes §5)
    has_real_saa: bool = True
    max_volatility: float | None = Field(
        default=None, description="RiskProfile.MaxVola des Klienten, zur Anzeige neben volatility"
    )


class FactSheet(BaseModel):
    """Alles Berechnete zu einem Klienten. Geht ins LLM — enthaelt deshalb KEINE PII.

    Keine IBANs, keine Geburtsdaten, keine Klarnamen. Siehe CLAUDE.md §3.
    """

    client_ref: str = Field(description="CASE-001 — das ist der Anzeigename, nicht der Klarname")
    is_company: bool = False
    reporting_currency: str = "CHF"

    risk_profile_name: str | None = None
    max_volatility: float | None = None
    max_prc: int | None = None
    esg_profile: str | None = None

    total_aum_chf: float = 0.0
    total_liquidity_chf: float = 0.0

    portfolios: list[PortfolioFact] = Field(default_factory=list)
    intents: list[ClientIntent] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    last_contact: datetime | None = Field(
        default=None, description="Juengste Notiz oder Proposal — 'seit dem letzten Kontakt'"
    )
    open_proposals: int = 0

    findings: list[Finding] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.now)

    # Abgeleitet, PII-frei: Alter ist kein Geburtsdatum
    age: int | None = None
    risk_level: int | None = Field(
        default=None, description="RiskProfile.RiskLevel 3-7; <= 4 gilt als konservativ"
    )

    # Zwei Zeitanker — nie date.today() in analytics/ (Plan D20)
    history_as_of: date | None = Field(
        default=None, description="Letztes PerformanceHistory-Datum → Renditen"
    )
    data_as_of: date | None = Field(
        default=None, description="Juengstes Datum aller Klientenfelder → 'offen seit', Profil-Alter"
    )

    # Transparenz fuer UI, Chat und Robustheitsnachweis
    exposures: dict[str, list[dict]] = Field(
        default_factory=dict,
        description="industry/currency/region → Top-10 [{name, weight_pct, direct_pct, via_funds_pct}]",
    )
    coverage: dict[str, str] = Field(
        default_factory=dict, description="detector → 'ok' | 'no_data' | 'error: <ExceptionName>'"
    )
    warnings: list[str] = Field(default_factory=list, description="z.B. 'Market data unavailable'")
    note_flags: list[str] = Field(
        default_factory=list,
        description="Keyword-Flags aus Notizen (risk_averse, liquidity_need, retirement, esg_interest) — nur fuer Boosts",
    )

    def top_findings(self, n: int = 5) -> list[Finding]:
        return sorted(self.findings, key=lambda f: f.score, reverse=True)[:n]

    def all_numbers(self) -> set[float]:
        """Jede Zahl, die im Briefing vorkommen darf. Der Validator nutzt das."""
        return {v for f in self.findings for v in f.numbers.values()}

    def by_id(self) -> dict[str, Finding]:
        return {f.id: f for f in self.findings}


# ---------------------------------------------------------------------------
# Briefing — was das LLM zurückgibt
# ---------------------------------------------------------------------------


class StatementType(str, Enum):
    FACT = "fact"  # grau  — Portfoliofakt
    MARKET = "market"  # blau  — Marktkontext
    HOUSE_VIEW = "house_view"  # lila  — CIO-Meinung
    RECOMMENDATION = "recommendation"  # gruen — Empfehlung
    RISK = "risk"  # rot   — Risiko/Verstoss
    ASSESSMENT = "assessment"  # kursiv — Interpretation/Schlussfolgerung des Assistenten (Jury: facts vs interpretations)


class Statement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    type: StatementType
    finding_ids: list[str] = Field(
        description="Mindestens eine. Ohne Referenz verwirft der Validator die Aussage."
    )


class Section(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    statements: list[Statement] = Field(description="Max 3 — 60-Sekunden-Regel")


class LikelyQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    answer_hint: str


class ActionKind(str, Enum):
    RESOLVE_VIOLATION = "resolve_violation"
    REBALANCE = "rebalance"
    REDUCE_CONCENTRATION = "reduce_concentration"
    REINVEST_LIQUIDITY = "reinvest_liquidity"
    FOLLOW_UP_PROPOSAL = "follow_up_proposal"
    BUY = "buy"
    SELL = "sell"
    SWITCH = "switch"
    CLIENT_FOLLOW_UP = "client_follow_up"  # Praeferenz, Ziel oder Sorge ansprechen
    UPDATE_PROFILE = "update_profile"


class NextBestAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(description="Konkret und umsetzbar, mit Betrag oder Titel")
    rationale: str
    finding_ids: list[str]
    priority: int = Field(default=1, description="1 = dringendste Aktion, 3 = kann warten")
    kind: ActionKind = Field(default=ActionKind.CLIENT_FOLLOW_UP, description="Steuert Icon/Badge im UI")


class Briefing(BaseModel):
    """Die drei Abschnitte aus dem Case, plus die zwei Extras, die Punkte bringen."""

    model_config = ConfigDict(extra="forbid")

    headline: str = Field(description="Ein Satz. Die Kernaussage des Gespraechs.")
    sections: list[Section] = Field(
        description="Genau 3: Recent Portfolio Development, Portfolio Health Check, "
        "Portfolio Outlook & Next Best Actions"
    )
    likely_questions: list[LikelyQuestion] = Field(default_factory=list)
    next_best_actions: list[NextBestAction] = Field(default_factory=list)

    def word_count(self) -> int:
        parts = [self.headline]
        parts += [s.text for sec in self.sections for s in sec.statements]
        parts += [q.question + " " + q.answer_hint for q in self.likely_questions]
        parts += [a.action + " " + a.rationale for a in self.next_best_actions]
        return sum(len(p.split()) for p in parts)

    def model_post_init(self, context: object, /) -> None:
        """Setzt die 60-Sekunden-Grenzen durch — bei jedem Weg, auf dem ein Briefing entsteht
        (messages.parse, model_validate auf rohem JSON, Template-Fallback, Tests).

        Die Grenzen dürfen NICHT als max_length im Schema stehen: Pydantic macht daraus maxItems,
        und Structured Outputs lehnt das mit HTTP 400 ab (docs/blocker-models-schema.md).
        Überzählige Einträge werden gekürzt; das Modell ordnet ohnehin nach Wichtigkeit.
        """
        for section in self.sections:
            section.statements = section.statements[:MAX_STATEMENTS_PER_SECTION]
        self.likely_questions = self.likely_questions[:MAX_LIKELY_QUESTIONS]
        self.next_best_actions = self.next_best_actions[:MAX_NEXT_BEST_ACTIONS]


# Die Längengrenzen des Briefings — hier statt im Schema (siehe Briefing.model_post_init).
# Prompt und Validator können sie importieren, damit überall dieselben Zahlen gelten.
MAX_STATEMENTS_PER_SECTION = 3
MAX_LIKELY_QUESTIONS = 2
MAX_NEXT_BEST_ACTIONS = 3


class ValidationIssue(BaseModel):
    kind: str = Field(description="unsupported_number | unknown_finding_id | too_long | no_reference")
    detail: str
    statement_text: str | None = None


class BriefingResult(BaseModel):
    """Was die API ans Frontend gibt."""

    client_ref: str
    briefing: Briefing
    fact_sheet: FactSheet
    issues: list[ValidationIssue] = Field(default_factory=list)
    generation_seconds: float = 0.0

    display_name: str = Field(default="", description="UI-Pfad, nie im LLM-Pfad")
    mode: Literal["ai", "ai_retry", "ai_gemini", "fallback"] = Field(
        default="ai", description="fallback = deterministisches Template-Briefing, weil LLM nicht verfuegbar"
    )
    timings_ms: dict[str, int] = Field(
        default_factory=dict, description="load, analytics, market, llm, validate, total"
    )
    generated_at: datetime = Field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# Markt-Snapshot — Vertrag zwischen enrich/ (erzeugt) und analytics/ + service (konsumieren).
# Liegt hier, damit analytics/ nichts aus enrich/ importieren muss.
# ---------------------------------------------------------------------------


class PriceSeries(BaseModel):
    ticker: str
    dates: list[date] = Field(default_factory=list)
    closes: list[float] = Field(default_factory=list)

    def return_pct(self) -> float | None:
        """(last / first − 1) × 100. None bei weniger als zwei Punkten."""
        if len(self.closes) < 2 or not self.closes[0]:
            return None
        return (self.closes[-1] / self.closes[0] - 1) * 100


class MarketSnapshot(BaseModel):
    as_of: datetime = Field(default_factory=datetime.now)
    source: Literal["live", "cache", "unavailable"] = "unavailable"
    tickers: dict[int, str] = Field(
        default_factory=dict, description="security_id → Yahoo-Ticker (nur aufgeloeste)"
    )
    prices: dict[str, PriceSeries] = Field(
        default_factory=dict,
        description="Ticker (Positionen UND Sektor-/Markt-Proxies) → 3-Monats-Schlusskurse",
    )
    news: list[Finding] = Field(default_factory=list, description="news-1..N, Typ MARKET_EVENT")
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
    liquidity_pct: float = Field(default=0.0, description="0-100")
    violation_count: int = 0
    error_count: int = 0
    open_proposal_count: int = 0
    portfolio_count: int = 1
    is_new: bool = Field(default=False, description="via Upload hinzugefuegt")


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)


class ChatResponse(BaseModel):
    answer: str
    sources: list[str] = Field(
        default_factory=list, description="Finding-/Positions-IDs, aus [..] in der Antwort extrahiert"
    )


class UploadResult(BaseModel):
    added_client_refs: list[str] = Field(default_factory=list)
    updated_client_refs: list[str] = Field(default_factory=list)
    reference_merged: bool = False
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Post-Call Follow-up Email & Sales Guidance Models
# ---------------------------------------------------------------------------


class ClientFacingEmail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(description="Prägnante Betreffzeile für die Nachfass-E-Mail")
    salutation: str = Field(description="Persönliche Anrede (z.B. 'Sehr geehrte/r...', 'Dear...')")
    intro: str = Field(description="Höflicher Dank für das Gespräch und kurzer Kontext")
    portfolio_recap: list[str] = Field(
        default_factory=list,
        description="2-3 verständliche Kernpunkte zur Portfolioentwicklung und Treibern, basierend auf Befunden",
    )
    agreed_next_steps: list[str] = Field(
        default_factory=list,
        description="Konkret vereinbarte Massnahmen und nächste Schritte für Kunde und Berater",
    )
    closing: str = Field(description="Wertschätzende Grussformel und Ausblick")
    finding_ids: list[str] = Field(
        default_factory=list, description="IDs aller referenzierten Befunde"
    )


class SalesOrientedNotes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cross_sell_opportunities: list[str] = Field(
        default_factory=list,
        description="Konkrete Vertriebs- und Ertragschancen (z. B. Cash anlegen, House-View-Titel, Mandatsausbau)",
    )
    suitability_or_risk_actions: list[str] = Field(
        default_factory=list,
        description="Regulatorische Massnahmen, Risikolimiten (z. B. Vola-Überschreitung, Profil-Aktualisierung)",
    )
    next_contact_date_hint: str = Field(
        default="", description="Empfohlenes Zeitfenster/Frist für die nächste Kontaktaufnahme"
    )
    crm_log_entry: str = Field(
        default="", description="Prägnanter Einzeiler für das Bank-CRM (Ergebnis des Gesprächs & To-dos)"
    )


class FollowUpEmailDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: ClientFacingEmail
    sales_notes: SalesOrientedNotes


class FollowUpEmailRequest(BaseModel):
    language: Literal["de", "en"] = "de"


class FollowUpEmailResult(BaseModel):
    client_ref: str
    display_name: str = ""
    email: ClientFacingEmail
    sales_notes: SalesOrientedNotes
    issues: list[ValidationIssue] = Field(default_factory=list)
    mode: Literal["ai", "ai_gemini", "fallback"] = "ai"
    language: Literal["de", "en"] = "de"
    generated_at: datetime = Field(default_factory=datetime.now)

