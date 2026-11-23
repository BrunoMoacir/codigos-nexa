import { App } from '@capacitor/app';
import { Browser } from '@capacitor/browser';

/**
 * Navegação no app nativo:
 *  - botão voltar do Android volta uma tela (e sai do app na raiz);
 *  - links e window.open para fora do app abrem no navegador do sistema — o
 *    WebView não navega para outros sites (capacitor.config.ts), e no Android
 *    o window.open simplesmente não fazia nada (WhatsApp do Contato, sites
 *    oficiais dos Direitos, links das respostas do chat).
 */

const ehExterno = (url: string): boolean => {
  try {
    const alvo = new URL(url, window.location.href);
    return (alvo.protocol === 'https:' || alvo.protocol === 'http:') && alvo.origin !== window.location.origin;
  } catch {
    return false;
  }
};

export async function abrirExterno(url: string): Promise<void> {
  const alvo = new URL(url, window.location.href);
  if (alvo.protocol !== 'https:' && alvo.protocol !== 'http:') return;
  await Browser.open({ url: alvo.toString() });
}

export function iniciarNavegacaoNativa(): () => void {
  const voltar = App.addListener('backButton', ({ canGoBack }) => {
    if (canGoBack) window.history.back();
    else void App.exitApp();
  });

  const abrirOriginal = window.open.bind(window);
  window.open = ((url?: string | URL, alvo?: string, recursos?: string) => {
    const texto = url ? String(url) : '';
    if (texto && ehExterno(texto)) {
      void abrirExterno(texto);
      return null;
    }
    return abrirOriginal(url, alvo, recursos);
  }) as typeof window.open;

  const aoClicar = (evento: MouseEvent) => {
    const link = (evento.target as Element | null)?.closest?.('a[href]') as HTMLAnchorElement | null;
    if (!link || !ehExterno(link.href)) return;
    evento.preventDefault();
    void abrirExterno(link.href);
  };
  document.addEventListener('click', aoClicar, true);

  return () => {
    void voltar.then((h) => h.remove());
    window.open = abrirOriginal;
    document.removeEventListener('click', aoClicar, true);
  };
}
