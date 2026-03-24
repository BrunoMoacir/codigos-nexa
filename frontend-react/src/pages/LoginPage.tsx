import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
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
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: formData,
      });

      if (response.ok) {
        const data = await response.json();
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
    <div className="min-h-screen relative overflow-hidden bg-gradient-to-br from-slate-950 via-purple-950 to-slate-950">
      {/* Padrão de grade animado */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#4f4f4f12_1px,transparent_1px),linear-gradient(to_bottom,#4f4f4f12_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_110%)]" />

      {/* Orbes de luz animados */}
      <div className="absolute inset-0 overflow-hidden">
        <motion.div
          className="absolute w-[500px] h-[500px] rounded-full"
          style={{
            background: 'radial-gradient(circle, rgba(124,58,237,0.3) 0%, transparent 70%)',
            top: '-10%',
            left: '-10%',
          }}
          animate={{
            scale: [1, 1.2, 1],
            opacity: [0.3, 0.5, 0.3],
          }}
          transition={{
            duration: 8,
            repeat: Infinity,
            ease: 'easeInOut',
          }}
        />
        <motion.div
          className="absolute w-[400px] h-[400px] rounded-full"
          style={{
            background: 'radial-gradient(circle, rgba(99,102,241,0.3) 0%, transparent 70%)',
            bottom: '-10%',
            right: '-5%',
          }}
          animate={{
            scale: [1.2, 1, 1.2],
            opacity: [0.4, 0.6, 0.4],
          }}
          transition={{
            duration: 10,
            repeat: Infinity,
            ease: 'easeInOut',
          }}
        />
      </div>

      {/* Conteúdo principal */}
      <div className="relative z-10 min-h-screen flex items-center justify-center p-4">
        <div className="flex flex-col lg:flex-row items-center justify-center gap-12 lg:gap-20 max-w-7xl w-full">

          {/* Seção esquerda - Branding */}
          <motion.div
            className="text-center lg:text-left"
            initial={{ opacity: 0, x: -50 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8 }}
          >
            <motion.div
              className="inline-block mb-6"
              animate={{
                rotateY: [0, 360],
              }}
              transition={{
                duration: 20,
                repeat: Infinity,
                ease: 'linear',
              }}
            >
              <div className="w-24 h-24 bg-gradient-to-br from-purple-500 via-indigo-500 to-purple-600 rounded-3xl flex items-center justify-center shadow-2xl shadow-purple-500/50">
                <span className="text-5xl">💜</span>
              </div>
            </motion.div>

            <h1 className="text-7xl lg:text-8xl font-black mb-4 bg-gradient-to-r from-purple-200 via-purple-400 to-purple-200 bg-clip-text text-transparent">
              Nexa
            </h1>

            <p className="text-2xl text-slate-300 mb-6 font-light">
              Inteligência Financeira com IA
            </p>

            <div className="space-y-3 text-left max-w-md">
              <div className="flex items-start gap-3">
                <div className="mt-1 w-6 h-6 rounded-full bg-purple-500/20 flex items-center justify-center flex-shrink-0">
                  <div className="w-2 h-2 rounded-full bg-purple-400" />
                </div>
                <div>
                  <p className="text-slate-300 font-medium">Dashboard Inteligente</p>
                  <p className="text-slate-500 text-sm">Visualize suas finanças em tempo real</p>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <div className="mt-1 w-6 h-6 rounded-full bg-indigo-500/20 flex items-center justify-center flex-shrink-0">
                  <div className="w-2 h-2 rounded-full bg-indigo-400" />
                </div>
                <div>
                  <p className="text-slate-300 font-medium">Open Finance</p>
                  <p className="text-slate-500 text-sm">Conecte seus bancos com segurança</p>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <div className="mt-1 w-6 h-6 rounded-full bg-purple-500/20 flex items-center justify-center flex-shrink-0">
                  <div className="w-2 h-2 rounded-full bg-purple-400" />
                </div>
                <div>
                  <p className="text-slate-300 font-medium">IA Estratégica</p>
                  <p className="text-slate-500 text-sm">Recomendações personalizadas</p>
                </div>
              </div>
            </div>
          </motion.div>

          {/* Seção direita - Formulário */}
          <motion.div
            className="w-full max-w-md"
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2 }}
          >
            <div className="bg-slate-900/60 backdrop-blur-2xl rounded-3xl p-8 shadow-2xl border border-purple-500/20">

              {/* Tabs */}
              <div className="relative mb-8 p-1 bg-slate-800/50 rounded-2xl">
                <motion.div
                  className="absolute inset-y-1 bg-gradient-to-r from-purple-600 to-indigo-600 rounded-xl shadow-lg"
                  initial={false}
                  animate={{
                    left: activeTab === 'login' ? '0.25rem' : '50%',
                    right: activeTab === 'login' ? '50%' : '0.25rem',
                  }}
                  transition={{ type: 'spring', stiffness: 300, damping: 30 }}
                />

                <div className="relative flex gap-1">
                  <button
                    onClick={() => setActiveTab('login')}
                    disabled={isLoading}
                    className={`flex-1 py-3.5 px-6 rounded-xl font-semibold text-sm transition-colors relative z-10 ${
                      activeTab === 'login' ? 'text-white' : 'text-slate-400 hover:text-slate-300'
                    }`}
                  >
                    Entrar
                  </button>
                  <button
                    onClick={() => setActiveTab('register')}
                    disabled={isLoading}
                    className={`flex-1 py-3.5 px-6 rounded-xl font-semibold text-sm transition-colors relative z-10 ${
                      activeTab === 'register' ? 'text-white' : 'text-slate-400 hover:text-slate-300'
                    }`}
                  >
                    Criar Conta
                  </button>
                </div>
              </div>

              {/* Forms */}
              <AnimatePresence mode="wait">
                {activeTab === 'login' ? (
                  <motion.form
                    key="login"
                    onSubmit={handleLogin}
                    className="space-y-5"
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 20 }}
                    transition={{ duration: 0.3 }}
                  >
                    <div className="space-y-2">
                      <label className="block text-sm font-semibold text-slate-300 mb-2">
                        E-mail
                      </label>
                      <input
                        className="w-full px-4 py-3.5 bg-slate-800/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20 transition-all"
                        type="email"
                        placeholder="seu@email.com"
                        value={loginEmail}
                        onChange={(e) => setLoginEmail(e.target.value)}
                        autoComplete="email"
                        disabled={isLoading}
                      />
                    </div>

                    <div className="space-y-2">
                      <label className="block text-sm font-semibold text-slate-300 mb-2">
                        Senha
                      </label>
                      <input
                        className="w-full px-4 py-3.5 bg-slate-800/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20 transition-all"
                        type="password"
                        placeholder="••••••••"
                        value={loginPassword}
                        onChange={(e) => setLoginPassword(e.target.value)}
                        autoComplete="current-password"
                        disabled={isLoading}
                      />
                    </div>

                    <motion.button
                      type="submit"
                      className="w-full mt-6 py-4 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-bold rounded-xl shadow-lg shadow-purple-500/50 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                      disabled={isLoading}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                    >
                      {isLoading ? (
                        <span className="flex items-center justify-center gap-2">
                          <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                          </svg>
                          Entrando...
                        </span>
                      ) : (
                        'Entrar no Nexa'
                      )}
                    </motion.button>
                  </motion.form>
                ) : (
                  <motion.form
                    key="register"
                    onSubmit={handleRegister}
                    className="space-y-5"
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -20 }}
                    transition={{ duration: 0.3 }}
                  >
                    <div className="space-y-2">
                      <label className="block text-sm font-semibold text-slate-300 mb-2">
                        Nome Completo
                      </label>
                      <input
                        className="w-full px-4 py-3.5 bg-slate-800/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20 transition-all"
                        type="text"
                        placeholder="Seu nome completo"
                        value={registerName}
                        onChange={(e) => setRegisterName(e.target.value)}
                        autoComplete="name"
                        disabled={isLoading}
                      />
                    </div>

                    <div className="space-y-2">
                      <label className="block text-sm font-semibold text-slate-300 mb-2">
                        E-mail
                      </label>
                      <input
                        className="w-full px-4 py-3.5 bg-slate-800/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20 transition-all"
                        type="email"
                        placeholder="seu@email.com"
                        value={registerEmail}
                        onChange={(e) => setRegisterEmail(e.target.value)}
                        autoComplete="email"
                        disabled={isLoading}
                      />
                    </div>

                    <div className="space-y-2">
                      <label className="block text-sm font-semibold text-slate-300 mb-2">
                        Senha
                      </label>
                      <input
                        className="w-full px-4 py-3.5 bg-slate-800/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20 transition-all"
                        type="password"
                        placeholder="Mínimo 6 caracteres"
                        value={registerPassword}
                        onChange={(e) => setRegisterPassword(e.target.value)}
                        autoComplete="new-password"
                        disabled={isLoading}
                      />
                    </div>

                    <motion.button
                      type="submit"
                      className="w-full mt-6 py-4 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-bold rounded-xl shadow-lg shadow-purple-500/50 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                      disabled={isLoading}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                    >
                      {isLoading ? (
                        <span className="flex items-center justify-center gap-2">
                          <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                          </svg>
                          Criando...
                        </span>
                      ) : (
                        'Criar Conta'
                      )}
                    </motion.button>
                  </motion.form>
                )}
              </AnimatePresence>

              {/* Badge de segurança */}
              <div className="mt-6 pt-6 border-t border-slate-800">
                <div className="flex items-center justify-center gap-2 text-xs text-slate-500">
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" clipRule="evenodd" />
                  </svg>
                  <span>Criptografia JWT • Open Finance integrado</span>
                </div>
              </div>
            </div>

            {/* Texto adicional */}
            <p className="mt-6 text-center text-sm text-slate-500">
              Ao continuar, você concorda com nossos Termos de Uso
            </p>
          </motion.div>
        </div>
      </div>
    </div>
  );
};
