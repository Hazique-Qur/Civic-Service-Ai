/* =====================================================================
   auth.js — Shared authentication utilities for all pages
   ===================================================================== */

const AUTH_TOKEN_KEY = 'civic_auth_token';

function getAuthToken() {
  return localStorage.getItem(AUTH_TOKEN_KEY) || '';
}

function setAuthToken(token) {
  if (token) {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
  } else {
    localStorage.removeItem(AUTH_TOKEN_KEY);
  }
}

async function syncAuthFromSession() {
  try {
    const res = await fetch('/api/auth/token', { credentials: 'include' });
    if (res.ok) {
      const data = await res.json();
      if (data.token) {
        setAuthToken(data.token);
        return data.user;
      }
    }
  } catch (_) { /* offline */ }
  return null;
}

async function handleLogout() {
  try {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
  } catch (_) { /* ignore */ }
  setAuthToken('');
  window.location.href = '/login';
}

async function initAuthNav(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  let user = null;
  try {
    const res = await fetch('/api/auth/me', { credentials: 'include' });
    if (res.ok) {
      const data = await res.json();
      user = data.user;
      await syncAuthFromSession();
    }
  } catch (_) { /* ignore */ }

  if (user) {
    const avatar = user.avatar_url
      ? `<img src="${user.avatar_url}" alt="" class="auth-avatar" />`
      : `<span class="auth-avatar auth-avatar-fallback">${(user.display_name || user.email)[0].toUpperCase()}</span>`;
    container.innerHTML = `
      <div class="auth-nav-user">
        ${avatar}
        <span class="auth-nav-name">${escapeAuthHtml(user.display_name || user.email.split('@')[0])}</span>
        <button class="btn btn-ghost btn-sm auth-logout-btn" onclick="handleLogout()">Log Out</button>
      </div>`;
  } else {
    container.innerHTML = `
      <a href="/login" class="btn btn-ghost btn-sm">Sign In</a>
      <a href="/login?mode=signup" class="btn btn-primary btn-sm">Sign Up</a>`;
  }
}

function escapeAuthHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// Migrate legacy key
if (localStorage.getItem('civic_admin_token') && !localStorage.getItem(AUTH_TOKEN_KEY)) {
  setAuthToken(localStorage.getItem('civic_admin_token'));
  localStorage.removeItem('civic_admin_token');
}
