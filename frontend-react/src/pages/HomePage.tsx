import React from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';

export const HomePage: React.FC = () => {
  const navigate = useNavigate();
  const hora = new Date().getHours();
  const saudacao = hora < 12 ? 'Bom dia' : hora < 18 ? 'Boa tarde' : 'Boa noite';

  const userId = localStorage.getItem('user_id') || '';
  const displayName = userId
    ? userId.split('@')[0].split('_')[0].charAt(0).toUpperCase() +
      userId.split('@')[0].split('_')[0].slice(1)
    : '';

  const handleLogout = () => {
    localStorage.removeItem('jwt_token');
    localStorage.removeItem('user_id');
    window.location.href = '/login';
  };

  const modules = [
    {
      id: 'dashboard',
      icon: '💎',
      title: 'Meu Dinheiro',
      description: 'KPIs, cashflow, regra 50/30/20, metas e operações em tempo real.',
      badge: 'Dados Reais',
      badgeColor: 'from-emerald-500 to-green-600',
      gradient: 'from-emerald-500/20 to-green-600/20',
      route: '/dashboard',
    },
    {
      id: 'strategies',
      icon: '🧠',
      title: 'Estratégias Nexa',
      description: 'Optimizer, Architect, Fiscal Intelligence, peers e alertas de ação.',
      badge: 'Premium',
      badgeColor: 'from-purple-500 to-indigo-600',
      gradient: 'from-purple-500/20 to-indigo-600/20',
      route: '/strategies',
    },
    {
      id: 'connections',
      icon: '🔗',
      title: 'Conexões Open Finance',
      description: 'Conecte bancos reais via Pluggy e sincronize transações com 1 clique.',
      badge: 'Pluggy',
      badgeColor: 'from-amber-500 to-orange-600',
      gradient: 'from-amber-500/20 to-orange-600/20',
      route: '/connections',
    },
    {
      id: 'chat',
      icon: '💬',
      title: 'Chat Inteligente',
      description: 'Assistente financeiro com ferramentas analíticas e contexto da sua conta.',
      badge: 'LangGraph IA',
      badgeColor: 'from-purple-500 to-pink-600',
      gradient: 'from-purple-500/20 to-pink-600/20',
      route: '/chat',
    },
  ];

  const quickStats = [
    {
      label: 'Modo',
      value: 'Teste Real',
      subtitle: 'sem mock',
      color: 'text-emerald-400',
    },
    {
      label: 'Fonte',
      value: 'Open Finance',
      subtitle: 'Pluggy integrado',
      color: 'text-indigo-400',
    },
    {
      label: 'Cobertura',
      value: 'Módulos ativos',
      subtitle: 'Dashboard + Estratégias',
      color: 'text-purple-400',
    },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-purple-950/30 to-slate-950 relative overflow-hidden">
      {/* Padrão de grade de fundo */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#4f4f4f12_1px,transparent_1px),linear-gradient(to_bottom,#4f4f4f12_1px,transparent_1px)] bg-[size:4rem_4rem]" />

      {/* Conteúdo principal */}
      <div className="relative z-10">
        {/* Header */}
        <motion.header
          className="border-b border-purple-900/30 bg-slate-900/40 backdrop-blur-xl"
          initial={{ y: -100 }}
          animate={{ y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 bg-gradient-to-br from-purple-500 to-indigo-600 rounded-2xl flex items-center justify-center shadow-lg shadow-purple-500/50">
                  <span className="text-2xl">💜</span>
                </div>
                <div>
                  <h1 className="text-2xl font-bold bg-gradient-to-r from-purple-200 to-purple-400 bg-clip-text text-transparent">
                    Nexa
                  </h1>
                  <p className="text-xs text-slate-500">Inteligência Financeira</p>
                </div>
              </div>

              <motion.button
                onClick={handleLogout}
                className="px-6 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl font-medium text-sm transition-all border border-slate-700"
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                Sair
              </motion.button>
            </div>
          </div>
        </motion.header>

        {/* Hero Section */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
          <motion.div
            className="text-center mb-12"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <div className="inline-block px-4 py-1 bg-purple-500/10 border border-purple-500/30 rounded-full mb-4">
              <span className="text-purple-300 text-sm font-semibold tracking-wide">
                NEXA CENTRAL
              </span>
            </div>

            <h2 className="text-5xl sm:text-6xl font-black mb-4 bg-gradient-to-r from-slate-100 via-purple-200 to-slate-100 bg-clip-text text-transparent">
              {saudacao}
              {displayName && `, ${displayName}`} 👋
            </h2>

            <p className="text-lg text-slate-400 max-w-3xl mx-auto">
              Seu cockpit financeiro completo: visão diária, conexões bancárias e
              estratégia avançada.
            </p>
          </motion.div>

          {/* Módulos Principais */}
          <motion.div
            className="mb-12"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.2 }}
          >
            <div className="flex items-center gap-3 mb-6">
              <span className="text-3xl">🧭</span>
              <h3 className="text-2xl font-bold text-slate-100">Módulos principais</h3>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {modules.map((module, index) => (
                <motion.div
                  key={module.id}
                  className="group relative bg-slate-900/50 backdrop-blur-xl rounded-2xl p-6 border border-slate-800 hover:border-purple-500/50 transition-all cursor-pointer overflow-hidden"
                  onClick={() => navigate(module.route)}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5, delay: 0.1 * index }}
                  whileHover={{ scale: 1.02, y: -5 }}
                >
                  {/* Fundo gradiente */}
                  <div className={`absolute inset-0 bg-gradient-to-br ${module.gradient} opacity-0 group-hover:opacity-100 transition-opacity duration-500`} />

                  {/* Conteúdo */}
                  <div className="relative z-10">
                    <div className="flex items-start justify-between mb-4">
                      <span className="text-5xl">{module.icon}</span>
                      <div className={`px-3 py-1 bg-gradient-to-r ${module.badgeColor} rounded-full text-xs font-bold text-white shadow-lg`}>
                        {module.badge}
                      </div>
                    </div>

                    <h4 className="text-xl font-bold text-slate-100 mb-2 group-hover:text-purple-300 transition-colors">
                      {module.title}
                    </h4>

                    <p className="text-sm text-slate-400 mb-4">
                      {module.description}
                    </p>

                    <div className="flex items-center text-purple-400 font-semibold text-sm group-hover:translate-x-2 transition-transform">
                      <span>Acessar</span>
                      <svg className="w-4 h-4 ml-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>

          {/* Acesso Rápido */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.4 }}
          >
            <div className="flex items-center gap-3 mb-6">
              <span className="text-3xl">⚡</span>
              <h3 className="text-2xl font-bold text-slate-100">Acesso rápido</h3>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
              {quickStats.map((stat, index) => (
                <motion.div
                  key={stat.label}
                  className="bg-slate-900/50 backdrop-blur-xl rounded-2xl p-6 border border-slate-800 text-center"
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 0.5, delay: 0.1 * index }}
                >
                  <div className="text-xs text-slate-500 uppercase tracking-wider mb-2 font-semibold">
                    {stat.label}
                  </div>
                  <div className={`text-2xl font-bold ${stat.color} mb-1`}>
                    {stat.value}
                  </div>
                  <div className="text-xs text-slate-500">
                    {stat.subtitle}
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>

          {/* Dica */}
          <motion.div
            className="bg-indigo-500/10 border border-indigo-500/30 rounded-2xl p-6 text-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.6 }}
          >
            <div className="flex items-center justify-center gap-2 text-indigo-300">
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
              </svg>
              <p className="text-sm">
                <strong className="font-bold">Dica:</strong> Abra{' '}
                <span className="font-semibold text-indigo-200">Meu Dinheiro</span> para validar
                consistência dos dados e depois use{' '}
                <span className="font-semibold text-indigo-200">Estratégias Nexa</span> para
                recomendações acionáveis.
              </p>
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
};
