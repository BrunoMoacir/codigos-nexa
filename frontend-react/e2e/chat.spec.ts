import { expect, test } from '@playwright/test';
import { sessao, vigiar } from './apoio';

test.describe('chat', () => {
  test.use({ storageState: sessao('ana') });

  test('lista as conversas e abre uma conversa nova vazia', async ({ page }) => {
    const problemas = vigiar(page);
    await page.goto('/chat');
    await page.getByTitle('Conversas').click();
    await expect(page.getByText('Conversas').first()).toBeVisible();
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: /Nova conversa/ }).click();
    await expect(page.getByPlaceholder(/Pergunte sobre seus gastos/)).toBeEmpty();
    expect(problemas).toEqual([]);
  });

  // Gasta crédito de IA: só com HIVE_E2E_CHAT=1
  test('envia uma pergunta e recebe a resposta do agente', async ({ page }) => {
    test.skip(!process.env.HIVE_E2E_CHAT, 'defina HIVE_E2E_CHAT=1 para incluir o agente');
    const problemas = vigiar(page);
    await page.goto('/chat');
    await page.getByRole('button', { name: /Nova conversa/ }).click();
    await page.getByPlaceholder(/Pergunte sobre seus gastos/).fill('Quanto posso gastar até o fim do mês?');
    const resposta = page.waitForResponse((r) => r.url().includes('/chat/') && r.request().method() === 'POST', { timeout: 100_000 });
    await page.locator('.cp-send').click();
    expect((await resposta).status()).toBe(200);
    await expect(page.locator('.cp-bubble').last()).not.toBeEmpty();
    expect(problemas).toEqual([]);
  });
});
