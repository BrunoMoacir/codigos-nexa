import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { resetPassword } from '../api/auth';
import { describeError } from '../api/errors';
import { AuthCard } from '../components/layout/AuthCard';

/**
 * Destino do link de "redefinir senha" do e-mail (/reset-password?token=…).
 * O link apontava para a porta 8501 do Streamlit de demonstração, que não tem
 * essa rota. Trocar a senha encerra as outras sessões abertas (backend).
 */
export const ResetPasswordPage: React.FC = () => {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get('token') || '';
  const [senha, setSenha] = useState('');
  const [confirma, setConfirma] = useState('');
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState('');
  const [pronto, setPronto] = useState(false);

  const salvar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (senha.length < 8) { setErro('A senha precisa ter pelo menos 8 caracteres.'); return; }
    if (senha !== confirma) { setErro('As senhas não coincidem.'); return; }
    setSalvando(true);
    setErro('');
    try {
      await resetPassword(token, senha);
      setPronto(true);
    } catch (err) {
      const info = describeError(err);
      setErro(info.kind === 'validation'
        ? `${info.message} Peça um link novo se este já foi usado ou expirou.`
        : info.message);
    } finally {
      setSalvando(false);
    }
  };

  if (!token) {
    return (
      <AuthCard title="Link incompleto" footer={<Link to="/forgot-password">Pedir um link novo</Link>}>
        <div className="ac-msg erro">Este endereço não tem o código de redefinição. Abra o link direto do e-mail.</div>
      </AuthCard>
    );
  }

  return (
    <AuthCard title="Criar nova senha" subtitle="Escolha uma senha com pelo menos 8 caracteres.">
      {pronto ? (
        <>
          <div className="ac-msg ok" role="status">
            Senha alterada. Por segurança, as outras sessões abertas foram encerradas.
          </div>
          <button className="ac-btn" onClick={() => navigate('/login', { replace: true })}>Entrar</button>
        </>
      ) : (
        <form onSubmit={salvar} noValidate>
          {erro && <div className="ac-msg erro" role="alert">{erro}</div>}
          <label className="ac-label" htmlFor="rp-nova">Nova senha</label>
          <input id="rp-nova" className="ac-input" type="password" autoComplete="new-password"
            value={senha} onChange={e => setSenha(e.target.value)} disabled={salvando} autoFocus />
          <label className="ac-label" htmlFor="rp-conf">Confirmar nova senha</label>
          <input id="rp-conf" className="ac-input" type="password" autoComplete="new-password"
            value={confirma} onChange={e => setConfirma(e.target.value)} disabled={salvando} />
          <button className="ac-btn" type="submit" disabled={salvando}>
            {salvando ? 'Salvando…' : 'Salvar nova senha'}
          </button>
        </form>
      )}
    </AuthCard>
  );
};
