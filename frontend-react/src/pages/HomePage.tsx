import React from 'react';
import { useNavigate } from 'react-router-dom';

interface Module {
  icon: string;
  label: string;
  desc: string;
  path: string;
  tag?: string;
}

const modules: Module[] = [
  {
    icon: '↗',
    label: 'Meu Dinheiro',
    desc: 'KPIs, cashflow, regra 50/30/20 e operações em tempo real.',
    path: '/dashboard',
    tag: 'Dados reais',
  },
  {
    icon: '◈',
    label: 'Estratégias Nexa',
    desc: 'Optimizer, Architect, Fiscal Intelligence e alertas de ação.',
    path: '/strategies',
    tag: 'Premium',
  },
  {
    icon: '⌁',
    label: 'Conexões Open Finance',
    desc: 'Conecte bancos via Pluggy e sincronize com 1 clique.',
    path: '/connections',
    tag: 'Pluggy',
  },
  {
    icon: '◍',
    label: 'Chat Inteligente',
    desc: 'Assistente financeiro com ferramentas analíticas contextuais.',
    path: '/chat',
    tag: 'LangGraph IA',
  },
  {
    icon: '◉',
    label: 'Perfil',
    desc: 'Veja os dados da conta e da sessão atualmente logada.',
    path: '/profile',
    tag: 'Conta',
  },
];

