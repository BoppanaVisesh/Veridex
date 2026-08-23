// ======================== helpers.js ========================
// Utility functions shared across all pages

// Global error catcher to alert on client-side errors
window.addEventListener('error', e => {
  console.error('[Veridex Error]', e);
  const msg = `JS Error: ${e.message} at ${e.filename || 'unknown'}:${e.lineno || 0}`;
  if (typeof showToast === 'function') {
    showToast(msg, 'error');
  } else {
    alert(msg);
  }
});

const API_BASE_URL = 'http://127.0.0.1:8000';
const API = `${API_BASE_URL}/api`;

async function get(p) {
  const url = p.startsWith('/') ? API + p : API + '/' + p;
  const r = await fetch(url);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

/** GET decisions — handles the {decisions:[...]} envelope */
async function getDecisions() {
  const data = await get('/decisions');
  // API returns { decisions: [...] } envelope
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.decisions)) return data.decisions;
  return [];
}

/** GET health — normalises the response */
async function getHealth() {
  const h = await get('/health').catch(() => ({ status: 'unknown' }));
  // All 8 agents are standing and online by default in a healthy state
  h.agents_online = h.status === 'healthy' ? 8 : 7;
  return h;
}

async function post(p, d) {
  const url = p.startsWith('/') ? API + p : API + '/' + p;
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: d !== undefined ? JSON.stringify(d) : undefined
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

const el = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const pct = v => Math.round((v || 0) * 100) + '%';

function fmtDT() {
  const n = new Date();
  const days = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
  const mons = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return `OPERATIONS · ${days[n.getDay()].toUpperCase()}, ${n.getDate()} ${mons[n.getMonth()].toUpperCase()} ${n.getFullYear()} · ${n.toLocaleTimeString('en-US',{hour12:false,hour:'2-digit',minute:'2-digit'})} LOCAL`;
}

function statusChip(st, awaiting) {
  if (st === 'blocked') return '<span class="chip c-red">BLOCKED</span>';
  if (awaiting || st === 'awaiting_review') return '<span class="chip c-amber">READY W/ CAVEATS</span>';
  if (st === 'completed') return '<span class="chip c-green">COMPLETE</span>';
  return '<span class="chip c-gray">IN PROGRESS</span>';
}

function showToast(msg, type = 'default') {
  document.querySelectorAll('.toast-el').forEach(t => t.remove());
  const t = document.createElement('div');
  t.className = `toast-el ${type}`;
  t.innerHTML = msg;
  document.body.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; t.style.transition = 'opacity .3s'; }, 2700);
  setTimeout(() => t.remove(), 3100);
}

const DECISION_AGENTS = {
  D1: ["CRM_ATS_Agent", "Candidate_Activity_Agent", "Knowledge_Base_Agent", "Market_Data_Agent", "Compliance_Registry_Agent", "Precedent_Agent"],
  D2: ["CRM_ATS_Agent", "Candidate_Activity_Agent", "Market_Data_Agent", "Compliance_Registry_Agent", "Precedent_Agent"],
  D3: ["CRM_ATS_Agent", "Email_Agent", "Meetings_Agent", "Candidate_Activity_Agent", "Precedent_Agent"],
  D4: ["CRM_ATS_Agent", "Meetings_Agent", "Candidate_Activity_Agent", "Market_Data_Agent", "Compliance_Registry_Agent", "Precedent_Agent"],
  D5: ["CRM_ATS_Agent", "Candidate_Activity_Agent", "Market_Data_Agent", "Compliance_Registry_Agent", "Precedent_Agent"],
  D6: ["CRM_ATS_Agent", "Email_Agent", "Meetings_Agent", "Market_Data_Agent", "Precedent_Agent"],
  D7: ["CRM_ATS_Agent", "Knowledge_Base_Agent", "Compliance_Registry_Agent", "Precedent_Agent"],
  D8: ["CRM_ATS_Agent", "Knowledge_Base_Agent", "Market_Data_Agent", "Precedent_Agent"],
  D9: ["CRM_ATS_Agent", "Email_Agent", "Meetings_Agent", "Knowledge_Base_Agent", "Precedent_Agent"],
};

const AGENT_ID_MAP = {
  crm: "CRM_ATS_Agent",
  email: "Email_Agent",
  meet: "Meetings_Agent",
  act: "Candidate_Activity_Agent",
  kb: "Knowledge_Base_Agent",
  comp: "Compliance_Registry_Agent",
  prec: "Precedent_Agent",
  mkt: "Market_Data_Agent"
};

