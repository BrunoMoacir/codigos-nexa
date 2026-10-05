import { useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { logout } from '../../api/auth';
import { useSession } from '../../hooks/useAuth';

/**
 * Todas as telas que usam o AppShell. Eram só as 4 da navegação, e as 6
 * páginas legadas passavam valores fora do tipo — eram 6 dos 10 erros que
 * impediam o `npm run build`.
 */
export type HiveTab =
  | 'dashboard' | 'chat' | 'feed' | 'organizar'
  | 'strategies' | 'goals' | 'defesa' | 'direitos' | 'impostos' | 'wrapped'
  | 'connections' | 'planos' | 'profile' | 'home' | 'widget';

interface AppShellProps {
  current: HiveTab;
  children: ReactNode;
  /** Cabeçalho opcional da tela (as páginas legadas já passavam e era ignorado). */
  title?: string;
  subtitle?: string;
}

const css = `
  @import url('https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700,800,900&display=swap');

  .hs {
    font-family: 'Satoshi', system-ui, sans-serif;
    min-height: 100vh;
    background: #0E0C0A;
    color: #F3EFEA;
    display: flex;
  }

  /* ── SIDEBAR ── */
  .hs-sidebar {
    width: 220px;
    flex-shrink: 0;
    background: #0A0806;
    border-right: 1px solid rgba(243,239,234,0.06);
    display: flex;
    flex-direction: column;
    padding: 24px 14px;
    position: fixed;
    top: 0;
    left: 0;
    height: 100vh;
    z-index: 50;
  }

  .hs-logo {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0 10px;
    margin-bottom: 36px;
  }
  .hs-logo-word {
    font-size: 1rem;
    font-weight: 900;
    letter-spacing: 0.14em;
    color: #D4A820;
  }
  .hs-logo-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #D4A820;
    flex-shrink: 0;
  }

  .hs-nav { display: flex; flex-direction: column; gap: 2px; flex: 1; overflow-y: auto; }
  .hs-nav-section {
    font-size: 0.6rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase;
    color: rgba(243,239,234,0.28); padding: 14px 12px 4px;
  }
  .hs-more { display: none; }
  .hs-page-head { padding: 28px 32px 0; }
  .hs-page-title { font-size: 1.35rem; font-weight: 800; letter-spacing: -0.03em; margin: 0; color: #F3EFEA; }
  .hs-page-sub { font-size: 0.8rem; color: rgba(243,239,234,0.45); margin: 4px 0 0; }
  .hs-sheet { display: none; }

  .hs-nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 11px 12px;
    border-radius: 10px;
    border: none;
    background: transparent;
    color: rgba(243,239,234,0.35);
    font-family: inherit;
    font-size: 0.84rem;
    font-weight: 500;
    cursor: pointer;
    text-align: left;
    transition: color 0.15s, background 0.15s;
    position: relative;
    letter-spacing: 0.01em;
  }
  .hs-nav-item:hover {
    color: rgba(243,239,234,0.75);
    background: rgba(243,239,234,0.04);
  }
  .hs-nav-item.on {
    color: #F3EFEA;
    background: rgba(212,168,32,0.08);
  }
  .hs-nav-item.on::before {
    content: '';
    position: absolute;
    left: 0;
    top: 20%;
    bottom: 20%;
    width: 2.5px;
    background: #D4A820;
    border-radius: 0 2px 2px 0;
  }
  .hs-nav-icon {
    width: 18px;
    height: 18px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    opacity: 0.6;
  }
  .hs-nav-item.on .hs-nav-icon { opacity: 1; }

  .hs-divider {
    height: 1px;
    background: rgba(243,239,234,0.06);
    margin: 12px 0;
  }

  .hs-bottom { display: flex; flex-direction: column; gap: 4px; }

  .hs-user {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-radius: 10px;
    cursor: default;
    margin-bottom: 4px;
  }
  .hs-avatar {
    width: 30px;
    height: 30px;
    border-radius: 50%;
    background: rgba(212,168,32,0.2);
    border: 1px solid rgba(212,168,32,0.3);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.72rem;
    font-weight: 700;
    color: #D4A820;
    flex-shrink: 0;
  }
  .hs-user-name {
    font-size: 0.8rem;
    font-weight: 600;
    color: rgba(243,239,234,0.7);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .hs-action {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 12px;
    border-radius: 10px;
    border: none;
    background: transparent;
    color: rgba(243,239,234,0.25);
    font-family: inherit;
    font-size: 0.78rem;
    font-weight: 500;
    cursor: pointer;
    text-align: left;
    transition: color 0.15s, background 0.15s;
  }
  .hs-action:hover {
    color: rgba(243,239,234,0.6);
    background: rgba(243,239,234,0.04);
  }

  /* ── MAIN ── */
  .hs-main {
    margin-left: 220px;
    flex: 1;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    /* O shell é sempre escuro, mas as variáveis de tema ficavam no modo
       claro: as telas de ferramentas (Estratégias, Metas, Defesa…) saíam com
       card branco e o texto sem cor própria herdava o claro do shell —
       nome de cartão, select e histórico ficavam invisíveis. */
    color: #F3EFEA;
    --bg-main: #0A0806;
    --bg-surface: #100E0B;
    --bg-hover: #181512;
    --bg-active: #201C17;
    --text-primary: #F3EFEA;
    --text-secondary: rgba(243,239,234,0.72);
    --text-muted: rgba(243,239,234,0.45);
    --border-color: rgba(243,239,234,0.10);
    --accent-color: #D4A820;
  }
  .hs-main input, .hs-main select, .hs-main textarea { color: inherit; background-color: transparent; }
  .hs-main select option { color: #111; }
  .hs-main a { color: #D4A820; }
  .hs-page-body { padding: 16px 32px 40px; }

  /* ── MOBILE ── */
  @media (max-width: 860px) {
    .hs { flex-direction: column; }
    .hs-sidebar {
      position: fixed;
      bottom: 0;
      top: auto;
      left: 0;
      right: 0;
      width: 100%;
      height: auto;
      flex-direction: row;
      padding: 10px 12px env(safe-area-inset-bottom);
      border-right: none;
      border-top: 1px solid rgba(243,239,234,0.08);
      align-items: center;
      gap: 0;
    }
    .hs-logo { display: none; }
    .hs-nav {
      flex-direction: row;
      flex: 1;
      justify-content: space-around;
      gap: 0;
    }
    .hs-nav-item {
      flex-direction: column;
      align-items: center;
      gap: 4px;
      padding: 8px 12px;
      font-size: 0.65rem;
      border-radius: 8px;
    }
    .hs-nav-item.on::before { display: none; }
    .hs-nav-item.on {
      background: transparent;
      color: #D4A820;
    }
    .hs-nav-item.on .hs-nav-icon { opacity: 1; color: #D4A820; }
    .hs-nav-icon { width: 20px; height: 20px; }
    .hs-divider { display: none; }
    .hs-bottom { display: none; }
    .hs-nav-section, .hs-nav-item.sec { display: none; }
    .hs-more { display: flex; }
    .hs-sheet {
      display: block; position: fixed; left: 0; right: 0; bottom: 64px;
      background: #0A0806; border-top: 1px solid rgba(243,239,234,0.08);
      padding: 10px 12px; max-height: 60vh; overflow-y: auto; z-index: 50;
    }
    .hs-sheet .hs-nav-item {
      display: flex; flex-direction: row; font-size: 0.82rem; padding: 10px 12px;
    }
    .hs-sheet .hs-nav-section { display: block; }
    .hs-main {
      margin-left: 0;
      padding-bottom: 70px;
    }
  }
`;

const IconDashboard = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
    <rect x="2" y="2" width="5.5" height="5.5" rx="1.5" stroke="currentColor" strokeWidth="1.4"/>
    <rect x="8.5" y="2" width="5.5" height="5.5" rx="1.5" stroke="currentColor" strokeWidth="1.4"/>
    <rect x="2" y="8.5" width="5.5" height="5.5" rx="1.5" stroke="currentColor" strokeWidth="1.4"/>
    <rect x="8.5" y="8.5" width="5.5" height="5.5" rx="1.5" stroke="currentColor" strokeWidth="1.4"/>
  </svg>
);

