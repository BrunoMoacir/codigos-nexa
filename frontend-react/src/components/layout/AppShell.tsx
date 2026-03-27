import { useEffect, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';

type AppShellTab = 'home' | 'dashboard' | 'strategies' | 'connections' | 'chat';

interface AppShellProps {
  current: AppShellTab;
  title: string;
  subtitle: string;
  children: ReactNode;
}

const navItems: Array<{ key: AppShellTab; icon: string; label: string; path: string }> = [
  { key: 'home', icon: '⌂', label: 'Início', path: '/home' },
  { key: 'dashboard', icon: '↗', label: 'Meu Dinheiro', path: '/dashboard' },
  { key: 'strategies', icon: '◈', label: 'Estratégias', path: '/strategies' },
  { key: 'connections', icon: '⌁', label: 'Conexões', path: '/connections' },
  { key: 'chat', icon: '◍', label: 'Chat IA', path: '/chat' },
];

export const AppShell: React.FC<AppShellProps> = ({ current, title, subtitle, children }) => {
  const navigate = useNavigate();
  const [isMobile, setIsMobile] = useState<boolean>(() => window.innerWidth < 980);
  const userId = localStorage.getItem('user_id') || '';
  const displayName = userId
    ? userId.split('@')[0].split('_')[0].replace(/^./, (c) => c.toUpperCase())
    : 'Usuário';

  const handleLogout = () => {
    localStorage.removeItem('jwt_token');
    localStorage.removeItem('user_id');
    window.location.href = '/login';
  };

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < 980);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const [theme, setTheme] = useState<'light'|'dark'>(() => {
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

  useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
    } else {
      document.documentElement.removeAttribute('data-theme');
    }
  }, [theme]);

  return (
    <div
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
        style={
          isMobile
            ? {
                width: '100%',
                flexShrink: 0,
                background: 'var(--bg-surface)',
                borderBottom: '1px solid #ebebeb',
                display: 'grid',
                gap: 10,
                padding: '14px 14px 12px',
              }
            : {
                width: 220,
                flexShrink: 0,
                background: 'var(--bg-main)',
                borderRight: '1px solid #ebebeb',
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
            <span>{theme === 'light' ? '🌙' : '☀️'}</span>
            Modo {theme === 'light' ? 'Escuro' : 'Claro'}
          </button>

          <button
            onClick={handleLogout}
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
        </div>
        {children}
      </main>
    </div>
  );
};
