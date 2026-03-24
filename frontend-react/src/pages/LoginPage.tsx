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
      // API call
      const formData = new URLSearchParams();
      formData.append('username', loginEmail);
      formData.append('password', loginPassword);

      const response = await fetch('http://localhost:8000/api/v1/auth/token', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: formData,
      });

      if (response.ok) {
        const data = await response.json();

        // Salvar tokens
        localStorage.setItem('jwt_token', data.access_token);
        localStorage.setItem('user_id', data.user_id);

        toast.success('✅ Bem-vindo! Abrindo seu painel…', { id: toastId });

        setTimeout(() => {
          navigate('/home');
        }, 800);
      } else {
        const errorData = await response.json().catch(() => ({}));
        const errorMsg = errorData.detail || 'Credenciais inválidas';
        toast.error(`❌ ${errorMsg}`, { id: toastId });
      }
    } catch (error) {
      console.error('Erro no login:', error);
      toast.error('❌ Erro de conexão com servidor', { id: toastId });
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
    const toastId = toast.loading('Criando sua conta Nexa…');

    try {
      const response = await fetch('http://localhost:8000/api/v1/auth/register', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email: registerEmail,
          password: registerPassword,
          full_name: registerName,
        }),
      });

      if (response.ok) {
        toast.success('🎉 Conta criada! Fazendo login…', { id: toastId });

        // Auto-login após registro
        setTimeout(() => {
          setActiveTab('login');
          setLoginEmail(registerEmail);
          setLoginPassword(registerPassword);
          toast.success('Agora faça login com suas credenciais');
        }, 1000);
      } else {
        const errorData = await response.json().catch(() => ({}));
        const errorMsg = errorData.detail || 'Erro ao criar conta';
        toast.error(`❌ ${errorMsg}`, { id: toastId });
      }
    } catch (error) {
      toast.error('❌ Erro de conexão com servidor', { id: toastId });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo + Tagline */}
        <div className="text-center mb-8">
          <div className="text-6xl mb-3">💜</div>
          <h1
            className="text-5xl font-extrabold mb-2"
            style={{
              background: 'linear-gradient(135deg, #6366f1, #a78bfa)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            Nexa
          </h1>
          <p className="text-slate-500 text-base tracking-wide">
            Seu cérebro financeiro com IA
          </p>
        </div>

        {/* Card de Login */}
        <div className="glass-card">
          <p className="text-xs text-slate-500 text-center mb-6 tracking-wider">
            ACESSE OU CRIE SUA CONTA
          </p>

          {/* Tabs */}
          <div className="flex gap-2 mb-6">
            <button
              onClick={() => setActiveTab('login')}
              disabled={isLoading}
              className={`flex-1 py-3 px-4 rounded-xl font-semibold text-sm transition-all ${
                activeTab === 'login'
                  ? 'bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-lg'
                  : 'bg-slate-800/50 text-slate-400 hover:bg-slate-800/70'
              }`}
            >
              Entrar
            </button>
            <button
              onClick={() => setActiveTab('register')}
              disabled={isLoading}
              className={`flex-1 py-3 px-4 rounded-xl font-semibold text-sm transition-all ${
                activeTab === 'register'
                  ? 'bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-lg'
                  : 'bg-slate-800/50 text-slate-400 hover:bg-slate-800/70'
              }`}
            >
              Criar Conta
            </button>
          </div>

          {/* Login Form */}
          {activeTab === 'login' && (
            <form onSubmit={handleLogin} className="space-y-4">
              <input
                className="input-modern w-full"
                type="email"
                placeholder="📧  ex: seuemail@dominio.com"
                value={loginEmail}
                onChange={(e) => setLoginEmail(e.target.value)}
                autoComplete="email"
                disabled={isLoading}
              />
              <input
                className="input-modern w-full"
                type="password"
                placeholder="🔑  Senha"
                value={loginPassword}
                onChange={(e) => setLoginPassword(e.target.value)}
                autoComplete="current-password"
                disabled={isLoading}
              />
              <button
                type="submit"
                className="btn-primary w-full disabled:opacity-50"
                disabled={isLoading}
              >
                {isLoading ? 'Entrando...' : 'Entrar no Nexa →'}
              </button>
            </form>
          )}

          {/* Register Form */}
          {activeTab === 'register' && (
            <form onSubmit={handleRegister} className="space-y-4">
              <input
                className="input-modern w-full"
                type="text"
                placeholder="👤 Seu nome completo"
                value={registerName}
                onChange={(e) => setRegisterName(e.target.value)}
                autoComplete="name"
                disabled={isLoading}
              />
              <input
                className="input-modern w-full"
                type="email"
                placeholder="📧 Seu e-mail (obrigatório)"
                value={registerEmail}
                onChange={(e) => setRegisterEmail(e.target.value)}
                autoComplete="email"
                disabled={isLoading}
              />
              <input
                className="input-modern w-full"
                type="password"
                placeholder="🔑  Crie uma senha (mín. 6 chars)"
                value={registerPassword}
                onChange={(e) => setRegisterPassword(e.target.value)}
                autoComplete="new-password"
                disabled={isLoading}
              />
              <button
                type="submit"
                className="btn-primary w-full disabled:opacity-50"
                disabled={isLoading}
              >
                {isLoading ? 'Criando...' : 'Criar minha conta ✦'}
              </button>
            </form>
          )}
        </div>

        {/* Badge de Status */}
        <div className="text-center mt-6">
          <span className="text-xs text-slate-600 tracking-wider">
            🔒 Comunicação criptografada com JWT · Open Finance integrado
          </span>
        </div>
      </div>
    </div>
  );
};