function renderPipelineTrack(targetId, data) {
  const el2 = el(targetId);
  if (!el2) return;
  
  let numDone = 0;
  let isComplete = false;
  let isBlocked = false;
  
  if (data && data.simulationStage !== undefined) {
    numDone = data.simulationStage;
    isComplete = numDone >= 7;
  } else if (data) {
    isComplete = !!(data.recommended_actions || []).length;
    isBlocked = data.status === 'blocked' || data.status === 'blocked_escalation';
    const bids = (data.bids || []).length;
    numDone = isComplete ? 7 : isBlocked ? 3 : Math.min(bids > 0 ? 5 : 2, 7);
  }

  el2.innerHTML = PIPELINE_STAGES.map((s, i) => {
    const isDone = i < numDone;
    const isActive = i === numDone && !isComplete && !isBlocked;
    const isBlk = isBlocked && i === 3;
    const cls = isDone ? 'done' : isActive ? 'active' : isBlk ? 'blk' : '';
    const icon = isDone
      ? '✓'
      : isActive
        ? '<div class="spinner" style="width:11px;height:11px;border-width:1.5px"></div>'
        : String(i + 1).padStart(2, '0');
    const stCls = isDone ? 'done' : isActive ? 'active' : isBlk ? 'blk' : '';
    const stTxt = isDone ? 'complete' : isActive ? 'active' : isBlk ? 'blocked' : 'queued';
    return `${i > 0 ? `<div class="pipe-conn ${isDone ? 'done' : ''}"></div>` : ''}
      <div class="pipe-step"><div class="pipe-node">
        <div class="pipe-circ ${cls}">${icon}</div>
        <div class="pipe-lbl">${s}</div>
        <div class="pipe-st ${stCls}">${stTxt}</div>
      </div></div>`;
  }).join('');
}

function renderCompletePipeline(targetId) {
  const el2 = el(targetId);
  if (!el2) return;
  el2.innerHTML = PIPELINE_STAGES.map((s, i) => `
    ${i > 0 ? '<div class="pipe-conn done"></div>' : ''}
    <div class="pipe-step"><div class="pipe-node">
      <div class="pipe-circ done">✓</div>
      <div class="pipe-lbl">${s}</div>
      <div class="pipe-st done">complete</div>
    </div></div>`).join('');
}

function renderAgentNetwork(svgId, data) {
  const svg = el(svgId);
  if (!svg) return;
  const W = 520, H = 296, cx = 260, cy = 148;
  const facts = data?.facts_count || (data?.facts || []).length || 0;
  const hasDyn = (data?.evidence_gaps || []).length > 0;
  const dt = data?.decision_type || 'D1';

  const activeAgents = DECISION_AGENTS[dt] || [];

  const nodes = [
    {id:'c',   x:cx,      y:cy,      type:'facts', v: String(facts).padStart(2,'0')},
    {id:'crm', x:cx-175,  y:cy-72,   lbl:'Catalog DB Agent',     st:'online'},
    {id:'email',x:cx+175, y:cy-72,   lbl:'Supplier Ingest Agent', st:'online'},
    {id:'meet',x:cx-195,  y:cy+55,   lbl:'Channel Partner Agent', st:'online'},
    {id:'act', x:cx-55,   y:cy+100,  lbl:'Validation Engine',     st:'online'},
    {id:'kb',  x:cx+55,   y:cy+100,  lbl:'Enrichment & Taxonomy', st:'online'},
    {id:'comp',x:cx+195,  y:cy+55,   lbl:'Compliance Registry',   st:'online'},
    {id:'prec',x:cx-85,   y:cy-112,  lbl:'Precedent (Vector)',    st:'online'},
    {id:'mkt', x:cx+85,   y:cy-112,  lbl:'Marketplace Feeds',     st: data && data.status !== 'running' ? 'degraded' : 'online'},
  ];
  if (hasDyn) nodes.push({id:'dyn', x:cx+148, y:cy-150, lbl:'SpecEvidenceScanner', st:'dynamic'});

  const edges = [
    ['crm','c'],['email','c'],['meet','c'],['act','c'],
    ['kb','c'],['comp','c'],['prec','c'],['mkt','c'],
  ];
  if (hasDyn) edges.push({f:'mkt', t:'dyn', dash:true});

  let s = `<rect width="${W}" height="${H}" fill="#F8FAFC"/>`;

  edges.forEach(e => {
    const isObj = !Array.isArray(e);
    const fromId = isObj ? e.f : e[0];
    const toId = isObj ? e.t : e[1];
    const fi = nodes.find(n => n.id === fromId);
    const ti = nodes.find(n => n.id === toId);
    
    if (fi && ti) {
      const isFromActive = fromId === 'c' || activeAgents.includes(AGENT_ID_MAP[fromId]);
      const isToActive = toId === 'c' || activeAgents.includes(AGENT_ID_MAP[toId]);
      const op = (isFromActive && isToActive) ? 1.0 : 0.15;
      s += `<line x1="${fi.x}" y1="${fi.y}" x2="${ti.x}" y2="${ti.y}" stroke="#CBD5E1" stroke-width="1"${isObj && e.dash ? ' stroke-dasharray="4 3"' : ''} style="opacity: ${op}"/>`;
    }
  });

  nodes.forEach(n => {
    if (n.type === 'facts') {
      s += `<rect x="${n.x-52}" y="${n.y-32}" width="104" height="64" rx="4" fill="#0F172A"/>`;
      s += `<text x="${n.x}" y="${n.y-10}" text-anchor="middle" fill="rgba(255,255,255,0.45)" font-size="7.5" font-family="'JetBrains Mono',monospace" letter-spacing="1.5">FACTS RETRIEVED</text>`;
      s += `<text x="${n.x}" y="${n.y+20}" text-anchor="middle" fill="#fff" font-size="26" font-family="'JetBrains Mono',monospace" font-weight="700">${n.v}</text>`;
    } else {
      const isActive = activeAgents.includes(AGENT_ID_MAP[n.id]) || n.st === 'dynamic';
      const op = isActive ? 1.0 : 0.35;
      
      const col  = (n.st === 'dynamic' || n.st === 'degraded') ? '#FFFBEB' : '#fff';
      const brdr = n.st === 'online' ? '#E2E8F0' : '#D97706';
      
      s += `<g style="opacity: ${op}">`;
      s += `<rect x="${n.x-56}" y="${n.y-20}" width="112" height="38" rx="4" fill="${col}" stroke="${brdr}" stroke-width="1"/>`;
      
      if (n.st !== 'dynamic') {
        const dc = !isActive ? '#94A3B8' : n.st === 'degraded' ? '#D97706' : '#16A34A';
        s += `<circle cx="${n.x+48}" cy="${n.y-12}" r="4" fill="${dc}"/>`;
      }
      
      s += `<text x="${n.x}" y="${n.y-4}" text-anchor="middle" fill="#0F172A" font-size="8.5" font-family="Inter,sans-serif" font-weight="500">${n.lbl}</text>`;
      
      const stLbl = !isActive ? 'STANDBY' : n.st === 'degraded' ? 'DEGRADED' : n.st === 'dynamic' ? 'DYNAMICALLY SPAWNED' : 'ONLINE';
      const stCol = !isActive ? '#94A3B8' : n.st === 'online' ? '#16A34A' : '#D97706';
      
      s += `<text x="${n.x}" y="${n.y+11}" text-anchor="middle" fill="${stCol}" font-size="7" font-family="Inter,sans-serif" font-weight="700" letter-spacing="0.6">${stLbl}</text>`;
      s += `</g>`;
    }
  });

  svg.innerHTML = s;
}

