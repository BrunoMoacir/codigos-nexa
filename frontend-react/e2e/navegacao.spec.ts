import { expect, test } from '@playwright/test';
import { semLixoNaTela, sessao, vigiar, type Persona } from './apoio';

/** Toda tela logada abre sem erro de API e sem lixo de formatação, para cada plano. */
const TELAS = [
  '/chat', '/feed', '/organizar', '/profile', '/strategies', '/goals', '/connections',
  '/defesa', '/direitos', '/impostos', '/wrapped', '/planos', '/widget', '/organizar/cartao/novo',
];

const PERSONAS: { persona: Persona; plano: string }[] = [
  { persona: 'ana', plano: 'Total' },
  { persona: 'bruno', plano: 'Pro (MEI)' },
  { persona: 'carla', plano: 'Free' },
];

for (const { persona, plano } of PERSONAS) {
  test.describe(`${persona} (${plano})`, () => {
    test.use({ storageState: sessao(persona) });

    test('todas as telas abrem sem erro', async ({ page }) => {
      const problemas = vigiar(page);
      for (const rota of TELAS) {
        await page.goto(rota);
        await page.waitForLoadState('networkidle');
        await expect(page.locator('body')).not.toBeEmpty();
        await semLixoNaTela(page);
      }
      expect(problemas).toEqual([]);
    });
  });
}

test.describe('com a sessão da Ana', () => {
  test.use({ storageState: sessao('ana') });

  test('as três abas navegam pelo menu @celular', async ({ page }) => {
    const problemas = vigiar(page);
    await page.goto('/chat');
    for (const [aba, rota] of [['Oportunidades', /\/feed/], ['Organização', /\/organizar/], ['Chat IA', /\/chat/]] as const) {
      await page.getByRole('link', { name: aba }).or(page.getByRole('button', { name: aba })).first().click();
      await expect(page).toHaveURL(rota);
    }
    expect(problemas).toEqual([]);
  });

  test('/dashboard (rota que o backend ainda emite) leva à Organização', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page).toHaveURL(/\/organizar/);
  });
});
