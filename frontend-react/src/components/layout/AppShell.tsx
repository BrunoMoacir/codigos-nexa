import { useEffect, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';

type AppShellTab = 'home' | 'dashboard' | 'goals' | 'strategies' | 'connections' | 'chat' | 'profile';

interface AppShellProps {
  current: AppShellTab;
  title: string;
  subtitle: string;
  children: ReactNode;
}

const navItems: Array<{ key: AppShellTab; icon: string; label: string; path: string }> = [
  { key: 'home', icon: '⌂', label: 'Início', path: '/home' },
  { key: 'dashboard', icon: '↗', label: 'Meu Dinheiro', path: '/dashboard' },
  { key: 'goals', icon: '🎯', label: 'Metas', path: '/goals' },
  { key: 'strategies', icon: '◈', label: 'Estratégias', path: '/strategies' },
  { key: 'connections', icon: '⌁', label: 'Conexões', path: '/connections' },
  { key: 'chat', icon: '◍', label: 'Chat IA', path: '/chat' },
  { key: 'profile', icon: '◉', label: 'Perfil', path: '/profile' },
];

export const AppShell: React.FC<AppShellProps> = ({ current, title, subtitle, children }) => {
  const navigate = useNavigate();
  const [isMobile, setIsMobile] = useState<boolean>(() => window.innerWidth < 980);
  const [dataOrigin, setDataOrigin] = useState<'real' | 'sandbox'>(() => {
    const raw = localStorage.getItem('nexa_data_origin');
    return raw === 'sandbox' ? 'sandbox' : 'real';
  });

  const userName = localStorage.getItem('user_name') || '';
  const userEmail = localStorage.getItem('user_email') || '';
  const displayName = userName || (userEmail ? userEmail.split('@')[0] : 'Usuário');

  const handleLogout = () => {
    localStorage.removeItem('jwt_token');
    localStorage.removeItem('user_id');
    localStorage.removeItem('user_name');
    localStorage.removeItem('user_email');
    localStorage.removeItem('nexa_data_origin');
    localStorage.removeItem('nexa_data_origin_updated_at');
    window.location.href = '/login';
  };

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < 980);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    const onStorage = () => {
      const raw = localStorage.getItem('nexa_data_origin');
      setDataOrigin(raw === 'sandbox' ? 'sandbox' : 'real');
    };
    window.addEventListener('storage', onStorage);
    const interval = window.setInterval(onStorage, 1500);
    return () => {
      window.removeEventListener('storage', onStorage);
      window.clearInterval(interval);
    };
  }, []);

  const [theme, setTheme] = useState<'light'|'dark'>(() => {
    return (localStorage.getItem('theme') as 'light'|'dark') || 'light';
  });

  const toggleTheme = () => {
    const newTheme = theme === 'light' ? 'dark' : 'light';
    setTheme(newTheme);
    localStorage.setItem('theme', newTheme);
    document.documentElement.setAttribute('data-theme', newTheme);
  };

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  return (
    <>
      <style>{`
        .app-shell-wrapper {
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .app-shell-sidebar {
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .app-shell-nav-item {
          transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .app-shell-nav-item:hover {
          background: var(--bg-hover) !important;
          transform: translateX(2px);
        }
        .app-shell-btn {
          transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .app-shell-btn:hover {
          background: var(--bg-hover) !important;
          color: var(--text-primary) !important;
        }
        .app-shell-user-chip {
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .app-shell-avatar {
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .app-shell-border {
          transition: border-color 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
      `}</style>
      <div
        className="app-shell-wrapper"
        style={{
          minHeight: '100vh',
          background: 'transparent',
          color: 'var(--text-primary)',
          display: 'flex',
          flexDirection: isMobile ? 'column' : 'row',
          fontFamily: 'Inter, system-ui, sans-serif',
        }}
      >
      <aside
        className="app-shell-sidebar app-shell-border"
        style={
          isMobile
            ? {
                width: '100%',
                flexShrink: 0,
                background: 'var(--bg-surface)',
                borderBottom: '1px solid var(--border-color)',
                display: 'grid',
                gap: 10,
                padding: '14px 14px 12px',
              }
            : {
                width: 220,
                flexShrink: 0,
                background: 'var(--bg-main)',
                borderRight: '1px solid var(--border-color)',
                display: 'flex',
                flexDirection: 'column',
                padding: '28px 20px',
                gap: 32,
                position: 'sticky',
                top: 0,
                height: '100vh',
              }
        }
      >
        <div style={{ fontSize: 17, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 8, height: 8, borderRadius: 999, background: 'var(--text-primary)' }} />
          Nexa
        </div>

        <nav
          style={
            isMobile
              ? {
                  display: 'flex',
                  gap: 6,
                  overflowX: 'auto',
                  paddingBottom: 2,
                }
              : { display: 'flex', flexDirection: 'column', gap: 2, flex: 1 }
          }
        >
          {navItems.map((item) => (
            <button
              key={item.key}
              onClick={() => navigate(item.path)}
              className="app-shell-nav-item"
              style={{
                padding: isMobile ? '7px 10px' : '8px 10px',
                borderRadius: 8,
                fontSize: 13.5,
                fontWeight: item.key === current ? 500 : 450,
                color: item.key === current ? 'var(--text-primary)' : 'var(--text-muted)',
                background: item.key === current ? 'var(--bg-active)' : 'transparent',
                border: 'none',
                cursor: 'pointer',
                textAlign: 'left',
                display: 'flex',
                gap: 8,
                alignItems: 'center',
                fontFamily: 'inherit',
                whiteSpace: 'nowrap',
              }}
            >
              <span style={{ width: 18, textAlign: 'center' }}>{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>

        <div
          style={
            isMobile
              ? { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }
              : { display: 'flex', flexDirection: 'column', gap: 8 }
          }
        >
          <div
            className="app-shell-user-chip"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '8px 10px',
              borderRadius: 8,
              background: 'var(--bg-active)',
              minWidth: 0,
            }}
          >
            <div
              className="app-shell-avatar"
              style={{
                width: 28,
                height: 28,
                borderRadius: 999,
                background: 'var(--text-primary)',
                color: 'var(--bg-surface)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 11,
                fontWeight: 600,
              }}
            >
              {displayName[0]?.toUpperCase() || 'U'}
            </div>
            <div style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {displayName}
            </div>
          </div>

          <button
            onClick={toggleTheme}
            className="app-shell-btn"
            style={{
              padding: '8px 10px',
              borderRadius: 8,
              fontSize: 13,
              fontWeight: 450,
              color: 'var(--text-muted)',
              border: 'none',
              background: 'transparent',
              textAlign: 'left',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              display: 'flex',
              gap: 8,
              alignItems: 'center',
            }}
          >
            <span>{theme === 'light' ? '☾' : '☀'}</span>
            Modo {theme === 'light' ? 'escuro' : 'claro'}
          </button>

          <button
            onClick={handleLogout}
            className="app-shell-btn"
            style={{
              padding: '8px 10px',
              borderRadius: 8,
              fontSize: 13,
              fontWeight: 450,
              color: 'var(--text-muted)',
              border: 'none',
              background: 'transparent',
              textAlign: 'left',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            ← Sair
          </button>
        </div>
      </aside>

      <main style={{ flex: 1, padding: isMobile ? '20px 14px 24px' : '40px 44px 44px', maxWidth: 1280, width: '100%' }}>
        <div style={{ marginBottom: 30 }}>
          <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-muted)', letterSpacing: 0.8, textTransform: 'uppercase', marginBottom: 6 }}>
            Nexa
          </div>
          <h1 style={{ margin: 0, fontSize: isMobile ? 24 : 28, fontWeight: 600, letterSpacing: -0.6, color: 'var(--text-primary)' }}>{title}</h1>
          <p style={{ marginTop: 6, color: 'var(--text-muted)', fontSize: 14 }}>{subtitle}</p>
          <div style={{ marginTop: 8 }}>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                padding: '4px 10px',
                fontSize: 11,
                borderRadius: 999,
                border: dataOrigin === 'sandbox' ? '1px solid #fde68a' : '1px solid #bbf7d0',
                background: dataOrigin === 'sandbox' ? '#fffbeb' : '#f0fdf4',
                color: dataOrigin === 'sandbox' ? '#92400e' : '#166534',
              }}
            >
              {dataOrigin === 'sandbox' ? 'Modo Sandbox: dados fictícios' : 'Dados reais conectados'}
            </span>
          </div>
        </div>
        {children}
      </main>
    </div>
    </>
  );
};
