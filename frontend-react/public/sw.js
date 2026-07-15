/*
 * Nexa — Service Worker (PWA, R1.d)
 *
 * Responsabilidades:
 *   1. push            → exibe a notificação (payload {title, body, url, tag}
 *                        montado pelo backend em push_sender.send_to_user)
 *   2. notificationclick → foca/abre o app na URL do card
 *   3. fetch            → cache-first do shell estático (instalabilidade);
 *                        chamadas de API nunca são cacheadas
 */

const CACHE_NAME = 'nexa-shell-v1';
const SHELL_URLS = ['/', '/manifest.webmanifest', '/favicon.svg'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_URLS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // API e requests não-GET: rede sempre, sem cache (dados financeiros)
  if (event.request.method !== 'GET' || url.pathname.startsWith('/api/')) {
    return;
  }

  // Shell estático: cache-first com atualização em background
  event.respondWith(
    caches.match(event.request).then(
      (cached) =>
        cached ||
        fetch(event.request).then((response) => {
          if (response.ok && url.origin === self.location.origin) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return response;
        })
    )
  );
});

self.addEventListener('push', (event) => {
  let data = { title: 'Nexa', body: '', url: '/strategies', tag: '' };
  try {
    data = { ...data, ...event.data.json() };
  } catch {
    data.body = event.data ? event.data.text() : '';
  }

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      tag: data.tag || undefined, // mesmo tag → substitui, não empilha
      icon: '/favicon.svg',
      badge: '/favicon.svg',
      data: { url: data.url },
      lang: 'pt-BR',
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || '/strategies';

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ('focus' in client) {
          client.focus();
          if ('navigate' in client) client.navigate(targetUrl);
          return;
        }
      }
      return self.clients.openWindow(targetUrl);
    })
  );
});
