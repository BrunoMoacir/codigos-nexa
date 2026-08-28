import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { nexaApi } from '../api/nexa';

const css = `
  .fp { padding: 28px 32px; min-height: 100vh; background: #0E0C0A; }
  .fp-header { margin-bottom: 28px; }
  .fp-eyebrow { font-size: 0.67rem; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: #D4A820; margin-bottom: 8px; }
  .fp-title { font-size: 1.4rem; font-weight: 800; color: #F3EFEA; letter-spacing: -0.025em; margin-bottom: 4px; }
  .fp-sub { font-size: 0.8rem; color: rgba(243,239,234,0.3); }

  .fp-summary { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 32px; }
  .fp-kpi { background: rgba(243,239,234,0.03); border: 1px solid rgba(243,239,234,0.07); border-radius: 12px; padding: 16px 18px; }
  .fp-kpi-val { font-size: 1.35rem; font-weight: 800; letter-spacing: -0.035em; color: #F3EFEA; margin-bottom: 4px; font-variant-numeric: tabular-nums; }
  .fp-kpi-val.gold { color: #D4A820; }
  .fp-kpi-val.danger { color: #F07A64; }
  .fp-kpi-label { font-size: 0.7rem; color: rgba(243,239,234,0.3); font-weight: 500; }

  .fp-section-title { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: rgba(243,239,234,0.35); margin-bottom: 12px; }
  .fp-cards { display: flex; flex-direction: column; gap: 10px; margin-bottom: 32px; }

  .fp-card { background: rgba(243,239,234,0.03); border: 1px solid rgba(243,239,234,0.07); border-radius: 14px; padding: 18px 20px; display: flex; align-items: center; gap: 16px; cursor: default; transition: background 0.15s, border-color 0.15s; }
  .fp-card:hover { background: rgba(243,239,234,0.05); border-color: rgba(243,239,234,0.12); }
  .fp-card.alert { border-left: 3px solid #F07A64; }
  .fp-card.warn  { border-left: 3px solid #ECB040; }
  .fp-card.good  { border-left: 3px solid #2EC8A4; }
  .fp-card.gold  { border-left: 3px solid #D4A820; }
  .fp-card.info  { border-left: 3px solid #60B0F2; }

  .fp-card-icon { width: 40px; height: 40px; border-radius: 10px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; font-size: 1.1rem; }
  .fp-card.alert .fp-card-icon { background: rgba(240,122,100,0.1); }
  .fp-card.warn  .fp-card-icon { background: rgba(236,176,64,0.1); }
  .fp-card.good  .fp-card-icon { background: rgba(46,200,164,0.1); }
  .fp-card.gold  .fp-card-icon { background: rgba(212,168,32,0.1); }
  .fp-card.info  .fp-card-icon { background: rgba(96,176,242,0.1); }

  .fp-card-body { flex: 1; min-width: 0; }
  .fp-card-title { font-size: 0.88rem; font-weight: 600; color: #F3EFEA; margin-bottom: 3px; }
  .fp-card-desc { font-size: 0.75rem; color: rgba(243,239,234,0.35); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  .fp-card-right { text-align: right; flex-shrink: 0; }
  .fp-card-amount { font-size: 0.95rem; font-weight: 700; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
  .fp-card.alert .fp-card-amount { color: #F07A64; }
  .fp-card.warn  .fp-card-amount { color: #ECB040; }
  .fp-card.good  .fp-card-amount { color: #2EC8A4; }
  .fp-card.gold  .fp-card-amount { color: #D4A820; }
  .fp-card.info  .fp-card-amount { color: #60B0F2; }
  .fp-card-tag { font-size: 0.65rem; color: rgba(243,239,234,0.25); margin-top: 2px; }

  /* Skeleton */
  .fp-skel { background: rgba(243,239,234,0.05); border-radius: 14px; height: 76px; animation: fp-pulse 1.4s ease-in-out infinite; }
  @keyframes fp-pulse { 0%,100%{opacity:0.4} 50%{opacity:0.8} }

  /* Banner demo */
  .fp-demo-banner {
    display: flex; align-items: center; gap: 10px;
    background: rgba(212,168,32,0.07);
    border: 1px solid rgba(212,168,32,0.15);
    border-radius: 10px; padding: 10px 16px;
    margin-bottom: 20px; font-size: 0.75rem;
    color: rgba(243,239,234,0.5);
  }
  .fp-demo-dot { width: 6px; height: 6px; border-radius: 50%; background: #D4A820; flex-shrink: 0; }

  /* Connect CTA */
  .fp-connect { background: rgba(212,168,32,0.06); border: 1px solid rgba(212,168,32,0.15); border-radius: 14px; padding: 24px; display: flex; align-items: center; justify-content: space-between; gap: 20px; }
  .fp-connect-label { font-size: 0.95rem; font-weight: 700; color: #F3EFEA; margin-bottom: 4px; }
  .fp-connect-sub { font-size: 0.75rem; color: rgba(243,239,234,0.35); }
  .fp-connect-btn { padding: 10px 20px; background: #D4A820; color: #0C0A08; border: none; border-radius: 9px; font-family: inherit; font-size: 0.82rem; font-weight: 800; letter-spacing: 0.03em; cursor: pointer; white-space: nowrap; transition: background 0.15s; flex-shrink: 0; }
  .fp-connect-btn:hover { background: #E8C030; }

  @media (max-width: 860px) {
    .fp { padding: 20px 16px; }
    .fp-summary { grid-template-columns: repeat(2, 1fr); }
    .fp-connect { flex-direction: column; align-items: flex-start; }
    .fp-connect-btn { width: 100%; text-align: center; }
  }
`;

