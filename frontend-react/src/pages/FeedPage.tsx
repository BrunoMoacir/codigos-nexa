import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { nexaApi } from '../api/nexa';
import { isDemoMode } from '../utils/demoMode';

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

  /* Demo banner */
  .fp-demo { display: flex; align-items: center; gap: 8px; background: rgba(212,168,32,0.06); border: 1px solid rgba(212,168,32,0.13); border-radius: 10px; padding: 9px 14px; font-size: 0.73rem; color: rgba(243,239,234,0.4); }
  .fp-demo-dot { width: 5px; height: 5px; border-radius: 50%; background: #D4A820; flex-shrink: 0; }

  /* Empty state */
  .fp-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 48px 16px; gap: 8px; background: #100E0B; border: 1px solid rgba(243,239,234,0.07); border-radius: 14px; }
  .fp-empty-icon { font-size: 1.7rem; opacity: 0.25; margin-bottom: 2px; }
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
    .fp-cta { flex-direction: column; align-items: flex-start; }
    .fp-cta-btn { width: 100%; text-align: center; }
  }
`;

type CardType = 'alert' | 'warn' | 'good' | 'gold' | 'info';

interface FeedCard { type: CardType; icon: string; title: string; desc: string; amount: string; tag: string; }

const DEMO_ALERTS: FeedCard[] = [
  { type: 'alert', icon: '↯', title: 'Tarifa de manutenção cobrada',      desc: 'Nubank · Conta corrente · ago/25',      amount: '−R$ 35,00',   tag: 'RECORRENTE' },
  { type: 'alert', icon: '↯', title: 'Tarifa de TED avulso',              desc: 'Itaú · 3 transferências este mês',        amount: '−R$ 21,90',   tag: 'EVITÁVEL' },
  { type: 'warn',  icon: '◔', title: 'Anuidade de cartão se aproxima',    desc: 'Itaú Personnalité · próximo vencimento',   amount:  'R$ 580,00',   tag: 'EM 18 DIAS' },
  { type: 'warn',  icon: '↓', title: 'Rendimento abaixo do CDI',          desc: 'Poupança Bradesco · saldo médio R$ 4.200', amount: '−R$ 142/mês',  tag: 'OPORTUNIDADE' },
];

const DEMO_OPP: FeedCard[] = [
  { type: 'gold', icon: '✦', title: 'Cashback disponível não resgatado',  desc: 'Cartão Inter · Programa Duo Gourmet',      amount:  'R$ 78,00',   tag: 'DISPONÍVEL' },
  { type: 'good', icon: '↑', title: 'CDB prefixado disponível',           desc: 'Nubank · venc. 3 meses · 14,5% a.a.',     amount: '+R$ 210/ano',  tag: 'RECOMENDADO' },
  { type: 'gold', icon: '◈', title: 'Portabilidade de crédito',           desc: '3,2% a.m. atual → oferta 1,9% a.m.',      amount: '−R$ 380/mês',  tag: 'NOVA OFERTA' },
];

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapAlert(a: any): FeedCard {
  const t = (a.type || '').toLowerCase();
  const type: CardType = t === 'danger' ? 'alert' : t === 'warning' ? 'warn' : t === 'success' ? 'good' : 'info';
  return { type, icon: type === 'alert' ? '↯' : type === 'warn' ? '◔' : '↑', title: a.title || a.message, desc: a.message || '', amount: '', tag: '' };
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

  const totalAlerts = alerts.length;
  const totalOpps   = opps.length;

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
          {!loading && (
            <div className="fp-top-kpis">
              <div className="fp-mini-kpi">
                <div className="fp-mini-val red">{totalAlerts}</div>
                <div className="fp-mini-label">Alertas</div>
              </div>
              <div className="fp-mini-kpi">
                <div className="fp-mini-val gold">{totalOpps}</div>
                <div className="fp-mini-label">Oportunidades</div>
              </div>
              <div className="fp-mini-kpi">
                <div className="fp-mini-val dim">{totalAlerts + totalOpps}</div>
                <div className="fp-mini-label">Total</div>
              </div>
            </div>
          )}
        </div>

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
            <div className="fp-empty-icon">🔍</div>
            <div className="fp-empty-title">Nenhum alerta ou oportunidade ainda</div>
            <div className="fp-empty-sub">Conecte seu banco pra o HIVE analisar suas tarifas, assinaturas e oportunidades reais.</div>
          </div>
        ) : (
          <>
            {alerts.length > 0 && (
              <>
                <div className="fp-section-label">Alertas</div>
                <div className="fp-grid">
                  {alerts.map((o, i) => (
                    <div key={i} className={`fp-card ${o.type}`}>
                      <div className="fp-card-icon">{o.icon}</div>
                      <div className="fp-card-body">
                        <div className="fp-card-title">{o.title}</div>
                        {o.desc && <div className="fp-card-desc">{o.desc}</div>}
                      </div>
                      {(o.amount || o.tag) && (
                        <div className="fp-card-right">
                          {o.amount && <div className="fp-card-amount">{o.amount}</div>}
                          {o.tag    && <div className="fp-card-tag">{o.tag}</div>}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </>
            )}

            {opps.length > 0 && (
              <>
                <div className="fp-section-label">Oportunidades</div>
                <div className="fp-grid">
                  {opps.map((o, i) => (
                    <div key={i} className={`fp-card ${o.type}`}>
                      <div className="fp-card-icon">{o.icon}</div>
                      <div className="fp-card-body">
                        <div className="fp-card-title">{o.title}</div>
                        {o.desc && <div className="fp-card-desc">{o.desc}</div>}
                      </div>
                      {(o.amount || o.tag) && (
                        <div className="fp-card-right">
                          {o.amount && <div className="fp-card-amount">{o.amount}</div>}
                          {o.tag    && <div className="fp-card-tag">{o.tag}</div>}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </>
            )}
          </>
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
