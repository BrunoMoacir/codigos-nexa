import apiClient, { TIMEOUTS } from './client';

/**
 * Contratos da página de Estratégias, tirados das respostas reais.
 *
 * A página lia campos que não existem (cashback_pct e annual_return no
 * portfólio, lost_value no custo de oportunidade, total_deductible no fiscal,
 * peer_score no benchmark…) e mostrava R$ 0,00 / 0% em quase tudo.
 */

// ── Optimizer ───────────────────────────────────────────────────────────────

export interface CartaoDaCarteira {
  card_id: string;
  card_name: string;
  issuer: string;
  assigned_categories: string[];
  monthly_spend_directed: number;
  annual_return_from_this_card: number;
  effective_annuity: number;
  net_annual: number;
  reason: string;
  request_link: string | null;
}

export interface Carteira {
  total_cards: number;
  total_annual_return: number;
  total_annuity_cost: number;
  net_annual_gain: number;
  vs_single_best: number;
  single_best_net_gain: number;
  cards: CartaoDaCarteira[];
  explanation: string;
  data_quality: string;
}

export interface CartaoDaBase { card_id: string; name: string; issuer: string }

export interface Oportunidade {
  card_id: string;
  card_name: string;
  issuer: string;
  hypothetical_reward_value: number;
  difference: number;
  difference_annualized: number;
  difference_monthly: number;
  explanation: string;
}

export interface CustoDeOportunidade {
  current_card_name: string;
  period_months: number;
  total_spent: number;
  current_card_reward_value: number;
  best_opportunity: Oportunidade | null;
  opportunities: Oportunidade[];
}

export type VeredictoRoi = 'VALE_A_PENA' | 'MARGINAL' | 'NAO_VALE';

export interface RoiDoCartao {
  card_name: string;
  annuity_paid: number;
  reward_value_generated: number;
  net_roi: number;
  annuity_waived: boolean;
  spend_needed_for_waiver: number | null;
  verdict: VeredictoRoi;
  explanation: string;
}

export interface Promocao {
  id: string;
  loyalty_program: string;
  partner: string;
  bonus_pct: number;
  end_date: string;
  days_remaining: number;
  min_points: number | null;
  eligible_cards: string[];
  description: string;
}

export type TipoRecomendacao = 'SWITCH_RECOMMENDED' | 'KEEP_CURRENT' | 'INSUFFICIENT_DATA' | 'LOW_CONFIDENCE';

export interface AnaliseOptimizer {
  report_id: string;
  recommendation_type: TipoRecomendacao;
  strategy_text: string;
  best_card: {
    card_name: string;
    issuer: string;
    net_gain_expected: number;
    net_gain_min: number;
    net_gain_max: number;
    eligibility_reasons: string[];
    profile_match_reasons?: string[];
    warnings: string[];
  } | null;
  insights: { insight_id: string; type: string; title: string; description: string; gain_interval?: { expected?: number } }[];
  user_profile_summary: {
    lifestyle_cluster?: string;
    fss?: number;
    fss_level?: string;
    savings_rate?: number;
    monthly_avg_spend?: number;
    is_likely_mei?: boolean;
    life_stage?: string;
  };
  life_events: { event: string; confidence: number; trigger_action: string; supporting_signals: string[] }[];
  warnings: string[];
}

export interface RelatorioOptimizer {
  report_id: string;
  generated_at: string;
  recommendation_type: TipoRecomendacao;
  best_card_name: string | null;
  net_gain_expected: number | null;
  strategy_text: string | null;
}

// ── Architect ───────────────────────────────────────────────────────────────

export type Estrategia = 'FINANCING' | 'CONSORTIUM' | 'SAVE_INVEST' | 'FINANCING_RENTAL' | 'CONSORTIUM_SELIC_RENTAL';
export type TipoDeBem = 'IMOVEL' | 'VEICULO' | 'REFORMA' | 'VIAGEM' | 'OUTRO';
export type PerfilDeRisco = 'conservador' | 'moderado' | 'agressivo';

export interface PedidoSimulacao {
  user_id: string;
  target_amount: number;
  down_payment: number;
  asset_type: TipoDeBem;
  financing_months: number;
  risk_profile: PerfilDeRisco;
  include_consortium: boolean;
  prefers_consortium: boolean;
}

