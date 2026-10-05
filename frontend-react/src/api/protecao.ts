import apiClient, { TIMEOUTS } from './client';

/**
 * Defesa do consumidor (D1–D6), Direitos esquecidos (T3), Impostos (T1/T2) e
 * os cards compartilháveis (V1/V2). O backend tinha tudo pronto e nenhuma
 * tela chamava — o chat dizia "seus 3 documentos estão prontos" e não havia
 * onde baixá-los.
 */

// ── Defesa ──────────────────────────────────────────────────────────────────

export interface AchadoDeDefesa {
  detector: string;
  severity: 'HIGH' | 'MEDIUM' | 'LOW' | string;
  bank_name: string;
  title: string;
  description: string;
  amount_disputed: number;
  legal_basis: string;
  recommended_action: string;
  evidence_points: string[];
  confidence: number;
  requires_user_confirmation: boolean;
  legal_review_level?: string;
  estimated_vs_claimed?: string | null;
}

export interface AnaliseDeDefesa {
  findings: AchadoDeDefesa[];
  total_findings: number;
  high_severity: number;
  medium_severity: number;
  total_disputed_amount: number;
  summary: string;
  disclaimer: string;
}

export interface Dossie extends Omit<AnaliseDeDefesa, 'high_severity' | 'medium_severity' | 'summary'> {
  contestation_letter: string;
  procon_narrative: string;
  jec_petition: string;
  monetary_correction: unknown;
}

// ── Direitos esquecidos ─────────────────────────────────────────────────────

export interface Direito {
  category: 'svr_bacen' | 'fgts' | 'pis_pasep' | 'ir_restituicao' | string;
  title: string;
  description: string;
  estimated_amount: number | null;
  estimated_confidence: string;
  relevance_reason: string;
  official_channel: string;
  official_url: string;
  action_steps: string[];
  warning: string;
  /** assisted_real = dá para consultar daqui; guided = só orientação */
  capability: 'assisted_real' | 'authorized_real' | 'guided' | string;
}

export interface Direitos {
  rights: Direito[];
  total_estimated_recoverable: number;
  disclaimer: string;
  context_note?: string | null;
}

export interface CaptchaSvr { imagem_base64: string; hash: string; audio_base64?: string | null; instrucao: string }
export interface ResultadoSvr { tem_valor_a_receber: boolean; consultado_em_nome_de: string; fonte: string; proximos_passos: string[] }
export interface ResultadoIr {
  status: 'encontrada' | 'sem_restituicao' | 'nao_configurado';
  valor: number | null;
  situacao_descricao: string | null;
  detalhe: string | null;
  aviso_legal: string | null;
  proximos_passos: string[];
}

// ── Impostos ────────────────────────────────────────────────────────────────

export interface PosicaoDeInvestimento {
  bank_name: string;
  product_name: string;
  product_type: string;
  amount: number;
  current_balance: number;
  annual_rate_pct: number;
  holding_months: number;
  is_exempt: boolean;
  unrealized_gain: number;
  estimated_ir: number;
  has_come_cotas: boolean;
}

export interface OportunidadeFiscal {
  opportunity_type: string;
  title: string;
  description: string;
  position_ref: string;
  recommended_action: string;
  estimated_tax_saving_brl: number;
  benefit_kind: 'tax_saving' | 'deferral';
  confidence: 'high' | 'medium' | 'low';
  action_deadline: string | null;
}

export interface OtimizacaoDeIr {
  portfolio: PosicaoDeInvestimento[];
  total_invested: number;
  total_current_balance: number;
  total_unrealized_gain: number;
  total_estimated_ir_liability: number;
  opportunities: OportunidadeFiscal[];
  total_estimated_tax_saving: number;
  total_estimated_deferral_gain: number;
  summary: string;
  data_source: 'pluggy' | 'no_data';
}

export interface Breakeven {
  cdb_rate_pct: number;
  holding_months: number;
  ir_rate_pct: number;
  cdb_net_rate_pct: number;
  lci_breakeven_pct: number;
  lci_advantage_pct: number | null;
  interpretation: string;
}