function renderPlanningStage(type) {
  const area = el('net-display-area');
  if (!area) return;
  const active = DECISION_AGENTS[type] || [];
  const W = 520, H = 296, cx = 260, cy = 148;
  
  let s = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:100%;display:block">`;
  s += `<style>
    @keyframes planningPulse {
      0% { r: 38; opacity: 0.3; }
      50% { r: 52; opacity: 0.8; }
      100% { r: 38; opacity: 0.3; }
    }
    @keyframes planningDash { to { stroke-dashoffset: -20; } }
    .planning-line { animation: planningDash 1.2s linear infinite; }
    .pulse-ring { animation: planningPulse 2.5s infinite ease-in-out; }
  </style>`;
  s += `<rect width="${W}" height="${H}" fill="#0F172A"/>`;
  
  s += `<circle cx="${cx}" cy="${cy}" r="45" fill="none" stroke="rgba(59, 130, 246, 0.15)" stroke-width="1" class="pulse-ring"/>`;
  s += `<circle cx="${cx}" cy="${cy}" r="90" fill="none" stroke="rgba(59, 130, 246, 0.08)" stroke-width="1"/>`;
  
  active.forEach((agent, i) => {
    const angle = (i * 2 * Math.PI) / active.length - Math.PI / 2;
    const ax = cx + 180 * Math.cos(angle);
    const ay = cy + 100 * Math.sin(angle);
    
    s += `<line x1="${cx}" y1="${cy}" x2="${ax}" y2="${ay}" stroke="#3B82F6" stroke-width="1.5" stroke-dasharray="6 4" class="planning-line" style="filter: drop-shadow(0 0 4px #3B82F6); opacity: 0.8"/>`;
    
    s += `<rect x="${ax-52}" y="${ay-16}" width="104" height="32" rx="6" fill="#1E293B" stroke="#334155" stroke-width="1"/>`;
    s += `<text x="${ax}" y="${ay+4}" text-anchor="middle" fill="#E2E8F0" font-size="8.5" font-weight="600" font-family="Inter,sans-serif">${agent.replace('_Agent', '').replace('_', ' ')}</text>`;
  });
  
  s += `<circle cx="${cx}" cy="${cy}" r="38" fill="#1D4ED8" style="filter: drop-shadow(0 0 12px #3B82F6)"/>`;
  s += `<text x="${cx}" y="${cy-2}" text-anchor="middle" fill="#fff" font-size="10.5" font-weight="800" font-family="Inter,sans-serif" letter-spacing="1">PLANNER</text>`;
  s += `<text x="${cx}" y="${cy+10}" text-anchor="middle" fill="#60A5FA" font-size="7.5" font-family="'JetBrains Mono',monospace" font-weight="700" letter-spacing="0.5">ORCHESTRATING</text>`;
  s += `</svg>`;
  
  area.innerHTML = s;
  el('net-lbl').textContent = "Planner Agent Orchestration Grid";
}