export interface Simulacao {
  recommended_strategy: Estrategia;
  costs: { min_cost: number; expected_cost: number; max_cost: number };
  npv: {
    financing: number | null;
    consortium: number | null;
    save_invest: number | null;
    financing_rental?: number | null;
    consortium_selic_rental?: number | null;
    discount_rate_used?: number;
  };
  liquidity_impact: number; // fração (−1 a 1)
  months_to_achieve: number;
  action_plan: { step: number; action: string; amount: number | null; is_critical: boolean }[];
  confidence_score: number; // 0–1
  warnings: string[];
  ssd_guarantee?: string | null;
}

export interface SimulacaoSalva {
  id: string;
  created_at: string;
  target_amount: number;
  asset_type: TipoDeBem;
  recommended_strategy: Estrategia;
  confidence_score: number;
  months_to_achieve: number;
  expected_cost: number;
}

export interface SimulacaoPendente { simulation_id: string; created_at: string; recommended_strategy: Estrategia; target_amount?: number }

export interface MetricasArchitect {
  total_simulations: number;
  favorite_strategy: Estrategia | null;
  avg_confidence_score: number | null;
  last_simulated_at: string | null;
}

// ── Fiscal (MEI) ────────────────────────────────────────────────────────────

export interface LinhaFiscal { subcategory: string; label: string; total: number; count: number }

export interface RelatorioFiscal {
  period_label: string;
  receitas: LinhaFiscal[];
  despesas: LinhaFiscal[];
  total_receita: number;
  total_despesa: number;
  lucro_estimado: number;
  rbt12_anualizado: number;
  das_aliquota_efetiva: number; // já em %
  das_estimado: number;
  das_faixa: string;
  das_anexo: string;
  fator_r: number | null;
  das_observacao: string;
  total_transactions: number;
}

export interface UsoMisto {
  candidates: {
    transaction_id: string;
    description: string;
    amount: number;
    date: string;
    suggested_pj_pct: number;
    pj_amount: number;
    explanation: string;
  }[];
  total_mixed_spend: number;
  total_pj_deductible: number;
}

// ── Comparação com pares ────────────────────────────────────────────────────

export interface Comparacao {
  bracket_label: string;
  monthly_income: number;
  user_savings_rate: number;      // %
  benchmark_savings_rate: number; // %
  savings_percentile_label: string;
  benchmark_source: string;
  categories: {
    category: string;
    label: string;
    user_pct: number;
    benchmark_pct: number;
    user_amount_brl: number;
    benchmark_amount_brl: number;
    status: string;
    insight: string;
  }[];
  highlights_above: string[];
  highlights_below: string[];
  summary_text: string;
}

// ── F5 · F7 · F13 ───────────────────────────────────────────────────────────

export interface RaioX {
  analysis_months: number;
  period_start: string;
  period_end: string;
  total_paid: number;
  monthly_avg: number;
  annual_projection: number;
  savings_opportunity: number;
  by_bank: { bank_name: string; total_paid: number; monthly_avg: number }[];
  by_fee_type: Record<string, number>;
  warnings: string[];
}

export interface OpcaoDeCompra {
  method: string;
  label: string;
  total_cost: number;
  monthly_cost: number | null;
  installments: number;
  net_cost: number;
  net_cost_real: number | null;
  notes: string;
  profile_fit: string;
}

export interface AnaliseDeCompra {
  recommended_label: string;
  recommended_net_cost: number;
  recommended_net_cost_real: number | null;
  reasoning: string;
  options: OpcaoDeCompra[];
  liquidity_impact: {
    safe_to_spend_before: number;
    safe_to_spend_after: number;
    affordable: boolean | null; // null = margem não calculada
    risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | 'UNKNOWN';
  };
  warnings: string[];
  profile_summary?: string;
}

/** GET /purchase/checkout-context — o F7 em uma frase, para decidir na hora. */
export interface ContextoDeCompra {
  verdict: string;
  recommended_label: string;
  savings_vs_worst: number;
  affordable: boolean | null;
  risk_level: string;
  safe_to_spend_after: number;
  options: { label: string; method: string; net_cost: number; monthly_cost: number | null; profile_fit: string }[];
}

export interface RevisaoDeCompras {
  total: number;
  total_savings_missed_brl: number;
  reviews: { transaction_id: string; merchant: string; amount: number; purchase_date: string; paid_method_label: string; best_method_label: string; potential_savings_brl: number }[];
}

