import apiClient from '../api/client';
import { apiBaseAbsoluta } from './api';
import { HiveNativo } from './hiveNativo';
import { ehNativo } from './plataforma';

/**
 * Widget de tela inicial. O app pede ao backend um token de escopo restrito
 * (só lê a margem do dia, 90 dias, um por aparelho, revogável) e entrega ao
 * código nativo. O JWT e o refresh da sessão NUNCA saem do WebView.
 */

const CHAVE_APARELHO = 'hive_aparelho_id';

/** Identificador deste aparelho (não é dado pessoal; sobrevive ao logout). */
export function idDoAparelho(): string {
  try {
    const salvo = localStorage.getItem(CHAVE_APARELHO);
    if (salvo && /^[A-Za-z0-9_-]{8,100}$/.test(salvo)) return salvo;
    const novo = globalThis.crypto?.randomUUID?.() || `aparelho-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
    localStorage.setItem(CHAVE_APARELHO, novo);
    return novo;
  } catch {
    return `aparelho-${Date.now()}`;
  }
}

let configuradoPara: string | null = null;

export async function configurarWidgetNativo(userId: string): Promise<void> {
  if (!ehNativo() || !userId || configuradoPara === userId) return;
  const { data } = await apiClient.post(`/widget/token/${userId}`, { device_id: idDoAparelho() });
  await HiveNativo.configurarWidget({ apiBase: apiBaseAbsoluta(), token: String(data.token) });
  configuradoPara = userId;
}

/** Logout: revoga o token no servidor e apaga a credencial do aparelho. Melhor esforço. */
export async function limparWidgetNativo(userId: string): Promise<void> {
  if (!ehNativo()) return;
  configuradoPara = null;
  try {
    if (userId) {
      await apiClient.request({ method: 'DELETE', url: `/widget/token/${userId}`, data: { device_id: idDoAparelho() } });
    }
  } catch {
    /* sessão já inválida: o token morre no "sair de todos" ou expira */
  }
  try {
    await HiveNativo.limparWidget();
  } catch {
    /* plugin indisponível */
  }
}
