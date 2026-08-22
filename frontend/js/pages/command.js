// ======================== pages/command.js ========================
// Page 01: Command Center

const CommandPage = {
  // Cache of scenario metadata from /api/scenarios
  _scenarios: {},

  async load() {
    try {
      const [health, decisions, scenarios] = await Promise.all([
        getHealth(),
        getDecisions(),
        get('/scenarios').catch(() => ({})),
      ]);
      // Merge backend scenario descriptions into our DT metadata
      Object.entries(scenarios).forEach(([type, sc]) => {
        if (DT[type]) {
          DT[type].desc        = sc.description || DT[type].desc;
          DT[type].realEntity  = sc.primary_entity;
          DT[type].realUrgency = sc.urgency;
        }
      });
      this._scenarios = scenarios;
      App.decisions   = decisions;
      this.render(health, decisions);
    } catch(e) { console.error('Dashboard error', e); }
  },

  render(health, decisions) {
    el('cc-datetime').innerHTML = fmtDT();

    const active = decisions.filter(d =>
      !['completed', 'rejected'].includes(d.status));
    const cnt = active.length;

    // ── KPI 01: Critical decisions waiting ──────────────────────
    el('kpi-critical').textContent = String(cnt).padStart(2, '0');
    el('q-count').textContent = cnt;
    el('nav-badge').textContent = cnt;
    el('nav-badge').style.display = cnt > 0 ? '' : 'none';
    el('bell-dot').style.display  = cnt > 0 ? '' : 'none';

    // ── KPI 02: Agents online ────────────────────────────────────
    const ag = health.agents_online || 8;
    el('kpi-agents').innerHTML =
      `${ag}<span style="font-size:1rem;font-weight:400;color:var(--text3)"> / 8</span>`;
    el('ag-online').textContent = ag;

    // ── KPI 03: Total decisions this session ─────────────────────
    const session = decisions.filter(d => !d.decision_id?.startsWith('HIST-'));
    el('kpi-today').textContent = session.length || decisions.length;

    // ── KPI 04: HITL acceptance rate ─────────────────────────────
    const decided  = decisions.filter(d => d.human_decision);
    const accepted = decided.filter(d => d.human_decision === 'accept');
    el('kpi-hitl').textContent = decided.length > 0
      ? (accepted.length / decided.length * 100).toFixed(1) + '%'
      : '--';

    // ── System status (sidebar footer) ───────────────────────────
    el('sys-txt').textContent = health.status === 'healthy'
      ? 'All systems nominal' : 'Degraded';
    el('sys-sub').textContent = `${ag}/8 agents · ${health.version || 'v1.0'}`;
    el('sys-dot').className   = 's-dot ' + (health.status === 'healthy' ? 'dot-g' : 'dot-a');

    // ── User info from platform field ─────────────────────────────
    // Keep hardcoded user for now; if a /api/user endpoint exists use it
    // el('tb-uname') already set in HTML defaults

    this.renderQueue(decisions);
    this.renderAgents(health);
  },

  renderQueue(decisions) {
    const body = el('queue-body');
    // Filter out seeded historical records (blank description)
    const live = decisions.filter(d =>
      !d.decision_id?.startsWith('HIST-') && d.description);

    if (!live.length) {
      body.innerHTML = `<div class="empty">
        <div class="empty-icon">⚡</div>
        <div>No active decisions</div>
        <button class="btn btn-primary btn-sm" style="margin-top:10px"
          onclick="App.nav('scenarios')">Run a Scenario</button>
      </div>`;
      return;
    }

    // Sort: awaiting_human_review and blocked first, then completed
    const sorted = [...live].sort((a, b) => {
      const p = {
        awaiting_human_review: 0,
        pending: 0,
        blocked: 1,
        completed: 3,
        rejected: 3,
      };
      return (p[a.status] ?? 2) - (p[b.status] ?? 2);
    });

    body.innerHTML = sorted.map(d => {
      const m = DT[d.decision_type] || {
        label: d.decision_type, icon: '📌', urgency: 'P3', sla: '?'
      };
      // Decide status tag
      const isBlocked  = d.status === 'blocked' || d.status === 'blocked_escalation';
      const isDone     = d.status === 'completed';
      const isAwaiting = d.awaiting_human || d.status === 'awaiting_human_review';
      const tag = isBlocked  ? '<span class="tag-blk">BLOCKED</span>'
        : isDone             ? '<span class="tag-rdy">READY</span>'
        : isAwaiting         ? '<span class="tag-cav">READY W/ CAVEATS</span>'
        :                      '<span class="tag-nrd">NOT-READY</span>';

      return `<div class="q-item" onclick="CommandPage.handleQueueItemClick('${d.decision_type}')">
        <div class="q-dt">${d.decision_type}</div>
        <div class="q-body">
          <div class="q-ttl">${esc(d.description || m.label)}</div>
          <div class="q-sub">${esc(d.primary_entity || '')}</div>
        </div>
        <div class="q-tags">
          <span class="tag-pri tag-pri-${(m.urgency||'').toLowerCase()}">${m.urgency} · ${m.sla}</span>
          ${tag}
        </div>
        <div class="q-arr">›</div>
      </div>`;
    }).join('');
  },

  renderAgents(health) {
    // Use agent list, mark market as degraded if health is not fully healthy
    const isFullHealth = health.status === 'healthy';
    el('agents-panel').innerHTML = AGENTS.map(a => {
      const degraded = (a.k === 'market') && !isFullHealth;
      return `<div class="ag-row">
        <div class="ag-dot ${degraded ? 'ag-dot-a' : 'ag-dot-g'}"></div>
        <div style="flex:1">
          <div class="ag-name">${a.lbl}</div>
          <div class="ag-model">${a.model}</div>
        </div>
        <div class="ag-time">${a.t}ms</div>
      </div>`;
    }).join('');
  },

  handleQueueItemClick(type) {
    ScenariosPage.run(type);
  },

  async clearQueue() {
    if (!confirm('Clear ALL live decisions? Historical data is preserved.')) return;
    try {
      const d = await post('/admin/reset');
      App.currentDecision = null;
      App.decisions = [];
      showToast(`Queue cleared: ${d.decisions_deleted || 0} decision(s) removed.`, 'success');
      await this.load();
    } catch(e) { showToast('Error: ' + e.message, 'error'); }
  },
};
