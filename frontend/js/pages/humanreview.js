// ======================== pages/humanreview.js ========================
// Page 05: Human Review — HITL Decision

const HumanReviewPage = {
  _decisionId: null,

  render(d) {
    if (!d) return;
    const m       = DT[d.decision_type] || { label: d.decision_type, icon: '📌' };
    const top     = (d.recommended_actions || [])[0] || {};
    const sc      = top.aggregate_score || 0;
    const bids    = d.bids || [];
    const favorable = bids.filter(b => !b.is_veto && (b.score || 0) > 0.5).length;
    const hasVeto   = bids.some(b => b.is_veto);
    const vetoB     = bids.find(b => b.is_veto);

    this._decisionId = d.decision_id;

    // ── Header ───────────────────────────────────────────────────
    el('hr-crumb').textContent =
      `HUMAN REVIEW · ${esc(d.primary_entity || (d.decision_id||'').substring(0,8))} · ${d.decision_type}`;
    el('hr-title').textContent = `${m.icon} ${m.label}`;
    el('hr-chip').innerHTML =
      statusChip(d.status, d.awaiting_human) +
      `&nbsp;<span style="font-family:'JetBrains Mono',monospace;font-size:.68rem">${Math.round(sc * 100)}%</span>`;

    // ── Action description ────────────────────────────────────────
    el('hr-action').textContent = top.description || d.description || 'Recommendation pending.';

    // ── Stat row ─────────────────────────────────────────────────
    el('hr-conf').textContent  = sc ? Math.round(sc * 100) + '%' : '--';
    el('hr-bids').textContent  = bids.length ? `${favorable} / ${bids.length}` : '--';
    el('hr-compl').textContent = hasVeto ? '⚡ VETO' : '✓ PASS';

    // ── Clarification ────────────────────────────────────────────
    // clarification is an object {question,context} or null
    const clar = d.clarification && typeof d.clarification === 'object'
      ? d.clarification : null;

    if (clar) {
      el('clar-section').innerHTML = `
        <div class="clar-box" style="margin-bottom:14px">
          <div class="clar-lbl">⚠ Agent-Initiated Clarification Required</div>
          <div class="clar-q">${esc(clar.question || clar.context || 'Please confirm before proceeding.')}</div>
          <textarea class="clar-inp" id="clar-inp" placeholder="Type your answer here…"></textarea>
          <div class="clar-ft">
            <span class="clar-note">Human inputs are capped at 60% confidence · cannot resolve compliance gaps</span>
            <button class="btn btn-primary btn-sm" onclick="HumanReviewPage.submitClar('${d.decision_id}')">
              Submit Answer
            </button>
          </div>
        </div>`;
    } else {
      el('clar-section').innerHTML = '';
    }

    // ── Compliance lock card ──────────────────────────────────────
    if (hasVeto && vetoB) {
      el('cl-desc').textContent = vetoB.veto_reason
        || 'Compliance veto is active. This decision cannot proceed through normal bidding. Escalation to a Compliance Officer is the only valid resolution path.';
    }

    // ── Decision buttons vs. done state ──────────────────────────
    const decided = d.human_decision || d.status === 'completed' || d.status === 'rejected';
    el('dec-grid').style.display = decided ? 'none' : 'grid';

    if (decided) {
      el('dec-done').style.display = 'block';
      const labels = {
        accept: '✓ Approved — action queued for execution',
        reject: '✕ Declined — decision halted and logged',
        edit:   '✎ Modified — amended action submitted',
      };
      el('dec-done-txt').textContent =
        labels[d.human_decision] ||
        (d.status === 'completed' ? '✓ Decision Complete' : '✕ Decision Rejected');
    } else {
      el('dec-done').style.display = 'none';
    }

    // ── Reset why-not panel ───────────────────────────────────────
    el('wn-ans').style.display  = 'none';
    el('wn-hint').style.display = 'block';
    el('wn-inp').value = '';
  },

  async decide(decision) {
    const id = App.currentDecision?.decision_id;
    if (!id) { showToast('No decision loaded', 'error'); return; }

    // Disable buttons immediately to prevent double-click
    el('dec-grid').querySelectorAll('button').forEach(b => b.disabled = true);

    try {
      const body = { decision };
      // If it's an edit, we could collect an edit description
      if (decision === 'edit') {
        const desc = prompt('Describe your modification (optional):');
        if (desc) body.edit_description = desc;
      }
      await post('/decisions/' + id + '/respond', body);

      // Update local state
      App.currentDecision.human_decision = decision;
      App.currentDecision.status = decision === 'accept' ? 'completed' : 'rejected';
      this.render(App.currentDecision);

      const msgs = {
        accept: '✓ Decision approved and queued',
        reject: 'Decision declined and logged',
        edit:   'Modified decision submitted',
      };
      showToast(msgs[decision] || 'Decision recorded', 'success');

      // Refresh command center badge count
      CommandPage.load().catch(() => {});
    } catch(e) {
      el('dec-grid').querySelectorAll('button').forEach(b => b.disabled = false);
      showToast('Error: ' + e.message, 'error');
    }
  },

  async submitClar(id) {
    const t = el('clar-inp')?.value?.trim();
    if (!t) { showToast('Please enter a clarification answer', 'error'); return; }
    try {
      // API expects { answer: "..." } (ClarificationAnswer schema)
      await post('/decisions/' + id + '/clarify', { answer: t });
      showToast('Clarification submitted — re-evaluating…', 'success');
      // Reload the decision to see updated state
      const updated = await get('/decisions/' + id);
      App.currentDecision = updated;
      this.render(updated);
    } catch(e) { showToast('Error: ' + e.message, 'error'); }
  },

  async submitWhyNot() {
    const id = this._decisionId || App.currentDecision?.decision_id;
    const q  = el('wn-inp')?.value?.trim();
    if (!q)  { showToast('Type a question first', 'error'); return; }
    if (!id) { showToast('No decision loaded', 'error'); return; }

    el('wn-hint').style.display = 'none';
    el('wn-ans').style.display  = 'block';
    el('wn-txt').textContent    = 'Querying pre-computed bid state…';

    try {
      // API expects { alternative: "..." } (WhyNotRequest schema)
      const r = await post('/decisions/' + id + '/why-not', { alternative: q });
      el('wn-txt').textContent =
        r.response || r.explanation || r.answer || JSON.stringify(r);
    } catch(e) {
      el('wn-txt').textContent = 'Error: ' + e.message;
    }
  },
};