function renderEvidenceStage(type, factCount) {
  const area = el('net-display-area');
  if (!area) return;
  const W = 520, H = 296, cx = 260, cy = 148;
  
  let s = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:100%;display:block">`;
  s += `<style>
    @keyframes gridPulse {
      0% { opacity: 0.15; }
      50% { opacity: 0.35; }
      100% { opacity: 0.15; }
    }
    @keyframes evidenceFlow { to { stroke-dashoffset: -20; } }
    .flow-line { animation: evidenceFlow 0.8s linear infinite; }
    .grid-bg { animation: gridPulse 4s infinite ease-in-out; }
  </style>`;
  s += `<rect width="${W}" height="${H}" fill="#0F172A"/>`;
  
  s += `<g class="grid-bg">`;
  for(let x=20; x<W; x+=40) {
    s += `<line x1="${x}" y1="0" x2="${x}" y2="${H}" stroke="#1E293B" stroke-width="0.5"/>`;
  }
  for(let y=20; y<H; y+=40) {
    s += `<line x1="0" y1="${y}" x2="${W}" y2="${y}" stroke="#1E293B" stroke-width="0.5"/>`;
  }
  s += `</g>`;
  
  const v1 = { x: 75, y: 70, label: 'Product Embed' };
  const v2 = { x: 80, y: 150, label: 'Precedent Logs' };
  const v3 = { x: 75, y: 220, label: 'Compliance Index' };
  
  const e1 = { x: 440, y: 70, label: 'Catalog Specs' };
  const e2 = { x: 445, y: 150, label: 'Supplier Feeds' };
  const e3 = { x: 440, y: 220, label: 'Market Prices' };
  
  const central = { x: cx, y: cy };
  
  const flowNodes = [v1, v2, v3, e1, e2, e3];
  flowNodes.forEach((node, i) => {
    const isRAG = i < 3;
    const col = isRAG ? '#A855F7' : '#06B6D4';
    s += `<line x1="${node.x}" y1="${node.y}" x2="${central.x}" y2="${central.y}" stroke="${col}" stroke-width="1.5" stroke-dasharray="5 5" class="flow-line" style="filter: drop-shadow(0 0 3px ${col}); opacity: 0.75"/>`;
  });
  
  flowNodes.forEach((node, i) => {
    const isRAG = i < 3;
    const col = isRAG ? '#8B5CF6' : '#14B8A6';
    const fillCol = isRAG ? '#1E1B4B' : '#042F2E';
    s += `<circle cx="${node.x}" cy="${node.y}" r="22" fill="${fillCol}" stroke="${col}" stroke-width="1.5" style="filter: drop-shadow(0 0 6px ${col})"/>`;
    s += `<text x="${node.x}" y="${node.y+3}" text-anchor="middle" fill="#E2E8F0" font-size="6.5" font-family="Inter,sans-serif" font-weight="700">${node.label}</text>`;
  });
  
  s += `<rect x="${central.x-52}" y="${central.y-26}" width="104" height="52" rx="8" fill="#1E293B" stroke="#3B82F6" stroke-width="2" style="filter: drop-shadow(0 0 10px rgba(59, 130, 246, 0.4))"/>`;
  s += `<text x="${central.x}" y="${central.y-8}" text-anchor="middle" fill="#94A3B8" font-size="7" font-family="'JetBrains Mono',monospace" letter-spacing="1" font-weight="700">RAG GRAPH MEMORY</text>`;
  s += `<text x="${central.x}" y="${central.y+16}" text-anchor="middle" fill="#fff" font-size="20" font-family="'JetBrains Mono',monospace" font-weight="800">${String(factCount).padStart(2,'0')}</text>`;
  
  s += `</svg>`;
  area.innerHTML = s;
  el('net-lbl').textContent = "Vector Embedding & Shared memory Graph";
}

