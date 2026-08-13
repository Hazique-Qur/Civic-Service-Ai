/* =====================================================================
   admin.js — Executive Admin Command Logic
   Chart.js dark neon visualizations, filterable complaints table,
   detail modal popup, department dispatch, statistics metrics.
   ===================================================================== */

const API = '';
const PAGE_SIZE = 15;

let allComplaints  = [];
let filteredList   = [];
let currentPage    = 0;
let metaData       = {};
let activeComplaintId = null;
let authToken      = getAuthToken();

// ── Auth Handling ─────────────────────────────────────────────────────

async function initAdminAuth() {
  if (!authToken) {
    const user = await syncAuthFromSession();
    if (user) authToken = getAuthToken();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initAdminAuth();
});

// ── Purge Database ────────────────────────────────────────────────────
document.getElementById('reset-db-btn').addEventListener('click', async () => {
  if (!confirm('WARNING: This will permanently delete ALL civic complaints in the database. Proceed?')) return;
  try {
    const res = await fetch(`${API}/api/admin/reset-db`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    if (res.ok) {
      showToast('Database successfully purged!', 'success');
      loadComplaints();
      loadStatistics();
    } else {
      showToast('Failed to purge database. Unauthorized.', 'error');
    }
  } catch(e) {
    showToast('Network error during database purge.', 'error');
  }
});

// ── Export CSV ────────────────────────────────────────────────────────
document.getElementById('export-csv-btn').addEventListener('click', async () => {
  const btn = document.getElementById('export-csv-btn');
  btn.disabled = true;
  btn.innerHTML = '<span>⏳</span> Exporting...';
  try {
    const res = await fetch(`${API}/api/complaints/export/csv`, {
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    if (!res.ok) throw new Error('Unauthorized or server error');
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `civic_complaints_${new Date().toISOString().slice(0,10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    showToast('CSV exported successfully!', 'success');
  } catch(e) {
    showToast('Export failed. Make sure you are logged in as admin.', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span>📥</span> Export CSV';
  }
});


// Chart instances
let chartCategory = null;
let chartPriority = null;
let chartStatus   = null;
let chartTrend    = null;
let chartLocations = null;

// ── Utility ───────────────────────────────────────────────────────────

function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  const icons = { success: '✅', error: '❌', info: 'ℹ️' };
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span>${icons[type]}</span> ${message}`;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

function getPriorityClass(p) {
  return { Critical:'critical', High:'high', Medium:'medium', Low:'low' }[p] || 'medium';
}
function getStatusClass(s) {
  return { Open:'open', Assigned:'assigned', 'In Progress':'in-progress', Resolved:'resolved', Successful:'resolved' }[s] || 'open';
}
function getCategoryEmoji(c) {
  const m = {
    'Water/Drainage':'💧','Roads/Pavements':'🛣️','Waste/Sanitation':'🗑️',
    'Electricity':'⚡','Parks/Green Spaces':'🌳','Noise/Disturbance':'🔊',
    'Public Safety':'🚨','Other':'📋'
  };
  return m[c] || '📋';
}
function getPriorityColor(p) {
  return { Critical:'#f43f5e', High:'#fb923c', Medium:'#facc15', Low:'#10b981' }[p] || '#94a3b8';
}
function timeAgo(iso) {
  const diff = Date.now() - new Date(iso + 'Z').getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1)  return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)  return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}
function escapeHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function formatHours(h) {
  if (h === null || h === undefined) return '—';
  if (h < 1) return `${Math.round(h * 60)}m`;
  if (h < 24) return `${h}h`;
  return `${(h / 24).toFixed(1)}d`;
}

// ── Fetch metadata & dropdowns ─────────────────────────────────────────

async function initMeta() {
  try {
    const res = await fetch(`${API}/api/meta`);
    metaData = (await res.json());

    // AI status badge
    const badge = document.getElementById('ai-status-badge');
    if (metaData.ai_active) {
      badge.className = 'badge badge-low';
      badge.textContent = '🤖 Gemini 2.0 AI Active';
    } else {
      badge.className = 'badge badge-medium';
      badge.textContent = '⚙️ Keyword Fallback Active';
    }

    // Category filter dropdown
    const catFilter = document.getElementById('filter-category');
    metaData.categories.forEach(cat => {
      const opt = document.createElement('option');
      opt.value = cat; opt.textContent = `${getCategoryEmoji(cat)} ${cat}`;
      catFilter.appendChild(opt);
    });

    // Update modal selects
    const statusSel = document.getElementById('update-status');
    const deptSel   = document.getElementById('update-department');
    metaData.statuses.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s; opt.textContent = s;
      statusSel.appendChild(opt);
    });
    metaData.departments.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d; opt.textContent = d;
      deptSel.appendChild(opt);
    });
  } catch(e) {
    console.error('initMeta error:', e);
  }
}

