/**
 * WidgetPage (R1.d) — superfície compacta do safe-to-spend.
 *
 * Pensada para: atalho do PWA na homescreen, janela pequena fixada no
 * desktop e como preview do futuro widget nativo. Uma olhada responde
 * "quanto posso gastar hoje?" — número grande, cor semafórica, contexto
 * em uma linha. Consome GET /safe-to-spend/{user}/widget (payload ~200B,
 * cache de 15 min no backend) e reconsulta a cada 15 min.
 *
 * Também é onde o usuário ativa os alertas push (cards WARNING/CRITICAL
 * chegam como notificação de sistema com o app fechado).
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import apiClient from '../api/client';
import { describeError } from '../api/errors';
import { getUserId } from '../api/session';
import { dataCurta } from '../api/painel';
import { getPushState, subscribeToPush, unsubscribeFromPush } from '../pwa/push';
import type { PushState } from '../pwa/push';

interface WidgetData {
  daily: number;
  remaining_month: number;
  pct_consumed: number;
  status: 'OK' | 'ATENCAO' | 'CRITICO';
  color: string;
  headline: string;
  subline: string;
  /** data do último lançamento do extrato ('YYYY-MM-DD') */
  data_as_of: string | null;
  /** extrato com mais de 7 dias — o número é de antes disso */
  stale: boolean;
  updated_at: string;
}

const REFRESH_MS = 15 * 60 * 1000;

const brl = (v: number) =>
  v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });

export const WidgetPage: React.FC = () => {
  const navigate = useNavigate();
  const userId = getUserId();
  const [data, setData] = useState<WidgetData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pushState, setPushState] = useState<PushState>('unsupported');
  const [pushBusy, setPushBusy] = useState(false);

  const load = useCallback(async () => {
    if (!userId) return;
    try {
      const { data } = await apiClient.get<WidgetData>(`/safe-to-spend/${userId}/widget`);
      setData(data);
      setError(null);
    } catch (err) {
      setError(describeError(err, 'Não foi possível atualizar agora.').message);
    }
  }, [userId]);

  useEffect(() => {
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    getPushState().then(setPushState).catch(() => setPushState('unsupported'));
  }, []);

  const [pushErro, setPushErro] = useState<string | null>(null);
  const togglePush = async () => {
    setPushBusy(true);
    setPushErro(null);
    try {
      const next = pushState === 'subscribed' ? await unsubscribeFromPush() : await subscribeToPush();
      setPushState(next);
    } catch (err) {
      // antes: falha silenciosa, o botão só voltava ao estado anterior
      setPushErro(describeError(err, 'Não foi possível mudar os alertas push.').message);
    } finally {
      setPushBusy(false);
    }
  };

  const pushLabel: Record<PushState, string> = {
    unsupported: 'Push não suportado neste navegador',
    'not-configured': 'Alertas push ainda não configurados no servidor',
    denied: 'Notificações bloqueadas no navegador',
    subscribed: '🔕 Desativar alertas push',
    unsubscribed: '🔔 Ativar alertas push',
  };
  const pushToggleable = pushState === 'subscribed' || pushState === 'unsubscribed';

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 18,
        padding: 24,
        background: 'var(--bg-base, #0f172a)',
        color: 'var(--text-primary, #f8fafc)',
        fontFamily: 'inherit',
        textAlign: 'center',
      }}
    >
      {!userId && (
        <p style={{ opacity: 0.8 }}>
          Faça login para ver sua margem segura.{' '}
          <Link to="/login?next=/widget" style={{ color: '#818cf8' }}>Entrar</Link>
        </p>
      )}

      {userId && !data && !error && <p style={{ opacity: 0.6 }}>Calculando sua margem…</p>}
      {userId && error && !data && <p style={{ opacity: 0.8 }}>{error}</p>}

      {data && (
        <>
          <div
            style={{
              fontSize: 11,
              letterSpacing: 1.2,
              textTransform: 'uppercase',
              fontWeight: 700,
              opacity: 0.65,
            }}
          >
            Seguro para gastar hoje
          </div>

          <div
            style={{
              fontSize: 64,
              fontWeight: 800,
              lineHeight: 1,
              color: data.color,
              textShadow: `0 0 40px ${data.color}44`,
            }}
          >
            {brl(data.daily)}
          </div>

          <div style={{ fontSize: 14, opacity: 0.85 }}>{data.subline}</div>

          <div
            style={{
              width: 'min(280px, 80vw)',
              height: 8,
              borderRadius: 999,
              background: 'rgba(148, 163, 184, 0.25)',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${Math.min(100, data.pct_consumed)}%`,
                height: '100%',
                borderRadius: 999,
                background: data.color,
                transition: 'width 0.6s ease',
              }}
            />
          </div>
          <div style={{ fontSize: 12, opacity: 0.6 }}>
            {/* com margem zero, "0% do mês usado · R$ 0 restantes" ao lado de
                "Segure os gastos" se contradizia */}
            {data.remaining_month <= 0
              ? 'Sem margem segura este mês'
              : `${data.pct_consumed.toFixed(0)}% do mês usado · ${brl(data.remaining_month)} restantes`}
          </div>
          {data.data_as_of && (
            <div style={{ fontSize: 11, opacity: data.stale ? 0.9 : 0.45, color: data.stale ? '#eab308' : undefined }}>
              {data.stale ? 'Extrato desatualizado: ' : 'Dados do extrato até '}{dataCurta(data.data_as_of)}
              {data.stale && <> · <Link to="/connections" style={{ color: 'inherit' }}>sincronizar</Link></>}
            </div>
          )}

          {error && <div style={{ fontSize: 11, opacity: 0.5 }}>{error}</div>}
        </>
      )}

      {userId && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 8 }}>
          <button
            onClick={togglePush}
            disabled={!pushToggleable || pushBusy}
            style={{
              padding: '10px 18px',
              borderRadius: 10,
              border: '1px solid rgba(129, 140, 248, 0.4)',
              background: pushState === 'subscribed' ? 'transparent' : 'rgba(99, 102, 241, 0.2)',
              color: 'inherit',
              cursor: pushToggleable ? 'pointer' : 'default',
              opacity: pushToggleable ? 1 : 0.5,
              fontSize: 13,
              fontWeight: 600,
            }}
          >
            {pushBusy ? '…' : pushLabel[pushState]}
          </button>
          {pushErro && <div style={{ fontSize: 11, color: '#f87171' }}>{pushErro}</div>}

          <button
            onClick={() => navigate('/feed')}
            style={{
              padding: '8px 18px',
              borderRadius: 10,
              border: 'none',
              background: 'transparent',
              color: '#818cf8',
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            Ver oportunidades →
          </button>
        </div>
      )}
    </div>
  );
};
