import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AxiosError, AxiosHeaders } from 'axios';
import { ChatPage } from '../../../pages/ChatPage';

vi.mock('../../../api/chat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api/chat')>();
  return {
    ...actual,
    chatApi: { historico: vi.fn(), enviar: vi.fn(), apagar: vi.fn(), ultimaSessao: vi.fn() },
  };
});

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => vi.fn() };
});

const { chatApi } = await import('../../../api/chat');
const historico = chatApi.historico as ReturnType<typeof vi.fn>;
const enviar = chatApi.enviar as ReturnType<typeof vi.fn>;
const apagar = chatApi.apagar as ReturnType<typeof vi.fn>;
const ultimaSessao = chatApi.ultimaSessao as ReturnType<typeof vi.fn>;

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function erroHttp(status: number, detail: unknown) {
  const headers = new AxiosHeaders();
  return new AxiosError('falhou', String(status), { headers }, null, {
    status, statusText: '', headers, config: { headers }, data: { detail },
  });
}

const SESSAO = 'sessao-salva-1';

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  localStorage.setItem('user_id', 'test_user_123');
  localStorage.setItem('jwt_token', 'test_jwt_123');
  localStorage.setItem('hive_chat_session:test_user_123', SESSAO);

  historico.mockResolvedValue([]);
  enviar.mockResolvedValue({
    response: 'Seu orçamento está **equilibrado**.',
    session_id: SESSAO,
    tools_used: ['get_budget_advice'],
    created_at: '2026-10-04T12:00:00Z',
  });
  apagar.mockResolvedValue({ deleted_count: 2 });
  ultimaSessao.mockResolvedValue(null);
});

describe('ChatPage', () => {
  it('carrega só a conversa da sessão salva', async () => {
    historico.mockResolvedValue([
      { id: 1, role: 'user', content: 'Quais foram meus gastos no cartão?', session_id: SESSAO, created_at: '2026-04-20T10:00:00Z' },
      { id: 2, role: 'assistant', content: 'Você gastou R$ 1.200,00 este mês.', session_id: SESSAO, created_at: '2026-04-20T10:00:02Z' },
    ]);

    renderPage();

    await waitFor(() => expect(historico).toHaveBeenCalledWith('test_user_123', SESSAO, 100));
    expect(await screen.findByText('Quais foram meus gastos no cartão?')).toBeInTheDocument();
    expect(screen.getByText('Você gastou R$ 1.200,00 este mês.')).toBeInTheDocument();
  });

  it('sem sessão salva no aparelho, retoma a da última conversa', async () => {
    localStorage.removeItem('hive_chat_session:test_user_123');
    ultimaSessao.mockResolvedValue('sessao-de-outro-aparelho');
    renderPage();
    await waitFor(() => expect(historico).toHaveBeenCalledWith('test_user_123', 'sessao-de-outro-aparelho', 100));
    expect(localStorage.getItem('hive_chat_session:test_user_123')).toBe('sessao-de-outro-aparelho');
  });

  it('envia na sessão atual, renderiza markdown e mostra as ferramentas consultadas', async () => {
    renderPage();

    const input = await screen.findByLabelText('Mensagem para o agente');
    fireEvent.change(input, { target: { value: 'Meu orçamento está bom?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar' }));

    await waitFor(() => expect(enviar).toHaveBeenCalledWith('test_user_123', 'Meu orçamento está bom?', SESSAO));
    const negrito = await screen.findByText('equilibrado');
    expect(negrito.tagName).toBe('STRONG');
    expect(screen.getByText(/Consultou: orçamento 50\/30\/20/)).toBeInTheDocument();
  });

  it('"Nova conversa" troca de sessão sem apagar o histórico', async () => {
    historico.mockResolvedValue([
      { id: 1, role: 'user', content: 'Preciso rever meu orçamento', session_id: SESSAO, created_at: '2026-04-20T10:00:00Z' },
    ]);
    renderPage();
    await screen.findByText('Preciso rever meu orçamento');

    fireEvent.click(screen.getByRole('button', { name: 'Nova conversa' }));

    expect(await screen.findByText(/Como posso/)).toBeInTheDocument();
    expect(apagar).not.toHaveBeenCalled();
    expect(localStorage.getItem('hive_chat_session:test_user_123')).not.toBe(SESSAO);
  });

  it('"Apagar conversa" apaga só a sessão atual', async () => {
    historico.mockResolvedValue([
      { id: 1, role: 'user', content: 'Preciso rever meu orçamento', session_id: SESSAO, created_at: '2026-04-20T10:00:00Z' },
    ]);
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderPage();
    await screen.findByText('Preciso rever meu orçamento');

    fireEvent.click(screen.getByRole('button', { name: 'Apagar conversa' }));

    await waitFor(() => expect(apagar).toHaveBeenCalledWith('test_user_123', SESSAO));
  });

  it('cota do plano (402) vira mensagem com link para os planos, não "backend fora do ar"', async () => {
    enviar.mockRejectedValue(erroHttp(402, {
      reason: 'Você usou as 5 mensagens de IA de hoje do plano Free.',
      required_plan: 'pro',
    }));
    renderPage();

    const input = await screen.findByLabelText('Mensagem para o agente');
    fireEvent.change(input, { target: { value: 'Oi' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar' }));

    expect(await screen.findByText(/5 mensagens de IA de hoje/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Ver planos/ })).toHaveAttribute('href', '/planos');
    expect(screen.queryByText(/backend/i)).not.toBeInTheDocument();
  });
});
