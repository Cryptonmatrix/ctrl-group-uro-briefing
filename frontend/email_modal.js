// Post-Call Follow-up Email & Sales Guidance Modal
// Hängt sich an den 'Follow-up E-Mail'-Button in der Clientbar an.
// Lädt POST /api/clients/{ref}/followup-email und rendert Kunden-Mail + Sales Guidance.

(() => {
  const h = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const $ = s => document.querySelector(s);

  document.head.insertAdjacentHTML('beforeend', `<style>
    #emailmodal{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(20,22,26,.55);
      z-index:9999;display:none;align-items:center;justify-content:center;padding:16px}
    #emailmodal.active{display:flex}
    .em-box{background:#fff;border-radius:4px;box-shadow:0 12px 36px rgba(0,0,0,.22);
      width:960px;max-width:96vw;max-height:92vh;display:flex;flex-direction:column;overflow:hidden;
      border:1px solid #c8c8d0}
    .em-head{background:#f8f9fa;border-bottom:1px solid var(--line);padding:12px 18px;
      display:flex;align-items:center;gap:12px}
    .em-head h3{margin:0;font-size:14px;font-weight:600;display:flex;align-items:center;gap:8px;color:var(--ink)}
    .em-head .spacer{flex:1}
    .em-lang{display:flex;gap:4px;background:#e8e8ed;padding:2px;border-radius:4px}
    .em-lang button{background:none;border:0;padding:3px 8px;font-size:11px;font-weight:600;
      border-radius:3px;color:#555;cursor:pointer}
    .em-lang button.active{background:#fff;color:var(--uro-blue);box-shadow:0 1px 3px rgba(0,0,0,.1)}
    .em-close{background:none;border:0;font-size:18px;line-height:1;color:#888;cursor:pointer;padding:4px}
    .em-close:hover{color:#222}
    .em-body{flex:1;overflow:auto;display:grid;grid-template-columns:1.2fr 1fr;gap:0;background:#f2f2f5}
    @media(max-width:768px){ .em-body{grid-template-columns:1fr} }
    .em-col{padding:16px;overflow:auto}
    .em-col.left{background:#fff;border-right:1px solid var(--line)}
    .em-col.right{background:#fcfcfd}
    .em-col-title{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;
      color:var(--muted);margin:0 0 12px;display:flex;align-items:center;justify-content:space-between}
    .em-badge-intern{background:#fff2e8;color:#d44d00;border:1px solid #ffd5b8;
      font-size:9.5px;padding:2px 6px;border-radius:3px;font-weight:600}
    
    .em-card{background:#fff;border:1px solid var(--line);border-radius:3px;padding:12px;margin-bottom:12px}
    .em-field-label{font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin-bottom:3px}
    .em-subj{font-size:13px;font-weight:600;padding:6px 8px;background:#fafafc;
      border:1px solid var(--line);border-radius:2px;margin-bottom:10px}
    .em-email-text{font-size:12.5px;line-height:1.6;color:#2c2c34;white-space:pre-wrap;background:#fafafc;
      border:1px solid var(--line);padding:10px 12px;border-radius:2px;max-height:420px;overflow:auto}
    .em-email-text ul{margin:6px 0;padding-left:18px}
    .em-email-text li{margin:3px 0}
    
    .em-actions{display:flex;gap:8px;margin-top:10px}
    .em-btn{font-size:12px;font-weight:600;padding:6px 12px;border-radius:3px;cursor:pointer;
      border:1px solid var(--line);background:#fff;color:var(--ink);display:inline-flex;align-items:center;gap:6px}
    .em-btn:hover{background:#f4f4f7}
    .em-btn.primary{background:var(--uro-orange);color:#fff;border-color:var(--uro-orange)}
    .em-btn.primary:hover{background:#e66000}
    .em-btn.blue{background:var(--uro-blue);color:#fff;border-color:var(--uro-blue)}
    .em-btn.blue:hover{background:#458ad6}
    
    .em-sec{margin-bottom:12px}
    .em-sec-title{font-size:11px;font-weight:600;color:var(--ink);margin-bottom:5px;display:flex;align-items:center;gap:6px}
    .em-item{font-size:12px;line-height:1.45;padding:6px 8px;background:#fff;border-left:3px solid var(--uro-blue);
      border:1px solid var(--line);border-left-width:3px;margin-bottom:5px;border-radius:2px}
    .em-item.opp{border-left-color:var(--green);background:#f6fcf8}
    .em-item.warn{border-left-color:var(--uro-red);background:#fdf6f5}
    .em-item.date{border-left-color:var(--violet);background:#f9f7fd;font-weight:500}
    
    .em-crm-box{background:#fff;border:1px solid var(--line);padding:8px 10px;border-radius:2px;
      font-size:11.5px;line-height:1.5;color:#333;margin-bottom:6px;font-family:monospace}
    
    .em-loading{padding:40px;text-align:center;color:var(--muted);font-size:13px}
    .em-mode{font-size:10px;padding:2px 7px;border-radius:2px;text-transform:uppercase;letter-spacing:.4px;font-weight:600}
    .em-mode.ai{background:#eef7ee;color:#2f7d52;border:1px solid #bce2c7}
    .em-mode.fallback{background:#fdf5e8;color:#b26a00;border:1px solid #fed89a}
  </style>`);

  // Inject modal markup
  document.body.insertAdjacentHTML('beforeend', `
    <div id="emailmodal">
      <div class="em-box">
        <div class="em-head">
          <h3><span>✉️</span> Nachfass-E-Mail & Vertriebsnotizen</h3>
          <span class="em-mode ai" id="em_mode">KI-generiert</span>
          <span class="spacer"></span>
          <div class="em-lang">
            <button class="active" id="em_lang_de">DE</button>
            <button id="em_lang_en">EN</button>
          </div>
          <button class="em-close" id="em_close">✕</button>
        </div>
        <div id="em_content" class="em-body">
          <div class="em-loading">Lade E-Mail-Entwurf und Vertriebsnotizen …</div>
        </div>
      </div>
    </div>
  `);

  let currentLang = 'de';
  let cachedData = null;

  async function loadEmail(ref, lang) {
    const box = $('#em_content');
    box.innerHTML = `<div class="em-col left" style="grid-column:1/-1;text-align:center;padding:40px">
      Lade E-Mail-Entwurf und Vertriebsnotizen (${lang.toUpperCase()}) …</div>`;

    try {
      const res = await fetch(`/api/clients/${encodeURIComponent(ref)}/followup-email`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language: lang })
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      cachedData = data;
      renderEmail(data);
    } catch (err) {
      box.innerHTML = `<div class="em-col left" style="grid-column:1/-1;padding:24px;color:var(--uro-red)">
        <b>Fehler beim Erstellen der Nachfass-E-Mail:</b><br>${h(err.message)}</div>`;
    }
  }

  function renderEmail(data) {
    const email = data.email;
    const sales = data.sales_notes;
    const modeBadge = $('#em_mode');
    if (modeBadge) {
      modeBadge.className = 'em-mode ' + (data.mode.startsWith('ai') ? 'ai' : 'fallback');
      modeBadge.textContent = data.mode.startsWith('ai') ? 'KI-generiert (geprüft)' : 'Regelbasiert (Fallback)';
    }

    const emailFullText = [
      email.salutation,
      '',
      email.intro,
      '',
      ...(email.portfolio_recap || []).map(p => `• ${p}`),
      '',
      (currentLang === 'de' ? 'Vereinbarte nächste Schritte:' : 'Agreed next steps:'),
      ...(email.agreed_next_steps || []).map(s => `• ${s}`),
      '',
      email.closing
    ].join('\n');

    const html = `
      <div class="em-col left">
        <div class="em-col-title">
          <span>Kunden-E-Mail (Entwurf)</span>
          <span style="font-weight:normal;text-transform:none">${h(data.display_name || data.client_ref)}</span>
        </div>
        
        <div class="em-field-label">${currentLang === 'de' ? 'Betreff' : 'Subject'}</div>
        <div class="em-subj" id="em_subj_text">${h(email.subject)}</div>

        <div class="em-field-label">${currentLang === 'de' ? 'Nachricht' : 'Body'}</div>
        <div class="em-email-text" id="em_body_text">${h(emailFullText)}</div>

        <div class="em-actions">
          <button class="em-btn primary" id="em_copy_btn">📋 E-Mail kopieren</button>
          <a class="em-btn blue" id="em_mailto_btn" href="#" style="text-decoration:none">✉️ In Mail-App öffnen</a>
        </div>
      </div>

      <div class="em-col right">
        <div class="em-col-title">
          <span>Sales & CRM Guidance</span>
          <span class="em-badge-intern">INTERN</span>
        </div>

        <div class="em-sec">
          <div class="em-sec-title">💡 ${currentLang === 'de' ? 'Cross-Selling & Ertragschancen' : 'Commercial & Cross-Selling'}</div>
          ${(sales.cross_sell_opportunities || []).map(o => `<div class="em-item opp">${h(o)}</div>`).join('') || '<div class="em-item">Keine spezifischen Opportunitäten.</div>'}
        </div>

        <div class="em-sec">
          <div class="em-sec-title">🛡️ ${currentLang === 'de' ? 'Regulatorik & Risikoüberwachung' : 'Suitability & Risk Actions'}</div>
          ${(sales.suitability_or_risk_actions || []).map(r => `<div class="em-item warn">${h(r)}</div>`).join('') || '<div class="em-item">Keine offenen Risikopunkte.</div>'}
        </div>

        <div class="em-sec">
          <div class="em-sec-title">⏱️ ${currentLang === 'de' ? 'Wiedervorlage-Empfehlung' : 'Next Contact Deadline'}</div>
          <div class="em-item date">📅 ${h(sales.next_contact_date_hint || 'Binnen 5 Bankwerktagen')}</div>
        </div>

        <div class="em-sec">
          <div class="em-sec-title">📝 ${currentLang === 'de' ? 'CRM-Aktivitätseintrag' : 'CRM Log Entry'}</div>
          <div class="em-crm-box" id="em_crm_text">${h(sales.crm_log_entry)}</div>
          <button class="em-btn" id="em_copy_crm_btn" style="width:100%;justify-content:center">📋 CRM-Eintrag kopieren</button>
        </div>
      </div>
    `;

    $('#em_content').innerHTML = html;

    // Mailto setup
    const mailtoSubject = encodeURIComponent(email.subject);
    const mailtoBody = encodeURIComponent(emailFullText);
    $('#em_mailto_btn').href = `mailto:?subject=${mailtoSubject}&body=${mailtoBody}`;

    // Copy handlers
    $('#em_copy_btn').onclick = () => {
      const full = `Betreff: ${email.subject}\n\n${emailFullText}`;
      navigator.clipboard.writeText(full).then(() => {
        const btn = $('#em_copy_btn');
        btn.textContent = '✓ Kopiert!';
        setTimeout(() => { btn.textContent = '📋 E-Mail kopieren'; }, 2000);
      });
    };

    $('#em_copy_crm_btn').onclick = () => {
      navigator.clipboard.writeText(sales.crm_log_entry).then(() => {
        const btn = $('#em_copy_crm_btn');
        btn.textContent = '✓ CRM-Eintrag kopiert!';
        setTimeout(() => { btn.textContent = '📋 CRM-Eintrag kopieren'; }, 2000);
      });
    };
  }

  // Open / Close events
  function openModal() {
    if (!window.current) return;
    $('#emailmodal').classList.add('active');
    loadEmail(window.current, currentLang);
  }

  function closeModal() {
    $('#emailmodal').classList.remove('active');
  }

  $('#em_close').onclick = closeModal;
  $('#emailmodal').onclick = e => {
    if (e.target.id === 'emailmodal') closeModal();
  };

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && $('#emailmodal').classList.contains('active')) {
      closeModal();
    }
  });

  // Language switch
  $('#em_lang_de').onclick = () => {
    if (currentLang === 'de') return;
    currentLang = 'de';
    $('#em_lang_de').classList.add('active');
    $('#em_lang_en').classList.remove('active');
    if (window.current) loadEmail(window.current, 'de');
  };

  $('#em_lang_en').onclick = () => {
    if (currentLang === 'en') return;
    currentLang = 'en';
    $('#em_lang_en').classList.add('active');
    $('#em_lang_de').classList.remove('active');
    if (window.current) loadEmail(window.current, 'en');
  };

  // Attach to button
  window.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('emailbtn');
    if (btn) {
      btn.onclick = openModal;
    }
  });
})();
