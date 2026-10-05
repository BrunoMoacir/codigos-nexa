import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ChatPage } from '../../../pages/ChatPage';

vi.mock('../../../api/nexa', () => ({
  nexaApi: {
    getChatHistory: vi.fn(),
    getChatSessions: vi.fn(),
    sendChatMessage: vi.fn(),
  },
}));

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => vi.fn() };
});

const { nexaApi } = await import('../../../api/nexa');
const mock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const USER = 'test_user_123';
const SESSAO = 'sessao-salva';
const SESSION_KEY = `hive-session:${USER}`;

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

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  localStorage.setItem('user_id', USER);
  localStorage.setItem('jwt_token', 'test_jwt_123');
  localStorage.setItem(SESSION_KEY, SESSAO);

  mock(nexaApi.getChatHistory).mockResolvedValue([]);
  mock(nexaApi.getChatSessions).mockResolvedValue([]);
  mock(nexaApi.sendChatMessage).mockResolvedValue({
    response: 'Seu orçamento está equilibrado.',
  });
});

describe('ChatPage', () => {
  it('carrega o histórico da conversa salva ao abrir a página', async () => {
    mock(nexaApi.getChatHistory).mockResolvedValue([
      { id: 1, role: 'user', content: 'Quais foram meus gastos no cartão?', created_at: '2026-04-20T10:00:00Z' },
      { id: 2, role: 'assistant', content: 'Você gastou R$ 1.200,00 este mês.', created_at: '2026-04-20T10:00:02Z' },
    ]);

    renderPage();

    await waitFor(() => {
      expect(nexaApi.getChatHistory).toHaveBeenCalledWith(USER, 100, SESSAO);
    });
    expect(await screen.findByText('Quais foram meus gastos no cartão?')).toBeInTheDocument();
    expect(screen.getByText('Você gastou R$ 1.200,00 este mês.')).toBeInTheDocument();
  });

  it('envia a mensagem na conversa atual e mostra a resposta do agente', async () => {
    // Depois do envio a tela recarrega o histórico: o servidor já devolve o par salvo.
    let salvo: unknown[] = [];
    mock(nexaApi.getChatHistory).mockImplementation(async () => salvo);
    mock(nexaApi.sendChatMessage).mockImplementation(async () => {
      salvo = [
        { id: 1, role: 'user', content: 'Meu orçamento está bom?', created_at: '2026-10-05T10:00:00Z' },
        { id: 2, role: 'assistant', content: 'Seu orçamento está equilibrado.', created_at: '2026-10-05T10:00:02Z' },
      ];
      return { response: 'Seu orçamento está equilibrado.' };
    });

    const { container } = renderPage();

    fireEvent.change(screen.getByPlaceholderText('Pergunte sobre seus gastos, tarifas, investimentos...'), {
      target: { value: 'Meu orçamento está bom?' },
    });
    fireEvent.click(container.querySelector('.cp-send') as HTMLButtonElement);

    await waitFor(() => {
      expect(nexaApi.sendChatMessage).toHaveBeenCalledWith(USER, 'Meu orçamento está bom?', SESSAO);
    });
    expect(await screen.findByText('Seu orçamento está equilibrado.')).toBeInTheDocument();
  });

  it('"Nova conversa" abre outra sessão sem apagar a anterior', async () => {
    mock(nexaApi.getChatHistory).mockResolvedValueOnce([
      { id: 1, role: 'user', content: 'Preciso rever meu orçamento', created_at: '2026-04-20T10:00:00Z' },
    ]);

    renderPage();
    await screen.findByText('Preciso rever meu orçamento');

    fireEvent.click(screen.getByRole('button', { name: /Nova conversa/ }));

    await waitFor(() => {
      expect(screen.queryByText('Preciso rever meu orçamento')).not.toBeInTheDocument();
    });
    const nova = localStorage.getItem(SESSION_KEY);
    expect(nova).toBeTruthy();
    expect(nova).not.toBe(SESSAO);
    await waitFor(() => {
      expect(nexaApi.getChatHistory).toHaveBeenLastCalledWith(USER, 100, nova);
    });
    // A conversa anterior continua guardada — nada é apagado no servidor.
    expect(localStorage.getItem(`hive-chat:${USER}:${SESSAO}`)).toContain('Preciso rever meu orçamento');
  });

  it('lista as conversas anteriores e abre a escolhida', async () => {
    mock(nexaApi.getChatSessions).mockResolvedValue([
      { session_id: 'sessao-antiga', title: 'Quanto posso gastar?', last_message_at: '2026-10-01T10:00:00Z', message_count: 4 },
    ]);

    renderPage();
    fireEvent.click(screen.getByTitle('Conversas'));
    fireEvent.click(await screen.findByText('Quanto posso gastar?'));

    await waitFor(() => {
      expect(nexaApi.getChatHistory).toHaveBeenCalledWith(USER, 100, 'sessao-antiga');
    });
  });
});
