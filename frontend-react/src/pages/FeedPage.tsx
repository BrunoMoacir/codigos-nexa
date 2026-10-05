import { useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { OpportunityRadarCard } from '../components/OpportunityRadarCard';
import { ComparadorInvestimentos } from '../components/ComparadorInvestimentos';
import { feedApi } from '../api/feed';
import type { Alertas, Notificacao, Notificacoes, Prioridade } from '../api/feed';
import { painelApi } from '../api/painel';
import { getErrorMessage } from '../api/errors';
import { getUserId } from '../api/session';

const css = `
  .fp { display: flex; flex-direction: column; min-height: 100vh; background: #0A0806; padding: 28px 28px 40px; gap: 20px; }

  /* Topo */
  .fp-top { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; }
  .fp-eyebrow { font-size: 0.62rem; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: #D4A820; margin-bottom: 6px; }
  .fp-title { font-size: 1.6rem; font-weight: 900; color: #F3EFEA; letter-spacing: -0.04em; line-height: 1; }
  .fp-top-kpis { display: flex; gap: 10px; }
  .fp-mini-kpi { background: #100E0B; border: 1px solid rgba(243,239,234,0.07); border-radius: 12px; padding: 12px 18px; text-align: right; }
  .fp-mini-val { font-size: 1.2rem; font-weight: 800; letter-spacing: -0.03em; font-variant-numeric: tabular-nums; }
  .fp-mini-val.red  { color: #F07A64; }
  .fp-mini-val.gold { color: #D4A820; }
  .fp-mini-val.dim  { color: #F3EFEA; }
  .fp-mini-label { font-size: 0.63rem; color: rgba(243,239,234,0.25); font-weight: 600; margin-top: 2px; letter-spacing: 0.04em; text-transform: uppercase; }

  /* Grid de cards */
  .fp-grid { display: flex; flex-direction: column; gap: 8px; }

  .fp-card {
    display: flex; align-items: center; gap: 16px;
    background: #100E0B;
    border: 1px solid rgba(243,239,234,0.06);
    border-left: 3px solid transparent;
    border-radius: 12px;
    padding: 16px 18px;
    transition: background 0.15s, border-color 0.12s;
    cursor: default;
  }
  .fp-card:hover { background: #161210; }
  .fp-card.alert { border-left-color: #F07A64; }
  .fp-card.warn  { border-left-color: #ECB040; }
  .fp-card.good  { border-left-color: #2EC8A4; }
  .fp-card.gold  { border-left-color: #D4A820; }
  .fp-card.info  { border-left-color: #60B0F2; }

  .fp-card-icon {
    width: 38px; height: 38px; border-radius: 10px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    font-size: 1rem; font-weight: 800;
  }
  .fp-card.alert .fp-card-icon { background: rgba(240,122,100,0.1);  color: #F07A64; }
  .fp-card.warn  .fp-card-icon { background: rgba(236,176,64,0.1);   color: #ECB040; }
  .fp-card.good  .fp-card-icon { background: rgba(46,200,164,0.1);   color: #2EC8A4; }
  .fp-card.gold  .fp-card-icon { background: rgba(212,168,32,0.1);   color: #D4A820; }
  .fp-card.info  .fp-card-icon { background: rgba(96,176,242,0.1);   color: #60B0F2; }

  .fp-card-body { flex: 1; min-width: 0; }
  .fp-card-title { font-size: 0.87rem; font-weight: 700; color: #F3EFEA; margin-bottom: 2px; }
  .fp-card-desc  { font-size: 0.73rem; color: rgba(243,239,234,0.32); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  .fp-card-right { text-align: right; flex-shrink: 0; }
  .fp-card-amount { font-size: 0.95rem; font-weight: 800; font-variant-numeric: tabular-nums; letter-spacing: -0.02em; }
  .fp-card.alert .fp-card-amount { color: #F07A64; }
  .fp-card.warn  .fp-card-amount { color: #ECB040; }
  .fp-card.good  .fp-card-amount { color: #2EC8A4; }
  .fp-card.gold  .fp-card-amount { color: #D4A820; }
  .fp-card.info  .fp-card-amount { color: #60B0F2; }
  .fp-card-tag   { font-size: 0.62rem; color: rgba(243,239,234,0.22); margin-top: 3px; font-weight: 600; letter-spacing: 0.04em; }

  .fp-section-label { font-size: 0.62rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: rgba(243,239,234,0.2); margin: 4px 0 8px; }

  /* Ações do card */
  .fp-card { align-items: flex-start; }
  .fp-card-desc.full { white-space: normal; line-height: 1.45; margin-top: 2px; }
  .fp-card-hint { font-size: 0.72rem; color: #D4A820; margin-top: 6px; line-height: 1.4; }
  .fp-actions { display: flex; gap: 6px; margin-top: 10px; flex-wrap: wrap; }
  .fp-act { background: rgba(243,239,234,0.06); color: rgba(243,239,234,0.75); border: 1px solid rgba(243,239,234,0.1); border-radius: 7px; padding: 5px 10px; font-family: inherit; font-size: 0.7rem; font-weight: 700; cursor: pointer; }
  .fp-act.go { background: rgba(212,168,32,0.12); color: #D4A820; border-color: rgba(212,168,32,0.3); }
  .fp-act:disabled { opacity: 0.5; cursor: default; }
  .fp-msg { font-size: 0.78rem; color: rgba(243,239,234,0.45); background: #100E0B; border: 1px solid rgba(243,239,234,0.06); border-radius: 12px; padding: 14px 18px; line-height: 1.5; }
  .fp-msg.erro { color: #F8AEA0; border-color: rgba(240,122,100,0.25); }

  /* Skeleton */
  .fp-skel { background: rgba(243,239,234,0.05); border-radius: 12px; animation: fp-pulse 1.4s ease-in-out infinite; }
  @keyframes fp-pulse { 0%,100%{opacity:0.35} 50%{opacity:0.7} }

  /* CTA */
  .fp-cta { display: flex; align-items: center; justify-content: space-between; gap: 20px; background: rgba(212,168,32,0.06); border: 1px solid rgba(212,168,32,0.14); border-radius: 12px; padding: 16px 20px; }
  .fp-cta-text { font-size: 0.85rem; font-weight: 700; color: rgba(243,239,234,0.65); }
  .fp-cta-sub  { font-size: 0.7rem; color: rgba(243,239,234,0.25); margin-top: 2px; }
  .fp-cta-btn  { padding: 8px 16px; background: #D4A820; color: #0A0800; border: none; border-radius: 8px; font-family: inherit; font-size: 0.78rem; font-weight: 800; letter-spacing: 0.04em; cursor: pointer; white-space: nowrap; transition: background 0.15s; flex-shrink: 0; }
  .fp-cta-btn:hover { background: #E8C030; }

  @media (max-width: 860px) {
    .fp { padding: 16px 14px 32px; }
    .fp-top { flex-direction: column; align-items: flex-start; }
    .fp-cta { flex-direction: column; align-items: flex-start; }
    .fp-cta-btn { width: 100%; text-align: center; }
  }
`;

type CardType = 'alert' | 'warn' | 'info';

const TIPO_POR_PRIORIDADE: Record<Prioridade, CardType> = { CRITICAL: 'alert', WARNING: 'warn', INFO: 'info' };
const ICONE: Record<CardType, string> = { alert: '↯', warn: '◔', info: '✦' };
const ORDEM: Record<Prioridade, number> = { CRITICAL: 0, WARNING: 1, INFO: 2 };
const COBERTOS_PELO_RADAR = new Set(['SAVINGS_BELOW_CDI', 'IDLE_MONEY_DETECTED']);
const ROTULO: Record<Prioridade, string> = { CRITICAL: 'URGENTE', WARNING: 'ATENÇÃO', INFO: 'PARA SABER' };

/** Card unificado: notificação do motor proativo ou alerta operacional. */
interface Card {
  chave: string;
  origem: 'notificacao' | 'alerta';
  prioridade: Prioridade;
  titulo: string;
  texto: string;
  dica?: string | null;
  rota?: string | null;
  notificacao?: Notificacao;
  alertaId?: string;
}

function rotaDaInterface(rota?: string | null): string | null {
  // '/feed' é esta própria tela; rota de API (/api/...) não é navegável
  if (!rota || rota === '/feed' || rota.startsWith('/api/')) return null;
  return rota;
}

// O Feed lia só /alerts, classificava pelo campo errado (type em vez de level)
// e, sem dado ou com erro, mostrava cards DEMO_* fixos com o banner "conecte
// seu banco". Agora: /notifications é a fonte principal (17 tipos de card),
// /alerts entra pelo `level`, cada card tem ação e "dispensar" de verdade, e
// erro aparece como erro.
export const FeedPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const userId = getUserId();

  const notifQ = useQuery({
    queryKey: ['feed', 'notificacoes', userId],
    queryFn: () => feedApi.notificacoes(userId),
    enabled: !!userId, staleTime: 2 * 60 * 1000,
  });
  const alertasQ = useQuery({
    queryKey: ['feed', 'alertas', userId],
    queryFn: () => feedApi.alertas(userId),
    enabled: !!userId, staleTime: 2 * 60 * 1000,
  });
  const conexoesQ = useQuery({ queryKey: ['pluggy', 'conexoes'], queryFn: painelApi.conexoes, enabled: !!userId, retry: false });

  const cards: Card[] = [
    // dinheiro parado e poupança × CDI são o próprio card do Radar, logo abaixo
    ...(notifQ.data?.notifications || []).filter(n => !COBERTOS_PELO_RADAR.has(n.type)).map((n): Card => ({
      chave: `n:${n.fingerprint}`, origem: 'notificacao', prioridade: n.priority,
      titulo: n.title, texto: n.message, dica: n.action_hint, rota: rotaDaInterface(n.action_route), notificacao: n,
    })),
    ...(alertasQ.data?.alerts || []).map((a): Card => ({
      chave: `a:${a.id}`, origem: 'alerta', prioridade: a.level,
      titulo: a.title, texto: a.message, rota: rotaDaInterface(a.action_url), alertaId: a.id,
    })),
  ].sort((x, y) => ORDEM[x.prioridade] - ORDEM[y.prioridade]);

  const urgentes = cards.filter(c => c.prioridade !== 'INFO');
  const avisos = cards.filter(c => c.prioridade === 'INFO');

  // 'shown' uma vez por card nesta montagem — só para o que o servidor ainda
  // não tinha visto (o GET não marca mais nada: é idempotente).
  const enviados = useRef(new Set<string>());
  useEffect(() => {
    for (const n of notifQ.data?.notifications || []) {
      if (!n.seen && !enviados.current.has(n.fingerprint)) {
        enviados.current.add(n.fingerprint);
        feedApi.evento(userId, n, 'shown');
      }
    }
  }, [notifQ.data, userId]);

  function abrir(c: Card) {
    if (c.notificacao) feedApi.evento(userId, c.notificacao, 'tapped');
    if (c.rota) navigate(c.rota);
  }

  async function dispensar(c: Card) {
    // some na hora; o servidor confirma em segundo plano
    if (c.notificacao) {
      const fp = c.notificacao.fingerprint;
      queryClient.setQueryData<Notificacoes>(['feed', 'notificacoes', userId], d =>
        d ? { ...d, notifications: d.notifications.filter(n => n.fingerprint !== fp), total: d.total - 1 } : d);
      await feedApi.evento(userId, c.notificacao, 'dismissed');
    } else if (c.alertaId) {
      const id = c.alertaId;
      queryClient.setQueryData<Alertas>(['feed', 'alertas', userId], d =>
        d ? { ...d, alerts: d.alerts.filter(a => a.id !== id) } : d);
      try {
        await feedApi.dispensarAlerta(userId, id);
      } catch {
        queryClient.invalidateQueries({ queryKey: ['feed', 'alertas', userId] });
      }
    }
  }

  const loading = notifQ.isLoading || alertasQ.isLoading;
  const erro = notifQ.error && alertasQ.error ? notifQ.error : null;
  const semConexao = conexoesQ.data && conexoesQ.data.total === 0;

  const renderCard = (c: Card) => {
    const tipo = TIPO_POR_PRIORIDADE[c.prioridade];
    return (
      <div key={c.chave} className={`fp-card ${tipo}`}>
        <div className="fp-card-icon">{ICONE[tipo]}</div>
        <div className="fp-card-body">
          <div className="fp-card-title">{c.titulo}</div>
          {c.texto && <div className="fp-card-desc full">{c.texto}</div>}
          {c.dica && <div className="fp-card-hint">→ {c.dica}</div>}
          <div className="fp-actions">
            {c.rota && <button className="fp-act go" onClick={() => abrir(c)}>Ver detalhes →</button>}
            <button className="fp-act" onClick={() => dispensar(c)} aria-label={`Dispensar: ${c.titulo}`}>Dispensar</button>
          </div>
        </div>
        <div className="fp-card-right">
          <div className="fp-card-tag">{ROTULO[c.prioridade]}</div>
        </div>
      </div>
    );
  };

  return (
    <AppShell current="feed">
      <style>{css}</style>
      <div className="fp">

        {/* Topo */}
        <div className="fp-top">
          <div>
            <div className="fp-eyebrow">Feed de Oportunidades</div>
            <div className="fp-title">O que o banco<br />não te conta.</div>
          </div>
          {!loading && !erro && (
            <div className="fp-top-kpis">
              <div className="fp-mini-kpi">
                <div className="fp-mini-val red">{urgentes.length}</div>
                <div className="fp-mini-label">Pedem atenção</div>
              </div>
              <div className="fp-mini-kpi">
                <div className="fp-mini-val gold">{avisos.length}</div>
                <div className="fp-mini-label">Oportunidades</div>
              </div>
              <div className="fp-mini-kpi">
                <div className="fp-mini-val dim">{cards.length}</div>
                <div className="fp-mini-label">Total</div>
              </div>
            </div>
          )}
        </div>

        {erro && (
          <div className="fp-msg erro">
            {getErrorMessage(erro, 'Não foi possível carregar o feed.')}{' '}
            <button className="fp-act" onClick={() => { notifQ.refetch(); alertasQ.refetch(); }}>Tentar de novo</button>
          </div>
        )}
        {/* uma das duas fontes falhou: o resto aparece, mas avisa */}
        {!erro && (notifQ.error || alertasQ.error) && (
          <div className="fp-msg erro">
            Parte do feed não carregou ({getErrorMessage(notifQ.error || alertasQ.error)}).
          </div>
        )}

        {loading ? (
          <div className="fp-grid">
            {[1,2,3,4].map(i => <div key={i} className="fp-skel" style={{ height: 72 }} />)}
          </div>
        ) : !erro && (
          <>
            <div className="fp-section-label">Pedem atenção</div>
            {urgentes.length > 0
              ? <div className="fp-grid">{urgentes.map(renderCard)}</div>
              : <div className="fp-msg">Nada urgente agora. Quando um gasto fugir do ritmo, uma tarifa subir ou o saldo apertar, aparece aqui.</div>}

            <div className="fp-section-label">Oportunidades</div>
            <OpportunityRadarCard userId={userId} />
            <ComparadorInvestimentos userId={userId} />
            {avisos.length > 0 && <div className="fp-grid">{avisos.map(renderCard)}</div>}
          </>
        )}

        {semConexao && (
          <div className="fp-cta">
            <div>
              <div className="fp-cta-text">Conecte seu banco para o feed olhar o seu dinheiro</div>
              <div className="fp-cta-sub">
                {conexoesQ.data?.pluggy_configured === false
                  ? 'Open Finance ainda não está configurado neste ambiente.'
                  : 'Open Finance · leitura apenas · criptografado'}
              </div>
            </div>
            <button className="fp-cta-btn" onClick={() => navigate('/connections')}>Conectar banco →</button>
          </div>
        )}
      </div>
    </AppShell>
  );
};
