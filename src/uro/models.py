"""Die Contracts des Projekts. Aenderungen hier betreffen alle drei — vorher im Team absprechen.

Datenfluss:  Ingest -> FactSheet -> Finding[] -> LLM -> Briefing -> Validator
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Findings — das, was die Engine deterministisch berechnet
# ---------------------------------------------------------------------------


class FindingType(str, Enum):
    """Welche Art von Beobachtung. Steuert Farbe im UI und Abschnitt im Briefing."""

    PERFORMANCE_DRIVER = "performance_driver"     # Position X trug -2.1pp bei
    SAA_DEVIATION = "saa_deviation"               # Aktien 62% vs. Ziel 45%
    CONCENTRATION = "concentration"               # 68% in einem Titel
    SUITABILITY_VIOLATION = "suitability_violation"  # aus SuitabilityViolations[]
    PREFERENCE_CONFLICT = "preference_conflict"   # Notiz sagt X, Depot haelt Y
    LIQUIDITY = "liquidity"                       # Bedarf laut Notiz vs. Cash
    OPEN_PROPOSAL = "open_proposal"               # nicht abgeschlossener Vorschlag
    HOUSE_VIEW = "house_view"                     # Abgleich mit CIO-Meinung
    MARKET_EVENT = "market_event"                 # News zu einer Position
    DATA_GAP = "data_gap"                         # fehlende Daten sind ein Finding!


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Finding(BaseModel):
    """Eine berechnete Beobachtung. Jede Zahl im Briefing muss aus einem Finding stammen.

    Das LLM darf Findings priorisieren, verknuepfen und formulieren — niemals rechnen.
    """

    id: str = Field(description="Stabil und sprechend, z.B. 'conc-nvda' oder 'saa-shares'")
    type: FindingType
    severity: Severity
    title: str = Field(description="Eine Zeile, sachlich, ohne Bewertung")
    detail: str = Field(description="Ein bis zwei Saetze Kontext fuer das LLM")

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


# ---------------------------------------------------------------------------
# FactSheet — alles, was die Engine ueber einen Klienten weiss
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
    source_note: str = Field(description="Originalzitat, fuer Nachvollziehbarkeit im UI")


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

    def top_findings(self, n: int = 5) -> list[Finding]:
        return sorted(self.findings, key=lambda f: f.score, reverse=True)[:n]

    def all_numbers(self) -> set[float]:
        """Jede Zahl, die im Briefing vorkommen darf. Der Validator nutzt das."""
        return {v for f in self.findings for v in f.numbers.values()}


# ---------------------------------------------------------------------------
# Briefing — was das LLM zurueckgibt
# ---------------------------------------------------------------------------


class StatementType(str, Enum):
    FACT = "fact"                    # grau  — Portfoliofakt
    MARKET = "market"                # blau  — Marktkontext
    HOUSE_VIEW = "house_view"        # lila  — CIO-Meinung
    RECOMMENDATION = "recommendation"  # gruen — Empfehlung
    RISK = "risk"                    # rot   — Risiko/Verstoss


class Statement(BaseModel):
    text: str
    type: StatementType
    finding_ids: list[str] = Field(
        description="Mindestens eine. Ohne Referenz verwirft der Validator die Aussage."
    )


class Section(BaseModel):
    title: str
    statements: list[Statement] = Field(max_length=3, description="Max 3 — 60-Sekunden-Regel")


class LikelyQuestion(BaseModel):
    question: str
    answer_hint: str


class NextBestAction(BaseModel):
    action: str = Field(description="Konkret und umsetzbar, mit Betrag oder Titel")
    rationale: str
    finding_ids: list[str]


class Briefing(BaseModel):
    """Die drei Abschnitte aus dem Case, plus die zwei Extras, die Punkte bringen."""

    headline: str = Field(description="Ein Satz. Die Kernaussage des Gespraechs.")
    sections: list[Section] = Field(
        description="Genau 3: Recent Portfolio Development, Portfolio Health Check, "
        "Portfolio Outlook & Next Best Actions"
    )
    likely_questions: list[LikelyQuestion] = Field(default_factory=list, max_length=2)
    next_best_actions: list[NextBestAction] = Field(default_factory=list, max_length=3)

    def word_count(self) -> int:
        parts = [self.headline]
        parts += [s.text for sec in self.sections for s in sec.statements]
        parts += [q.question + " " + q.answer_hint for q in self.likely_questions]
        parts += [a.action + " " + a.rationale for a in self.next_best_actions]
        return sum(len(p.split()) for p in parts)


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
