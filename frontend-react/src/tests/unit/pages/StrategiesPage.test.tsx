import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AxiosError, AxiosHeaders } from 'axios';
import { StrategiesPage } from '../../../pages/StrategiesPage';

vi.mock('../../../api/estrategias', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api/estrategias')>();
  const fns = [
    'carteira', 'cartoes', 'custoDeOportunidade', 'roi', 'promocoes', 'relatorios', 'analisar',
    'simular', 'simulacoes', 'metricasArchitect', 'fiscal', 'usoMisto', 'corrigirContexto', 'comparar',
    'raioX', 'analisarCompra', 'revisaoDeCompras', 'negociar', 'historicoDeNegociacao', 'registrarResultado',
    'responderInsight', 'simulacoesPendentes', 'responderSimulacao',
  ];
  return { ...actual, estrategiasApi: Object.fromEntries(fns.map((f) => [f, vi.fn()])) };
});
vi.mock('../../../api/painel', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api/painel')>();
  return { ...actual, painelApi: { ...actual.painelApi, previsao: vi.fn(), lancamentos: vi.fn() } };
});

const { estrategiasApi } = await import('../../../api/estrategias');
const { painelApi } = await import('../../../api/painel');
const m = (f: unknown) => f as ReturnType<typeof vi.fn>;

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <StrategiesPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  localStorage.setItem('user_id', 'u1');

  m(painelApi.previsao).mockResolvedValue({
    safe_to_spend: { current_balance: 5000, safe_to_spend_total: 1800, safe_to_spend_daily: 60 },
    cashflow: { negative_day: null, days_at_risk: 0, worst_balance: 1000 },
    financial_health: { savings_rate: 10, income_profile: { monthly_net_income: 8500, confidence: 0.9 } },
  });
  m(estrategiasApi.carteira).mockResolvedValue({
    total_cards: 1, total_annual_return: 763, total_annuity_cost: 0, net_annual_gain: 763,
    vs_single_best: 0, single_best_net_gain: 763, explanation: '', data_quality: 'OK',
    cards: [{ card_id: 'picpay', card_name: 'PicPay Card', issuer: 'PicPay', assigned_categories: ['alimentacao'],
      monthly_spend_directed: 2000, annual_return_from_this_card: 763, effective_annuity: 0, net_annual: 763,
      reason: 'Melhor cashback em alimentação', request_link: null }],
  });
  m(estrategiasApi.cartoes).mockResolvedValue({ total: 0, cards: [] });
  m(estrategiasApi.promocoes).mockResolvedValue({ promotions: [] });
  m(estrategiasApi.relatorios).mockResolvedValue({ reports: [] });
  m(estrategiasApi.simulacoes).mockResolvedValue([]);
  m(estrategiasApi.simulacoesPendentes).mockResolvedValue([]);
  m(estrategiasApi.metricasArchitect).mockResolvedValue({ total_simulations: 0, favorite_strategy: null, avg_confidence_score: null, last_simulated_at: null });
  m(estrategiasApi.raioX).mockResolvedValue({ analysis_months: 12, period_start: '2025-09-01', period_end: '2026-08-29', total_paid: 0, monthly_avg: 0, annual_projection: 0, savings_opportunity: 0, by_bank: [], by_fee_type: {}, warnings: [] });
  m(estrategiasApi.revisaoDeCompras).mockResolvedValue({ total: 0, total_savings_missed_brl: 0, reviews: [] });
  m(estrategiasApi.historicoDeNegociacao).mockResolvedValue({ items: [], total_potential_gain: 0, total_realized_gain: 0 });
});

