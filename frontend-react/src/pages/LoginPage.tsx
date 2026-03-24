import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';

export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<'login' | 'register'>('login');
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [registerName, setRegisterName] = useState('');
  const [registerEmail, setRegisterEmail] = useState('');
  const [registerPassword, setRegisterPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!loginEmail || !loginPassword) {
      toast.error('Preencha e-mail e senha.');
      return;
    }
    setIsLoading(true);
    const toastId = toast.loading('Autenticando…');
    try {
      const formData = new URLSearchParams();
      formData.append('username', loginEmail);
      formData.append('password', loginPassword);
      const response = await fetch('http://localhost:8000/api/v1/auth/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: formData,
      });
      if (response.ok) {
        const data = await response.json();
        localStorage.setItem('jwt_token', data.access_token);
        localStorage.setItem('user_id', data.user_id);
        toast.success('Bem-vindo!', { id: toastId });
        setTimeout(() => navigate('/home'), 600);
      } else {
        const errorData = await response.json().catch(() => ({}));
        toast.error(errorData.detail || 'Credenciais inválidas', { id: toastId });
      }
    } catch (error) {
      console.error('Erro no login:', error);
      toast.error('Erro de conexão com o servidor', { id: toastId });
    } finally {
      setIsLoading(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!registerName || !registerEmail || !registerPassword) {
      toast.error('Preencha todos os campos.');
      return;
    }
    if (registerPassword.length < 6) {
      toast.error('A senha deve ter pelo menos 6 caracteres.');
      return;
    }
    setIsLoading(true);
    const toastId = toast.loading('Criando conta…');
    try {
      const response = await fetch('http://localhost:8000/api/v1/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: registerEmail, password: registerPassword, full_name: registerName }),
      });
      if (response.ok) {
        toast.success('Conta criada! Faça login.', { id: toastId });
        setTimeout(() => {
          setActiveTab('login');
          setLoginEmail(registerEmail);
          setLoginPassword(registerPassword);
        }, 800);
      } else {
        const errorData = await response.json().catch(() => ({}));
        toast.error(errorData.detail || 'Erro ao criar conta', { id: toastId });
      }
    } catch (error) {
      console.error('Erro no registro:', error);
      toast.error('Erro de conexão com o servidor', { id: toastId });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');

        .lp-root {
          font-family: 'Inter', system-ui, sans-serif;
          min-height: 100vh;
          display: grid;
          grid-template-columns: 1fr 1fr;
          background: #fff;
          color: #111;
        }
        @media (max-width: 768px) {
          .lp-root { grid-template-columns: 1fr; }
          .lp-left  { display: none; }
        }

        /* ── Left panel ── */
        .lp-left {
          background: #0a0a0a;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          padding: 48px;
        }
        .lp-logo-text {
          color: #fff;
          font-size: 20px;
          font-weight: 600;
          letter-spacing: -0.4px;
        }
        .lp-hero {
          flex: 1;
          display: flex;
          flex-direction: column;
          justify-content: center;
          gap: 24px;
        }
        .lp-hero-tag {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          background: rgba(255,255,255,0.08);
          border: 1px solid rgba(255,255,255,0.12);
          border-radius: 100px;
          padding: 6px 14px;
          width: fit-content;
          color: rgba(255,255,255,0.6);
          font-size: 12px;
          font-weight: 500;
          letter-spacing: 0.4px;
          text-transform: uppercase;
        }
        .lp-hero-title {
          font-size: 36px;
          font-weight: 600;
          color: #fff;
          line-height: 1.25;
          letter-spacing: -0.8px;
          margin: 0;
        }
        .lp-hero-title span { color: rgba(255,255,255,0.4); }
        .lp-features {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        .lp-feature {
          display: flex;
          align-items: center;
          gap: 12px;
          color: rgba(255,255,255,0.55);
          font-size: 14px;
        }
        .lp-feature-dot {
          width: 6px; height: 6px;
          border-radius: 50%;
          background: rgba(255,255,255,0.3);
          flex-shrink: 0;
        }
        .lp-footer-text {
          color: rgba(255,255,255,0.25);
          font-size: 12px;
        }

        /* ── Right panel ── */
        .lp-right {
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 48px 40px;
        }
        .lp-form-wrap {
          width: 100%;
          max-width: 360px;
          display: flex;
          flex-direction: column;
          gap: 28px;
        }
        .lp-form-header h2 {
          font-size: 22px;
          font-weight: 600;
          letter-spacing: -0.4px;
          margin: 0 0 4px;
          color: #111;
        }
        .lp-form-header p {
          font-size: 14px;
          color: #888;
          margin: 0;
        }

        /* Tabs */
        .lp-tabs {
          display: flex;
          background: #f4f4f5;
          border-radius: 10px;
          padding: 4px;
          gap: 2px;
        }
        .lp-tab {
          flex: 1;
          padding: 8px;
          border: none;
          border-radius: 7px;
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.15s ease;
          background: transparent;
          color: #888;
        }
        .lp-tab.active {
          background: #fff;
          color: #111;
          box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }

        /* Form fields */
        .lp-field {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        .lp-input {
          width: 100%;
          padding: 11px 14px;
          border: 1px solid #e4e4e7;
          border-radius: 10px;
          font-size: 14px;
          font-family: inherit;
          color: #111;
          background: #fff;
          outline: none;
          transition: border-color 0.15s;
          box-sizing: border-box;
        }
        .lp-input::placeholder { color: #bbb; }
        .lp-input:focus { border-color: #111; }
        .lp-input:disabled { background: #fafafa; color: #999; }

        /* Button */
        .lp-btn {
          width: 100%;
          padding: 12px;
          background: #111;
          color: #fff;
          border: none;
          border-radius: 10px;
          font-size: 14px;
          font-weight: 500;
          font-family: inherit;
          cursor: pointer;
          transition: all 0.15s ease;
          letter-spacing: 0.1px;
        }
        .lp-btn:hover:not(:disabled) { background: #333; }
        .lp-btn:disabled { opacity: 0.45; cursor: not-allowed; }

        /* Footer */
        .lp-form-footer {
          text-align: center;
          font-size: 12px;
          color: #aaa;
          line-height: 1.6;
        }
        .lp-form-footer a { color: #888; text-decoration: underline; cursor: pointer; }
      `}</style>

      <div className="lp-root">
        {/* ── Left Panel ── */}
        <aside className="lp-left">
          <div className="lp-logo-text">Nexa</div>

          <div className="lp-hero">
            <div className="lp-hero-tag">
              <span>●</span> Inteligência Financeira
            </div>
            <h2 className="lp-hero-title">
              Controle total <span>das suas</span> finanças
            </h2>
            <div className="lp-features">
              {[
                'Dashboard inteligente em tempo real',
                'Open Finance via Pluggy integrado',
                'IA estratégica com LangGraph',
              ].map((f) => (
                <div className="lp-feature" key={f}>
                  <span className="lp-feature-dot" />
                  {f}
                </div>
              ))}
            </div>
          </div>

          <div className="lp-footer-text">© 2025 Nexa · Todos os direitos reservados</div>
        </aside>

        {/* ── Right Panel ── */}
        <main className="lp-right">
          <div className="lp-form-wrap">
            <div className="lp-form-header">
              <h2>{activeTab === 'login' ? 'Entrar na conta' : 'Criar conta'}</h2>
              <p>
                {activeTab === 'login'
                  ? 'Acesse seu painel financeiro.'
                  : 'Configure sua conta em segundos.'}
              </p>
            </div>

            <div className="lp-tabs">
              <button
                className={`lp-tab ${activeTab === 'login' ? 'active' : ''}`}
                onClick={() => setActiveTab('login')}
                disabled={isLoading}
              >
                Entrar
              </button>
              <button
                className={`lp-tab ${activeTab === 'register' ? 'active' : ''}`}
                onClick={() => setActiveTab('register')}
                disabled={isLoading}
              >
                Criar Conta
              </button>
            </div>

            {activeTab === 'login' ? (
              <form onSubmit={handleLogin} className="lp-field">
                <input
                  className="lp-input"
                  type="email"
                  placeholder="seu@email.com"
                  value={loginEmail}
                  onChange={(e) => setLoginEmail(e.target.value)}
                  autoComplete="email"
                  disabled={isLoading}
                />
                <input
                  className="lp-input"
                  type="password"
                  placeholder="Senha"
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                  autoComplete="current-password"
                  disabled={isLoading}
                />
                <button type="submit" className="lp-btn" disabled={isLoading}>
                  {isLoading ? 'Entrando…' : 'Entrar'}
                </button>
              </form>
            ) : (
              <form onSubmit={handleRegister} className="lp-field">
                <input
                  className="lp-input"
                  type="text"
                  placeholder="Nome completo"
                  value={registerName}
                  onChange={(e) => setRegisterName(e.target.value)}
                  autoComplete="name"
                  disabled={isLoading}
                />
                <input
                  className="lp-input"
                  type="email"
                  placeholder="seu@email.com"
                  value={registerEmail}
                  onChange={(e) => setRegisterEmail(e.target.value)}
                  autoComplete="email"
                  disabled={isLoading}
                />
                <input
                  className="lp-input"
                  type="password"
                  placeholder="Crie uma senha (mín. 6 caracteres)"
                  value={registerPassword}
                  onChange={(e) => setRegisterPassword(e.target.value)}
                  autoComplete="new-password"
                  disabled={isLoading}
                />
                <button type="submit" className="lp-btn" disabled={isLoading}>
                  {isLoading ? 'Criando conta…' : 'Criar conta'}
                </button>
              </form>
            )}

            <div className="lp-form-footer">
              Ao continuar, você concorda com nossos{' '}
              <a>Termos de Uso</a> e <a>Política de Privacidade</a>
            </div>
          </div>
        </main>
      </div>
    </>
  );
};