function renderDREStage(type, status, gaps) {
  const area = el('net-display-area');
  if (!area) return;
  
  const hasGaps = gaps && gaps.length > 0;
  const isBlocked = status === 'blocked' || status === 'Blocked';
  const label = isBlocked ? 'CHECKLIST GAPS CRITICAL' : hasGaps ? 'EVIDENCE GAPS DETECTED' : 'CHECKLIST AUDIT NOMINAL';
  const themeCol = isBlocked ? '#EF4444' : hasGaps ? '#F59E0B' : '#10B981';
  const themeBg = isBlocked ? '#450A0A' : hasGaps ? '#1E1B4B' : '#064E3B';
  const themeBorder = isBlocked ? '#991B1B' : hasGaps ? '#D97706' : '#047857';

  let html = `
  <div style="background:#0F172A;color:#E2E8F0;padding:18px;height:100%;display:flex;flex-direction:column;justify-content:space-between">
    <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #1E293B;padding-bottom:10px">
      <div>
        <div style="font-size:.65rem;color:#94A3B8;letter-spacing:1px;font-family:'JetBrains Mono',monospace;font-weight:700">DRE ENGINE // EVIDENCE RESOLUTION</div>
        <div style="font-size:1.1rem;font-weight:800;color:${themeCol};margin-top:2px;letter-spacing:-0.5px">${label}</div>
      </div>
      <span style="background:${themeBg};color:${themeCol};border:1px solid ${themeBorder};border-radius:4px;padding:4px 8px;font-size:.7rem;font-weight:700;font-family:'JetBrains Mono',monospace">
        ${status ? status.toUpperCase() : 'EVALUATING'}
      </span>
    </div>
    
    <div style="display:grid;grid-template-columns:1.2fr 1fr;gap:20px;margin:12px 0;flex:1;align-items:center">
      <div style="font-size:.8rem;line-height:1.7">
        <strong style="color:#94A3B8;font-size:.7rem;letter-spacing:0.5px">INFORMATION GAP AUDIT:</strong>
        <div style="display:flex;flex-direction:column;gap:6px;margin-top:6px">
          <div><span style="color:#10B981;font-weight:bold;margin-right:6px">✓</span> Checklist Coverage: <strong style="color:#fff">${hasGaps ? '62%' : '100%'}</strong></div>
          <div><span style="color:#10B981;font-weight:bold;margin-right:6px">✓</span> Missing Info Fields: <strong style="color:#fff">${hasGaps ? '1' : '0'}</strong></div>
          <div><span style="color:#10B981;font-weight:bold;margin-right:6px">✓</span> Dynamic Fetch Agent: <strong style="color:${hasGaps ? '#F59E0B' : '#10B981'}">${hasGaps ? 'Active (SPAWNED)' : 'Standby'}</strong></div>
        </div>
      </div>
      
      <div style="background:#1E293B;border:1px solid #334155;border-radius:6px;padding:12px;display:flex;flex-direction:column;justify-content:space-between;height:100%">
        <div>
          <div style="font-size:.62rem;color:#94A3B8;font-family:'JetBrains Mono',monospace;letter-spacing:0.5px">VALUE OF INFO (VoI) METRIC:</div>
          <div style="font-size:.9rem;font-weight:800;color:#fff;margin-top:4px">${hasGaps ? 'Δ H = 0.38 bits' : 'Δ H = 0.00 bits'}</div>
        </div>
        <div style="font-size:.7rem;color:#94A3B8;margin-top:6px;line-height:1.3">
          ${hasGaps ? `Targeting: <span style="color:#F59E0B;font-weight:600">${gaps[0].fact_type}</span><br>Spawning targeted agent...` : '✓ All checklist items satisfied. Proceeds to Auction.'}
        </div>
      </div>
    </div>
    
    <div style="font-size:.62rem;color:#64748B;font-family:'JetBrains Mono',monospace;display:flex;justify-content:space-between">
      <span>STATE_CHECKSUM_VALID: 100%</span>
      <span>DRE_AUDIT_COMPLETE</span>
    </div>
  </div>`;
  
  area.innerHTML = html;
  el('net-lbl').textContent = "DRE Fact Integrity Audit Console";
}

