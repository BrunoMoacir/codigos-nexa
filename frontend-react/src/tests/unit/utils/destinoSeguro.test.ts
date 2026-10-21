import { describe, expect, it } from 'vitest';
import { destinoSeguro } from '../../../utils/destinoSeguro';

describe('destinoSeguro (para onde ir depois do login)', () => {
  it('volta para a tela interna de onde a sessão expirou', () => {
    expect(destinoSeguro('%2Fgoals')).toBe('/goals');
    expect(destinoSeguro('/organizar?mes=2026-09')).toBe('/organizar?mes=2026-09');
  });

  it('sem next, vai para o chat', () => {
    expect(destinoSeguro(null)).toBe('/chat');
    expect(destinoSeguro('')).toBe('/chat');
  });

  it.each([
    ['https://exemplo.com'],
    ['https%3A%2F%2Fexemplo.com'],
    ['//exemplo.com'],
    ['/\\exemplo.com'],
    ['javascript:alert(1)'],
  ])('recusa destino externo %s (sem redirecionamento aberto)', (next) => {
    expect(destinoSeguro(next)).toBe('/chat');
  });

  it('não manda de volta para o próprio login ou cadastro', () => {
    expect(destinoSeguro('/login?next=%2Fchat')).toBe('/chat');
    expect(destinoSeguro('/register')).toBe('/chat');
  });

  it('next mal codificado cai no padrão', () => {
    expect(destinoSeguro('%E0%A4%A')).toBe('/chat');
  });
});
