import { useEffect, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';

export type HiveTab = 'chat' | 'feed' | 'organizar';

interface AppShellProps {
  current: HiveTab;
  children: ReactNode;
}

const css = `
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800;900&display=swap');

  .hs {
    font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
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

  .hs-nav { display: flex; flex-direction: column; gap: 2px; flex: 1; }

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
  }

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
    .hs-main {
      margin-left: 0;
      padding-bottom: 70px;
    }
  }
`;

const IconChat = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
    <path d="M2 3C2 2.45 2.45 2 3 2h10c.55 0 1 .45 1 1v7c0 .55-.45 1-1 1H5l-3 3V3z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round"/>
  </svg>
);

const IconFeed = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
    <rect x="2" y="2" width="5" height="5" rx="1.2" stroke="currentColor" strokeWidth="1.4"/>
    <rect x="9" y="2" width="5" height="5" rx="1.2" stroke="currentColor" strokeWidth="1.4"/>
    <rect x="2" y="9" width="5" height="5" rx="1.2" stroke="currentColor" strokeWidth="1.4"/>
    <rect x="9" y="9" width="5" height="5" rx="1.2" stroke="currentColor" strokeWidth="1.4"/>
  </svg>
);

const IconOrganizar = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
    <path d="M2 5h12M2 8h8M2 11h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
);

const IconLogout = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
    <path d="M5 2H3C2.45 2 2 2.45 2 3v8c0 .55.45 1 1 1h2M9 10l3-3-3-3M12 7H5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

const navItems = [
  { key: 'chat' as HiveTab, label: 'Chat IA', icon: <IconChat />, path: '/chat' },
  { key: 'feed' as HiveTab, label: 'Oportunidades', icon: <IconFeed />, path: '/feed' },
  { key: 'organizar' as HiveTab, label: 'Organizar', icon: <IconOrganizar />, path: '/organizar' },
];

export const AppShell: React.FC<AppShellProps> = ({ current, children }) => {
  const navigate = useNavigate();
  const [, forceUpdate] = useState(0);

  const userName = localStorage.getItem('user_name') || '';
  const userEmail = localStorage.getItem('user_email') || '';
  const displayName = userName || (userEmail ? userEmail.split('@')[0] : 'Usuário');
  const initials = displayName.slice(0, 2).toUpperCase();

  const handleLogout = () => {
    ['jwt_token','user_id','user_name','user_email','nexa_data_origin','nexa_data_origin_updated_at'].forEach(k => localStorage.removeItem(k));
    window.location.href = '/login';
  };

  useEffect(() => { forceUpdate(n => n + 1); }, []);

  return (
    <>
      <style>{css}</style>
      <div className="hs">
        <aside className="hs-sidebar">
          <div className="hs-logo">
            <div className="hs-logo-dot" />
            <span className="hs-logo-word">HIVE</span>
          </div>

          <nav className="hs-nav">
            {navItems.map(item => (
              <button
                key={item.key}
                className={`hs-nav-item${current === item.key ? ' on' : ''}`}
                onClick={() => navigate(item.path)}
              >
                <span className="hs-nav-icon">{item.icon}</span>
                {item.label}
              </button>
            ))}
          </nav>

          <div className="hs-divider" />

          <div className="hs-bottom">
            <div className="hs-user">
              <div className="hs-avatar">{initials}</div>
              <span className="hs-user-name">{displayName}</span>
            </div>
            <button className="hs-action" onClick={handleLogout}>
              <IconLogout />
              Sair
            </button>
          </div>
        </aside>

        <main className="hs-main">
          {children}
        </main>
      </div>
    </>
  );
};
