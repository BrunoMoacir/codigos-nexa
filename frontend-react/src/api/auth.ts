import apiClient from './client';
import { session } from './session';
import type { LoginResponse, RegisterRequest, RegisterResponse } from './types';

/**
 * Autenticação real contra o backend.
 *
 * O LoginPage não chamava nada disto: validava campo vazio, pedia um código
 * de 6 dígitos que nenhum servidor emitia, aceitava qualquer um e navegava.
 * Nenhum JWT era salvo, e toda tela rodava em demonstração.
 */

/** E-mail como o backend o guarda: sem espaços e em minúsculas. */
export function normalizarEmail(email: string): string {
  return email.trim().toLowerCase();
}

/** Login OAuth2 password flow (form-urlencoded, como o FastAPI exige). */
export async function login(email: string, password: string): Promise<LoginResponse> {
  const form = new URLSearchParams();
  const usuario = normalizarEmail(email);
  form.append('username', usuario);
  form.append('password', password);
  const { data } = await apiClient.post<LoginResponse>('/auth/token', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  session.save(data, usuario);
  return data;
}

/** Cria a conta e já entra nela — o /register não devolve tokens. */
export async function register(payload: RegisterRequest): Promise<RegisterResponse> {
  const corpo = { ...payload, email: normalizarEmail(payload.email) };
  const { data } = await apiClient.post<RegisterResponse>('/auth/register', corpo);
  await login(corpo.email, payload.password);
  return data;
}

/**
 * Sai de verdade: revoga no servidor o access E o refresh desta sessão.
 * O logout antigo só limpava o navegador — o token seguia válido até expirar,
 * e o refresh de 14 dias ainda gerava sessão nova.
 */
/**
 * Sem cancelar o push, o próximo usuário do mesmo navegador continuava
 * recebendo os alertas financeiros de quem saiu. Melhor esforço: não segura
 * o logout se o navegador ou o servidor falharem.
 */
async function cancelarPush(): Promise<void> {
  try {
    const { unsubscribeFromPush } = await import('../pwa/push');
    await Promise.race([unsubscribeFromPush(), new Promise((r) => setTimeout(r, 3000))]);
  } catch {
    /* sem suporte a push ou sem inscrição */
  }
}

async function limparWidget(): Promise<void> {
  try {
    const { limparWidgetNativo } = await import('../native/widgetNativo');
    await limparWidgetNativo(session.userId);
  } catch {
    /* fora do app nativo ou plugin indisponível */
  }
}

export async function logout(): Promise<void> {
  const refresh = session.refreshToken;
  await cancelarPush();
  await limparWidget();
  try {
    if (session.accessToken) {
      await apiClient.post('/auth/logout', refresh ? { refresh_token: refresh } : {});
    }
  } catch {
    /* sessão já inválida no servidor: limpar o navegador basta */
  } finally {
    session.clear();
  }
}

/** Encerra a sessão em TODOS os aparelhos (troca de senha não é exigida). */
export async function logoutAll(): Promise<void> {
  await cancelarPush();
  await limparWidget();
  try {
    await apiClient.post('/auth/logout-all');
  } finally {
    session.clear();
  }
}

export async function forgotPassword(email: string): Promise<void> {
  await apiClient.post('/auth/forgot-password', { email: normalizarEmail(email) });
}

export async function resetPassword(token: string, newPassword: string): Promise<void> {
  await apiClient.post('/auth/reset-password', { token, new_password: newPassword });
}

export async function verifyEmail(token: string): Promise<void> {
  await apiClient.post('/auth/verify-email', { token });
}

export async function resendVerification(email: string): Promise<void> {
  await apiClient.post('/auth/resend-verification', { email: normalizarEmail(email) });
}

export const isAuthenticated = (): boolean => session.isActive;

export const getUserId = (): string | null => session.userId || null;
