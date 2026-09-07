// Modo demonstração — por conta (localStorage), não global.
//
// Contas sem banco conectado mostram por padrão o estado real: vazio, com
// CTA para conectar. O modo demo existe só para permitir ver como as telas
// ficam com dados — ativado manualmente por conta em ProfilePage, nunca
// ligado por padrão numa conta nova.

function key(userId: string): string {
  return `hive-demo-mode:${userId}`;
}

export function isDemoMode(userId: string | null | undefined): boolean {
  if (!userId) return false;
  try {
    return localStorage.getItem(key(userId)) === 'true';
  } catch {
    return false;
  }
}

export function setDemoMode(userId: string, enabled: boolean): void {
  try {
    localStorage.setItem(key(userId), enabled ? 'true' : 'false');
  } catch {
    // localStorage indisponível — modo demo simplesmente não persiste.
  }
}
