"""OWNER: JACOB — der eine Ort für Einstellungen und Schwellenwerte.

Zwei Teile:
  1. `Settings` (Umgebung / .env): API-Key, Modell, Timeouts, Pfade. Nur hier lesen.
  2. Analyse-Konstanten: jede Schwelle, jedes Gewicht, jede Mapping-Tabelle, die ein
     Detektor oder das Scoring braucht. Keine Magic Numbers in `analytics/`.

Herkunft der Werte: Design-Spec §5 (docs/superpowers/specs/…) und die gemessenen Daten in
docs/data-notes.md. Wer einen Wert ändert, schreibt die Begründung als Kommentar daneben.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Umgebungsvariablen (Präfix-frei), optional aus `.env` im Repo-Root."""

    anthropic_api_key: str | None = None
    llm_model: str = "claude-opus-5"  # Latenz-Notfall: LLM_MODEL=claude-sonnet-5 (Plan D6)
    llm_effort: str = "low"  # Opus 5 denkt sonst adaptiv — kostet Sekunden (CLAUDE.md §7)
    llm_timeout_s: float = 45.0
    llm_max_tokens: int = 4000  # reicht für ≤ 260 Wörter strukturiertes JSON
    llm_max_retries: int = 1

    # Tier 2 Fallback: Google Gemini
    gemini_api_key: str | None = None
    google_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_timeout_s: float = 15.0

    data_dir: str = "data"
    log_dir: str = "logs"

    market_budget_s: float = 8.0  # Gesamtbudget für Ticker + Kurse + News (Spec §6.2)
    market_call_timeout_s: float = 5.0
    market_cache_enabled: bool = True  # Disk-Fallback nur lesen, wenn live scheitert (Plan D11)
    market_top_positions: int = 15  # Ticker nur für die größten Positionen auflösen (Spec §6.1)
    news_max_items: int = 6
    news_max_age_days: int = 14

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


# ---------------------------------------------------------------------------
# Auswahl für das LLM
# ---------------------------------------------------------------------------

TOP_N_FOR_LLM = 10  # gerankte Findings, die das Briefing-Modell sieht (Spec §5.16: Top 12, hier 10)
MAX_PER_TYPE = 3  # Diversität: höchstens 3 Findings desselben Typs in der Auswahl
NOTES_FOR_LLM = 5  # jüngste Notizen wörtlich als note-1..N
NOTE_MAX_CHARS = 600

# ---------------------------------------------------------------------------
# Detektor-Schwellen (Brüche 0–1, außer wo "_pct"/"_pp" steht)
# ---------------------------------------------------------------------------

# Konzentration auf Klientenebene mit Fonds-Look-through: (Schwelle, Referenzgröße für materiality) je Ebene — Spec §5.9.
CONCENTRATION = {
    "security": (0.10, 0.15),
    "industry": (0.20, 0.30),
    "currency": (0.30, 0.50),  # nur Fremdwährungen ≠ ReportingCurrency
    "region": (0.40, 0.60),  # ohne Heimatregion und Sammelbuckets
}
CONCENTRATION_SINGLE_ERROR = 0.25  # Einzeltitel ab 25 % des Vermögens: ERROR statt WARNING
CONCENTRATION_MAX_SINGLE_FINDINGS = 3
EXPOSURE_TOP_N = 10  # FactSheet.exposures je Dimension (für Chat und UI)
HOME_COUNTRY_GROUP = {
    "CHF": "Switzerland",
    "EUR": "Rest of Europe",
    "USD": "North America",
    "GBP": "Great Britain",
}
REPORTING_CURRENCY_GROUP = {"CHF": "Swiss francs", "USD": "US-Dollar", "EUR": "Euro"}
IGNORED_REGION_BUCKETS = {"Others", "Not classified"}

# Look-through-Zeilen nutzen andere Regions- und Währungsnamen als die SAA (gemessen, data-notes §3/§6)
LOOKTHROUGH_COUNTRY_MAP = {
    "Equities North America": "North America",
    "Equities Euroland": "Rest of Europe",
    "Equities Switzerland": "Switzerland",
    "Equities Pacific": "Asia/Pacific (ex Japan)",
    "Equities Japan": "Japan",
    "Aktien UK": "Great Britain",
    "Equities EmMa": "Others",
}
LOOKTHROUGH_CURRENCY_GROUPS = {"Swiss francs", "US-Dollar", "Euro"}  # alle anderen 40 Währungen → "Andere"
LOOKTHROUGH_CURRENCY_DEFAULT = "Andere"
LOOKTHROUGH_COUNTRY_DEFAULT = "Others"