// ── Load & Render Complaints Table ─────────────────────────────────────

async function loadComplaints() {
  const params = new URLSearchParams();
  const search   = document.getElementById('filter-search').value.trim();
  const category = document.getElementById('filter-category').value;
  const priority = document.getElementById('filter-priority').value;
  const status   = document.getElementById('filter-status').value;
  if (search)   params.set('search', search);
  if (category) params.set('category', category);
  if (priority) params.set('priority', priority);
  if (status)   params.set('status', status);
  params.set('limit', '500');

  try {
    const res = await fetch(`${API}/api/complaints?${params}`);
    const data = await res.json();
    allComplaints = data.complaints || [];
    filteredList  = [...allComplaints];
    currentPage   = 0;
    renderTable();
    document.getElementById('last-updated').textContent =
      `Last synced: ${new Date().toLocaleTimeString()}`;
  } catch(e) {
    showToast('Failed to sync complaint records.', 'error');
  }
}

function renderTable() {
  const tbody   = document.getElementById('complaints-tbody');
  const start   = currentPage * PAGE_SIZE;
  const end     = start + PAGE_SIZE;
  const page    = filteredList.slice(start, end);
  const total   = filteredList.length;

  document.getElementById('page-info').textContent =
    `Showing ${Math.min(start+1, total)}–${Math.min(end, total)} of ${total} records`;
  document.getElementById('prev-btn').disabled = currentPage === 0;
  document.getElementById('next-btn').disabled = end >= total;

  if (!page.length) {
    tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:48px;color:var(--clr-text-muted);">No matching civic complaints found.</td></tr>';
    return;
  }

  tbody.innerHTML = page.map(c => {
    const emoji  = getCategoryEmoji(c.category);
    const pClass = getPriorityClass(c.priority);
    const sClass = getStatusClass(c.status);
    const pColor = getPriorityColor(c.priority);
    const pct    = Math.round((c.ai_confidence || 0) * 100);
    const desc   = c.description.length > 55 ? c.description.slice(0, 55) + '…' : c.description;
    const summary = c.ai_summary ? (c.ai_summary.length > 50 ? c.ai_summary.slice(0,50)+'…' : c.ai_summary) : '—';
    const id4    = String(c.id).padStart(4, '0');

    return `
      <tr data-id="${c.id}" onclick="openModal(${c.id})">
        <td style="font-family:'JetBrains Mono',monospace;font-weight:700;color:#a5b4fc;font-size:0.8rem;">#${id4}</td>
        <td class="td-primary">${escapeHtml(desc)}</td>
        <td class="text-secondary" style="font-size:0.82rem;">${escapeHtml(c.location)}</td>
        <td><span class="category-chip" style="font-size:0.75rem;">${emoji} ${c.category}</span></td>
        <td>
          <span class="badge badge-${pClass}">${c.priority}</span>
        </td>
        <td><span class="badge badge-${sClass}">${c.status}</span></td>
        <td class="text-secondary" style="font-size:0.82rem;">${escapeHtml(c.department)}</td>
        <td class="text-muted" style="font-size:0.8rem;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(summary)}</td>
        <td>
          <div class="conf-bar">
            <div class="conf-mini"><div class="conf-mini-fill" style="width:${pct}%"></div></div>
            <span class="text-xs text-muted fw-600">${pct}%</span>
          </div>
        </td>
        <td class="text-muted" style="font-size:0.78rem;white-space:nowrap;">${timeAgo(c.date_submitted)}</td>
      </tr>
    `;
  }).join('');
}

// ── Modal Details & AI Recommendation ───────────────────────────

