import { expect, test } from '@playwright/test';
import { SENHA_DEMO, sessao } from './apoio';

test('senha errada mostra o erro e não entra', async ({ page }) => {
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  await page.getByPlaceholder('seu@email.com').fill('ana.demo@nexa.test');
  await page.getByPlaceholder('••••••••').fill('senha-errada');
  await page.locator('form button[type=submit]').click();
  await expect(page.getByText(/incorretos/i)).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});

test('next externo é ignorado (sem redirecionamento aberto)', async ({ page }) => {
  await page.goto('/login?next=https%3A%2F%2Fexemplo.com');
  await page.waitForLoadState('networkidle');
  await page.getByPlaceholder('seu@email.com').fill('carla.demo@nexa.test');
  await page.getByPlaceholder('••••••••').fill(SENHA_DEMO);
  await page.locator('form button[type=submit]').click();
  await expect(page).toHaveURL(/^http:\/\/(127\.0\.0\.1|localhost):\d+\/chat/);
});

test.describe('com a sessão da Carla', () => {
  test.use({ storageState: sessao('carla') });

  test('access vencido com refresh válido: renova sozinho e fica na tela', async ({ page }) => {
    await page.goto('/chat');
    await page.evaluate(() => localStorage.setItem('jwt_token', 'token.vencido.xx'));
    const renovou = page.waitForResponse((r) => r.url().includes('/auth/refresh') && r.status() === 200);
    await page.goto('/organizar');
    await renovou;
    await expect(page).toHaveURL(/\/organizar/);
  });

  test('sessão morta: vai ao login e, depois de entrar, volta para a tela em que estava', async ({ page }) => {
    await page.goto('/chat');
    await page.evaluate(() => {
      localStorage.setItem('jwt_token', 'token.vencido.xx');
      localStorage.setItem('refresh_token', 'refresh-invalido');
    });
    await page.goto('/goals');
    await expect(page).toHaveURL(/\/login\?next=%2Fgoals/);
    // o redirecionamento é um recarregamento completo: espera a tela assentar antes de digitar
    await page.waitForLoadState('networkidle');
    await page.getByPlaceholder('seu@email.com').fill('carla.demo@nexa.test');
    await page.getByPlaceholder('••••••••').fill(SENHA_DEMO);
    await page.locator('form button[type=submit]').click();
    await expect(page).toHaveURL(/\/goals$/);
  });
});
