"""OWNER: LEVIN — Gespraechsprotokoll als druckfertige Seite.

Das dritte Stueck der Produktgeschichte: vor dem Gespraech das Briefing,
waehrend des Gespraechs der Chat, danach dieses Dokument.

Bewusst HTML statt PDF: reportlab und weasyprint sind nicht installiert und
sollen es fuer einen Prototypen auch nicht werden. Der Browser macht aus dieser
Seite ueber "Drucken -> Als PDF sichern" ein sauberes PDF. Das @page-CSS unten
setzt die Raender.

Die Zielgruppe ist der Berater, nicht der Endkunde: Es ist die Unterlage, mit der
er das Gespraech nachbereitet und aus der er dem Kunden schreibt. Deshalb stehen
Zahlen drin, aber keine Finding-IDs — die braucht nur die Maschine.

Selbsttest ohne API-Schluessel:
    uv run python -m uro.report --demo > /tmp/protokoll.html && open /tmp/protokoll.html
"""

from __future__ import annotations

import html
import sys
from datetime import datetime

from uro.models import BriefingResult

CSS = """
:root{--ink:#1c1c1f;--muted:#6b6b73;--line:#d8d8dc;--red:#c0392b;--green:#2f7d52}
*{box-sizing:border-box}
body{margin:0;padding:28px 34px;color:var(--ink);background:#fff;
  font:13px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  max-width:820px}
h1{font-size:19px;margin:0 0 2px}
h2{font-size:11px;text-transform:uppercase;letter-spacing:.7px;color:var(--muted);
  margin:22px 0 8px;padding-bottom:4px;border-bottom:1px solid var(--line)}
.sub{color:var(--muted);font-size:12px;margin-bottom:18px}
.kpis{display:flex;gap:26px;flex-wrap:wrap;padding:12px 0;border-top:1px solid var(--line);
  border-bottom:1px solid var(--line)}
.kpi .k{font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted)}
.kpi .v{font-size:16px;font-variant-numeric:tabular-nums}
.kpi .v.warn{color:var(--red)}
.lead{font-size:14px;line-height:1.5;margin:14px 0 0}
ul{margin:0;padding-left:18px}
li{margin:3px 0}
ol.steps{margin:0;padding-left:20px;counter-reset:s}
ol.steps li{margin:0 0 13px;break-inside:avoid}
ol.steps .why{color:var(--muted);font-size:12px;margin-top:2px}
.fill{margin-top:6px;display:flex;gap:26px;font-size:11px;color:var(--muted)}
.fill span{border-bottom:1px solid var(--line);min-width:180px;padding-bottom:1px}
.open li{color:var(--ink)}
.open .sev{color:var(--red);font-weight:600}
footer{margin-top:26px;padding-top:10px;border-top:1px solid var(--line);
  font-size:10.5px;color:var(--muted);line-height:1.5}
@media print{
  body{padding:0;max-width:none}
  h2{break-after:avoid}
  section{break-inside:avoid}
  @page{margin:18mm}
}
"""


def _e(value: object) -> str:
    return html.escape(str(value if value is not None else ""))


def _chf(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}".replace(",", "'")


def _pct(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}%"


