import React from 'react';
import { useNavigate } from 'react-router-dom';

export const HomePage: React.FC = () => {
  const navigate = useNavigate();
  // Saudação dinâmica
  const hora = new Date().getHours();
  const saudacao = hora < 12 ? 'Bom dia' : hora < 18 ? 'Boa tarde' : 'Boa noite';

  // Nome do usuário (extrai do localStorage)
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

  return (
    <div className="min-h-screen p-8">
      {/* Header com Logout */}
      <div className="flex justify-between items-center mb-8">
        <div></div>
        <button
          onClick={handleLogout}
          className="btn-primary"
        >
          Sair →
        </button>
      </div>

      {/* Hero Banner */}
      <div className="mb-8 text-center">
        <div className="text-xs text-purple-400 font-bold tracking-widest uppercase mb-2">
          NEXA CENTRAL
        </div>
        <h1 className="text-4xl font-extrabold mb-3">
          {saudacao}
          {displayName && `, ${displayName}`} 👋
        </h1>
        <p className="text-slate-400 text-base max-w-2xl mx-auto">
          Seu cockpit financeiro completo: visão diária, conexões bancárias e
          estratégia avançada.
        </p>
      </div>

      {/* Section Header */}
      <div className="section-header">
        <span className="icon">🧭</span>
        <span className="title">Módulos principais</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        {/* Card: Meu Dinheiro */}
        <div 
          onClick={() => navigate('/dashboard')}
          className="glass-card hover:border-emerald-500/40 transition-all group cursor-pointer"
        >
          <div className="text-5xl mb-4">📊</div>
          <h3 className="text-xl font-bold mb-2 group-hover:text-emerald-400 transition-colors">
            Meu Dinheiro
          </h3>
          <p className="text-slate-400 text-sm mb-4">
            KPIs, cashflow, regra 50/30/20, metas e operações em tempo real.
          </p>
          <div className="badge-green">Dados Reais</div>
          <div className="mt-4 text-sm text-purple-400 font-semibold group-hover:translate-x-1 transition-transform inline-block">
            → Acessar Meu Dinheiro
          </div>
        </div>

        {/* Card: Estratégias Nexa */}
        <div 
          onClick={() => navigate('/strategies')}
          className="glass-card hover:border-purple-500/40 transition-all group cursor-pointer"
        >
          <div className="text-5xl mb-4">🧠</div>
          <h3 className="text-xl font-bold mb-2 group-hover:text-purple-400 transition-colors">
            Estratégias Nexa
          </h3>
          <p className="text-slate-400 text-sm mb-4">
            Optimizer, Architect, Fiscal Intelligence, peers e alertas de ação.
          </p>
          <div className="badge-purple">Premium</div>
          <div className="mt-4 text-sm text-purple-400 font-semibold group-hover:translate-x-1 transition-transform inline-block">
            → Acessar Estratégias
          </div>
        </div>

        {/* Card: Conexões Open Finance */}
        <div 
          onClick={() => navigate('/connections')}
          className="glass-card hover:border-yellow-500/40 transition-all group cursor-pointer"
        >
          <div className="text-5xl mb-4">🔗</div>
          <h3 className="text-xl font-bold mb-2 group-hover:text-yellow-400 transition-colors">
            Conexões Open Finance
          </h3>
          <p className="text-slate-400 text-sm mb-4">
            Conecte bancos reais via Pluggy e sincronize transações com 1 clique.
          </p>
          <div className="badge-yellow">Pluggy</div>
          <div className="mt-4 text-sm text-purple-400 font-semibold group-hover:translate-x-1 transition-transform inline-block">
            → Acessar Conexões
          </div>
        </div>

        {/* Card: Chat Inteligente */}
        <div 
          onClick={() => navigate('/chat')}
          className="glass-card hover:border-purple-500/40 transition-all group cursor-pointer"
        >
          <div className="text-5xl mb-4">💬</div>
          <h3 className="text-xl font-bold mb-2 group-hover:text-purple-400 transition-colors">
            Chat Inteligente
          </h3>
          <p className="text-slate-400 text-sm mb-4">
            Assistente financeiro com ferramentas analíticas e contexto da sua conta.
          </p>
          <div className="badge-purple">LangGraph IA</div>
          <div className="mt-4 text-sm text-purple-400 font-semibold group-hover:translate-x-1 transition-transform inline-block">
            → Acessar Chat
          </div>
        </div>
      </div>

      {/* Acesso Rápido */}
      <div className="section-header">
        <span className="icon">⚡</span>
        <span className="title">Acesso rápido</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="glass-card text-center">
          <div className="text-xs text-slate-500 uppercase tracking-wider mb-1">
            Modo
          </div>
          <div className="text-2xl font-bold text-emerald-400 mb-1">
            Teste Real
          </div>
          <div className="text-xs text-emerald-300">sem mock</div>
        </div>

        <div className="glass-card text-center">
          <div className="text-xs text-slate-500 uppercase tracking-wider mb-1">
            Fonte
          </div>
          <div className="text-2xl font-bold text-indigo-400 mb-1">
            Open Finance
          </div>
          <div className="text-xs text-indigo-300">Pluggy integrado</div>
        </div>

        <div className="glass-card text-center">
          <div className="text-xs text-slate-500 uppercase tracking-wider mb-1">
            Cobertura
          </div>
          <div className="text-2xl font-bold text-purple-400 mb-1">
            Módulos ativos
          </div>
          <div className="text-xs text-purple-300">Dashboard + Estratégias</div>
        </div>
      </div>

      {/* Dica */}
      <div
        className="glass-card text-center py-4"
        style={{
          background: 'rgba(99, 102, 241, 0.05)',
          borderStyle: 'dashed',
        }}
      >
        <p className="text-sm text-slate-400 m-0">
          💡 Dica: abra{' '}
          <strong className="text-indigo-300">Meu Dinheiro</strong> para validar
          consistência dos dados e depois use{' '}
          <strong className="text-indigo-300">Estratégias Nexa</strong> para
          recomendações acionáveis.
        </p>
      </div>
    </div>
  );
};