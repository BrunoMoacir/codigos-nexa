import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { verifyEmail } from '../api/auth';
import { describeError } from '../api/errors';
import { session } from '../api/session';
import { AuthCard } from '../components/layout/AuthCard';

type Estado = 'verificando' | 'ok' | 'erro' | 'sem-token';

/** Destino do link "confirmar e-mail" enviado no cadastro (/verify-email?token=…). */
export const VerifyEmailPage: React.FC = () => {
  const [params] = useSearchParams();
  const token = params.get('token') || '';
  const [estado, setEstado] = useState<Estado>(token ? 'verificando' : 'sem-token');
  const [erro, setErro] = useState('');
  const enviado = useRef(false); // o StrictMode monta duas vezes; o token é de uso único

  useEffect(() => {
    if (!token || enviado.current) return;
    enviado.current = true;
    verifyEmail(token)
      .then(() => setEstado('ok'))
      .catch(err => {
        setErro(describeError(err, 'Link inválido ou expirado.').message);
        setEstado('erro');
      });
  }, [token]);

  const destino = session.isActive ? '/dashboard' : '/login';

  return (
    <AuthCard
      title="Confirmação de e-mail"
      footer={<Link to={destino}>{session.isActive ? 'Ir para o painel' : 'Ir para o login'}</Link>}
    >
      {estado === 'verificando' && <div className="ac-msg ok">Confirmando…</div>}
      {estado === 'ok' && <div className="ac-msg ok" role="status">E-mail confirmado. Obrigado!</div>}
      {estado === 'erro' && (
        <div className="ac-msg erro" role="alert">
          {erro} Você pode pedir um novo link na tela de Perfil.
        </div>
      )}
      {estado === 'sem-token' && (
        <div className="ac-msg erro">Este endereço não tem o código de confirmação. Abra o link direto do e-mail.</div>
      )}
    </AuthCard>
  );
};
