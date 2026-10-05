/*
 * HIVE — Service Worker (PWA, R1.d)
 *
 * Responsabilidades:
 *   1. push              → exibe a notificação (payload {title, body, url, tag}
 *                          montado pelo backend em push_sender.send_to_user)
 *   2. notificationclick → foca/abre o app na URL do card (padrão: o Feed)
 *   3. fetch             → navegação e arquivos do app pela REDE primeiro; o
 *                          cache é só a cópia para abrir offline. Chamadas de
 *                          API nunca passam por aqui.
 *
 * Era cache-first para tudo: depois de um deploy o navegador seguia servindo
 * o HTML e o bundle antigos (com a URL de API antiga) até alguém limpar o
 * cache na mão. Os /assets/* têm hash no nome, então podem ser cache-first;
 * o HTML não.
 */

const CACHE_NAME = 'hive-shell-v2';
const SHELL_URLS = ['/', '/manifest.webmanifest', '/favicon.svg'];
const URL_PADRAO = '/feed';

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

function guardar(request, response) {
  if (response && response.ok) {
    const copia = response.clone();
    caches.open(CACHE_NAME).then((cache) => cache.put(request, copia));
  }
  return response;
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // Só GET da própria origem; API (dados financeiros) nunca é cacheada.
  if (request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) {
    return;
  }

  // Arquivo com hash no nome não muda: cache-first é seguro.
  if (url.pathname.startsWith('/assets/')) {
    event.respondWith(caches.match(request).then((c) => c || fetch(request).then((r) => guardar(request, r))));
    return;
  }

  // Navegação e demais arquivos: rede primeiro, cache só se estiver offline.
  event.respondWith(
    fetch(request)
      .then((r) => guardar(request, r))
      .catch(() =>
        caches.match(request).then((c) => c || (request.mode === 'navigate' ? caches.match('/') : undefined))
      )
  );
});

self.addEventListener('push', (event) => {
  let data = { title: 'HIVE', body: '', url: URL_PADRAO, tag: '' };
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
      data: { url: data.url || URL_PADRAO },
      lang: 'pt-BR',
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || URL_PADRAO;

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
