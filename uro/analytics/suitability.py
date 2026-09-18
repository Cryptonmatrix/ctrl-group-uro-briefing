"""OWNER: JACOB — Verstösse und Risikoprofil-Abgleich.

Hier sitzt der stärkste Befund des Projekts (siehe CLAUDE.md §4):
14 Portfolios reissen das Volatilitätslimit ihres Risikoprofils, bei 11 davon
meldet die Suitability-Engine null Verstösse — weil ihnen keine Strategie
zugewiesen ist und die SAA-Regeln deshalb nie feuern.

Wir rechnen unabhängig davon (`risk_profile_findings`, Typ RISK_PROFILE).

Verstösse aus SuitabilityViolations[] werden NICHT neu erkannt, nur angereichert:
  - IndividualRuleOverrides filtern (Regeln, die der Kunde bewusst abgewählt hat)
  - gleicher RuleCode → EIN Finding mit allen betroffenen Titeln (23× "Cluster risk" wären sonst 23 Findings)
  - SecurityIsin → Name über die CHF-Tranche
  - ViolationPath → "actual vs limit", wenn die Werte wie Anteile aussehen (data-notes §8)
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from uro.analytics.format import num, pct, slug, truncate
from uro.config import NO_STRATEGY_NAMES, VOLA_ERROR_FACTOR
from uro.ingest import ReferenceIndex, get, lst
from uro.models import Finding, FindingType, Severity

SOURCE_VIOLATIONS = "clients.json › SuitabilityViolations"
SOURCE_RISK = "clients.json › Portfolios[].Volatility vs reference.json › RiskProfiles[].MaxVola"


def _limit_from_path(violation: dict[str, Any]) -> tuple[float, float] | None:
    """Letzter ViolationPath-Eintrag, dessen Werte wie Anteile (0–1.5) aussehen → (actual, limit) als Brüche."""
    found: tuple[float, float] | None = None
    for entry in lst(violation, "ViolationPath"):
        field = str(get(entry, "FieldName", ""))
        if "ClientType" in field:
            continue
        left, right = get(entry, "LeftValue"), get(entry, "RightValue")
        if not isinstance(left, int | float) or not isinstance(right, int | float):
            continue
        if 0 <= left <= 1.5 and 0 < right <= 1.5:
            found = (float(left), float(right))
    return found


def violation_findings(
    client: dict[str, Any],
    ref: ReferenceIndex,
    portfolio_nr_by_id: dict[Any, str],
    aum: float,
) -> list[Finding]:
    """Aus SuitabilityViolations[] (bei 20 von 47 Klienten null). Ein Finding je RuleCode."""
    overrides = {get(o, "RuleCode") for o in lst(client, "IndividualRuleOverrides")}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for v in lst(client, "SuitabilityViolations"):
        code = get(v, "RuleCode")
        if not code or code in overrides:
            continue
        groups[str(code)].append(v)

    out: list[Finding] = []
    for code, items in groups.items():
        is_error = any(get(v, "Severity") == "Error" for v in items)
        pnrs = sorted({portfolio_nr_by_id.get(get(v, "PortfolioId")) or str(get(v, "PortfolioId", "")) for v in items})

        affected: list[tuple[bool, float, str, int | None, tuple[float, float] | None]] = []
        for v in items:
            isin = get(v, "SecurityIsin")
            sec = ref.security_by_isin(isin) if isin else None
            name = str(get(sec, "Name") or isin or "").strip()
            limits = _limit_from_path(v)
            ratio = limits[0] / limits[1] if limits and limits[1] else 0.0
            affected.append((get(v, "Severity") == "Error", ratio, name, get(sec, "Id"), limits))
        affected.sort(key=lambda a: (not a[0], -a[1]))  # Errors zuerst, dann grösste Überschreitung

        names = [a[2] for a in affected if a[2]]
        security_ids = sorted({a[3] for a in affected if a[3] is not None})
        worst = next((a for a in affected if a[4]), None)

        numbers: dict[str, float] = {}
        detail_parts = [f"{len(items)} active violation(s) of rule '{code}' in portfolio {', '.join(pnrs)}."]
        per_security = []
        for _, _, name, _, limits in affected:
            if not limits:
                continue
            label = name or "portfolio"
            per_security.append(f"{label}: {pct(limits[0] * 100)} vs limit {pct(limits[1] * 100)}")
        if per_security:
            detail_parts.append("Actual vs limit — " + "; ".join(per_security) + ".")
        if worst and worst[4]:
            numbers = {"actual_pct": num(worst[4][0] * 100), "limit_pct": num(worst[4][1] * 100)}
        rule_text = get(items[0], "RuleDescription") or get(ref.rule(code), "Description")
        if rule_text:
            detail_parts.append(f"Rule text (DE): '{truncate(str(rule_text), 160)}'")

        title = f"Suitability {'ERROR' if is_error else 'WARNING'}: {code}"
        if names:
            title += f" — {truncate(', '.join(dict.fromkeys(names)), 90)}"

        out.append(
            Finding(
                id=f"viol-{slug(code)}",
                type=FindingType.SUITABILITY_VIOLATION,
                severity=Severity.ERROR if is_error else Severity.WARNING,
                title=title,
                detail=" ".join(detail_parts),
                numbers=numbers,
                portfolio_nr=", ".join(pnrs) if pnrs else None,
                security_ids=security_ids,
                materiality_chf=aum * (0.3 if is_error else 0.1),
                source=SOURCE_VIOLATIONS,
            )
        )
    return out


def risk_profile_findings(
    client: dict[str, Any], portfolio: dict[str, Any], profile: dict[str, Any] | None, aum: float
) -> list[Finding]:
    """Portfolio.Volatility gegen RiskProfiles[].MaxVola — unabhängig von der Regel-Engine.

    Fehlt das Profil oder die Volatilität, ist das ein DATA_GAP-Finding, kein Fehler.
    """
    pnr = str(get(portfolio, "PortfolioNr", "?"))
    vola = get(portfolio, "Volatility")
    max_vola = get(profile, "MaxVola") if profile else None

    if profile is None:
        return [
            Finding(
                id=f"gap-profile-{pnr}",
                type=FindingType.DATA_GAP,
                severity=Severity.WARNING,
                title=f"No risk profile on file — suitability of portfolio {pnr} cannot be assessed",
                detail="Without a risk profile there is no volatility ceiling to compare against. Reassessing the profile is the first step.",
                portfolio_nr=pnr,
                materiality_chf=aum,
                source=SOURCE_RISK,
            )
        ]
    if vola is None:
        return [
            Finding(
                id=f"gap-vola-{pnr}",
                type=FindingType.DATA_GAP,
                severity=Severity.WARNING,
                title=f"Portfolio volatility not available for {pnr}",
                detail=f"The risk engine has no volatility figure for {pnr}; the profile limit cannot be checked.",
                portfolio_nr=pnr,
                materiality_chf=aum,
                source=SOURCE_RISK,
            )
        ]
    if max_vola is None or vola <= max_vola:
        return []

    factor = vola / max_vola
    over_pct = num((factor - 1) * 100)
    vola_pct = num(vola * 100)
    max_pct = num(max_vola * 100)
    reported = len(lst(client, "SuitabilityViolations"))
    profile_name = str(get(profile, "Name", "risk profile"))
    strategy = get(portfolio, "StrategyName")

    notes = []
    if strategy in NO_STRATEGY_NAMES:
        notes.append("No strategy is assigned to the portfolio, so the SAA-based rules never fire.")
    if reported == 0:
        notes.append("The rule engine reports 0 violations for this client — the breach is invisible in the standard violation list.")
    else:
        notes.append(f"The rule engine reports {reported} violation(s) for this client, none of them this volatility breach.")

    return [
        Finding(
            id=f"risk-breach-{pnr}",
            type=FindingType.RISK_PROFILE,
            severity=Severity.ERROR if factor >= VOLA_ERROR_FACTOR else Severity.WARNING,
            title=f"Portfolio volatility {pct(vola_pct)} exceeds the {pct(max_pct)} limit of {profile_name}",
            detail=(
                f"Portfolio {pnr} runs at {pct(vola_pct)} volatility against a {pct(max_pct)} ceiling — "
                f"{pct(over_pct)} above the limit. " + " ".join(notes)
            ),
            numbers={"volatility_pct": vola_pct, "max_volatility_pct": max_pct, "overshoot_pct": over_pct},
            portfolio_nr=pnr,
            materiality_chf=aum,
            source=SOURCE_RISK,
        )
    ]
