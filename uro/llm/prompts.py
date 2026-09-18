"""OWNER: GIANLUCA — System-Prompt und Rendering des Fact Sheets.

Der System-Prompt ist stabil und wird gecacht. Volatile Findings kommen in den
User-Turn, sonst greift der Cache nicht.
"""

from __future__ import annotations

from uro.analytics.scoring import select_for_llm
from uro.config import TOP_N_FOR_LLM
from uro.models import FactSheet

SYSTEM_PROMPT = """Du bist der Briefing-Assistent von URO Advisor Pro für professionelle Wealth Manager.

Ein Berater bekommt gleich einen Kundenanruf und hat 60 Sekunden zum Lesen.

ABSOLUTE REGEL: Du darfst KEINE Zahl nennen, die nicht woertlich in den übergebenen
Findings steht. Du rechnest nichts, du leitest nichts ab, du rundest nicht. Wenn eine
Zahl fehlt, beschreibst du qualitativ statt zu schaetzen. Jede Aussage traegt die IDs
der Findings, auf die sie sich stuetzt.

AUFBAU — genau drei Abschnitte in dieser Reihenfolge:
1. "Recent Portfolio Development" — wie hat sich das Portfolio entwickelt, was trieb es
2. "Portfolio Health Check" — Abweichungen, Verstösse, Klumpenrisiken, Kundenumstände
3. "Portfolio Outlook & Next Best Actions" — was folgt daraus, was soll der Berater tun

Pro Abschnitt hoechstens drei Aussagen. Gesamtlaenge 150-220 Wörter.

TYPISIERUNG jeder Aussage:
  fact           Portfoliofakt aus den Daten
  market         externer Marktkontext
  house_view     Einschätzung der Bank
  recommendation Handlungsempfehlung
  risk           Risiko oder Regelverstoss

STIL: erfahrener Berater unter Zeitdruck, kein Endkunde. Praezise, sachlich, keine Floskeln,
keine Einleitung, kein Fazit. Deutsch.

Meldet die Regel-Engine der Bank zu einem Risiko nichts, das wir selbst berechnet haben,
benenne das sachlich als Beobachtung — nicht als Vorwurf.

Das Briefing ist ein internes Vorbereitungsdokument für den Berater, keine Anlageberatung
an den Endkunden."""


def render_fact_sheet(fact_sheet: FactSheet, max_findings: int = TOP_N_FOR_LLM) -> str:
    """Findings und Kontext als kompakter Text. Enthaelt keine PII.

    Auswahl über analytics.scoring.select_for_llm: Profil ("profile") und Notizen ("note-N") sind
    IMMER dabei (Contract: Profil immer im LLM-Kontext), dazu die max_findings bestbewerteten
    übrigen Findings mit Typ-Diversität. Vorher fielen Profil und Notizen bei risikoreichen
    Klienten aus dem Top-6-Fenster (21 von 47 Klienten).
    """
    fs = fact_sheet
    lines = [
        f"KLIENT {fs.client_ref}" + (" (Firmenkunde)" if fs.is_company else ""),
        f"Vermögen: {fs.total_aum_chf:,.0f} {fs.reporting_currency}",
        f"Liquidität: {fs.total_liquidity_chf:,.0f} {fs.reporting_currency}",
        f"Risikoprofil: {fs.risk_profile_name or 'nicht hinterlegt'}"
        + (f" (max. Volatilität {fs.max_volatility * 100:.1f}%)" if fs.max_volatility else ""),
        f"Offene Vorschläge: {fs.open_proposals}",
    ]
    if fs.tags:
        lines.append(f"Interessen-Tags: {', '.join(fs.tags)}")
    if fs.last_contact:
        lines.append(f"Letzter Kontakt: {fs.last_contact:%Y-%m-%d}")

    for p in fs.portfolios:
        lines.append(
            f"\nPORTFOLIO {p.portfolio_nr} '{p.name}' — {p.aum_chf:,.0f} {p.currency}, "
            f"Strategie: {p.strategy_name or 'keine hinterlegt'}"
        )
        perf = ", ".join(f"{label} {v:+.2f}%" for label, v in
                         [("3M", p.perf_3m_pct), ("12M", p.perf_12m_pct), ("YTD", p.perf_ytd_pct)]
                         if v is not None)
        lines.append(f"  Rendite: {perf or 'nicht berechenbar'}")
        top = sorted(p.positions, key=lambda x: x.weight_pct, reverse=True)[:5]
        for pos in top:
            lines.append(f"  {pos.weight_pct:5.1f}%  {pos.name[:45]:47} {pos.sector or ''}")

    profile, notes, ranked = select_for_llm(fs, max_findings)

    lines.append("\nFINDINGS (gerankt, wichtigstes zuerst — nur diese Zahlen darfst du verwenden):")
    for f in ranked:
        nums = "  ".join(f"{k}={v}" for k, v in f.numbers.items())
        rank = f" rank {f.rank}," if f.rank else ""
        lines.append(f"[{f.id}] ({rank} {f.severity.value}/{f.type.value}) {f.title}")
        lines.append(f"      {f.detail}")
        if nums:
            lines.append(f"      Zahlen: {nums}")

    if profile:
        lines.append("\nKLIENTENPROFIL (immer relevant, ID zitieren):")
        for f in profile:
            nums = "  ".join(f"{k}={v}" for k, v in f.numbers.items())
            lines.append(f"[{f.id}] {f.title}")
            lines.append(f"      {f.detail}")
            if nums:
                lines.append(f"      Zahlen: {nums}")

    if notes:
        lines.append("\nKUNDENNOTIZEN (wörtlich, jüngste zuerst — Ziele, Sorgen, Präferenzen; ID zitieren):")
        for f in notes:
            lines.append(f"[{f.id}] {f.title}")

    if fs.intents:
        lines.append("\nKUNDENANGABEN AUS NOTIZEN:")
        for i in fs.intents:
            lines.append(f"- {i.kind}: {i.subject} — {i.detail}")

    return "\n".join(lines)
