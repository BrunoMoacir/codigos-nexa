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
];

export const HomePage: React.FC = () => {
  const navigate = useNavigate();

  const hora = new Date().getHours();
  const saudacao = hora < 12 ? 'Bom dia' : hora < 18 ? 'Boa tarde' : 'Boa noite';

  const storedName = localStorage.getItem('user_name') || '';
  const storedEmail = localStorage.getItem('user_email') || '';
  
  const [displayName] = React.useState(() => {
    if (storedName) {
      return storedName.split(' ')[0].replace(/^./, (c) => c.toUpperCase());
    }
    if (storedEmail) return storedEmail.split('@')[0].replace(/^./, (c) => c.toUpperCase());
    
    return '';
  });

  const handleLogout = () => {
    localStorage.removeItem('jwt_token');
    localStorage.removeItem('user_id');
    localStorage.removeItem('user_email');
    window.location.href = '/login';
  };

  const [theme, setTheme] = React.useState<'light'|'dark'>(() => {
    return (localStorage.getItem('nexa-theme') as 'light'|'dark') || 'light';
  });

  const toggleTheme = () => {
    const newTheme = theme === 'light' ? 'dark' : 'light';
    setTheme(newTheme);
    localStorage.setItem('nexa-theme', newTheme);
    if (newTheme === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
    } else {
      document.documentElement.removeAttribute('data-theme');
    }
  };

  React.useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
    } else {
      document.documentElement.removeAttribute('data-theme');
    }
  }, [theme]);

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
        }

        /* ── Sidebar ── */
        .hp-sidebar {
          width: 220px;
          flex-shrink: 0;
          background: var(--bg-surface);
          border-right: 1px solid var(--border-color);
          display: flex;
          flex-direction: column;
          padding: 28px 20px;
          gap: 32px;
        }
        .hp-sidebar-logo {
          font-size: 17px;
          font-weight: 600;
          letter-spacing: -0.3px;
          color: var(--text-primary);
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .hp-sidebar-logo-dot {
          width: 8px; height: 8px;
          border-radius: 50%;
          background: var(--text-primary);
        }
        .hp-sidebar-nav {
          display: flex;
          flex-direction: column;
          gap: 2px;
          flex: 1;
        }
        .hp-nav-item {
          padding: 8px 10px;
          border-radius: 8px;
          font-size: 13.5px;
          font-weight: 450;
          color: var(--text-muted);
          cursor: pointer;
          transition: all 0.12s ease;
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
        }
        .hp-nav-item.active {
          background: var(--bg-hover);
          color: var(--text-primary);
          font-weight: 500;
        }
        .hp-nav-icon {
          font-size: 14px;
          width: 18px;
          text-align: center;
          flex-shrink: 0;
        }
        .hp-sidebar-footer {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .hp-user-chip {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 8px 10px;
          border-radius: 8px;
          background: var(--bg-hover);
        }
        .hp-user-avatar {
          width: 28px; height: 28px;
          border-radius: 50%;
          background: var(--text-primary);
          color: var(--bg-surface);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 11px;
          font-weight: 600;
          flex-shrink: 0;
        }
        .hp-user-name {
          font-size: 12.5px;
          font-weight: 500;
          color: var(--text-primary);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .hp-logout-btn {
          padding: 8px 10px;
          border-radius: 8px;
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
          transition: color 0.12s;
        }
        .hp-logout-btn:hover { color: #ef4444; }

        /* ── Main ── */
        .hp-main {
          flex: 1;
          padding: 48px 56px;
          max-width: 860px;
        }
        .hp-greeting-wrap {
          margin-bottom: 40px;
        }
        .hp-greeting-label {
          font-size: 12px;
          font-weight: 500;
          color: var(--text-muted);
          letter-spacing: 0.8px;
          text-transform: uppercase;
          margin-bottom: 6px;
        }
        .hp-greeting-title {
          font-size: 28px;
          font-weight: 600;
          letter-spacing: -0.6px;
          color: var(--text-primary);
          margin: 0;
        }
        .hp-greeting-sub {
          font-size: 14px;
          color: var(--text-muted);
          margin-top: 6px;
        }

        /* Section label */
        .hp-section-label {
          font-size: 11px;
          font-weight: 600;
          letter-spacing: 0.9px;
          text-transform: uppercase;
          color: var(--text-muted);
          margin: 0 0 16px;
        }

        /* Module grid */
        .hp-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 12px;
          margin-bottom: 40px;
        }
        @media (max-width: 900px) { .hp-grid { grid-template-columns: 1fr; } }

        .hp-card {
          background: var(--bg-surface);
          border: 1px solid var(--border-color);
          border-radius: 12px;
          padding: 22px 24px;
          cursor: pointer;
          transition: all 0.15s ease;
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .hp-card:hover {
          border-color: var(--text-muted);
          box-shadow: 0 4px 16px rgba(0,0,0,0.05);
          transform: translateY(-1px);
        }
        .hp-card-top {
          display: flex;
          align-items: center;
          justify-content: space-between;
        }
        .hp-card-icon {
          font-size: 18px;
          color: var(--text-secondary);
          font-weight: 300;
          width: 32px;
          height: 32px;
          border-radius: 8px;
          background: var(--bg-hover);
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .hp-card-tag {
          font-size: 10.5px;
          font-weight: 500;
          color: var(--text-muted);
          background: var(--bg-hover);
          border-radius: 100px;
          padding: 3px 10px;
        }
        .hp-card-label {
          font-size: 14.5px;
          font-weight: 600;
          color: var(--text-primary);
          letter-spacing: -0.2px;
        }
        .hp-card-desc {
          font-size: 13px;
          color: var(--text-muted);
          line-height: 1.5;
        }
        .hp-card-cta {
          font-size: 12px;
          font-weight: 500;
          color: var(--text-secondary);
          display: flex;
          align-items: center;
          gap: 4px;
          margin-top: 2px;
          transition: color 0.12s;
        }
        .hp-card:hover .hp-card-cta { color: var(--text-primary); }

        /* Stats strip */
        .hp-stats {
          display: flex;
          gap: 12px;
          margin-bottom: 40px;
        }
        .hp-stat {
          flex: 1;
          background: var(--bg-surface);
          border: 1px solid var(--border-color);
          border-radius: 10px;
          padding: 16px 20px;
        }
        .hp-stat-label {
          font-size: 11px;
          font-weight: 500;
          color: var(--text-muted);
          letter-spacing: 0.6px;
          text-transform: uppercase;
          margin-bottom: 6px;
        }
        .hp-stat-value {
          font-size: 16px;
          font-weight: 600;
          color: var(--text-primary);
        }
        .hp-stat-sub {
          font-size: 11.5px;
          color: var(--text-muted);
          margin-top: 2px;
        }

        /* Tip */
        .hp-tip {
          background: var(--bg-surface);
          border: 1px solid var(--border-color);
          border-radius: 10px;
          padding: 14px 20px;
          font-size: 13px;
          color: var(--text-muted);
          line-height: 1.5;
        }
        .hp-tip strong { color: var(--text-secondary); font-weight: 500; }
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
            <div className="hp-user-chip">
              <div className="hp-user-avatar">
                {displayName ? displayName[0].toUpperCase() : 'U'}
              </div>
              <div className="hp-user-name">{displayName || 'Usuário'}</div>
            </div>
            <button className="hp-logout-btn" onClick={toggleTheme}>
              <span>{theme === 'light' ? '🌙' : '☀️'}</span>
              <span>Modo {theme === 'light' ? 'Escuro' : 'Claro'}</span>
            </button>
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
              <div className="hp-stat-value">Produção</div>
              <div className="hp-stat-sub">Sem dados mock</div>
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
