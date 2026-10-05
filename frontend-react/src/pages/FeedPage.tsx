import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { nexaApi } from '../api/nexa';
import { isDemoMode } from '../utils/demoMode';

const css = `
  @import url('https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700,800,900&display=swap');

  .fp { font-family: 'Satoshi', system-ui, sans-serif; display: flex; flex-direction: column; min-height: 100vh; background: #0A0806; padding: 28px 28px 40px; gap: 20px; }

  /* Topo */
  .fp-top { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; }
  .fp-eyebrow { font-size: 0.62rem; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: #D4A820; margin-bottom: 6px; }
  .fp-title { font-size: 1.6rem; font-weight: 900; color: #F3EFEA; letter-spacing: -0.04em; line-height: 1; }
  .fp-title em { font-style: normal; color: #D4A820; }

  /* Hero — resumo + gráfico comparativo */
  .fp-hero {
    display: grid; grid-template-columns: 1fr 1.3fr; gap: 26px;
    background: linear-gradient(135deg, #14110C 0%, #0F0D0A 100%);
    border: 1px solid rgba(243,239,234,0.08);
    border-radius: 20px;
    padding: 26px 28px;
    position: relative;
    overflow: hidden;
  }
  .fp-hero::before {
    content: '';
    position: absolute; top: -60px; right: -60px;
    width: 220px; height: 220px; border-radius: 50%;
    background: radial-gradient(circle, rgba(212,168,32,0.16), transparent 70%);
    pointer-events: none;
  }
  .fp-hero-main { display: flex; flex-direction: column; justify-content: center; gap: 6px; position: relative; z-index: 1; }
  .fp-hero-label { font-size: 0.68rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: rgba(243,239,234,0.35); }
  .fp-hero-value { font-size: 2.3rem; font-weight: 900; letter-spacing: -0.05em; color: #F3EFEA; font-variant-numeric: tabular-nums; line-height: 1.05; }
  .fp-hero-sub { font-size: 0.78rem; color: rgba(243,239,234,0.3); max-width: 240px; line-height: 1.4; }

  .fp-hero-chart { display: flex; flex-direction: column; justify-content: center; gap: 16px; position: relative; z-index: 1; }
  .fp-bar-row { display: flex; align-items: center; gap: 12px; }
  .fp-bar-icon { flex-shrink: 0; display: flex; }
  .fp-bar-icon.red  { color: #F07A64; }
  .fp-bar-icon.gold { color: #D4A820; }
  .fp-bar-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 5px; }
  .fp-bar-top { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
  .fp-bar-label { font-size: 0.76rem; font-weight: 600; color: rgba(243,239,234,0.55); }
  .fp-bar-val { font-size: 0.85rem; font-weight: 800; font-variant-numeric: tabular-nums; flex-shrink: 0; }
  .fp-bar-val.red  { color: #F07A64; }
  .fp-bar-val.gold { color: #D4A820; }
  .fp-bar-track { height: 7px; border-radius: 4px; background: rgba(243,239,234,0.06); overflow: hidden; }
  .fp-bar-fill { height: 100%; border-radius: 4px; transition: width 0.6s ease; }
  .fp-bar-fill.red  { background: linear-gradient(90deg, #F07A64, #F0A090); }
  .fp-bar-fill.gold { background: linear-gradient(90deg, #D4A820, #F0C840); }

  /* Grid de cards */
  .fp-grid { display: flex; flex-direction: column; gap: 10px; }

  .fp-card {
    display: flex; align-items: center; gap: 16px;
    background: #100E0B;
    border: 1px solid rgba(243,239,234,0.07);
    border-left: 3px solid transparent;
    border-radius: 12px;
    padding: 16px 20px;
    transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
    cursor: default;
  }
  .fp-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 24px rgba(0,0,0,0.35);
  }
  .fp-card.alert { border-left-color: #F07A64; }
  .fp-card.warn  { border-left-color: #ECB040; }
  .fp-card.good  { border-left-color: #2EC8A4; }
  .fp-card.gold  { border-left-color: #D4A820; }
  .fp-card.info  { border-left-color: #60B0F2; }

  .fp-card-icon { flex-shrink: 0; display: flex; }
  .fp-card.alert .fp-card-icon { color: #F07A64; }
  .fp-card.warn  .fp-card-icon { color: #ECB040; }
  .fp-card.good  .fp-card-icon { color: #2EC8A4; }
  .fp-card.gold  .fp-card-icon { color: #D4A820; }
  .fp-card.info  .fp-card-icon { color: #60B0F2; }

  .fp-card-body { flex: 1; min-width: 0; }
  .fp-card-title { font-size: 0.9rem; font-weight: 700; color: #F3EFEA; margin-bottom: 3px; }
  .fp-card-desc  { font-size: 0.74rem; color: rgba(243,239,234,0.32); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  .fp-card-right { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; flex-shrink: 0; }
  .fp-card-amount { font-size: 0.98rem; font-weight: 800; font-variant-numeric: tabular-nums; letter-spacing: -0.02em; }
  .fp-card.alert .fp-card-amount { color: #F07A64; }
  .fp-card.warn  .fp-card-amount { color: #ECB040; }
  .fp-card.good  .fp-card-amount { color: #2EC8A4; }
  .fp-card.gold  .fp-card-amount { color: #D4A820; }
  .fp-card.info  .fp-card-amount { color: #60B0F2; }

  .fp-chip { display: inline-block; font-size: 0.64rem; font-weight: 800; letter-spacing: 0.05em; white-space: nowrap; }
  .fp-card.alert .fp-chip { color: #F07A64; }
  .fp-card.warn  .fp-chip { color: #ECB040; }
  .fp-card.good  .fp-chip { color: #2EC8A4; }
  .fp-card.gold  .fp-chip { color: #D4A820; }
  .fp-card.info  .fp-chip { color: #60B0F2; }

  .fp-section-label { font-size: 0.68rem; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; color: rgba(243,239,234,0.4); margin: 4px 0 2px; }

  /* Alertas e Oportunidades lado a lado — dá pra ver as duas sem rolar */
  .fp-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; align-items: start; }
  .fp-columns.single { grid-template-columns: 1fr; }
  .fp-column { display: flex; flex-direction: column; gap: 8px; min-width: 0; }

  /* Demo banner — texto simples, sem caixa */
  .fp-demo { display: flex; align-items: center; gap: 8px; font-size: 0.73rem; color: rgba(243,239,234,0.35); font-style: italic; padding: 2px 2px; }
  .fp-demo-dot { width: 5px; height: 5px; border-radius: 2px; background: #D4A820; flex-shrink: 0; }

  /* Empty state */
  .fp-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 48px 16px; gap: 8px; background: #100E0B; border: 1px solid rgba(243,239,234,0.07); border-radius: 14px; }
  .fp-empty-icon { color: rgba(243,239,234,0.3); margin-bottom: 2px; }
  .fp-empty-title { font-size: 0.9rem; font-weight: 700; color: rgba(243,239,234,0.5); }
  .fp-empty-sub { font-size: 0.78rem; color: rgba(243,239,234,0.28); max-width: 320px; line-height: 1.6; }

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
    .fp-hero { grid-template-columns: 1fr; }
    .fp-columns { grid-template-columns: 1fr; }
    .fp-cta { flex-direction: column; align-items: flex-start; }
    .fp-cta-btn { width: 100%; text-align: center; }
  }
`;