describe('StrategiesPage', () => {
  it('a carteira mostra o valor real de cada cartão (não R$ 0,00 de campo inexistente)', async () => {
    renderPage();
    expect(await screen.findByText('PicPay Card')).toBeInTheDocument();
    expect(screen.getAllByText(/R\$\s?763,00\/ano/).length).toBeGreaterThan(0);
    expect(screen.getByText(/um cartão só basta/)).toBeInTheDocument();
  });

  it('Grande compra: envia o pedido, mostra a estratégia em português e NPV nulo como "não calculado"', async () => {
    m(estrategiasApi.simular).mockResolvedValue({
      recommended_strategy: 'SAVE_INVEST',
      costs: { min_cost: 130000, expected_cost: 135842, max_cost: 140000 },
      npv: { financing: -132341, consortium: null, save_invest: -87830, discount_rate_used: 0.0118 },
      liquidity_impact: 0, months_to_achieve: 36,
      action_plan: [{ step: 1, action: 'Abrir conta em corretora', amount: null, is_critical: true }],
      confidence_score: 0.78, warnings: [],
    });
    renderPage();
    fireEvent.click(screen.getByText('Grande compra'));
    fireEvent.click(screen.getByRole('button', { name: 'Simular' }));

    await waitFor(() => expect(estrategiasApi.simular).toHaveBeenCalledWith(expect.objectContaining({
      user_id: 'u1', target_amount: 120000, down_payment: 20000, financing_months: 48, asset_type: 'VEICULO',
    })));
    expect(await screen.findAllByText('Juntar e comprar à vista')).not.toHaveLength(0);
    expect(screen.getByText('não calculado')).toBeInTheDocument();
    expect(screen.getByText('78%')).toBeInTheDocument();
  });

  it('Grande compra: timeout aparece como erro, não como "execute uma simulação"', async () => {
    m(estrategiasApi.simular).mockRejectedValue(new AxiosError('timeout of 75000ms exceeded', 'ECONNABORTED'));
    renderPage();
    fireEvent.click(screen.getByText('Grande compra'));
    fireEvent.click(screen.getByRole('button', { name: 'Simular' }));
    expect(await screen.findByText(/demorando mais que o normal/)).toBeInTheDocument();
  });

  it('MEI / Fiscal: lê os campos reais do relatório e explica o DAS', async () => {
    m(estrategiasApi.fiscal).mockResolvedValue({
      period_label: '2026', receitas: [], despesas: [], total_receita: 54000, total_despesa: 12000, lucro_estimado: 42000,
      rbt12_anualizado: 54000, das_aliquota_efetiva: 6, das_estimado: 3240, das_faixa: 'Faixa 1', das_anexo: 'III',
      fator_r: 0.31, das_observacao: 'Fator R acima de 28% → Anexo III.', total_transactions: 80,
    });
    m(estrategiasApi.usoMisto).mockResolvedValue({ candidates: [], total_mixed_spend: 0, total_pj_deductible: 0 });
    renderPage();
    fireEvent.click(screen.getByText('MEI / Fiscal'));
    expect(await screen.findByText('R$ 54.000')).toBeInTheDocument();
    expect(screen.getByText('R$ 3.240,00')).toBeInTheDocument();
    expect(screen.getByText(/Fator R acima de 28%/)).toBeInTheDocument();
  });

  it('Comparação: poupança contra pares e destaques rotulados acima/abaixo', async () => {
    m(estrategiasApi.comparar).mockResolvedValue({
      bracket_label: 'renda alta', monthly_income: 9000, user_savings_rate: 7.6, benchmark_savings_rate: 19,
      savings_percentile_label: '10% inferiores', benchmark_source: 'IBGE/POF', categories: [],
      highlights_above: ['Outros'], highlights_below: ['Alimentação'], summary_text: '',
    });
    renderPage();
    fireEvent.click(screen.getByText('Comparação'));
    expect(await screen.findByText('7,6%')).toBeInTheDocument();
    expect(screen.getByText(/acima/).closest('div')).toHaveTextContent('Outros');
    expect(screen.getByText(/abaixo/).closest('div')).toHaveTextContent('Alimentação');
  });

  it('Compra inteligente manda a margem que a tela mostra e trata margem desconhecida', async () => {
    m(estrategiasApi.analisarCompra).mockResolvedValue({
      recommended_label: 'Cartão 6x sem juros', recommended_net_cost: 2997, recommended_net_cost_real: 2911,
      reasoning: 'Para R$ 3.000,00, **6x** é melhor.', options: [], warnings: [],
      liquidity_impact: { safe_to_spend_before: 0, safe_to_spend_after: 0, affordable: null, risk_level: 'UNKNOWN' },
    });
    renderPage();
    fireEvent.click(screen.getByText('Tarifas, compra e negociação'));
    await screen.findByText(/margem segura do mês R\$\s?1\.800,00/);
    fireEvent.click(screen.getByRole('button', { name: 'Analisar compra' }));

    await waitFor(() => expect(estrategiasApi.analisarCompra).toHaveBeenCalledWith(expect.objectContaining({
      amount: 3000, safe_to_spend: 1800, monthly_income: 8500,
    })));
    expect(await screen.findByText(/custo líquido R\$\s?2\.911,00/)).toBeInTheDocument();
    expect(screen.getByText(/Margem segura do mês não calculada/)).toBeInTheDocument();
  });

  it('402 vira convite para os planos', async () => {
    const headers = new AxiosHeaders();
    m(estrategiasApi.carteira).mockRejectedValue(new AxiosError('402', '402', { headers }, null, {
      status: 402, statusText: '', headers, config: { headers },
      data: { detail: { error: 'upgrade_required', reason: 'Disponível no plano Pro.', required_plan: 'pro' } },
    }));
    renderPage();
    expect(await screen.findByText(/Disponível no plano Pro/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ver planos' })).toHaveAttribute('href', '/planos');
  });
});
