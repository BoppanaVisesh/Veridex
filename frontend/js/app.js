// ======================== app.js ========================
// Main app router, search modal, keyboard shortcuts, init

const App = {
  page: 'command',
  currentDecision: null,
  decisions: [],

  // ── Navigation ──────────────────────────────────────────────
  nav(p) {
    document.querySelectorAll('.page').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(x => x.classList.remove('active'));
    el('page-' + p)?.classList.add('active');
    el('nav-' + p)?.classList.add('active');
    this.page = p;

    const names = {
      command:        'command-center',
      scenarios:      'run-scenario',
      missioncontrol: 'mission-control',
      investigation:  'investigation',
      humanreview:    'human-review',
      metrics:        'metrics',
      catalog:        'catalog-intelligence',
      unilog:         'unilog-intelligence',
    };
    el('crumb-txt').textContent = names[p] || p;

    if (p === 'command')       { CommandPage.load(); }
    if (p === 'scenarios')     { ScenariosPage.render(); }
    if (p === 'metrics')       { MetricsPage.load(); }
    if (p === 'catalog')       { CatalogPage.load(); }
    if (p === 'unilog')        { UnilogPage.init(); }

    if (p === 'investigation') {
      if (App.currentDecision) {
        InvestigationPage.render(App.currentDecision);
      } else {
        // Auto-load the first live decision if none selected yet
        App._autoLoadDecision('investigation');
      }
    }

    if (p === 'humanreview') {
      if (App.currentDecision) {
        HumanReviewPage.render(App.currentDecision);
      } else {
        App._autoLoadDecision('humanreview');
      }
    }
  },

  // Auto-load first available live decision and navigate to target page
  async _autoLoadDecision(targetPage) {
    // Show loading state
    const titleEl = el(targetPage === 'investigation' ? 'inv-title' : 'hr-title');
    if (titleEl) titleEl.textContent = 'Loading...';

    try {
      const decisions = await getDecisions();
      App.decisions = decisions;
      const live = decisions.filter(d =>
        !d.decision_id?.startsWith('HIST-') && d.description);

      if (!live.length) {
        showToast('No active decisions. Run a scenario first.', 'error');
        App.nav('scenarios');
        return;
      }

      // Prefer awaiting_human_review, then anything live
      const preferred = live.find(d =>
        d.awaiting_human || d.status === 'awaiting_human_review'
      ) || live[0];

      await App.openDecision(preferred.decision_id, targetPage);
    } catch(e) {
      showToast('Error loading decision: ' + e.message, 'error');
    }
  },

  // Load a specific decision and navigate to a page
  async openDecision(id, targetPage = 'investigation') {
    try {
      const d = await get('/decisions/' + id);
      App.currentDecision = d;

      if (targetPage === 'investigation' || targetPage == null) {
        InvestigationPage.render(d);
        // Make sure investigation page is active
        if (App.page !== 'investigation') {
          document.querySelectorAll('.page').forEach(x => x.classList.remove('active'));
          document.querySelectorAll('.nav-item').forEach(x => x.classList.remove('active'));
          el('page-investigation')?.classList.add('active');
          el('nav-investigation')?.classList.add('active');
          el('crumb-txt').textContent = 'investigation';
          App.page = 'investigation';
        }
      } else if (targetPage === 'humanreview') {
        HumanReviewPage.render(d);
      }
    } catch(e) {
      showToast('Error loading decision: ' + e.message, 'error');
    }
  },

  // ── Search Modal ─────────────────────────────────────────────
  openSearch() {
    el('s-modal').classList.add('open');
    setTimeout(() => el('s-inp')?.focus(), 50);
  },
  closeSearch() {
    el('s-modal').classList.remove('open');
  },
  searchFilter(q) {
    const b = el('s-results');
    if (!q.trim()) {
      b.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text3);font-size:.8rem">Start typing to search...</div>';
      return;
    }
    const ql = q.toLowerCase();
    const matches = App.decisions.filter(d =>
      !d.decision_id?.startsWith('HIST-') && (
        (d.description    || '').toLowerCase().includes(ql) ||
        (d.decision_type  || '').toLowerCase().includes(ql) ||
        (d.primary_entity || '').toLowerCase().includes(ql) ||
        (d.decision_id    || '').toLowerCase().includes(ql)
      )
    );
    b.innerHTML = matches.length
      ? matches.map(d => {
          const mt = DT[d.decision_type] || { icon: '📌', label: d.decision_type };
          return `<div class="s-r-item" onclick="App.closeSearch(); App.openDecision('${d.decision_id}')">
            <div class="s-r-icon">${mt.icon}</div>
            <div>
              <div class="s-r-title">${esc((d.description || mt.label).substring(0, 60))}</div>
              <div class="s-r-sub">${d.decision_type} · ${esc(d.primary_entity || '—')} · ${(d.status || '').replace(/_/g,' ')}</div>
            </div>
            <div class="q-arr">›</div>
          </div>`;
        }).join('')
      : '<div style="padding:16px;text-align:center;color:var(--text3);font-size:.8rem">No results found</div>';
  },
};

// ── Keyboard Shortcuts ──────────────────────────────────────────
document.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); App.openSearch(); }
  if ((e.metaKey || e.ctrlKey) && '1234567'.includes(e.key)) {
    e.preventDefault();
    const pages = ['command','scenarios','missioncontrol','investigation','humanreview','metrics','catalog','unilog'];
    const t = pages[+e.key - 1];
    if (t) App.nav(t);
  }
  if (e.key === 'Escape') App.closeSearch();
  if (e.key === 'Enter' && document.activeElement === el('wn-inp')) HumanReviewPage.submitWhyNot();
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && App.page === 'humanreview') {
    e.preventDefault(); HumanReviewPage.decide('accept');
  }
});

// ── Platform Banner ─────────────────────────────────────────────
async function loadPlatformInfo() {
  try {
    const h = await getHealth();
    const verEl = el('platform-ver');
    if (verEl && h.version) verEl.textContent = h.version + ' · NBA Platform';
    if (h.platform) document.title = `Veridex · ${h.platform}`;
  } catch(e) { /* non-critical */ }
}

// ── Init ────────────────────────────────────────────────────────
(async () => {
  ScenariosPage.render();        // Pre-render scenario grid
  loadPlatformInfo();            // Update version from API
  await CommandPage.load();      // Load KPIs + queue
  // Auto-refresh command center every 30s
  setInterval(() => { if (App.page === 'command') CommandPage.load(); }, 30000);
})();
