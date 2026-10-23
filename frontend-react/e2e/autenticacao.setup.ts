import { test as setup } from '@playwright/test';
import { entrar, type Persona } from './apoio';

/**
 * Entra uma vez com cada persona e guarda a sessão (localStorage) em
 * e2e/.auth/. O login tem limite de 10 tentativas por minuto por IP: entrar de
 * novo em cada teste estourava o limite e o teste ficava parado no login (429).
 */
for (const persona of ['ana', 'bruno', 'carla'] as Persona[]) {
  setup(`sessão de ${persona}`, async ({ page }) => {
    await entrar(page, persona);
    await page.context().storageState({ path: `e2e/.auth/${persona}.json` });
  });
}
