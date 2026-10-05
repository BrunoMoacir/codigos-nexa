/**
 * Web Push do PWA (R1.d) — inscrição/cancelamento junto ao backend.
 *
 * Fluxo de inscrição:
 *   1. GET /push/vapid-public-key  → chave pública (base64url)
 *   2. pushManager.subscribe(...)  → PushSubscription do navegador
 *   3. POST /push/subscribe/{uid}  → persiste em push_subscriptions
 *
 * Cards WARNING/CRITICAL do NotificationEngine passam a chegar como
 * notificação de sistema mesmo com o app fechado.
 */
import apiClient from '../api/client';
import { getUserId } from '../api/session';

export type PushState = 'unsupported' | 'not-configured' | 'denied' | 'subscribed' | 'unsubscribed';

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = atob(base64);
  return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)));
}

function isSupported(): boolean {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
}

/**
 * Estado conciliado navegador × servidor. O navegador podia ter inscrição que
 * o servidor perdeu (banco recriado, outra conta no mesmo aparelho): a tela
 * dizia "ativado" e nenhum alerta chegava. Nesse caso reenvia a inscrição.
 */
export async function getPushState(): Promise<PushState> {
  if (!isSupported()) return 'unsupported';
  if (Notification.permission === 'denied') return 'denied';

  const userId = getUserId();
  const { data } = await apiClient.get(userId ? `/push/status/${userId}` : '/push/vapid-public-key');
  if (!data.configured) return 'not-configured';

  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  if (!subscription) return 'unsubscribed';
  if (userId && data.subscribed === false) {
    try {
      await apiClient.post(`/push/subscribe/${userId}`, subscription.toJSON());
    } catch {
      return 'unsubscribed';
    }
  }
  return 'subscribed';
}

export async function subscribeToPush(): Promise<PushState> {
  if (!isSupported()) return 'unsupported';

  const userId = getUserId();
  if (!userId) throw new Error('Usuário não autenticado');

  const { data } = await apiClient.get('/push/vapid-public-key');
  if (!data.configured || !data.public_key) return 'not-configured';

  const permission = await Notification.requestPermission();
  if (permission !== 'granted') return 'denied';

  const registration = await navigator.serviceWorker.ready;
  const subscription =
    (await registration.pushManager.getSubscription()) ||
    (await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(data.public_key) as BufferSource,
    }));

  await apiClient.post(`/push/subscribe/${userId}`, subscription.toJSON());
  return 'subscribed';
}

export async function unsubscribeFromPush(): Promise<PushState> {
  if (!isSupported()) return 'unsupported';

  const userId = getUserId();
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();

  if (subscription) {
    if (userId) {
      try {
        await apiClient.request({
          method: 'DELETE',
          url: `/push/subscribe/${userId}`,
          data: subscription.toJSON(),
        });
      } catch {
        // backend indisponível não impede o unsubscribe local
      }
    }
    await subscription.unsubscribe();
  }
  return 'unsubscribed';
}