# ESG-Regel der Bank (einzige in den Daten): "Sustainable investments only" → related_ids statt Doppelmeldung
ESG_RULE_KEYWORDS = ("sustainab", "esg", "nachhalt")

# SAA: AssetClass hat Min/Target/Max → Bandverletzung. Die anderen drei Dimensionen haben in den
# Daten nur ein Target (258 von 333 Mappings ohne Min/Max, data-notes §5) → feste Schwelle.
SAA_OTHER_DIM_THRESHOLD_PP = 10.0
SAA_MAGNITUDE_REF_PP = 15.0
NO_STRATEGY_NAMES = {"No strategy"}  # Portfolios ohne echte SAA (29 von 57) — kein Soll-Ist-Vergleich
# Mandatsart über SAA.InvestmentServiceId → InvestmentServices[].Name. Execution-only heisst: keine Eignungsprüfung
# (FIDLEG Art. 13), die Regel-Engine meldet dort nie etwas (11 Klienten, 0 Verstösse). Vola über Profil ist dann
# kein Verstoss, sondern ein Anlass, ein Beratungsgespräch bzw. -mandat anzubieten.
EXECUTION_ONLY_SERVICE_NAMES = {"Execution only"}

# Risikoprofil: Portfolio.Volatility gegen RiskProfiles[].MaxVola (der Pitch-Befund, CLAUDE.md §4)
VOLA_ERROR_FACTOR = 1.2  # ab 20 % über dem Limit ERROR, darunter WARNING
CONSERVATIVE_RISK_LEVEL_MAX = 4  # Anlageprofil 3/4 gelten als konservativ (Boost-Regel)

# Performance (Spec §5.4)
PERF_NEGATIVE_3M = -0.02
PERF_POSITIVE_3M = 0.02
PERF_MAGNITUDE_REF = 0.05
DRIVER_MIN_CONTRIBUTION_PP = 0.3
DRIVER_TOP_N = 3
PRICE_COVERAGE_WARN = 0.20  # Coverage-Hinweis, wenn > 20 % des Vermögens ohne Kursdaten

# Marktvergleich (Spec §5.5)
SECTOR_WIDE_SECTOR_RET = -0.05
SECTOR_WIDE_MARKET_RET_FLOOR = -0.03
MARKET_WIDE_RET = -0.05
STOCK_SPECIFIC_GAP_PP = -10.0

# Liquidität / Fälligkeit / offene Punkte (Spec §5.11, §5.13)
CASH_DEFAULT_TARGET = 0.10
CASH_EXCESS_MIN_PP = 5.0
MATURITY_WINDOW_DAYS = 180
PERPETUAL_MATURITY_YEAR = 2200  # Jahr ≥ 2200 bedeutet "kein Verfall" (DATA.md)
PROFILE_REVIEW_MONTHS = 24
PROPOSAL_FOLLOW_UP_DAYS = 60
SENIOR_AGE = 60

# Proposals (data-notes §9): ProposalStatuses = Entwurf(1) · Final(3) · Abgelehnt(4)
OPEN_PROPOSAL_STATUSES = {"Entwurf"}
EXECUTED_IF_SUBMITTED_STATUSES = {"Final"}  # Final ohne TransactionsSubmittedDateUTC = offen
REJECTED_PROPOSAL_STATUSES = {"Abgelehnt"}

# ESG (data-notes §7): Score 0–10, höher = besser; Profil "Yes" verlangt ≥ 5.714
ESG_ACTIVE_PROFILE_NAMES = {"Yes"}

