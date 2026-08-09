/* =====================================================================
   citizen.js — Citizen Complaint Portal Logic
   Live AI preview, duplicate detection, chat widget, recent feed.
   ===================================================================== */

const API = '';

// ── Helpers ──────────────────────────────────────────────────────────

function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  const icons = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span>${icons[type] || '💬'}</span> ${message}`;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 5000);
}

function getPriorityClass(priority) {
  return { 'Critical': 'critical', 'High': 'high', 'Medium': 'medium', 'Low': 'low' }[priority] || 'medium';
}

function getStatusClass(status) {
  return {
    'Open': 'open', 'Assigned': 'assigned',
    'In Progress': 'in-progress', 'Resolved': 'resolved', 'Successful': 'resolved'
  }[status] || 'open';
}

function getCategoryEmoji(category) {
  const map = {
    'Water/Drainage': '💧', 'Roads/Pavements': '🛣️', 'Waste/Sanitation': '🗑️',
    'Electricity': '⚡', 'Parks/Green Spaces': '🌳', 'Noise/Disturbance': '🔊',
    'Public Safety': '🚨', 'Other': '📋'
  };
  return map[category] || '📋';
}

function getPriorityDotColor(priority) {
  return {
    'Critical': 'var(--clr-critical)',
    'High': 'var(--clr-high)',
    'Medium': 'var(--clr-medium)',
    'Low': 'var(--clr-low)'
  }[priority] || 'var(--clr-medium)';
}

function timeAgo(isoString) {
  const diff = Date.now() - new Date(isoString + 'Z').getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function escapeHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── AI Status Check ───────────────────────────────────────────────────

async function checkAIStatus() {
  try {
    const res = await fetch(`${API}/api/health`);
    const data = await res.json();
    const badge = document.getElementById('ai-status-badge');
    const modeText = document.getElementById('ai-mode-text');
    if (badge) {
      if (data.ai_active) {
        badge.className = 'badge badge-low';
        badge.textContent = '🤖 Gemini 2.0 AI Active';
        if (modeText) modeText.textContent = 'Using Google Gemini 2.0 Flash for real-time triage & classification.';
      } else {
        badge.className = 'badge badge-medium';
        badge.textContent = '⚙️ Keyword Fallback';
        if (modeText) modeText.textContent = 'Keyword-based classifier active (add GEMINI_API_KEY to enable Gemini).';
      }
    }
  } catch {
    const badge = document.getElementById('ai-status-badge');
    if (badge) {
      badge.className = 'badge badge-critical';
      badge.textContent = '⚠️ Connection Error';
    }
  }
}

// ── Live AI Neural Preview (debounced) ────────────────────────────────

let previewTimeout = null;
let duplicateTimeout = null;

function showIdleState() {
  const idle = document.getElementById('ai-idle');
  const thinking = document.getElementById('ai-thinking-state');
  const result = document.getElementById('ai-preview-result');
  if (idle) idle.classList.remove('hidden');
  if (thinking) thinking.classList.add('hidden');
  if (result) result.classList.add('hidden');
}

function showThinkingState() {
  const idle = document.getElementById('ai-idle');
  const thinking = document.getElementById('ai-thinking-state');
  const result = document.getElementById('ai-preview-result');
  if (idle) idle.classList.add('hidden');
  if (thinking) thinking.classList.remove('hidden');
  if (result) result.classList.add('hidden');
}

function showPreviewResult(complaint) {
  const idle = document.getElementById('ai-idle');
  const thinking = document.getElementById('ai-thinking-state');
  const result = document.getElementById('ai-preview-result');
  if (idle) idle.classList.add('hidden');
  if (thinking) thinking.classList.add('hidden');
  if (result) result.classList.remove('hidden');

  const emoji = getCategoryEmoji(complaint.category);
  const pClass = getPriorityClass(complaint.priority);

  document.getElementById('preview-summary').textContent = complaint.ai_summary || 'No summary generated.';
  document.getElementById('preview-category').textContent = `${emoji} ${complaint.category}`;
  document.getElementById('preview-priority').textContent = complaint.priority;
  document.getElementById('preview-priority').className = `badge badge-${pClass}`;
  document.getElementById('preview-dept').textContent = `🏢 ${complaint.department}`;
  document.getElementById('preview-dept-info').textContent = complaint.department;

  const pct = Math.round((complaint.ai_confidence || 0) * 100);
  document.getElementById('preview-confidence').textContent = `${pct}%`;
  document.getElementById('confidence-fill').style.width = `${pct}%`;
  document.getElementById('preview-reasoning').textContent = complaint.ai_reasoning || '';
}

async function runLivePreview(description, location) {
  if (description.length < 10) { showIdleState(); return; }
  showThinkingState();
  try {
    const res = await fetch(`${API}/api/complaints`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description, location: location || 'Unknown', contact: '' }),
    });
    if (!res.ok) throw new Error('API error');
    const data = await res.json();
    showPreviewResult(data.complaint);
    window._previewComplaint = data.complaint;
  } catch {
    showIdleState();
  }
}

// ── Duplicate Detection ───────────────────────────────────────────────

async function checkForDuplicate(description, location) {
  if (description.length < 20) return;
  try {
    const res = await fetch(`${API}/api/complaints/check-duplicate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description, location }),
    });
    const data = await res.json();
    const dupBanner = document.getElementById('duplicate-banner');
    if (dupBanner) {
      if (data.is_duplicate && data.similarity_score > 0.6) {
        dupBanner.classList.remove('hidden');
        document.getElementById('dup-reason').textContent =
          data.reason || 'A similar complaint has already been submitted.';
        const similar = data.similar_complaint;
        if (similar) {
          document.getElementById('dup-ticket').textContent =
            `Similar Ticket #${String(similar.id).padStart(4,'0')} — ${similar.location} (${similar.status})`;
        }
      } else {
        dupBanner.classList.add('hidden');
      }
    }
  } catch { /* silent fail */ }
}

