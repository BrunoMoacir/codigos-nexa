import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../api/client', () => ({
  default: { get: vi.fn() },
  TIMEOUTS: { padrao: 30000, lento: 75000, chat: 95000 },
}));

const { default: apiClient } = await import('../../../api/client');
const { nexaApi } = await import('../../../api/nexa');
const get = apiClient.get as unknown as ReturnType<typeof vi.fn>;

function iso(mesesAtras: number, dia = 15) {
  const d = new Date();
  const alvo = new Date(d.getFullYear(), d.getMonth() - mesesAtras, dia);
  return `${alvo.getFullYear()}-${String(alvo.getMonth() + 1).padStart(2, '0')}-${String(alvo.getDate()).padStart(2, '0')}`;
}

const lancamento = (date: string, i: number) => ({ id: `t${i}`, description: 'x', amount: -10, date, category: 'Outros', type: 'expense' });

beforeEach(() => get.mockReset());

describe('getTransactionsWindow (Organização)', () => {
  it('pede 1.000 por página e para quando não há mais', async () => {
    get.mockResolvedValueOnce({ data: { total: 2, has_more: false, transactions: [lancamento(iso(0), 1), lancamento(iso(1), 2)] } });
    const r = await nexaApi.getTransactionsWindow('u1', 12);
    expect(get).toHaveBeenCalledTimes(1);
    expect(get).toHaveBeenCalledWith('/transactions/u1', { params: { limit: 1000, offset: 0 } });
    expect(r.transactions).toHaveLength(2);
  });

  it('pagina até cobrir a janela de 12 meses — não só os 100 mais recentes', async () => {
    const pagina1 = Array.from({ length: 1000 }, (_, i) => lancamento(iso(Math.floor(i / 200)), i));
    const pagina2 = Array.from({ length: 500 }, (_, i) => lancamento(iso(5 + Math.floor(i / 100)), 1000 + i));
    get
      .mockResolvedValueOnce({ data: { total: 1500, has_more: true, transactions: pagina1 } })
      .mockResolvedValueOnce({ data: { total: 1500, has_more: false, transactions: pagina2 } });
    const r = await nexaApi.getTransactionsWindow('u1', 12);
    expect(get).toHaveBeenCalledTimes(2);
    expect(get).toHaveBeenLastCalledWith('/transactions/u1', { params: { limit: 1000, offset: 1000 } });
    expect(r.transactions).toHaveLength(1500);
  });

  it('para de paginar quando a página já passou do início da janela e descarta o que é mais antigo', async () => {
    const pagina = [lancamento(iso(0), 1), lancamento(iso(11), 2), lancamento(iso(14), 3)];
    get.mockResolvedValueOnce({ data: { total: 5000, has_more: true, transactions: pagina } });
    const r = await nexaApi.getTransactionsWindow('u1', 12);
    expect(get).toHaveBeenCalledTimes(1);
    expect(r.transactions.map((t) => t.id)).toEqual(['t1', 't2']);
  });
});