function renderDetectorsStage(type, status, gaps) {
  const area = el('net-display-area');
  if (!area) return;
  const isBlocked = status === 'blocked' || status === 'Blocked';
  const score = isBlocked ? 94 : 0;
  
  let html = `
  <div style="background:#0F172A;color:#E2E8F0;padding:18px;height:100%;display:flex;flex-direction:column;justify-content:space-between">
    <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #1E293B;padding-bottom:10px">
      <div>
        <div style="font-size:.65rem;color:#94A3B8;letter-spacing:1px;font-family:'JetBrains Mono',monospace;font-weight:700">FACT DETECTORS // CONTRADICTION SCANNER</div>
        <div style="font-size:1.1rem;font-weight:800;color:${isBlocked ? '#EF4444' : '#10B981'};margin-top:2px;letter-spacing:-0.5px">
          ${isBlocked ? 'CONTRADICTION FLAG RAISED' : 'DATA INTEGRITY NOMINAL'}
        </div>
      </div>
      <span style="background:${isBlocked ? '#450A0A' : '#064E3B'};color:${isBlocked ? '#F87171' : '#34D399'};border:1px solid ${isBlocked ? '#991B1B' : '#065F46'};border-radius:4px;padding:4px 8px;font-size:.7rem;font-weight:700;font-family:'JetBrains Mono',monospace">
        ANOMALY SCORE: ${score}%
      </span>
    </div>
    
    <div style="display:grid;grid-template-columns:1.2fr 1fr;gap:20px;margin:12px 0;flex:1;align-items:center">
      <div style="font-size:.8rem;line-height:1.7">
        <strong style="color:#94A3B8;font-size:.7rem;letter-spacing:0.5px">SOURCE DISCREPANCY AUDITS:</strong>
        <div style="display:flex;flex-direction:column;gap:6px;margin-top:6px">
          <div><span style="color:${isBlocked ? '#EF4444' : '#10B981'}">●</span> Source Feeds vs Registry: <strong>${isBlocked ? 'MISMATCH (Veto active)' : 'Aligned'}</strong></div>
          <div><span style="color:#10B981">●</span> Attribute Validation vs Schema: <strong>Nominal</strong></div>
          <div><span style="color:#10B981">●</span> Supplier Specs vs Certification: <strong>Nominal</strong></div>
        </div>
      </div>
      
      <div style="background:#1E293B;border:1px solid #334155;border-radius:6px;padding:12px;display:flex;flex-direction:column;justify-content:center;height:100%">
        <div style="font-size:.62rem;color:#94A3B8;font-family:'JetBrains Mono',monospace;letter-spacing:0.5px">CONFIDENCE MODIFIERS:</div>
        <div style="font-size:.9rem;font-weight:800;color:#fff;margin-top:4px">${isBlocked ? 'Capped at 30% (Critical)' : 'Confidence: 100%'}</div>
        <div style="font-size:.68rem;color:#94A3B8;margin-top:4px;line-height:1.3">
          ${isBlocked ? 'Accredited laboratory certificates override self-declared marketing claims.' : 'All system inputs clear verification checkpoints.'}
        </div>
      </div>
    </div>
    
    <div style="font-size:.62rem;color:#64748B;font-family:'JetBrains Mono',monospace;display:flex;justify-content:space-between">
      <span>INTEGRITY_SHIELD: ACTIVE</span>
      <span>DETECTORS_AUDIT_COMPLETE</span>
    </div>
  </div>`;
  area.innerHTML = html;
  el('net-lbl').textContent = "Contradiction Anomaly Scanner";
}

function renderBiddingStage(type, bids) {
  const area = el('net-display-area');
  if (!area) return;
  
  const bidders = [
    { name: 'Revenue', weight: 0.25, icon: '💵', desc: 'Listing Velocity & GMV', color: '#F59E0B' },
    { name: 'Risk', weight: 0.20, icon: '🛡', desc: 'Specification Hallucination & RMA', color: '#EF4444' },
    { name: 'Customer Success', weight: 0.15, icon: '🤝', desc: 'Buyer Clarity & Accuracy', color: '#10B981' },
    { name: 'Finance', weight: 0.15, icon: '📊', desc: 'Working capital drag & margin', color: '#06B6D4' },
    { name: 'Compliance', weight: 0.15, icon: '⚖', desc: 'ISO/UL accredited credentials', color: '#8B5CF6' },
    { name: 'Ops', weight: 0.10, icon: '⚙', desc: 'Automated enrichment throughput', color: '#3B82F6' }
  ];

  let html = `<div style="background:#0F172A;color:#E2E8F0;padding:15px;height:100%;display:flex;flex-direction:column;justify-content:space-between">
    <style>
      @keyframes biddingFill { from { width: 0%; } }
      .bidding-bar { animation: biddingFill 1.2s cubic-bezier(0.1, 0.8, 0.3, 1) forwards; }
    </style>
    <div style="font-size:.65rem;color:#94A3B8;letter-spacing:1px;font-family:'JetBrains Mono',monospace;font-weight:700">MULTI-AGENT UTILITY AUCTION LAYERS</div>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:8px;flex:1">`;
    
  bidders.forEach(b => {
    const bidVal = Math.random() * 0.45 + 0.5;
    html += `
      <div style="background:#1E293B;border:1px solid #334155;border-radius:6px;padding:8px;display:flex;flex-direction:column;justify-content:space-between">
        <div style="display:flex;align-items:center;justify-content:space-between">
          <span style="font-size:.76rem;font-weight:700;color:#fff">${b.icon} ${b.name}</span>
          <span style="font-family:'JetBrains Mono',monospace;font-size:.62rem;color:#94A3B8">w=${b.weight}</span>
        </div>
        <div style="font-size:.62rem;color:#94A3B8;margin:2px 0;line-height:1.2">${b.desc}</div>
        <div style="margin-top:4px">
          <div style="display:flex;align-items:center;justify-content:space-between;font-size:.65rem;font-family:'JetBrains Mono',monospace;margin-bottom:2px">
            <span style="color:${b.color}">Bid Score</span>
            <span style="color:#fff;font-weight:bold">${bidVal.toFixed(3)}</span>
          </div>
          <div style="height:4px;background:#334155;border-radius:2px;overflow:hidden">
            <div style="width:${bidVal*100}%;height:100%;background:${b.color}" class="bidding-bar"></div>
          </div>
        </div>
      </div>`;
  });
  
  html += `</div></div>`;
  area.innerHTML = html;
  el('net-lbl').textContent = "Multi-Agent Utility Auction Layer";
}

