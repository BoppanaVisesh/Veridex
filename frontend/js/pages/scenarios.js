// ======================== pages/scenarios.js ========================
// Page 02: Run Scenario (uses real /api/scenarios and live /api/catalog/products data)

const ScenariosPage = {
  _loaded: false,
  _products: [],
  _selectedProductId: '',

  async render() {
    // Load real scenario data and live catalog products
    if (!this._loaded) {
      try {
        const [sc, prods] = await Promise.all([
          get('/scenarios').catch(() => ({})),
          get('/catalog/products').catch(() => []),
        ]);

        this._products = prods || [];

        // Merge backend descriptions + entities into DT metadata
        Object.entries(sc).forEach(([type, data]) => {
          if (DT[type]) {
            if (data.description)   DT[type].desc       = data.description;
            if (data.primary_entity)DT[type].realEntity  = data.primary_entity;
            if (data.urgency != null)DT[type].realUrgency = data.urgency;
          }
        });
        this._loaded = true;
      } catch(e) { console.warn('Could not load scenarios/products from API:', e.message); }
    }
    this._populateProductSelectors();
    this._render();
  },

  async refreshProducts() {
    try {
      this._products = await get('/catalog/products').catch(() => []);
      this._populateProductSelectors();
      showToast(`Loaded ${this._products.length} live catalog products`, 'info');
    } catch(e) {
      showToast('Failed to refresh products', 'error');
    }
  },

  _populateProductSelectors() {
    const sel = el('sc-product-select');
    const datalist = el('cust-products-list');
    if (!sel) return;

    const currentVal = this._selectedProductId || sel.value || '';
    
    let html = `<option value="">-- Use Default Scenario Entity --</option>`;
    let dlHtml = '';

    this._products.forEach(p => {
      const name = p.name || p.id;
      const statusBadge = p.status ? `[${p.status.toUpperCase()}]` : '';
      const selected = (p.id === currentVal) ? 'selected' : '';
      html += `<option value="${esc(p.id)}" ${selected}>${esc(name)} ${statusBadge} (${esc(p.id.slice(0, 8))})</option>`;
      dlHtml += `<option value="${esc(p.id)}">${esc(name)} ${statusBadge}</option>`;
    });

    sel.innerHTML = html;
    if (datalist) datalist.innerHTML = dlHtml;
  },

  onProductSelected() {
    const sel = el('sc-product-select');
    this._selectedProductId = sel ? sel.value : '';
    if (this._selectedProductId) {
      const prod = this._products.find(p => p.id === this._selectedProductId);
      showToast(`Target product set: ${prod ? prod.name : this._selectedProductId}`, 'info');
    }
  },

  _render() {
    el('sc-grid').innerHTML = Object.entries(DT).map(([type, m]) => {
      const urgencyPriority = m.urgency || 'P3';
      const col = urgencyPriority === 'P0' ? 'var(--red)'
        : urgencyPriority === 'P1' ? 'var(--amber)'
        : urgencyPriority === 'P2' ? 'var(--blue)'
        : 'var(--text3)';

      // Show real entity if available or target product
      const activeEntity = this._selectedProductId || m.realEntity;
      const entityHint = activeEntity
        ? `<span style="font-family:'JetBrains Mono',monospace;font-size:.65rem;color:var(--blue)">→ ${esc(activeEntity)}</span>`
        : '';

      return `<div class="sc-card" onclick="ScenariosPage.run('${type}')">
        <div class="sc-type">${type}</div>
        <div class="sc-name">${m.icon} ${m.label}</div>
        <div class="sc-desc">${esc(m.desc)}</div>
        ${entityHint ? `<div style="margin-bottom:8px">${entityHint}</div>` : ''}
        <div class="sc-meta">
          <span style="display:flex;align-items:center;gap:4px">
            <span style="width:7px;height:7px;border-radius:50%;background:${col};display:inline-block"></span>
            ${urgencyPriority}
          </span>
          <span>SLA: ${m.sla}</span>
        </div>
        <button class="btn btn-primary btn-sm sc-run">Run Live →</button>
      </div>`;
    }).join('');
  },

  async run(type) {
    const m = DT[type] || { label: type, icon: '📌' };
    App.nav('missioncontrol');
    MissionControlPage.init(type, m);

    try {
      const payload = { decision_type: type };
      const selectedProd = el('sc-product-select')?.value || this._selectedProductId;
      if (selectedProd) {
        payload.product_id = selectedProd;
      }

      const data = await post('/decisions/run-scenario', payload);
      App.currentDecision = data;
      // Refresh decisions list (uses envelope-aware helper)
      const all = await getDecisions().catch(() => App.decisions);
      App.decisions = all;
      MissionControlPage.setRealData(data);
    } catch(e) {
      MissionControlPage.onError(e.message);
    }
  },

  async runCustom() {
    const type = el('cust-dt')?.value || 'D1';
    const entity = el('cust-entity')?.value?.trim();
    const desc = el('cust-desc')?.value?.trim();
    if (!entity) { showToast('Please select or enter a Product / Entity ID', 'error'); return; }
    
    const m = DT[type] || { label: type, icon: '📌' };
    App.nav('missioncontrol');
    MissionControlPage.init(type, m);
    
    try {
      const data = await post('/decisions', {
        decision_type: type,
        entity_id: entity,
        entity_type: 'Product',
        description: desc || `Custom ${type} review for ${entity}`
      });
      App.currentDecision = data;
      const all = await getDecisions().catch(() => App.decisions);
      App.decisions = all;
      MissionControlPage.setRealData(data);
      
      // Clear form inputs
      if (el('cust-entity')) el('cust-entity').value = '';
      if (el('cust-desc')) el('cust-desc').value = '';
    } catch(e) {
      MissionControlPage.onError(e.message);
    }
  }
};