function selectLocation(chip) {
  document.querySelectorAll('.suggestion-chip').forEach(c => c.classList.remove('selected'));
  chip.classList.add('selected');
  const input = document.getElementById('location');
  if (input) {
    input.value = chip.textContent;
    input.dispatchEvent(new Event('input'));
  }
}

function showSuccessCard(complaint) {
  document.getElementById('complaint-form').classList.add('hidden');
  document.getElementById('duplicate-banner').classList.add('hidden');
  document.getElementById('submission-success').classList.remove('hidden');
  document.getElementById('ai-preview-result').classList.add('hidden');
  document.getElementById('ai-idle').classList.add('hidden');

  const emoji = getCategoryEmoji(complaint.category);
  const pClass = getPriorityClass(complaint.priority);

  document.getElementById('ticket-id').textContent = `TICKET #${String(complaint.id).padStart(4, '0')}`;
  document.getElementById('success-category').textContent = `${emoji} ${complaint.category}`;
  document.getElementById('success-priority').textContent = complaint.priority;
  document.getElementById('success-priority').className = `badge badge-${pClass}`;
  document.getElementById('success-summary').textContent = complaint.ai_summary || '';
  document.getElementById('success-dept').textContent = `🏢 Dispatched to: ${complaint.department}`;

  showToast('Civic report submitted and dispatched to field team!', 'success');
  loadRecentComplaints();
}

// ── Recent Community Complaints Feed ──────────────────────────────────

async function loadRecentComplaints() {
  const feed = document.getElementById('recent-feed');
  if (!feed) return;
  try {
    const res = await fetch(`${API}/api/complaints?limit=8`);
    const data = await res.json();
    renderFeed(data.complaints || []);
  } catch {
    feed.innerHTML = '<p class="text-muted text-sm" style="padding:20px;">Could not load recent reports.</p>';
  }
}

