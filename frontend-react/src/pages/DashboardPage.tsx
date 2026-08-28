import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AppShell } from '../components/layout/AppShell';
import { nexaApi } from '../api/nexa';

const css = `
  .db { display: flex; flex-direction: column; min-height: 100vh; background: #0A0806; padding: 28px 28px 40px; gap: 22px; }

  /* Header */
  .db-header { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; }
  .db-greeting { font-size: 0.62rem; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: rgba(243,239,234,0.25); margin-bottom: 4px; }
  .db-title { font-size: 1.75rem; font-weight: 900; color: #F3EFEA; letter-spacing: -0.04em; line-height: 1; }
  .db-title span { color: #D4A820; }
  .db-period { display: flex; gap: 2px; background: #100E0B; border: 1px solid rgba(243,239,234,0.07); border-radius: 10px; padding: 3px; }
  .db-period-btn { padding: 6px 14px; border: none; background: transparent; border-radius: 7px; font-family: inherit; font-size: 0.75rem; font-weight: 600; color: rgba(243,239,234,0.3); cursor: pointer; transition: all 0.15s; letter-spacing: 0.02em; }
  .db-period-btn.on { background: rgba(212,168,32,0.12); color: #D4A820; }

  /* Main grid */
  .db-grid { display: grid; grid-template-columns: 1fr 320px; gap: 14px; }
  .db-grid-full { display: grid; grid-template-columns: 1fr 320px; gap: 14px; }

  /* Cards base */
  .db-card { background: #100E0B; border: 1px solid rgba(243,239,234,0.06); border-radius: 14px; }

  /* Chart card */
  .db-chart-card { padding: 22px 24px 18px; }
  .db-chart-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 18px; }
  .db-chart-label { font-size: 0.63rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: rgba(243,239,234,0.25); margin-bottom: 4px; }
  .db-chart-val { font-size: 1.5rem; font-weight: 900; color: #F3EFEA; letter-spacing: -0.04em; font-variant-numeric: tabular-nums; }
  .db-chart-val span { font-size: 0.9rem; color: rgba(243,239,234,0.35); font-weight: 500; }
  .db-chart-tabs { display: flex; gap: 2px; background: rgba(243,239,234,0.04); border-radius: 8px; padding: 2px; }
  .db-chart-tab { padding: 5px 11px; border: none; background: transparent; border-radius: 6px; font-family: inherit; font-size: 0.72rem; font-weight: 600; color: rgba(243,239,234,0.3); cursor: pointer; transition: all 0.15s; }
  .db-chart-tab.on { background: rgba(212,168,32,0.1); color: #D4A820; }

  /* SVG bar chart */
  .db-bars-wrap { position: relative; }
  .db-bar-tooltip {
    position: absolute; pointer-events: none;
    background: #1C1915; border: 1px solid rgba(212,168,32,0.25); border-radius: 8px;
    padding: 7px 12px; white-space: nowrap;
    font-size: 0.78rem; font-weight: 700; color: #F3EFEA;
    transform: translateX(-50%);
    transition: opacity 0.1s;
  }
  .db-bar-tooltip-sub { font-size: 0.65rem; color: rgba(243,239,234,0.35); font-weight: 500; margin-top: 1px; }
  .db-axis-labels { display: flex; padding: 0 4px; margin-top: 6px; }
  .db-axis-label { flex: 1; text-align: center; font-size: 0.63rem; color: rgba(243,239,234,0.2); font-weight: 500; }

  /* KPI stack */
  .db-kpis { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .db-kpi { background: #100E0B; border: 1px solid rgba(243,239,234,0.06); border-radius: 14px; padding: 16px 18px; }
  .db-kpi-icon { width: 32px; height: 32px; border-radius: 9px; display: flex; align-items: center; justify-content: center; font-size: 0.85rem; margin-bottom: 12px; }
  .db-kpi-label { font-size: 0.62rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: rgba(243,239,234,0.22); margin-bottom: 5px; }
  .db-kpi-val { font-size: 1.15rem; font-weight: 900; letter-spacing: -0.03em; font-variant-numeric: tabular-nums; line-height: 1; }
  .db-kpi-delta { font-size: 0.65rem; font-weight: 600; margin-top: 4px; }
  .db-kpi-delta.up   { color: #2EC8A4; }
  .db-kpi-delta.down { color: #F07A64; }
  .db-kpi-delta.neu  { color: rgba(243,239,234,0.25); }
  .db-kpi.green .db-kpi-icon { background: rgba(46,200,164,0.08);  color: #2EC8A4; }
  .db-kpi.red   .db-kpi-icon { background: rgba(240,122,100,0.08); color: #F07A64; }
  .db-kpi.gold  .db-kpi-icon { background: rgba(212,168,32,0.08);  color: #D4A820; }
  .db-kpi.blue  .db-kpi-icon { background: rgba(96,176,242,0.08);  color: #60B0F2; }
  .db-kpi.green .db-kpi-val { color: #2EC8A4; }
  .db-kpi.red   .db-kpi-val { color: #F07A64; }
  .db-kpi.gold  .db-kpi-val { color: #D4A820; }
  .db-kpi.blue  .db-kpi-val { color: #60B0F2; }

  /* Transactions */
  .db-txn-card { padding: 20px 22px; }
  .db-txn-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
  .db-txn-title { font-size: 0.85rem; font-weight: 800; color: #F3EFEA; }
  .db-txn-link { font-size: 0.7rem; font-weight: 600; color: rgba(212,168,32,0.6); background: none; border: none; font-family: inherit; cursor: pointer; padding: 0; }
  .db-txn-link:hover { color: #D4A820; }
  .db-txn-cols { display: grid; grid-template-columns: 32px 1fr auto auto; gap: 0 12px; align-items: center; margin-bottom: 8px; }
  .db-txn-col-hd { font-size: 0.58rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: rgba(243,239,234,0.15); padding-bottom: 8px; border-bottom: 1px solid rgba(243,239,234,0.05); }
  .db-txn-col-hd:last-child { text-align: right; }
  .db-txn-row { display: contents; }
  .db-txn-row > * { padding: 9px 0; border-bottom: 1px solid rgba(243,239,234,0.04); }
  .db-txn-ico { width: 30px; height: 30px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 0.8rem; flex-shrink: 0; }
  .db-txn-ico.out { background: rgba(240,122,100,0.1); color: #F07A64; }
  .db-txn-ico.in  { background: rgba(46,200,164,0.1);  color: #2EC8A4; }
  .db-txn-name { font-size: 0.82rem; font-weight: 600; color: #F3EFEA; }
  .db-txn-date { font-size: 0.67rem; color: rgba(243,239,234,0.25); margin-top: 1px; font-weight: 500; }
  .db-txn-cat  { font-size: 0.67rem; color: rgba(243,239,234,0.25); font-weight: 500; }
  .db-txn-amt  { font-size: 0.88rem; font-weight: 800; text-align: right; font-variant-numeric: tabular-nums; letter-spacing: -0.02em; }
  .db-txn-amt.out { color: #F07A64; }
  .db-txn-amt.in  { color: #2EC8A4; }

  /* Summary card (right of transactions) */
  .db-sum-card { padding: 20px 22px; display: flex; flex-direction: column; gap: 14px; }
  .db-sum-title { font-size: 0.85rem; font-weight: 800; color: #F3EFEA; margin-bottom: 2px; }
  .db-sum-item { display: flex; flex-direction: column; gap: 5px; }
  .db-sum-row { display: flex; align-items: center; justify-content: space-between; }
  .db-sum-name { font-size: 0.77rem; font-weight: 600; color: rgba(243,239,234,0.55); }
  .db-sum-pct  { font-size: 0.7rem; font-weight: 700; color: rgba(243,239,234,0.3); }
  .db-sum-bar  { height: 5px; border-radius: 99px; background: rgba(243,239,234,0.06); overflow: hidden; }
  .db-sum-fill { height: 100%; border-radius: 99px; }
  .db-sum-divider { height: 1px; background: rgba(243,239,234,0.05); }

  /* Skeleton */
  .db-skel { background: rgba(243,239,234,0.05); border-radius: 12px; animation: db-pulse 1.4s ease-in-out infinite; }
  @keyframes db-pulse { 0%,100%{opacity:0.35} 50%{opacity:0.7} }

  @media (max-width: 960px) {
    .db { padding: 16px 14px 80px; gap: 14px; }
    .db-grid, .db-grid-full { grid-template-columns: 1fr; }
    .db-kpis { grid-template-columns: 1fr 1fr; }
  }
`;

