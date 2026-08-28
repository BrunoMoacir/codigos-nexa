import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { nexaApi } from '../api/nexa';
import type { Transaction, Goal } from '../api/types';

const css = `
  .op { padding: 28px 32px; min-height: 100vh; background: #0E0C0A; }
  .op-header { margin-bottom: 28px; }
  .op-eyebrow { font-size: 0.67rem; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: #D4A820; margin-bottom: 8px; }
  .op-title { font-size: 1.4rem; font-weight: 800; color: #F3EFEA; letter-spacing: -0.025em; margin-bottom: 4px; }
  .op-sub { font-size: 0.8rem; color: rgba(243,239,234,0.3); }

  .op-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 24px; }
  .op-block { background: rgba(243,239,234,0.03); border: 1px solid rgba(243,239,234,0.07); border-radius: 14px; padding: 20px; }
  .op-block.wide { grid-column: 1 / -1; }
  .op-block-title { font-size: 0.7rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: rgba(243,239,234,0.3); margin-bottom: 14px; }

  /* Categorias */
  .op-cat-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; gap: 10px; }
  .op-cat-left { display: flex; align-items: center; gap: 9px; min-width: 0; flex: 1; }
  .op-cat-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .op-cat-name { font-size: 0.8rem; color: rgba(243,239,234,0.65); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .op-cat-bar-wrap { flex: 1; height: 4px; background: rgba(243,239,234,0.07); border-radius: 2px; overflow: hidden; margin: 0 6px; }
  .op-cat-bar { height: 100%; border-radius: 2px; }
  .op-cat-val { font-size: 0.8rem; font-weight: 600; color: rgba(243,239,234,0.6); font-variant-numeric: tabular-nums; white-space: nowrap; }

  /* Metas */
  .op-goal { margin-bottom: 14px; }
  .op-goal:last-child { margin-bottom: 0; }
  .op-goal-top { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; }
  .op-goal-name { font-size: 0.82rem; font-weight: 600; color: #F3EFEA; }
  .op-goal-pct { font-size: 0.72rem; color: #D4A820; font-weight: 700; }
  .op-goal-bar-wrap { height: 5px; background: rgba(243,239,234,0.07); border-radius: 3px; overflow: hidden; margin-bottom: 4px; }
  .op-goal-bar { height: 100%; background: #D4A820; border-radius: 3px; transition: width 0.6s ease; }
  .op-goal-amounts { font-size: 0.7rem; color: rgba(243,239,234,0.25); font-variant-numeric: tabular-nums; }

  /* Tabela */
  .op-table { width: 100%; border-collapse: collapse; }
  .op-table th { text-align: left; font-size: 0.66rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: rgba(243,239,234,0.25); padding-bottom: 10px; border-bottom: 1px solid rgba(243,239,234,0.06); }
  .op-table td { padding: 10px 0; border-bottom: 1px solid rgba(243,239,234,0.05); font-size: 0.82rem; color: rgba(243,239,234,0.65); vertical-align: middle; }
  .op-table tr:last-child td { border-bottom: none; }
  .op-table td:last-child { text-align: right; color: rgba(243,239,234,0.85); font-weight: 600; font-variant-numeric: tabular-nums; }

  .op-pill { display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 20px; font-size: 0.62rem; font-weight: 700; letter-spacing: 0.04em; }
  .op-pill.in  { background: rgba(46,200,164,0.12); color: #2EC8A4; }
  .op-pill.out { background: rgba(240,122,100,0.12); color: #F07A64; }

  /* Skeleton */
  .op-skel { background: rgba(243,239,234,0.05); border-radius: 14px; animation: op-pulse 1.4s ease-in-out infinite; }
  @keyframes op-pulse { 0%,100%{opacity:0.4} 50%{opacity:0.8} }

  /* Banner demo */
  .op-demo-banner { display: flex; align-items: center; gap: 10px; background: rgba(212,168,32,0.07); border: 1px solid rgba(212,168,32,0.15); border-radius: 10px; padding: 10px 16px; margin-bottom: 20px; font-size: 0.75rem; color: rgba(243,239,234,0.5); }
  .op-demo-dot { width: 6px; height: 6px; border-radius: 50%; background: #D4A820; flex-shrink: 0; }

  /* Connect CTA */
  .op-connect { background: rgba(212,168,32,0.06); border: 1px solid rgba(212,168,32,0.15); border-radius: 14px; padding: 24px; display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-top: 8px; }
  .op-connect-label { font-size: 0.95rem; font-weight: 700; color: #F3EFEA; margin-bottom: 4px; }
  .op-connect-sub { font-size: 0.75rem; color: rgba(243,239,234,0.35); }
  .op-connect-btn { padding: 10px 20px; background: #D4A820; color: #0C0A08; border: none; border-radius: 9px; font-family: inherit; font-size: 0.82rem; font-weight: 800; letter-spacing: 0.03em; cursor: pointer; white-space: nowrap; transition: background 0.15s; flex-shrink: 0; }
  .op-connect-btn:hover { background: #E8C030; }

  .op-empty { text-align: center; padding: 32px 20px; color: rgba(243,239,234,0.2); font-size: 0.85rem; }

  @media (max-width: 860px) {
    .op { padding: 20px 16px; }
    .op-grid { grid-template-columns: 1fr; }
    .op-block.wide { grid-column: auto; }
    .op-connect { flex-direction: column; align-items: flex-start; }
    .op-connect-btn { width: 100%; text-align: center; }
  }
`;

