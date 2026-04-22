import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { StrategiesPage } from '../../../pages/StrategiesPage';

vi.mock('../../../api/nexa', () => ({
  nexaApi: {
    architectSimulate: vi.fn(),
    architectListSimulations: vi.fn(),
    architectMetrics: vi.fn(),
    getOptimizerPortfolio: vi.fn(),
    getOptimizerCards: vi.fn(),
    getOptimizerPromotions: vi.fn(),
    getOptimizerOpportunityCost: vi.fn(),
    getTransactions: vi.fn(),
    getOptimizerPromotionOpportunities: vi.fn(),
    getOptimizerReports: vi.fn(),
    getOptimizerRoi: vi.fn(),
    analyzeOptimizer: vi.fn(),
    getForecast: vi.fn(),
    getFiscalReport: vi.fn(),
    getFiscalMixedUse: vi.fn(),
    getPeerComparison: vi.fn(),
    getNotifications: vi.fn(),
    getBankCosts: vi.fn(),
  },
}));

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => vi.fn() };
});

const { nexaApi } = await import('../../../api/nexa');

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
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
  localStorage.setItem('user_id', 'test_user_123');

  (nexaApi.architectListSimulations as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  (nexaApi.architectMetrics as ReturnType<typeof vi.fn>).mockResolvedValue({
    total_simulations: 5,
    most_common_strategy: 'FINANCIAMENTO',
  });
  (nexaApi.getOptimizerPortfolio as ReturnType<typeof vi.fn>).mockResolvedValue({ cards: [] });
  (nexaApi.getOptimizerCards as ReturnType<typeof vi.fn>).mockResolvedValue({ cards: [] });
  (nexaApi.getOptimizerPromotions as ReturnType<typeof vi.fn>).mockResolvedValue({ promotions: [] });
  (nexaApi.getTransactions as ReturnType<typeof vi.fn>).mockResolvedValue({ transactions: [] });
  (nexaApi.getOptimizerPromotionOpportunities as ReturnType<typeof vi.fn>).mockResolvedValue({ opportunities: [] });
  (nexaApi.getOptimizerReports as ReturnType<typeof vi.fn>).mockResolvedValue({ reports: [] });
  (nexaApi.getOptimizerRoi as ReturnType<typeof vi.fn>).mockResolvedValue({ verdict: 'NAO_VALE' });
});

describe('StrategiesPage — aba Architect (F3)', () => {
  it('renderiza os tabs incluindo Architect', () => {
    renderPage();
    expect(screen.getByText('Architect')).toBeInTheDocument();
  });

  it('exibe o painel de simulação ao clicar em Architect', async () => {
    renderPage();
    fireEvent.click(screen.getByText('Architect'));
    expect(screen.getByText('Simulação estratégica')).toBeInTheDocument();
    expect(screen.getByText('Simular')).toBeInTheDocument();
  });

  it('chama architectSimulate com os campos corretos ao clicar em Simular', async () => {
    (nexaApi.architectSimulate as ReturnType<typeof vi.fn>).mockResolvedValue({
      recommended_strategy: 'FINANCIAMENTO',
      confidence_score: 0.85,
      months_to_achieve: 48,
      costs: { expected_cost: 150000 },
      liquidity_impact: 0.35,
      npv: { financiamento: -5000 },
      action_plan: [{ step: 1, action: 'Abrir conta' }],
    });

    renderPage();
    fireEvent.click(screen.getByText('Architect'));
    fireEvent.click(screen.getByText('Simular'));

    await waitFor(() => {
      expect(nexaApi.architectSimulate).toHaveBeenCalledOnce();
    });

    const payload = (nexaApi.architectSimulate as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(payload).toMatchObject({
      user_id: 'test_user_123',
      risk_profile: 'moderado',
      include_consortium: true,
    });
    expect(typeof payload.target_amount).toBe('number');
    expect(typeof payload.down_payment).toBe('number');
    expect(typeof payload.financing_months).toBe('number');
  });

  it('exibe resultado da simulação após resposta bem-sucedida', async () => {
    (nexaApi.architectSimulate as ReturnType<typeof vi.fn>).mockResolvedValue({
      recommended_strategy: 'CONSORCIO',
      confidence_score: 0.78,
      months_to_achieve: 60,
      costs: { expected_cost: 120000 },
      liquidity_impact: 0.20,
      npv: { consorcio: 3000 },
      action_plan: [],
    });

    renderPage();
    fireEvent.click(screen.getByText('Architect'));
    fireEvent.click(screen.getByText('Simular'));

    await waitFor(() => {
      expect(screen.getByText('CONSORCIO')).toBeInTheDocument();
    });

    expect(screen.getByText('78%')).toBeInTheDocument();
    expect(screen.getByText('60 meses')).toBeInTheDocument();
  });

  it('carrega histórico e métricas do Architect ao abrir a aba', async () => {
    renderPage();
    fireEvent.click(screen.getByText('Architect'));

    await waitFor(() => {
      expect(nexaApi.architectListSimulations).toHaveBeenCalledWith('test_user_123', 8);
      expect(nexaApi.architectMetrics).toHaveBeenCalledWith('test_user_123');
    });
  });

  it('exibe métricas do Architect quando disponíveis', async () => {
    renderPage();
    fireEvent.click(screen.getByText('Architect'));

    await waitFor(() => {
      expect(screen.getByText('5')).toBeInTheDocument();
      expect(screen.getByText('FINANCIAMENTO')).toBeInTheDocument();
    });
  });

  it('exibe mensagem quando não há histórico de simulações', async () => {
    renderPage();
    fireEvent.click(screen.getByText('Architect'));

    await waitFor(() => {
      expect(screen.getByText('Nenhuma simulação prévia encontrada.')).toBeInTheDocument();
    });
  });
});