async function openModal(id) {
  activeComplaintId = id;
  const overlay = document.getElementById('complaint-modal');
  overlay.classList.add('active');

  try {
    const res = await fetch(`${API}/api/complaints/${id}`);
    const data = await res.json();
    const c = data.complaint;

    const emoji  = getCategoryEmoji(c.category);
    const pClass = getPriorityClass(c.priority);
    const sClass = getStatusClass(c.status);
    const pct    = Math.round((c.ai_confidence || 0) * 100);

    // Fetch AI suggestion if available
    let aiSuggestion = '';
    try {
      const suggRes = await fetch(`${API}/api/complaints/${id}/suggest-action`);
      if (suggRes.ok) {
        const suggData = await suggRes.json();
        if (suggData.suggestion) aiSuggestion = suggData.suggestion;
      }
    } catch(e) {}

    document.getElementById('modal-content').innerHTML = `
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:24px;">
        <span class="badge badge-${pClass}">${c.priority}</span>
        <span class="badge badge-${sClass}">${c.status}</span>
        <span class="text-xs text-muted" style="font-family:'JetBrains Mono',monospace;">Ticket #${String(c.id).padStart(4,'0')}</span>
        <span class="text-xs text-muted" style="margin-left:auto;">${timeAgo(c.date_submitted)}</span>
      </div>

      <div class="form-group" style="margin-bottom:16px;">
        <span class="form-label">Full Problem Description</span>
        <p style="font-size:0.95rem;color:var(--clr-text-primary);line-height:1.6;background:rgba(255,255,255,0.03);padding:14px;border-radius:var(--radius-md);border:1px solid var(--clr-border);">${escapeHtml(c.description)}</p>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:20px;">
        <div>
          <span class="form-label">Location</span>
          <span class="text-primary text-sm fw-500">📍 ${escapeHtml(c.location)}</span>
        </div>
        <div>
          <span class="form-label">Category</span>
          <span class="text-primary text-sm fw-500">${emoji} ${c.category}</span>
        </div>
        <div>
          <span class="form-label">Assigned Department</span>
          <span class="text-primary text-sm fw-500">${escapeHtml(c.department)}</span>
        </div>
        <div>
          <span class="form-label">Reporter Contact</span>
          <span class="text-primary text-sm fw-500">${c.contact ? escapeHtml(c.contact) : '—'}</span>
        </div>
      </div>

      <div class="ai-result-card" style="margin-bottom:20px;">
        <div class="ai-label">✦ Gemini AI Synthesis ${c.ai_used_fallback ? '<span style="color:var(--clr-medium);font-size:0.65rem;">(Keyword Fallback)</span>' : ''}</div>
        <p class="ai-summary">${escapeHtml(c.ai_summary || 'No summary generated.')}</p>
        <div class="confidence-bar-wrap">
          <div class="confidence-bar-label">
            <span>Confidence Index</span>
            <span class="fw-700">${pct}%</span>
          </div>
          <div class="confidence-bar-track">
            <div class="confidence-bar-fill" style="width:${pct}%"></div>
          </div>
        </div>
        <p class="text-xs text-muted mt-8">${escapeHtml(c.ai_reasoning || '')}</p>
      </div>

      ${aiSuggestion ? `
        <div class="card card-sm" style="background:rgba(6,182,212,0.08);border:1px solid rgba(6,182,212,0.3);margin-bottom:20px;">
          <div class="section-eyebrow" style="font-size:0.7rem;margin-bottom:6px;">💡 AI Operational Action Recommendation</div>
          <p class="text-xs text-primary" style="line-height:1.5;">${escapeHtml(aiSuggestion)}</p>
        </div>
      ` : ''}

      ${c.admin_notes ? `
        <div style="margin-bottom:16px;">
          <span class="form-label">Previous Admin Notes</span>
          <p class="text-xs text-secondary" style="background:rgba(255,255,255,0.03);padding:10px 14px;border-radius:var(--radius-sm);">${escapeHtml(c.admin_notes)}</p>
        </div>
      ` : ''}
    `;

    // Pre-fill update form
    document.getElementById('update-status').value = c.status;
    document.getElementById('update-department').value = c.department;
    document.getElementById('update-notes').value = c.admin_notes || '';
  } catch(e) {
    document.getElementById('modal-content').innerHTML =
      '<p class="text-muted">Failed to load complaint details.</p>';
  }
}

