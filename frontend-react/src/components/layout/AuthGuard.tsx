import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useSession } from '../../hooks/useAuth';

/**
 * Guarda das rotas privadas.
 *
 * Não existia nenhuma: qualquer rota renderizava sem sessão, e as páginas
 * tratavam "não está logado" como "não tem banco conectado" — mostravam
 * dados de demonstração e chamavam `/transactions/` com user_id vazio.
 *
 * Basta haver refresh token para entrar: o access expira em 30 min, e o
 * cliente HTTP o renova na primeira chamada que tomar 401.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { isActive } = useSession();
  const location = useLocation();

  if (!isActive) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <>{children}</>;
}

/** Nome antigo, mantido para quem importava. */
export const AuthGuard = RequireAuth;
