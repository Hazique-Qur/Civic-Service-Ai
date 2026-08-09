/* =====================================================================
   feed.js — Live Community Feed (dedicated page)
   Full complaint listing with search, category/priority/status filters,
   live polling every 30s, and pagination.
   ===================================================================== */

const API = '';
const FEED_PAGE_SIZE = 12;

let feedPage       = 0;
let feedTotal      = 0;
let feedAll        = [];
let pollInterval   = null;

// ── Helpers ──────────────────────────────────────────────────────────

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
function getPriorityDotColor(p) {
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

// ── Stats Counter Refresh ────────────────────────────────────────────

async function refreshCounters() {
  try {
    const res = await fetch(`${API}/api/statistics`);
    const data = await res.json();
    const s = data.statistics.summary;
    document.getElementById('cnt-total').textContent    = s.total    ?? '—';
    document.getElementById('cnt-open').textContent     = s.open_count ?? '—';
    document.getElementById('cnt-critical').textContent = s.critical_count ?? '—';
    document.getElementById('cnt-resolved').textContent = s.resolved_count ?? '—';
  } catch { /* silent */ }
}

// ── AI Status ────────────────────────────────────────────────────────

async function checkAIStatus() {
  try {
    const res = await fetch(`${API}/api/health`);
    const data = await res.json();
    const badge = document.getElementById('ai-status-badge');
    if (badge) {
      if (data.ai_active) {
        badge.className = 'badge badge-low';
        badge.textContent = '🤖 Gemini 2.0 AI Active';
      } else {
        badge.className = 'badge badge-medium';
        badge.textContent = '⚙️ Keyword Fallback';
      }
    }
  } catch { /* ignore */ }
}

// ── Feed Loading ─────────────────────────────────────────────────────

async function loadFeed(resetPage = false) {
  if (resetPage) feedPage = 0;

  const search   = document.getElementById('feed-search').value.trim();
  const category = document.getElementById('feed-category').value;
  const priority = document.getElementById('feed-priority').value;
  const status   = document.getElementById('feed-status').value;

  const params = new URLSearchParams({ limit: '500' });
  if (search)   params.set('search', search);
  if (category) params.set('category', category);
  if (priority) params.set('priority', priority);
  if (status)   params.set('status', status);

  const container = document.getElementById('feed-container');
  const skeleton  = document.getElementById('feed-skeleton');
  const emptyEl   = document.getElementById('feed-empty');

  if (skeleton) skeleton.classList.remove('hidden');
  if (emptyEl)  emptyEl.classList.add('hidden');

  try {
    const res = await fetch(`${API}/api/complaints?${params}`);
    const data = await res.json();
    feedAll   = data.complaints || [];
    feedTotal = feedAll.length;
    renderFeedPage();
    updateLastSync();
  } catch {
    if (container) container.innerHTML = '<p class="text-muted text-sm text-center" style="padding:48px;">Failed to load community feed. Please try again.</p>';
  } finally {
    if (skeleton) skeleton.classList.add('hidden');
  }
}

function renderFeedPage() {
  const container = document.getElementById('feed-container');
  const emptyEl   = document.getElementById('feed-empty');
  const start = feedPage * FEED_PAGE_SIZE;
  const end   = start + FEED_PAGE_SIZE;
  const page  = feedAll.slice(start, end);
  const total = feedAll.length;

  // Pagination info
  document.getElementById('feed-page-info').textContent =
    total ? `Showing ${Math.min(start+1, total)}–${Math.min(end, total)} of ${total} reports` : '0 reports';
  document.getElementById('feed-prev-btn').disabled = feedPage === 0;
  document.getElementById('feed-next-btn').disabled = end >= total;

  if (!page.length) {
    if (container) container.innerHTML = '';
    if (emptyEl) emptyEl.classList.remove('hidden');
    return;
  }
  if (emptyEl) emptyEl.classList.add('hidden');

  container.innerHTML = page.map(c => {
    const emoji    = getCategoryEmoji(c.category);
    const pClass   = getPriorityClass(c.priority);
    const sClass   = getStatusClass(c.status);
    const dotColor = getPriorityDotColor(c.priority);
    const desc     = c.description.length > 200 ? c.description.slice(0, 200) + '...' : c.description;
    const isResolved = (c.status === 'Resolved' || c.status === 'Successful');
    const resolvedBadge = isResolved ? '<span style="font-size:0.78rem;">✅</span>' : '';
    const pct = Math.round((c.ai_confidence || 0) * 100);

    return `
      <div class="feed-card" style="
        background: rgba(15,23,42,0.7);
        border: 1px solid rgba(255,255,255,0.07);
        border-radius: var(--radius-lg);
        padding: 24px 28px;
        position: relative;
        transition: var(--transition);
        backdrop-filter: blur(12px);
      " onmouseover="this.style.borderColor='rgba(99,102,241,0.35)';this.style.transform='translateY(-2px)'"
         onmouseout="this.style.borderColor='rgba(255,255,255,0.07)';this.style.transform='none'">

        <!-- Priority dot indicator -->
        <div style="
          position:absolute; top:0; left:0; bottom:0; width:4px;
          border-radius:var(--radius-lg) 0 0 var(--radius-lg);
          background: ${dotColor};
          box-shadow: 0 0 12px ${dotColor}55;
        "></div>

        <div style="padding-left:8px;">
          <!-- Header row -->
          <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:14px;">
            <span class="category-chip" style="font-size:0.76rem;">${emoji} ${c.category}</span>
            <span class="badge badge-${pClass}" style="font-size:0.74rem;">${c.priority}</span>
            <span class="badge badge-${sClass}" style="font-size:0.74rem;">${resolvedBadge} ${c.status}</span>
            <span style="margin-left:auto;font-size:0.75rem;color:var(--clr-text-muted);">🕐 ${timeAgo(c.date_submitted)}</span>
          </div>

          <!-- Description -->
          <p style="font-size:0.92rem;color:var(--clr-text-secondary);line-height:1.65;margin-bottom:14px;">${escapeHtml(desc)}</p>

          <!-- AI Summary -->
          ${c.ai_summary ? `<p style="font-size:0.8rem;color:var(--clr-text-muted);background:rgba(99,102,241,0.06);border:1px solid rgba(99,102,241,0.15);padding:10px 14px;border-radius:var(--radius-sm);margin-bottom:14px;line-height:1.5;">✦ ${escapeHtml(c.ai_summary)}</p>` : ''}

          <!-- Footer row -->
          <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
            <span style="font-size:0.78rem;color:var(--clr-text-muted);">📍 ${escapeHtml(c.location)}</span>
            <span style="font-size:0.78rem;color:var(--clr-text-muted);">🏢 ${escapeHtml(c.department)}</span>
            <span style="margin-left:auto;display:flex;align-items:center;gap:6px;">
              <div style="width:56px;height:4px;background:rgba(255,255,255,0.08);border-radius:2px;overflow:hidden;">
                <div style="width:${pct}%;height:100%;background:linear-gradient(90deg,var(--clr-primary),var(--clr-accent-cyan));border-radius:2px;"></div>
              </div>
              <span style="font-size:0.72rem;color:var(--clr-text-muted);">${pct}% conf.</span>
            </span>
          </div>
        </div>
      </div>`;
  }).join('');
}

function updateLastSync() {
  const el = document.getElementById('last-sync');
  if (el) el.textContent = `Last synced: ${new Date().toLocaleTimeString()}`;
}

// ── Category Dropdown Population ─────────────────────────────────────

async function populateFeedFilters() {
  try {
    const res = await fetch(`${API}/api/meta`);
    const meta = await res.json();
    const catSel = document.getElementById('feed-category');
    (meta.categories || []).forEach(cat => {
      const opt = document.createElement('option');
      opt.value = cat;
      opt.textContent = `${getCategoryEmoji(cat)} ${cat}`;
      catSel.appendChild(opt);
    });
  } catch { /* ignore */ }
}

// ── Event Bindings ────────────────────────────────────────────────────

let feedDebounce = null;

function bindFeedEvents() {
  // Search
  document.getElementById('feed-search').addEventListener('input', () => {
    clearTimeout(feedDebounce);
    feedDebounce = setTimeout(() => loadFeed(true), 350);
  });

  // Filters
  ['feed-category','feed-priority','feed-status'].forEach(id => {
    document.getElementById(id).addEventListener('change', () => loadFeed(true));
  });

  // Clear
  document.getElementById('feed-clear-btn').addEventListener('click', () => {
    document.getElementById('feed-search').value   = '';
    document.getElementById('feed-category').value = '';
    document.getElementById('feed-priority').value = '';
    document.getElementById('feed-status').value   = '';
    loadFeed(true);
  });

  // Pagination
  document.getElementById('feed-prev-btn').addEventListener('click', () => {
    if (feedPage > 0) { feedPage--; renderFeedPage(); window.scrollTo({ top: 0, behavior: 'smooth' }); }
  });
  document.getElementById('feed-next-btn').addEventListener('click', () => {
    if ((feedPage + 1) * FEED_PAGE_SIZE < feedTotal) { feedPage++; renderFeedPage(); window.scrollTo({ top: 0, behavior: 'smooth' }); }
  });

  // Manual refresh
  document.getElementById('feed-refresh-btn').addEventListener('click', () => {
    loadFeed(true);
    refreshCounters();
  });
}

// ── Live Polling ──────────────────────────────────────────────────────

function startLivePolling() {
  pollInterval = setInterval(() => {
    loadFeed(false);   // keep current page
    refreshCounters();
  }, 30000);           // every 30 seconds
}

// ── Init ──────────────────────────────────────────────────────────────

async function init() {
  await Promise.all([populateFeedFilters(), checkAIStatus()]);
  bindFeedEvents();
  await loadFeed(true);
  await refreshCounters();
  startLivePolling();
}

document.addEventListener('DOMContentLoaded', init);
