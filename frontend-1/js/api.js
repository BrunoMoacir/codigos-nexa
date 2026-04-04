/**
 * api.js — Camada de chamadas autenticadas à API do Nexa Backend (Railway)
 *
 * Espelha 100% as rotas de /frontend-react/src/api/nexa.ts + client.ts
 *
 * BASE_URL:
 *   - Produção (Railway):  https://codigos-nexa-production.up.railway.app/api/v1
 *   - Desenvolvimento:     http://localhost:8000/api/v1  (se USAR_PROXY=false)
 */

// ─── CONFIGURAÇÃO ─────────────────────────────────────────────────────────────
// Em produção no Railway, usa a URL direta.
// Em localhost, usa a URL direta também (o backend no Railway já deve ter CORS=*).
const BASE_URL = 'https://codigos-nexa-production.up.railway.app/api/v1';

// ─── FETCH AUTENTICADO ────────────────────────────────────────────────────────

async function apiFetch(path, options = {}) {
  const token = localStorage.getItem('jwt_token');
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };

  let res;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers,
      mode: 'cors',
    });
  } catch (networkErr) {
    throw new Error('Sem conexão com o servidor. Verifique sua internet.');
  }

  if (res.status === 401) {
    localStorage.removeItem('jwt_token');
    localStorage.removeItem('user_id');
    if (typeof showScreen === 'function') showScreen('login');
    throw new Error('Sessão expirada. Faça login novamente.');
  }

  if (res.status === 404) {
    throw Object.assign(new Error('Não encontrado'), { status: 404 });
  }

  if (res.status === 503) {
    throw new Error('Serviço temporariamente indisponível. Tente novamente em instantes.');
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const msg = body.detail || body.message || `Erro ${res.status}`;
    throw new Error(msg);
  }

  if (res.status === 204) return null;
  return res.json();
}

// ─── HELPER: query string ─────────────────────────────────────────────────────
function qs(params = {}) {
  const p = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join('&');
  return p ? `?${p}` : '';
}

// ─── API OBJECT ───────────────────────────────────────────────────────────────