const IconChat = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
    <path d="M2 3C2 2.45 2.45 2 3 2h10c.55 0 1 .45 1 1v7c0 .55-.45 1-1 1H5l-3 3V3z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round"/>
  </svg>
);

const IconFeed = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
    <path d="M2 4h12M2 8h8M2 12h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <circle cx="13" cy="8" r="1.5" fill="currentColor"/>
  </svg>
);

const IconOrganizar = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
    <path d="M2 12 L5 7 L8 9 L11 5 L14 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M2 14h12" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" opacity="0.4"/>
  </svg>
);

const IconLogout = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
    <path d="M5 2H3C2.45 2 2 2.45 2 3v8c0 .55.45 1 1 1h2M9 10l3-3-3-3M12 7H5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

const IconDot = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
    <polygon points="8,2 13.2,5 13.2,11 8,14 2.8,11 2.8,5" stroke="currentColor" strokeWidth="1.3"/>
  </svg>
);

const navItems = [
  { key: 'dashboard' as HiveTab, label: 'Dashboard',    icon: <IconDashboard />, path: '/dashboard' },
  { key: 'chat'      as HiveTab, label: 'Chat IA',      icon: <IconChat />,      path: '/chat'      },
  { key: 'feed'      as HiveTab, label: 'Oportunidades',icon: <IconFeed />,      path: '/feed'      },
  { key: 'organizar' as HiveTab, label: 'Organizar',    icon: <IconOrganizar />, path: '/organizar' },
];

/**
 * O que ficava inalcançável: 6 páginas roteadas sem link (Estratégias, Metas,
 * Conexões, Perfil…) e as funcionalidades de backend que não tinham tela —
 * Defesa do Consumidor, Direitos Esquecidos, Impostos, Wrapped, Planos.
 */