// ── Cards compartilháveis ───────────────────────────────────────────────────

export interface Wrapped {
  year: number;
  highlights: { category: string; title: string; value_formatted: string; description: string }[];
  total_fees_paid_year: number;
  total_savings_identified: number;
  score_start: number | null;
  score_end: number | null;
  score_delta: number | null;
  badges_earned: string[];
  summary_tagline: string;
  disclaimer: string;
  is_partial_year: boolean;
}

export interface PlacarDeEconomia {
  total_annual_savings_brl: number;
  months_active: number;
  tagline: string;
  sources: { name: string; annual_savings_brl: number; description: string }[];
  disclaimer: string;
}

/** Baixa uma resposta binária (com o token da sessão) como arquivo. */
function baixar(blob: Blob, nome: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const protecaoApi = {
  defesa: async (userId: string): Promise<AnaliseDeDefesa> =>
    (await apiClient.get(`/defense/${userId}`, { timeout: TIMEOUTS.lento })).data,
  portabilidade: async (userId: string): Promise<AnaliseDeDefesa> =>
    (await apiClient.get(`/defense/${userId}/portability`, { timeout: TIMEOUTS.lento })).data,
  dossie: async (userId: string): Promise<Dossie> =>
    (await apiClient.get(`/defense/${userId}/dossier`, { timeout: TIMEOUTS.lento })).data,
  /** ZIP com carta ao banco, relato para o PROCON e modelo de petição do JEC. */
  baixarDossie: async (userId: string): Promise<void> => {
    const { data } = await apiClient.get(`/defense/${userId}/zip`, { responseType: 'blob', timeout: TIMEOUTS.lento });
    baixar(data, `hive-dossie-${new Date().toISOString().slice(0, 10)}.zip`);
  },

  direitos: async (userId: string): Promise<Direitos> => (await apiClient.get(`/rights/${userId}`)).data,
  captchaSvr: async (userId: string): Promise<CaptchaSvr> => (await apiClient.get(`/rights/${userId}/svr/captcha`)).data,
  /** CPF e nascimento vão no corpo e não são guardados pelo backend. */
  consultarSvr: async (userId: string, dados: { cpf: string; data_nascimento: string; captcha_hash: string; captcha_resposta: string }): Promise<ResultadoSvr> =>
    (await apiClient.post(`/rights/${userId}/svr/check`, dados, { timeout: TIMEOUTS.lento })).data,
  consultarIr: async (userId: string, token: string): Promise<ResultadoIr> =>
    (await apiClient.post(`/rights/${userId}/ir/check`, { token_compartilhamento: token }, { timeout: TIMEOUTS.lento })).data,

  otimizarIr: async (userId: string): Promise<OtimizacaoDeIr> => (await apiClient.get(`/tax/optimize/${userId}`)).data,
  breakeven: async (cdb: number, meses: number, lci?: number): Promise<Breakeven> =>
    (await apiClient.post('/tax/breakeven', { cdb_rate_pct: cdb, holding_months: meses, ...(lci ? { lci_offered_rate_pct: lci } : {}) })).data,

  wrapped: async (userId: string, ano: number): Promise<Wrapped> => (await apiClient.get(`/viral/wrapped/${userId}/${ano}`)).data,
  placar: async (userId: string): Promise<PlacarDeEconomia> => (await apiClient.get(`/viral/savings-card/${userId}`)).data,
  /** Imagem do card buscada COM o token (uma <img src> direta levaria 401). */
  imagem: async (caminho: string): Promise<Blob> =>
    (await apiClient.get(caminho, { responseType: 'blob' })).data,
  registrarCompartilhamento: async (userId: string, card: 'savings_card' | 'wrapped', canal: string) =>
    (await apiClient.post('/viral/shares', { user_id: userId, card_type: card, channel: canal, utm_campaign: card }, { params: { user_id: userId } })).data,
  baixar,
};

export const ROTULO_SEVERIDADE: Record<string, string> = { HIGH: 'Grave', MEDIUM: 'Moderado', LOW: 'Leve' };
