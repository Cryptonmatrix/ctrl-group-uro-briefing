"""OWNER: LEVIN — Batch über alle Klienten. Das ist eine Pitch-Slide, kein Test.

    uv run python -m eval.run_all                      nur die Engine, kein API-Key noetig
    uv run python -m eval.run_all --briefings          mit LLM-Aufruf und Validierung
    uv run python -m eval.run_all --briefings --limit 5   nur die ersten 5 (schneller Check)
    uv run python -m eval.run_all --briefings --market    zusaetzlich Kurse und News holen
    uv run python -m eval.run_all --file data/xy.json     andere Klientendatei
    uv run python -m eval.run_all --briefings --workers 6 parallel (Standard 4)

Beantwortet die Jury-Frage nach dem unbekannten Testklienten, bevor sie gestellt wird.
Die Zahlen am Ende gehen so auf die Slide.
"""

from __future__ import annotations

import concurrent.futures as cf
import statistics
import sys
import time
from collections import Counter

from uro.analytics import build_fact_sheet
from uro.ingest import get, load_clients, load_reference


def _arg(argv: list[str], name: str, default: str) -> str:
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def _process(client, reference, with_briefings: bool, with_market: bool) -> dict:
    """Ein Klient. Faengt jeden Fehler, damit ein kaputter Datensatz den Lauf nicht beendet."""
    ref = get(client, "ClientRef", "?")
    out = {"ref": ref, "ok": False, "error": None, "engine_ms": 0.0,
           "findings": 0, "gaps": 0, "brief_s": None, "words": None,
           "issues": 0, "unsupported": 0, "mode": None}
    try:
        t0 = time.perf_counter()
        fs = build_fact_sheet(client, reference)
        out["engine_ms"] = (time.perf_counter() - t0) * 1000
        out["findings"] = len(fs.findings)
        out["gaps"] = sum(1 for f in fs.findings if f.type.value == "data_gap")

        if with_briefings:
            from uro.llm.briefing import generate_briefing
            from uro.llm.validator import validate

            if with_market:
                from uro.enrich import build_snapshot, enrich_fact_sheet
                try:
                    fs = enrich_fact_sheet(fs, market=build_snapshot(fs, budget_s=6.0), client=client)
                except Exception:  # noqa: BLE001 — Marktdaten sind optional
                    pass

            t1 = time.perf_counter()
            briefing, mode = generate_briefing(fs)
            briefing, issues = validate(briefing, fs)
            out["brief_s"] = time.perf_counter() - t1
            out["words"] = briefing.word_count()
            out["issues"] = len(issues)
            out["unsupported"] = sum(1 for i in issues if i.kind == "unsupported_number")
            out["mode"] = mode
        # Ein Detektor, der intern scheitert, endet in coverage als "error: …" — das ist ein Fehlschlag,
        # kein Erfolg (Review P2 #18). Fehlende Daten ("no_data") bleiben erlaubt.
        broken = {k: v for k, v in fs.coverage.items() if str(v).startswith("error")}
        if broken:
            out["error"] = f"detector errors: {broken}"
        else:
            out["ok"] = True
    except Exception as exc:  # noqa: BLE001 — jeder Fehler soll im Bericht stehen
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def main(argv: list[str]) -> int:
    path = _arg(argv, "--file", "data/clients.json")
    limit = int(_arg(argv, "--limit", "0"))
    workers = int(_arg(argv, "--workers", "4"))
    with_briefings = "--briefings" in argv
    with_market = "--market" in argv

    clients = load_clients(path)
    reference = load_reference("data/reference.json")
    if limit:
        clients = clients[:limit]

    print(f"Datei: {path} · {len(clients)} Klienten"
          f"{' · mit Briefings' if with_briefings else ' · nur Engine'}"
          f"{' · mit Marktdaten' if with_market else ''}")
    t_start = time.perf_counter()

    if with_briefings and workers > 1:
        with cf.ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(lambda c: _process(c, reference, True, with_market), clients))
    else:
        results = [_process(c, reference, with_briefings, with_market) for c in clients]

    ok = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]
    engine = [r["engine_ms"] for r in ok]
    briefed = [r for r in ok if r["brief_s"] is not None]

    print(f"\n{'─' * 58}")
    print(f"Fact Sheets erzeugt        {len(ok)} / {len(clients)}")
    print(f"Findings insgesamt         {sum(r['findings'] for r in ok)}"
          f"  (Schnitt {statistics.mean([r['findings'] for r in ok]):.1f})")
    print(f"Klienten mit Datenlücken   {sum(1 for r in ok if r['gaps'])}  (sauber behandelt)")
    print(f"Engine-Zeit                Schnitt {statistics.mean(engine):.1f} ms,"
          f" max {max(engine):.1f} ms")

    if briefed:
        words = [r["words"] for r in briefed]
        secs = [r["brief_s"] for r in briefed]
        unsupported = sum(r["unsupported"] for r in briefed)
        print(f"\nBriefings erzeugt          {len(briefed)} / {len(ok)}")
        print(f"Unbelegte Zahlen           {unsupported}"
              f"   <- das ist die Zahl fuer den Pitch")
        print(f"Validator-Hinweise         {sum(r['issues'] for r in briefed)}")
        print(f"Briefing-Zeit              Schnitt {statistics.mean(secs):.1f} s,"
              f" max {max(secs):.1f} s")
        print(f"Briefing-Länge             Schnitt {statistics.mean(words):.0f} Wörter"
              f" (Ziel 150-220), max {max(words)}")
        ueber = sum(1 for w in words if w > 220)
        print(f"  davon über 220 Wörter    {ueber}")
        print(f"Modus                      {dict(Counter(r['mode'] for r in briefed))}")

    print(f"\nGesamtdauer                {time.perf_counter() - t_start:.1f} s")
    if failed:
        print(f"\nFEHLER bei {len(failed)} Klienten:")
        for r in failed:
            print(f"  {r['ref']}: {r['error']}")
    print("─" * 58)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
