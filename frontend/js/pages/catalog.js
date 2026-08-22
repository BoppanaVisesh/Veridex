// ======================== pages/catalog.js ========================
// Page 07: Catalog Intelligence — Ingestion, Validation, 3-Tier Enrichment & Evidence Tracking

const CatalogPage = {
  _currentProductId: null,
  _activeSse: null,
  _selectedSingleFile: null,
  _selectedBatchFiles: [],

  async load() {
    try {
      const [dash, products, enrMode] = await Promise.all([
        get('/catalog/dashboard').catch(() => ({})),
        get('/catalog/products').catch(() => []),
        get('/catalog/enrichment-mode').catch(() => ({ enrichment_mode: 'deterministic_fallback' })),
      ]);
      this.renderDashboard(dash);
      this.renderProductsList(products);
      this.renderEnrichmentMode(enrMode);
    } catch(e) {
      console.error('Catalog load error', e);
    }
  },

  // ── Dashboard Metrics & Health ─────────────────────────────────────────────

  renderDashboard(dash) {
    if (!dash) return;

    const totalProd = dash.total_products ?? 0;
    const totalFields = dash.total_fields ?? 0;
    const valPct = dash.validation_coverage_pct ?? dash.fields_validated_pct ?? 0;
    const valCount = (dash.fields_verified ?? 0) + (dash.fields_validated ?? 0);
    const llmPct = dash.fields_llm_enriched_pct ?? dash.fields_enriched_pct ?? 0;
    const llmCount = dash.fields_llm_enriched ?? dash.fields_enriched ?? 0;
    const rulePct = dash.fields_rule_inferred_pct ?? 0;
    const ruleCount = dash.fields_rule_inferred ?? 0;
    const flagged = dash.fields_flagged_count ?? 0;
    const conflicted = dash.fields_conflicted_count ?? 0;
    const review = dash.products_needing_review_count ?? dash.fields_needs_review_count ?? 0;
    const reviewFields = dash.fields_needs_review_count ?? (flagged + conflicted);

    // Row 1: KPI Cards (6 Tiles)
    if (el('cat-kpi-products')) el('cat-kpi-products').textContent = totalProd;
    if (el('cat-kpi-fields')) el('cat-kpi-fields').textContent = totalFields;
    if (el('cat-kpi-val-pct')) el('cat-kpi-val-pct').textContent = valPct + '%';
    if (el('cat-kpi-val-sub')) el('cat-kpi-val-sub').textContent = `${valCount} source validated`;
    if (el('cat-kpi-llm-pct')) el('cat-kpi-llm-pct').textContent = llmPct + '%';
    if (el('cat-kpi-llm-sub')) el('cat-kpi-llm-sub').textContent = `${llmCount} LLM inferred`;
    if (el('cat-kpi-rule-pct')) el('cat-kpi-rule-pct').textContent = rulePct + '%';
    if (el('cat-kpi-rule-sub')) el('cat-kpi-rule-sub').textContent = `${ruleCount} rule fallback`;
    if (el('cat-kpi-review')) el('cat-kpi-review').textContent = review;
    if (el('cat-kpi-review-sub')) el('cat-kpi-review-sub').textContent = `${reviewFields} unverified / flags`;

    // Catalog Health Bars
    if (el('cat-h-val-pct')) el('cat-h-val-pct').textContent = valPct + '%';
    if (el('cat-h-val-bar')) el('cat-h-val-bar').style.width = Math.min(100, Math.max(0, valPct)) + '%';
    if (el('cat-h-llm-pct')) el('cat-h-llm-pct').textContent = llmPct + '%';
    if (el('cat-h-llm-bar')) el('cat-h-llm-bar').style.width = Math.min(100, Math.max(0, llmPct)) + '%';
    if (el('cat-h-rule-pct')) el('cat-h-rule-pct').textContent = rulePct + '%';
    if (el('cat-h-rule-bar')) el('cat-h-rule-bar').style.width = Math.min(100, Math.max(0, rulePct)) + '%';
    if (el('cat-h-flagged')) el('cat-h-flagged').textContent = flagged;
    if (el('cat-h-conflicted')) el('cat-h-conflicted').textContent = conflicted;
    if (el('cat-h-review')) el('cat-h-review').textContent = review;

    const healthBadge = el('cat-health-badge');
    if (healthBadge) {
      if (flagged > 0 || conflicted > 0 || review > 0) {
        healthBadge.textContent = 'Attention Needed';
        healthBadge.className = 'chip c-amber';
      } else {
        healthBadge.textContent = 'Nominal';
        healthBadge.className = 'chip c-green';
      }
    }

    // Pipeline Stages (6 stages)
    const pipe = dash.pipeline_stages || {};
    if (el('cat-pipe-ingest')) el('cat-pipe-ingest').textContent = pipe.ingest ?? totalProd;
    if (el('cat-pipe-clean')) el('cat-pipe-clean').textContent = pipe.clean ?? totalFields;
    if (el('cat-pipe-validate')) el('cat-pipe-validate').textContent = pipe.validate ?? (valCount + flagged + conflicted);
    if (el('cat-pipe-enrich')) el('cat-pipe-enrich').textContent = pipe.enrich ?? (llmCount + ruleCount);
    if (el('cat-pipe-verify')) el('cat-pipe-verify').textContent = pipe.verify ?? valCount;
    if (el('cat-pipe-explain')) el('cat-pipe-explain').textContent = pipe.explain ?? totalFields;
  },

  renderEnrichmentMode(info) {
    const lbl = el('cat-enr-mode-lbl');
    if (!lbl) return;
    if (info.enrichment_mode === 'LLM') {
      lbl.textContent = 'LLM (Gemini Active)';
      lbl.style.color = 'var(--purple)';
    } else {
      lbl.textContent = 'Deterministic Rule Engine';
      lbl.style.color = 'var(--amber)';
    }
  },

  // ── Products List ─────────────────────────────────────────────────────────

  renderProductsList(products) {
    const tbody = el('cat-products-tbody');
    const badge = el('cat-prod-count-badge');
    if (badge) badge.textContent = `${products.length} product${products.length === 1 ? '' : 's'}`;
    if (!tbody) return;

    if (!products || !products.length) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:36px;color:var(--text3)">
        <div style="font-size:1.8rem;margin-bottom:8px">📦</div>
        <div style="font-weight:600;font-size:.88rem;color:var(--text2)">No products in catalog database</div>
        <div style="font-size:.74rem;color:var(--text3);margin-top:4px">Upload a single file or batch to start the ingestion pipeline.</div>
      </td></tr>`;
      return;
    }

    tbody.innerHTML = products.map(p => {
      const statusCls = p.status === 'ready' ? 'c-green'
        : p.status === 'needs_review' ? 'c-red'
        : p.status === 'validating' || p.status === 'enriching' ? 'c-amber'
        : 'c-blue';

      const fmt = (p.raw_source_type || 'manual').toUpperCase();
      const hashShort = p.canonical_hash ? p.canonical_hash.substring(0, 8) : '—';

      return `<tr style="border-bottom:1px solid var(--border);transition:background .12s;cursor:pointer" onclick="CatalogPage.openProduct('${p.id}')">
        <td style="padding:12px 16px">
          <div style="font-weight:700;color:var(--text)">${esc(p.name)}</div>
          <div style="font-size:.68rem;color:var(--text3);font-family:'JetBrains Mono',monospace;margin-top:2px">ID: ${p.id.substring(0, 8)} · Hash: ${hashShort}</div>
        </td>
        <td style="padding:12px 8px">
          <span class="chip c-gray" style="font-family:'JetBrains Mono',monospace">${fmt}</span>
        </td>
        <td style="padding:12px 8px;font-family:'JetBrains Mono',monospace;font-weight:600">
          <span class="chip c-blue" id="cat-prod-fcount-${p.id}">Inspect ›</span>
        </td>
        <td style="padding:12px 8px">
          <span class="chip c-green">Source-Backed</span>
        </td>
        <td style="padding:12px 8px">
          <span class="chip c-purple">3-Tier</span>
        </td>
        <td style="padding:12px 8px">
          <span class="chip ${statusCls}">${(p.status || 'ingested').toUpperCase()}</span>
        </td>
        <td style="padding:12px 16px;text-align:right" onclick="event.stopPropagation()">
          <div style="display:flex;gap:6px;justify-content:flex-end">
            <button class="btn btn-outline btn-sm" onclick="CatalogPage.openProduct('${p.id}')">View</button>
            <button class="btn btn-primary btn-sm" onclick="CatalogPage.quickValidate('${p.id}')">✓</button>
          </div>
        </td>
      </tr>`;
    }).join('');
  },

  // ── Product Details View ──────────────────────────────────────────────────

  async openProduct(id) {
    this._currentProductId = id;
    try {
      const p = await get('/catalog/products/' + id);
      this.renderProductDetail(p);
    } catch(e) {
      showToast('Error loading product details: ' + e.message, 'error');
    }
  },

  renderProductDetail(p) {
    const detailPanel = el('cat-product-detail');
    if (!detailPanel) return;

    detailPanel.style.display = 'block';
    el('cat-detail-title').textContent = p.name;
    const hashInfo = p.canonical_hash ? ` · Canonical Hash: ${p.canonical_hash.substring(0, 12)}...` : '';
    el('cat-detail-id').textContent = `Product ID: ${p.id} · Source: ${(p.raw_source_type || 'csv').toUpperCase()}${hashInfo}`;

    const resBox = el('cat-detail-result');
    if (resBox) resBox.style.display = 'none';

    const fields = p.fields || [];
    const fieldsBody = el('cat-fields-table-body');

    if (!fields.length) {
      fieldsBody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--text3);padding:24px">No fields extracted yet.</td></tr>`;
      return;
    }

    fieldsBody.innerHTML = fields.map(f => {
      const confVal = f.confidence;
      const confPct = confVal != null ? Math.round(confVal * 100) + '%' : '—';
      const st = (f.status || 'raw').toLowerCase();
      const method = f.enrichment_method || (st === 'validated' ? 'source_data' : 'unknown');
      const isVer = f.is_verified || st === 'verified';

      // Status chip
      let stChip = '<span class="chip c-gray">RAW</span>';
      if (st === 'verified' || isVer) {
        stChip = '<span class="chip c-green">✓ VERIFIED</span>';
      } else if (st === 'validated') {
        stChip = '<span class="chip c-green">✓ VALIDATED</span>';
      } else if (st === 'conflicted') {
        stChip = '<span class="chip c-red">⚠ CONFLICTED</span>';
      } else if (st === 'flagged') {
        stChip = '<span class="chip c-red">🚩 FLAGGED</span>';
      } else if (st === 'needs_review' || f.value === 'Unknown') {
        stChip = '<span class="chip c-red">🔍 NEEDS REVIEW</span>';
      } else if (method === 'llm') {
        stChip = '<span class="chip c-purple">🤖 LLM INFERRED</span>';
      } else if (method === 'deterministic_fallback') {
        stChip = '<span class="chip c-amber">🔧 RULE INFERRED</span>';
      } else if (st === 'enriched') {
        stChip = '<span class="chip c-purple">💡 ENRICHED</span>';
      }

      // Method badge
      let methodBadge = '<span class="chip c-gray">Source Ingestion</span>';
      if (method === 'source_data') {
        methodBadge = '<span style="background:#ECFDF5;color:#059669;border:1px solid #A7F3D0;border-radius:4px;font-size:.63rem;font-weight:700;padding:2px 6px">📄 Source Data</span>';
      } else if (method === 'llm') {
        methodBadge = '<span style="background:#F3F0FF;color:#7C3AED;border:1px solid #DDD6FE;border-radius:4px;font-size:.63rem;font-weight:700;padding:2px 6px">🤖 Gemini LLM</span>';
      } else if (method === 'deterministic_fallback') {
        methodBadge = '<span style="background:#FFFBEB;color:#D97706;border:1px solid #FDE68A;border-radius:4px;font-size:.63rem;font-weight:700;padding:2px 6px">🔧 Rule Fallback</span>';
      } else if (method === 'no_evidence' || f.value === 'Unknown') {
        methodBadge = '<span style="background:#FEF2F2;color:#DC2626;border:1px solid #FECACA;border-radius:4px;font-size:.63rem;font-weight:700;padding:2px 6px">⚠️ No Evidence</span>';
      }

      // Value display
      const isUnknown = f.value === 'Unknown' || f.value == null;
      const valDisplay = !isUnknown 
        ? `<strong style="color:var(--text)">${esc(f.value)}</strong>` 
        : `<span style="color:var(--red);font-style:italic;font-weight:600">Unknown (No reliable evidence)</span>`;
      const unitDisplay = f.unit ? `<span class="chip c-dark" style="margin-left:4px">${esc(f.unit)}</span>` : '';

      // Reason / Source hint
      const reasonText = f.reasoning || f.validation_reason || (f.source_fields ? `Context: ${f.source_fields}` : 'Ingested from source document');
      const reasonColor = (st === 'flagged' || st === 'conflicted' || st === 'needs_review' || isUnknown) ? 'var(--red)' : 'var(--text3)';

      // Confidence color
      const confCol = confVal >= 0.85 ? 'var(--green)' : (confVal >= 0.55 ? 'var(--amber)' : 'var(--red)');

      return `<tr style="border-bottom:1px solid var(--border)">
        <td style="padding:10px 16px;font-weight:700;font-family:'JetBrains Mono',monospace;color:var(--text)">
          ${esc(f.field_name)}
        </td>
        <td style="padding:10px 8px">
          <div>${valDisplay} ${unitDisplay}</div>
        </td>
        <td style="padding:10px 8px">${stChip}</td>
        <td style="padding:10px 8px;font-family:'JetBrains Mono',monospace;font-weight:700;color:${confCol}">${confPct}</td>
        <td style="padding:10px 8px">${methodBadge}</td>
        <td style="padding:10px 8px;font-size:.71rem;color:${reasonColor};max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(reasonText)}">
          ${esc(reasonText)}
        </td>
        <td style="padding:10px 16px;text-align:right">
          <button class="btn btn-outline btn-sm" style="font-size:.7rem;padding:3px 9px" onclick="CatalogPage.explainField('${p.id}', '${f.field_name}')">
            🔍 Explain
          </button>
        </td>
      </tr>`;
    }).join('');

    detailPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  },

  async quickValidate(productId) {
    try {
      showToast('Validating product...', 'default');
      const r = await post(`/catalog/products/${productId}/validate`);
      showToast(`Validated: ${r.validated_count} passed, ${r.flagged_count} flagged.`, 'success');
      await this.load();
      if (this._currentProductId === productId) {
        await this.openProduct(productId);
      }
    } catch(e) {
      showToast('Validation failed: ' + e.message, 'error');
    }
  },

  async validateCurrentProduct() {
    if (!this._currentProductId) return;
    try {
      showToast('Running comprehensive field validation...', 'default');
      const r = await post(`/catalog/products/${this._currentProductId}/validate`);
      const resBox = el('cat-detail-result');
      if (resBox) {
        resBox.style.display = 'block';
        resBox.style.background = r.flagged_count > 0 ? 'var(--amber-bg)' : 'var(--green-bg)';
        resBox.style.color = r.flagged_count > 0 ? 'var(--amber)' : 'var(--green)';
        resBox.innerHTML = `<strong>Validation Complete:</strong> ${r.validated_count} validated, ${r.flagged_count} flagged, ${r.conflicted_count} conflicted.`;
      }
      showToast(`Validation pass complete.`, 'success');
      await this.openProduct(this._currentProductId);
      await this.load();
    } catch(e) {
      showToast('Error validating product: ' + e.message, 'error');
    }
  },

  async enrichCurrentProduct() {
    if (!this._currentProductId) return;
    try {
      showToast('Running 3-tier evidence-based enrichment...', 'default');
      const r = await post(`/catalog/products/${this._currentProductId}/enrich`);
      const resBox = el('cat-detail-result');
      if (resBox) {
        resBox.style.display = 'block';
        resBox.style.background = 'var(--purple-bg)';
        resBox.style.color = 'var(--purple)';
        resBox.innerHTML = `<strong>Enrichment Engine (${r.enrichment_mode}):</strong> Inferred ${r.enriched_count} attribute(s) with evidence provenance.`;
      }
      showToast(`Enrichment complete: ${r.enriched_count} field(s) processed (${r.enrichment_mode}).`, 'success');
      await this.openProduct(this._currentProductId);
      await this.load();
    } catch(e) {
      showToast('Error enriching product: ' + e.message, 'error');
    }
  },

  // ── Explanation Modal ─────────────────────────────────────────────────────

  async explainField(productId, fieldName) {
    try {
      const exp = await get(`/catalog/products/${productId}/explain/${fieldName}`);
      this.showExplanationModal(exp);
    } catch(e) {
      showToast('Error fetching explanation: ' + e.message, 'error');
    }
  },

  showExplanationModal(exp) {
    const modal = el('cat-exp-modal');
    if (!modal) return;

    el('cat-exp-title').textContent = `Audit Trail & Evidence Provenance · ${exp.field_name}`;
    el('cat-exp-body').innerHTML = `
      <div style="background:#0F172A;color:#E2E8F0;padding:18px;border-radius:8px;font-size:.82rem;line-height:1.7">
        ${this.formatMarkdown(exp.explanation)}
      </div>`;
    modal.classList.add('open');
  },

  closeExplanationModal() {
    el('cat-exp-modal')?.classList.remove('open');
  },

  formatMarkdown(txt) {
    if (!txt) return '';
    return txt
      .replace(/^##\s*(.*$)/gim, '<h3 style="color:#60A5FA;font-size:1rem;margin-top:14px;margin-bottom:6px">$1</h3>')
      .replace(/^###\s*(.*$)/gim, '<h4 style="color:#93C5FD;font-size:.88rem;margin-top:12px;margin-bottom:4px">$1</h4>')
      .replace(/^>\s*(.*$)/gim, '<blockquote style="border-left:3px solid #38BDF8;background:rgba(56,189,248,0.08);padding:8px 12px;border-radius:4px;color:#BAE6FD;margin:8px 0">$1</blockquote>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong style="color:#FFFFFF">$1</strong>')
      .replace(/`([^`]+)`/g, '<code style="background:#1E293B;color:#38BDF8;padding:2px 6px;border-radius:4px;font-family:\'JetBrains Mono\',monospace">$1</code>')
      .replace(/^•\s*(.*$)/gim, '<li style="margin-left:16px;list-style:disc">$1</li>')
      .replace(/\n/g, '<br>');
  },

  // ── Single File Upload ────────────────────────────────────────────────────

  onSingleFileSelect(input) {
    if (!input.files || !input.files.length) return;
    const file = input.files[0];
    this._selectedSingleFile = file;

    const infoBox = el('cat-single-file-info');
    const fnameEl = el('cat-single-fname');
    const fsizeEl = el('cat-single-fsize');
    const dropBox = el('cat-single-drop');

    if (infoBox && fnameEl && fsizeEl) {
      fnameEl.textContent = file.name;
      fsizeEl.textContent = `${(file.size / 1024).toFixed(1)} KB · ${file.type || 'Catalog Document'}`;
      infoBox.style.display = 'block';
      if (dropBox) dropBox.style.borderColor = 'var(--accent)';
    }
  },

  clearSingleFile() {
    this._selectedSingleFile = null;
    const fileInp = el('cat-single-file');
    if (fileInp) fileInp.value = '';
    const infoBox = el('cat-single-file-info');
    if (infoBox) infoBox.style.display = 'none';
    const dropBox = el('cat-single-drop');
    if (dropBox) dropBox.style.borderColor = 'var(--border)';
    const resBox = el('cat-single-result');
    if (resBox) resBox.style.display = 'none';
  },

  async uploadSingleFile() {
    const fileInp = el('cat-single-file');
    const nameInp = el('cat-single-name');
    const file = this._selectedSingleFile || (fileInp && fileInp.files ? fileInp.files[0] : null);

    if (!file) {
      showToast('Please select a catalog file to upload.', 'error');
      return;
    }

    const formData = new FormData();
    formData.append('file', file);
    if (nameInp && nameInp.value.trim()) {
      formData.append('product_name', nameInp.value.trim());
    }

    const btn = el('cat-single-submit');
    if (btn) { btn.disabled = true; btn.textContent = 'Processing Ingestion...'; }

    try {
      showToast('Uploading and running ingestion pipeline...', 'default');
      const res = await fetch(`${API}/catalog/upload`, {
        method: 'POST',
        body: formData
      });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText);
      }
      const data = await res.json();

      const resBox = el('cat-single-result');
      if (resBox) {
        resBox.style.display = 'block';
        if (data.duplicate_products > 0 && data.created_products === 0) {
          resBox.style.background = 'var(--amber-bg)';
          resBox.style.color = 'var(--amber)';
          resBox.innerHTML = `<strong>Duplicate Detected:</strong> Product already exists in catalog. Identity hash matched existing record. Timestamp refreshed.`;
          showToast(`Duplicate skipped: product already exists in database.`, 'default');
        } else {
          resBox.style.background = 'var(--green-bg)';
          resBox.style.color = 'var(--green)';
          resBox.innerHTML = `<strong>Success:</strong> Ingested ${data.created_products} new product(s). ${data.duplicate_products} duplicate(s) skipped.`;
          showToast(`Ingested ${data.created_products} new product(s)!`, 'success');
        }
      }

      await this.load();
    } catch(e) {
      showToast('Upload error: ' + e.message, 'error');
      const resBox = el('cat-single-result');
      if (resBox) {
        resBox.style.display = 'block';
        resBox.style.background = 'var(--red-bg)';
        resBox.style.color = 'var(--red)';
        resBox.textContent = `Upload failed: ${e.message}`;
      }
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Upload & Run Pipeline'; }
    }
  },

  // ── Batch Files Upload ────────────────────────────────────────────────────

  onBatchFilesSelect(input) {
    if (!input.files || !input.files.length) return;
    this._selectedBatchFiles = Array.from(input.files);

    const infoBox = el('cat-batch-file-info');
    const countLbl = el('cat-batch-count-lbl');
    const listEl = el('cat-batch-file-list');
    const dropBox = el('cat-batch-drop');

    if (infoBox && countLbl && listEl) {
      countLbl.textContent = `${this._selectedBatchFiles.length} file(s) selected`;
      listEl.innerHTML = this._selectedBatchFiles.map(f =>
        `<div>• <strong>${esc(f.name)}</strong> (${(f.size / 1024).toFixed(1)} KB)</div>`
      ).join('');
      infoBox.style.display = 'block';
      if (dropBox) dropBox.style.borderColor = 'var(--purple)';
    }
  },

  clearBatchFiles() {
    this._selectedBatchFiles = [];
    const fileInp = el('cat-batch-file');
    if (fileInp) fileInp.value = '';
    const infoBox = el('cat-batch-file-info');
    if (infoBox) infoBox.style.display = 'none';
    const dropBox = el('cat-batch-drop');
    if (dropBox) dropBox.style.borderColor = 'var(--border)';
  },

  async uploadBatchFiles() {
    const fileInp = el('cat-batch-file');
    const files = this._selectedBatchFiles.length > 0 ? this._selectedBatchFiles
      : (fileInp && fileInp.files ? Array.from(fileInp.files) : []);

    if (!files.length) {
      showToast('Please select one or more catalog files for batch processing.', 'error');
      return;
    }

    const formData = new FormData();
    for (const f of files) {
      formData.append('files', f);
    }

    const btn = el('cat-batch-submit');
    if (btn) { btn.disabled = true; btn.textContent = 'Initializing Batch Job...'; }

    try {
      showToast(`Starting batch job for ${files.length} file(s)...`, 'default');
      const res = await fetch(`${API}/catalog/batch-upload`, {
        method: 'POST',
        body: formData
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();

      showToast(`Batch job #${data.job_id.substring(0, 8)} started!`, 'success');
      this.startSseProgressStream(data.job_id);
    } catch(e) {
      showToast('Batch upload error: ' + e.message, 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '⚡ Start Batch Pipeline'; }
    }
  },

  startSseProgressStream(jobId) {
    const feedBox = el('cat-job-feed');
    const progBar = el('cat-job-bar');
    const jobBox = el('cat-job-box');
    const createdEl = el('cat-job-created');
    const dupesEl = el('cat-job-dupes');
    const failedEl = el('cat-job-failed');

    if (jobBox) jobBox.style.display = 'block';
    if (feedBox) feedBox.innerHTML = `<div style="color:#A5B4FC">[${new Date().toLocaleTimeString()}] Connected to batch stream #${jobId.substring(0, 8)}...</div>`;
    if (progBar) progBar.style.width = '0%';
    if (createdEl) createdEl.textContent = '0';
    if (dupesEl) dupesEl.textContent = '0';
    if (failedEl) failedEl.textContent = '0';

    if (this._activeSse) this._activeSse.close();

    const sseUrl = `${API}/catalog/jobs/${jobId}/stream`;
    const evtSource = new EventSource(sseUrl);
    this._activeSse = evtSource;

    evtSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.message && feedBox) {
          const row = document.createElement('div');
          row.style.lineHeight = '1.7';
          if (data.message.includes('DUPLICATE')) {
            row.style.color = '#FCA5A5';
          } else if (data.message.includes('validated')) {
            row.style.color = '#6EE7B7';
          } else if (data.message.includes('Failed') || data.message.includes('error')) {
            row.style.color = '#F87171';
          } else {
            row.style.color = '#CBD5E1';
          }
          row.textContent = data.message;
          feedBox.appendChild(row);
          feedBox.scrollTop = feedBox.scrollHeight;
        }

        if (data.percent != null && progBar) {
          progBar.style.width = `${data.percent}%`;
        }

        if (data.done) {
          evtSource.close();
          this._activeSse = null;
          if (createdEl) createdEl.textContent = data.created_products ?? 0;
          if (dupesEl) dupesEl.textContent = data.duplicate_products ?? 0;
          if (failedEl) failedEl.textContent = data.failed_products ?? 0;
          showToast(`✓ Batch processing completed! (${data.created_products || 0} created, ${data.duplicate_products || 0} duplicates skipped)`, 'success');
          this.load();
        }
      } catch(err) { console.error('SSE parse error', err); }
    };

    evtSource.onerror = (err) => {
      console.warn('SSE stream ended or disconnected.', err);
      evtSource.close();
      this._activeSse = null;
      this.load();
    };
  },

  // ── Intelligence Verification ─────────────────────────────────────────────

  async runPipelineCheck() {
    const btn = el('cat-pipeline-check-btn');
    const resultBox = el('cat-pipeline-result');
    const badge = el('cat-pipeline-badge');
    const stagesEl = el('cat-pipeline-stages');

    if (btn) { btn.disabled = true; btn.textContent = 'Running Smoke Test...'; }
    if (resultBox) resultBox.style.display = 'block';
    if (stagesEl) stagesEl.innerHTML = '<div>Initiating end-to-end smoke test across all 6 pipeline stages...</div>';

    try {
      const res = await post('/catalog/pipeline-check');
      if (badge) {
        badge.textContent = res.result || 'PASS';
        badge.className = res.result === 'PASS' ? 'chip c-green' : 'chip c-red';
      }

      if (stagesEl && res.stages) {
        const rows = Object.entries(res.stages).map(([stage, info]) => {
          const icon = info.status === 'pass' ? '✓' : (info.status === 'warn' ? '⚠' : '✗');
          const col = info.status === 'pass' ? '#16A34A' : (info.status === 'warn' ? '#D97706' : '#DC2626');
          return `<div><span style="color:${col};font-weight:700">${icon} [${stage.toUpperCase()}]</span>: ${esc(info.detail || info.status)}</div>`;
        });
        stagesEl.innerHTML = rows.join('') + `<div style="margin-top:8px;color:var(--text3);font-size:.68rem">Enrichment Engine Mode: <strong>${res.enrichment_mode || 'deterministic_fallback'}</strong> · Timestamp: ${res.timestamp || ''}</div>`;
      }
      showToast(`Pipeline Check: ${res.result}`, res.result === 'PASS' ? 'success' : 'error');
    } catch(e) {
      showToast('Pipeline check failed: ' + e.message, 'error');
      if (stagesEl) stagesEl.innerHTML = `<div style="color:var(--red)">Failed to complete pipeline check: ${esc(e.message)}</div>`;
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '▶ Run Pipeline Check'; }
    }
  },

  // ── Safe Clear Demo Data ──────────────────────────────────────────────────

  async clearDemoData() {
    const ok = confirm('Clear all catalog demo data? (Products, fields, and evidence will be removed. Core decision logs will NOT be touched.)');
    if (!ok) return;

    try {
      showToast('Clearing catalog data...', 'default');
      const formData = new FormData();
      formData.append('confirmed', 'true');

      const res = await fetch(`${API}/catalog/clear-demo-data`, {
        method: 'POST',
        body: formData
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();

      showToast(`Catalog reset: ${data.products_removed} products removed.`, 'success');
      const detail = el('cat-product-detail');
      if (detail) detail.style.display = 'none';
      await this.load();
    } catch(e) {
      showToast('Clear error: ' + e.message, 'error');
    }
  }
};
