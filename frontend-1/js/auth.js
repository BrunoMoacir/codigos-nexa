/**
 * auth.js — Autenticação espelhando /frontend-react/src/api/auth.ts
 *
 * Salva no localStorage (mesmas chaves do React):
 *   jwt_token    — Bearer token para todas as requisições
 *   user_id      — UUID do usuário
 *   user_email   — email (usado como username no OAuth2)
 *   user_name    — full_name retornado pela API
 */

const auth = {
  /**
   * Login OAuth2 Password Flow
   * POST /auth/token  →  { access_token, user_id, full_name? }
   */
  login: async (email, password) => {
    const data = await api.login(email, password);

    // Espelha exatamente auth.ts:20-25
    localStorage.setItem('jwt_token',  data.access_token);
    localStorage.setItem('user_id',    data.user_id);
    localStorage.setItem('user_email', email);          // username é o email
    if (data.full_name) {
      localStorage.setItem('user_name', data.full_name);
    }

    return data;
  },

  /**
   * Cadastro de novo usuário
   * POST /auth/register
   */
  register: async (email, password, fullName) => {
    const data = await api.register(email, password, fullName);
    return data;
  },

  /**
   * Logout — limpa exatamente as mesmas chaves do auth.ts:42-46
   */
  logout: () => {
    localStorage.removeItem('jwt_token');
    localStorage.removeItem('user_id');
    localStorage.removeItem('user_name');
    localStorage.removeItem('user_email');
    // Limpar caches globais
    window._forecastData = null;
    window._budgetData   = null;
    window._txData       = [];
    window._shadowData   = [];
    // Ir para tela de login
    if (typeof showScreen === 'function') showScreen('login');
  },

  /** Verificar se autenticado (auth.ts:51-53) */
  isAuthenticated: () => !!localStorage.getItem('jwt_token'),

  /** Obter user_id (auth.ts:58-60) */
  getUserId: () => localStorage.getItem('user_id'),

  /** Obter nome do usuário */
  getUserName: () => {
    const name  = localStorage.getItem('user_name')  || '';
    const email = localStorage.getItem('user_email') || '';
    const first = name.split(' ')[0];
    return first || email.split('@')[0] || 'Usuário';
  },

  /** Obter email */
  getUserEmail: () => localStorage.getItem('user_email') || '',
};

// ─── HANDLERS DE LOGIN / CADASTRO ────────────────────────────────────────────

async function handleLogin(event) {
  event?.preventDefault();
  const email    = document.getElementById('login-email')?.value?.trim();
  const password = document.getElementById('login-pass')?.value;
  const errEl    = document.getElementById('login-error');
  const btn      = document.getElementById('login-btn');

  if (!email || !password) {
    if (errEl) errEl.textContent = 'Preencha e-mail e senha.';
    return;
  }

  btn.disabled    = true;
  btn.textContent = 'Entrando...';
  if (errEl) errEl.textContent = '';

  try {
    await auth.login(email, password);
    // Inicializar app após login
    await initApp();
  } catch (err) {
    if (errEl) errEl.textContent = err.message || 'Erro no login.';
    btn.disabled    = false;
    btn.textContent = 'Entrar';
  }
}

async function handleRegister(event) {
  event?.preventDefault();
  const name     = document.getElementById('reg-name')?.value?.trim();
  const email    = document.getElementById('reg-email')?.value?.trim();
  const password = document.getElementById('reg-pass')?.value;
  const errEl    = document.getElementById('reg-error');
  const btn      = document.getElementById('reg-btn');

  if (!name || !email || !password) {
    if (errEl) errEl.textContent = 'Preencha todos os campos.';
    return;
  }
  if (password.length < 8) {
    if (errEl) errEl.textContent = 'Senha deve ter no mínimo 8 caracteres.';
    return;
  }

  btn.disabled    = true;
  btn.textContent = 'Cadastrando...';
  if (errEl) errEl.textContent = '';

  try {
    await auth.register(email, password, name);
    // Após cadastro, logar automaticamente
    await auth.login(email, password);
    await initApp();
  } catch (err) {
    if (errEl) errEl.textContent = err.message || 'Erro no cadastro.';
    btn.disabled    = false;
    btn.textContent = 'Cadastrar';
  }
}

window.auth           = auth;
window.handleLogin    = handleLogin;
window.handleRegister = handleRegister;
