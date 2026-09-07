import React, { useState } from 'react';
import { AppShell } from '../components/layout/AppShell';
import { isDemoMode, setDemoMode } from '../utils/demoMode';

const card: React.CSSProperties = {
  background: 'var(--bg-surface)',
  border: '1px solid var(--border-color)',
  borderRadius: 12,
  padding: 16,
};

const label: React.CSSProperties = {
  fontSize: 11,
  letterSpacing: 0.8,
  textTransform: 'uppercase',
  color: 'var(--text-muted)',
  marginBottom: 6,
  fontWeight: 600,
};

export const ProfilePage: React.FC = () => {
  const userId = localStorage.getItem('user_id') || 'Não definido';
  const userName = localStorage.getItem('user_name') || '';
  const userEmail = localStorage.getItem('user_email') || 'Não definido';
  const displayName = userName || (userEmail && userEmail.includes('@') ? userEmail.split('@')[0] : 'Usuário');
  const token = localStorage.getItem('jwt_token');
  const theme = localStorage.getItem('theme') || 'light';
  const dataOrigin = localStorage.getItem('nexa_data_origin') === 'sandbox' ? 'Sandbox' : 'Dados reais';
  const dataOriginUpdatedAt = localStorage.getItem('nexa_data_origin_updated_at');
  const rawUserId = localStorage.getItem('user_id') || '';
  const [demoMode, setDemoModeState] = useState(() => isDemoMode(rawUserId));

  const toggleDemoMode = () => {
    const next = !demoMode;
    setDemoMode(rawUserId, next);
    setDemoModeState(next);
  };

  return (
    <AppShell
      current="profile"
    >
      <div style={{ display: 'grid', gap: 12 }}>
        <div style={{ ...card, display: 'flex', alignItems: 'center', gap: 14 }}>
          <div
            style={{
              width: 58,
              height: 58,
              borderRadius: 999,
              background: 'var(--text-primary)',
              color: 'var(--bg-surface)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 20,
              fontWeight: 700,
            }}
          >
            {displayName?.[0]?.toUpperCase() || 'U'}
          </div>
          <div>
            <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)' }}>{displayName}</div>
            <div style={{ fontSize: 14, color: 'var(--text-muted)', marginTop: 2 }}>{userEmail}</div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
          <div style={card}>
            <div style={label}>Conta</div>
            <div style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 8 }}>ID do usuário</div>
            <div style={{ fontSize: 13, color: 'var(--text-primary)', wordBreak: 'break-all' }}>{userId}</div>
          </div>

          <div style={card}>
            <div style={label}>Sessão</div>
            <div style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 8 }}>
              Status de autenticação
            </div>
            <div style={{ fontSize: 13, color: token ? '#166534' : '#991b1b', fontWeight: 600 }}>
              {token ? 'Logado' : 'Sem token'}
            </div>
          </div>

          <div style={card}>
            <div style={label}>Preferências</div>
            <div style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 8 }}>Tema atual</div>
            <div style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 600 }}>
              {theme === 'dark' ? 'Escuro' : 'Claro'}
            </div>
          </div>

          <div style={card}>
            <div style={label}>Dados</div>
            <div style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 8 }}>Origem detectada</div>
            <div style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 600 }}>{dataOrigin}</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 6 }}>
              {dataOriginUpdatedAt
                ? `Atualizado em ${new Date(dataOriginUpdatedAt).toLocaleString('pt-BR')}`
                : 'Sem atualização registrada'}
            </div>
          </div>
        </div>

        <div style={{ ...card, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
          <div>
            <div style={label}>Modo demonstração</div>
            <div style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 4 }}>
              Mostra dados de exemplo em Organizar, Oportunidades e Cartões — só nesta conta.
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {demoMode
                ? 'Ativado — você está vendo dados fictícios.'
                : 'Desativado — mostrando o estado real (vazio até conectar um banco).'}
            </div>
          </div>
          <button
            onClick={toggleDemoMode}
            aria-pressed={demoMode}
            style={{
              width: 46, height: 26, borderRadius: 999, border: 'none', cursor: 'pointer',
              background: demoMode ? '#D4A820' : 'var(--border-color)',
              position: 'relative', flexShrink: 0, transition: 'background 0.15s',
            }}
          >
            <span style={{
              position: 'absolute', top: 3, left: demoMode ? 23 : 3,
              width: 20, height: 20, borderRadius: '50%', background: '#fff',
              transition: 'left 0.15s', boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
            }} />
          </button>
        </div>
      </div>
    </AppShell>
  );
};