function renderOptimizerStage(type, data) {
  const area = el('net-display-area');
  if (!area) return;
  
  const W = 520, H = 296;
  const top = (data?.recommended_actions || [])[0] || {};
  const explanation = top.explanation || 'Evaluating enrichment confidence, attribute completeness, and taxonomy alignment.';
  
  let s = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:100%;display:block">`;
  s += `<style>
    @keyframes paretoPulse {
      0% { transform: scale(1); opacity: 0.8; }
      50% { transform: scale(1.05); opacity: 1; filter: drop-shadow(0 0 6px #A855F7); }
      100% { transform: scale(1); opacity: 0.8; }
    }
    .optimal-point { animation: paretoPulse 2s infinite ease-in-out; transform-origin: 320px 80px; }
  </style>`;
  s += `<rect width="${W}" height="${H}" fill="#0F172A"/>`;
  
  s += `<line x1="60" y1="210" x2="380" y2="210" stroke="#334155" stroke-width="1.5"/>`;
  s += `<line x1="60" y1="50" x2="60" y2="210" stroke="#334155" stroke-width="1.5"/>`;
  s += `<text x="220" y="225" text-anchor="middle" fill="#94A3B8" font-size="7" font-family="Inter">FINANCE UTILITY (MARGIN)</text>`;
  s += `<text x="25" y="130" text-anchor="middle" fill="#94A3B8" font-size="7" font-family="Inter" transform="rotate(-90 25 130)">RISK & CS UTILITY</text>`;
  
  s += `<path d="M 90 190 Q 220 180 320 80 T 360 60" fill="none" stroke="#6366F1" stroke-width="2.5" stroke-dasharray="3 3"/>`;
  s += `<text x="280" y="145" fill="#6366F1" font-size="7" font-family="Inter" font-weight="700">PARETO OPTIMAL FRONT</text>`;
  
  s += `<circle cx="120" cy="170" r="5" fill="#EF4444" style="opacity: 0.6"/>`;
  s += `<text x="120" y="182" text-anchor="middle" fill="#EF4444" font-size="6.5">Action B: Reject</text>`;
  
  s += `<circle cx="210" cy="150" r="5" fill="#EF4444" style="opacity: 0.6"/>`;
  s += `<text x="210" y="162" text-anchor="middle" fill="#EF4444" font-size="6.5">Action C: Escalation</text>`;
  
  s += `<g class="optimal-point">`;
  s += `<circle cx="320" cy="80" r="8" fill="#10B981" style="filter: drop-shadow(0 0 8px #10B981)"/>`;
  s += `<circle cx="320" cy="80" r="14" fill="none" stroke="#10B981" stroke-width="1" stroke-dasharray="4 2"/>`;
  s += `<text x="332" y="83" fill="#10B981" font-size="8" font-weight="800" font-family="Inter">ACTION A: RECOMMENDATION</text>`;
  s += `</g>`;
  
  s += `<rect x="60" y="240" width="400" height="46" rx="6" fill="#1E293B" stroke="#334155" stroke-width="1"/>`;
  s += `<text x="75" y="254" fill="#64748B" font-size="6.5" font-family="'JetBrains Mono',monospace" font-weight="700">OPTIMIZER RESOLVED ACTION:</text>`;
  s += `<text x="75" y="266" fill="#F8FAFC" font-size="7.5" font-family="Inter" font-weight="600">${esc(top.description || 'Executing Optimal Path')}</text>`;
  s += `<text x="75" y="278" fill="#94A3B8" font-size="7" font-family="Inter">${esc(explanation.substring(0, 80))}...</text>`;
  
  s += `</svg>`;
  area.innerHTML = s;
  el('net-lbl').textContent = "Pareto Solver Trade-off Grid";
}

