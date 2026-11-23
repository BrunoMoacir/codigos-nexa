import { beforeEach, describe, expect, it, vi } from 'vitest';

// ── Capacitor simulado: o teste decide se "está no app nativo" ───────────────
const estado = vi.hoisted(() => ({ nativo: true, plataforma: 'android' as 'android' | 'ios' | 'web' }));

vi.mock('@capacitor/core', () => ({
  Capacitor: { isNativePlatform: () => estado.nativo, getPlatform: () => estado.plataforma },
  registerPlugin: () => plugin,
}));

const plugin = vi.hoisted(() => ({
  configurarWidget: vi.fn(async () => {}),
  limparWidget: vi.fn(async () => {}),
  widgetDisponivel: vi.fn(async () => ({ disponivel: true })),
}));

const push = vi.hoisted(() => {
  const ouvintes: Record<string, (x: unknown) => void> = {};
  return {
    ouvintes,
    api: {
      checkPermissions: vi.fn(async () => ({ receive: 'granted' })),
      requestPermissions: vi.fn(async () => ({ receive: 'granted' })),
      createChannel: vi.fn(async () => {}),
      register: vi.fn(async () => {}),
      unregister: vi.fn(async () => {}),
      addListener: vi.fn(async (evento: string, fn: (x: unknown) => void) => {
        ouvintes[evento] = fn;
        return { remove: vi.fn(async () => { delete ouvintes[evento]; }) };
      }),
    },
  };
});
vi.mock('@capacitor/push-notifications', () => ({ PushNotifications: push.api }));

const browser = vi.hoisted(() => ({ open: vi.fn(async () => {}) }));
vi.mock('@capacitor/browser', () => ({ Browser: browser }));
vi.mock('@capacitor/app', () => ({ App: { addListener: vi.fn(async () => ({ remove: vi.fn() })), exitApp: vi.fn() } }));

const http = vi.hoisted(() => ({ post: vi.fn(), request: vi.fn() }));
vi.mock('../../../api/client', () => ({
  default: http,
  API_BASE_URL: 'https://api.hive.test/api/v1',
  TIMEOUTS: { padrao: 30000, lento: 75000, chat: 95000 },
}));

beforeEach(() => {
  vi.clearAllMocks();
  estado.nativo = true;
  estado.plataforma = 'android';
  localStorage.clear();
  localStorage.setItem('user_id', 'u1');
  localStorage.setItem('jwt_token', 'jwt.da.sessao');
});

describe('push nativo', () => {
  it('registra o token FCM do aparelho no backend', async () => {
    const { ativarPushNativo } = await import('../../../native/pushNativo');
    push.api.register.mockImplementationOnce(async () => {
      push.ouvintes.registration({ value: 'fcmToken:APA91b-abc_123' });
    });
    await expect(ativarPushNativo()).resolves.toBe('subscribed');
    expect(push.api.createChannel).toHaveBeenCalledWith(expect.objectContaining({ id: 'alertas', visibility: 0 }));
    expect(http.post).toHaveBeenCalledWith('/push/devices/u1', { token: 'fcmToken:APA91b-abc_123', platform: 'android' });
  });

  it('novo login confirma o aparelho que já tinha push ligado (o reset revoga no servidor)', async () => {
    const { sincronizarPushNativo } = await import('../../../native/pushNativo');
    localStorage.setItem('hive_push_nativo', 'fcmToken:APA91b-abc_123');
    await sincronizarPushNativo('u1');
    expect(http.post).toHaveBeenCalledWith('/push/devices/u1', { token: 'fcmToken:APA91b-abc_123', platform: 'android' });
  });

  it('login não liga push sozinho: sem token guardado ou sem permissão, nada vai ao backend', async () => {
    const { sincronizarPushNativo } = await import('../../../native/pushNativo');
    await sincronizarPushNativo('u1');
    localStorage.setItem('hive_push_nativo', 'fcmToken:APA91b-abc_123');
    push.api.checkPermissions.mockResolvedValueOnce({ receive: 'denied' });
    await sincronizarPushNativo('u1');
    expect(http.post).not.toHaveBeenCalled();
  });

  it('não registra o token APNs cru do iOS sem Firebase', async () => {
    estado.plataforma = 'ios';
    const { ativarPushNativo } = await import('../../../native/pushNativo');
    push.api.register.mockImplementationOnce(async () => {
      push.ouvintes.registration({ value: 'a'.repeat(64) });
    });
    await expect(ativarPushNativo()).resolves.toBe('not-configured');
    expect(http.post).not.toHaveBeenCalled();
  });

  it('não derruba o ouvinte de toque nas notificações ao registrar', async () => {
    const { ativarPushNativo, ouvirToquesNasNotificacoes } = await import('../../../native/pushNativo');
    ouvirToquesNasNotificacoes(() => {});
    push.api.register.mockImplementationOnce(async () => {
      push.ouvintes.registration({ value: 'fcmToken:xyz' });
    });
    await ativarPushNativo();
    expect(push.ouvintes.pushNotificationActionPerformed).toBeTypeOf('function');
  });

  it('toque numa notificação só navega para rota interna', async () => {
    const { ouvirToquesNasNotificacoes } = await import('../../../native/pushNativo');
    const navegar = vi.fn();
    ouvirToquesNasNotificacoes(navegar);
    await Promise.resolve();
    push.ouvintes.pushNotificationActionPerformed({ notification: { data: { url: '/defesa' } } });
    push.ouvintes.pushNotificationActionPerformed({ notification: { data: { url: 'https://phishing.exemplo' } } });
    push.ouvintes.pushNotificationActionPerformed({ notification: { data: { url: '//phishing.exemplo' } } });
    expect(navegar.mock.calls.map((c) => c[0])).toEqual(['/defesa', '/feed', '/feed']);
  });

  it('o toggle do push no perfil usa o FCM quando está no app', async () => {
    const { getPushState } = await import('../../../pwa/push');
    await expect(getPushState()).resolves.toBe('unsubscribed');
    expect(push.api.checkPermissions).toHaveBeenCalled();
  });
});