type CardType = 'alert' | 'warn' | 'good' | 'gold' | 'info';

interface FeedCard { type: CardType; title: string; desc: string; amount: string; tag: string; }

const DEMO_ALERTS: FeedCard[] = [
  { type: 'alert', title: 'Tarifa de manutenção cobrada',      desc: 'Nubank · Conta corrente · ago/25',      amount: '−R$ 35,00',   tag: 'RECORRENTE' },
  { type: 'alert', title: 'Tarifa de TED avulso',              desc: 'Itaú · 3 transferências este mês',        amount: '−R$ 21,90',   tag: 'EVITÁVEL' },
  { type: 'warn',  title: 'Anuidade de cartão se aproxima',    desc: 'Itaú Personnalité · próximo vencimento',   amount:  'R$ 580,00',   tag: 'EM 18 DIAS' },
  { type: 'warn',  title: 'Rendimento abaixo do CDI',          desc: 'Poupança Bradesco · saldo médio R$ 4.200', amount: '−R$ 142/mês',  tag: 'OPORTUNIDADE' },
];

const DEMO_OPP: FeedCard[] = [
  { type: 'gold', title: 'Cashback disponível não resgatado',  desc: 'Cartão Inter · Programa Duo Gourmet',      amount:  'R$ 78,00',   tag: 'DISPONÍVEL' },
  { type: 'good', title: 'CDB prefixado disponível',           desc: 'Nubank · venc. 3 meses · 14,5% a.a.',     amount: '+R$ 210/ano',  tag: 'RECOMENDADO' },
  { type: 'gold', title: 'Portabilidade de crédito',           desc: '3,2% a.m. atual → oferta 1,9% a.m.',      amount: '−R$ 380/mês',  tag: 'NOVA OFERTA' },
];

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapAlert(a: any): FeedCard {
  // A severidade vem em `level` (CRITICAL/WARNING/INFO); `type` é o tipo do
  // alerta (NEGATIVE_BALANCE…) e fazia todo alerta cair em "Oportunidades".
  const nivel = String(a.level || '').toUpperCase();
  const type: CardType = nivel === 'CRITICAL' ? 'alert' : nivel === 'WARNING' ? 'warn' : 'info';
  return { type, title: a.title || a.message, desc: a.message || '', amount: '', tag: '' };
}