const MONTHS = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];

const DEMO_SPEND = [4200, 3800, 5100, 4600, 5800, 6200, 5500, 7100, 6800, 5200, 4900, 7400];
const DEMO_TXNS = [
  { dir: 'out' as const, icon: '🛒', name: 'Supermercado Extra',  cat: 'Alimentação',  date: '27 ago, 14:32', amount: -284.90 },
  { dir: 'in'  as const, icon: '💼', name: 'Salário',              cat: 'Receita',       date: '25 ago, 09:00', amount: 6500.00 },
  { dir: 'out' as const, icon: '⛽', name: 'Shell Combustível',    cat: 'Transporte',   date: '24 ago, 18:15', amount: -190.00 },
  { dir: 'out' as const, icon: '📱', name: 'Nubank — Fatura',     cat: 'Cartão',        date: '22 ago, 12:00', amount: -1340.00 },
  { dir: 'in'  as const, icon: '↩', name: 'Reembolso iFood',     cat: 'Estorno',       date: '20 ago, 10:30', amount: 42.00 },
  { dir: 'out' as const, icon: '🎬', name: 'Netflix',              cat: 'Assinatura',   date: '18 ago, 00:01', amount: -55.90 },
  { dir: 'out' as const, icon: '🏋', name: 'Smart Fit',            cat: 'Saúde',         date: '15 ago, 08:00', amount: -99.90 },
];