type CardType = 'alert' | 'warn' | 'good' | 'gold' | 'info';

interface FeedCard {
  type: CardType;
  icon: string;
  title: string;
  desc: string;
  amount: string;
  tag: string;
}

const DEMO_CARDS: FeedCard[] = [
  { type: 'alert', icon: '⚠', title: 'Tarifa de manutenção cobrada',     desc: 'Nubank · Conta corrente',          amount: '−R$ 35,00',  tag: 'Recorrente' },
  { type: 'alert', icon: '⚠', title: 'Tarifa de TED avulso',             desc: 'Itaú · 3 transferências este mês', amount: '−R$ 21,90',  tag: 'Evitável' },
  { type: 'warn',  icon: '↓',  title: 'Rendimento abaixo do CDI',         desc: 'Poupança · Saldo médio R$ 4.200',  amount: '−R$ 142/mês',tag: 'Oportunidade' },
  { type: 'gold',  icon: '✦',  title: 'Cashback disponível não resgatado',desc: 'Cartão Inter · Duo Gourmet',       amount: 'R$ 78,00',   tag: 'Disponível agora' },
  { type: 'good',  icon: '↑',  title: 'CDB prefixado em aberto',          desc: 'Nubank · Venc. em 3 meses · 14,5% a.a.', amount: '+R$ 210/ano', tag: 'Recomendado' },
  { type: 'warn',  icon: '⧖',  title: 'Anuidade de cartão se aproxima',  desc: 'Itaú Personnalité',                amount: 'R$ 580,00',  tag: 'Em 18 dias' },
  { type: 'gold',  icon: '◈',  title: 'Portabilidade de crédito',         desc: '3,2% a.m. → oferta 1,9% a.m.',    amount: '−R$ 380/mês',tag: 'Nova oferta' },
];

function mapAlertType(t: string): CardType {
  if (t === 'danger' || t === 'error') return 'alert';
  if (t === 'warning') return 'warn';
  if (t === 'success') return 'good';
  if (t === 'info') return 'info';
  return 'warn';
}