export interface RoteiroDeNegociacao {
  opportunity: { bank_name: string; product: string; description: string; potential_saving_monthly: number };
  opening_line: string;
  key_arguments: string[];
  target_ask: string;
  fallback_ask: string;
  closing_line: string;
  recommended_channel: string;
  best_time: string;
  estimated_success_pct: number;
  generated_by: string;
}

export interface Negociacao {
  opportunities_found: number;
  scripts: RoteiroDeNegociacao[];
  summary: string;
  confidence_score: number;
  warnings: string[];
}

export interface HistoricoDeNegociacao {
  items: { id: string; bank_name: string; trigger_type: string; potential_gain: number | null; generated_at: string; result_status: string | null }[];
  total_potential_gain: number;
  total_realized_gain: number;
}

export type ResultadoNegociacao = 'sucesso' | 'parcial' | 'recusado' | 'nao_tentou';

// ── Chamadas ────────────────────────────────────────────────────────────────

export const estrategiasApi = {
  carteira: async (userId: string, maxCards: number, renda?: number): Promise<Carteira> =>
    (await apiClient.get(`/optimizer/portfolio/${userId}`, { params: { max_cards: maxCards, ...(renda ? { monthly_income: renda } : {}) } })).data,
  cartoes: async (): Promise<{ total: number; cards: CartaoDaBase[] }> =>
    (await apiClient.get('/optimizer/cards')).data,
  custoDeOportunidade: async (userId: string, cardId: string, meses = 3): Promise<CustoDeOportunidade> =>
    (await apiClient.get('/optimizer/opportunity-cost', { params: { user_id: userId, current_card_id: cardId, months: meses } })).data,
  roi: async (userId: string, cardId: string): Promise<RoiDoCartao> =>
    (await apiClient.get(`/optimizer/roi/${cardId}`, { params: { user_id: userId } })).data,
  promocoes: async (): Promise<{ promotions: Promocao[] }> =>
    (await apiClient.get('/optimizer/promotions')).data,
  relatorios: async (userId: string): Promise<{ reports: RelatorioOptimizer[] }> =>
    (await apiClient.get(`/optimizer/reports/${userId}`)).data,
  /** Sem renda nem margem no corpo, o backend usa as do /forecast. */
  analisar: async (userId: string, cartaoAtual?: string, contexto?: { safe_to_spend?: number; monthly_income?: number }): Promise<AnaliseOptimizer> =>
    (await apiClient.post('/optimizer/analyze', { user_id: userId, current_cards: cartaoAtual ? [cartaoAtual] : [], ...contexto }, { timeout: TIMEOUTS.lento })).data,

  /** Simulação chama BACEN + LLM: 12–20 s. */
  simular: async (pedido: PedidoSimulacao): Promise<Simulacao> =>
    (await apiClient.post('/architect/simulate', pedido, { timeout: TIMEOUTS.lento })).data,
  simulacoes: async (userId: string, limit = 8): Promise<SimulacaoSalva[]> =>
    (await apiClient.get('/architect/simulations', { params: { user_id: userId, limit } })).data,
  metricasArchitect: async (userId: string): Promise<MetricasArchitect> =>
    (await apiClient.get('/architect/metrics', { params: { user_id: userId } })).data,

  /** "Vou fazer" / "Não se aplica": calibra o ranking dos próximos insights. */
  responderInsight: async (reportId: string, insightId: string, resposta: 'ACCEPTED' | 'REJECTED') =>
    (await apiClient.post(`/optimizer/recommendations/${reportId}/feedback`, { insight_id: insightId, outcome: resposta })).data,
  /** Simulações com 6+ meses sem retorno — o que o usuário fez de fato. */
  simulacoesPendentes: async (): Promise<SimulacaoPendente[]> =>
    (await apiClient.get('/architect/simulations/pending-feedback')).data,
  responderSimulacao: async (simulationId: string, seguiu: boolean, estrategia: Estrategia) =>
    (await apiClient.post(`/architect/simulations/${simulationId}/feedback`, { feedback_followed: seguiu, strategy_used: estrategia })).data,

  fiscal: async (userId: string, ano: number, mes?: number): Promise<RelatorioFiscal> =>
    (await apiClient.get(`/fiscal-report/${userId}`, { params: { year: ano, ...(mes ? { month: mes } : {}) } })).data,
  usoMisto: async (userId: string, ano: number, mes?: number): Promise<UsoMisto> =>
    (await apiClient.get(`/fiscal-report/${userId}/mixed-use`, { params: { year: ano, ...(mes ? { month: mes } : {}) } })).data,
  /** "Isto é PJ / PF": correção humana do classificador. */
  corrigirContexto: async (userId: string, transactionId: string, contexto: 'PF' | 'PJ') =>
    (await apiClient.post('/context/override', { transaction_id: transactionId, corrected_context: contexto }, { params: { user_id: userId } })).data,

  comparar: async (userId: string, renda?: number): Promise<Comparacao> =>
    (await apiClient.get(`/peers/compare/${userId}`, { params: { history_months: 3, ...(renda ? { monthly_income: renda } : {}) } })).data,

  raioX: async (userId: string): Promise<RaioX> =>
    (await apiClient.get(`/costs/raio-x/${userId}`)).data,
  analisarCompra: async (pedido: { user_id: string; amount: number; category: string; installments: number; cash_price?: number; safe_to_spend?: number; monthly_income?: number }): Promise<AnaliseDeCompra> =>
    (await apiClient.post('/purchase/analyze', { ...pedido, apply_opportunity_cost: true }, { timeout: TIMEOUTS.lento })).data,
  contextoDeCompra: async (userId: string, valor: number, parcelas = 1, categoria = 'Outros'): Promise<ContextoDeCompra> =>
    (await apiClient.get(`/purchase/checkout-context/${userId}`, { params: { amount: valor, installments: parcelas, category: categoria }, timeout: TIMEOUTS.lento })).data,
  revisaoDeCompras: async (userId: string): Promise<RevisaoDeCompras> =>
    (await apiClient.get(`/purchase/recent-review/${userId}`)).data,
  /** Um roteiro por oportunidade, gerados em paralelo no backend (LLM). */
  negociar: async (userId: string, banco?: string): Promise<Negociacao> =>
    (await apiClient.post('/negotiator/generate-script', { user_id: userId, ...(banco ? { bank_name: banco } : {}) }, { timeout: TIMEOUTS.lento })).data,
  historicoDeNegociacao: async (userId: string): Promise<HistoricoDeNegociacao> =>
    (await apiClient.get(`/negotiator/history/${userId}`)).data,
  registrarResultado: async (recordId: string, resultado: ResultadoNegociacao, ganhoMensal?: number) =>
    (await apiClient.patch(`/negotiator/history/${recordId}`, { result_status: resultado, ...(ganhoMensal ? { result_gain: ganhoMensal } : {}) })).data,
};

