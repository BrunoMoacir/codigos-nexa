import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ChatPage } from '../../../pages/ChatPage';

vi.mock('../../../api/nexa', () => ({
  nexaApi: {
    getChatHistory: vi.fn(),
    sendChatMessage: vi.fn(),
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
        <ChatPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  localStorage.setItem('user_id', 'test_user_123');
  localStorage.setItem('jwt_token', 'test_jwt_123');

  (nexaApi.getChatHistory as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  (nexaApi.sendChatMessage as ReturnType<typeof vi.fn>).mockResolvedValue({
    response: 'Seu orçamento está equilibrado.',
  });
});

describe('ChatPage', () => {
  it('carrega o histórico salvo do backend ao abrir a página', async () => {
    (nexaApi.getChatHistory as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: 1,
        role: 'human',
        content: 'Quais foram meus gastos no cartão?',
        created_at: '2026-04-20T10:00:00Z',
      },
      {
        id: 2,
        role: 'assistant',
        content: 'Você gastou R$ 1.200,00 este mês.',
        created_at: '2026-04-20T10:00:02Z',
      },
    ]);

    renderPage();

    await waitFor(() => {
      expect(nexaApi.getChatHistory).toHaveBeenCalledWith('test_user_123', 100);
    });

    expect(await screen.findByText('Quais foram meus gastos no cartão?')).toBeInTheDocument();
    expect(screen.getByText('Você gastou R$ 1.200,00 este mês.')).toBeInTheDocument();
  });

  it('envia uma mensagem e mostra a resposta do agente', async () => {
    renderPage();

    const input = screen.getByPlaceholderText('Pergunte sobre orçamento, metas, cartões ou simulações...');
    fireEvent.change(input, { target: { value: 'Meu orçamento está bom?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar' }));

    await waitFor(() => {
      expect(nexaApi.sendChatMessage).toHaveBeenCalledWith('test_user_123', 'Meu orçamento está bom?');
    });

    expect(await screen.findByText('Seu orçamento está equilibrado.')).toBeInTheDocument();
  });
});
