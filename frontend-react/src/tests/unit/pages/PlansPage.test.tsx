import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AxiosError, AxiosHeaders } from 'axios';
import { PlansPage } from '../../../pages/PlansPage';

const nativo = vi.hoisted(() => ({ venda: true }));
vi.mock('../../../native/plataforma', () => ({
  vendaNoApp: () => nativo.venda,
  ehNativo: () => !nativo.venda,
  plataforma: () => (nativo.venda ? 'web' : 'android'),
}));

vi.mock('../../../api/conta', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api/conta')>();
  return {
    ...actual,
    contaApi: { ...actual.contaApi, planos: vi.fn(), assinatura: vi.fn(), checkout: vi.fn(), portal: vi.fn(), confirmar: vi.fn() },
  };
});

const { contaApi } = await import('../../../api/conta');
const m = (f: unknown) => f as ReturnType<typeof vi.fn>;

const PLANOS = [
  { plan_id: 'free', name: 'Grátis', price_brl_monthly: 0, tagline: 'Para começar', features: ['1 banco'] },
  { plan_id: 'pro', name: 'Pro', price_brl_monthly: 19.9, tagline: 'Para quem quer economizar', features: ['3 bancos'] },
  { plan_id: 'total', name: 'Total', price_brl_monthly: 39.9, tagline: 'Tudo liberado', features: ['Defesa do consumidor'] },
];
const assinatura = (plan: string, extra: Record<string, unknown> = {}) => ({
  plan, status: 'active', current_period_end: null, cancel_at_period_end: false,
  billing_enabled: true, enforcement_enabled: true, usage: [], ...extra,
});

function renderPage(url = '/planos') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <PlansPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  nativo.venda = true;
  localStorage.clear();
  localStorage.setItem('user_id', 'u1');
  m(contaApi.planos).mockResolvedValue(PLANOS);
  m(contaApi.assinatura).mockResolvedValue(assinatura('free'));
  // o redirecionamento para o Stripe nunca resolve no teste
  m(contaApi.portal).mockReturnValue(new Promise(() => {}));
  m(contaApi.checkout).mockReturnValue(new Promise(() => {}));
});

describe('PlansPage', () => {
  it('quem já paga troca de plano pelo portal — nunca abre um segundo checkout', async () => {
    m(contaApi.assinatura).mockResolvedValue(assinatura('pro'));
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Trocar para Total' }));
    await waitFor(() => expect(contaApi.portal).toHaveBeenCalledWith('u1'));
    expect(contaApi.checkout).not.toHaveBeenCalled();
  });

  it('checkout recusado com 409 (assinatura já ativa) cai no portal, sem mostrar erro', async () => {
    const resposta = { status: 409, data: { detail: { error: 'already_subscribed' } }, statusText: '', headers: {}, config: { headers: new AxiosHeaders() } };
    m(contaApi.checkout).mockRejectedValue(new AxiosError('conflito', 'ERR_BAD_REQUEST', undefined, undefined, resposta));
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Assinar Pro' }));
    await waitFor(() => expect(contaApi.portal).toHaveBeenCalled());
    expect(screen.queryByText(/Não foi possível abrir o pagamento/)).not.toBeInTheDocument();
  });

  it('a volta do checkout confirma a sessão no backend e mostra o plano ativo', async () => {
    m(contaApi.confirmar).mockResolvedValue({ plan: 'total' });
    renderPage('/planos?checkout=success&session_id=cs_test_abc123');
    expect(await screen.findByText(/seu plano Total já está ativo/)).toBeInTheDocument();
    expect(contaApi.confirmar).toHaveBeenCalledWith('u1', 'cs_test_abc123');
  });

  it('pagamento ainda pendente (boleto) não promete o plano', async () => {
    m(contaApi.confirmar).mockResolvedValue({ plan: 'free' });
    renderPage('/planos?checkout=success&session_id=cs_test_boleto');
    expect(await screen.findByText(/o plano é liberado assim que o pagamento for confirmado/)).toBeInTheDocument();
  });

  it('no app nativo a compra fica desativada e o aviso aponta o site (regras das lojas)', async () => {
    nativo.venda = false;
    renderPage();
    expect(await screen.findByText(/Para assinar ou trocar de plano, entre na sua conta pelo site/)).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Assinar Pro' })).toBeDisabled();
  });
});
