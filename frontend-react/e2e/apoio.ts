import { expect, type Page } from '@playwright/test';

export type Persona = 'ana' | 'bruno' | 'carla';

export const SENHA_DEMO = 'demo1234';

/** Sessão salva pelo passo de preparação — use com `test.use({ storageState: sessao('ana') })`. */
export const sessao = (persona: Persona) => `e2e/.auth/${persona}.json`;

/** Entra com uma persona de demonstração pela tela de login. */
export async function entrar(page: Page, persona: Persona) {
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  await page.getByPlaceholder('seu@email.com').fill(`${persona}.demo@nexa.test`);
  await page.getByPlaceholder('••••••••').fill(SENHA_DEMO);
  await page.locator('form button[type=submit]').click();
  await expect(page).toHaveURL(/\/chat/);
}

/**
 * Registra tudo o que dá errado na página: respostas 4xx/5xx da API, erros de
 * JavaScript e erros no console. O teste termina exigindo a lista vazia.
 */
export function vigiar(page: Page) {
  const problemas: string[] = [];
  page.on('pageerror', (e) => problemas.push(`erro de página: ${e.message}`));
  page.on('console', (m) => {
    // a fonte vem de um CDN; sem rede para ele o app usa a fonte do sistema
    if (m.type() === 'error' && !/fontshare|ERR_NAME_NOT_RESOLVED|favicons/i.test(m.text())) {
      problemas.push(`console: ${m.text().slice(0, 200)}`);
    }
  });
  page.on('response', (r) => {
    if (r.url().includes('/api/v1/') && r.status() >= 400) {
      problemas.push(`HTTP ${r.status()} ${r.request().method()} ${new URL(r.url()).pathname}`);
    }
  });
  return problemas;
}

/** Texto que nunca deveria aparecer numa tela pronta. */
export async function semLixoNaTela(page: Page) {
  const texto = await page.locator('body').innerText();
  for (const lixo of ['NaN', 'undefined', '[object Object]', 'Invalid Date']) {
    expect(texto, `"${lixo}" na tela ${page.url()}`).not.toContain(lixo);
  }
}
