"""OWNER: JACOB — die EINZIGE Stelle, die Zahlen und Daten in Text verwandelt.

Warum zentral: Der Validator (llm/validator.py) prüft jede Zahl im Briefing gegen die Werte in
`Finding.numbers` und gegen die Zahlen im gerenderten Fact Sheet. Damit das zusammenpasst, muss
jede Zahl im Text genauso gerundet sein wie der Wert in `numbers`. Detektoren rufen deshalb
`num()` bzw. `round_chf()` für den Wert in `numbers` und `pct()` / `chf()` für den Text auf.

Konvention im FactSheet: Prozentwerte sind 0–100 (weight_pct, perf_3m_pct), nicht Brüche.
Wer einen Bruch aus den Rohdaten hat, nutzt `frac_pct()`.
"""

from __future__ import annotations

import re
from datetime import date, datetime


def num(x: float, digits: int = 1) -> float:
    """Der Wert, der in `Finding.numbers` landet — gleiche Rundung wie im Text."""
    return round(float(x), digits)


def pct(x_pct: float, signed: bool = False, digits: int = 1) -> str:
    """68.2 → '68.2%'; mit signed: 6.09 → '+6.1%'. Eingabe ist bereits in Prozent (0–100)."""
    v = round(float(x_pct), digits)
    body = f"{v:+.{digits}f}" if signed else f"{v:.{digits}f}"
    return f"{body}%"


def frac_pct(fraction: float, signed: bool = False, digits: int = 1) -> str:
    """0.735 → '73.5%'. Für Brüche 0–1 aus den Rohdaten."""
    return pct(float(fraction) * 100, signed=signed, digits=digits)


def pp(x_pp: float, signed: bool = True, digits: int = 1) -> str:
    """Prozentpunkte: 16.0 → '+16.0 pp'."""
    v = round(float(x_pp), digits)
    body = f"{v:+.{digits}f}" if signed else f"{v:.{digits}f}"
    return f"{body} pp"


def round_chf(x: float) -> float:
    """Betrag so runden, wie er im Text steht: ab 1 Mio auf 1'000, ab 100'000 auf 100, sonst auf 1."""
    a = abs(float(x))
    step = 1000 if a >= 1_000_000 else 100 if a >= 100_000 else 1
    return float(round(float(x) / step) * step)


def chf(x: float, currency: str = "CHF") -> str:
    """102900 → 'CHF 102,900'. Rundet über round_chf(), damit numbers und Text übereinstimmen."""
    return f"{currency} {round_chf(x):,.0f}"


def date_str(d: date | datetime | None) -> str:
    """'12 Jun 2026'. None → 'unknown date'."""
    if d is None:
        return "unknown date"
    if isinstance(d, datetime):
        d = d.date()
    return d.strftime("%d %b %Y")


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug(text: str, max_len: int = 40) -> str:
    """'Cluster risk of a single financial instrument' → 'cluster-risk-of-a-single-financial-instr'."""
    s = _SLUG_RE.sub("-", str(text).lower()).strip("-")
    return s[:max_len].rstrip("-") or "x"


def truncate(text: str, n: int = 600) -> str:
    text = str(text)
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"
