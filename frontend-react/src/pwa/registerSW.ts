import { ehNativo } from '../native/plataforma';

/**
 * Registro do service worker do PWA (R1.d).
 * Chamado uma vez no boot (main.tsx). Silencioso quando não suportado.
 *
 * Só em produção: no `vite dev` o SW servia do cache os arquivos que o HMR
 * acabou de trocar. Em dev, remove o que tiver ficado registrado.
 */
export function registerServiceWorker(): void {
  if (!('serviceWorker' in navigator)) return;
  // no app nativo os arquivos já vêm do pacote instalado; um SW ali só
  // serviria versões antigas do cache depois de uma atualização da loja
  if (ehNativo()) return;

  if (!import.meta.env.PROD) {
    navigator.serviceWorker.getRegistrations()
      .then((regs) => regs.forEach((r) => r.unregister()))
      .catch(() => {});
    return;
  }

  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js')
      .catch((err) => console.warn('[PWA] falha ao registrar service worker:', err));
  });
}
