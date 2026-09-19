"""OWNER: JACOB — Liquidität: Überschuss, Bedarf aus Notizen, Fälligkeiten.

Drei Findings:
  liq-cash            Cash deutlich über dem SAA-Ziel (oder alles in Cash) → Chance, anzulegen
  liq-need            Notiz nennt einen Betrag ("Needs approximately CHF 15,000 …") → deterministisch
                      gegen den Kontostand geprüft. CASE-012: CHF 328 vorhanden → nicht gedeckt (ERROR).
                      CASE-016: dieselbe Notiz, CHF 150'625 vorhanden → gedeckt (INFO). Dieselbe Notiz,
                      gegensätzliche Bewertung — weil die Engine rechnet (CLAUDE.md §4).
  liq-maturity-<sid>  Anleihe läuft innerhalb von 180 Tagen ab data_as_of aus → Wiederanlage

Zeitanker ist fs.data_as_of, nie date.today().
"""

from __future__ import annotations

from typing import Any

from uro.analytics.format import chf, date_str, num, pct, round_chf, truncate
from uro.analytics.notes import liquidity_need_from_notes
from uro.analytics.positions import is_cash
from uro.config import CASH_DEFAULT_TARGET, CASH_EXCESS_MIN_PP, MATURITY_WINDOW_DAYS
from uro.models import FactSheet, Finding, FindingType, Severity

SOURCE_CASH = "clients.json › LiquidityInDefaultCurrency vs reference.json › StrategicAssetAllocations"
SOURCE_NEED = "clients.json › ClientNotes vs LiquidityInDefaultCurrency"
SOURCE_MATURITY = "reference.json › Securities[].MaturityDateUtc"


def _saa_liquidity_target_pct(fs: FactSheet) -> float | None:
    """Liquiditäts-Target der ersten echten SAA (aus der bereits gebauten Allokation)."""
    for pf in fs.portfolios:
        if not pf.has_real_saa:
            continue
        for line in pf.allocation:
            if line.dimension == "AssetClass" and line.category == "Liquidity" and line.target_pct is not None:
                return line.target_pct
    return None


def liquidity_findings(fs: FactSheet, client: dict[str, Any]) -> list[Finding]:
    aum = fs.total_aum_chf
    if aum <= 0:
        return []
    out: list[Finding] = []
    cash = fs.total_liquidity_chf
    cash_pct = num(cash / aum * 100)
    securities = [p for pf in fs.portfolios for p in pf.positions if not is_cash(p)]

    # a) Überschuss / nichts investiert
    target = _saa_liquidity_target_pct(fs)
    target_pct = num(target if target is not None else CASH_DEFAULT_TARGET * 100)
    target_label = "SAA target" if target is not None else "default target"
    if not securities and cash > 0:
        out.append(
            Finding(
                id="liq-cash",
                type=FindingType.LIQUIDITY,
                severity=Severity.OPPORTUNITY,
                title=f"{pct(cash_pct)} of assets are cash ({chf(round_chf(cash))}) — nothing is invested",
                detail="There are no security positions. The whole balance is available to invest according to the client's profile.",
                numbers={"cash_pct": cash_pct, "cash_chf": round_chf(cash)},
                materiality_chf=cash,
                source=SOURCE_CASH,
            )
        )
    elif cash_pct - target_pct >= CASH_EXCESS_MIN_PP:
        excess = round_chf((cash_pct - target_pct) / 100 * aum)
        out.append(
            Finding(
                id="liq-cash",
                type=FindingType.LIQUIDITY,
                severity=Severity.OPPORTUNITY,
                title=f"Cash {pct(cash_pct)} of assets vs {target_label} {pct(target_pct)}: ≈ {chf(excess)} available to invest",
                detail=f"Liquidity is {chf(round_chf(cash))}; at the {target_label} of {pct(target_pct)} about {chf(excess)} could be put to work.",
                numbers={"cash_pct": cash_pct, "target_pct": target_pct, "excess_chf": excess},
                materiality_chf=excess,
                source=SOURCE_CASH,
            )
        )

    # b) Bedarf aus Notizen
    need, note_id = liquidity_need_from_notes(client)
    if need:
        need_chf = round_chf(need)
        cash_chf = round_chf(cash)
        if need > cash:
            shortfall = round_chf(need - cash)
            out.append(
                Finding(
                    id="liq-need",
                    type=FindingType.LIQUIDITY,
                    severity=Severity.ERROR,
                    title=f"Liquidity need of {chf(need_chf)} from the client notes is not covered: cash is {chf(cash_chf)}",
                    detail=f"Shortfall of {chf(shortfall)}. Raising liquidity (sale or transfer) should be discussed before the need becomes due.",
                    numbers={"need_chf": need_chf, "cash_chf": cash_chf, "shortfall_chf": shortfall},
                    related_ids=[note_id] if note_id else [],
                    # Gewicht = ungedeckter Anteil des BEDARFS (CASE-012: 98 %), nicht Lücke / Vermögen (33 %) —
                    # eine Steuerzahlung, die nicht bezahlt werden kann, ist nicht "klein", nur weil das Depot gross ist.
                    materiality_chf=aum * min(1.0, (need - cash) / need),
                    source=SOURCE_NEED,
                )
            )
        else:
            out.append(
                Finding(
                    id="liq-need",
                    type=FindingType.LIQUIDITY,
                    severity=Severity.INFO,
                    title=f"Liquidity need of {chf(need_chf)} from the client notes is covered by {chf(cash_chf)} cash",
                    detail="The amount mentioned in the notes is available; no action needed on liquidity.",
                    numbers={"need_chf": need_chf, "cash_chf": cash_chf},
                    related_ids=[note_id] if note_id else [],
                    materiality_chf=need,
                    source=SOURCE_NEED,
                )
            )

    # c) Fälligkeiten
    as_of = fs.data_as_of
    if as_of:
        for p in securities:
            if p.maturity_date is None:
                continue
            days = (p.maturity_date - as_of).days
            if 0 <= days <= MATURITY_WINDOW_DAYS:
                weight = num(p.client_weight_pct if p.client_weight_pct is not None else p.weight_pct)
                amount = round_chf(p.amount_chf)
                out.append(
                    Finding(
                        id=f"liq-maturity-{p.security_id}",
                        type=FindingType.LIQUIDITY,
                        severity=Severity.OPPORTUNITY,
                        title=f"{truncate(p.name, 50)} ({pct(weight)}, {chf(amount)}) matures {date_str(p.maturity_date)} — reinvestment needed",
                        detail=f"The bond matures in {days} days; the proceeds of about {chf(amount)} need a new home.",
                        numbers={"weight_pct": weight, "amount_chf": amount, "days_to_maturity": float(days)},
                        security_ids=[p.security_id],
                        materiality_chf=p.amount_chf,
                        source=SOURCE_MATURITY,
                    )
                )
    return out
