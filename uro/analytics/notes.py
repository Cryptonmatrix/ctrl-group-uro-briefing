"""OWNER: JACOB (Prüfung) + GIANLUCA (Extraktion) — Notizen und Klientenprofil.

Stand A1 (deterministisch, ohne LLM):
  - `note_findings`   die jüngsten Notizen WÖRTLICH als note-1..N. Das LLM erkennt daraus Ziele,
                      Sorgen und Präferenzen und muss beim Verwenden die note-ID zitieren.
  - `note_flags`      Keyword-Flags (risk_averse, risk_tolerant, liquidity_need, retirement,
                      esg_interest) — nur für das Scoring, nie als Fakt dargestellt.
  - `profile_findings` genau ein Finding "profile" mit den PII-freien Stammdaten des Klienten.

Auftrag B3 (Gianluca): `llm/extract_notes.py` extrahiert ClientIntent[]; `check_intents` prüft
sie deterministisch gegen Positionen und Liquidität (z. B. "needs CHF 15,000" vs. CHF 328 Cash).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from uro.analytics.format import chf, date_str, num, pct, round_chf, slug, truncate
from uro.config import NOTE_KEYWORDS, NOTE_MAX_CHARS, NOTES_FOR_LLM
from uro.ingest import get, lst, parse_date
from uro.models import ClientIntent, FactSheet, Finding, FindingType, Severity

SOURCE_NOTES = "clients.json › ClientNotes"
SOURCE_PROFILE = "clients.json › client fields; reference.json › RiskProfiles"


def note_flags(client: dict[str, Any]) -> list[str]:
    """Keyword-Treffer über alle Notizen. Eine risikotolerante Notiz hebt 'risk_averse' derselben Notiz auf
    ('unconcerned by volatility' enthält 'concern', meint aber das Gegenteil)."""
    flags: set[str] = set()
    for note in lst(client, "ClientNotes"):
        text = str(get(note, "Note", "")).lower()
        hit = {flag for flag, words in NOTE_KEYWORDS.items() if any(w in text for w in words)}
        if "risk_tolerant" in hit:
            hit.discard("risk_averse")
        flags |= hit
    return sorted(flags)


def sorted_notes(client: dict[str, Any]) -> list[tuple[date | None, str]]:
    """Notizen neueste zuerst, undatierte am Ende — dieselbe Reihenfolge wie die note-N-IDs."""
    notes = []
    for n in lst(client, "ClientNotes"):
        text = str(get(n, "Note", "")).strip()
        if text:
            notes.append((parse_date(get(n, "CreatedByDateUTC")), text))
    dated = sorted((t for t in notes if t[0] is not None), key=lambda t: t[0], reverse=True)
    return dated + [t for t in notes if t[0] is None]


_AMOUNT_RE = re.compile(r"CHF\s?(\d[\d,'\.]*)", re.IGNORECASE)
_NEED_RE = re.compile(
    r"\b(need|needs|needed|require|requires|will|plans?|planning|wants? to|intends?|upcoming|due)\b"
)
_DONE_RE = re.compile(
    r"\b(paid|was transferred|already|completed|received|has been|were withdrawn|settled)\b"
)


def liquidity_need_from_notes(client: dict[str, Any]) -> tuple[float | None, str | None]:
    """Erster CHF-Betrag in einer Notiz mit Liquiditäts-Stichwort → (Betrag, note-ID). Sonst (None, None).

    "Needs approximately CHF 15,000 in liquid funds for the Q1 tax payment." → (15000.0, "note-2")
    "Prefers CHF-hedged investments" hat keine Ziffer nach CHF und zählt nicht.
    """
    keywords = NOTE_KEYWORDS.get("liquidity_need", [])
    for i, (_, text) in enumerate(sorted_notes(client)[:NOTES_FOR_LLM], start=1):
        low = text.lower()
        if not any(w in low for w in keywords):
            continue
        # Nur ein künftiger Bedarf zählt: "needs/plans/will …", nicht "paid/received/already transferred …".
        if not _NEED_RE.search(low) or _DONE_RE.search(low):
            continue
        m = _AMOUNT_RE.search(text)
        if not m:
            continue
        raw = m.group(1).replace("'", "").replace(",", "").rstrip(".")
        try:
            amount = float(raw)
        except ValueError:
            continue
        if amount > 0:
            return amount, f"note-{i}"
    return None, None


def note_findings(client: dict[str, Any], as_of: date | None = None) -> list[Finding]:
    """Die jüngsten Notizen wörtlich, neueste zuerst: note-1, note-2, …"""
    notes = sorted_notes(client)

    out: list[Finding] = []
    for i, (created, text) in enumerate(notes[:NOTES_FOR_LLM], start=1):
        out.append(
            Finding(
                id=f"note-{i}",
                type=FindingType.CLIENT_NOTE,
                severity=Severity.INFO,
                title=f"[{date_str(created)}] {truncate(text, 120)}",
                detail=truncate(text, NOTE_MAX_CHARS),
                recency_days=(as_of - created).days if (as_of and created) else None,
                source=SOURCE_NOTES,
            )
        )
    return out


def profile_findings(client: dict[str, Any], fs: FactSheet) -> list[Finding]:
    """Genau ein Finding 'profile' — PII-frei: ClientRef statt Name, Alter statt Geburtsdatum."""
    numbers: dict[str, float] = {}
    who = f"Client {fs.client_ref}"
    if fs.is_company:
        who += ", company client"
    elif fs.age is not None:
        who += f", {fs.age}"
        numbers["age"] = float(fs.age)
    reg_type = str(get(client, "RegulatoryClientTypeName") or "").strip().lower()
    if reg_type and not fs.is_company:
        who += f", {reg_type}"

    if fs.risk_profile_name:
        risk = f"risk profile '{fs.risk_profile_name}'"
        if fs.max_volatility is not None:
            max_pct = num(fs.max_volatility * 100)
            numbers["max_volatility_pct"] = max_pct
            risk += f" (max volatility {pct(max_pct)})"
    else:
        risk = "no risk profile on file"

    esg = f"ESG preference '{fs.esg_profile}'" if fs.esg_profile else "no ESG preference set"
    aum = round_chf(fs.total_aum_chf)
    numbers["aum_chf"] = aum
    liq_pct = num(fs.total_liquidity_chf / fs.total_aum_chf * 100) if fs.total_aum_chf > 0 else 0.0
    numbers["liquidity_pct"] = liq_pct

    title = (
        f"{who}, {risk}, {esg}, reporting currency {fs.reporting_currency}, "
        f"AuM {chf(aum, fs.reporting_currency)}, liquidity {pct(liq_pct)}."
    )

    portfolios = lst(client, "Portfolios")
    strategies = sorted({str(get(p, "StrategyName") or "none") for p in portfolios})
    profiled = parse_date(get(client, "ProfilingDateUtc"))
    detail = (
        f"Interest tags: {', '.join(fs.tags) if fs.tags else '—'}. "
        f"{len(portfolios)} portfolio(s); strategy: {', '.join(strategies) if strategies else 'none'}. "
        f"Risk profile last assessed {date_str(profiled)}."
    )

    return [
        Finding(
            id="profile",
            type=FindingType.CLIENT_PROFILE,
            severity=Severity.INFO,
            title=title,
            detail=detail,
            numbers=numbers,
            source=SOURCE_PROFILE,
        )
    ]


def check_intents(
    intents: list[ClientIntent],
    portfolios_or_fs: Any,
    reference: Any = None,
    client: dict[str, Any] | None = None,
) -> list[Finding]:
    """Auftrag B3: extrahierte Absichten deterministisch gegen Positionen und Liquidität prüfen.

    Prüfungen:
      1. liquidity_need: Betrag vs. verfügbare Liquidität.
         - Shortfall -> Finding (ERROR, Type LIQUIDITY) mit numbers need_chf, available_chf.
         - Gedeckt   -> Finding (INFO, Type LIQUIDITY) mit numbers need_chf, available_chf.
      2. exclusion: ethische/ESG-Ausschlüsse (Fossil, Tabak, Rüstung) vs. Branchen-Exposure inkl. Look-through.
         - PREFERENCE_CONFLICT nur ab 2.0 % des Vermögens (CLAUDE.md §4).
      3. concern: z.B. Sensitivität gegenüber Marktvolatilität.
    """
    if not intents:
        return []

    from uro.models import FactSheet, PositionFact

    fs: FactSheet | None = None
    if isinstance(portfolios_or_fs, FactSheet):
        fs = portfolios_or_fs
        portfolios = fs.portfolios
        total_liquidity_chf = fs.total_liquidity_chf
        total_aum_chf = fs.total_aum_chf
        industry_exposures = fs.exposures.get("industry", [])
    elif isinstance(portfolios_or_fs, list):
        portfolios = portfolios_or_fs
        total_liquidity_chf = sum(getattr(p, "liquidity_chf", 0.0) for p in portfolios)
        total_aum_chf = sum(getattr(p, "aum_chf", 0.0) for p in portfolios)
        industry_exposures = []
    else:
        return []

    all_positions: list[PositionFact] = [pos for p in portfolios for pos in getattr(p, "positions", [])]

    findings: list[Finding] = []
    seen_ids: set[str] = set()

    for intent in intents:
        kind = intent.kind.lower()
        subject_lower = intent.subject.lower()
        detail_lower = intent.detail.lower()
        note_text = intent.source_note or intent.detail

        # 1. Liquidity Need — nur, wenn die Engine den Bedarf nicht schon als liq-need aus derselben Notiz rechnet
        #    (analytics/liquidity.py). Sonst stünde dieselbe Lücke zweimal unter den Top-Findings.
        if kind == "liquidity_need":
            if fs is not None and any(f.id == "liq-need" for f in fs.findings):
                continue
            m = _AMOUNT_RE.search(note_text) or _AMOUNT_RE.search(intent.detail)
            need_amount: float | None = None
            if m:
                raw = m.group(1).replace("'", "").replace(",", "").rstrip(".")
                try:
                    need_amount = float(raw)
                except ValueError:
                    need_amount = None

            if need_amount and need_amount > 0:
                need_chf = round_chf(need_amount)
                avail_chf = round_chf(total_liquidity_chf)

                if total_liquidity_chf < need_amount:
                    shortfall = round_chf(need_amount - total_liquidity_chf)
                    fid = f"intent-liquidity-shortfall-{slug(intent.subject or 'cash', 25)}"
                    if fid not in seen_ids:
                        seen_ids.add(fid)
                        findings.append(
                            Finding(
                                id=fid,
                                type=FindingType.LIQUIDITY,
                                severity=Severity.ERROR,
                                title=f"Liquidity shortfall: needs {chf(need_chf)} vs {chf(avail_chf)} available",
                                detail=(
                                    f"Client note states: '{note_text}'. "
                                    f"Current liquid funds of {chf(avail_chf)} fall short by {chf(shortfall)}."
                                ),
                                numbers={
                                    "need_chf": need_chf,
                                    "available_chf": avail_chf,
                                    "shortfall_chf": shortfall,
                                },
                                source=SOURCE_NOTES,
                            )
                        )
                else:
                    fid = f"intent-liquidity-covered-{slug(intent.subject or 'cash', 25)}"
                    if fid not in seen_ids:
                        seen_ids.add(fid)
                        findings.append(
                            Finding(
                                id=fid,
                                type=FindingType.LIQUIDITY,
                                severity=Severity.INFO,
                                title=f"Liquidity need of {chf(need_chf)} is covered ({chf(avail_chf)} available)",
                                detail=f"Client note states: '{note_text}'. Liquid reserves are sufficient.",
                                numbers={"need_chf": need_chf, "available_chf": avail_chf},
                                source=SOURCE_NOTES,
                            )
                        )

        # 2. Ethical / ESG Exclusions
        elif kind == "exclusion":
            target_industries: list[str] = []
            excl_label = "ethical exclusions"
            if any(
                w in subject_lower or w in detail_lower or w in note_text.lower()
                for w in ["fossil", "oil", "gas", "petroleum", "coal"]
            ):
                target_industries.append("Energy")
                excl_label = "fossil fuels"
            # Rüstung und Tabak bewusst NICHT über ganze Branchen: Industrials bzw. Consumer Staples messen etwas
            # anderes. CASE-003 hätte sonst "excludes tobacco, but holds 73.4% in Consumer Staples" bekommen —
            # das ist Lindt, also Schokolade. Die Daten kennen keine Unterbranche; CLAUDE.md §4 misst 0.00 %.

            for ind_name in target_industries:
                exp_pct: float = 0.0
                if industry_exposures:
                    exp_pct = next(
                        (
                            float(e.get("weight_pct", 0.0))
                            for e in industry_exposures
                            if e.get("name") == ind_name
                        ),
                        0.0,
                    )
                elif total_aum_chf > 0:
                    ind_amt = sum(
                        pos.amount_chf
                        for pos in all_positions
                        if pos.industry == ind_name or pos.sector == ind_name
                    )
                    exp_pct = (ind_amt / total_aum_chf) * 100.0

                exp_pct = num(exp_pct)
                # CLAUDE.md §4: PREFERENCE_CONFLICT nur ab 2 % des Vermögens
                if exp_pct >= 2.0:
                    fid = f"intent-exclusion-{slug(excl_label, 20)}-{slug(ind_name, 15)}"
                    if fid not in seen_ids:
                        seen_ids.add(fid)
                        findings.append(
                            Finding(
                                id=fid,
                                type=FindingType.PREFERENCE_CONFLICT,
                                severity=Severity.WARNING,
                                title=f"Client excludes {excl_label}, but holds {pct(exp_pct)} in {ind_name}",
                                detail=(
                                    f"Client note: '{note_text}'. "
                                    f"Portfolio holds {pct(exp_pct)} exposure in {ind_name} (threshold: 2.0%)."
                                ),
                                numbers={"conflict_weight_pct": exp_pct, "threshold_pct": 2.0},
                                source=SOURCE_NOTES,
                            )
                        )

        # 3. Specific Concerns (e.g. Volatility Sensitivity)
        elif kind == "concern" and any(
            w in subject_lower or w in detail_lower for w in ["volatil", "nervous", "worry"]
        ):
            fid = "intent-concern-volatility"
            if fid not in seen_ids:
                seen_ids.add(fid)
                findings.append(
                    Finding(
                        id=fid,
                        type=FindingType.PREFERENCE_CONFLICT,
                        severity=Severity.INFO,
                        title="Client sensitive to market fluctuations",
                        detail=f"Client note: '{note_text}'. Consider capital preservation priorities.",
                        numbers={},
                        source=SOURCE_NOTES,
                    )
                )

    return findings
