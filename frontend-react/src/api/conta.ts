import apiClient, { TIMEOUTS } from './client';

/** Planos, assinatura, preferências e direitos LGPD do titular. */

export interface Plano {
  plan_id: 'free' | 'pro' | 'total' | string;
  name: string;
  price_brl_monthly: number;
  tagline: string;
  features: string[];
}

export interface Assinatura {
  plan: string;
  status: string;
  cancel_at_period_end: boolean;
  current_period_end: string | null;
  usage: { key: string; used: number; limit: number; window: 'daily' | 'monthly' | string }[];
  /** false = Stripe não configurado neste ambiente (não dá para assinar) */
  billing_enabled: boolean;
  /** false = limites em modo observação (nada é bloqueado ainda) */
  enforcement_enabled: boolean;
}

export type Canal = 'email' | 'in_app' | 'push';
export type Frequencia = 'realtime' | 'daily' | 'weekly' | 'off';

export interface Preferencias {
  notification_channels: Canal[];
  notification_frequency: Frequencia;
  digest_time: string; // 'HH:MM'
  subscription_status: 'active' | 'paused' | 'cancelled';
  paused_until: string | null;
  is_default: boolean;
}

/** Frase que o backend exige para apagar os dados (LGPD art. 18 VI). */
export const FRASE_DE_EXCLUSAO = 'EXCLUIR MEUS DADOS';

export const contaApi = {
  planos: async (): Promise<Plano[]> => (await apiClient.get('/billing/plans')).data,
  assinatura: async (userId: string): Promise<Assinatura> => (await apiClient.get(`/billing/subscription/${userId}`)).data,
  checkout: async (userId: string, plano: 'pro' | 'total'): Promise<string> => {
    const { data } = await apiClient.post(`/billing/checkout/${userId}`, { plan: plano });
    if (!data?.checkout_url) throw new Error('O Stripe não devolveu o link de pagamento.');
    return data.checkout_url;
  },
  portal: async (userId: string): Promise<string> => {
    const { data } = await apiClient.post(`/billing/portal/${userId}`);
    if (!data?.portal_url) throw new Error('O Stripe não devolveu o link do portal.');
    return data.portal_url;
  },

  preferencias: async (userId: string): Promise<Preferencias> => (await apiClient.get(`/settings/${userId}`)).data,
  salvarPreferencias: async (userId: string, p: Partial<Omit<Preferencias, 'is_default'>>): Promise<Preferencias> =>
    (await apiClient.put(`/settings/${userId}`, p)).data,

  /** Baixa o JSON de portabilidade (LGPD art. 18 V) como arquivo. */
  exportarDados: async (userId: string): Promise<void> => {
    const { data } = await apiClient.get(`/privacy/export/${userId}`, { timeout: TIMEOUTS.lento });
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `hive-meus-dados-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
  /** Irreversível: apaga conta e dados. Exige a frase exata. */
  excluirDados: async (userId: string, confirmacao: string): Promise<void> => {
    await apiClient.delete(`/privacy/erase/${userId}`, { data: { confirm: confirmacao }, timeout: TIMEOUTS.lento });
  },
};

export const ROTULO_USO: Record<string, string> = {
  chat_messages: 'Mensagens de IA',
  purchase_checks: 'Consultas de Compra Inteligente',
  connected_banks: 'Bancos conectados',
  negotiator_scripts: 'Roteiros do Negociador',
};

export const ROTULO_JANELA: Record<string, string> = { daily: 'hoje', monthly: 'neste mês' };
