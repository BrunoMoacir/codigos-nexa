import { API_BASE_URL } from '../api/client';

/**
 * Base ABSOLUTA da API — o widget nativo roda fora do WebView e não tem o
 * proxy do Vite/nginx. No build mobile, VITE_API_URL é obrigatória e https
 * (o vite.config.ts recusa o build sem isso).
 */
export function apiBaseAbsoluta(): string {
  const base = new URL(API_BASE_URL, window.location.origin).toString().replace(/\/+$/, '');
  if (!base.startsWith('https://')) {
    throw new Error('A API do app nativo precisa ser https (defina VITE_API_URL no .env.mobile).');
  }
  return base;
}
