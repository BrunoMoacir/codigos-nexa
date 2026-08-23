import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { API_BASE_URL } from '../api/client';

const css = `
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800;900&display=swap');

  .lp {
    font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
    min-height: 100vh;
    background: #0C0A08;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    position: relative;
  }

  .lp-glow {
    position: fixed;
    inset: 0;
    pointer-events: none;
    background:
      radial-gradient(ellipse 60% 50% at 30% 20%, rgba(212,168,32,0.06) 0%, transparent 70%),
      radial-gradient(ellipse 40% 40% at 75% 80%, rgba(192,16,56,0.04) 0%, transparent 70%);
  }

  .lp-wrap {
    position: relative;
    z-index: 1;
    width: 100%;
    max-width: 380px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 32px;
  }

  .lp-brand {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
  }
  .lp-wordmark {
    font-size: 2.4rem;
    font-weight: 900;
    letter-spacing: 0.18em;
    color: #D4A820;
    line-height: 1;
  }
  .lp-tagline {
    font-size: 0.7rem;
    font-weight: 500;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.25);
  }

  .lp-card {
    width: 100%;
    background: rgba(243,239,234,0.03);
    border: 1px solid rgba(243,239,234,0.08);
    border-radius: 16px;
    padding: 28px 28px 24px;
  }

  .lp-tabs {
    display: flex;
    gap: 0;
    margin-bottom: 24px;
    border-bottom: 1px solid rgba(243,239,234,0.1);
  }
  .lp-tab {
    flex: 1;
    padding: 10px 8px;
    background: transparent;
    border: none;
    font-family: inherit;
    font-size: 0.82rem;
    font-weight: 600;
    color: rgba(243,239,234,0.3);
    cursor: pointer;
    position: relative;
    transition: color 0.18s;
    letter-spacing: 0.02em;
  }
  .lp-tab.on { color: #F3EFEA; }
  .lp-tab.on::after {
    content: '';
    position: absolute;
    bottom: -1px;
    left: 0;
    right: 0;
    height: 2px;
    background: #D4A820;
    border-radius: 2px 2px 0 0;
  }
  .lp-tab:hover:not(.on) { color: rgba(243,239,234,0.6); }

  .lp-fields { display: flex; flex-direction: column; gap: 12px; margin-bottom: 20px; }
  .lp-field label {
    display: block;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.4);
    margin-bottom: 6px;
  }
  .lp-input {
    width: 100%;
    padding: 11px 14px;
    background: rgba(243,239,234,0.05);
    color: #F3EFEA;
    border: 1px solid rgba(243,239,234,0.1);
    border-radius: 10px;
    font-family: inherit;
    font-size: 0.88rem;
    outline: none;
    transition: border-color 0.18s, background 0.18s;
    box-sizing: border-box;
  }
  .lp-input::placeholder { color: rgba(243,239,234,0.2); }
  .lp-input:focus {
    border-color: rgba(212,168,32,0.5);
    background: rgba(243,239,234,0.07);
  }

  .lp-btn {
    width: 100%;
    padding: 13px;
    background: #D4A820;
    color: #0C0A08;
    border: none;
    border-radius: 10px;
    font-family: inherit;
    font-size: 0.88rem;
    font-weight: 800;
    letter-spacing: 0.04em;
    cursor: pointer;
    transition: background 0.18s, transform 0.15s, opacity 0.18s;
    margin-bottom: 12px;
  }
  .lp-btn:hover:not(:disabled) {
    background: #E8C030;
    transform: translateY(-1px);
  }
  .lp-btn:active:not(:disabled) { transform: translateY(0); }
  .lp-btn:disabled { opacity: 0.35; cursor: not-allowed; }

  .lp-note {
    text-align: center;
    font-size: 0.67rem;
    color: rgba(243,239,234,0.18);
    line-height: 1.6;
  }
`;