const DEMO_CATS = [
  { name: 'Alimentação',  pct: 32, color: '#D4A820' },
  { name: 'Cartão',       pct: 24, color: '#60B0F2' },
  { name: 'Transporte',   pct: 14, color: '#2EC8A4' },
  { name: 'Assinaturas',  pct: 9,  color: '#F07A64'  },
  { name: 'Saúde',        pct: 8,  color: '#B08A2A'  },
  { name: 'Outros',       pct: 13, color: 'rgba(243,239,234,0.15)' },
];

function fmt(v: number) {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 }).format(Math.abs(v));
}

function BarChart({ data, months, period }: { data: number[]; months: string[]; period: number }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const max = Math.max(...data, 1);
  const W = 480; const H = 110;
  const n = data.length;
  const barW = Math.floor((W / n) * 0.55);
  const gap  = W / n;

  const selectedIdx = hovered ?? (period === 1 ? n - 1 : null);

  return (
    <div className="db-bars-wrap" style={{ position: 'relative' }}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: '100%', height: 'auto', display: 'block', overflow: 'visible' }}
        onMouseLeave={() => setHovered(null)}
      >
        <defs>
          <linearGradient id="barGold" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#D4A820"/>
            <stop offset="100%" stopColor="#A07A10"/>
          </linearGradient>
          <linearGradient id="barDim" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgba(243,239,234,0.12)"/>
            <stop offset="100%" stopColor="rgba(243,239,234,0.06)"/>
          </linearGradient>
        </defs>

        {/* Y grid lines */}
        {[0.25, 0.5, 0.75, 1].map(f => (
          <line key={f} x1={0} x2={W} y1={H - f * H} y2={H - f * H}
            stroke="rgba(243,239,234,0.05)" strokeWidth="1"/>
        ))}

        {data.map((v, i) => {
          const bh = Math.max(6, (v / max) * (H - 10));
          const x  = gap * i + (gap - barW) / 2;
          const y  = H - bh;
          const active = selectedIdx === i;
          return (
            <g key={i}
              onMouseEnter={() => setHovered(i)}
              style={{ cursor: 'pointer' }}
            >
              <rect x={x} y={y} width={barW} height={bh}
                rx={4} ry={4}
                fill={active ? 'url(#barGold)' : 'url(#barDim)'}
                style={{ transition: 'fill 0.15s' }}
              />
            </g>
          );
        })}
      </svg>

      {/* Tooltip */}
      {selectedIdx !== null && (
        <div className="db-bar-tooltip" style={{
          left: `${((selectedIdx + 0.5) / n) * 100}%`,
          top: `-${Math.max(14, ((data[selectedIdx] / max) * 60) - 4)}px`,
          opacity: 1,
        }}>
          {fmt(data[selectedIdx])}
          <div className="db-bar-tooltip-sub">{months[selectedIdx]}</div>
        </div>
      )}

      <div className="db-axis-labels">
        {months.map((m, i) => (
          <div key={i} className="db-axis-label"
            style={{ color: selectedIdx === i ? 'rgba(212,168,32,0.7)' : undefined }}>
            {m}
          </div>
        ))}
      </div>
    </div>
  );
}