const CAT_COLORS = ['#D4A820','#2EC8A4','#60B0F2','#F07A64','#ECB040','#947060','#B088E0','#78C8A0'];

const DEMO_CATS = [
  { name: 'Moradia',     color: '#D4A820', pct: 38, val: 'R$ 1.520' },
  { name: 'Alimentação', color: '#2EC8A4', pct: 22, val: 'R$ 880' },
  { name: 'Transporte',  color: '#60B0F2', pct: 14, val: 'R$ 560' },
  { name: 'Saúde',       color: '#F07A64', pct: 10, val: 'R$ 400' },
  { name: 'Lazer',       color: '#ECB040', pct:  9, val: 'R$ 360' },
  { name: 'Outros',      color: '#947060', pct:  7, val: 'R$ 280' },
];

const DEMO_GOALS = [
  { name: 'Reserva de emergência', curr: 8400,  total: 15000 },
  { name: 'Viagem Europa',         curr: 3200,  total: 12000 },
  { name: 'Notebook novo',         curr: 1800,  total: 2500  },
];

const DEMO_TXNS = [
  { desc: 'Salário',      date: 'Hoje',   type: 'in',  val: '+R$ 6.200,00' },
  { desc: 'Aluguel',      date: 'Ontem',  type: 'out', val: '−R$ 1.400,00' },
  { desc: 'iFood',        date: '19 ago', type: 'out', val: '−R$ 87,50' },
  { desc: 'Supermercado', date: '18 ago', type: 'out', val: '−R$ 312,00' },
  { desc: 'Freelance',    date: '17 ago', type: 'in',  val: '+R$ 800,00' },
  { desc: 'Netflix',      date: '15 ago', type: 'out', val: '−R$ 55,90' },
];

function fmtBRL(n: number) {
  return `R$ ${Math.abs(n).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`;
}

function fmtDate(d: string) {
  try {
    return new Date(d).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' });
  } catch { return d; }
}

function buildCatsFromTxns(txns: Transaction[]) {
  const map: Record<string, number> = {};
  for (const t of txns) {
    if (t.type === 'expense' || t.amount < 0) {
      const cat = t.category || 'Outros';
      map[cat] = (map[cat] || 0) + Math.abs(t.amount);
    }
  }
  const entries = Object.entries(map).sort((a, b) => b[1] - a[1]).slice(0, 6);
  const total = entries.reduce((s, [, v]) => s + v, 0) || 1;
  return entries.map(([name, val], i) => ({
    name,
    color: CAT_COLORS[i] || '#947060',
    pct: Math.round((val / total) * 100),
    val: fmtBRL(val),
  }));
}

