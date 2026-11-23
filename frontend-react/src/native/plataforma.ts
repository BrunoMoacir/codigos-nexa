import { Capacitor } from '@capacitor/core';

/**
 * Onde o app está rodando. No navegador (web/PWA) tudo segue como sempre; no
 * app nativo (Capacitor) os módulos deste diretório trocam o que o WebView não
 * faz: push, downloads, links externos, botão voltar.
 */
export const ehNativo = (): boolean => Capacitor.isNativePlatform();

export const plataforma = (): 'android' | 'ios' | 'web' => {
  const p = Capacitor.getPlatform();
  return p === 'android' || p === 'ios' ? p : 'web';
};

/**
 * Assinatura dentro do app nativo: desligada. As lojas exigem o faturamento
 * delas para vender assinatura digital dentro do app (App Store 3.1.1; Google
 * Play Billing) — abrir o Stripe ali pode reprovar o app. No app a pessoa vê o
 * plano e os limites; assinar e trocar de plano é pelo site.
 */
export const vendaNoApp = (): boolean => !ehNativo();
