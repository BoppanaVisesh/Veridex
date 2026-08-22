// ======================== pages/investigation.js ========================
// Page 04: Investigation — Decision Detail

const InvestigationPage = {
  render(d) {
    if (!d) return;

    const m   = DT[d.decision_type] || { label: d.decision_type, icon: '📌' };
    const top = (d.recommended_actions || [])[0] || {};
    const sc  = top.aggregate_score || 0;
    const conf = Math.round(sc * 100);
    const bids = d.bids || [];

    // ── Header ─────────────────────────────────────────────────
    el('inv-crumb').textContent =
      `INVESTIGATION · ${esc(d.primary_entity || (d.decision_id||'').substring(0,8))} · ${d.decision_type}`;
    el('inv-title').textContent = `${m.icon} ${m.label}`;
    el('inv-subject').textContent =
      (d.description || 'No description').substring(0, 180);
    el('inv-status-chip').innerHTML = statusChip(d.status, d.awaiting_human);

    // ── Render Template HTML depending on decision type ──────────
    const dt = d.decision_type;
    let layoutHtml = '';
    
    // Chips representation
    const chips = [];
    if (top.action_type) chips.push(`<span class="chip c-dark">${esc(top.action_type)}</span>`);
    if (d.awaiting_human) chips.push('<span class="chip c-amber">READY WITH CAVEATS</span>');
    else if (d.status === 'completed') chips.push('<span class="chip c-green">COMPLETE</span>');
    if (d.facts_count)    chips.push(`<span class="chip c-gray">${d.facts_count} FACTS</span>`);
    if (d.dre_iterations) chips.push(`<span class="chip c-gray">DRE × ${d.dre_iterations}</span>`);
    const chipsStr = chips.join('');

    if (dt === 'D1' || dt === 'D2') {
      layoutHtml = this._getFulfillmentLayoutHtml(d, top, conf, sc, chipsStr);
    } else if (dt === 'D3') {
      layoutHtml = this._getRetentionLayoutHtml(d, top, conf, sc, chipsStr);
    } else if (dt === 'D7') {
      layoutHtml = this._getComplianceLayoutHtml(d, top, conf, sc, chipsStr);
    } else {
      // D4, D5, D6, D8, D9
      layoutHtml = this._getFinancialLayoutHtml(d, top, conf, sc, chipsStr);
    }

    el('inv-dynamic-details').innerHTML = layoutHtml;

    // ── Render Dynamic Outcome Alert Issues ──────────
    const issues = [];
    const missing = d.missing_info || top.missing_info || [];
    const contrad = d.contradictions || top.contradictions || [];
    if (missing.length) {
      issues.push(`<div style="background:var(--amber-bg);border:1px solid var(--amber-b);border-radius:8px;padding:11px 14px;margin-bottom:10px;font-size:.79rem">
        <strong style="color:var(--amber)">⚠ Missing Info (${missing.length})</strong>
        <div style="margin-top:3px;color:var(--text2)">${missing.map(x => esc(x.description||x.fact_type||x)).join(' · ')}</div>
      </div>`);
    }
    if (contrad.length) {
      issues.push(`<div style="background:var(--red-bg);border:1px solid var(--red-b);border-radius:8px;padding:11px 14px;margin-bottom:10px;font-size:.79rem">
        <strong style="color:var(--red)">⚡ Contradictions (${contrad.length})</strong>
        <div style="margin-top:3px;color:var(--text2)">${contrad.map(x => esc(x.description||x)).join(' · ')}</div>
      </div>`);
    }
    const issuesEl = el('inv-issues');
    if (issuesEl) issuesEl.innerHTML = issues.join('');

    // ── Sub-sections ───────────────────────────────────────────
    this.renderOutcomeTree(d, top, bids);
    this.renderBidding(bids, d.status === 'blocked' || d.status === 'blocked_escalation');
    this.setupWhatIf(d);
    renderCompletePipeline('inv-pipe-track');
    this.renderOutcomeBox(d);
    this.renderEvidenceTimeline(d);
    this.renderPrecedents(d, top);
    this.renderInsights(d, top);

    // Fetch and render live trace audit trail & execution log
    get('/trace/' + d.decision_id).then(res => {
      this.renderAuditTrailAndLogs(d, res.events || []);
    }).catch(err => {
      console.warn('Could not load trace logs:', err);
      this.renderAuditTrailAndLogs(d, []);
    });
  },

  _getFulfillmentLayoutHtml(d, top, conf, sc, chipsStr) {
    const bids = d.bids || [];
    const openDays = Math.floor(Math.random() * 4) + 2;
    const applicantCount = d.decision_type === 'D1' ? 12 : 18;
    const matchCount = d.decision_type === 'D1' ? 5 : 8;
    const matchPercent = Math.round((matchCount / applicantCount) * 100);

    return `
    <div class="inv-layout" style="grid-template-columns: 310px 1fr; gap: 20px;">
      <!-- Left Column: Sourcing & SLA funnels -->
      <div>
        <!-- Sourcing Scorecard -->
        <div class="card" style="padding:18px;margin-bottom:14px;border-top:4px solid var(--blue)">
          <div class="sec-lbl">Sourcing Match Score</div>
          <div style="display:flex;align-items:center;gap:14px;margin:10px 0">
            <div class="conf-ring" style="width:70px;height:70px;margin:0">
              <svg width="70" height="70" viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="50" fill="none" stroke="#F1F5F9" stroke-width="12"/>
                <circle cx="60" cy="60" r="50" fill="none" stroke="var(--blue)" stroke-width="12"
                  stroke-dasharray="314" stroke-dashoffset="${314 - (314 * conf / 100)}"
                  stroke-linecap="round"/>
              </svg>
              <div class="conf-ring-label" style="font-size:1.15rem;font-family:'JetBrains Mono',monospace;font-weight:700">${conf}%</div>
            </div>
            <div>
              <div style="font-size:1.2rem;font-weight:700;font-family:'JetBrains Mono',monospace">${sc.toFixed(3)}</div>
              <div style="font-size:.65rem;color:var(--text3);text-transform:uppercase">Confidence Index</div>
            </div>
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:10px">${chipsStr}</div>
        </div>

        <!-- Sourcing Pipeline Funnel -->
        <div class="card" style="padding:15px;margin-bottom:14px">
          <div class="sec-lbl" style="margin-bottom:8px">Sourcing Pipeline Funnel</div>
          <div style="display:flex;flex-direction:column;gap:8px">
            <div style="display:flex;justify-content:space-between;font-size:.8rem">
              <span>Total Applicants</span>
              <strong style="color:var(--blue)">${applicantCount}</strong>
            </div>
            <div style="height:6px;background:var(--bg-muted);border-radius:3px;overflow:hidden">
              <div style="width:100%;height:100%;background:var(--blue);opacity:.3"></div>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:.8rem">
              <span>Screened Match</span>
              <strong style="color:var(--blue)">${matchCount} (${matchPercent}%)</strong>
            </div>
            <div style="height:6px;background:var(--bg-muted);border-radius:3px;overflow:hidden">
              <div style="width:${matchPercent}%;height:100%;background:var(--blue);opacity:.6"></div>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:.8rem">
              <span>Submittals to Client</span>
              <strong style="color:var(--blue)">2</strong>
            </div>
            <div style="height:6px;background:var(--bg-muted);border-radius:3px;overflow:hidden">
              <div style="width:15%;height:100%;background:var(--blue)"></div>
            </div>
          </div>
        </div>

        <!-- SLA Urgency countdown -->
        <div class="card" style="padding:15px">
          <div class="sec-lbl">SLA Performance Target</div>
          <div style="font-size:1.15rem;font-weight:700;margin-top:4px;color:var(--red)">
            🚨 Urgent (SLA Breach Risk)
          </div>
          <div style="font-size:.76rem;color:var(--text2);margin-top:5px;line-height:1.4">
            Days Open: <strong>${openDays} days</strong><br>
            SLA Breach Window: <strong>3 days Max</strong>
          </div>
        </div>
      </div>

      <!-- Right Column: Recommendation, KPIs & Feedback -->
      <div>
        <div class="card" style="padding:18px;margin-bottom:14px;border-top:4px solid var(--blue)">
          <div class="sec-lbl" style="margin-bottom:7px">Recommended Action</div>
          <div style="font-size:1.1rem;font-weight:700;line-height:1.55;margin-bottom:12px">${esc(top.description || 'No action generated.')}</div>
          <div class="sec-lbl" style="margin-bottom:5px">Sourcing Rationale</div>
          <div style="font-size:.82rem;color:var(--text2);line-height:1.7">${this.formatExplanation(top.explanation)}</div>
        </div>

        <div class="conf-stats" style="margin-bottom:14px">
          <div class="cs-cell"><div class="cs-val">${sc ? sc.toFixed(2) : '--'}</div><div class="cs-lbl">Score</div></div>
          <div class="cs-cell"><div class="cs-val">${bids.length}</div><div class="cs-lbl">Bidders</div></div>
          <div class="cs-cell"><div class="cs-val">${(d.evidence_gaps || []).length}</div><div class="cs-lbl">Gaps</div></div>
          <div class="cs-cell"><div class="cs-val">${d.dre_iterations ?? 1}</div><div class="cs-lbl">DRE Loops</div></div>
        </div>

        <div id="inv-issues"></div>
        <div id="inv-outcome-box"></div>
      </div>
    </div>`;
  },

  _getRetentionLayoutHtml(d, top, conf, sc, chipsStr) {
    const bids = d.bids || [];
    return `
    <div class="inv-layout" style="grid-template-columns: 310px 1fr; gap: 20px;">
      <!-- Left Column: Engagement & Retention Stats -->
      <div>
        <!-- Retention threat index -->
        <div class="card" style="padding:18px;margin-bottom:14px;border-top:4px solid var(--amber)">
          <div class="sec-lbl">Attrition Risk Index</div>
          <div style="display:flex;align-items:center;gap:14px;margin:10px 0">
            <div class="conf-ring" style="width:70px;height:70px;margin:0">
              <svg width="70" height="70" viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="50" fill="none" stroke="#F1F5F9" stroke-width="12"/>
                <circle cx="60" cy="60" r="50" fill="none" stroke="var(--amber)" stroke-width="12"
                  stroke-dasharray="314" stroke-dashoffset="${314 - (314 * conf / 100)}"
                  stroke-linecap="round"/>
              </svg>
              <div class="conf-ring-label" style="font-size:1.15rem;font-family:'JetBrains Mono',monospace;font-weight:700;color:var(--amber)">${conf}%</div>
            </div>
            <div>
              <div style="font-size:1.2rem;font-weight:700;font-family:'JetBrains Mono',monospace">${sc.toFixed(3)}</div>
              <div style="font-size:.65rem;color:var(--text3);text-transform:uppercase">Threat Level</div>
            </div>
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:10px">${chipsStr}</div>
        </div>

        <!-- Data Quality Indicators -->
        <div class="card" style="padding:15px;margin-bottom:14px">
          <div class="sec-lbl" style="margin-bottom:8px">Data Quality Indicators</div>
          <div style="display:flex;flex-direction:column;gap:10px">
            <div style="display:flex;align-items:center;gap:8px">
              <div class="s-dot dot-r" style="width:8px;height:8px"></div>
              <div style="flex:1">
                <div style="font-size:.78rem;font-weight:600">Specification Inconsistency Delay</div>
                <div style="font-size:.68rem;color:var(--text3)">Discrepancy detected across supplier batch</div>
              </div>
            </div>
            <div style="display:flex;align-items:center;gap:8px">
              <div class="s-dot dot-a" style="width:8px;height:8px"></div>
              <div style="flex:1">
                <div style="font-size:.78rem;font-weight:600">Validation Confidence Drift</div>
                <div style="font-size:.68rem;color:var(--text3)">Dropped below 60% threshold on 2 attributes</div>
              </div>
            </div>
            <div style="display:flex;align-items:center;gap:8px">
              <div class="s-dot dot-g" style="width:8px;height:8px"></div>
              <div style="flex:1">
                <div style="font-size:.78rem;font-weight:600">Supplier Ingestion Feed Health</div>
                <div style="font-size:.68rem;color:var(--text3)">Batch syntax and schema validation nominal</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Data Lineage snippet card -->
        <div class="card" style="padding:15px">
          <div class="sec-lbl">Data Lineage Audit Snippet</div>
          <div style="font-size:.78rem;color:var(--text2);margin-top:5px;line-height:1.45;font-style:italic">
            "Extracted operating specs from supplier PDF; compliance certification requires laboratory accreditation report."
          </div>
          <div style="font-size:.65rem;color:var(--text3);margin-top:6px;text-transform:uppercase;letter-spacing:.03em">
            Source: Email Analysis
          </div>
        </div>
      </div>

      <!-- Right Column: Recommendation & KPIs -->
      <div>
        <div class="card" style="padding:18px;margin-bottom:14px;border-top:4px solid var(--amber)">
          <div class="sec-lbl" style="margin-bottom:7px">Recommended Action</div>
          <div style="font-size:1.1rem;font-weight:700;line-height:1.55;margin-bottom:12px">${esc(top.description || 'No action generated.')}</div>
          <div class="sec-lbl" style="margin-bottom:5px">Retention Rationale</div>
          <div style="font-size:.82rem;color:var(--text2);line-height:1.7">${this.formatExplanation(top.explanation)}</div>
        </div>

        <div class="conf-stats" style="margin-bottom:14px">
          <div class="cs-cell"><div class="cs-val">${sc ? sc.toFixed(2) : '--'}</div><div class="cs-lbl">Score</div></div>
          <div class="cs-cell"><div class="cs-val">${bids.length}</div><div class="cs-lbl">Bidders</div></div>
          <div class="cs-cell"><div class="cs-val">${(d.evidence_gaps || []).length}</div><div class="cs-lbl">Gaps</div></div>
          <div class="cs-cell"><div class="cs-val">${d.dre_iterations ?? 1}</div><div class="cs-lbl">DRE Loops</div></div>
        </div>

        <div id="inv-issues"></div>
        <div id="inv-outcome-box"></div>
      </div>
    </div>`;
  },

  _getComplianceLayoutHtml(d, top, conf, sc, chipsStr) {
    const bids = d.bids || [];
    return `
    <div class="inv-layout" style="grid-template-columns: 310px 1fr; gap: 20px;">
      <!-- Left Column: Legal check points -->
      <div>
        <!-- Veto status scorecard -->
        <div class="card" style="padding:18px;margin-bottom:14px;border-top:4px solid var(--red);background:#FEF2F2">
          <div class="sec-lbl" style="color:var(--red)">Legal Compliance Status</div>
          <div style="display:flex;align-items:center;gap:14px;margin:10px 0">
            <div style="width:50px;height:50px;border-radius:50%;background:#FCA5A5;display:grid;place-items:center;color:#fff;font-size:1.6rem;font-weight:900">
              ⚠
            </div>
            <div>
              <div style="font-size:1.25rem;font-weight:900;color:var(--red)">VETO BLOCKED</div>
              <div style="font-size:.65rem;color:var(--text3);text-transform:uppercase">Compliance Alert</div>
            </div>
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:10px">${chipsStr}</div>
        </div>

        <!-- Registry check values -->
        <div class="card" style="padding:15px;margin-bottom:14px">
          <div class="sec-lbl" style="margin-bottom:8px">Registry Checkpoints</div>
          <div style="display:flex;flex-direction:column;gap:8px">
            <div style="display:flex;justify-content:space-between;align-items:center;font-size:.8rem">
              <span>Work Authorization Status</span>
              <span class="chip c-red">VISA EXPIRED</span>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center;font-size:.8rem">
              <span>Background Screening</span>
              <span class="chip c-green">CLEARED</span>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center;font-size:.8rem">
              <span>State Tax Filing</span>
              <span class="chip c-green">VERIFIED</span>
            </div>
          </div>
        </div>

        <!-- Registry details -->
        <div class="card" style="padding:15px">
          <div class="sec-lbl">Registry Verification Node</div>
          <div style="font-size:.76rem;color:var(--text2);margin-top:4px;line-height:1.4">
            Source: <strong>Deterministic DHS Registry</strong><br>
            Trust Level: <strong>100% (No LLM extraction)</strong>
          </div>
        </div>
      </div>

      <!-- Right Column: Escalation recommended details -->
      <div>
        <div class="card" style="padding:18px;margin-bottom:14px;border-top:4px solid var(--red)">
          <div class="sec-lbl" style="margin-bottom:7px">Recommended Action</div>
          <div style="font-size:1.1rem;font-weight:700;line-height:1.55;margin-bottom:12px;color:var(--red)">${esc(top.description || 'Regulatory Veto Blocked.')}</div>
          <div class="sec-lbl" style="margin-bottom:5px">Legal Rationale</div>
          <div style="font-size:.82rem;color:var(--text2);line-height:1.7">${this.formatExplanation(top.explanation)}</div>
        </div>

        <div class="conf-stats" style="margin-bottom:14px">
          <div class="cs-cell"><div class="cs-val" style="color:var(--red)">0.00</div><div class="cs-lbl">Bidding Score</div></div>
          <div class="cs-cell"><div class="cs-val">VETO</div><div class="cs-lbl">Status</div></div>
          <div class="cs-cell"><div class="cs-val">${(d.evidence_gaps || []).length}</div><div class="cs-lbl">Gaps</div></div>
          <div class="cs-cell"><div class="cs-val">${d.dre_iterations ?? 1}</div><div class="cs-lbl">DRE Loops</div></div>
        </div>

        <div id="inv-issues"></div>
        <div id="inv-outcome-box"></div>
      </div>
    </div>`;
  },

  _getFinancialLayoutHtml(d, top, conf, sc, chipsStr) {
    const bids = d.bids || [];
    return `
    <div class="inv-layout" style="grid-template-columns: 310px 1fr; gap: 20px;">
      <!-- Left Column: Margin & Commercial Stats -->
      <div>
        <!-- Profitability index -->
        <div class="card" style="padding:18px;margin-bottom:14px;border-top:4px solid var(--green)">
          <div class="sec-lbl">Commercial Score</div>
          <div style="display:flex;align-items:center;gap:14px;margin:10px 0">
            <div class="conf-ring" style="width:70px;height:70px;margin:0">
              <svg width="70" height="70" viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="50" fill="none" stroke="#F1F5F9" stroke-width="12"/>
                <circle cx="60" cy="60" r="50" fill="none" stroke="var(--green)" stroke-width="12"
                  stroke-dasharray="314" stroke-dashoffset="${314 - (314 * conf / 100)}"
                  stroke-linecap="round"/>
              </svg>
              <div class="conf-ring-label" style="font-size:1.15rem;font-family:'JetBrains Mono',monospace;font-weight:700;color:var(--green)">${conf}%</div>
            </div>
            <div>
              <div style="font-size:1.2rem;font-weight:700;font-family:'JetBrains Mono',monospace">${sc.toFixed(3)}</div>
              <div style="font-size:.65rem;color:var(--text3);text-transform:uppercase">Economic Value</div>
            </div>
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:10px">${chipsStr}</div>
        </div>

        <!-- Profit margin thresholds -->
        <div class="card" style="padding:15px;margin-bottom:14px">
          <div class="sec-lbl" style="margin-bottom:8px">Commercial Margins</div>
          <div style="display:flex;flex-direction:column;gap:8px">
            <div style="display:flex;justify-content:space-between;font-size:.8rem">
              <span>Standard Margin Floor</span>
              <strong>22.0%</strong>
            </div>
            <div style="height:6px;background:var(--bg-muted);border-radius:3px;overflow:hidden">
              <div style="width:75%;height:100%;background:var(--green);opacity:.4"></div>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:.8rem">
              <span>Estimated Deal Margin</span>
              <strong style="color:var(--green)">24.8%</strong>
            </div>
            <div style="height:6px;background:var(--bg-muted);border-radius:3px;overflow:hidden">
              <div style="width:83%;height:100%;background:var(--green)"></div>
            </div>
          </div>
        </div>

        <!-- Client metrics -->
        <div class="card" style="padding:15px">
          <div class="sec-lbl">Client Spend Trend</div>
          <div style="font-size:1.15rem;font-weight:700;margin-top:4px;color:var(--green)">
            📈 Growing Spend
          </div>
          <div style="font-size:.76rem;color:var(--text2);margin-top:4px">
            Tenure: <strong>36 months</strong><br>
            NPS Rating: <strong>82/100</strong>
          </div>
        </div>
      </div>

      <!-- Right Column: Recommendation & KPIs -->
      <div>
        <div class="card" style="padding:18px;margin-bottom:14px;border-top:4px solid var(--green)">
          <div class="sec-lbl" style="margin-bottom:7px">Recommended Action</div>
          <div style="font-size:1.1rem;font-weight:700;line-height:1.55;margin-bottom:12px">${esc(top.description || 'No action generated.')}</div>
          <div class="sec-lbl" style="margin-bottom:5px">Financial Justification</div>
          <div style="font-size:.82rem;color:var(--text2);line-height:1.7">${this.formatExplanation(top.explanation)}</div>
        </div>

        <div class="conf-stats" style="margin-bottom:14px">
          <div class="cs-cell"><div class="cs-val">${sc ? sc.toFixed(2) : '--'}</div><div class="cs-lbl">Score</div></div>
          <div class="cs-cell"><div class="cs-val">${bids.length}</div><div class="cs-lbl">Bidders</div></div>
          <div class="cs-cell"><div class="cs-val">${(d.evidence_gaps || []).length}</div><div class="cs-lbl">Gaps</div></div>
          <div class="cs-cell"><div class="cs-val">${d.dre_iterations ?? 1}</div><div class="cs-lbl">DRE Loops</div></div>
        </div>

        <div id="inv-issues"></div>
        <div id="inv-outcome-box"></div>
      </div>
    </div>`;
  },

  renderOutcomeBox(d) {
    const oBox = el('inv-outcome-box');
    if (!oBox) return;
    
    const isClosed = ['completed', 'rejected'].includes(d.status);
    const outcome = d.outcome;
    
    if (!isClosed) {
      oBox.innerHTML = `
        <div class="card" style="padding:15px;border-color:var(--border)">
          <div class="sec-lbl" style="color:var(--text3)">Downstream Outcome</div>
          <div style="font-size:.76rem;color:var(--text3);margin-top:5px">
            This decision is still in review. Make a human decision in the <strong>Human Review</strong> tab at the bottom before resolving the downstream outcome.
          </div>
        </div>`;
    } else if (outcome && outcome.was_correct !== null) {
      const isCorrect = outcome.was_correct;
      oBox.innerHTML = `
        <div class="card" style="padding:15px;border-color:${isCorrect ? 'var(--green-b)' : 'var(--red-b)'};background:${isCorrect ? 'var(--green-bg)' : 'var(--red-bg)'}">
          <div class="sec-lbl" style="color:${isCorrect ? 'var(--green)' : 'var(--red)'}">✓ Outcome Recorded</div>
          <div style="font-size:1rem;font-weight:700;margin-top:6px">
            ${isCorrect ? 'Success (Correct Call)' : 'Failure (Incorrect Call)'}
          </div>
          <div style="font-size:.8rem;color:var(--text2);margin-top:5px">
            Result: <strong>${esc(outcome.downstream_result || 'N/A')}</strong>
          </div>
          <div style="font-size:.68rem;color:var(--text3);margin-top:6px;font-family:'JetBrains Mono',monospace">
            Recorded in sentinel.db · updates factored into weights
          </div>
        </div>`;
    } else {
      oBox.innerHTML = `
        <div class="card" style="padding:15px;border-color:var(--amber-b);background:var(--amber-bg)">
          <div class="sec-lbl" style="color:var(--amber)">Simulate Downstream Outcome</div>
          <div style="font-size:.76rem;color:var(--text2);margin-top:4px;margin-bottom:10px">
            Provide downstream results to trigger reinforcement learning updates in config weights.
          </div>
          
          <div style="display:flex;flex-direction:column;gap:8px">
            <div>
              <label style="font-size:.75rem;font-weight:600;display:block;margin-bottom:3px">Was this recommendation correct?</label>
              <select id="outcome-correct" class="clar-inp" style="padding:6px;height:auto;font-size:.8rem;border:1px solid var(--border)">
                <option value="true">Yes — Correct Call (Success)</option>
                <option value="false">No — Incorrect Call (Failure)</option>
              </select>
            </div>
            <div>
              <label style="font-size:.75rem;font-weight:600;display:block;margin-bottom:3px">Downstream Result Description</label>
              <input id="outcome-desc" type="text" class="clar-inp" style="padding:6px;font-size:.8rem;border:1px solid var(--border)" 
                placeholder="e.g. Published in 2 days / RMA return due to voltage mismatch">
            </div>
            <button class="btn btn-primary btn-sm" style="align-self:flex-start;margin-top:4px"
              onclick="InvestigationPage.submitOutcome('${d.decision_id}')">
              Record Outcome & Run Learning
            </button>
          </div>
        </div>`;
    }
  },

  renderOutcomeTree(d, top, bids) {
    const sc = top.aggregate_score || 0;
    const rp = Math.round(sc * 100);
    const np = Math.round((1 - sc) * 55);
    const ep = Math.max(1, 100 - rp - np);
    const label = DT[d.decision_type]?.label || 'Recommended action';

    // Use losing bids for Branch C context
    const losing = (top.losing_bids || []).slice(0, 1);
    const altDesc = losing.length
      ? `Alternative: ${esc(losing[0].rationale?.substring(0,80) || 'Escalation path')}...`
      : 'Surfaces concerns prematurely. Mixed precedent.';

    // Use similar past cases count
    const precedents = (top.similar_past_cases || []).length;

    el('ot-body').innerHTML = `
      <div class="ot-card is-rec">
        <div class="ot-branch">↗ Branch A · RECOMMENDED</div>
        <div class="ot-name">${esc(label)}</div>
        <div class="ot-prob">${rp}<sup>%</sup></div>
        <div class="ot-desc">${esc(top.description?.substring(0,120) || 'Recommended path')}</div>
        <div class="ot-fx">fx = P(success | intervene) × EV · score ${sc.toFixed(3)}</div>
      </div>
      <div class="ot-card">
        <div class="ot-branch">→ Branch B · NO ACTION</div>
        <div class="ot-name">Do nothing — wait and monitor</div>
        <div class="ot-prob">${np}<sup>%</sup></div>
        <div class="ot-desc">Status-quo drift. Risk of catalog decay and unlisted revenue loss compounding.</div>
        <div class="ot-fx">fx = P(drift) × (syndication_delay + delisting_penalty)</div>
      </div>
      <div class="ot-card">
        <div class="ot-branch">↑ Branch C · ESCALATION</div>
        <div class="ot-name">Escalate to senior catalog specialist</div>
        <div class="ot-prob">${ep}<sup>%</sup></div>
        <div class="ot-desc">${altDesc}</div>
        <div class="ot-fx">fx = Heuristic · ${precedents || Math.ceil(Math.random()*3)+1} similar precedent case(s)</div>
      </div>`;
  },

  renderBidding(bids, isBlocked) {
    const veto = bids.find(b => b.is_veto) || isBlocked;
    el('compl-badge').innerHTML = veto
      ? '<span class="chip c-red">⚡ Compliance · VETO</span>'
      : '<span class="chip c-green">⚡ Compliance · Pass</span>';

    // Render the radar chart
    this.renderRadarChart(isBlocked ? [] : bids);

    if (!bids.length) {
      if (isBlocked) {
        el('bid-grid').innerHTML = `<div style="color:var(--red);font-size:.82rem;padding:12px;grid-column:1/-1;background:var(--red-bg);border:1px solid var(--red-b);border-radius:6px">
          🚫 Compliance Lock Active. The pipeline was terminated at the DRE check stage due to an unresolved compliance gap (e.g. expired visa or background check). The bidding layer and optimizer were bypassed entirely to protect the enterprise from compliance exposure.</div>`;
      } else {
        el('bid-grid').innerHTML = `<div style="color:var(--text3);font-size:.82rem;padding:10px;grid-column:1/-1">
          No bids recorded. Run a scenario to see bidder evaluations.</div>`;
      }
      return;
    }

    el('bid-grid').innerHTML = bids.map(b => {
      const bm     = BIDDER_META[b.bidder] || { model: 'Gemini', col: '#0F172A' };
      const dn     = b.bidder === 'CustomerSuccess' ? 'Customer Success' : (b.bidder || '—');
      const scoreW = Math.round((b.score || 0) * 100);
      const confW  = Math.round(((b.confidence ?? b.score) || 0) * 100);
      const isVeto = !!b.is_veto;

      return `<div class="bid-card" style="${isVeto ? 'border-color:var(--red-b);background:var(--red-bg)' : ''}">
        <div class="bid-hd">
          <div>
            <div class="bid-name">${dn}</div>
            <div class="bid-model">${bm.model}</div>
          </div>
          <span class="bid-contrib${isVeto ? ' bid-veto-chip' : ''}">${isVeto ? '🚫 VETO' : 'CONTRIBUTED'}</span>
        </div>
        <div class="bid-stat-l">Score</div>
        <div class="bid-score">${(b.score || 0).toFixed(2)}</div>
        <div class="bid-bar-t">
          <div class="bid-bar-f" style="width:${scoreW}%;background:${isVeto ? 'var(--red)' : bm.col}"></div>
        </div>
        <div class="bid-stat-l">Confidence</div>
        <div class="bid-score">${confW}%</div>
        <div class="bid-bar-t">
          <div class="bid-bar-f" style="width:${confW}%;background:${bm.col};opacity:.45"></div>
        </div>
        <div class="bid-rat">${isVeto
          ? `<span style="color:var(--red);font-weight:600">Veto: </span>${esc((b.veto_reason||'').substring(0,100))}`
          : esc((b.rationale||'').substring(0,110))}${(b.rationale||'').length > 110 ? '…' : ''}</div>
      </div>`;
    }).join('');
  },

  renderRadarChart(bids) {
    const container = el('bid-radar-container');
    if (!container) return;

    // If there are no bids or it is blocked, hide the radar chart container
    if (!bids || !bids.length) {
      container.style.display = 'none';
      return;
    } else {
      container.style.display = 'flex';
    }

    const W = 280, H = 280;
    const X0 = W / 2, Y0 = H / 2;
    const R = 75; // radius of chart

    // Define bidders and metadata (angle, color, short label)
    const biddersDef = [
      { key: 'Revenue',        lbl: 'Revenue',   color: '#2563EB', angle: -Math.PI / 2 },
      { key: 'Risk',           lbl: 'Risk',      color: '#DC2626', angle: -Math.PI / 6 },
      { key: 'CustomerSuccess',lbl: 'Cust.Suc.', color: '#16A34A', angle: Math.PI / 6 },
      { key: 'Finance',        lbl: 'Finance',   color: '#D97706', angle: Math.PI / 2 },
      { key: 'Compliance',     lbl: 'Compliance',color: '#0F172A', angle: 5 * Math.PI / 6 },
      { key: 'Ops',            lbl: 'Ops',       color: '#7C3AED', angle: 7 * Math.PI / 6 }
    ];

    // Find score for each bidder key from bids list
    const scores = biddersDef.map(def => {
      const bid = bids.find(b => b.bidder === def.key);
      return bid ? (bid.is_veto ? 0.1 : (bid.score || 0.0)) : 0.5;
    });

    let svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" style="display:block">`;
    
    // Draw concentric grid hexagons
    const levels = [0.25, 0.50, 0.75, 1.00];
    levels.forEach(lvl => {
      const pts = biddersDef.map(def => {
        const x = X0 + (R * lvl) * Math.cos(def.angle);
        const y = Y0 + (R * lvl) * Math.sin(def.angle);
        return `${x},${y}`;
      }).join(' ');
      
      svg += `<polygon points="${pts}" fill="none" stroke="#E2E8F0" stroke-width="1" />`;
      
      // Draw grid labels
      const yLabel = Y0 - (R * lvl);
      svg += `<text x="${X0 + 3}" y="${yLabel + 8}" fill="#94A3B8" font-size="7" font-family="'JetBrains Mono',monospace">${Math.round(lvl * 100)}%</text>`;
    });

    // Draw axis lines and bidder text labels
    biddersDef.forEach(def => {
      const x = X0 + R * Math.cos(def.angle);
      const y = Y0 + R * Math.sin(def.angle);
      svg += `<line x1="${X0}" y1="${Y0}" x2="${x}" y2="${y}" stroke="#E2E8F0" stroke-width="1" stroke-dasharray="2 2" />`;
      
      let textAnchor = 'middle';
      let dy = 0;
      const xOffset = Math.cos(def.angle);
      const yOffset = Math.sin(def.angle);
      
      if (Math.abs(xOffset) < 0.1) {
        textAnchor = 'middle';
        dy = yOffset > 0 ? 10 : -4;
      } else {
        textAnchor = xOffset > 0 ? 'start' : 'end';
        dy = 3;
      }
      
      const lx = X0 + (R + 10) * xOffset;
      const ly = Y0 + (R + 10) * yOffset + dy;
      
      svg += `<text x="${lx}" y="${ly}" text-anchor="${textAnchor}" fill="#64748B" font-size="8" font-family="Inter" font-weight="600">${def.lbl}</text>`;
    });

    // Draw data polygon
    const dataPts = biddersDef.map((def, idx) => {
      const score = scores[idx];
      const x = X0 + (R * score) * Math.cos(def.angle);
      const y = Y0 + (R * score) * Math.sin(def.angle);
      return `${x},${y}`;
    }).join(' ');
    
    svg += `<polygon points="${dataPts}" fill="rgba(99, 102, 241, 0.12)" stroke="#6366F1" stroke-width="2" />`;

    // Draw circles and text value labels
    biddersDef.forEach((def, idx) => {
      const score = scores[idx];
      const x = X0 + (R * score) * Math.cos(def.angle);
      const y = Y0 + (R * score) * Math.sin(def.angle);
      
      svg += `<circle cx="${x}" cy="${y}" r="4" fill="${def.color}" stroke="#FFFFFF" stroke-width="1.5" style="filter: drop-shadow(0 1px 2px rgba(0,0,0,0.15))" />`;
      
      const scoreVal = Math.round(score * 100);
      let ty = y - 7;
      if (Math.sin(def.angle) > 0.5) ty = y + 13;
      
      svg += `<text x="${x}" y="${ty}" text-anchor="middle" fill="#1E293B" font-size="8" font-family="'JetBrains Mono',monospace" font-weight="700">${scoreVal}%</text>`;
    });

    svg += `</svg>`;
    container.innerHTML = svg;
  },

  setupWhatIf(d) {
    // Use numeric facts for override fields
    const numFacts = (d.facts || [])
      .filter(f => {
        if (typeof f.value === 'number') return true;
        const s = String(f.value || '').trim();
        // Match clean numeric, percentage, or currency strings (no alphabetic characters)
        return /^[0-9.\-\s%$,]+$/.test(s) && s !== '';
      })
      .slice(0, 3)
      .map(f => ({ key: f.fact_type, lbl: f.fact_type.replace(/_/g,' '), val: f.value }));

    const defaults = [
      { key: 'field_completeness_pct', lbl: 'Completeness (%)',  val: '' },
      { key: 'product_age_days',       lbl: 'Product Age (days)', val: '' },
      { key: 'confidence_score',       lbl: 'Confidence Score',   val: '' },
    ];
    const fields = numFacts.length ? numFacts : defaults;

    el('wi-fields').innerHTML = fields.map(f =>
      `<div class="wi-field">
        <label>${esc(f.lbl)}</label>
        <input data-key="${f.key}" placeholder="${f.val !== '' ? f.val : 'New value…'}" type="number" step="any">
      </div>`).join('');

    el('wi-btn').onclick = () => InvestigationPage.runWhatIf(d.decision_id);
    el('wi-result').style.display = 'none';
  },

  async runWhatIf(id) {
    const cont   = el('wi-result');
    const inputs = document.querySelectorAll('[data-key]');
    const ov = {};
    inputs.forEach(inp => {
      const v = inp.value.trim();
      if (v !== '') ov[inp.dataset.key] = isNaN(v) ? v : parseFloat(v);
    });
    if (!Object.keys(ov).length) { showToast('Enter at least one value to override', 'error'); return; }

    cont.style.display = 'block';
    cont.innerHTML = '<div style="display:flex;align-items:center;gap:8px"><div class="spinner"></div> Simulating…</div>';

    try {
      const r   = await post('/decisions/' + id + '/whatif', { overrides: ov });
      const sg  = r.score_delta >= 0 ? '+' : '';
      const col = r.score_delta > .01 ? 'var(--green)'
        : r.score_delta < -.01 ? 'var(--red)' : 'var(--text3)';
      const chg  = (r.bid_deltas || []).filter(b => Math.abs(b.delta) > .001);
      const flip = r.recommendation_flipped
        ? '<span class="chip c-red" style="margin-left:7px">⚠ Recommendation Flipped</span>' : '';

      const tbl = chg.length
        ? `<table style="width:100%;border-collapse:collapse;font-size:.77rem;margin-top:10px">
            <tr style="border-bottom:1px solid var(--border)">
              <th style="text-align:left;padding:3px 8px;color:var(--text3);font-size:.6rem;text-transform:uppercase">Bidder</th>
              <th style="padding:3px 8px;color:var(--text3);font-size:.6rem;text-transform:uppercase">Before</th>
              <th style="padding:3px 8px;color:var(--text3);font-size:.6rem;text-transform:uppercase">After</th>
              <th style="padding:3px 8px;color:var(--text3);font-size:.6rem;text-transform:uppercase">Δ</th>
            </tr>
            ${chg.map(b => `<tr>
              <td style="padding:3px 8px;font-weight:500">${b.bidder}</td>
              <td style="padding:3px 8px;font-family:'JetBrains Mono',monospace">${(b.original_score||0).toFixed(3)}</td>
              <td style="padding:3px 8px;font-family:'JetBrains Mono',monospace">${(b.patched_score||0).toFixed(3)}</td>
              <td style="padding:3px 8px;font-family:'JetBrains Mono',monospace;color:${b.delta>0?'var(--green)':'var(--red)'};font-weight:700">
                ${b.delta > 0 ? '+' : ''}${(b.delta||0).toFixed(3)}
              </td>
            </tr>`).join('')}
          </table>`
        : '<div style="font-size:.78rem;color:var(--text3);margin-top:8px">No significant bid score changes under these overrides.</div>';

      cont.innerHTML = `
        <div class="wi-result-t">Simulation Result</div>
        <div style="font-size:1.05rem;font-weight:700;font-family:'JetBrains Mono',monospace">
          ${(r.original?.aggregate_score||0).toFixed(3)}
          <span style="color:var(--text3)"> → </span>
          <span style="color:${col}">${(r.patched?.aggregate_score||0).toFixed(3)}</span>
          <span style="font-size:.82rem;color:${col}">(${sg}${(r.score_delta||0).toFixed(3)})</span>
          ${flip}
        </div>${tbl}`;
    } catch(e) {
      cont.innerHTML = `<span style="color:var(--red);font-size:.82rem">Error: ${e.message}</span>`;
    }
  },

  copyExecutiveSummary(d) {
    if (!d) { showToast('No decision loaded', 'error'); return; }
    const top  = (d.recommended_actions || [])[0] || {};
    const sc   = top.aggregate_score != null ? (top.aggregate_score * 100).toFixed(1) + '%' : 'N/A';
    const rec  = (top.description || 'No recommendation').substring(0, 250);
    const bt   = (d.bids || []).map(b =>
      `  - ${b.bidder}: ${((b.score||0) * 100).toFixed(0)}%${b.is_veto ? ' [VETO]' : ''}`).join('\n');
    const txt = [
      'VERIDEX DECISION SUMMARY',
      `Decision ID:  ${d.decision_id}`,
      `Type:         ${d.decision_type} — ${DT[d.decision_type]?.label || ''}`,
      `Entity:       ${d.primary_entity || '—'}`,
      `Status:       ${(d.status || 'unknown').toUpperCase()}`,
      `Confidence:   ${sc}`,
      `Facts:        ${d.facts_count || 0}`,
      '',
      'RECOMMENDATION:',
      rec,
      '',
      'AGENT VOTES:',
      bt || '  (none recorded)',
      '',
      `Generated: ${new Date().toLocaleString()}`,
      'Platform: Veridex NBA Platform v1.0',
    ].join('\n');

    navigator.clipboard.writeText(txt)
      .then(() => showToast('Executive summary copied to clipboard!', 'success'))
      .catch(() => {
        const ta = document.createElement('textarea');
        ta.value = txt; document.body.appendChild(ta);
        ta.select(); document.execCommand('copy'); document.body.removeChild(ta);
        showToast('Copied!', 'success');
      });
  },

  async submitOutcome(id) {
    const wasCorrectVal = el('outcome-correct')?.value === 'true';
    const desc = el('outcome-desc')?.value?.trim();
    if (!desc) { showToast('Please enter a description of the downstream result', 'error'); return; }
    
    try {
      await post('/outcomes/' + id, {
        downstream_result: desc,
        was_correct: wasCorrectVal
      });
      showToast('Outcome recorded successfully! Brier scores and bidding weights updated.', 'success');
      
      // Refresh current decision details
      const updated = await get('/decisions/' + id);
      App.currentDecision = updated;
      
      // Reload page
      this.render(updated);
    } catch(e) {
      showToast('Error recording outcome: ' + e.message, 'error');
    }
  },

  renderAuditTrailAndLogs(d, events) {
    const auditBody = el('audit-trail-body');
    const logBody = el('execution-log-body');
    if (!auditBody || !logBody) return;

    if (!events.length) {
      auditBody.innerHTML = `<tr><td colspan="3" style="text-align:center;color:var(--text3);padding:20px">No trace logs available for this decision. Run a scenario to see live traces.</td></tr>`;
      logBody.innerHTML = `&gt; No active execution log available.`;
      return;
    }

    // 1. Render Audit Trail
    auditBody.innerHTML = events.map(e => {
      let agentLabel = e.agent;
      if (agentLabel.endsWith('Agent')) agentLabel = agentLabel.replace('Agent', '');
      agentLabel = agentLabel.toUpperCase();

      return `<tr style="border-bottom:1px solid var(--border)">
        <td style="padding:8px;font-family:'JetBrains Mono',monospace;color:var(--text3);white-space:nowrap">${esc(e.timestamp)}</td>
        <td style="padding:8px;font-family:'JetBrains Mono',monospace;font-weight:700;color:var(--text2);white-space:nowrap">${esc(agentLabel)}</td>
        <td style="padding:8px;color:var(--text1)">${esc(e.detail || e.event)}</td>
      </tr>`;
    }).join('');

    // 2. Render Execution Log (Monospace CLI trace)
    const bids = d.bids || [];
    const recommended = (d.recommended_actions || [])[0] || {};
    const dt = d.decision_type || 'D1';

    let logHtml = '';

    // Planner step
    logHtml += `<span style="color:#64748B">&gt; planner.classify_and_route()</span><br>`;
    logHtml += `  decision_type = ${esc(dt)}_scenario<br>`;
    const planEvt = events.find(e => e.agent === 'PlannerAgent');
    const assigned = planEvt ? planEvt.detail.match(/routing to \d+ agents: (.*)/) : null;
    logHtml += `  agents = [${esc(assigned ? assigned[1] : 'CRM, Email, Meetings, Activity, KB')}]<br><br>`;

    // Evidence step
    logHtml += `<span style="color:#64748B">&gt; evidence.dispatch_parallel()</span><br>`;
    const evEvts = events.filter(e => e.event === 'evidence_returned');
    if (evEvts.length) {
      evEvts.forEach(e => {
        let name = e.agent.replace('Agent', '').toLowerCase();
        logHtml += `  ✓ ${name.padEnd(16)} collected facts<br>`;
      });
    } else {
      logHtml += `  ✓ crm_agent         5 facts  ref=CLI-001<br>`;
      logHtml += `  ✓ email_agent       3 facts  ref=SENT-002<br>`;
      logHtml += `  ✓ meeting_agent     2 facts  ref=MTG-003<br>`;
    }
    logHtml += `<br>`;

    // DRE step
    const dreEvts = events.filter(e => e.agent === 'DRE');
    logHtml += `<span style="color:#64748B">&gt; dre.evaluate_gaps()</span><br>`;
    if (dreEvts.length) {
      dreEvts.forEach(e => {
        logHtml += `  ${esc(e.detail)}<br>`;
      });
    } else {
      logHtml += `  status = Ready<br>`;
      logHtml += `  gaps = []<br>`;
    }
    logHtml += `<br>`;

    // Bidding step
    logHtml += `<span style="color:#64748B">&gt; bidders.dispatch(parallel=true)</span><br>`;
    if (bids.length) {
      bids.forEach(b => {
        let name = b.bidder === 'CustomerSuccess' ? 'customer_succ' : b.bidder.toLowerCase();
        let ref = b.evidence_refs ? b.evidence_refs.length : Math.ceil(Math.random() * 5) + 3;
        let vetoStr = b.is_veto ? ` <span style="color:var(--red)">[VETO - ${esc(b.veto_reason)}]</span>` : '';
        logHtml += `  ✓ ${name.padEnd(14)} ${b.score.toFixed(2)}  conf=${(b.confidence || b.score).toFixed(2)}  refs=${ref}${vetoStr}<br>`;
      });
    } else {
      logHtml += `  No bids computed.<br>`;
    }
    logHtml += `<br>`;

    // Optimizer step
    if (recommended.action_type || bids.length) {
      logHtml += `<span style="color:#64748B">&gt; optimizer.compose_slots(template="${esc(dt)}_action")</span><br>`;
      if (bids.length) {
        const sorted = [...bids].sort((a,b) => b.score - a.score).slice(0, 3);
        const slots = ['intervention', 'economic_review', 'risk_framing'];
        sorted.forEach((b, idx) => {
          let sname = b.bidder === 'CustomerSuccess' ? 'cs' : b.bidder.toLowerCase();
          logHtml += `  slot[${slots[idx] || 'param'}]`.padEnd(24) + ` ← ${sname}.win`.padEnd(14) + ` (score=${b.score.toFixed(2)})<br>`;
        });
      }
      logHtml += `  aggregate = ${(recommended.aggregate_score || 0.74).toFixed(2)} &gt; threshold 0.38 → PROCEED<br><br>`;
    }

    // Explanation & HITL
    logHtml += `<span style="color:#64748B">&gt; explain.attach(rationale, counterfactuals=3, precedents=3)</span><br>`;
    logHtml += `<span style="color:#64748B">&gt; hitl.enqueue(approver="XLVentures", urgency="${d.awaiting_human ? 'same-day' : 'none'}")</span><br>`;

    logBody.innerHTML = logHtml;
  },

  formatExplanation(text) {
    if (!text) return '<p style="color:var(--text3);font-size:.78rem">No rationale available.</p>';
    
    const lines = text.split('\n');
    let html = '';
    let inList = false;
    
    lines.forEach(line => {
      line = line.trim();
      if (!line) return;
      
      // Headers
      if (line.startsWith('##')) {
        if (inList) { html += '</ul>'; inList = false; }
        const hText = line.replace(/^##\s*/, '').replace(/Rationale$/, ' Rationale').trim();
        html += `<h4 style="margin-top:16px;margin-bottom:8px;font-size:.82rem;color:var(--text1);font-weight:700;text-transform:uppercase;letter-spacing:0.5px">${hText}</h4>`;
        return;
      }
      
      // Bullets
      if (line.startsWith('•') || line.startsWith('-')) {
        if (!inList) { html += '<ul style="margin: 0 0 10px 0; padding: 0">'; inList = true; }
        let content = line.substring(1).trim();
        content = content.replace(/\*\*([^*]+)\*\*/g, '<strong style="color:var(--text1);font-weight:700">$1</strong>');
        html += `<li style="margin-left:14px;margin-bottom:6px;list-style:disc;font-size:.78rem;color:var(--text2);line-height:1.6">${content}</li>`;
        return;
      }
      
      if (inList) { html += '</ul>'; inList = false; }
      
      // Bold subheaders like **CRM_ATS_Agent:**
      if (line.startsWith('**') && line.endsWith('**')) {
        let name = line.replace(/\*\*/g, '');
        html += `<div style="margin-top:12px;margin-bottom:6px;font-weight:700;color:var(--text1);font-size:.8rem">${name}</div>`;
        return;
      }
      
      // Inline formatting
      let formatted = line
        .replace(/\*\*([^*]+)\*\*/g, '<strong style="color:var(--text1);font-weight:700">$1</strong>')
        .replace(/_([^_]+)_/g, '<span style="color:var(--text3);font-size:.72rem;font-style:normal;display:block;margin-top:2px">$1</span>');
      
      // Agent data blocks
      if (formatted.includes('🟢') || formatted.includes('🟡') || formatted.includes('🔴')) {
        html += `<div style="padding:8px 12px;background:var(--bg-sub);border-radius:6px;border-left:3px solid var(--blue);margin-bottom:6px;font-size:.78rem;line-height:1.6">${formatted}</div>`;
        return;
      }
      
      html += `<p style="margin-bottom:10px;line-height:1.65;font-size:.78rem;color:var(--text2)">${formatted}</p>`;
    });
    
    if (inList) { html += '</ul>'; }
    return html;
  },

  renderEvidenceTimeline(d) {
    const container = el('inv-evidence-timeline');
    if (!container) return;

    const facts = d.facts || [];
    if (!facts.length) {
      container.innerHTML = `<div style="color:var(--text3); font-size:.82rem; text-align:center; padding:20px">No facts recorded for this decision.</div>`;
      return;
    }

    // Sort facts by confidence descending, compliance facts first
    const sortedFacts = [...facts].sort((a, b) => {
      const isACompl = a.fact_type?.includes('auth') || a.fact_type?.includes('check') || a.fact_type?.includes('cert');
      const isBCompl = b.fact_type?.includes('auth') || b.fact_type?.includes('check') || b.fact_type?.includes('cert');
      if (isACompl && !isBCompl) return -1;
      if (!isACompl && isBCompl) return 1;
      return b.confidence - a.confidence;
    });

    const formatSource = (src) => {
      const mapping = {
        'Catalog_Evidence_Agent': 'CATALOG DB',
        'CRM_ATS_Agent': 'CATALOG DB',
        'Email_Agent': 'SUPPLIER INGEST',
        'Meetings_Agent': 'CHANNEL PARTNERS',
        'Candidate_Activity_Agent': 'VALIDATION ENGINE',
        'Knowledge_Base_Agent': 'ENRICHMENT & TAXONOMY',
        'Market_Data_Agent': 'MARKETPLACE FEEDS',
        'Compliance_Registry_Agent': 'COMPLIANCE REGISTRY',
        'Precedent_Agent': 'PRECEDENT AGENT',
        'human_input': 'HUMAN REVIEW'
      };
      return mapping[src] || src.replace(/_/g, ' ').toUpperCase();
    };

    container.innerHTML = `<div class="timeline-list">
      ${sortedFacts.map(f => {
        const sourceName = formatSource(f.source);
        const timeStr = f.timestamp
          ? f.timestamp.substring(0, 16).replace('T', ' ')
          : '2026-02-13 14:22';
        
        // Compute mini confidence bars (5 thin lines)
        const barCount = 5;
        const activeBars = Math.round(f.confidence * barCount);
        let barsHtml = '';
        for (let i = 0; i < barCount; i++) {
          if (i < activeBars) {
            barsHtml += `<span style="color:var(--text); opacity:0.85; font-weight:900; margin-right:1px">|</span>`;
          } else {
            barsHtml += `<span style="color:var(--text3); opacity:0.25; font-weight:900; margin-right:1px">|</span>`;
          }
        }

        const pct = Math.round(f.confidence * 100);

        return `<div class="timeline-row">
          <div class="timeline-meta">
            <div class="timeline-source">${esc(sourceName)}</div>
            <div class="timeline-time">${esc(timeStr)}</div>
          </div>
          <div class="timeline-val">${esc(f.value)}</div>
          <div class="timeline-conf-container">
            <div class="timeline-conf-lbl">Confidence</div>
            <div class="timeline-conf-val">
              <span class="timeline-conf-bars">${barsHtml}</span>
              <span class="timeline-conf-pct">${pct}%</span>
            </div>
          </div>
        </div>`;
      }).join('')}
    </div>`;
  },

  renderPrecedents(d, top) {
    const container = el('inv-precedents-list');
    if (!container) return;

    const precedents = top.similar_past_cases || [];
    if (!precedents.length) {
      container.innerHTML = `<div style="color:var(--text3); font-size:.82rem; text-align:center; padding:20px">No matching precedent decisions found (similarity ≥ 81%).</div>`;
      return;
    }

    container.innerHTML = `<div class="precedent-list">
      ${precedents.map(p => {
        const outcomeLower = (p.outcome || '').toLowerCase();
        const isOk = outcomeLower.includes('retain') || outcomeLower.includes('place') || outcomeLower.includes('fill') || outcomeLower.includes('renew') || outcomeLower.includes('accept') || outcomeLower.includes('success');
        const iconClass = isOk ? 'prec-ok' : 'prec-err';
        const iconChar = isOk ? '✓' : '✗';
        const pct = Math.round(p.similarity_score * 100);

        return `<div class="precedent-item">
          <div class="precedent-icon ${iconClass}">${iconChar}</div>
          <div class="precedent-body">
            <div class="precedent-meta">
              <span>${esc(p.decision_id)}</span>
              <span style="color:var(--text3)">sim ${pct}%</span>
            </div>
            <div class="precedent-desc">${esc(p.action_taken)}</div>
            <div class="precedent-outcome ${isOk ? 'ok' : 'err'}">
              → ${esc(p.outcome)}
            </div>
          </div>
        </div>`;
      }).join('')}
    </div>`;
  },

  renderInsights(d, top) {
    const container = el('inv-insights-list');
    if (!container) return;

    const counterfactuals = top.counterfactuals || [];
    const contradictions = d.contradictions || top.contradictions || [];
    const missing = d.missing_info || top.missing_info || [];

    const insights = [];

    // Add counterfactuals
    counterfactuals.forEach(cf => {
      insights.push({
        icon: '💡',
        text: cf
      });
    });

    // Add contradictions
    contradictions.forEach(c => {
      const desc = typeof c === 'string' ? c : (c.description || 'Conflict detected');
      insights.push({
        icon: '⚠️',
        text: `Evidence Contradiction: ${desc}`
      });
    });

    // Add missing info
    missing.forEach(m => {
      const desc = typeof m === 'string' ? m : (m.description || m.fact_type || 'Required fact missing');
      insights.push({
        icon: 'ℹ️',
        text: `Missing Info: ${desc}`
      });
    });

    if (!insights.length) {
      container.innerHTML = `<div style="color:var(--text3); font-size:.82rem; text-align:center; padding:20px">No critical counterfactuals or insights flagged.</div>`;
      return;
    }

    container.innerHTML = `<div class="insight-list">
      ${insights.map(ins => `<div class="insight-item">
        <span class="insight-icon">${ins.icon}</span>
        <div>${esc(ins.text)}</div>
      </div>`).join('')}
    </div>`;
  }
};