def render_report(result: BriefingResult) -> str:
    """Eine vollstaendige HTML-Seite als String. Alles aus den Daten wird escaped."""
    fs = result.fact_sheet
    b = result.briefing
    pf = fs.portfolios[0] if fs.portfolios else None

    vola = pf.volatility * 100 if pf and pf.volatility is not None else None
    limit = fs.max_volatility * 100 if fs.max_volatility is not None else None
    breach = vola is not None and limit is not None and vola > limit

    kpis = [
        ("Vermögen", f"CHF {_chf(fs.total_aum_chf)}", False),
        ("Liquidität", f"CHF {_chf(fs.total_liquidity_chf)}", False),
        ("Rendite 3M", _pct(pf.perf_3m_pct) if pf else "—", False),
        ("Volatilität", f"{_pct(vola, 1)} / Limit {_pct(limit, 1)}", breach),
        ("Risikoprofil", _e(fs.risk_profile_name or "nicht hinterlegt"), fs.risk_profile_name is None),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="k">{_e(k)}</div>'
        f'<div class="v{" warn" if warn else ""}">{v}</div></div>'
        for k, v, warn in kpis
    )

    sections = "".join(
        f"<section><h2>{_e(s.title)}</h2><ul>"
        + "".join(f"<li>{_e(st.text)}</li>" for st in s.statements)
        + "</ul></section>"
        for s in b.sections if s.statements
    )

    steps = "".join(
        f"<li><b>{_e(a.action)}</b><div class=\"why\">{_e(a.rationale)}</div>"
        '<div class="fill"><span>Verantwortlich</span><span>Bis wann</span>'
        '<span>Erledigt</span></div></li>'
        for a in b.next_best_actions
    ) or "<li>Keine Massnahmen vereinbart.</li>"

    # Offene Punkte: Fehler-Befunde, die keine der vereinbarten Massnahmen adressiert.
    adressiert = {i for a in b.next_best_actions for i in a.finding_ids}
    adressiert |= {i for s in b.sections for st in s.statements for i in st.finding_ids}
    offen = [f for f in fs.findings
             if f.severity.value == "error" and f.id not in adressiert][:5]
    offen_html = (
        "<ul class=\"open\">"
        + "".join(f'<li><span class="sev">Offen:</span> {_e(f.title)}</li>' for f in offen)
        + "</ul>"
    ) if offen else '<p style="color:#6b6b73">Alle als Fehler eingestuften Befunde wurden im Gespräch adressiert.</p>'

    fragen = "".join(
        f"<li><b>{_e(q.question)}</b><div class=\"why\">{_e(q.answer_hint)}</div></li>"
        for q in b.likely_questions
    )

    modus = {"ai": "KI-generiert", "ai_retry": "KI-generiert (zweiter Versuch)",
             "ai_gemini": "KI-generiert (Ersatzmodell)",
             "fallback": "regelbasiert, Sprachmodell nicht verfügbar"}.get(result.mode, result.mode)

    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="utf-8"><title>Gesprächsprotokoll {_e(result.client_ref)}</title>
<style>{CSS}</style></head>
<body>

<h1>Gesprächsprotokoll — {_e(result.display_name or result.client_ref)}</h1>
<div class="sub">{_e(result.client_ref)} · erstellt am {result.generated_at:%d.%m.%Y um %H:%M} Uhr</div>

<div class="kpis">{kpi_html}</div>

<p class="lead">{_e(b.headline)}</p>

{sections}

<section><h2>Vereinbarte nächste Schritte</h2>
  <ol class="steps">{steps}</ol>
</section>

<section><h2>Offene Punkte</h2>
  {offen_html}
</section>

{f'<section><h2>Themen für das nächste Gespräch</h2><ul class="steps">{fragen}</ul></section>' if fragen else ''}

<footer>
  Internes Vorbereitungs- und Protokolldokument für die Beratung. Keine Anlageberatung
  an den Endkunden.<br>
  Datenstand {result.generated_at:%d.%m.%Y}. Briefing {_e(modus)}. Alle Zahlen stammen aus
  der Portfolioanalyse und wurden gegen die Datenbasis geprüft.
</footer>

</body>
</html>"""


def _demo() -> BriefingResult:
    """Beispiel ohne API-Aufruf, damit sich das Layout pruefen laesst."""
    from uro.analytics import build_fact_sheet
    from uro.ingest import find_client, load_clients, load_reference
    from uro.llm.fallback import template_briefing

    clients = load_clients("data/clients.json")
    fs = build_fact_sheet(find_client(clients, "CASE-003"), load_reference("data/reference.json"))
    return BriefingResult(
        client_ref="CASE-003", display_name="Ron Burgundy", briefing=template_briefing(fs),
        fact_sheet=fs, mode="fallback", generated_at=datetime.now(),
    )


if __name__ == "__main__":
    if "--demo" in sys.argv:
        sys.stdout.write(render_report(_demo()))
    else:
        sys.stderr.write("Aufruf: uv run python -m uro.report --demo > /tmp/protokoll.html\n")
        sys.exit(1)