export const HomePage: React.FC = () => {
  const navigate = useNavigate();
  const [isDark, setIsDark] = React.useState(false);

  React.useEffect(() => {
    const theme = localStorage.getItem('theme') || 'light';
    setIsDark(theme === 'dark');
    document.documentElement.setAttribute('data-theme', theme);
  }, []);

  const toggleTheme = () => {
    const newTheme = isDark ? 'light' : 'dark';
    setIsDark(!isDark);
    localStorage.setItem('theme', newTheme);
    document.documentElement.setAttribute('data-theme', newTheme);
  };

  const hora = new Date().getHours();
  const saudacao = hora < 12 ? 'Bom dia' : hora < 18 ? 'Boa tarde' : 'Boa noite';

  const userName = localStorage.getItem('user_name') || '';
  const userEmail = localStorage.getItem('user_email') || '';
  
  // Pegar apenas o primeiro nome
  const firstName = userName ? userName.split(' ')[0] : '';
  const displayName = firstName || (userEmail ? userEmail.split('@')[0] : 'Usuário');
  
  const dataOrigin = localStorage.getItem('nexa_data_origin') === 'sandbox' ? 'sandbox' : 'real';

  const handleLogout = () => {
    localStorage.removeItem('jwt_token');
    localStorage.removeItem('user_id');
    localStorage.removeItem('user_name');
    localStorage.removeItem('user_email');
    localStorage.removeItem('nexa_data_origin');
    localStorage.removeItem('nexa_data_origin_updated_at');
    window.location.href = '/login';
  };

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');

        .hp-root {
          font-family: 'Inter', system-ui, sans-serif;
          min-height: 100vh;
          background: var(--bg-main);
          color: var(--text-primary);
          display: flex;
          transition: background-color 0.3s cubic-bezier(0.4, 0, 0.2, 1),
                      color 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .hp-root {
          --bg-main: #fafafa;
          --bg-surface: #fff;
          --bg-elevated: #fff;
          --text-primary: #111;
          --text-secondary: #555;
          --text-tertiary: #888;
          --text-muted: #999;
          --text-faint: #bbb;
          --border-base: #ebebeb;
          --border-hover: #d0d0d0;
          --bg-hover: #f4f4f5;
          --bg-active: #eceff1;
          --shadow-sm: 0 1px 3px rgba(0,0,0,0.06);
          --shadow-md: 0 4px 16px rgba(0,0,0,0.08);
          --shadow-lg: 0 8px 24px rgba(0,0,0,0.12);
          --accent: #111;
          --accent-hover: #333;
          --danger: #ef4444;
          --danger-hover: #dc2626;
        }

        [data-theme='dark'] .hp-root {
          --bg-main: #0a0a0a;
          --bg-surface: #141414;
          --bg-elevated: #1a1a1a;
          --text-primary: #ededed;
          --text-secondary: #b8b8b8;
          --text-tertiary: #8a8a8a;
          --text-muted: #6a6a6a;
          --text-faint: #4a4a4a;
          --border-base: #222;
          --border-hover: #333;
          --bg-hover: #1f1f1f;
          --bg-active: #252525;
          --shadow-sm: 0 1px 3px rgba(0,0,0,0.3);
          --shadow-md: 0 4px 16px rgba(0,0,0,0.4);
          --shadow-lg: 0 8px 24px rgba(0,0,0,0.5);
          --accent: #ededed;
          --accent-hover: #fff;
          --danger: #f87171;
          --danger-hover: #ef4444;
        }

        /* ── Sidebar ── */
        .hp-sidebar {
          width: 240px;
          flex-shrink: 0;
          background: var(--bg-surface);
          border-right: 1px solid var(--border-base);
          display: flex;
          flex-direction: column;
          padding: 28px 20px;
          gap: 32px;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .hp-sidebar-logo {
          font-size: 17px;
          font-weight: 600;
          letter-spacing: -0.3px;
          color: var(--text-primary);
          display: flex;
          align-items: center;
          gap: 8px;
          transition: color 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .hp-sidebar-logo-dot {
          width: 8px; height: 8px;
          border-radius: 50%;
          background: var(--accent);
          transition: background-color 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .hp-sidebar-nav {
          display: flex;
          flex-direction: column;
          gap: 2px;
          flex: 1;
        }
        .hp-nav-item {
          padding: 10px 12px;
          border-radius: 9px;
          font-size: 13.5px;
          font-weight: 450;
          color: var(--text-tertiary);
          cursor: pointer;
          transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
          display: flex;
          align-items: center;
          gap: 10px;
          border: none;
          background: none;
          width: 100%;
          text-align: left;
          font-family: inherit;
        }
        .hp-nav-item:hover {
          background: var(--bg-hover);
          color: var(--text-primary);
          transform: translateX(2px);
        }
        .hp-nav-item.active {
          background: var(--bg-active);
          color: var(--text-primary);
          font-weight: 500;
        }
        .hp-nav-icon {
          font-size: 15px;
          width: 20px;
          text-align: center;
          flex-shrink: 0;
          transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .hp-nav-item:hover .hp-nav-icon {
          transform: scale(1.1);
        }
        .hp-sidebar-footer {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .hp-theme-toggle {
          padding: 10px 12px;
          border-radius: 9px;
          font-size: 13px;
          font-weight: 500;
          color: var(--text-tertiary);
          cursor: pointer;
          border: none;
          background: none;
          text-align: left;
          font-family: inherit;
          display: flex;
          align-items: center;
          gap: 8px;
          transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .hp-theme-toggle:hover {
          background: var(--bg-hover);
          color: var(--text-primary);
        }
        .hp-user-chip {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 10px 12px;
          border-radius: 9px;
          background: var(--bg-hover);
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .hp-user-avatar {
          width: 32px; height: 32px;
          border-radius: 50%;
          background: var(--accent);
          color: var(--bg-surface);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 12px;
          font-weight: 600;
          flex-shrink: 0;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .hp-user-name {
          font-size: 13px;
          font-weight: 500;
          color: var(--text-primary);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          transition: color 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .hp-logout-btn {
          padding: 10px 12px;
          border-radius: 9px;
          font-size: 13px;
          font-weight: 450;
          color: var(--text-muted);
          cursor: pointer;
          border: none;
          background: none;
          text-align: left;
          font-family: inherit;
          display: flex;
          align-items: center;
          gap: 8px;
          transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .hp-logout-btn:hover {
          color: var(--danger);
          background: var(--bg-hover);
        }

        /* ── Main ── */
        .hp-main {
          flex: 1;
          padding: 48px 56px;
          max-width: 880px;
        }
        .hp-greeting-wrap {
          margin-bottom: 40px;
        }
        .hp-greeting-label {
          font-size: 12px;
          font-weight: 500;
          color: var(--text-faint);
          letter-spacing: 0.8px;
          text-transform: uppercase;
          margin-bottom: 8px;
          transition: color 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .hp-greeting-title {
          font-size: 32px;
          font-weight: 600;
          letter-spacing: -0.8px;
          color: var(--text-primary);
          margin: 0;
          transition: color 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .hp-greeting-sub {
          font-size: 14.5px;
          color: var(--text-muted);
          margin-top: 8px;
          transition: color 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        /* Section label */
        .hp-section-label {
          font-size: 11px;
          font-weight: 600;
          letter-spacing: 0.9px;
          text-transform: uppercase;
          color: var(--text-faint);
          margin: 0 0 16px;
          transition: color 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        /* Module grid */
        .hp-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 14px;
          margin-bottom: 40px;
        }
        @media (max-width: 900px) { .hp-grid { grid-template-columns: 1fr; } }

        .hp-card {
          background: var(--bg-surface);
          border: 1px solid var(--border-base);
          border-radius: 14px;
          padding: 24px;
          cursor: pointer;
          transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        .hp-card:hover {
          border-color: var(--border-hover);
          box-shadow: var(--shadow-md);
          transform: translateY(-2px);
        }
        .hp-card:active {
          transform: translateY(0);
        }
        .hp-card-top {
          display: flex;
          align-items: center;
          justify-content: space-between;
        }
        .hp-card-icon {
          font-size: 19px;
          color: var(--text-secondary);
          font-weight: 300;
          width: 36px;
          height: 36px;
          border-radius: 9px;
          background: var(--bg-hover);
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .hp-card:hover .hp-card-icon {
          transform: scale(1.1) rotate(5deg);
        }
        .hp-card-tag {
          font-size: 10.5px;
          font-weight: 500;
          color: var(--text-tertiary);
          background: var(--bg-hover);
          border-radius: 100px;
          padding: 4px 11px;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .hp-card-label {
          font-size: 15px;
          font-weight: 600;
          color: var(--text-primary);
          letter-spacing: -0.3px;
          transition: color 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .hp-card-desc {
          font-size: 13px;
          color: var(--text-muted);
          line-height: 1.6;
          transition: color 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .hp-card-cta {
          font-size: 12.5px;
          font-weight: 500;
          color: var(--text-secondary);
          display: flex;
          align-items: center;
          gap: 4px;
          margin-top: 4px;
          transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .hp-card:hover .hp-card-cta {
          color: var(--text-primary);
          gap: 6px;
        }

        /* Stats strip */
        .hp-stats {
          display: flex;
          gap: 14px;
          margin-bottom: 40px;
        }
        .hp-stat {
          flex: 1;
          background: var(--bg-surface);
          border: 1px solid var(--border-base);
          border-radius: 12px;
          padding: 18px 20px;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .hp-stat:hover {
          border-color: var(--border-hover);
          box-shadow: var(--shadow-sm);
        }
        .hp-stat-label {
          font-size: 11px;
          font-weight: 500;
          color: var(--text-faint);
          letter-spacing: 0.6px;
          text-transform: uppercase;
          margin-bottom: 8px;
          transition: color 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .hp-stat-value {
          font-size: 17px;
          font-weight: 600;
          color: var(--text-primary);
          transition: color 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .hp-stat-sub {
          font-size: 11.5px;
          color: var(--text-faint);
          margin-top: 4px;
          transition: color 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        /* Tip */
        .hp-tip {
          background: var(--bg-surface);
          border: 1px solid var(--border-base);
          border-radius: 12px;
          padding: 16px 20px;
          font-size: 13px;
          color: var(--text-tertiary);
          line-height: 1.6;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .hp-tip strong {
          color: var(--text-secondary);
          font-weight: 500;
          transition: color 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        @media (max-width: 768px) {
          .hp-sidebar { width: 200px; }
          .hp-main { padding: 32px 24px; }
          .hp-greeting-title { font-size: 26px; }
        }
      `}</style>

      <div className="hp-root">
        {/* ── Sidebar ── */}
        <aside className="hp-sidebar">
          <div className="hp-sidebar-logo">
            <div className="hp-sidebar-logo-dot" />
            Nexa
          </div>

          <nav className="hp-sidebar-nav">
            {[
              { icon: '⌂', label: 'Início', path: '/home', active: true },
              { icon: '↗', label: 'Meu Dinheiro', path: '/dashboard', active: false },
              { icon: '◈', label: 'Estratégias', path: '/strategies', active: false },
              { icon: '⌁', label: 'Conexões', path: '/connections', active: false },
              { icon: '◍', label: 'Chat IA', path: '/chat', active: false },
              { icon: '◉', label: 'Perfil', path: '/profile', active: false },
            ].map((item) => (
              <button
                key={item.path}
                onClick={() => navigate(item.path)}
                className={`hp-nav-item ${item.active ? 'active' : ''}`}
              >
                <span className="hp-nav-icon">{item.icon}</span>
                {item.label}
              </button>
            ))}
          </nav>

          <div className="hp-sidebar-footer">
            <button className="hp-theme-toggle" onClick={toggleTheme}>
              {isDark ? '☀' : '☾'} {isDark ? 'Modo claro' : 'Modo escuro'}
            </button>
            <div className="hp-user-chip">
              <div className="hp-user-avatar">
                {displayName ? displayName[0].toUpperCase() : 'U'}
              </div>
              <div className="hp-user-name">{displayName}</div>
            </div>
            <button className="hp-logout-btn" onClick={handleLogout}>
              ← Sair
            </button>
          </div>
        </aside>

        {/* ── Main ── */}
        <main className="hp-main">
          {/* Greeting */}
          <div className="hp-greeting-wrap">
            <div className="hp-greeting-label">Nexa Central</div>
            <h1 className="hp-greeting-title">
              {saudacao}{displayName ? `, ${displayName}` : ''}.
            </h1>
            <p className="hp-greeting-sub">
              Aqui está seu cockpit financeiro. Escolha um módulo para começar.
            </p>
          </div>

          {/* Stats */}
          <p className="hp-section-label">Visão Rápida</p>
          <div className="hp-stats">
            <div className="hp-stat">
              <div className="hp-stat-label">Modo</div>
              <div className="hp-stat-value">{dataOrigin === 'sandbox' ? 'Sandbox' : 'Produção'}</div>
              <div className="hp-stat-sub">{dataOrigin === 'sandbox' ? 'Com dados de teste' : 'Dados reais'}</div>
            </div>
            <div className="hp-stat">
              <div className="hp-stat-label">Fonte</div>
              <div className="hp-stat-value">Open Finance</div>
              <div className="hp-stat-sub">Pluggy integrado</div>
            </div>
            <div className="hp-stat">
              <div className="hp-stat-label">Módulos</div>
              <div className="hp-stat-value">4 ativos</div>
              <div className="hp-stat-sub">Dashboard + IA</div>
            </div>
          </div>

          {/* Modules */}
          <p className="hp-section-label">Módulos</p>
          <div className="hp-grid">
            {modules.map((m) => (
              <div className="hp-card" key={m.path} onClick={() => navigate(m.path)}>
                <div className="hp-card-top">
                  <div className="hp-card-icon">{m.icon}</div>
                  {m.tag && <span className="hp-card-tag">{m.tag}</span>}
                </div>
                <div className="hp-card-label">{m.label}</div>
                <div className="hp-card-desc">{m.desc}</div>
                <div className="hp-card-cta">Acessar →</div>
              </div>
            ))}
          </div>

          {/* Tip */}
          <div className="hp-tip">
            💡 Dica: Abra <strong>Meu Dinheiro</strong> para validar os dados das suas
            contas conectadas e use <strong>Estratégias</strong> para recomendações
            acionáveis personalizadas.
          </div>
        </main>
      </div>
    </>
  );
};
