"""OWNER: LEVIN — Batch ueber alle Klienten. Das ist eine Pitch-Slide, kein Test.

    uv run python eval/run_all.py                     nur die Engine (kein API-Key noetig)
    uv run python eval/run_all.py --briefings         mit LLM-Call und Validierung
    uv run python eval/run_all.py --file data/xy.json andere Client-Datei

Beantwortet die Jury-Frage nach dem unbekannten Testklienten, bevor sie gestellt wird.
"""

from __future__ import annotations

import os
import statistics
import sys
import time

from uro.analytics import build_fact_sheet
from uro.ingest import load_clients, load_reference


def main(argv: list[str]) -> int:
    path = argv[argv.index("--file") + 1] if "--file" in argv else "data/clients.json"
    with_briefings = "--briefings" in argv

    clients = load_clients(path)
    reference = load_reference("data/reference.json")

    engine_ms: list[float] = []
    brief_s: list[float] = []
    words: list[int] = []
    failures: list[tuple[str, str]] = []
    issue_count = 0
    finding_total = 0
    gap_clients = 0

    for c in clients:
        ref = c.get("ClientRef", "?")
        try:
            t0 = time.perf_counter()
            fs = build_fact_sheet(c, reference)
            engine_ms.append((time.perf_counter() - t0) * 1000)
            finding_total += len(fs.findings)
            if any(f.type.value == "data_gap" for f in fs.findings):
                gap_clients += 1

            if with_briefings:
                from uro.llm.briefing import generate_briefing
                from uro.llm.validator import validate
                t1 = time.perf_counter()
                briefing, issues = validate(generate_briefing(fs), fs)
                brief_s.append(time.perf_counter() - t1)
                words.append(briefing.word_count())
                issue_count += len(issues)
        except Exception as exc:  # noqa: BLE001 — wir wollen jeden Fehler sehen, nicht abbrechen
            failures.append((ref, f"{type(exc).__name__}: {exc}"))

    ok = len(clients) - len(failures)
    print(f"\nDatei: {path}")
    print(f"Fact Sheets erzeugt:       {ok} / {len(clients)}")
    print(f"Findings insgesamt:        {finding_total}  (Schnitt {finding_total / max(ok, 1):.1f} je Klient)")
    print(f"Klienten mit Datenluecken: {gap_clients}  (sauber behandelt, kein Absturz)")
    print(f"Engine-Zeit:               Schnitt {statistics.mean(engine_ms):.0f} ms, "
          f"max {max(engine_ms):.0f} ms")
    if with_briefings:
        print(f"Briefings erzeugt:         {len(brief_s)} / {ok}")
        print(f"Unbelegte Aussagen:        {issue_count}")
        print(f"Briefing-Zeit:             Schnitt {statistics.mean(brief_s):.1f} s, "
              f"max {max(brief_s):.1f} s")
        print(f"Briefing-Laenge:           Schnitt {statistics.mean(words):.0f} Woerter (Ziel 150-220)")
    for ref, err in failures:
        print(f"  FEHLER {ref}: {err}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