type Period = '1a' | '6m' | '3m' | '1m';

export const DashboardPage: React.FC = () => {
  const [period, setPeriod] = useState<Period>('1a');
  const [chartTab, setChartTab] = useState<'total' | 'media'>('total');
  const userId = localStorage.getItem('user_id') || '';
  const userName = localStorage.getItem('user_name') || localStorage.getItem('user_email') || '';
  const displayName = userName ? userName.split(' ')[0] || userName.split('@')[0] : 'você';

  const txnQ = useQuery({
    queryKey: ['transactions', userId],
    queryFn: () => nexaApi.getTransactions(userId),
    enabled: !!userId, retry: 1, staleTime: 5 * 60 * 1000,
  });

  const loading = txnQ.isLoading;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const rawTxns: any[] = txnQ.data?.transactions || [];
  const hasReal = rawTxns.length > 0;

  const txns = hasReal
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ? rawTxns.slice(0, 7).map((t: any) => ({
        dir: (t.amount > 0 ? 'in' : 'out') as 'in' | 'out',
        icon: t.amount > 0 ? '↑' : '↓',
        name: t.description || t.name || 'Transação',
        cat: t.category || 'Geral',
        date: t.date || '',
        amount: t.amount,
      }))
    : DEMO_TXNS;

  const sliceMap: Record<Period, number> = { '1a': 12, '6m': 6, '3m': 3, '1m': 1 };
  const sliceN = sliceMap[period];
  const spendData = DEMO_SPEND.slice(12 - sliceN);
  const monthsData = MONTHS.slice(12 - sliceN);

  const totalSpend = spendData.reduce((a, b) => a + b, 0);
  const avgSpend   = Math.round(totalSpend / spendData.length);
  const thisMonth  = spendData[spendData.length - 1];
  const lastMonth  = spendData[spendData.length - 2] ?? thisMonth;
  const spendDelta = ((thisMonth - lastMonth) / lastMonth) * 100;

  const chartData   = chartTab === 'total' ? spendData : spendData.map(() => avgSpend);

  return (
    <AppShell current="dashboard">
      <style>{css}</style>
      <div className="db">

        {/* Header */}
        <div className="db-header">
          <div>
            <div className="db-greeting">Painel de controle</div>
            <div className="db-title">
              Bem-vindo de volta,{' '}
              <span>{displayName.charAt(0).toUpperCase() + displayName.slice(1)}!</span>
            </div>
          </div>
          <div className="db-period">
            {(['1a','6m','3m','1m'] as Period[]).map(p => (
              <button key={p} className={`db-period-btn${period === p ? ' on' : ''}`}
                onClick={() => setPeriod(p)}>
                {p === '1a' ? '1 Ano' : p === '6m' ? '6 Meses' : p === '3m' ? '3 Meses' : '1 Mês'}
              </button>
            ))}
          </div>
        </div>

        {/* Row 1: Chart + KPIs */}
        <div className="db-grid">
          {/* Bar Chart */}
          <div className="db-card db-chart-card">
            <div className="db-chart-header">
              <div>
                <div className="db-chart-label">Gastos no período</div>
                <div className="db-chart-val">
                  {fmt(totalSpend)} <span>BRL</span>
                </div>
              </div>
              <div className="db-chart-tabs">
                <button className={`db-chart-tab${chartTab === 'total' ? ' on' : ''}`}
                  onClick={() => setChartTab('total')}>Total</button>
                <button className={`db-chart-tab${chartTab === 'media' ? ' on' : ''}`}
                  onClick={() => setChartTab('media')}>Média</button>
              </div>
            </div>
            <BarChart data={chartData} months={monthsData} period={sliceN} />
          </div>

          {/* KPI 2×2 */}
          <div className="db-kpis">
            <div className="db-kpi green">
              <div className="db-kpi-icon">↑</div>
              <div className="db-kpi-label">Receita mensal</div>
              <div className="db-kpi-val">R$ 6.500</div>
              <div className="db-kpi-delta up">+8% vs. mês ant.</div>
            </div>
            <div className="db-kpi red">
              <div className="db-kpi-icon">↓</div>
              <div className="db-kpi-label">Gastos mês</div>
              <div className="db-kpi-val">{fmt(thisMonth)}</div>
              <div className={`db-kpi-delta ${spendDelta > 0 ? 'down' : 'up'}`}>
                {spendDelta > 0 ? '+' : ''}{spendDelta.toFixed(1)}% vs. mês ant.
              </div>
            </div>
            <div className="db-kpi gold">
              <div className="db-kpi-icon">◈</div>
              <div className="db-kpi-label">Saldo atual</div>
              <div className="db-kpi-val">R$ 4.820</div>
              <div className="db-kpi-delta neu">Conta + poupança</div>
            </div>
            <div className="db-kpi blue">
              <div className="db-kpi-icon">%</div>
              <div className="db-kpi-label">Taxa poupança</div>
              <div className="db-kpi-val">26%</div>
              <div className="db-kpi-delta up">Meta: 20% ✓</div>
            </div>
          </div>
        </div>

        {/* Row 2: Transactions + Category summary */}
        <div className="db-grid-full">
          {/* Transactions */}
          <div className="db-card db-txn-card">
            <div className="db-txn-top">
              <div className="db-txn-title">Transações Recentes</div>
              <button className="db-txn-link">Ver todas →</button>
            </div>

            {loading ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {[1,2,3,4].map(i => <div key={i} className="db-skel" style={{ height: 44 }} />)}
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: '30px 1fr auto auto', gap: '0 12px', alignItems: 'center' }}>
                {/* Header cols */}
                <div style={{ gridColumn: '1/2' }} />
                <div className="db-txn-col-hd">Transação</div>
                <div className="db-txn-col-hd">Categoria</div>
                <div className="db-txn-col-hd" style={{ textAlign: 'right' }}>Valor</div>

                {txns.map((t, i) => (
                  <div key={i} style={{ display: 'contents' }}>
                    <div style={{ padding: '9px 0', borderBottom: '1px solid rgba(243,239,234,0.04)' }}>
                      <div className={`db-txn-ico ${t.dir}`}>{t.icon}</div>
                    </div>
                    <div style={{ padding: '9px 0', borderBottom: '1px solid rgba(243,239,234,0.04)' }}>
                      <div className="db-txn-name">{t.name}</div>
                      <div className="db-txn-date">{t.date}</div>
                    </div>
                    <div style={{ padding: '9px 0', borderBottom: '1px solid rgba(243,239,234,0.04)' }}>
                      <div className="db-txn-cat">{t.cat}</div>
                    </div>
                    <div style={{ padding: '9px 0', borderBottom: '1px solid rgba(243,239,234,0.04)' }}>
                      <div className={`db-txn-amt ${t.dir}`}>
                        {t.dir === 'out' ? '−' : '+'}{fmt(t.amount)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Category breakdown */}
          <div className="db-card db-sum-card">
            <div className="db-sum-title">Gasto por Categoria</div>
            <div className="db-sum-divider" />
            {DEMO_CATS.map((c, i) => (
              <div key={i} className="db-sum-item">
                <div className="db-sum-row">
                  <div className="db-sum-name">{c.name}</div>
                  <div className="db-sum-pct">{c.pct}%</div>
                </div>
                <div className="db-sum-bar">
                  <div className="db-sum-fill" style={{ width: `${c.pct}%`, background: c.color }} />
                </div>
              </div>
            ))}
            <div className="db-sum-divider" />
            <div style={{ fontSize: '0.7rem', color: 'rgba(243,239,234,0.2)', fontWeight: 500 }}>
              {hasReal ? 'Dados reais · abr/25' : 'Dados de demonstração'}
            </div>
          </div>
        </div>

      </div>
    </AppShell>
  );
};