function renderFeed(complaints) {
  const feed = document.getElementById('recent-feed');
  if (!feed) return;
  if (!complaints.length) {
    feed.innerHTML = '<p class="text-secondary text-sm" style="padding:32px;text-align:center;">No reports yet. Be the first! 🎉</p>';
    return;
  }
  feed.innerHTML = `<div style="padding: 8px 0;">` + complaints.map(c => {
    const emoji = getCategoryEmoji(c.category);
    const dotColor = getPriorityDotColor(c.priority);
    const pClass = getPriorityClass(c.priority);
    const sClass = getStatusClass(c.status);
    const statusIcon = (c.status === 'Successful' || c.status === 'Resolved') ? '✅ ' : '';
    const desc = c.description.length > 120 ? c.description.slice(0, 120) + '...' : c.description;
    return `
      <div class="feed-item">
        <div class="feed-dot" style="background:${dotColor};box-shadow:0 0 8px ${dotColor};"></div>
        <div style="flex:1;min-width:0;">
          <p style="font-size:0.9rem;color:var(--clr-text-secondary);margin-bottom:8px;line-height:1.5;">${escapeHtml(desc)}</p>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
            <span class="category-chip" style="font-size:0.74rem;padding:4px 10px;">${emoji} ${c.category}</span>
            <span class="badge badge-${pClass}" style="font-size:0.72rem;">${c.priority}</span>
            <span class="badge badge-${sClass}" style="font-size:0.72rem;">${statusIcon}${c.status}</span>
            <span style="font-size:0.75rem;color:var(--clr-text-muted);">📍 ${escapeHtml(c.location)}</span>
            <span style="font-size:0.75rem;color:var(--clr-text-muted);margin-left:auto;">🕐 ${timeAgo(c.date_submitted)}</span>
          </div>
        </div>
      </div>`;
  }).join('') + `</div>`;
}

// ── AI Chat Widget ────────────────────────────────────────────────────

let chatOpen = false;
const chatMessages = [];

function toggleChat() {
  chatOpen = !chatOpen;
  const panel = document.getElementById('chat-panel');
  const btn   = document.getElementById('chat-toggle-btn');
  if (chatOpen) {
    panel.classList.remove('hidden');
    btn.style.background = 'linear-gradient(135deg, #ef4444, #dc2626)';
    btn.textContent = '✕';
    if (chatMessages.length === 0) {
      addBotMessage("👋 Hi! I'm the CivicAI assistant. I can help you identify what category your issue falls under, understand which department handles it, or explain how the reporting process works. What's on your mind?");
    }
  } else {
    panel.classList.add('hidden');
    btn.style.background = 'linear-gradient(135deg, var(--clr-primary), var(--clr-accent-cyan))';
    btn.textContent = '💬';
  }
}

function addBotMessage(text) {
  chatMessages.push({ role: 'bot', text });
  renderChat();
}

function renderChat() {
  const container = document.getElementById('chat-messages');
  if (!container) return;
  container.innerHTML = chatMessages.map(m => {
    if (m.role === 'user') {
      return `<div style="display:flex;justify-content:flex-end;margin-bottom:10px;">
        <div style="background:linear-gradient(135deg,var(--clr-primary),var(--clr-accent-cyan));color:#fff;padding:11px 16px;border-radius:18px 18px 4px 18px;font-size:0.86rem;max-width:85%;line-height:1.5;">${escapeHtml(m.text)}</div>
      </div>`;
    } else {
      const isTyping = m.text === '...';
      return `<div style="display:flex;margin-bottom:10px;gap:10px;align-items:flex-start;">
        <div style="width:30px;height:30px;border-radius:50%;background:linear-gradient(135deg,var(--clr-primary),var(--clr-accent-cyan));flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:0.78rem;">🤖</div>
        <div style="background:rgba(15,23,42,0.9);border:1px solid var(--clr-border);padding:11px 16px;border-radius:4px 18px 18px 18px;font-size:0.86rem;max-width:85%;color:var(--clr-text-secondary);line-height:1.55;">${isTyping ? '<span style="color:var(--clr-accent-cyan);">Thinking...</span>' : m.text.replace(/\n/g,'<br>')}</div>
      </div>`;
    }
  }).join('');
  container.scrollTop = container.scrollHeight;
}