const api = {

  // ── AUTH ──────────────────────────────────────────────────────────────────

  /**
   * POST /auth/token  →  { access_token, user_id, full_name }
   * OAuth2 Password Flow (form-urlencoded)
   */
  login: async (email, password) => {
    const formData = new URLSearchParams();
    formData.append('username', email);
    formData.append('password', password);

    let res;
    try {
      res = await fetch(`${BASE_URL}/auth/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: formData,
        mode: 'cors',
      });
    } catch (networkErr) {
      throw new Error('Sem conexão com o servidor.');
    }

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || 'E-mail ou senha incorretos.');
    }
    return res.json();
  },

  /** POST /auth/register */
  register: async (email, password, fullName) => {
    let res;
    try {
      res = await fetch(`${BASE_URL}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, full_name: fullName }),
        mode: 'cors',
      });
    } catch (networkErr) {
      throw new Error('Sem conexão com o servidor.');
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || 'Erro ao criar conta.');
    }
    return res.json();
  },

  // ── FORECAST ──────────────────────────────────────────────────────────────
  /** GET /forecast/{user_id} */
  getForecast: (userId) => apiFetch(`/forecast/${userId}`),

  /** GET /budget/{user_id}?monthly_income= */
  getBudget: (userId, monthlyIncome) =>
    apiFetch(`/budget/${userId}${qs({ monthly_income: monthlyIncome })}`),

  // ── TRANSAÇÕES ────────────────────────────────────────────────────────────
  /** GET /transactions/{user_id}?limit=&offset= */
  getTransactions: (userId, limit = 300, offset = 0) =>
    apiFetch(`/transactions/${userId}${qs({ limit, offset })}`),

  // ── METAS ─────────────────────────────────────────────────────────────────
  /** GET /goals/{user_id}?status=&limit=&offset= */
  getGoals: (userId, status = 'ACTIVE', limit = 50, offset = 0) =>
    apiFetch(`/goals/${userId}${qs({ status, limit, offset })}`),

  /** GET /goals/{user_id}/{goal_id} */
  getGoal: (userId, goalId) => apiFetch(`/goals/${userId}/${goalId}`),

  /** POST /goals/{user_id} */
  createGoal: (userId, data) =>
    apiFetch(`/goals/${userId}`, { method: 'POST', body: JSON.stringify(data) }),

  /** PATCH /goals/{user_id}/{goal_id}/progress */
  updateGoalProgress: (userId, goalId, data) =>
    apiFetch(`/goals/${userId}/${goalId}/progress`, { method: 'PATCH', body: JSON.stringify(data) }),

  /** DELETE /goals/{user_id}/{goal_id} */
  abandonGoal: (userId, goalId) =>
    apiFetch(`/goals/${userId}/${goalId}`, { method: 'DELETE' }),

  // ── NOTIFICAÇÕES ──────────────────────────────────────────────────────────
  /** GET /notifications/{user_id}?monthly_income=&include_info= */
  getNotifications: (userId, monthlyIncome, includeInfo = true) =>
    apiFetch(`/notifications/${userId}${qs({
      ...(monthlyIncome && monthlyIncome > 0 ? { monthly_income: monthlyIncome } : {}),
      include_info: includeInfo,
    })}`),

  // ── ALERTAS ───────────────────────────────────────────────────────────────
  /** GET /alerts/{user_id} */
  getAlerts: (userId) => apiFetch(`/alerts/${userId}`),

  // ── ASSINATURAS ───────────────────────────────────────────────────────────
  /** GET /subscriptions/{user_id} */
  getSubscriptions: (userId) => apiFetch(`/subscriptions/${userId}`),

  // ── HEALTH SCORE ──────────────────────────────────────────────────────────
  /** GET /health-score/history/{user_id}?months= */
  getHealthScoreHistory: (userId, months = 6) =>
    apiFetch(`/health-score/history/${userId}${qs({ months })}`),

  // ── F5 — RAIO-X CUSTOS BANCÁRIOS ─────────────────────────────────────────
  /** GET /costs/raio-x/{user_id} */
  getBankCosts: (userId) => apiFetch(`/costs/raio-x/${userId}`),

  // ── F7 — ANÁLISE DE COMPRA ────────────────────────────────────────────────
  /** POST /purchase/analyze */
  analyzePurchase: (payload) =>
    apiFetch('/purchase/analyze', { method: 'POST', body: JSON.stringify(payload) }),

  // ── NEGOCIADOR ────────────────────────────────────────────────────────────
  /** POST /negotiator/generate-script */
  generateNegotiationScript: (payload) =>
    apiFetch('/negotiator/generate-script', { method: 'POST', body: JSON.stringify(payload) }),

  // ── RELATÓRIO FISCAL ─────────────────────────────────────────────────────
  /** GET /fiscal-report/{user_id}?year=&month= */
  getFiscalReport: (userId, year, month) =>
    apiFetch(`/fiscal-report/${userId}${qs({ year, month })}`),

  /** GET /fiscal-report/{user_id}/mixed-use?year=&month= */
  getFiscalMixedUse: (userId, year, month) =>
    apiFetch(`/fiscal-report/${userId}/mixed-use${qs({ year, month })}`),

  // ── COMPARATIVO DE PARES ─────────────────────────────────────────────────
  /** GET /peers/compare/{user_id}?monthly_income=&history_months= */
  getPeerComparison: (userId, monthlyIncome, historyMonths = 3) =>
    apiFetch(`/peers/compare/${userId}${qs({
      history_months: historyMonths,
      ...(monthlyIncome && monthlyIncome > 0 ? { monthly_income: monthlyIncome } : {}),
    })}`),

  // ── OPTIMIZER ─────────────────────────────────────────────────────────────
  /** GET /optimizer/portfolio/{user_id}?max_cards=&monthly_income= */
  getOptimizerPortfolio: (userId, maxCards, monthlyIncome) =>
    apiFetch(`/optimizer/portfolio/${userId}${qs({
      max_cards: maxCards,
      ...(monthlyIncome ? { monthly_income: monthlyIncome } : {}),
    })}`),

  /** GET /optimizer/cards */
  getOptimizerCards: () => apiFetch('/optimizer/cards'),

  /** GET /optimizer/opportunity-cost?user_id=&current_card_id=&months= */
  getOptimizerOpportunityCost: (userId, currentCardId, months = 3) =>
    apiFetch(`/optimizer/opportunity-cost${qs({ user_id: userId, current_card_id: currentCardId, months })}`),

  /** GET /optimizer/promotions */
  getOptimizerPromotions: () => apiFetch('/optimizer/promotions'),

  // ── F13 — ARCHITECT ───────────────────────────────────────────────────────
  /** POST /architect/simulate */
  architectSimulate: (payload) =>
    apiFetch('/architect/simulate', { method: 'POST', body: JSON.stringify(payload) }),

  /** GET /architect/simulations?user_id=&limit= */
  architectListSimulations: (userId, limit = 8) =>
    apiFetch(`/architect/simulations${qs({ user_id: userId, limit })}`),

  /** GET /architect/metrics?user_id= */
  architectMetrics: (userId) =>
    apiFetch(`/architect/metrics${qs({ user_id: userId })}`),

  // ── CHAT ─────────────────────────────────────────────────────────────────
  /** POST /chat/ */
  sendChatMessage: (userId, message) =>
    apiFetch('/chat/', { method: 'POST', body: JSON.stringify({ user_id: userId, message }) }),

  /** GET /chat/history?user_id=&limit= */
  getChatHistory: (userId, limit = 50) =>
    apiFetch(`/chat/history${qs({ user_id: userId, limit })}`),

  // ── PLUGGY ────────────────────────────────────────────────────────────────
  /** POST /pluggy/connect-token */
  createPluggyToken: () => apiFetch('/pluggy/connect-token', { method: 'POST' }),

  /** GET /pluggy/items */
  getPluggyItems: () => apiFetch('/pluggy/items'),

  /** POST /pluggy/sandbox?perf_multiplier= */
  createSandboxItem: (perfMultiplier) =>
    apiFetch(`/pluggy/sandbox${qs({ perf_multiplier: perfMultiplier })}`, { method: 'POST' }),

  /** POST /pluggy/sync */
  syncPluggyTransactions: () => apiFetch('/pluggy/sync', { method: 'POST' }),

  // ── SHADOW INVOICES ───────────────────────────────────────────────────────
  /** GET /shadow-invoices/{user_id} */
  getShadowInvoices: (userId) => apiFetch(`/shadow-invoices/${userId}`),
};

window.api = api;