// ── Rótulos ─────────────────────────────────────────────────────────────────

export const ROTULO_ESTRATEGIA: Record<string, string> = {
  FINANCING: 'Financiamento',
  CONSORTIUM: 'Consórcio',
  SAVE_INVEST: 'Juntar e comprar à vista',
  FINANCING_RENTAL: 'Financiar e alugar o imóvel',
  CONSORTIUM_SELIC_RENTAL: 'Consórcio + renda fixa + aluguel',
};

export const ROTULO_RECOMENDACAO: Record<string, string> = {
  SWITCH_RECOMMENDED: 'Vale trocar de cartão',
  KEEP_CURRENT: 'Mantenha o cartão atual',
  INSUFFICIENT_DATA: 'Dados insuficientes',
  LOW_CONFIDENCE: 'Recomendação com baixa confiança',
};

export const ROTULO_VEREDICTO: Record<VeredictoRoi, string> = {
  VALE_A_PENA: 'Vale a pena',
  MARGINAL: 'No limite',
  NAO_VALE: 'Não compensa',
};

export const ROTULO_EVENTO: Record<string, string> = {
  income_drop: 'Queda de renda',
  income_increase: 'Aumento de renda',
  new_baby: 'Chegada de bebê',
  wedding: 'Casamento',
  moving: 'Mudança',
  new_job: 'Emprego novo',
  travel: 'Viagem',
  retirement: 'Aposentadoria',
};

export const ROTULO_CANAL: Record<string, string> = {
  APP_CHAT: 'Chat do app (fica registrado)',
  TELEFONE: 'Telefone',
  AGENCIA: 'Agência',
  EMAIL: 'E-mail',
};
