import { useState } from 'react';
import { forgotPassword } from '../api/auth';
import { describeError } from '../api/errors';
import { AuthCard } from '../components/layout/AuthCard';

/**
 * "Esqueci minha senha". O backend tinha o fluxo completo (link de uso único,
 * 60 min) e a interface não tinha caminho até ele.
 *
 * A resposta é sempre a mesma, exista a conta ou não: o servidor devolve 202
 * nos dois casos para não virar oráculo de quais e-mails estão cadastrados.
 */
export const ForgotPasswordPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [enviado, setEnviado] = useState(false);
  const [erro, setErro] = useState('');

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) { setErro('Informe o e-mail da sua conta.'); return; }
    setEnviando(true);
    setErro('');
    try {
      await forgotPassword(email);
      setEnviado(true);
    } catch (err) {
      setErro(describeError(err, 'Não foi possível enviar agora. Tente de novo.').message);
    } finally {
      setEnviando(false);
    }
  };

  return (
    <AuthCard
      title="Recuperar senha"
      subtitle="Informe o e-mail da conta. Se ele estiver cadastrado, enviamos um link para criar uma nova senha."
    >
      {enviado ? (
        <div className="ac-msg ok" role="status">
          Se houver uma conta com <strong>{email.trim().toLowerCase()}</strong>, o link chega em instantes.
          Ele vale por 60 minutos e só pode ser usado uma vez. Confira também o spam.
        </div>
      ) : (
        <form onSubmit={enviar} noValidate>
          {erro && <div className="ac-msg erro" role="alert">{erro}</div>}
          <label className="ac-label" htmlFor="fp-email">E-mail</label>
          <input id="fp-email" className="ac-input" type="email" autoComplete="email"
            value={email} onChange={e => setEmail(e.target.value)} disabled={enviando} autoFocus />
          <button className="ac-btn" type="submit" disabled={enviando}>
            {enviando ? 'Enviando…' : 'Enviar link'}
          </button>
        </form>
      )}
    </AuthCard>
  );
};
