// Follow-up-Chat unter dem Briefing (CLAUDE.md §2: Bonus Prio 1).
// Eigene Datei, damit index.html (Levin) konfliktarm bleibt: Sie hängt sich an renderFacts/renderBriefing
// an und nutzt nur die globalen `current` und `facts`. Backend: POST /api/clients/{ref}/chat → {answer, sources}.
(() => {
  const h = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const q = s => document.querySelector(s);

  const QUICK = [
    'What drove the recent performance?',
    'Has the client raised any concerns or wishes in the notes?',
    'Which positions carry the most risk?',
    'Are there open or rejected proposals?',
    'What should I propose in this conversation?',
  ];

  document.head.insertAdjacentHTML('beforeend', `<style>
    #chatcard .chatlog{max-height:360px;overflow:auto;padding:10px 13px;display:flex;flex-direction:column;gap:8px}
    #chatcard .hint{color:var(--muted);font-size:12px}
    #chatcard .msg{max-width:88%;padding:7px 10px;border-radius:3px;line-height:1.5}
    #chatcard .msg.user{align-self:flex-end;background:#eaf3fc;border:1px solid #d3e4f6}
    #chatcard .msg.bot{align-self:flex-start;background:#fafafa;border:1px solid var(--line)}
    #chatcard .msg.err{align-self:flex-start;background:#fdf5f4;border:1px solid #f1c9c4;color:#9b2c21}
    #chatcard .msg.wait{color:var(--muted);font-style:italic}
    #chatcard .quick{display:flex;flex-wrap:wrap;gap:6px;padding:0 13px 10px}
    #chatcard .quick button{font-size:11px;border:1px solid var(--line);background:#fff;border-radius:12px;
      padding:3px 10px;color:#5a5a63}
    #chatcard .quick button:hover{border-color:var(--uro-blue);color:var(--uro-blue)}
    #chatcard form{display:flex;gap:8px;padding:10px 13px;border-top:1px solid var(--line)}
    #chatcard input{flex:1;border:1px solid var(--line);border-radius:2px;padding:6px 9px;font:inherit}
    #chatcard .cchip{font-size:10px;border:1px solid var(--line);border-radius:2px;padding:0 4px;margin:0 2px;
      color:var(--muted);background:#fff;cursor:help;white-space:nowrap}
  </style>`);

  const threads = {};         // ref → {history: [{role, content}], log: [{kind, html}]}
  let briefingData = null;    // letzte /briefing-Antwort: enthält das angereicherte Fact Sheet für Tooltips
  let pending = false;

  const thread = () => (threads[current] ??= {history: [], log: []});

  function lookup() {
    const fs = (briefingData && briefingData.client_ref === current) ? briefingData.fact_sheet : facts?.fact_sheet;
    const byId = {};
    for (const f of fs?.findings || []) byId[f.id] = `${f.title}\n\n${f.detail}\n\nSource: ${f.source}`;
    for (const p of fs?.portfolios || [])
      for (const pos of p.positions || [])
        byId[`pos-${pos.security_id}`] = `${pos.name} — ${pos.weight_pct.toFixed(1)}% of portfolio ${p.portfolio_nr}`;
    return byId;
  }

  // Antworttext: escapen, [id] / [id1, id2] als Quellen-Chip mit Tooltip, **fett**, Zeilenumbrüche.
  function renderAnswer(text) {
    const tips = lookup();
    return h(text)
      .replace(/\[([a-zA-Z0-9_,\s-]+)\]/g, (_, ids) => ids.split(',').map(s => s.trim()).filter(Boolean)
        .map(id => `<span class="cchip" title="${h(tips[id] || 'Source not in this fact sheet')}">${h(id)}</span>`).join(''))
      .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
      .replace(/\n/g, '<br>');
  }

  function paint() {
    const log = q('#chatlog');
    if (!log) return;
    const t = thread();
    log.innerHTML = t.log.length
      ? t.log.map(m => `<div class="msg ${m.kind}">${m.html}</div>`).join('')
      : '<div class="hint">Rückfragen zu diesem Klienten. Die Antwort stützt sich nur auf seine Daten und nennt die Quellen.</div>';
    if (pending) log.insertAdjacentHTML('beforeend', '<div class="msg bot wait">Claude sucht in den Daten …</div>');
    log.scrollTop = log.scrollHeight;

    const likely = (briefingData && briefingData.client_ref === current)
      ? briefingData.briefing.likely_questions.map(x => x.question) : [];
    q('#chatquick').innerHTML = [...likely, ...QUICK].slice(0, 6)
      .map(x => `<button type="button" data-q="${h(x)}">${h(x)}</button>`).join('');
  }

  async function ask(question) {
    question = question.trim();
    if (!question || pending || !current) return;
    const ref = current, t = thread();
    t.history.push({role: 'user', content: question});
    t.log.push({kind: 'user', html: h(question)});
    pending = true; paint();
    try {
      const res = await fetch(`/api/clients/${encodeURIComponent(ref)}/chat`, {
        method: 'POST', headers: {'content-type': 'application/json'},
        body: JSON.stringify({messages: t.history}),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      t.history.push({role: 'assistant', content: data.answer});
      t.log.push({kind: 'bot', html: renderAnswer(data.answer)});
    } catch (err) {
      t.history.pop();  // unbeantwortete Frage nicht in den Verlauf fürs Modell
      t.log.push({kind: 'err', html: `Keine Antwort: ${h(err.message)}`});
    } finally {
      pending = false;
      if (current === ref) paint();
    }
  }

  function mount() {
    const anchor = q('#bcard');
    if (!anchor || q('#chatcard')) return;
    anchor.insertAdjacentHTML('afterend', `
      <div class="card" id="chatcard">
        <h2>Rückfragen zum Klienten</h2>
        <div class="chatlog" id="chatlog"></div>
        <div class="quick" id="chatquick"></div>
        <form id="chatform" autocomplete="off">
          <input id="chatq" placeholder="z. B. What is the total semiconductor exposure?">
          <button class="action primary" type="submit">Fragen</button>
        </form>
      </div>`);
    q('#chatform').onsubmit = e => { e.preventDefault(); const i = q('#chatq'); ask(i.value); i.value = ''; };
    q('#chatquick').onclick = e => { const b = e.target.closest('button[data-q]'); if (b) ask(b.dataset.q); };
    paint();
  }

  const baseRenderFacts = renderFacts;
  renderFacts = function (d) { baseRenderFacts(d); mount(); };
  const baseRenderBriefing = renderBriefing;
  renderBriefing = function (d) { baseRenderBriefing(d); briefingData = d; paint(); };
})();
