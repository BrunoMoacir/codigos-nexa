import apiClient from './client';

/** Contratos do painel (Dashboard/Home) — ver backend/app/forecast/*. */

export interface ResumoMes {
  month: string; // 'YYYY-MM'
  income: number;
  expenses: number;
  net: number;
}

export interface ResumoCategoria {
  category: string;
  total: number;
  count: number;
  pct: number; // 0–100
}

/** GET /transactions/{uid}/summary (C2). income/expenses positivos, em reais. */
export interface ResumoExtrato {
  user_id: string;
  period: { start: string | null; end: string | null };
  n_transactions: number;
  months: ResumoMes[];
  totals: { income: number; expenses: number; net: number; savings_rate_pct: number };
  by_category: ResumoCategoria[];
  data_as_of: string | null; // 'YYYY-MM-DD'
}

/** Item de GET /transactions/{uid} (C1). */
export interface Lancamento {
  id: string;
  transaction_id: string;
  account_id?: string | null;
  date: string; // 'YYYY-MM-DD'
  description: string;
  amount: number; // negativo = saída
  type: 'income' | 'expense';
  category?: string | null;
  is_recurring?: boolean;
  is_installment?: boolean;
  context_type?: string | null;
}

export interface PaginaDeLancamentos {
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
  transactions: Lancamento[];
}

/** O que o painel lê de GET /forecast/{uid}. */
export interface Previsao {
  safe_to_spend: {
    current_balance?: number | null;
    safe_to_spend_total: number;
    safe_to_spend_daily: number;
    risk_level?: string;
  };
  cashflow: {
    negative_day: number | null;
    first_negative_date?: string | null;
    days_at_risk: number;
    worst_balance: number;
  };
  financial_health: {
    profile_type?: string;
    /** porcentagem, −100 a 100 */
    savings_rate: number;
    income_profile?: { monthly_net_income?: number; income_pattern?: string; confidence?: number } | null;
  };
}

/** O que o painel lê de GET /health-score/history/{uid} — o score exibível. */
export interface HistoricoSaude {
  current_score: number | null;
  trend?: 'IMPROVING' | 'STABLE' | 'DECLINING' | string;
  change_30d?: number | null;
  resilience_score?: number | null;
  fss_score?: number | null;
  fss_level?: string | null;
  data_quality?: string | null;
  /** savings_rate em porcentagem */
  history: { date: string; score: number; savings_rate?: number; profile_type?: string }[];
}

/** GET /pluggy/connections — conexões persistidas, sem depender da Pluggy. */
export type OrigemDosDados = 'none' | 'demonstracao' | 'sandbox' | 'open_finance' | 'misto';

export interface Conexoes {
  pluggy_configured: boolean;
  total: number;
  /** de onde vêm os dados do usuário — derivado das conexões, não de flag local */
  data_source: OrigemDosDados;
  connections: {
    item_id: string;
    connector_name: string | null;
    connected_at: string | null;
    consent_expires_estimate: string | null;
    source: Exclude<OrigemDosDados, 'none' | 'misto'>;
  }[];
}

export const ROTULO_ORIGEM: Record<OrigemDosDados, string> = {
  none: 'Nenhum banco conectado',
  demonstracao: 'Dados de demonstração',
  sandbox: 'Sandbox da Pluggy (dados fictícios)',
  open_finance: 'Open Finance (dados reais)',
  misto: 'Open Finance + dados de teste',
};

export const painelApi = {
  conexoes: async (): Promise<Conexoes> => {
    const { data } = await apiClient.get('/pluggy/connections');
    return data;
  },
  resumo: async (userId: string, months = 12): Promise<ResumoExtrato> => {
    const { data } = await apiClient.get(`/transactions/${userId}/summary`, { params: { months } });
    return data;
  },
  lancamentos: async (userId: string, limit = 20, offset = 0): Promise<PaginaDeLancamentos> => {
    const { data } = await apiClient.get(`/transactions/${userId}`, { params: { limit, offset } });
    return data;
  },
  previsao: async (userId: string): Promise<Previsao> => {
    const { data } = await apiClient.get(`/forecast/${userId}`);
    return data;
  },
  saude: async (userId: string, months = 6): Promise<HistoricoSaude> => {
    const { data } = await apiClient.get(`/health-score/history/${userId}`, { params: { months } });
    return data;
  },
};

// ── Formatação compartilhada ────────────────────────────────────────────────

const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];

export function brl(valor: number, casas = 2): string {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency', currency: 'BRL',
    minimumFractionDigits: casas, maximumFractionDigits: casas,
  }).format(valor);
}

/**
 * 'YYYY-MM-DD' → '29 ago'. Sem `new Date('YYYY-MM-DD')`: o navegador lê a
 * data como meia-noite UTC e, no Brasil (UTC−3), mostra o dia ANTERIOR.
 */
export function dataCurta(iso: string | null | undefined): string {
  if (!iso) return '—';
  const [a, m, d] = iso.slice(0, 10).split('-').map(Number);
  if (!a || !m || !d) return iso;
  return `${d} ${MESES[m - 1]}`;
}

export function dataLonga(iso: string | null | undefined): string {
  if (!iso) return '—';
  const [a, m, d] = iso.slice(0, 10).split('-').map(Number);
  if (!a || !m || !d) return iso;
  return `${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}/${a}`;
}

/** 'YYYY-MM' → 'ago/26' */
export function rotuloMes(yyyymm: string): string {
  const [a, m] = yyyymm.split('-').map(Number);
  if (!a || !m) return yyyymm;
  return `${MESES[m - 1]}/${String(a).slice(2)}`;
}

/** Dias desde 'YYYY-MM-DD' até hoje (calendário local). */
export function diasDesde(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const [a, m, d] = iso.slice(0, 10).split('-').map(Number);
  if (!a || !m || !d) return null;
  const alvo = new Date(a, m - 1, d);
  const hoje = new Date();
  const zero = new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate());
  return Math.round((zero.getTime() - alvo.getTime()) / 86_400_000);
}
