import apiClient from './client';

/** Contratos da aba Organizar e da página de Metas. */

export type TipoMeta = 'imovel' | 'viagem' | 'carro' | 'educacao' | 'emergencia' | 'outros';
export type StatusMeta = 'ACTIVE' | 'COMPLETED' | 'ABANDONED';
/** SEM_DADOS = nenhum ritmo de aporte registrado ainda (não é "irrealista"). */
export type Viabilidade = 'EASY' | 'MODERATE' | 'HARD' | 'UNREALISTIC' | 'SEM_DADOS';

export interface ProjecaoMeta {
  on_track: boolean;
  projected_completion_date: string | null;
  months_to_complete: number | null;
  monthly_contribution_needed: number;
  current_monthly_actual: number;
  gap: number;
  feasibility: Viabilidade;
  alerts: string[];
  suggestion: string;
}

export interface Meta {
  goal_id: string;
  name: string;
  goal_type: TipoMeta;
  target_amount: number;
  current_amount: number;
  progress_pct: number;
  remaining: number;
  target_date: string | null; // 'YYYY-MM-DD'
  monthly_contribution_needed: number | null;
  monthly_contribution_actual: number | null;
  status: StatusMeta;
  projection?: ProjecaoMeta;
}

export interface NovaMeta {
  name: string;
  goal_type: TipoMeta;
  target_amount: number;
  current_amount?: number;
  target_date?: string;
}

export interface GrupoOrcamento {
  group: 'essenciais' | 'desejos' | 'poupanca';
  current_amount: number;
  current_pct: number; // 0–100
  target_pct: number;  // 0–100
  suggested_amount: number;
  status: string;
  delta_pct: number;
}

/** GET /budget/{uid} — a renda é estimada pelo extrato quando não vem. */
export interface Orcamento {
  income: number;
  income_source: 'estimada' | 'informada';
  history_months: number;
  total_expenses_avg: number;
  expenses_pct_income: number;
  group_summary: GrupoOrcamento[];
  actionable_cuts?: { category: string; monthly_saving?: number; suggestion?: string }[];
  summary_text?: string;
  confidence?: number;
}

export interface Assinatura {
  name: string;
  category: string | null;
  amount: number;
  billing_cycle: string;
  first_seen: string | null;
  last_seen: string | null;
  price_changed: boolean;
  needs_attention: boolean;
}

export interface Assinaturas {
  total: number;
  subscriptions: Assinatura[];
  total_monthly_cost: number;
  summary_text?: string | null;
}

/** GET /shadow_invoice/{uid}/summary — total_monthly_committed vem negativo (saída). */
export interface Compromissos {
  total_monthly_committed: number;
  total_count: number;
  subscriptions: number;
  installments: number;
}

export interface Desafio {
  id: string;
  challenge_type: string;
  title: string;
  target_label: string;
  pct_progress: number;
  status: 'ACTIVE' | 'COMPLETED' | 'FAILED' | 'SEM_DADOS' | string;
  completed_at: string | null;
}

export interface Selo {
  badge_type: string;
  earned_at: string;
  metadata: Record<string, unknown> | null;
}

export interface EventoFiscal {
  event_code: string;
  name: string;
  description: string;
  action_hint: string;
  deadline: string; // 'YYYY-MM-DD'
  days_until_deadline: number;
  is_obligation: boolean;
  estimated_amount_brl: number | null;
  is_personalized: boolean;
}

export const organizarApi = {
  metas: async (userId: string, status: StatusMeta = 'ACTIVE'): Promise<{ goals: Meta[]; total: number }> => {
    // include_projections: sem isso a viabilidade não vem, e a página caía
    // num "Moderada" padrão que ninguém calculou.
    const { data } = await apiClient.get(`/goals/${userId}`, {
      params: { status, limit: 50, offset: 0, include_projections: true },
    });
    return data;
  },
  criarMeta: async (userId: string, meta: NovaMeta): Promise<Meta> => {
    const { data } = await apiClient.post(`/goals/${userId}`, meta);
    return data;
  },
  aportar: async (userId: string, goalId: string, valor: number, ritmoMensal?: number): Promise<Meta> => {
    const { data } = await apiClient.patch(`/goals/${userId}/${goalId}/progress`, {
      amount_to_add: valor,
      ...(ritmoMensal !== undefined && ritmoMensal > 0 ? { monthly_actual: ritmoMensal } : {}),
    });
    return data;
  },
  abandonar: async (userId: string, goalId: string): Promise<void> => {
    await apiClient.delete(`/goals/${userId}/${goalId}`);
  },
  orcamento: async (userId: string, renda?: number): Promise<Orcamento> => {
    const { data } = await apiClient.get(`/budget/${userId}`, {
      params: renda && renda > 0 ? { monthly_income: renda } : {},
    });
    return data;
  },
  assinaturas: async (userId: string): Promise<Assinaturas> => {
    const { data } = await apiClient.get(`/subscriptions/${userId}/simple`);
    return data;
  },
  compromissos: async (userId: string): Promise<Compromissos> => {
    const { data } = await apiClient.get(`/shadow_invoice/${userId}/summary`);
    return data;
  },
  desafios: async (userId: string): Promise<{ challenges: Desafio[]; completed_total: number }> => {
    const { data } = await apiClient.get(`/health-score/challenges/${userId}`);
    return data;
  },
  selos: async (userId: string): Promise<{ badges: Selo[]; total: number }> => {
    const { data } = await apiClient.get(`/health-score/badges/${userId}`);
    return data;
  },
  sazonalidade: async (userId: string): Promise<{ events: EventoFiscal[]; total: number }> => {
    const { data } = await apiClient.get(`/seasonality/${userId}`);
    return data;
  },
};

/** Amanhã em 'YYYY-MM-DD' (calendário local): o backend exige prazo FUTURO. */
export function amanhaISO(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

// Todos os badge_type que badge_service.py e challenge_service.py concedem.
export const ROTULO_SELO: Record<string, string> = {
  PRIMEIRO_INSIGHT: 'Primeiro insight',
  '3_MESES_VERDE': '3 meses no verde',
  '6_MESES_VERDE': '6 meses no verde',
  NEGOCIADOR: 'Negociador',
  ECONOMIZOU_100: 'Economizou R$ 100',
  ECONOMIZOU_500: 'Economizou R$ 500',
  ECONOMIZOU_1000: 'Economizou R$ 1.000',
  ECONOMIZOU_5000: 'Economizou R$ 5.000',
  SCORE_RECORD: 'Score recorde',
  DEFENSOR: 'Defensor dos seus direitos',
  PORTABILIDADE: 'Portabilidade',
  VIRAL_SHARE: 'Compartilhou o resumo',
  PRIMEIRO_DESAFIO: 'Primeiro desafio concluído',
  DESAFIO_TRIPLO: 'Três desafios concluídos',
  DESAFIO_STREAK_3: '3 meses de desafios seguidos',
};
