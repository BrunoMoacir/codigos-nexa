import axios from 'axios';
import type { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import { session } from './session';

/**
 * Cliente HTTP único da aplicação.
 *
 * Base URL: `VITE_API_URL` quando definida; senão o caminho relativo
 * `/api/v1`, que o Vite (dev) e o nginx (produção) encaminham ao backend. O
 * fallback antigo era um backend Railway que não existe mais — inclusive em
 * `npm run dev`, que nunca falava com o backend local.
 */
export const API_BASE_URL = String(import.meta.env.VITE_API_URL || '').trim() || '/api/v1';

/**
 * Orçamentos de tempo por tipo de chamada.
 *
 * O timeout único de 15 s era menor que o trabalho do próprio produto: o chat
 * encadeia 2–3 ferramentas e tem orçamento de 60 s no servidor (LLM em 45 s),
 * o Architect leva 12–15 s, o Negociador chama um LLM por oportunidade. O
 * axios desistia, a tela dizia "backend inativo", e o servidor terminava,
 * gravava e consumia a cota do usuário mesmo assim.
 */
export const TIMEOUTS = {
  padrao: 30_000,
  lento: 75_000,   // architect, negociador, defesa (consulta o BACEN)
  chat: 95_000,    // acima dos 60 s do servidor + rede: quem desiste é o backend, com 504 legível
} as const;

const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: TIMEOUTS.padrao,
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = session.accessToken;
  if (token && config.headers && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Renovação do access token ──────────────────────────────────────────────
//
// O access dura 30 min; o refresh, 14 dias, e é de uso único (rotação). Sem
// isto, todo usuário era jogado para /login a cada meia hora — inclusive o
// widget fixado na homescreen, que atualiza de 15 em 15 min.
//
// Fila única: várias requisições que tomam 401 ao mesmo tempo esperam UMA
// renovação. Duas renovações concorrentes usariam o mesmo refresh token, e a
// segunda seria lida pelo backend como reuso de token rotacionado (vazamento).

const AUTH_PATHS = ['/auth/token', '/auth/register', '/auth/refresh', '/auth/forgot-password',
  '/auth/reset-password', '/auth/verify-email', '/auth/resend-verification'];

let renovando: Promise<string | null> | null = null;

async function renovarAccess(): Promise<string | null> {
  const refresh = session.refreshToken;
  if (!refresh) return null;
  try {
    // axios cru: não passa pelos interceptors (evita laço 401 → refresh → 401)
    const { data } = await axios.post(`${API_BASE_URL}/auth/refresh`, { refresh_token: refresh }, {
      timeout: TIMEOUTS.padrao,
      headers: { 'Content-Type': 'application/json' },
    });
    session.rotate(data.access_token, data.refresh_token);
    return data.access_token as string;
  } catch {
    return null;
  }
}

function irParaLogin(): void {
  session.clear();
  const aqui = window.location.pathname + window.location.search;
  if (!window.location.pathname.startsWith('/login')) {
    window.location.href = `/login?next=${encodeURIComponent(aqui)}`;
  }
}

type RetryConfig = InternalAxiosRequestConfig & { _hiveRetry?: boolean };

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as RetryConfig | undefined;
    const status = error.response?.status;
    const url = config?.url || '';
    const ehAuth = AUTH_PATHS.some((p) => url.startsWith(p));

    // O 401 do próprio login ("senha errada") é resposta, não sessão expirada.
    if (status !== 401 || !config || ehAuth) return Promise.reject(error);

    if (!config._hiveRetry) {
      config._hiveRetry = true;
      renovando = renovando || renovarAccess().finally(() => { renovando = null; });
      const novo = await renovando;
      if (novo) {
        config.headers = config.headers || {};
        config.headers.Authorization = `Bearer ${novo}`;
        return apiClient(config);
      }
    }
    irParaLogin();
    return Promise.reject(error);
  },
);

export default apiClient;
