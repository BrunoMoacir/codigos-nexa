import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// Navegador (fora do app nativo): a ponte só concilia o Web Push no login.
vi.mock('../../../native/plataforma', () => ({ ehNativo: () => false, plataforma: () => 'web' }));
const pwa = vi.hoisted(() => ({ getPushState: vi.fn(async () => 'subscribed') }));
vi.mock('../../../pwa/push', () => pwa);

const { PonteNativa } = await import('../../../native/PonteNativa');

function permissao(valor: NotificationPermission) {
  vi.stubGlobal('Notification', { permission: valor });
}

const montar = () =>
  render(
    <MemoryRouter>
      <PonteNativa />
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('Web Push depois de um login novo', () => {
  it('navegador com push ligado reenvia a inscrição (o reset revoga no servidor)', async () => {
    permissao('granted');
    localStorage.setItem('user_id', 'u1');
    localStorage.setItem('jwt_token', 'jwt.da.sessao');
    montar();
    await waitFor(() => expect(pwa.getPushState).toHaveBeenCalledTimes(1));
  });

  it('sem permissão concedida ou sem sessão, nada é conciliado', async () => {
    permissao('default');
    localStorage.setItem('user_id', 'u1');
    localStorage.setItem('jwt_token', 'jwt.da.sessao');
    montar();
    cleanup();
    permissao('granted');
    localStorage.clear();
    montar();
    await new Promise((r) => setTimeout(r, 20));
    expect(pwa.getPushState).not.toHaveBeenCalled();
  });

  it('escrita de outra aba no storage não repete a conciliação da mesma conta', async () => {
    permissao('granted');
    localStorage.setItem('user_id', 'u1');
    localStorage.setItem('jwt_token', 'jwt.da.sessao');
    montar();
    await waitFor(() => expect(pwa.getPushState).toHaveBeenCalledTimes(1));
    window.dispatchEvent(new StorageEvent('storage', { key: 'qualquer' }));
    await new Promise((r) => setTimeout(r, 20));
    expect(pwa.getPushState).toHaveBeenCalledTimes(1);
  });
});