# Notiz-Keywords → Flags für das Scoring (nie als Fakt dargestellt). Notizen sind Englisch
# (153/153), DE/FR-Wörter bleiben als billige Absicherung für neue Dateien.
NOTE_KEYWORDS: dict[str, list[str]] = {
    "risk_averse": [
        "nervous",
        "worried",
        "concern",
        "cautious",
        "capital preservation",
        "safety",
        "conservative",
        "angst",
        "sorge",
        "vorsichtig",
        "sicherheit",
        "prudent",
        "inquiet",
    ],
    "risk_tolerant": [
        "unconcerned",
        "patient",
        "long view",
        "long-term",
        "comfortable with risk",
        "risk-tolerant",
        "aggressive",
    ],
    "liquidity_need": [
        "liquid",
        "cash",
        "withdraw",
        "tax payment",
        "property",
        "house",
        "apartment",
        "purchase",
        "tuition",
        "wedding",
        "haus",
        "immobil",
        "entnahme",
        "achat",
        "maison",
    ],
    "retirement": ["retire", "retirement", "pension", "rente", "ruhestand", "retraite"],
    "esg_interest": ["esg", "sustainab", "fossil", "climate", "green", "nachhaltig", "durable"],
}

# ---------------------------------------------------------------------------
# Scoring — score = severity × materiality × client_relevance × recency (CLAUDE.md §7)
# Werte: Spec §5.16 (base_severity). Schlüssel: (FindingType.value, Severity.value).
# ---------------------------------------------------------------------------

SEVERITY_WEIGHT: dict[tuple[str, str], float] = {
    ("suitability_violation", "error"): 1.00,
    ("risk_profile", "error"): 1.00,
    ("saa_deviation", "warning"): 0.80,
    ("saa_deviation", "info"): 0.60,  # Währung/Region/Branche: nur Target, keine Bänder
    ("suitability_violation", "warning"): 0.75,
    ("risk_profile", "warning"): 0.75,
    ("performance", "warning"): 0.70,
    ("performance_driver", "warning"): 0.70,
    ("performance_driver", "opportunity"): 0.40,
    ("concentration", "error"): 0.75,
    ("concentration", "warning"): 0.70,
    ("preference_conflict", "warning"): 0.70,
    ("esg", "warning"): 0.65,
    ("market_comparison", "info"): 0.60,
    ("house_view", "warning"): 0.60,
    ("liquidity", "error"): 0.75,
    ("liquidity", "warning"): 0.60,
    ("open_proposal", "info"): 0.55,
    ("client_profile", "info"): 0.50,
    ("open_item", "info"): 0.50,
    ("data_gap", "warning"): 0.45,
    ("data_gap", "info"): 0.45,
    ("liquidity", "opportunity"): 0.45,
    ("liquidity", "info"): 0.35,  # Liquiditätsbedarf ist gedeckt — Kontext, kein Problem
    ("performance", "opportunity"): 0.40,
    ("house_view", "info"): 0.35,
    ("house_view", "opportunity"): 0.30,
    ("rejected_proposal", "info"): 0.25,
    ("market_event", "info"): 0.25,
    ("client_note", "info"): 0.20,
}
SEVERITY_DEFAULT = 0.40
MATERIALITY_MIN = 0.2
BOOST_CAP = 1.6
BOOST_RISK_AVERSE = 1.3
BOOST_LIQUIDITY_NEED = 1.3
BOOST_SHARED_POSITION = 1.2
BOOST_PROPOSAL_ADDRESSES_DEVIATION = 1.3
RECENCY_MATERIAL_CHANGE = 1.1
RECENCY_STALE_CONTEXT = 0.9
RECENCY_STALE_MONTHS = 12

# ---------------------------------------------------------------------------
# Mapping-Tabellen für Look-through und Marktdaten (exakte Strings: data-notes §3)
# ---------------------------------------------------------------------------

# FundUnbundlingMappings nutzt teils andere Branchennamen als SAA_IndustryName
LOOKTHROUGH_INDUSTRY_MAP = {
    "Raw materials": "Materials",
    "Communication Services": "Telecommunication Services",
}
# Asset-Klasse: KEIN Look-through. Alle 224 gehaltenen Look-through-Fonds sind laut SAA_AssetClassName
# "Shares" und ihre Zeilen nennen nur "Equities …" — die eigene SAA-Klasse des Fonds ist genauso genau.

SAA_ASSET_CLASSES = ["Liquidity", "Bonds", "Shares", "Real estate", "Specialties andCommodities"]
CRYPTO_CURRENCIES = {"BTC", "ETH", "SOL", "DOT", "SHIB", "OZG", "ADA", "XRP"}
CRYPTO_ASSET_CLASS = "Crypto"

MARKET_PROXIES = {"CHF": "^SSMI", "USD": "^GSPC", "EUR": "^STOXX50E", "GBP": "^FTSE", "default": "URTH"}