document.getElementById('modal-close-btn').addEventListener('click', () => {
  document.getElementById('complaint-modal').classList.remove('active');
});
document.getElementById('complaint-modal').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) e.currentTarget.classList.remove('active');
});

// ── Save & Dispatch Changes ────────────────────────────────────────────

document.getElementById('update-submit-btn').addEventListener('click', async () => {
  if (!activeComplaintId) return;
  const btn = document.getElementById('update-submit-btn');
  btn.disabled = true;
  btn.textContent = 'Saving Dispatch...';

  try {
    const res = await fetch(`${API}/api/complaints/${activeComplaintId}`, {
      method: 'PATCH',
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
      },
      body: JSON.stringify({
        status:      document.getElementById('update-status').value,
        department:  document.getElementById('update-department').value,
        admin_notes: document.getElementById('update-notes').value,
      }),
    });
    if (!res.ok) throw new Error('Update failed');
    showToast('Complaint status & department updated successfully!', 'success');
    document.getElementById('complaint-modal').classList.remove('active');
    await Promise.all([loadComplaints(), loadStatistics()]);
  } catch(e) {
    showToast('Failed to update complaint record.', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Save & Dispatch Changes';
  }
});

// ── Statistics & Visual Charts ─────────────────────────────────────────

const CHART_DEFAULTS = {
  responsive: true,
  maintainAspectRatio: true,
  plugins: {
    legend: { labels: { color: '#94a3b8', font: { family: 'Inter', size: 11, weight: '500' } } }
  },
};

const CATEGORY_COLORS = [
  '#6366f1','#06b6d4','#10b981','#facc15','#8b5cf6','#f43f5e','#38bdf8','#c084fc'
];
const PRIORITY_COLORS = ['#f43f5e','#fb923c','#facc15','#10b981'];
const STATUS_COLORS   = ['#94a3b8','#c084fc','#38bdf8','#34d399'];

