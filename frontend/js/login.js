let authMode = 'login';
let googleEnabled = false;

function showError(message) {
  const errorEl = document.getElementById('auth-error');
  const errorMessage = document.getElementById('error-message');
  errorMessage.textContent = message;
  errorEl.classList.add('visible');
}

function hideError() {
  document.getElementById('auth-error').classList.remove('visible');
}

function setAuthMode(mode) {
  authMode = mode;
  const title = document.getElementById('auth-title');
  const subtitle = document.getElementById('auth-subtitle');
  const groupName = document.getElementById('group-name');
  const groupConfirm = document.getElementById('group-confirm');
  const groupTerms = document.getElementById('group-terms');
  const passwordStrength = document.getElementById('password-strength');
  const displayNameInput = document.getElementById('display_name');
  const passwordInput = document.getElementById('password');
  const confirmInput = document.getElementById('password_confirm');
  const submitBtn = document.getElementById('submit-btn');
  const formSwitchDesc = document.getElementById('form-switch-desc');
  const tabLogin = document.getElementById('tab-login');
  const tabSignup = document.getElementById('tab-signup');

  hideError();

  const isSignup = mode === 'signup';
  groupName.hidden = !isSignup;
  groupConfirm.hidden = !isSignup;
  groupTerms.hidden = !isSignup;
  passwordStrength.hidden = !isSignup;
  displayNameInput.required = isSignup;
  confirmInput.required = isSignup;
  passwordInput.autocomplete = isSignup ? 'new-password' : 'current-password';

  if (isSignup) {
    title.textContent = 'Create Your Account';
    subtitle.textContent = 'Join the premium civic reporting platform';
    submitBtn.textContent = 'Create Premium Account';
    formSwitchDesc.innerHTML = 'Already have an account? <a href="#" onclick="setAuthMode(\'login\'); return false;">Sign in here</a>';
    tabLogin.classList.remove('active');
    tabSignup.classList.add('active');
  } else {
    title.textContent = 'Welcome Back';
    subtitle.textContent = 'Access your civic dashboard & track reports';
    submitBtn.textContent = 'Access Account';
    formSwitchDesc.innerHTML = 'Don\'t have an account? <a href="#" onclick="setAuthMode(\'signup\'); return false;">Sign up here</a>';
    tabLogin.classList.add('active');
    tabSignup.classList.remove('active');
  }
}

function updatePasswordStrength(password) {
  const fill = document.getElementById('strength-fill');
  const label = document.getElementById('strength-label');
  if (!fill || !label) return;

  let score = 0;
  if (password.length >= 6) score++;
  if (password.length >= 10) score++;
  if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score++;
  if (/\d/.test(password)) score++;
  if (/[^A-Za-z0-9]/.test(password)) score++;

  const levels = [
    { pct: '20%', color: '#f43f5e', text: 'Weak' },
    { pct: '40%', color: '#fb923c', text: 'Fair' },
    { pct: '60%', color: '#facc15', text: 'Good' },
    { pct: '80%', color: '#06b6d4', text: 'Strong' },
    { pct: '100%', color: '#10b981', text: 'Excellent' },
  ];
  const level = levels[Math.min(score, levels.length - 1)];
  fill.style.width = password.length ? level.pct : '0%';
  fill.style.background = level.color;
  label.textContent = password.length ? level.text : '';
  label.style.color = level.color;
}

async function handleAuthSubmit(event) {
  event.preventDefault();
  hideError();

  const email = document.getElementById('email').value.trim();
  const password = document.getElementById('password').value;
  const displayName = document.getElementById('display_name').value.trim();
  const confirmPassword = document.getElementById('password_confirm').value;
  const submitBtn = document.getElementById('submit-btn');

  if (authMode === 'signup') {
    if (!displayName) {
      showError('Please enter your display name.');
      return;
    }
    if (password !== confirmPassword) {
      showError('Passwords do not match.');
      return;
    }
    if (!document.getElementById('terms_accept').checked) {
      showError('Please accept the Terms of Service to continue.');
      return;
    }
  }

  const url = authMode === 'signup' ? '/api/auth/signup' : '/api/auth/login';
  const body = authMode === 'signup'
    ? { email, password, display_name: displayName }
    : { email, password };

  submitBtn.disabled = true;
  const originalText = submitBtn.textContent;
  submitBtn.textContent = authMode === 'signup' ? 'Creating Account…' : 'Signing In…';

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(body),
    });

    const data = await res.json();
    if (res.ok && data.success) {
      setAuthToken(data.token);
      redirectAfterAuth();
    } else {
      const detail = data.detail;
      showError(typeof detail === 'string' ? detail : 'Authentication failed. Please try again.');
    }
  } catch (_) {
    showError('Unable to connect to the server.');
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = originalText;
  }
}

function redirectAfterAuth() {
  const params = new URLSearchParams(window.location.search);
  const redirect = params.get('redirect');
  window.location.href = redirect === 'admin' ? '/admin' : '/';
}

function continueWithGoogle() {
  if (!googleEnabled) {
    showError('Google sign-in is not configured yet. Please use email authentication or contact your administrator.');
    return;
  }
  window.location.href = '/api/auth/google/login';
}

async function handleOAuthReturn() {
  const params = new URLSearchParams(window.location.search);
  if (params.get('oauth') !== 'success') return;

  const user = await syncAuthFromSession();
  if (user) {
    redirectAfterAuth();
  } else {
    showError('Google sign-in completed but session could not be established. Please try again.');
  }
}

window.addEventListener('DOMContentLoaded', async () => {
  initAuthNav('auth-nav');

  const params = new URLSearchParams(window.location.search);
  if (params.get('mode') === 'signup') setAuthMode('signup');

  const passwordInput = document.getElementById('password');
  passwordInput.addEventListener('input', () => {
    if (authMode === 'signup') updatePasswordStrength(passwordInput.value);
  });

  try {
    const res = await fetch('/api/meta');
    if (res.ok) {
      const meta = await res.json();
      googleEnabled = !!meta.google_oauth_enabled;
      const googleBtn = document.getElementById('google-login-btn');
      if (!googleEnabled) {
        googleBtn.classList.add('oauth-disabled');
        googleBtn.title = 'Google sign-in not configured';
      }
    }
  } catch (_) { /* ignore */ }

  const error = params.get('error');
  const reason = params.get('reason');

  if (error === 'google_auth_failed') {
    showError('Google sign-in failed. Please try again or use your email.');
  }
  if (reason === 'admin_required') {
    showError('Admin credentials required to view that page.');
  }

  await handleOAuthReturn();
});