async function sendChatMessage() {
  const input = document.getElementById('chat-input');
  if (!input) return;
  const msg = input.value.trim();
  if (!msg) return;
  input.value = '';
  chatMessages.push({ role: 'user', text: msg });
  renderChat();

  const typingId = 'typing-' + Date.now();
  chatMessages.push({ role: 'bot', text: '...', _id: typingId });
  renderChat();

  try {
    const res = await fetch(`${API}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg }),
    });
    const data = await res.json();
    const idx = chatMessages.findIndex(m => m._id === typingId);
    if (idx > -1) chatMessages.splice(idx, 1);
    chatMessages.push({ role: 'bot', text: data.reply || 'Sorry, I had trouble responding.' });
    renderChat();
  } catch {
    const idx = chatMessages.findIndex(m => m._id === typingId);
    if (idx > -1) chatMessages.splice(idx, 1);
    addBotMessage('Connection issue — please try again.');
  }
}

// ── Event Bindings ────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // Description events
  const descEl = document.getElementById('description');
  if (descEl) {
    descEl.addEventListener('input', function () {
      const len = this.value.length;
      document.getElementById('char-count').textContent = len;

      clearTimeout(previewTimeout);
      clearTimeout(duplicateTimeout);

      const location = document.getElementById('location').value;
      if (len < 10) { showIdleState(); return; }
      showThinkingState();

      previewTimeout = setTimeout(() => {
        runLivePreview(this.value, location);
      }, 1400);

      duplicateTimeout = setTimeout(() => {
        checkForDuplicate(this.value, location);
      }, 2500);
    });
  }

  // Location events
  const locEl = document.getElementById('location');
  if (locEl) {
    locEl.addEventListener('input', function () {
      const description = document.getElementById('description').value;
      if (description.length >= 10) {
        clearTimeout(previewTimeout);
        previewTimeout = setTimeout(() => {
          runLivePreview(description, this.value);
        }, 900);
      }
    });
  }

  // Form submission
  const formEl = document.getElementById('complaint-form');
  if (formEl) {
    formEl.addEventListener('submit', async (e) => {
      e.preventDefault();

      const description = document.getElementById('description').value.trim();
      const location    = document.getElementById('location').value.trim();
      const contact     = document.getElementById('contact').value.trim();

      if (!description || description.length < 10) {
        showToast('Please provide a detailed description (at least 10 characters).', 'error');
        return;
      }
      if (!location) {
        showToast('Please enter the problem location or landmark.', 'error');
        return;
      }

      if (window._previewComplaint) {
        showSuccessCard(window._previewComplaint);
        window._previewComplaint = null;
        return;
      }

      const btn = document.getElementById('submit-btn');
      btn.disabled = true;
      document.getElementById('submit-icon').innerHTML = '<div class="spinner" style="width:18px;height:18px;border-width:2px;"></div>';
      document.getElementById('submit-text').textContent = 'AI Triaging...';

      try {
        const res = await fetch(`${API}/api/complaints`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ description, location, contact }),
        });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Submission failed');
        }
        const data = await res.json();
        showSuccessCard(data.complaint);
      } catch (err) {
        showToast(`Error: ${err.message}`, 'error');
      } finally {
        btn.disabled = false;
        document.getElementById('submit-icon').textContent = '🚀';
        document.getElementById('submit-text').textContent = 'Submit Civic Report';
      }
    });
  }

  // Success button
  const successBtn = document.getElementById('submit-another-btn');
  if (successBtn) {
    successBtn.addEventListener('click', () => {
      document.getElementById('complaint-form').reset();
      document.getElementById('char-count').textContent = '0';
      document.getElementById('complaint-form').classList.remove('hidden');
      document.getElementById('submission-success').classList.add('hidden');
      document.getElementById('duplicate-banner').classList.add('hidden');
      showIdleState();
      window._previewComplaint = null;
    });
  }

  // Chat Widget bindings
  const chatInput = document.getElementById('chat-input');
  if (chatInput) {
    chatInput.addEventListener('keypress', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChatMessage(); }
    });
  }
  document.getElementById('chat-send-btn')?.addEventListener('click', sendChatMessage);
  document.getElementById('chat-toggle-btn')?.addEventListener('click', toggleChat);

  // Initialize page-dependent actions
  checkAIStatus();
  loadRecentComplaints();
});