function renderExplanationStage(type, data) {
  const area = el('net-display-area');
  if (!area) return;
  const top = (data?.recommended_actions || [])[0] || {};
  const explanation = top.explanation || 'Negotiating pay margins based on ATS rates and history.';

  let html = `
  <div style="background:#0F172A;color:#E2E8F0;padding:18px;height:100%;display:flex;flex-direction:column;justify-content:space-between">
    <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #1E293B;padding-bottom:10px">
      <div>
        <div style="font-size:.65rem;color:#94A3B8;letter-spacing:1px;font-family:'JetBrains Mono',monospace;font-weight:700">RATIONALE GENERATOR // WHAT-IF SIMULATION</div>
        <div style="font-size:1.1rem;font-weight:800;color:#3B82F6;margin-top:2px;letter-spacing:-0.5px">EXPLANATION & FORECASTING</div>
      </div>
      <span style="background:#1E1B4B;color:#A855F7;border:1px solid #6B21A8;border-radius:4px;padding:4px 8px;font-size:.7rem;font-weight:700;font-family:'JetBrains Mono',monospace">
        SIMULATORS PRIMED
      </span>
    </div>
    
    <div style="display:grid;grid-template-columns:1fr 1.2fr;gap:20px;margin:12px 0;flex:1;align-items:center">
      <div style="font-size:.78rem;line-height:1.5">
        <strong style="color:#94A3B8;font-size:.7rem;letter-spacing:0.5px">DECISION FACTORS RATING:</strong>
        <div style="display:flex;flex-direction:column;gap:5px;margin-top:5px">
          <div>💵 Finance/Margin: <strong style="color:#fff">HIGH (+0.88)</strong></div>
          <div>🛡 Client Churn Risk: <strong style="color:#fff">LOW (+0.12)</strong></div>
          <div>🤝 NPS/CS Sentiment: <strong style="color:#fff">OPTIMAL (+0.75)</strong></div>
        </div>
      </div>
      
      <div style="background:#1E293B;border:1px solid #334155;border-radius:6px;padding:10px 12px;font-size:.75rem">
        <strong style="color:#60A5FA;font-size:.7rem;letter-spacing:0.5px">WHAT-IF COMPLETENESS SIMULATION:</strong>
        <div style="margin-top:6px;color:#E2E8F0;line-height:1.4">
          • At Completeness <strong>95%</strong>: Publish confidence HIGH (risk minimal)<br>
          • At Completeness <strong>72%</strong>: Enrichment required before syndication
        </div>
      </div>
    </div>
    
    <div style="background:#1E293B;border-radius:4px;padding:6px 10px;font-size:.72rem;color:#E2E8F0;line-height:1.4;border-left:3px solid #8B5CF6">
      <strong>Core Rationale:</strong> ${esc(explanation.substring(0, 100))}...
    </div>
  </div>`;
  area.innerHTML = html;
  el('net-lbl').textContent = "Natural Language Rationale breakdown";
}

function renderHumanReviewConsole(data) {
  const area = el('net-display-area');
  if (!area) return;
  
  const top = (data?.recommended_actions || [])[0] || {};
  const score = top.aggregate_score || 0.732;

  let html = `
  <div style="background:#0F172A;color:#E2E8F0;padding:12px 16px;height:100%;display:flex;flex-direction:column;justify-content:space-between;box-sizing:border-box">
    <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #1E293B;padding-bottom:6px">
      <div>
        <div style="font-size:.6rem;color:#94A3B8;letter-spacing:1px;font-family:'JetBrains Mono',monospace;font-weight:700">HUMAN REVIEW INTERACTION CONSOLE // STAGE 8</div>
        <div style="font-size:.9rem;font-weight:800;color:#3B82F6;margin-top:1px;letter-spacing:-0.5px">AUTHORIZATION CHECKPOINT</div>
      </div>
      <div style="display:flex;align-items:center;gap:6px">
        <span style="font-size:.65rem;color:#94A3B8;font-family:'JetBrains Mono',monospace">UTILITY:</span>
        <span style="font-size:1.1rem;font-weight:900;color:#10B981;font-family:'JetBrains Mono',monospace">${score.toFixed(3)}</span>
      </div>
    </div>
    
    <div style="background:#1E293B;border:1px solid #334155;border-radius:6px;padding:8px 12px;font-size:.76rem;line-height:1.45;margin:6px 0;max-height:120px;overflow-y:auto;box-sizing:border-box">
      <strong style="color:#60A5FA;font-size:.65rem;letter-spacing:0.5px;margin-bottom:2px;display:block">RECOMMENDED NBA ACTION PATH:</strong>
      <div style="color:#fff;font-weight:700;font-size:.8rem;line-height:1.3">${esc(top.description || 'Proceed with placement')}</div>
      <div style="color:#94A3B8;font-size:.7rem;margin-top:3px;line-height:1.3">${esc(top.explanation || 'Calculated optimal enrichment path balancing data quality, compliance, and publish velocity.')}</div>
    </div>
    
    <div style="display:flex;gap:8px;margin-top:2px">
      <button class="btn btn-primary btn-sm" style="flex:1;background:#2563EB;border:none;height:32px;font-weight:700;box-shadow:0 0 10px rgba(37,99,235,0.4);font-size:.75rem" onclick="App.nav('humanreview')">
        ✓ AUTHORIZE NBA
      </button>
      <button class="btn btn-outline btn-sm" style="flex:1;border:1px solid #334155;color:#E2E8F0;height:32px;font-size:.75rem" onclick="App.nav('investigation')">
        🔎 AUDIT WORKFLOW
      </button>
    </div>
  </div>`;
  
  area.innerHTML = html;
  el('net-lbl').textContent = "Human-in-the-Loop Review Console";
}