export const OrganizarPage: React.FC = () => {
  const navigate = useNavigate();
  const userId = localStorage.getItem('user_id') || '';

  const txnsQ = useQuery({
    queryKey: ['transactions', userId],
    queryFn: () => nexaApi.getTransactions(userId, 50),
    enabled: !!userId,
    retry: 1,
    staleTime: 2 * 60 * 1000,
  });

  const goalsQ = useQuery({
    queryKey: ['goals', userId],
    queryFn: () => nexaApi.getGoals(userId),
    enabled: !!userId,
    retry: 1,
    staleTime: 2 * 60 * 1000,
  });

  const loading = txnsQ.isLoading || goalsQ.isLoading;

  const txns: Transaction[] = txnsQ.data?.transactions || [];
  const goals: Goal[] = goalsQ.data?.goals || [];
  const hasReal = txns.length > 0 || goals.length > 0;
  const isDemo = !hasReal && !loading;

  const cats = txns.length > 0 ? buildCatsFromTxns(txns) : DEMO_CATS;
  const displayGoals = goals.length > 0 ? goals : DEMO_GOALS;

  const displayTxns = txns.length > 0
    ? txns.slice(0, 10).map(t => ({
        desc: t.description,
        date: fmtDate(t.date),
        type: t.type === 'income' || t.amount > 0 ? 'in' : 'out',
        val: (t.type === 'income' || t.amount > 0 ? '+' : '−') + fmtBRL(t.amount),
      }))
    : DEMO_TXNS;

  return (
    <AppShell current="organizar">
      <style>{css}</style>
      <div className="op">
        <div className="op-header">
          <div className="op-eyebrow">Organizar</div>
          <div className="op-title">Visão financeira</div>
          <div className="op-sub">{hasReal ? 'Dados reais via Open Finance.' : 'Seus dados agregados via Open Finance.'}</div>
        </div>

        {isDemo && (
          <div className="op-demo-banner">
            <div className="op-demo-dot" />
            Demonstração — conecte seu banco para ver seus dados reais.
          </div>
        )}

        {loading ? (
          <div className="op-grid">
            <div className="op-skel" style={{ height: 260 }} />
            <div className="op-skel" style={{ height: 260 }} />
            <div className="op-skel" style={{ height: 220, gridColumn: '1/-1' }} />
          </div>
        ) : (
          <div className="op-grid">
            {/* Categorias */}
            <div className="op-block">
              <div className="op-block-title">Gastos por categoria</div>
              {cats.length === 0
                ? <div className="op-empty">Nenhuma transação de saída registrada.</div>
                : cats.map(c => (
                  <div key={c.name} className="op-cat-row">
                    <div className="op-cat-left">
                      <div className="op-cat-dot" style={{ background: c.color }} />
                      <span className="op-cat-name">{c.name}</span>
                    </div>
                    <div className="op-cat-bar-wrap">
                      <div className="op-cat-bar" style={{ width: `${c.pct}%`, background: c.color }} />
                    </div>
                    <span className="op-cat-val">{c.val}</span>
                  </div>
                ))}
            </div>

            {/* Metas */}
            <div className="op-block">
              <div className="op-block-title">Metas</div>
              {displayGoals.length === 0
                ? <div className="op-empty">Nenhuma meta criada ainda.</div>
                : displayGoals.map((g: Goal | typeof DEMO_GOALS[0]) => {
                    const curr = 'current_amount' in g ? g.current_amount : (g as typeof DEMO_GOALS[0]).curr;
                    const total = 'target_amount' in g ? g.target_amount : (g as typeof DEMO_GOALS[0]).total;
                    const name = g.name;
                    const pct = Math.min(100, Math.round((curr / total) * 100));
                    return (
                      <div key={name} className="op-goal">
                        <div className="op-goal-top">
                          <span className="op-goal-name">{name}</span>
                          <span className="op-goal-pct">{pct}%</span>
                        </div>
                        <div className="op-goal-bar-wrap">
                          <div className="op-goal-bar" style={{ width: `${pct}%` }} />
                        </div>
                        <div className="op-goal-amounts">
                          {fmtBRL(curr)} de {fmtBRL(total)}
                        </div>
                      </div>
                    );
                  })}
            </div>

            {/* Extrato */}
            <div className="op-block wide">
              <div className="op-block-title">Últimas movimentações</div>
              {displayTxns.length === 0
                ? <div className="op-empty">Nenhuma transação encontrada.</div>
                : (
                  <div style={{ overflowX: 'auto' }}>
                    <table className="op-table">
                      <thead>
                        <tr>
                          <th>Descrição</th>
                          <th>Data</th>
                          <th>Tipo</th>
                          <th>Valor</th>
                        </tr>
                      </thead>
                      <tbody>
                        {displayTxns.map((t, i) => (
                          <tr key={i}>
                            <td>{t.desc}</td>
                            <td>{t.date}</td>
                            <td><span className={`op-pill ${t.type}`}>{t.type === 'in' ? 'Entrada' : 'Saída'}</span></td>
                            <td>{t.val}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
            </div>
          </div>
        )}

        <div className="op-connect">
          <div>
            <div className="op-connect-label">Conecte seu banco para dados reais</div>
            <div className="op-connect-sub">Via Open Finance · Leitura apenas · Dados criptografados</div>
          </div>
          <button className="op-connect-btn" onClick={() => navigate('/connections')}>
            Conectar banco →
          </button>
        </div>
      </div>
    </AppShell>
  );
};
