import { PushNotifications } from '@capacitor/push-notifications';
import apiClient from '../api/client';
import { getUserId } from '../api/session';
import type { PushState } from '../pwa/push';
import { plataforma } from './plataforma';

/**
 * Push nativo (FCM). O token do aparelho vai para POST /push/devices/{uid};
 * no logout sai com DELETE. O backend manda os mesmos alertas WARNING/CRITICAL
 * que o Web Push manda para o navegador.
 */

const CHAVE_TOKEN = 'hive_push_nativo';

/** Token APNs cru (64 hex) = o iOS sem o Firebase: o backend não sabe usá-lo. */
export const ehTokenApnsCru = (token: string) => /^[0-9a-fA-F]{64}$/.test(token);

function tokenGuardado(): string | null {
  try {
    return localStorage.getItem(CHAVE_TOKEN);
  } catch {
    return null;
  }
}

/** Espera o token do registro; remove SÓ os próprios ouvintes (o de toque nas
 * notificações, da PonteNativa, continua de pé). */
async function esperarToken(ms = 15_000): Promise<{ token: Promise<string>; remover: () => Promise<void> }> {
  let resolver!: (t: string) => void;
  let rejeitar!: (e: Error) => void;
  const token = new Promise<string>((res, rej) => {
    resolver = res;
    rejeitar = rej;
  });
  const timer = window.setTimeout(() => rejeitar(new Error('O aparelho não devolveu o token de push.')), ms);
  const ok = await PushNotifications.addListener('registration', (t) => {
    window.clearTimeout(timer);
    resolver(t.value);
  });
  const erro = await PushNotifications.addListener('registrationError', (e) => {
    window.clearTimeout(timer);
    rejeitar(new Error(e.error || 'Falha ao registrar o push.'));
  });
  return {
    token,
    remover: async () => {
      window.clearTimeout(timer);
      await ok.remove();
      await erro.remove();
    },
  };
}

export async function estadoPushNativo(): Promise<PushState> {
  const { receive } = await PushNotifications.checkPermissions();
  if (receive === 'denied') return 'denied';
  return receive === 'granted' && tokenGuardado() ? 'subscribed' : 'unsubscribed';
}

export async function ativarPushNativo(): Promise<PushState> {
  const userId = getUserId();
  if (!userId) throw new Error('Usuário não autenticado');
  let { receive } = await PushNotifications.checkPermissions();
  if (receive !== 'granted') ({ receive } = await PushNotifications.requestPermissions());
  if (receive !== 'granted') return 'denied';

  if (plataforma() === 'android') {
    // canal dos alertas; visibilidade privada na tela de bloqueio (0 = PRIVATE)
    await PushNotifications.createChannel({
      id: 'alertas', name: 'Alertas financeiros', importance: 4, visibility: 0,
      description: 'Saldo negativo, cobranças indevidas e oportunidades',
    });
  }
  const espera = await esperarToken();
  let valor: string;
  try {
    await PushNotifications.register();
    valor = await espera.token;
  } finally {
    await espera.remover();
  }
  if (ehTokenApnsCru(valor)) return 'not-configured'; // iOS sem Firebase (ver docs/MOBILE.md)

  await apiClient.post(`/push/devices/${userId}`, { token: valor, platform: plataforma() });
  try {
    localStorage.setItem(CHAVE_TOKEN, valor);
  } catch {
    /* sem storage: o estado só não persiste */
  }
  return 'subscribed';
}

/**
 * Login novo ou app aberto com sessão: confirma o aparelho no backend.
 *
 * O reset de senha e o "sair de todos os aparelhos" revogam os aparelhos no
 * servidor. Sem esta confirmação, o celular da própria pessoa continuaria
 * aparecendo como inscrito no Perfil e não receberia mais nada depois do novo
 * login. Só age se o push já estava ligado NESTE aparelho (token guardado e
 * permissão concedida). Um login não liga push por conta própria.
 */
export async function sincronizarPushNativo(userId: string): Promise<void> {
  const token = tokenGuardado();
  if (!token) return;
  const { receive } = await PushNotifications.checkPermissions();
  if (receive !== 'granted') return;
  await apiClient.post(`/push/devices/${userId}`, { token, platform: plataforma() });
}

export async function desativarPushNativo(): Promise<PushState> {
  const userId = getUserId();
  const token = tokenGuardado();
  try {
    if (userId && token) await apiClient.request({ method: 'DELETE', url: `/push/devices/${userId}`, data: { token } });
  } catch {
    /* backend fora: o aparelho para de receber assim que o token for revogado */
  }
  try {
    localStorage.removeItem(CHAVE_TOKEN);
    await PushNotifications.unregister();
  } catch {
    /* plugin indisponível */
  }
  return 'unsubscribed';
}

/** Toque na notificação: abre a tela do card (só rotas internas do app). */
export function ouvirToquesNasNotificacoes(navegar: (rota: string) => void): () => void {
  const ouvinte = PushNotifications.addListener('pushNotificationActionPerformed', (acao) => {
    const rota = String(acao.notification?.data?.url || '/feed');
    navegar(rota.startsWith('/') && !rota.startsWith('//') ? rota : '/feed');
  });
  return () => {
    void ouvinte.then((h) => h.remove());
  };
}