function parseAmount(s: string): number {
  const m = s.replace(/\./g, '').match(/-?\d+(?:,\d+)?/);
  if (!m) return 0;
  return Math.abs(parseFloat(m[0].replace(',', '.')));
}

function fmtBRL(n: number) {
  return `R$ ${n.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`;
}

// ─── Ícones por tipo de card (sem emoji, sem glifo unicode solto) ────────────
function TypeIcon({ type }: { type: CardType }) {
  switch (type) {
    case 'alert':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <path d="M12 3v10M12 21a1.4 1.4 0 1 1 0-2.8A1.4 1.4 0 0 1 12 21Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
        </svg>
      );
    case 'warn':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8"/>
          <path d="M12 7.5v5.2l3.2 1.9" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      );
    case 'good':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <path d="M4 15l5-5 4 4 7-8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M15 6h5v5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      );
    case 'gold':
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="1.8"/>
          <path d="M12 8v8M9.5 10a2.5 2 0 0 1 2.5-1.5c1.4 0 2.5.7 2.5 1.7s-1.1 1.4-2.5 1.8c-1.4.4-2.5.9-2.5 1.8 0 1 1.1 1.7 2.5 1.7a2.5 2 0 0 0 2.5-1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
        </svg>
      );
    default:
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8"/>
          <path d="M12 11v5.5M12 7.8v.1" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
        </svg>
      );
  }
}

