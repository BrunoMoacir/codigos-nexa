import { defineConfig, devices } from '@playwright/test';

/**
 * Testes de ponta a ponta contra o app e a API de verdade.
 *
 * Pré-requisitos: backend no ar em http://localhost:8000 com as personas de
 * demonstração (`cd backend && python3 -m demo.seed`). O Vite sobe sozinho
 * (ou reaproveita o que já estiver rodando na porta 3000).
 *
 *   npx playwright install chromium     # uma vez
 *   npm run test:e2e
 *
 * Variáveis:
 *   E2E_BASE_URL              testa outro endereço (ex.: o build do nginx) e não sobe o Vite
 *   PLAYWRIGHT_CHROMIUM_PATH  usa um Chromium já instalado em vez do baixado pelo Playwright
 *   HIVE_E2E_CHAT=1           inclui o envio real ao agente (gasta crédito de IA)
 */
const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:3000';
const chromium = process.env.PLAYWRIGHT_CHROMIUM_PATH;

export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: BASE,
    locale: 'pt-BR',
    timezoneId: 'America/Sao_Paulo',
    serviceWorkers: 'block',
    trace: 'retain-on-failure',
    launchOptions: chromium ? { executablePath: chromium } : {},
  },
  projects: [
    // entra uma vez com cada persona e guarda a sessão (ver e2e/autenticacao.setup.ts)
    { name: 'sessoes', testMatch: /autenticacao\.setup\.ts/ },
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1366, height: 860 } }, dependencies: ['sessoes'] },
    { name: 'celular', use: { ...devices['Pixel 7'] }, grep: /@celular/, dependencies: ['sessoes'] },
  ],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: 'npm run dev -- --port 3000 --strictPort --host 127.0.0.1',
        url: BASE,
        reuseExistingServer: true,
        timeout: 60_000,
      },
});
