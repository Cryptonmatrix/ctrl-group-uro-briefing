"""Durchstich auf der Kommandozeile.

    uv run python -m uro.demo CASE-003          Briefing erzeugen
    uv run python -m uro.demo CASE-003 --facts  nur die Engine, ohne LLM (kein Key noetig)

Das ist der Beweis, dass die Kette von den Rohdaten bis zum validierten Briefing
durchlaeuft. Frontend kommt spaeter, diese Datei bleibt als Testwerkzeug.
"""

from __future__ import annotations

import sys
import time

from uro.analytics import build_fact_sheet
from uro.ingest import find_client, load_clients, load_reference
from uro.models import FactSheet

COLORS = {"fact": "\033[37m", "market": "\033[36m", "house_view": "\033[35m",
          "recommendation": "\033[32m", "risk": "\033[31m"}
RESET = "\033[0m"
BOLD = "\033[1m"


def print_facts(fs: FactSheet, elapsed: float) -> None:
    print(f"\n{BOLD}FACT SHEET {fs.client_ref}{RESET}   (Engine: {elapsed * 1000:.0f} ms)")
    print(f"  Vermögen {fs.total_aum_chf:,.0f} {fs.reporting_currency} · "
          f"Liquidität {fs.total_liquidity_chf:,.0f} · "
          f"Profil {fs.risk_profile_name or 'keins'} · {len(fs.findings)} Findings")
    print(f"\n{BOLD}  Top-Findings{RESET}")
    for f in fs.top_findings(6):
        color = COLORS["risk"] if f.severity.value == "error" else ""
        print(f"    {color}[{f.score:5.2f}] {f.severity.value:7} {f.title[:80]}{RESET}")


def print_briefing(briefing, issues, elapsed: float) -> None:
    print(f"\n{BOLD}BRIEFING{RESET}   ({elapsed:.1f} s · {briefing.word_count()} Wörter)")
    print(f"\n  {BOLD}{briefing.headline}{RESET}\n")
    for section in briefing.sections:
        print(f"  {BOLD}{section.title}{RESET}")
        for st in section.statements:
            color = COLORS.get(st.type.value, "")
            print(f"    {color}• {st.text}{RESET}")
            print(f"      \033[90m{st.type.value} <- {', '.join(st.finding_ids)}{RESET}")
        print()
    if briefing.likely_questions:
        print(f"  {BOLD}Womit der Kunde kommen wird{RESET}")
        for q in briefing.likely_questions:
            print(f"    ? {q.question}\n      -> {q.answer_hint}")
        print()
    if briefing.next_best_actions:
        print(f"  {BOLD}Next Best Actions{RESET}")
        for a in briefing.next_best_actions:
            print(f"    {COLORS['recommendation']}-> {a.action}{RESET}\n      {a.rationale}")
        print()
    if issues:
        print(f"  {COLORS['risk']}{BOLD}Validator: {len(issues)} Aussagen verworfen{RESET}")
        for i in issues:
            print(f"    - {i.kind}: {i.detail}")
    else:
        print(f"  {COLORS['recommendation']}Validator: keine unbelegte Zahl, keine tote Referenz{RESET}")


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ref = next((a for a in argv if not a.startswith("-")), "CASE-003")
    facts_only = "--facts" in argv

    t0 = time.perf_counter()
    clients = load_clients("data/clients.json")
    reference = load_reference("data/reference.json")
    fs = build_fact_sheet(find_client(clients, ref), reference)
    print_facts(fs, time.perf_counter() - t0)

    if facts_only:
        return 0
    from uro.config import get_settings

    settings = get_settings()
    has_key = bool(settings.anthropic_api_key or settings.gemini_api_key or settings.google_api_key)
    if not has_key:
        print(f"\n  {COLORS['risk']}Kein API-Key (ANTHROPIC_API_KEY oder GEMINI_API_KEY) in .env gefunden.{RESET}")
        print("  Key in .env eintragen für KI-Briefings.")
        return 1

    from uro.llm.briefing import generate_briefing
    from uro.llm.validator import validate

    t1 = time.perf_counter()
    briefing, mode = generate_briefing(fs)
    briefing, issues = validate(briefing, fs)
    print(f"\n  {BOLD}Modus: {mode}{RESET}")
    print_briefing(briefing, issues, time.perf_counter() - t1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