const navSections: { title: string; items: { key: HiveTab; label: string; path: string }[] }[] = [
  {
    title: 'Ferramentas',
    items: [
      { key: 'strategies', label: 'Estratégias',        path: '/strategies' },
      { key: 'goals',      label: 'Metas',              path: '/goals' },
      { key: 'defesa',     label: 'Defesa do consumidor', path: '/defesa' },
      { key: 'direitos',   label: 'Direitos esquecidos',  path: '/direitos' },
      { key: 'impostos',   label: 'Impostos',           path: '/impostos' },
      { key: 'wrapped',    label: 'Seu ano (Wrapped)',  path: '/wrapped' },
    ],
  },
  {
    title: 'Conta',
    items: [
      { key: 'connections', label: 'Conexões bancárias', path: '/connections' },
      { key: 'widget',      label: 'Margem do dia e alertas', path: '/widget' },
      { key: 'planos',      label: 'Planos',             path: '/planos' },
      { key: 'profile',     label: 'Perfil e privacidade', path: '/profile' },
    ],
  },
];

export const AppShell: React.FC<AppShellProps> = ({ current, children, title, subtitle }) => {
  const navigate = useNavigate();
  const { displayName } = useSession();
  const initials = displayName.slice(0, 2).toUpperCase();
  const [maisAberto, setMaisAberto] = useState(false);
  const [saindo, setSaindo] = useState(false);

  // Sair revoga a sessão no servidor (access + refresh). O logout antigo só
  // limpava o navegador: o token seguia válido, e o histórico do chat em
  // cache local sobrevivia para o próximo usuário do mesmo aparelho.
  const handleLogout = async () => {
    setSaindo(true);
    await logout();
    navigate('/login', { replace: true });
  };

  const irPara = (path: string) => {
    setMaisAberto(false);
    navigate(path);
  };
  const secundariaAtiva = navSections.some(sec => sec.items.some(i => i.key === current));

  return (
    <>
      <style>{css}</style>
      <div className="hs">
        <aside className="hs-sidebar">
          <div className="hs-logo">
            <svg width="20" height="22" viewBox="0 0 180 200" fill="none">
              <polygon points="90,10 168,55 168,145 90,190 12,145 12,55" fill="#7A5002"/>
              <polygon points="90,10 12,55 12,145 90,190 105,181 105,19" fill="#D4A820"/>
              <polygon points="100,16 110,22 110,178 100,184" fill="#090500"/>
            </svg>
            <span className="hs-logo-word">HIVE</span>
          </div>

          <nav className="hs-nav">
            {navItems.map(item => (
              <button
                key={item.key}
                className={`hs-nav-item${current === item.key ? ' on' : ''}`}
                onClick={() => irPara(item.path)}
              >
                <span className="hs-nav-icon">{item.icon}</span>
                {item.label}
              </button>
            ))}
            {navSections.map(sec => (
              <div key={sec.title}>
                <div className="hs-nav-section">{sec.title}</div>
                {sec.items.map(item => (
                  <button
                    key={item.key}
                    className={`hs-nav-item sec${current === item.key ? ' on' : ''}`}
                    onClick={() => irPara(item.path)}
                  >
                    <span className="hs-nav-icon"><IconDot /></span>
                    {item.label}
                  </button>
                ))}
              </div>
            ))}
            <button
              className={`hs-nav-item hs-more${secundariaAtiva || maisAberto ? ' on' : ''}`}
              onClick={() => setMaisAberto(v => !v)}
              aria-expanded={maisAberto}
            >
              <span className="hs-nav-icon"><IconDot /></span>
              Mais
            </button>
          </nav>

          {maisAberto && (
            <div className="hs-sheet" role="menu">
              {navSections.map(sec => (
                <div key={sec.title}>
                  <div className="hs-nav-section">{sec.title}</div>
                  {sec.items.map(item => (
                    <button
                      key={item.key}
                      className={`hs-nav-item${current === item.key ? ' on' : ''}`}
                      onClick={() => irPara(item.path)}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              ))}
              <button className="hs-nav-item" onClick={handleLogout} disabled={saindo}>
                {saindo ? 'Saindo…' : 'Sair'}
              </button>
            </div>
          )}

          <div className="hs-divider" />

          <div className="hs-bottom">
            <div className="hs-user">
              <div className="hs-avatar">{initials}</div>
              <span className="hs-user-name">{displayName}</span>
            </div>
            <button className="hs-action" onClick={handleLogout} disabled={saindo}>
              <IconLogout />
              {saindo ? 'Saindo…' : 'Sair'}
            </button>
          </div>
        </aside>

        <main className="hs-main">
          {title && (
            <header className="hs-page-head">
              <h1 className="hs-page-title">{title}</h1>
              {subtitle && <p className="hs-page-sub">{subtitle}</p>}
            </header>
          )}
          {/* telas com título (as de ferramentas) não tinham margem própria */}
          {title ? <div className="hs-page-body">{children}</div> : children}
        </main>
      </div>
    </>
  );
};