export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const [tab, setTab] = useState<'login' | 'register'>('login');
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [name, setName] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!loginEmail || !loginPassword) { toast.error('Preencha e-mail e senha.'); return; }
    setLoading(true);
    const tid = toast.loading('Entrando…');
    try {
      const body = new URLSearchParams();
      body.append('username', loginEmail);
      body.append('password', loginPassword);
      const res = await fetch(`${API_BASE_URL}/auth/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body,
      });
      if (res.ok) {
        const data = await res.json();
        localStorage.setItem('jwt_token', data.access_token);
        localStorage.setItem('user_id', data.user_id);
        localStorage.setItem('user_email', loginEmail);
        localStorage.setItem('nexa_data_origin', 'real');
        localStorage.setItem('nexa_data_origin_updated_at', new Date().toISOString());
        if (data.full_name) localStorage.setItem('user_name', data.full_name);
        toast.success('Bem-vindo ao HIVE', { id: tid });
        setTimeout(() => navigate('/chat'), 400);
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Credenciais inválidas', { id: tid });
      }
    } catch {
      toast.error('Erro de conexão', { id: tid });
    } finally { setLoading(false); }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !regEmail || !regPassword) { toast.error('Preencha todos os campos.'); return; }
    if (regPassword.length < 6) { toast.error('Senha mínima de 6 caracteres.'); return; }
    setLoading(true);
    const tid = toast.loading('Criando conta…');
    try {
      const res = await fetch(`${API_BASE_URL}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: regEmail, password: regPassword, full_name: name }),
      });
      if (res.ok) {
        toast.success('Conta criada!', { id: tid });
        setTimeout(() => { setTab('login'); setLoginEmail(regEmail); setLoginPassword(regPassword); }, 600);
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Erro ao criar conta', { id: tid });
      }
    } catch {
      toast.error('Erro de conexão', { id: tid });
    } finally { setLoading(false); }
  };

  return (
    <>
      <style>{css}</style>
      <div className="lp">
        <div className="lp-glow" />
        <div className="lp-wrap">

          <div className="lp-brand">
            <div className="lp-wordmark">HIVE</div>
            <div className="lp-tagline">Inteligência Financeira</div>
          </div>

          <div className="lp-card">
            <div className="lp-tabs">
              <button className={`lp-tab${tab === 'login' ? ' on' : ''}`} onClick={() => setTab('login')} disabled={loading}>
                Entrar
              </button>
              <button className={`lp-tab${tab === 'register' ? ' on' : ''}`} onClick={() => setTab('register')} disabled={loading}>
                Criar conta
              </button>
            </div>

            {tab === 'login' ? (
              <form onSubmit={handleLogin}>
                <div className="lp-fields">
                  <div className="lp-field">
                    <label>E-mail</label>
                    <input className="lp-input" type="email" placeholder="seu@email.com"
                      value={loginEmail} onChange={e => setLoginEmail(e.target.value)}
                      autoComplete="email" disabled={loading} />
                  </div>
                  <div className="lp-field">
                    <label>Senha</label>
                    <input className="lp-input" type="password" placeholder="••••••••"
                      value={loginPassword} onChange={e => setLoginPassword(e.target.value)}
                      autoComplete="current-password" disabled={loading} />
                  </div>
                </div>
                <button type="submit" className="lp-btn" disabled={loading}>
                  {loading ? 'Entrando…' : 'Entrar'}
                </button>
              </form>
            ) : (
              <form onSubmit={handleRegister}>
                <div className="lp-fields">
                  <div className="lp-field">
                    <label>Nome</label>
                    <input className="lp-input" type="text" placeholder="Seu nome"
                      value={name} onChange={e => setName(e.target.value)}
                      autoComplete="name" disabled={loading} />
                  </div>
                  <div className="lp-field">
                    <label>E-mail</label>
                    <input className="lp-input" type="email" placeholder="seu@email.com"
                      value={regEmail} onChange={e => setRegEmail(e.target.value)}
                      autoComplete="email" disabled={loading} />
                  </div>
                  <div className="lp-field">
                    <label>Senha</label>
                    <input className="lp-input" type="password" placeholder="Mínimo 6 caracteres"
                      value={regPassword} onChange={e => setRegPassword(e.target.value)}
                      autoComplete="new-password" disabled={loading} />
                  </div>
                </div>
                <button type="submit" className="lp-btn" disabled={loading}>
                  {loading ? 'Criando…' : 'Criar conta'}
                </button>
              </form>
            )}

            <div className="lp-note">Ao continuar você aceita os Termos de Uso e a Política de Privacidade.</div>
          </div>

        </div>
      </div>
    </>
  );
};
