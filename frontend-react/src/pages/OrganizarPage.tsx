import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { nexaApi } from '../api/nexa';
import { isDemoMode } from '../utils/demoMode';
import type { Transaction, Goal, CreditCard } from '../api/types';

// ─── Sparkline SVG ────────────────────────────────────────────────────────────
function AreaChart({ data, color = '#D4A820', h = 80 }: { data: number[]; color?: string; h?: number }) {
  if (!data.length) return null;
  const w = 400;
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const range = max - min || 1;
  const pad = 8;
  const pts = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (w - pad * 2);
    const y = h - pad - ((v - min) / range) * (h - pad * 2);
    return `${x},${y}`;
  });
  const linePath = `M ${pts.join(' L ')}`;
  const areaPath = `M ${pad},${h - pad} L ${pts.join(' L ')} L ${w - pad},${h - pad} Z`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: '100%', height: h, display: 'block' }} preserveAspectRatio="none">
      <defs>
        <linearGradient id="ag" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.22" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill="url(#ag)" />
      <path d={linePath} fill="none" stroke={color} strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

// ─── Empty state (honesto — sem banco conectado, sem modo demo) ──────────────
function EmptyPanel({ icon, title, sub }: { icon: string; title: string; sub: string }) {
  return (
    <div className="op-empty">
      <div className="op-empty-icon">{icon}</div>
      <div className="op-empty-title">{title}</div>
      <div className="op-empty-sub">{sub}</div>
    </div>
  );
}

// ─── Cartão de crédito visual ─────────────────────────────────────────────────
function CardVisual({ card }: { card: { bank_name?: string | null; brand?: string | null; last4?: string | null; credit_limit?: number | null; available_credit_limit?: number | null } }) {
  return (
    <div className="op-card-visual">
      <div className="op-card-visual-top">
        <span className="op-card-visual-bank">{card.bank_name || 'Cartão'}</span>
        <span className="op-card-visual-brand">{(card.brand || 'CARTÃO').toUpperCase()}</span>
      </div>
      <div className="op-card-visual-number">•••• •••• •••• {card.last4 || '····'}</div>
      <div className="op-card-visual-bottom">
        <div>
          <div className="op-card-visual-label">Disponível</div>
          <div className="op-card-visual-val">{fmtBRL(card.available_credit_limit ?? 0)}</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div className="op-card-visual-label">Limite total</div>
          <div className="op-card-visual-val">{fmtBRL(card.credit_limit ?? 0)}</div>
        </div>
      </div>
    </div>
  );
}

const css = `
  .op { display: flex; flex-direction: column; min-height: 100vh; background: #0A0806; padding: 28px 28px 40px; gap: 20px; }

  /* KPIs */
  .op-kpis { display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; }
  .op-kpi {
    background: #100E0B;
    border: 1px solid rgba(243,239,234,0.07);
    border-radius: 14px;
    padding: 18px 20px;
    display: flex; flex-direction: column; gap: 6px;
  }
  .op-kpi-label { font-size: 0.67rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: rgba(243,239,234,0.28); }
  .op-kpi-val { font-size: 1.55rem; font-weight: 800; letter-spacing: -0.04em; font-variant-numeric: tabular-nums; color: #F3EFEA; }
  .op-kpi-val.gold   { color: #D4A820; }
  .op-kpi-val.green  { color: #2EC8A4; }
  .op-kpi-val.red    { color: #F07A64; }
  .op-kpi-val.dim    { color: rgba(243,239,234,0.2); }
  .op-kpi-delta { font-size: 0.72rem; font-weight: 600; color: rgba(243,239,234,0.25); }
  .op-kpi-delta.up   { color: #2EC8A4; }
  .op-kpi-delta.down { color: #F07A64; }

  /* Row */
  .op-row { display: grid; grid-template-columns: 1fr 340px; gap: 14px; align-items: start; }
  .op-row.full { grid-template-columns: 1fr; }

  /* Panels */
  .op-panel {
    background: #100E0B;
    border: 1px solid rgba(243,239,234,0.07);
    border-radius: 16px;
    padding: 20px 22px;
    overflow: hidden;
  }
  .op-panel-head {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 18px;
  }
  .op-panel-title { font-size: 0.78rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: rgba(243,239,234,0.35); }
  .op-panel-badge { font-size: 0.68rem; font-weight: 700; color: #D4A820; background: rgba(212,168,32,0.1); border: 1px solid rgba(212,168,32,0.2); border-radius: 20px; padding: 2px 10px; }
  .op-panel-badge.demo { color: rgba(243,239,234,0.4); background: rgba(243,239,234,0.05); border-color: rgba(243,239,234,0.1); }

  /* Empty state */
  .op-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 30px 16px; gap: 6px; min-height: 120px; }
  .op-empty-icon { font-size: 1.5rem; opacity: 0.25; margin-bottom: 2px; }
  .op-empty-title { font-size: 0.84rem; font-weight: 700; color: rgba(243,239,234,0.5); }
  .op-empty-sub { font-size: 0.74rem; color: rgba(243,239,234,0.28); max-width: 240px; line-height: 1.5; }

  /* Chart x-axis labels */
  .op-chart-labels { display: flex; justify-content: space-between; margin-top: 6px; }
  .op-chart-label { font-size: 0.62rem; color: rgba(243,239,234,0.2); font-variant-numeric: tabular-nums; }

  /* Categorias */
  .op-cats { display: flex; flex-direction: column; gap: 12px; }
  .op-cat-row { display: flex; align-items: center; gap: 10px; }
  .op-cat-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
  .op-cat-name { font-size: 0.8rem; color: rgba(243,239,234,0.6); flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .op-cat-track { flex: 1.5; height: 4px; background: rgba(243,239,234,0.07); border-radius: 2px; overflow: hidden; }
  .op-cat-fill  { height: 100%; border-radius: 2px; }
  .op-cat-val   { font-size: 0.78rem; font-weight: 600; color: rgba(243,239,234,0.55); font-variant-numeric: tabular-nums; min-width: 64px; text-align: right; }

  /* Metas */
  .op-goals { display: flex; flex-direction: column; gap: 16px; }
  .op-goal-row { display: flex; flex-direction: column; gap: 6px; }
  .op-goal-top { display: flex; justify-content: space-between; align-items: center; }
  .op-goal-name { font-size: 0.82rem; font-weight: 600; color: #F3EFEA; }
  .op-goal-pct  { font-size: 0.72rem; font-weight: 800; color: #D4A820; }
  .op-goal-track { height: 6px; background: rgba(243,239,234,0.07); border-radius: 3px; overflow: hidden; }
  .op-goal-fill  { height: 100%; border-radius: 3px; background: linear-gradient(90deg, #D4A820, #F0C840); transition: width 0.6s ease; }
  .op-goal-sub   { font-size: 0.68rem; color: rgba(243,239,234,0.22); font-variant-numeric: tabular-nums; }

  /* Transações */
  .op-txn-list { display: flex; flex-direction: column; }
  .op-txn-row {
    display: flex; align-items: center; gap: 14px;
    padding: 11px 0;
    border-bottom: 1px solid rgba(243,239,234,0.05);
  }
  .op-txn-row:last-child { border-bottom: none; }
  .op-txn-icon {
    width: 34px; height: 34px; border-radius: 10px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.8rem; font-weight: 800;
  }
  .op-txn-icon.in  { background: rgba(46,200,164,0.12); color: #2EC8A4; }
  .op-txn-icon.out { background: rgba(240,122,100,0.1);  color: #F07A64; }
  .op-txn-info { flex: 1; min-width: 0; }
  .op-txn-desc { font-size: 0.83rem; font-weight: 600; color: #F3EFEA; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .op-txn-date { font-size: 0.68rem; color: rgba(243,239,234,0.25); margin-top: 1px; }
  .op-txn-val  { font-size: 0.88rem; font-weight: 700; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .op-txn-val.in  { color: #2EC8A4; }
  .op-txn-val.out { color: rgba(243,239,234,0.7); }

  /* Cartões */
  .op-cards-row { display: flex; gap: 14px; overflow-x: auto; padding-bottom: 4px; }
  .op-card-visual {
    min-width: 260px; flex: 1;
    max-width: 320px;
    border-radius: 16px;
    padding: 20px 22px;
    background: linear-gradient(135deg, #1C1610 0%, #2A2015 65%, #1C1610 100%);
    border: 1px solid rgba(212,168,32,0.25);
    position: relative;
    overflow: hidden;
    display: flex; flex-direction: column; gap: 24px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.35);
  }
  .op-card-visual::before {
    content: '';
    position: absolute; top: -50%; right: -25%;
    width: 200px; height: 200px; border-radius: 50%;
    background: radial-gradient(circle, rgba(212,168,32,0.16), transparent 70%);
    pointer-events: none;
  }
  .op-card-visual-top { display: flex; justify-content: space-between; align-items: flex-start; position: relative; }
  .op-card-visual-bank { font-size: 0.86rem; font-weight: 800; color: #F3EFEA; }
  .op-card-visual-brand { font-size: 0.66rem; font-weight: 700; letter-spacing: 0.08em; color: #D4A820; }
  .op-card-visual-number { font-size: 0.98rem; font-weight: 600; letter-spacing: 0.1em; color: rgba(243,239,234,0.75); font-variant-numeric: tabular-nums; position: relative; }
  .op-card-visual-bottom { display: flex; justify-content: space-between; align-items: flex-end; position: relative; }
  .op-card-visual-label { font-size: 0.6rem; text-transform: uppercase; letter-spacing: 0.06em; color: rgba(243,239,234,0.35); margin-bottom: 3px; }
  .op-card-visual-val { font-size: 0.9rem; font-weight: 800; color: #F3EFEA; font-variant-numeric: tabular-nums; }

  /* Connect CTA */
  .op-cta {
    display: flex; align-items: center; justify-content: space-between; gap: 20px;
    background: rgba(212,168,32,0.06);
    border: 1px solid rgba(212,168,32,0.14);
    border-radius: 14px; padding: 18px 22px;
  }
  .op-cta-text { font-size: 0.88rem; font-weight: 700; color: rgba(243,239,234,0.7); }
  .op-cta-sub  { font-size: 0.72rem; color: rgba(243,239,234,0.28); margin-top: 3px; }
  .op-cta-btn  { padding: 9px 18px; background: #D4A820; color: #0A0800; border: none; border-radius: 8px; font-family: inherit; font-size: 0.8rem; font-weight: 800; letter-spacing: 0.04em; cursor: pointer; white-space: nowrap; transition: background 0.15s; flex-shrink: 0; }
  .op-cta-btn:hover { background: #E8C030; }

  /* Skeleton */
  .op-skel { background: rgba(243,239,234,0.05); border-radius: 14px; animation: op-pulse 1.4s ease-in-out infinite; }
  @keyframes op-pulse { 0%,100%{opacity:0.35} 50%{opacity:0.7} }

  @media (max-width: 1024px) {
    .op-kpis { grid-template-columns: repeat(2,1fr); }
    .op-row  { grid-template-columns: 1fr; }
  }
  @media (max-width: 600px) {
    .op { padding: 16px 14px 32px; }
    .op-kpis { grid-template-columns: repeat(2,1fr); }
  }
`;

const CAT_COLORS = ['#D4A820','#2EC8A4','#60B0F2','#F07A64','#ECB040','#B088E0'];

const DEMO_SPEND = [3200, 2800, 3600, 3100, 4200, 3800, 4000, 3500, 3900, 4100, 3700, 4000];
const DEMO_MONTHS = ['Set','Out','Nov','Dez','Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago'];

const DEMO_CATS = [
  { name: 'Moradia',     color: '#D4A820', pct: 38, val: 'R$ 1.520' },
  { name: 'Alimentação', color: '#2EC8A4', pct: 22, val: 'R$  880' },
  { name: 'Transporte',  color: '#60B0F2', pct: 14, val: 'R$  560' },
  { name: 'Saúde',       color: '#F07A64', pct: 10, val: 'R$  400' },
  { name: 'Lazer',       color: '#ECB040', pct:  9, val: 'R$  360' },
  { name: 'Outros',      color: '#B088E0', pct:  7, val: 'R$  280' },
];

const DEMO_GOALS = [
  { name: 'Reserva de emergência', curr: 8400,  total: 15000 },
  { name: 'Viagem Europa',         curr: 3200,  total: 12000 },
  { name: 'Notebook novo',         curr: 1800,  total: 2500  },
];

const DEMO_TXNS = [
  { desc: 'Salário',       date: 'Hoje',   type: 'in',  val: '+R$ 6.200,00' },
  { desc: 'Aluguel',       date: 'Ontem',  type: 'out', val:  'R$ 1.400,00' },
  { desc: 'iFood',         date: '26 ago', type: 'out', val:    'R$  87,50' },
  { desc: 'Supermercado',  date: '25 ago', type: 'out', val:   'R$  312,00' },
  { desc: 'Freelance',     date: '24 ago', type: 'in',  val:  '+R$  800,00' },
  { desc: 'Netflix',       date: '22 ago', type: 'out', val:    'R$   55,90' },
  { desc: 'Farmácia',      date: '21 ago', type: 'out', val:    'R$   43,20' },
  { desc: 'Combustível',   date: '20 ago', type: 'out', val:   'R$  180,00' },
];

const DEMO_CARDS = [
  { bank_name: 'Nubank', brand: 'Mastercard', last4: '4532', credit_limit: 8500, available_credit_limit: 3180 },
  { bank_name: 'Itaú',   brand: 'Visa',        last4: '1187', credit_limit: 5000, available_credit_limit: 4260 },
];

function fmtBRL(n: number) {
  return `R$ ${Math.abs(n).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`;
}

function fmtDate(d: string) {
  try { return new Date(d).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' }); }
  catch { return d; }
}

function buildCats(txns: Transaction[]) {
  const map: Record<string, number> = {};
  for (const t of txns) {
    if (t.amount < 0 || t.type === 'expense') {
      const k = t.category || 'Outros';
      map[k] = (map[k] || 0) + Math.abs(t.amount);
    }
  }
  const entries = Object.entries(map).sort((a, b) => b[1] - a[1]).slice(0, 6);
  const total = entries.reduce((s, [, v]) => s + v, 0) || 1;
  return entries.map(([name, val], i) => ({
    name, color: CAT_COLORS[i] || '#947060',
    pct: Math.round((val / total) * 100), val: fmtBRL(val),
  }));
}

function buildSpend(txns: Transaction[]) {
  const map: Record<string, number> = {};
  for (const t of txns) {
    if (t.amount < 0 || t.type === 'expense') {
      const m = t.date?.slice(0, 7) || '';
      map[m] = (map[m] || 0) + Math.abs(t.amount);
    }
  }
  const vals = Object.values(map);
  return vals.length >= 2 ? vals.slice(-12) : [];
}

export const OrganizarPage: React.FC = () => {
  const navigate = useNavigate();
  const userId = localStorage.getItem('user_id') || '';
  const demo = isDemoMode(userId);

  const txnsQ = useQuery({
    queryKey: ['transactions', userId],
    queryFn: () => nexaApi.getTransactions(userId, 100),
    enabled: !!userId,
    retry: 1, staleTime: 2 * 60 * 1000,
  });

  const goalsQ = useQuery({
    queryKey: ['goals', userId],
    queryFn: () => nexaApi.getGoals(userId),
    enabled: !!userId,
    retry: 1, staleTime: 2 * 60 * 1000,
  });

  const cardsQ = useQuery({
    queryKey: ['cards', userId],
    queryFn: () => nexaApi.getCards(),
    enabled: !!userId,
    retry: 1, staleTime: 2 * 60 * 1000,
  });

  const loading = txnsQ.isLoading || goalsQ.isLoading || cardsQ.isLoading;
  const txns: Transaction[] = txnsQ.data?.transactions || [];
  const goals: Goal[] = goalsQ.data?.goals || [];
  const realCards: CreditCard[] = cardsQ.data || [];

  // "Real" aqui = banco conectado com transações sincronizadas. Metas e
  // cartões têm suas próprias fontes (goals é manual; cards vem do sync do
  // Pluggy) — cada seção decide sozinha entre real / demo / vazio honesto.
  const hasReal = txns.length > 0;
  const hasRealGoals = goals.length > 0;
  const hasRealCards = realCards.length > 0;
  const showDemo = !hasReal && demo;
  const showEmpty = !hasReal && !demo;

  const cats: { name: string; color: string; pct: number; val: string }[] =
    hasReal ? buildCats(txns) : showDemo ? DEMO_CATS : [];
  const spendData = hasReal ? buildSpend(txns) : showDemo ? DEMO_SPEND : [];
  const displayGoals = hasRealGoals ? goals : (!hasRealGoals && demo ? DEMO_GOALS : []);
  const displayCards: { bank_name?: string | null; brand?: string | null; last4?: string | null; credit_limit?: number | null; available_credit_limit?: number | null }[] =
    hasRealCards ? realCards : (!hasRealCards && demo ? DEMO_CARDS : []);

  const totalIn  = txns.filter(t => t.amount > 0 || t.type === 'income').reduce((s, t) => s + Math.abs(t.amount), 0);
  const totalOut = txns.filter(t => t.amount < 0 || t.type === 'expense').reduce((s, t) => s + Math.abs(t.amount), 0);
  const saldo    = totalIn - totalOut;

  const displayTxns = hasReal
    ? txns.slice(0, 8).map(t => ({
        desc: t.description,
        date: fmtDate(t.date),
        type: t.amount > 0 || t.type === 'income' ? 'in' : 'out',
        val:  (t.amount > 0 || t.type === 'income' ? '+' : '') + fmtBRL(t.amount),
      }))
    : showDemo ? DEMO_TXNS : [];

  return (
    <AppShell current="organizar">
      <style>{css}</style>
      <div className="op">

        {/* ── KPIs ── */}
        {loading ? (
          <div className="op-kpis">
            {[1,2,3,4].map(i => <div key={i} className="op-skel" style={{ height: 90 }} />)}
          </div>
        ) : (
          <div className="op-kpis">
            <div className="op-kpi">
              <span className="op-kpi-label">Receita</span>
              <span className={`op-kpi-val ${hasReal ? 'green' : showDemo ? 'green' : 'dim'}`}>
                {hasReal ? fmtBRL(totalIn) : showDemo ? 'R$ 7.000' : '—'}
              </span>
              <span className="op-kpi-delta up">{hasReal || showDemo ? '▲ este mês' : 'sem dados ainda'}</span>
            </div>
            <div className="op-kpi">
              <span className="op-kpi-label">Gastos</span>
              <span className={`op-kpi-val ${hasReal ? 'red' : showDemo ? 'red' : 'dim'}`}>
                {hasReal ? fmtBRL(totalOut) : showDemo ? 'R$ 4.000' : '—'}
              </span>
              <span className="op-kpi-delta down">{hasReal || showDemo ? '▼ vs mês anterior' : 'sem dados ainda'}</span>
            </div>
            <div className="op-kpi">
              <span className="op-kpi-label">Saldo</span>
              <span className={`op-kpi-val ${hasReal ? (saldo >= 0 ? 'green' : 'red') : showDemo ? 'gold' : 'dim'}`}>
                {hasReal ? fmtBRL(saldo) : showDemo ? 'R$ 3.000' : '—'}
              </span>
              <span className="op-kpi-delta">{hasReal || showDemo ? 'disponível agora' : 'sem dados ainda'}</span>
            </div>
            <div className="op-kpi">
              <span className="op-kpi-label">Taxa de poupança</span>
              <span className={`op-kpi-val ${hasReal || showDemo ? 'gold' : 'dim'}`}>
                {hasReal && totalIn ? `${Math.round((saldo / totalIn) * 100)}%` : showDemo ? '43%' : '—'}
              </span>
              <span className="op-kpi-delta up">{hasReal || showDemo ? '▲ acima da média' : 'sem dados ainda'}</span>
            </div>
          </div>
        )}

        {/* ── Gráfico + Categorias ── */}
        {!loading && (
          <div className="op-row">
            <div className="op-panel">
              <div className="op-panel-head">
                <span className="op-panel-title">Gastos mensais</span>
                {showDemo && <span className="op-panel-badge demo">exemplo</span>}
                {(hasReal || showDemo) && <span className="op-panel-badge">últimos 12 meses</span>}
              </div>
              {spendData.length > 0 ? (
                <>
                  <AreaChart data={spendData} color="#D4A820" h={120} />
                  <div className="op-chart-labels">
                    {DEMO_MONTHS.slice(-spendData.length).map(m => (
                      <span key={m} className="op-chart-label">{m}</span>
                    ))}
                  </div>
                </>
              ) : (
                <EmptyPanel icon="📈" title="Nenhum gasto registrado ainda" sub="Conecte seu banco pra ver a evolução dos seus gastos mês a mês." />
              )}
            </div>

            <div className="op-panel">
              <div className="op-panel-head">
                <span className="op-panel-title">Por categoria</span>
                {showDemo && <span className="op-panel-badge demo">exemplo</span>}
              </div>
              {cats.length > 0 ? (
                <div className="op-cats">
                  {cats.map(c => (
                    <div key={c.name} className="op-cat-row">
                      <div className="op-cat-dot" style={{ background: c.color }} />
                      <span className="op-cat-name">{c.name}</span>
                      <div className="op-cat-track">
                        <div className="op-cat-fill" style={{ width: `${c.pct}%`, background: c.color }} />
                      </div>
                      <span className="op-cat-val">{c.val}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyPanel icon="🏷" title="Sem categorias ainda" sub="Assim que suas transações chegarem, elas aparecem organizadas aqui." />
              )}
            </div>
          </div>
        )}

        {/* ── Cartões ── */}
        {!loading && (
          <div className="op-panel">
            <div className="op-panel-head">
              <span className="op-panel-title">Cartões</span>
              {showDemo && !hasRealCards && <span className="op-panel-badge demo">exemplo</span>}
              {(hasRealCards || (!hasRealCards && demo)) && <span className="op-panel-badge">{displayCards.length} {displayCards.length === 1 ? 'cartão' : 'cartões'}</span>}
            </div>
            {displayCards.length > 0 ? (
              <div className="op-cards-row">
                {displayCards.map((c, i) => <CardVisual key={i} card={c} />)}
              </div>
            ) : (
              <EmptyPanel icon="💳" title="Nenhum cartão conectado" sub="Conecte seu banco pra ver bandeira, limite e fatura dos seus cartões aqui." />
            )}
          </div>
        )}

        {/* ── Transações + Metas ── */}
        {!loading && (
          <div className="op-row">
            <div className="op-panel">
              <div className="op-panel-head">
                <span className="op-panel-title">Movimentações recentes</span>
                {showDemo && <span className="op-panel-badge demo">exemplo</span>}
                {displayTxns.length > 0 && <span className="op-panel-badge">{displayTxns.length} transações</span>}
              </div>
              {displayTxns.length > 0 ? (
                <div className="op-txn-list">
                  {displayTxns.map((t, i) => (
                    <div key={i} className="op-txn-row">
                      <div className={`op-txn-icon ${t.type}`}>{t.type === 'in' ? '↑' : '↓'}</div>
                      <div className="op-txn-info">
                        <div className="op-txn-desc">{t.desc}</div>
                        <div className="op-txn-date">{t.date}</div>
                      </div>
                      <div className={`op-txn-val ${t.type}`}>{t.val}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyPanel icon="↔" title="Nenhuma movimentação ainda" sub="Suas transações aparecem aqui assim que você conectar uma conta." />
              )}
            </div>

            <div className="op-panel">
              <div className="op-panel-head">
                <span className="op-panel-title">Metas</span>
                {!hasRealGoals && demo && <span className="op-panel-badge demo">exemplo</span>}
                {displayGoals.length > 0 && <span className="op-panel-badge">{displayGoals.length} ativas</span>}
              </div>
              {displayGoals.length > 0 ? (
                <div className="op-goals">
                  {displayGoals.map((g: Goal | typeof DEMO_GOALS[0]) => {
                    const curr  = 'current_amount' in g ? g.current_amount : (g as { curr: number }).curr;
                    const total = 'target_amount'  in g ? g.target_amount  : (g as { total: number }).total;
                    const pct   = Math.min(100, Math.round((curr / total) * 100));
                    return (
                      <div key={g.name} className="op-goal-row">
                        <div className="op-goal-top">
                          <span className="op-goal-name">{g.name}</span>
                          <span className="op-goal-pct">{pct}%</span>
                        </div>
                        <div className="op-goal-track">
                          <div className="op-goal-fill" style={{ width: `${pct}%` }} />
                        </div>
                        <div className="op-goal-sub">{fmtBRL(curr)} de {fmtBRL(total)}</div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <EmptyPanel icon="🎯" title="Nenhuma meta ainda" sub="Crie sua primeira meta financeira e acompanhe o progresso por aqui." />
              )}
            </div>
          </div>
        )}

        {/* ── CTA banco ── */}
        {showEmpty && !loading && (
          <div className="op-cta">
            <div>
              <div className="op-cta-text">Conecte seu banco para dados reais</div>
              <div className="op-cta-sub">Open Finance · leitura apenas · criptografado</div>
            </div>
            <button className="op-cta-btn" onClick={() => navigate('/connections')}>Conectar banco →</button>
          </div>
        )}
      </div>
    </AppShell>
  );
};