async function loadStatistics() {
  try {
    const res = await fetch(`${API}/api/statistics`);
    const data = await res.json();
    const stats = data.statistics;

    // Stat cards
    const sum = stats.summary;
    document.getElementById('stat-total').textContent    = sum.total;
    document.getElementById('stat-open').textContent     = sum.open_count;
    document.getElementById('stat-critical').textContent = sum.critical_count;
    document.getElementById('stat-resolved').textContent = sum.resolved_count;

    // Category doughnut
    const catLabels = Object.keys(sum.by_category);
    const catValues = Object.values(sum.by_category);
    if (chartCategory) chartCategory.destroy();
    chartCategory = new Chart(document.getElementById('chart-category').getContext('2d'), {
      type: 'doughnut',
      data: {
        labels: catLabels,
        datasets: [{ data: catValues, backgroundColor: CATEGORY_COLORS, borderWidth: 0, hoverOffset: 6 }],
      },
      options: {
        ...CHART_DEFAULTS,
        plugins: { ...CHART_DEFAULTS.plugins, legend: { position: 'bottom', labels: { color: '#94a3b8', font: { size: 10 } } } },
      }
    });

    // Priority bar
    const priOrder  = ['Critical','High','Medium','Low'];
    const priValues = priOrder.map(p => sum.by_priority[p] || 0);
    if (chartPriority) chartPriority.destroy();
    chartPriority = new Chart(document.getElementById('chart-priority').getContext('2d'), {
      type: 'bar',
      data: {
        labels: priOrder,
        datasets: [{ data: priValues, backgroundColor: PRIORITY_COLORS, borderRadius: 8, borderWidth: 0 }],
      },
      options: {
        ...CHART_DEFAULTS,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,0.05)' } },
          y: { ticks: { color: '#94a3b8', stepSize: 1 }, grid: { color: 'rgba(255,255,255,0.05)' } },
        },
      },
    });

    // Status doughnut
    const statOrder  = ['Open','Assigned','In Progress','Resolved'];
    const statValues = statOrder.map(s => sum.by_status[s] || 0);
    if (chartStatus) chartStatus.destroy();
    chartStatus = new Chart(document.getElementById('chart-status').getContext('2d'), {
      type: 'doughnut',
      data: {
        labels: statOrder,
        datasets: [{ data: statValues, backgroundColor: STATUS_COLORS, borderWidth: 0, hoverOffset: 6 }],
      },
      options: {
        ...CHART_DEFAULTS,
        plugins: { legend: { position: 'bottom', labels: { color: '#94a3b8', font: { size: 10 } } } },
      },
    });

    // Trend line
    const trend = stats.daily_trend;
    const tLabels = trend.map(t => t.date.slice(5));  // MM-DD
    const tValues = trend.map(t => t.count);
    if (chartTrend) chartTrend.destroy();
    chartTrend = new Chart(document.getElementById('chart-trend').getContext('2d'), {
      type: 'line',
      data: {
        labels: tLabels,
        datasets: [{
          data: tValues,
          borderColor: '#06b6d4',
          backgroundColor: 'rgba(6, 182, 212, 0.12)',
          fill: true,
          tension: 0.4,
          pointRadius: 4,
          pointBackgroundColor: '#06b6d4',
          borderWidth: 3,
        }],
      },
      options: {
        ...CHART_DEFAULTS,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: '#94a3b8', maxTicksLimit: 12, font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.04)' } },
          y: { ticks: { color: '#94a3b8', stepSize: 1 }, grid: { color: 'rgba(255,255,255,0.04)' } },
        },
      },
    });

    // Resolution time stats
    const rt = stats.resolution_times;
    document.getElementById('rs-mean').textContent   = formatHours(rt.mean_hours);
    document.getElementById('rs-median').textContent = formatHours(rt.median_hours);
    document.getElementById('rs-stddev').textContent = rt.std_dev !== null ? `${rt.std_dev}h` : '—';
    document.getElementById('rs-min').textContent    = formatHours(rt.min_hours);
    document.getElementById('rs-max').textContent    = formatHours(rt.max_hours);
    document.getElementById('rs-count').textContent  = rt.count;

    // Top Locations bar chart
    const locs = stats.top_locations;
    if (locs.length) {
      if (chartLocations) chartLocations.destroy();
      chartLocations = new Chart(document.getElementById('chart-locations').getContext('2d'), {
        type: 'bar',
        data: {
          labels: locs.map(l => l.location.length > 25 ? l.location.slice(0,25)+'…' : l.location),
          datasets: [{
            data: locs.map(l => l.count),
            backgroundColor: 'rgba(99, 102, 241, 0.65)',
            borderRadius: 6,
            borderWidth: 0,
          }],
        },
        options: {
          ...CHART_DEFAULTS,
          indexAxis: 'y',
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: '#94a3b8', stepSize: 1 }, grid: { color: 'rgba(255,255,255,0.04)' } },
            y: { ticks: { color: '#94a3b8', font: { size: 11 } }, grid: { display: false } },
          },
        },
      });
    }

  } catch(e) {
    console.error('loadStatistics error:', e);
  }
}

// ── Filter Events & Pagination ─────────────────────────────────────────

let filterTimeout = null;
['filter-search','filter-category','filter-priority','filter-status'].forEach(id => {
  document.getElementById(id).addEventListener('input', () => {
    clearTimeout(filterTimeout);
    filterTimeout = setTimeout(() => { currentPage = 0; loadComplaints(); }, 350);
  });
  document.getElementById(id).addEventListener('change', () => { currentPage = 0; loadComplaints(); });
});

document.getElementById('clear-filters-btn').addEventListener('click', () => {
  document.getElementById('filter-search').value   = '';
  document.getElementById('filter-category').value = '';
  document.getElementById('filter-priority').value = '';
  document.getElementById('filter-status').value   = '';
  currentPage = 0;
  loadComplaints();
});

document.getElementById('prev-btn').addEventListener('click', () => {
  if (currentPage > 0) { currentPage--; renderTable(); }
});
document.getElementById('next-btn').addEventListener('click', () => {
  if ((currentPage + 1) * PAGE_SIZE < filteredList.length) { currentPage++; renderTable(); }
});

document.getElementById('refresh-btn').addEventListener('click', () => {
  loadComplaints();
  loadStatistics();
  showToast('Dashboard data synced.', 'info');
});

// ── Init ───────────────────────────────────────────────────────────────

async function init() {
  await initAdminAuth();
  await initMeta();
  await Promise.all([loadComplaints(), loadStatistics()]);
}

init();
