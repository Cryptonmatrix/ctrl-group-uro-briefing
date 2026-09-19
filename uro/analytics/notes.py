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

from uro.analytics.format import chf, date_str, num, pct, round_chf, truncate
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


def check_intents(intents: list[ClientIntent], portfolios, reference) -> list[Finding]:
    """Auftrag B3: extrahierte Absichten deterministisch gegen Positionen und Liquidität prüfen."""
    raise NotImplementedError("check_intents kommt in Auftrag B3 (Notiz-Extraktion)")
