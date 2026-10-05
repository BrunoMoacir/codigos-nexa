/**
 * Sessão do usuário — fonte única das chaves de localStorage.
 *
 * As páginas liam `localStorage.getItem('user_id')` direto, cada uma do seu
 * jeito, e o refresh token que o backend devolve no login era jogado fora.
 * Tudo que é sessão passa por aqui: quem precisa do usuário chama
 * `getUserId()`, quem precisa saber se mudou escuta `onSessionChange`.
 *
 * As chaves antigas (`jwt_token`, `user_id`, `user_name`, `user_email`) foram
 * mantidas de propósito — o widget fixado na homescreen e o service worker as
 * leem, e trocar o nome derrubaria sessões abertas no deploy.
 */

const KEYS = {
  access: 'jwt_token',
  refresh: 'refresh_token',
  userId: 'user_id',
  name: 'user_name',
  email: 'user_email',
} as const;

/** Chaves de cache local que pertencem ao usuário e saem junto no logout. */
const USER_SCOPED_PREFIXES = [
  'nexa_data_origin', 'hive_chat_', 'hive_cache_',
  // versão anterior do chat guardava a conversa inteira no aparelho com estas
  // chaves, e o logout não as limpava: o próximo usuário do navegador via tudo
  'hive-chat:', 'hive-session:',
];

const EVENT = 'hive:session';

function read(key: string): string {
  try {
    return localStorage.getItem(key) || '';
  } catch {
    return '';
  }
}

function write(key: string, value: string | null | undefined): void {
  try {
    if (value) localStorage.setItem(key, value);
    else localStorage.removeItem(key);
  } catch {
    /* modo privado / storage bloqueado: a sessão vive só em memória */
  }
}

export interface SessionTokens {
  access_token: string;
  refresh_token?: string | null;
  user_id: string;
  full_name?: string | null;
}

export const session = {
  get accessToken(): string {
    return read(KEYS.access);
  },
  get refreshToken(): string {
    return read(KEYS.refresh);
  },
  get userId(): string {
    return read(KEYS.userId);
  },
  get userName(): string {
    return read(KEYS.name);
  },
  get userEmail(): string {
    return read(KEYS.email);
  },
  /** Há como continuar a sessão (access válido ou refresh para renová-lo). */
  get isActive(): boolean {
    return Boolean(read(KEYS.userId) && (read(KEYS.access) || read(KEYS.refresh)));
  },

  save(tokens: SessionTokens, email?: string): void {
    write(KEYS.access, tokens.access_token);
    if (tokens.refresh_token) write(KEYS.refresh, tokens.refresh_token);
    write(KEYS.userId, tokens.user_id);
    if (tokens.full_name !== undefined) write(KEYS.name, tokens.full_name || '');
    if (email) write(KEYS.email, email);
    window.dispatchEvent(new Event(EVENT));
  },

  /** Atualiza só o par de tokens (rotação do refresh). */
  rotate(access: string, refresh?: string | null): void {
    write(KEYS.access, access);
    if (refresh) write(KEYS.refresh, refresh);
  },

  clear(): void {
    Object.values(KEYS).forEach((k) => write(k, null));
    try {
      for (let i = localStorage.length - 1; i >= 0; i--) {
        const k = localStorage.key(i);
        if (k && USER_SCOPED_PREFIXES.some((p) => k.startsWith(p))) localStorage.removeItem(k);
      }
      localStorage.removeItem('auth-storage'); // store zustand legado
    } catch {
      /* ignore */
    }
    window.dispatchEvent(new Event(EVENT));
  },
};

/** O user_id da sessão, ou string vazia — nunca `null`. */
export function getUserId(): string {
  return session.userId;
}

export function onSessionChange(fn: () => void): () => void {
  window.addEventListener(EVENT, fn);
  window.addEventListener('storage', fn); // outra aba fez login/logout
  return () => {
    window.removeEventListener(EVENT, fn);
    window.removeEventListener('storage', fn);
  };
}
