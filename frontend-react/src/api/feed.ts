import apiClient from './client';

/**
 * Contratos do Feed (aba Oportunidades).
 *
 * O Feed lia só GET /alerts e classificava a severidade por `type` — que é o
 * TIPO do alerta (NEGATIVE_BALANCE, TOKEN_EXPIRY…); a severidade vem em
 * `level`. Todo alerta caía em "Oportunidades" e o KPI de alertas ficava em 0.
 * A fonte principal agora é o motor de notificações (/notifications), com
 * prioridade, ação e fingerprint para os eventos de interação.
 */

export type Prioridade = 'CRITICAL' | 'WARNING' | 'INFO';

/** GET /notifications/{uid} — `id` = fingerprint estável do card. */
export interface Notificacao {
  id: string;
  fingerprint: string;
  type: string;
  priority: Prioridade;
  title: string;
  message: string;
  action_hint?: string | null;
  action_route?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  seen: boolean;
}

export interface Notificacoes {
  total: number;
  by_priority: Record<Prioridade, number>;
  notifications: Notificacao[];
}

/** GET /alerts/{uid} — alertas operacionais (saldo, conexão, compromisso). */
export interface Alerta {
  id: string;
  type: string;
  level: Prioridade;
  title: string;
  message: string;
  due_date?: string | null;
  action_url?: string | null; // rota da interface (ex.: /connections)
}

export interface Alertas {
  alerts: Alerta[];
  total_count: number;
  critical_count: number;
  warning_count: number;
}

export type EventoNotificacao = 'shown' | 'tapped' | 'dismissed' | 'acted';

export interface OportunidadeItem {
  rank: number;
  bank_name: string;
  product_type: string;
  cdi_pct: number;
  annual_rate_net_pct: number;
  is_exempt: boolean;
  liquidity: string;       // 'daily' | '12m' | '24m' | …
  liquidity_days: number;
  monthly_gain_brl: number;
  annual_gain_brl: number;
  fgc_covered: boolean;
  promotional: boolean;
  cdi_pct_max: number | null;
  steps: string[];
}

/** GET /opportunities/{uid} */
export interface Radar {
  idle_amount: number;
  gross_idle_amount: number;
  emergency_reserve: number;  // META da reserva (N meses de gasto)
  reserve_protected: number;  // quanto do saldo ficou de fato protegido
  reserve_months_applied: number;
  monthly_loss_in_checking: number;
  cdi_annual_pct: number;
  top_opportunity: OportunidadeItem | null;
  recommendation: string;
  idle_detection_status: 'CONFIRMED' | 'PRELIMINARY' | 'NO_IDLE_MONEY' | 'NO_DATA';
  idle_source?: 'REAL_BALANCE' | 'CASHFLOW_PROXY';
  disclaimer?: string;
}

export interface PoupancaVsCdi {
  status: string;
  severity: string;
  savings_annual_pct: number;
  cdi_annual_pct: number;
  estimated_loss_annual_brl: number;
  amount_reference_brl: number;
}

export interface Comparativo {
  amount: number;
  holding_months: number;
  cdi_annual_pct: number;
  savings_annual_pct: number;
  entries: { label: string; investment_type: string; annual_rate_net_pct: number; net_yield_brl: number; is_exempt: boolean; fgc_covered: boolean; liquidity: string; fees_brl: number }[];
  winner: string;
  winner_vs_savings_brl: number;
  recommendation: string;
  disclaimer: string;
}

export interface BancoIdeal {
  amount_simulated: number;
  ranking: { bank_name: string; match_score: number; reasons: string[]; is_user_current_bank: boolean; projected_annual_gain_brl: number; projected_monthly_fee_brl: number; top_card_name: string | null }[];
  user_current_bank: string | null;
  user_current_bank_rank: number | null;
  best_bank: string | null;
  switch_recommendation: string;
  disclaimer: string;
}

export const feedApi = {
  notificacoes: async (userId: string, includeInfo = true): Promise<Notificacoes> => {
    const { data } = await apiClient.get(`/notifications/${userId}`, { params: { include_info: includeInfo } });
    return data;
  },
  /** Fire-and-forget: falha de telemetria não pode quebrar a tela. */
  evento: async (userId: string, n: Pick<Notificacao, 'fingerprint' | 'type'>, evento: EventoNotificacao) => {
    try {
      await apiClient.post(`/notifications/${userId}/events`, {
        fingerprint: n.fingerprint,
        notification_type: n.type,
        event_type: evento,
      });
    } catch {
      /* ignorado de propósito */
    }
  },
  alertas: async (userId: string): Promise<Alertas> => {
    const { data } = await apiClient.get(`/alerts/${userId}`);
    return data;
  },
  dispensarAlerta: async (userId: string, alertId: string): Promise<void> => {
    await apiClient.delete(`/alerts/${userId}/${encodeURIComponent(alertId)}`);
  },
  radar: async (userId: string, holdingMonths = 12): Promise<Radar> => {
    const { data } = await apiClient.get(`/opportunities/${userId}`, { params: { holding_months: holdingMonths } });
    return data;
  },
  /** Tesouro × CDB × poupança para um valor e prazo. */
  comparativo: async (valor: number, meses: number): Promise<Comparativo> => {
    const { data } = await apiClient.get('/opportunities/treasury-vs-cdb-vs-savings', { params: { amount: valor, holding_months: meses } });
    return data;
  },
  /** Ranking de bancos para o perfil do usuário (rendimento, tarifas, cartão). Plano Pro. */
  bancoIdeal: async (userId: string, valor: number, meses: number): Promise<BancoIdeal> => {
    const { data } = await apiClient.get(`/opportunities/${userId}/bank-match`, { params: { amount: valor, holding_months: meses } });
    return data;
  },
  poupancaVsCdi: async (referencia = 10000): Promise<PoupancaVsCdi> => {
    const { data } = await apiClient.get('/opportunities/savings-vs-cdi', { params: { amount_reference_brl: referencia } });
    return data;
  },
};

/** Liquidez em português: 'daily' → 'liquidez diária', '24m' → 'resgate em 24 meses'. */
export function rotuloLiquidez(liquidez: string, dias?: number): string {
  if (liquidez === 'daily' || dias === 0 || dias === 1) return 'liquidez diária';
  const m = /^(\d+)m$/.exec(liquidez || '');
  if (m) return `resgate só em ${m[1]} meses`;
  return dias ? `resgate em ~${dias} dias` : liquidez;
}