// ======================== pages/missioncontrol.js ========================
const MissionControlPage = {
  _timer: null,
  _start: null,
  _realData: null,
  _currentDecisionType: null,
  _currentStageIndex: 0,

  init(type, m) {
    this._currentDecisionType = type;
    this._currentStageIndex = 0;
    this._realData = null;

    el('mc-crumb').textContent  = `MISSION CONTROL · ${type} · RUNNING`;
    el('mc-title').textContent  = `${type}: ${m.label}`;
    el('mc-chip').innerHTML     = '<span class="chip c-gray"><div class="spinner" style="width:10px;height:10px;border-width:1.5px;margin-right:4px;vertical-align:middle"></div>Initializing...</span>';
    el('mc-facts').textContent  = '--';
    el('mc-agents').textContent = '--';
    el('mc-score').textContent  = '--';
    el('mc-elapsed').textContent= '0:00.000';
    el('dre-status').textContent= 'Initializing...';
    el('dre-iter-badge').textContent = 'Iteration —';
    el('dre-gap').textContent   = 'Gathering evidence...';
    el('dre-gap-d').textContent = '—';
    el('dre-conf').textContent  = '—';
    el('dre-states-el').innerHTML = '';
    el('feed-body').innerHTML   = '<div style="color:var(--text3);font-size:.76rem;text-align:center;padding:18px">Starting pipeline...</div>';

    // Hide stage navigation during live execution
    const prev = el('mc-prev-stage');
    const next = el('mc-next-stage');
    const lbl = el('mc-stage-viewing-lbl');
    const live = el('mc-live-badge');
    if (prev) prev.style.display = 'none';
    if (next) next.style.display = 'none';
    if (lbl) lbl.style.display = 'none';
    if (live) live.style.display = 'block';

    this._start = Date.now();
    if (this._timer) clearInterval(this._timer);
    this._timer = setInterval(() => {
      const s = (Date.now() - this._start) / 1000;
      el('mc-elapsed').textContent =
        `0:${String(Math.floor(s)).padStart(2,'0')}.${String(Math.floor((s % 1) * 1000)).padStart(3,'0')}`;
    }, 50);

    renderPipelineTrack('mc-pipe-track', { simulationStage: 0 });
    renderPlanningStage(type);
    const legend = el('net-legend-el');
    if (legend) legend.style.display = 'flex';
    this.renderAgentProg([]);

    this.addFeed('info', 'Planner', `Received ${type} decision · classifying urgency...`);
    this.addFeed('info', 'Planner', `Routing to evidence agents in parallel...`);

    const scheduleStage = (stageNum, delay, action) => {
      setTimeout(() => {
        if (this._start === null) return;
        this._currentStageIndex = stageNum;
        renderPipelineTrack('mc-pipe-track', { simulationStage: stageNum });
        action();
      }, delay);
    };

    // Stage 1: EVIDENCE (600ms)
    scheduleStage(1, 600, () => {
      renderEvidenceStage(type, 0);
      const active = DECISION_AGENTS[type] || [];
      active.forEach((agentName, idx) => {
        setTimeout(() => {
          if (this._start === null) return;
          const cleanName = agentName.replace('_Agent', '').replace('_', ' ');
          this.addFeed('info', cleanName, `Querying sources for ${type} context...`);
          renderEvidenceStage(type, idx + 1);
        }, idx * 180);
      });
    });

    // Stage 2: DRE (2000ms)
    scheduleStage(2, 2000, () => {
      this.addFeed('info', 'DRE', 'Computing VoI scores across evidence gaps...');
      el('dre-status').textContent = 'Evaluating readiness...';
      el('dre-iter-badge').textContent = 'Iteration 1';
      el('dre-gap').textContent = 'Analyzing checklist...';
      
      const gaps = this._realData ? this._realData.evidence_gaps : [];
      renderDREStage(type, 'Evaluating', gaps);
    });

    // Stage 3: DETECT (3200ms)
    scheduleStage(3, 3200, () => {
      this.addFeed('info', 'Quality', 'Running contradiction and missing-info detectors...');
      const statusVal = this._realData ? this._realData.dre_status : 'Ready with caveats';
      const gaps = this._realData ? this._realData.evidence_gaps : [];
      renderDetectorsStage(type, statusVal, gaps);
    });

    // Stage 4: BIDDING (4000ms)
    scheduleStage(4, 4000, () => {
      this.addFeed('info', 'Bidding', 'Bidders evaluating utility impact slots...');
      const bids = this._realData ? this._realData.bids : [];
      renderBiddingStage(type, bids);
      this.renderAgentProg([], true);
    });

    // Stage 5: OPTIMIZER (4800ms)
    scheduleStage(5, 4800, () => {
      this.addFeed('info', 'Optimizer', 'Resolving multi-objective weights...');
      renderOptimizerStage(type, this._realData);
    });

    // Stage 6: EXPLAIN (5600ms)
    scheduleStage(6, 5600, () => {
      this.addFeed('info', 'Explain', 'Generating counterfactuals and rationale...');
      renderExplanationStage(type, this._realData);
    });

    // Stage 7: REVIEW (6400ms)
    const checkCompletion = () => {
      if (this._start === null) return;
      if (this._realData) {
        this._currentStageIndex = 7;
        renderHumanReviewConsole(this._realData);
        this.onComplete(this._realData);
      } else {
        setTimeout(checkCompletion, 100);
      }
    };
    setTimeout(checkCompletion, 6400);
  },

  setRealData(data) {
    this._realData = data;
  },

  prevStage() {
    if (this._currentStageIndex > 0) {
      this._currentStageIndex--;
      this.viewStage(this._currentStageIndex);
    }
  },

  nextStage() {
    if (this._currentStageIndex < 7) {
      this._currentStageIndex++;
      this.viewStage(this._currentStageIndex);
    }
  },

  updateStageNavControls() {
    const prev = el('mc-prev-stage');
    const next = el('mc-next-stage');
    const lbl = el('mc-stage-viewing-lbl');
    
    if (prev) prev.disabled = this._currentStageIndex === 0;
    if (next) next.disabled = this._currentStageIndex === 7;
    
    const STAGE_NAMES = ["Planning", "Evidence", "DRE Check", "Detectors", "Bidding", "Optimizer", "Explanation", "Review"];
    if (lbl) lbl.textContent = `Stage ${this._currentStageIndex + 1}: ${STAGE_NAMES[this._currentStageIndex]}`;
  },

  viewStage(idx) {
    const type = this._currentDecisionType || 'D1';
    const data = this._realData;
    
    const legend = el('net-legend-el');
    if (legend) {
      legend.style.display = (idx <= 1) ? 'flex' : 'none';
    }
    
    if (idx === 0) {
      renderPlanningStage(type);
    } else if (idx === 1) {
      renderEvidenceStage(type, data ? data.facts_count : 8);
    } else if (idx === 2) {
      const statusVal = data ? data.dre_status : 'Ready with caveats';
      const gaps = data ? data.evidence_gaps : [];
      renderDREStage(type, statusVal, gaps);
    } else if (idx === 3) {
      const statusVal = data ? data.dre_status : 'Ready with caveats';
      const gaps = data ? data.evidence_gaps : [];
      renderDetectorsStage(type, statusVal, gaps);
    } else if (idx === 4) {
      const bids = data ? data.bids : [];
      renderBiddingStage(type, bids);
    } else if (idx === 5) {
      renderOptimizerStage(type, data);
    } else if (idx === 6) {
      renderExplanationStage(type, data);
    } else if (idx === 7) {
      renderHumanReviewConsole(data);
    }
    
    this.updateStageNavControls();
  },

  onComplete(data) {
    if (this._timer) clearInterval(this._timer);
    this._start = null;
    const sc  = (data.recommended_actions || [])[0]?.aggregate_score || 0;
    const cnt = data.facts_count || (data.facts || []).length || 0;

    el('mc-facts').textContent  = String(cnt).padStart(2, '0');
    el('mc-agents').textContent = `${(data.bids || []).length} / 8`;
    el('mc-score').textContent  = sc.toFixed(2);
    el('mc-crumb').textContent  = `MISSION CONTROL · ${data.decision_type} · COMPLETE`;

    el('mc-chip').innerHTML = (data.status === 'blocked' || data.status === 'blocked_escalation')
      ? '<span class="chip c-red">BLOCKED</span>'
      : data.awaiting_human
        ? '<span class="chip c-amber">Ready w/ Caveats</span>'
        : '<span class="chip c-green">READY</span>';

    this.addFeed('ok',   'Bidding',  `Bidders completed · aggregate score ${sc.toFixed(3)}`);
    this.addFeed('ok',   'Pipeline', `Decision ready · status: ${data.status}`);

    renderPipelineTrack('mc-pipe-track', data);
    
    // Show stage navigation buttons upon completion
    const prev = el('mc-prev-stage');
    const next = el('mc-next-stage');
    const lbl = el('mc-stage-viewing-lbl');
    const live = el('mc-live-badge');
    if (prev) prev.style.display = 'inline-block';
    if (next) next.style.display = 'inline-block';
    if (lbl) lbl.style.display = 'inline-block';
    if (live) live.style.display = 'none';

    // Hide network legend and show human review console in display area
    const legend = el('net-legend-el');
    if (legend) legend.style.display = 'none';
    
    this._currentStageIndex = 7;
    renderHumanReviewConsole(data);
    this.updateStageNavControls();
    
    this.renderAgentProg(data.bids || [], false);
    this.renderDRE(data);

    showToast('Pipeline complete — <a href="#" onclick="App.nav(\'investigation\');return false" style="color:#fff;text-decoration:underline">View investigation →</a>', 'success');
  },

  onError(msg) {
    if (this._timer) clearInterval(this._timer);
    this._start = null;
    el('mc-chip').innerHTML = '<span class="chip c-red">ERROR</span>';
    this.addFeed('err', 'Pipeline', 'Error: ' + msg);
  },

  renderAgentProg(bids, animate = false) {
    const done = bids.length > 0;
    
    if (animate) {
      el('ag-prog-wrap').innerHTML = AGENTS.map((a, i) => {
        const bars = '░'.repeat(15);
        return `<div class="ag-prog-row" id="ag-prog-row-${i}">
          <div class="ag-prog-name">${a.lbl}</div>
          <div class="ag-prog-bars">${bars}</div>
          <div class="ag-prog-pct">--</div>
        </div>`;
      }).join('');
      
      AGENTS.forEach((a, i) => {
        setTimeout(() => {
          if (this._start === null) return;
          const row = el(`ag-prog-row-${i}`);
          if (row) {
            row.querySelector('.ag-prog-bars').innerHTML = '█'.repeat(15);
            row.querySelector('.ag-prog-pct').innerHTML = '100%';
          }
        }, i * 150);
      });
    } else {
      el('ag-prog-wrap').innerHTML = AGENTS.map((a, i) => {
        const bidder = bids.find(b => b.bidder?.toLowerCase() === a.k ||
          (a.k === 'crm' && b.bidder === 'Revenue') ||
          (a.k === 'compliance' && b.bidder === 'Compliance'));
        const pctV = done ? 100 : 0;
        const filledBars = Math.round(pctV / 7);
        const bars = '█'.repeat(filledBars) + '░'.repeat(15 - filledBars);
        return `<div class="ag-prog-row">
          <div class="ag-prog-name">${a.lbl}</div>
          <div class="ag-prog-bars">${bars}</div>
          <div class="ag-prog-pct">${done ? pctV + '%' : '--'}</div>
        </div>`;
      }).join('');
    }
  },

  renderDRE(data) {
    el('dre-iter-badge').textContent = `ITERATION ${data.dre_iterations || 1}`;
    const sc = (data.recommended_actions || [])[0]?.aggregate_score || 0;
    const lbl = (data.status === 'blocked' || data.status === 'blocked_escalation') ? 'Blocked'
      : data.awaiting_human ? 'Ready with caveats' : 'Ready';
    el('dre-status').textContent = lbl;
    el('dre-conf').textContent   = pct(sc);

    const gap = (data.evidence_gaps || [])[0];
    el('dre-gap').textContent   = gap?.fact_type || 'No gaps detected';
    el('dre-gap-d').textContent = gap
      ? `VoI score: ${(gap.voi_score || 0).toFixed(2)} · weight × (1 − confidence)`
      : '—';

    const steps = [
      { l:'Not-Ready',        n: gap ? `Missing: ${gap.fact_type}` : 'No gaps', s: gap ? 'curr' : 'done' },
      { l:'Dynamic Agent',    n: gap ? `${gap.fact_type} agent spawned` : 'No agent needed', s: 'done' },
      { l:'Re-evaluate',      n: 'Evidence merged, gap flagged', s: 'done' },
      { l:'Ready w/ caveats', n: 'Proceed; residual flagged to reviewer', s: 'active' },
    ];
    el('dre-states-el').innerHTML = steps.map(s =>
      `<div class="dre-state">
        <div class="dre-sq ${s.s}"></div>
        <div>
          <div class="dre-sl">${s.l}</div>
          ${s.n ? `<div class="dre-sn">${esc(s.n)}</div>` : ''}
        </div>
      </div>`).join('');
  },

  addFeed(type, agent, msg) {
    const b = el('feed-body');
    if (!b) return;
    // Clear placeholder on first real message
    if (b.querySelector('[style*="text-align:center"]')) b.innerHTML = '';
    const cm = { ok:'feed-msg ok', warn:'feed-msg warn', err:'feed-msg err', info:'feed-msg' };
    const t  = new Date().toLocaleTimeString('en-US', {
      hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
    const row = document.createElement('div');
    row.className = 'feed-row';
    row.innerHTML = `<span class="feed-time">${t}</span><span class="feed-agent">[${esc(agent)}]</span><span class="${cm[type] || 'feed-msg'}">${esc(msg)}</span>`;
    b.appendChild(row);
    b.scrollTop = b.scrollHeight;
  },
};
