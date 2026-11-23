import type { CapacitorConfig } from '@capacitor/cli';

/**
 * App nativo (Android/iOS) — o MESMO frontend-react, embrulhado pelo Capacitor.
 *
 * Segurança:
 *  - sem `server.url`: o app sempre roda o build embutido (dist/). Carregar o
 *    código de um servidor remoto permitiria trocar o app sem passar pela loja
 *    e abriria o WebView para qualquer conteúdo daquele host;
 *  - `allowNavigation` vazio: o WebView não navega para fora do app. Links
 *    externos (Stripe, WhatsApp, sites oficiais) abrem no navegador do sistema
 *    (src/native/navegacao.ts);
 *  - https no Android (https://localhost) e sem tráfego em texto puro;
 *  - depuração do WebView só nos builds de debug (padrão do Capacitor).
 *
 * appId: identificador definitivo da loja. Defina o seu ANTES da primeira
 * publicação — depois não muda.
 */
const config: CapacitorConfig = {
  appId: 'br.com.hive.app',
  appName: 'HIVE',
  webDir: 'dist',
  server: {
    androidScheme: 'https',
    cleartext: false,
    allowNavigation: [],
  },
  android: {
    allowMixedContent: false,
  },
  ios: {
    contentInset: 'never',
  },
  plugins: {
    PushNotifications: {
      presentationOptions: ['badge', 'sound', 'alert'],
    },
  },
};

export default config;
