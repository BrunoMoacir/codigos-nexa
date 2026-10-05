import apiClient, { TIMEOUTS } from './client';

/** Contrato do chat (C6): conversa por sessão, ferramentas usadas no turno. */

export interface RespostaChat {
  response: string;
  session_id: string | null;
  tools_used: string[];
  created_at: string | null;
}

export interface ItemHistorico {
  id: number;
  role: 'user' | 'assistant' | string;
  content: string;
  session_id: string | null;
  created_at: string;
}

export const chatApi = {
  /** O backend dá 60 s ao agente; o cliente espera um pouco mais (TIMEOUTS.chat). */
  enviar: async (userId: string, mensagem: string, sessionId: string): Promise<RespostaChat> => {
    const { data } = await apiClient.post(
      '/chat/',
      { user_id: userId, message: mensagem, session_id: sessionId },
      { timeout: TIMEOUTS.chat },
    );
    return data;
  },
  historico: async (userId: string, sessionId: string, limit = 100): Promise<ItemHistorico[]> => {
    const { data } = await apiClient.get('/chat/history', {
      params: { user_id: userId, session_id: sessionId, limit },
    });
    return data;
  },
  /** Sessão da mensagem mais recente do usuário (null = nenhuma ou sem sessão). */
  ultimaSessao: async (userId: string): Promise<string | null> => {
    const { data } = await apiClient.get('/chat/history', { params: { user_id: userId, limit: 1 } });
    return (Array.isArray(data) && data[0]?.session_id) || null;
  },
  /** Apaga SÓ esta conversa (mensagens e memória do agente). */
  apagar: async (userId: string, sessionId: string): Promise<{ deleted_count: number }> => {
    const { data } = await apiClient.delete('/chat/history', {
      params: { user_id: userId, session_id: sessionId },
    });
    return data;
  },
};

/** Nome que o usuário entende para cada ferramenta do agente. */
export const ROTULO_FERRAMENTA: Record<string, string> = {
  detect_abusive_fees: 'tarifas abusivas',
  detect_abusive_interest: 'juros abusivos',
  detect_wrongful_charges: 'cobranças indevidas',
  get_annual_wrapped: 'retrospectiva do ano',
  get_bank_cost_analysis: 'raio-x de custos do banco',
  get_best_bank: 'melhor banco para você',
  get_budget_advice: 'orçamento 50/30/20',
  get_card_optimization: 'otimização de cartões',
  get_defense_analysis: 'defesa do consumidor',
  get_evidence_dossier: 'dossiê de provas',
  get_expert_card_analysis: 'análise de cartões',
  get_financial_forecast: 'previsão de caixa',
  get_financing_simulation: 'simulação de financiamento',
  get_fiscal_calendar: 'calendário fiscal',
  get_fiscal_report: 'relatório fiscal',
  get_forgotten_rights: 'direitos esquecidos',
  get_goals_summary: 'metas',
  get_leverage_simulation: 'simulação de alavancagem',
  get_monthly_challenges: 'desafios do mês',
  get_negotiation_script: 'roteiro de negociação',
  get_opportunities: 'radar de oportunidades',
  get_peer_comparison: 'comparação com pessoas parecidas',
  get_plan_info: 'seu plano',
  get_portability_analysis: 'portabilidade',
  get_purchase_recommendation: 'compra inteligente',
  get_spending_alerts: 'alertas de gasto',
  get_timing_scenarios: 'melhor momento de compra',
  get_transfer_promotions: 'promoções de pontos',
  get_user_profile_context: 'seu perfil financeiro',
  review_recent_purchases: 'compras recentes',
  simulate_investment: 'simulação de investimento',
};

/** Ferramentas cujo resultado tem uma tela própria para aprofundar. */
export const TELA_DA_FERRAMENTA: Record<string, { rota: string; rotulo: string }> = {
  get_evidence_dossier: { rota: '/defesa', rotulo: 'Abrir o dossiê na Defesa' },
  get_defense_analysis: { rota: '/defesa', rotulo: 'Ver na Defesa do Consumidor' },
  detect_abusive_fees: { rota: '/defesa', rotulo: 'Ver na Defesa do Consumidor' },
  detect_abusive_interest: { rota: '/defesa', rotulo: 'Ver na Defesa do Consumidor' },
  detect_wrongful_charges: { rota: '/defesa', rotulo: 'Ver na Defesa do Consumidor' },
  get_forgotten_rights: { rota: '/direitos', rotulo: 'Ver Direitos esquecidos' },
  get_fiscal_report: { rota: '/impostos', rotulo: 'Ver Impostos' },
  get_fiscal_calendar: { rota: '/impostos', rotulo: 'Ver Impostos' },
  get_goals_summary: { rota: '/goals', rotulo: 'Ver metas' },
  get_annual_wrapped: { rota: '/wrapped', rotulo: 'Abrir a retrospectiva' },
};