function mapAlertIcon(t: string): string {
  if (t === 'danger' || t === 'error') return '⚠';
  if (t === 'warning') return '↓';
  if (t === 'success') return '↑';
  return 'ℹ';
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapNotifType(n: any): CardType {
  const sev = (n.severity || n.type || '').toLowerCase();
  if (sev === 'critical' || sev === 'danger') return 'alert';
  if (sev === 'warning' || sev === 'warn') return 'warn';
  if (sev === 'opportunity' || sev === 'good') return 'good';
  if (sev === 'info') return 'info';
  return 'gold';
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapNotifIcon(n: any): string {
  const sev = (n.severity || n.type || '').toLowerCase();
  if (sev === 'critical' || sev === 'danger') return '⚠';
  if (sev === 'opportunity' || sev === 'good') return '↑';
  return '✦';
}

function fmt(v: number | undefined) {
  if (!v) return '';
  return `R$ ${Math.abs(v).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`;
}

export const FeedPage: React.FC = () => {
  const navigate = useNavigate();
  const userId = localStorage.getItem('user_id') || '';

  const alertsQ = useQuery({
    queryKey: ['alerts', userId],
    queryFn: () => nexaApi.getAlerts(userId),
    enabled: !!userId,
    retry: 1,
    staleTime: 2 * 60 * 1000,
  });

  const notifsQ = useQuery({
    queryKey: ['notifications', userId],
    queryFn: () => nexaApi.getNotifications(userId),
    enabled: !!userId,
    retry: 1,
    staleTime: 2 * 60 * 1000,
  });

  const loading = alertsQ.isLoading || notifsQ.isLoading;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const realAlerts: FeedCard[] = (alertsQ.data?.alerts || []).map((a: any) => ({
    type: mapAlertType(a.type),
    icon: mapAlertIcon(a.type),
    title: a.title || a.message || 'Alerta',
    desc: a.message || a.description || '',
    amount: a.amount ? fmt(a.amount) : '',
    tag: a.category || a.tag || '',
  }));

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const rawNotifs: any[] = notifsQ.data?.notifications || notifsQ.data?.items || notifsQ.data || [];
  const realNotifs: FeedCard[] = (Array.isArray(rawNotifs) ? rawNotifs : []).map(n => ({
    type: mapNotifType(n),
    icon: mapNotifIcon(n),
    title: n.title || n.message || 'Notificação',
    desc: n.description || n.detail || n.message || '',
    amount: n.impact_brl ? `R$ ${Math.abs(n.impact_brl).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}` : '',
    tag: n.category || n.tag || '',
  }));

  const realCards = [...realAlerts, ...realNotifs];
  const hasReal = realCards.length > 0;
  const cards = hasReal ? realCards : DEMO_CARDS;
  const isDemo = !hasReal && !loading;

  const alertCount = realAlerts.filter(c => c.type === 'alert').length;
  const warnCount  = realAlerts.filter(c => c.type === 'warn').length;

  return (
    <AppShell current="feed">
      <style>{css}</style>
      <div className="fp">
        <div className="fp-header">
          <div className="fp-eyebrow">Feed de Oportunidades</div>
          <div className="fp-title">O que o banco não te conta</div>
          <div className="fp-sub">{hasReal ? 'Dados reais da sua conta.' : 'Atualizado em tempo real com seus dados financeiros.'}</div>
        </div>

        <div className="fp-summary">
          <div className="fp-kpi">
            <div className="fp-kpi-val danger">{hasReal ? alertCount + warnCount : 7}</div>
            <div className="fp-kpi-label">Alertas ativos</div>
          </div>
          <div className="fp-kpi">
            <div className="fp-kpi-val gold">{hasReal ? realCards.filter(c => c.type === 'good' || c.type === 'gold').length : 3}</div>
            <div className="fp-kpi-label">Oportunidades</div>
          </div>
          <div className="fp-kpi">
            <div className="fp-kpi-val">{hasReal ? realCards.length : DEMO_CARDS.length}</div>
            <div className="fp-kpi-label">Total no feed</div>
          </div>
        </div>

        {isDemo && (
          <div className="fp-demo-banner">
            <div className="fp-demo-dot" />
            Demonstração — conecte seu banco para ver seus alertas reais.
          </div>
        )}

        {loading ? (
          <div className="fp-cards">
            {[1,2,3,4].map(i => <div key={i} className="fp-skel" />)}
          </div>
        ) : (
          <>
            <div className="fp-section-title">Alertas e oportunidades</div>
            <div className="fp-cards">
              {cards.map((o, i) => (
                <div key={i} className={`fp-card ${o.type}`}>
                  <div className="fp-card-icon">{o.icon}</div>
                  <div className="fp-card-body">
                    <div className="fp-card-title">{o.title}</div>
                    {o.desc && <div className="fp-card-desc">{o.desc}</div>}
                  </div>
                  {(o.amount || o.tag) && (
                    <div className="fp-card-right">
                      {o.amount && <div className="fp-card-amount">{o.amount}</div>}
                      {o.tag   && <div className="fp-card-tag">{o.tag}</div>}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </>
        )}

        <div className="fp-connect">
          <div>
            <div className="fp-connect-label">Conecte seu banco para análise completa</div>
            <div className="fp-connect-sub">Via Open Finance · Leitura apenas · Dados criptografados</div>
          </div>
          <button className="fp-connect-btn" onClick={() => navigate('/connections')}>
            Conectar banco →
          </button>
        </div>
      </div>
    </AppShell>
  );
};
