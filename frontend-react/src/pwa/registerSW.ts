/**
 * Registro do service worker do PWA (R1.d).
 * Chamado uma vez no boot (main.tsx). Silencioso quando não suportado.
 */
export function registerServiceWorker(): void {
  if (!('serviceWorker' in navigator)) return;

  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js')
      .catch((err) => console.warn('[PWA] falha ao registrar service worker:', err));
  });
}
