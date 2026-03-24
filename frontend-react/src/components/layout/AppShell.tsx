import type { ReactNode } from 'react';
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
  const userId = localStorage.getItem('user_id') || '';
  const displayName = userId
    ? userId.split('@')[0].split('_')[0].replace(/^./, (c) => c.toUpperCase())
    : 'Usuário';

  const handleLogout = () => {
    localStorage.removeItem('jwt_token');
    localStorage.removeItem('user_id');
    window.location.href = '/login';
  };

  return (
    <div style={{ minHeight: '100vh', background: '#fafafa', color: '#111', display: 'flex', fontFamily: 'Inter, system-ui, sans-serif' }}>
      <aside
        style={{
          width: 220,
          flexShrink: 0,
          background: '#fff',
          borderRight: '1px solid #ebebeb',
          display: 'flex',
          flexDirection: 'column',
          padding: '28px 20px',
          gap: 32,
        }}
      >
        <div style={{ fontSize: 17, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 8, height: 8, borderRadius: 999, background: '#111' }} />
          Nexa
        </div>

        <nav style={{ display: 'flex', flexDirection: 'column', gap: 2, flex: 1 }}>
          {navItems.map((item) => (
            <button
              key={item.key}
              onClick={() => navigate(item.path)}
              style={{
                padding: '8px 10px',
                borderRadius: 8,
                fontSize: 13.5,
                fontWeight: item.key === current ? 500 : 450,
                color: item.key === current ? '#111' : '#888',
                background: item.key === current ? '#f4f4f5' : 'transparent',
                border: 'none',
                cursor: 'pointer',
                textAlign: 'left',
                display: 'flex',
                gap: 10,
                alignItems: 'center',
                fontFamily: 'inherit',
              }}
            >
              <span style={{ width: 18, textAlign: 'center' }}>{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '8px 10px',
              borderRadius: 8,
              background: '#f4f4f5',
            }}
          >
            <div
              style={{
                width: 28,
                height: 28,
                borderRadius: 999,
                background: '#111',
                color: '#fff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 11,
                fontWeight: 600,
              }}
            >
              {displayName[0]?.toUpperCase() || 'U'}
            </div>
            <div style={{ fontSize: 12.5, fontWeight: 500, color: '#111', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {displayName}
            </div>
          </div>
          <button
            onClick={handleLogout}
            style={{
              padding: '8px 10px',
              borderRadius: 8,
              fontSize: 13,
              fontWeight: 450,
              color: '#999',
              border: 'none',
              background: 'transparent',
              textAlign: 'left',
              cursor: 'pointer',
            }}
          >
            ← Sair
          </button>
        </div>
      </aside>

      <main style={{ flex: 1, padding: '42px 56px 56px', maxWidth: 1100, width: '100%' }}>
        <div style={{ marginBottom: 30 }}>
          <div style={{ fontSize: 12, fontWeight: 500, color: '#aaa', letterSpacing: 0.8, textTransform: 'uppercase', marginBottom: 6 }}>
            Nexa
          </div>
          <h1 style={{ margin: 0, fontSize: 28, fontWeight: 600, letterSpacing: -0.6, color: '#111' }}>{title}</h1>
          <p style={{ marginTop: 6, color: '#999', fontSize: 14 }}>{subtitle}</p>
        </div>
        {children}
      </main>
    </div>
  );
};
