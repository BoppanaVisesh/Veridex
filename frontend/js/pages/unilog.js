/**
 * Unilog Intelligence Page
 * Handles preview loading, sample dataset export, and custom file upload+export.
 */

const UnilogPage = (() => {
  let _uploadFile = null;

  // ── Init ────────────────────────────────────────────────────────────────────
  async function init() {
    await _checkMode();
    await loadPreview();
  }

  async function _checkMode() {
    try {
      const r = await fetch('/api/catalog/enrichment-mode');
      const d = await r.json();
      const badge = document.getElementById('ul-mode-badge');
      if (!badge) return;
      if (d.gemini_api_key_configured) {
        badge.textContent = '⚡ Gemini LLM Active';
        badge.style.background = '#F0FDF4'; badge.style.color = '#16A34A';
        badge.style.border = '1px solid #BBF7D0';
      } else {
        badge.textContent = '⚙ Deterministic Rules';
        badge.style.background = '#FFF7ED'; badge.style.color = '#D97706';
        badge.style.border = '1px solid #FDE68A';
      }
    } catch (e) { /* ignore */ }
  }

  // ── Preview ─────────────────────────────────────────────────────────────────
  async function loadPreview() {
    const loading = document.getElementById('ul-preview-loading');
    const wrap    = document.getElementById('ul-preview-wrap');
    const cards   = document.getElementById('ul-preview-cards');
    const modeBadge = document.getElementById('ul-preview-mode');

    if (loading) loading.style.display = 'block';
    if (wrap)    wrap.style.display    = 'none';

    try {
      const r = await fetch('/api/catalog/unilog-preview?limit=5');
      if (!r.ok) throw new Error(await r.text());
      const d = await r.json();

      // Update enrichment mode badge
      if (modeBadge) {
        modeBadge.textContent = d.gemini_configured ? 'Gemini LLM' : 'Deterministic Rules';
      }

      // Compute stats
      let totalAttrs = 0, classified = 0;
      d.rows.forEach(row => {
        totalAttrs += (row.attributes || []).length;
        if (row.Classpath && !row.Classpath.includes('Uncategorized')) classified++;
      });
      const avgAttrs = d.rows.length > 0 ? (totalAttrs / d.rows.length).toFixed(1) : '--';
      const classifiedPct = d.rows.length > 0
        ? Math.round((classified / d.rows.length) * 100) + '%' : '--';

      const attrEl = document.getElementById('ul-stat-attrs');
      const classEl = document.getElementById('ul-stat-classified');
      if (attrEl) attrEl.textContent = avgAttrs;
      if (classEl) classEl.textContent = classifiedPct;

      // Build preview cards
      if (!cards) return;
      cards.innerHTML = '';

      d.rows.forEach((row, idx) => {
        const conf = parseFloat(row._confidence || 0);
        const confColor = conf >= 0.85 ? '#10B981' : conf >= 0.65 ? '#F59E0B' : '#EF4444';
        const needsReview = row._needs_review === 'Yes';

        const attrHtml = (row.attributes || []).map(a =>
          `<span style="display:inline-flex;align-items:center;gap:4px;background:var(--bg-muted);
            border:1px solid var(--border);border-radius:4px;padding:2px 8px;font-size:.68rem;margin:2px">
            <span style="color:var(--text3)">${_esc(a.label)}:</span>
            <span style="font-weight:600">${_esc(a.value)}${a.uom ? ' ' + _esc(a.uom) : ''}</span>
          </span>`
        ).join('');

        const classpathParts = (row.Classpath || '').split('>');
        const classpathHtml = classpathParts.map((p, i) =>
          `<span style="color:${i === classpathParts.length-1 ? 'var(--blue)' : 'var(--text3)'}">
            ${i > 0 ? ' › ' : ''}${_esc(p)}
          </span>`
        ).join('');

        cards.insertAdjacentHTML('beforeend', `
          <div style="border:1px solid var(--border);border-radius:10px;padding:16px;
               background:var(--bg);position:relative;overflow:hidden">

            <!-- Confidence bar (left edge) -->
            <div style="position:absolute;left:0;top:0;bottom:0;width:4px;
                 background:${confColor};border-radius:10px 0 0 10px"></div>

            <div style="display:flex;align-items:flex-start;justify-content:space-between;
                 margin-bottom:10px;padding-left:8px">
              <div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:.72rem;
                     color:var(--text3);margin-bottom:2px">Row ${idx+1} · MPN: ${_esc(row.Mfg_Part_Num)}</div>
                <div style="font-size:.92rem;font-weight:700">${_esc(row.SHORT_DESC || row.Mfg_Part_Num)}</div>
              </div>
              <div style="display:flex;gap:6px;align-items:center;flex-shrink:0">
                ${needsReview ? `<span style="background:#FEF3C7;color:#92400E;border:1px solid #FDE68A;
                  border-radius:4px;padding:2px 8px;font-size:.65rem;font-weight:700">NEEDS REVIEW</span>` : ''}
                <span style="background:${confColor}22;color:${confColor};border:1px solid ${confColor}44;
                  border-radius:4px;padding:2px 8px;font-size:.68rem;font-weight:700">
                  ${Math.round(conf*100)}% confidence
                </span>
              </div>
            </div>

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;padding-left:8px;margin-bottom:12px">
              <div>
                <div style="font-size:.62rem;color:var(--text3);text-transform:uppercase;
                     letter-spacing:.06em;margin-bottom:3px">Manufacturer</div>
                <div style="font-size:.8rem;font-weight:600">${_esc(row.MANUFACTURER_NAME || '—')}</div>
              </div>
              <div>
                <div style="font-size:.62rem;color:var(--text3);text-transform:uppercase;
                     letter-spacing:.06em;margin-bottom:3px">Brand</div>
                <div style="font-size:.8rem;font-weight:600">${_esc(row.BRAND_NAME || '—')}</div>
              </div>
              <div>
                <div style="font-size:.62rem;color:var(--text3);text-transform:uppercase;
                     letter-spacing:.06em;margin-bottom:3px">INVOICE_DESC (≤40c)</div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:.75rem;
                     color:var(--blue)">${_esc(row.INVOICE_DESC || '—')}</div>
              </div>
              <div>
                <div style="font-size:.62rem;color:var(--text3);text-transform:uppercase;
                     letter-spacing:.06em;margin-bottom:3px">Enrichment Mode</div>
                <div style="font-size:.75rem;color:var(--text2)">${_esc(row._enrichment_mode || '—')}</div>
              </div>
            </div>

            <!-- Classpath breadcrumb -->
            <div style="padding-left:8px;margin-bottom:10px">
              <div style="font-size:.62rem;color:var(--text3);text-transform:uppercase;
                   letter-spacing:.06em;margin-bottom:3px">Classpath</div>
              <div style="font-size:.75rem">${classpathHtml || '—'}</div>
            </div>

            <!-- MOBILE_DESC -->
            <div style="padding-left:8px;margin-bottom:10px">
              <div style="font-size:.62rem;color:var(--text3);text-transform:uppercase;
                   letter-spacing:.06em;margin-bottom:3px">MOBILE_DESC</div>
              <div style="font-size:.78rem;color:var(--text2)">${_esc(row.MOBILE_DESC || '—')}</div>
            </div>

            <!-- LONG_DESC1 -->
            <div style="padding-left:8px;margin-bottom:12px">
              <div style="font-size:.62rem;color:var(--text3);text-transform:uppercase;
                   letter-spacing:.06em;margin-bottom:3px">LONG_DESC1</div>
              <div style="font-size:.76rem;color:var(--text2);line-height:1.5">
                ${_esc((row.LONG_DESC1 || '—').substring(0, 220))}${(row.LONG_DESC1||'').length > 220 ? '…' : ''}
              </div>
            </div>

            <!-- Extracted Attributes -->
            ${attrHtml ? `
              <div style="padding-left:8px">
                <div style="font-size:.62rem;color:var(--text3);text-transform:uppercase;
                     letter-spacing:.06em;margin-bottom:5px">Extracted Attributes</div>
                <div style="display:flex;flex-wrap:wrap;gap:3px">${attrHtml}</div>
              </div>` : ''}
          </div>
        `);
      });

      if (loading) loading.style.display = 'none';
      if (wrap)    wrap.style.display    = 'block';

    } catch (e) {
      if (loading) loading.innerHTML =
        `<div style="color:var(--red);padding:20px">Error loading preview: ${_esc(String(e))}</div>`;
    }
  }

  // ── Download Sample ─────────────────────────────────────────────────────────
  async function downloadSample() {
    const btn   = document.getElementById('ul-sample-btn');
    const limit = document.getElementById('ul-sample-limit')?.value || 100;
    const fmt   = document.getElementById('ul-sample-fmt')?.value  || 'xlsx';
    const status = document.getElementById('ul-export-status');

    _setStatus(status, 'info', `Processing ${limit} rows...`);
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Processing...'; }

    try {
      const url = `/api/catalog/unilog-sample-export?limit=${limit}&fmt=${fmt}`;
      const r = await fetch(url);
      if (!r.ok) throw new Error(await r.text());

      const blob = await r.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `unilog_enriched_${limit}rows.${fmt}`;
      a.click();
      URL.revokeObjectURL(a.href);

      _setStatus(status, 'success',
        `Downloaded ${limit} enriched rows as .${fmt.toUpperCase()} (252 columns)`);
    } catch (e) {
      _setStatus(status, 'error', 'Export failed: ' + e.message);
    } finally {
      if (btn) { btn.disabled = false; btn.innerHTML = '&#11015; Download'; }
    }
  }

  // ── Upload & Export Custom File ─────────────────────────────────────────────
  function onFileSelect(input) {
    _uploadFile = input.files[0] || null;
    const info = document.getElementById('ul-upload-info');
    if (!info) return;
    if (_uploadFile) {
      info.style.display = 'block';
      info.textContent = `${_uploadFile.name} (${(_uploadFile.size/1024).toFixed(1)} KB)`;
    } else {
      info.style.display = 'none';
    }
  }

  async function uploadAndExport() {
    const btn    = document.getElementById('ul-upload-btn');
    const fmt    = document.getElementById('ul-upload-fmt')?.value || 'xlsx';
    const status = document.getElementById('ul-export-status');

    if (!_uploadFile) {
      _setStatus(status, 'error', 'Please select a file first.');
      return;
    }

    _setStatus(status, 'info', `Uploading and enriching ${_uploadFile.name}...`);
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Processing...'; }

    try {
      const fd = new FormData();
      fd.append('file', _uploadFile, _uploadFile.name);
      fd.append('fmt', fmt);

      const r = await fetch('/api/catalog/unilog-export', {
        method: 'POST',
        body: fd,
      });
      if (!r.ok) throw new Error(await r.text());

      const blob = await r.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `enriched_output.${fmt}`;
      a.click();
      URL.revokeObjectURL(a.href);

      _setStatus(status, 'success', `Enriched output downloaded as .${fmt.toUpperCase()} (252 columns)`);
    } catch (e) {
      _setStatus(status, 'error', 'Upload failed: ' + e.message);
    } finally {
      if (btn) { btn.disabled = false; btn.innerHTML = '&#11015; Process &amp; Download'; }
    }
  }

  // ── Helpers ─────────────────────────────────────────────────────────────────
  function _setStatus(el, type, msg) {
    if (!el) return;
    const styles = {
      info:    { bg: '#EFF6FF', color: '#1D4ED8', border: '#BFDBFE' },
      success: { bg: '#F0FDF4', color: '#15803D', border: '#BBF7D0' },
      error:   { bg: '#FEF2F2', color: '#DC2626', border: '#FECACA' },
    };
    const s = styles[type] || styles.info;
    el.style.display     = 'block';
    el.style.background  = s.bg;
    el.style.color       = s.color;
    el.style.border      = `1px solid ${s.border}`;
    el.style.borderRadius = '6px';
    el.textContent = msg;
  }

  function _esc(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  return { init, loadPreview, downloadSample, onFileSelect, uploadAndExport };
})();
