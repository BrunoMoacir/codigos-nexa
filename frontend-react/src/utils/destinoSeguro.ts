/**
 * Para onde ir depois do login. O cliente HTTP manda para /login?next=<tela>
 * quando a sessão expira; aceitamos só caminhos internos do próprio app — um
 * `next=https://outro.site` ou `next=//outro.site` viraria redirecionamento aberto.
 */
export function destinoSeguro(next: string | null | undefined, padrao = '/chat'): string {
  if (!next) return padrao;
  let destino: string;
  try {
    destino = decodeURIComponent(next);
  } catch {
    return padrao;
  }
  if (!destino.startsWith('/') || destino.startsWith('//') || destino.startsWith('/\\')) return padrao;
  if (/^\/(login|register)(\/|\?|$)/.test(destino)) return padrao;
  return destino;
}