export const FeedPage: React.FC = () => {
  const navigate = useNavigate();
  const userId = localStorage.getItem('user_id') || '';

  const alertsQ = useQuery({
    queryKey: ['alerts', userId],
    queryFn: () => nexaApi.getAlerts(userId),
    enabled: !!userId, retry: 1, staleTime: 2 * 60 * 1000,
  });

  const demo = isDemoMode(userId);
  const loading = alertsQ.isLoading;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const realAlerts: FeedCard[] = (alertsQ.data?.alerts || []).map((a: any) => mapAlert(a));
  const hasReal = realAlerts.length > 0;
  const showDemo = !hasReal && demo;
  const showEmpty = !hasReal && !demo;

  const alerts = hasReal ? realAlerts.filter(c => c.type === 'alert' || c.type === 'warn') : showDemo ? DEMO_ALERTS : [];
  const opps   = hasReal ? realAlerts.filter(c => c.type === 'good' || c.type === 'gold' || c.type === 'info') : showDemo ? DEMO_OPP : [];

  const alertsTotal = alerts.reduce((s, a) => s + parseAmount(a.amount), 0);
  const oppsTotal   = opps.reduce((s, a) => s + parseAmount(a.amount), 0);
  const barMax = Math.max(alertsTotal, oppsTotal, 1);

  return (
    <AppShell current="feed">
      <style>{css}</style>
      <div className="fp">

        {/* Topo */}
        <div className="fp-top">
          <div>
            <div className="fp-eyebrow">Feed de Oportunidades</div>
            <div className="fp-title">O que o banco<br />não te <em>conta</em>.</div>
          </div>
        </div>

        {!loading && !showEmpty && (
          <div className="fp-hero">
            <div className="fp-hero-main">
              <span className="fp-hero-label">Identificado este mês</span>
              <span className="fp-hero-value">{fmtBRL(alertsTotal + oppsTotal)}</span>
              <span className="fp-hero-sub">em tarifas evitáveis e oportunidades que você ainda não aproveitou.</span>
            </div>
            <div className="fp-hero-chart">
              <div className="fp-bar-row">
                <div className="fp-bar-icon red"><TypeIcon type="alert" /></div>
                <div className="fp-bar-main">
                  <div className="fp-bar-top">
                    <span className="fp-bar-label">Perdido em tarifas</span>
                    <span className="fp-bar-val red">{fmtBRL(alertsTotal)}</span>
                  </div>
                  <div className="fp-bar-track"><div className="fp-bar-fill red" style={{ width: `${Math.round((alertsTotal / barMax) * 100)}%` }} /></div>
                </div>
              </div>
              <div className="fp-bar-row">
                <div className="fp-bar-icon gold"><TypeIcon type="gold" /></div>
                <div className="fp-bar-main">
                  <div className="fp-bar-top">
                    <span className="fp-bar-label">Oportunidades disponíveis</span>
                    <span className="fp-bar-val gold">{fmtBRL(oppsTotal)}</span>
                  </div>
                  <div className="fp-bar-track"><div className="fp-bar-fill gold" style={{ width: `${Math.round((oppsTotal / barMax) * 100)}%` }} /></div>
                </div>
              </div>
            </div>
          </div>
        )}

        {showDemo && !loading && (
          <div className="fp-demo">
            <div className="fp-demo-dot" />
            Modo demonstração — desative em Perfil para ver o estado real.
          </div>
        )}

        {loading ? (
          <div className="fp-grid">
            {[1,2,3,4,5].map(i => <div key={i} className="fp-skel" style={{ height: 72 }} />)}
          </div>
        ) : showEmpty ? (
          <div className="fp-empty">
            <svg className="fp-empty-icon" width="30" height="30" viewBox="0 0 24 24" fill="none">
              <circle cx="10.5" cy="10.5" r="6.5" stroke="currentColor" strokeWidth="1.6"/>
              <path d="M20 20l-4.8-4.8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
            </svg>
            <div className="fp-empty-title">Nenhum alerta ou oportunidade ainda</div>
            <div className="fp-empty-sub">Conecte seu banco pra o HIVE analisar suas tarifas, assinaturas e oportunidades reais.</div>
          </div>
        ) : (
          <div className={`fp-columns${alerts.length > 0 && opps.length > 0 ? '' : ' single'}`}>
            {alerts.length > 0 && (
              <div className="fp-column">
                <div className="fp-section-label">Alertas</div>
                <div className="fp-grid">
                  {alerts.map((o, i) => (
                    <div key={i} className={`fp-card ${o.type}`}>
                      <div className="fp-card-icon"><TypeIcon type={o.type} /></div>
                      <div className="fp-card-body">
                        <div className="fp-card-title">{o.title}</div>
                        {o.desc && <div className="fp-card-desc">{o.desc}</div>}
                      </div>
                      {(o.amount || o.tag) && (
                        <div className="fp-card-right">
                          {o.amount && <div className="fp-card-amount">{o.amount}</div>}
                          {o.tag    && <span className="fp-chip">{o.tag}</span>}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {opps.length > 0 && (
              <div className="fp-column">
                <div className="fp-section-label">Oportunidades</div>
                <div className="fp-grid">
                  {opps.map((o, i) => (
                    <div key={i} className={`fp-card ${o.type}`}>
                      <div className="fp-card-icon"><TypeIcon type={o.type} /></div>
                      <div className="fp-card-body">
                        <div className="fp-card-title">{o.title}</div>
                        {o.desc && <div className="fp-card-desc">{o.desc}</div>}
                      </div>
                      {(o.amount || o.tag) && (
                        <div className="fp-card-right">
                          {o.amount && <div className="fp-card-amount">{o.amount}</div>}
                          {o.tag    && <span className="fp-chip">{o.tag}</span>}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        <div className="fp-cta">
          <div>
            <div className="fp-cta-text">Conecte seu banco para alertas reais</div>
            <div className="fp-cta-sub">Open Finance · leitura apenas · criptografado</div>
          </div>
          <button className="fp-cta-btn" onClick={() => navigate('/connections')}>Conectar banco →</button>
        </div>
      </div>
    </AppShell>
  );
};