describe('widget nativo', () => {
  it('entrega ao código nativo o token de escopo restrito — nunca o JWT', async () => {
    http.post.mockResolvedValueOnce({ data: { token: 'hwt_abc', expires_at: '2027-02-20' } });
    const { configurarWidgetNativo } = await import('../../../native/widgetNativo');
    await configurarWidgetNativo('u1');
    expect(http.post).toHaveBeenCalledWith('/widget/token/u1', { device_id: expect.stringMatching(/^[A-Za-z0-9_-]{8,100}$/) });
    expect(plugin.configurarWidget).toHaveBeenCalledWith({ apiBase: 'https://api.hive.test/api/v1', token: 'hwt_abc' });
    const enviado = JSON.stringify(plugin.configurarWidget.mock.calls);
    expect(enviado).not.toContain('jwt.da.sessao');
  });

  it('logout revoga no servidor e apaga a credencial do aparelho', async () => {
    const { limparWidgetNativo } = await import('../../../native/widgetNativo');
    await limparWidgetNativo('u1');
    expect(http.request).toHaveBeenCalledWith(expect.objectContaining({ method: 'DELETE', url: '/widget/token/u1' }));
    expect(plugin.limparWidget).toHaveBeenCalled();
  });

  it('fora do app nativo não faz nada', async () => {
    estado.nativo = false;
    const { configurarWidgetNativo } = await import('../../../native/widgetNativo');
    await configurarWidgetNativo('u2');
    expect(http.post).not.toHaveBeenCalled();
  });
});

describe('navegação no app nativo', () => {
  it('window.open para fora abre o navegador do sistema; rota interna não', async () => {
    const { iniciarNavegacaoNativa } = await import('../../../native/navegacao');
    const original = vi.fn(() => null);
    window.open = original as unknown as typeof window.open;
    const parar = iniciarNavegacaoNativa();
    window.open('https://wa.me/5531999999999?text=oi', '_blank');
    expect(browser.open).toHaveBeenCalledWith({ url: 'https://wa.me/5531999999999?text=oi' });
    window.open('/chat');
    expect(original).toHaveBeenCalledWith('/chat', undefined, undefined);
    parar();
  });

  it('link externo clicado abre fora do WebView', async () => {
    const { iniciarNavegacaoNativa } = await import('../../../native/navegacao');
    const parar = iniciarNavegacaoNativa();
    const a = document.createElement('a');
    a.href = 'https://valoresareceber.bcb.gov.br/';
    document.body.appendChild(a);
    a.click();
    expect(browser.open).toHaveBeenCalledWith({ url: 'https://valoresareceber.bcb.gov.br/' });
    a.remove();
    parar();
  });
});

describe('assinatura no app', () => {
  it('compra fica fora do app nativo (regras das lojas)', async () => {
    const { vendaNoApp } = await import('../../../native/plataforma');
    expect(vendaNoApp()).toBe(false);
    estado.nativo = false;
    expect(vendaNoApp()).toBe(true);
  });
});
