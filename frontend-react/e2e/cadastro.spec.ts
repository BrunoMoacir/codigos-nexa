import { expect, test } from '@playwright/test';

test('cadastro em 3 passos cria a conta com o aceite dos termos e entra', async ({ page }) => {
  const email = `e2e_${Date.now()}@nexa.test`;
  const registro = page.waitForRequest((r) => r.url().includes('/auth/register') && r.method() === 'POST');

  await page.goto('/register');
  await page.getByPlaceholder('Seu nome completo').fill('Teste E2E');
  await page.getByPlaceholder('seu@email.com').fill(email);
  await page.getByPlaceholder('Mínimo 8 caracteres').fill('SenhaForte@2026');
  await page.getByPlaceholder('Repita a senha').fill('SenhaForte@2026');
  await page.getByRole('button', { name: 'Continuar', exact: true }).click();

  await expect(page.getByText('Passo 2 de 3')).toBeVisible();
  await page.getByRole('button', { name: 'Continuar', exact: true }).click();

  await expect(page.getByText('Passo 3 de 3')).toBeVisible();
  await page.getByRole('button', { name: 'Confirmar e entrar' }).click();
  await expect(page.getByText('Aceite os termos para continuar')).toBeVisible();

  for (const caixa of await page.locator('input[type=checkbox]').all()) await caixa.check();
  await page.getByRole('button', { name: 'Confirmar e entrar' }).click();

  const corpo = (await registro).postDataJSON();
  expect(corpo.accepted_terms).toBe(true);
  expect(corpo.email).toBe(email);
  await expect(page.getByText('Bem-vindo, Teste.')).toBeVisible();
});

test('e-mail já cadastrado é avisado no passo 1', async ({ page }) => {
  await page.goto('/register');
  await page.getByPlaceholder('Seu nome completo').fill('Ana');
  await page.getByPlaceholder('seu@email.com').fill('ANA.demo@nexa.test');
  await page.getByPlaceholder('Mínimo 8 caracteres').fill('SenhaForte@2026');
  await page.getByPlaceholder('Repita a senha').fill('SenhaForte@2026');
  await page.getByRole('button', { name: 'Continuar', exact: true }).click();
  await expect(page.getByText('Passo 1 de 3')).toBeVisible();
  await expect(page.getByText(/já|cadastrad/i).first()).toBeVisible();
});
