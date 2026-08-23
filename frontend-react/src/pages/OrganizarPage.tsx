import { AppShell } from '../components/layout/AppShell';

const css = `
  .op {
    padding: 28px 32px;
    min-height: 100vh;
    background: #0E0C0A;
  }
  .op-header { margin-bottom: 28px; }
  .op-eyebrow {
    font-size: 0.67rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #D4A820;
    margin-bottom: 8px;
  }
  .op-title {
    font-size: 1.4rem;
    font-weight: 800;
    color: #F3EFEA;
    letter-spacing: -0.025em;
    margin-bottom: 4px;
  }
  .op-sub {
    font-size: 0.8rem;
    color: rgba(243,239,234,0.3);
  }

  .op-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-bottom: 24px;
  }

  .op-block {
    background: rgba(243,239,234,0.03);
    border: 1px solid rgba(243,239,234,0.07);
    border-radius: 14px;
    padding: 20px 20px;
  }
  .op-block-title {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.3);
    margin-bottom: 14px;
  }

  /* Categorias */
  .op-cat-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
    gap: 10px;
  }
  .op-cat-left {
    display: flex;
    align-items: center;
    gap: 9px;
    min-width: 0;
    flex: 1;
  }
  .op-cat-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .op-cat-name {
    font-size: 0.8rem;
    color: rgba(243,239,234,0.65);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .op-cat-bar-wrap {
    flex: 1;
    height: 4px;
    background: rgba(243,239,234,0.07);
    border-radius: 2px;
    overflow: hidden;
    margin: 0 6px;
  }
  .op-cat-bar { height: 100%; border-radius: 2px; }
  .op-cat-val {
    font-size: 0.8rem;
    font-weight: 600;
    color: rgba(243,239,234,0.6);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  /* Metas */
  .op-goal {
    margin-bottom: 14px;
  }
  .op-goal:last-child { margin-bottom: 0; }
  .op-goal-top {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 6px;
  }
  .op-goal-name {
    font-size: 0.82rem;
    font-weight: 600;
    color: #F3EFEA;
  }
  .op-goal-pct {
    font-size: 0.72rem;
    color: #D4A820;
    font-weight: 700;
  }
  .op-goal-bar-wrap {
    height: 5px;
    background: rgba(243,239,234,0.07);
    border-radius: 3px;
    overflow: hidden;
    margin-bottom: 4px;
  }
  .op-goal-bar { height: 100%; background: #D4A820; border-radius: 3px; }
  .op-goal-amounts {
    font-size: 0.7rem;
    color: rgba(243,239,234,0.25);
    font-variant-numeric: tabular-nums;
  }

  /* Wide block */
  .op-block.wide {
    grid-column: 1 / -1;
  }

  /* Tabela simples */
  .op-table { width: 100%; border-collapse: collapse; }
  .op-table th {
    text-align: left;
    font-size: 0.66rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: rgba(243,239,234,0.25);
    padding-bottom: 10px;
    border-bottom: 1px solid rgba(243,239,234,0.06);
  }
  .op-table td {
    padding: 10px 0;
    border-bottom: 1px solid rgba(243,239,234,0.05);
    font-size: 0.82rem;
    color: rgba(243,239,234,0.65);
    vertical-align: middle;
  }
  .op-table tr:last-child td { border-bottom: none; }
  .op-table td:last-child { text-align: right; color: rgba(243,239,234,0.85); font-weight: 600; font-variant-numeric: tabular-nums; }

  .op-pill {
    display: inline-flex;
    align-items: center;
    padding: 2px 8px;
    border-radius: 20px;
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.04em;
  }
  .op-pill.in  { background: rgba(46,200,164,0.12); color: #2EC8A4; }
  .op-pill.out { background: rgba(240,122,100,0.12); color: #F07A64; }

  @media (max-width: 860px) {
    .op { padding: 20px 16px; }
    .op-grid { grid-template-columns: 1fr; }
    .op-block.wide { grid-column: auto; }
  }
`;

const cats = [
  { name: 'Moradia',      color: '#D4A820', pct: 38, val: 'R$ 1.520' },
  { name: 'Alimentação',  color: '#2EC8A4', pct: 22, val: 'R$ 880' },
  { name: 'Transporte',   color: '#60B0F2', pct: 14, val: 'R$ 560' },
  { name: 'Saúde',        color: '#F07A64', pct: 10, val: 'R$ 400' },
  { name: 'Lazer',        color: '#ECB040', pct:  9, val: 'R$ 360' },
  { name: 'Outros',       color: '#947060', pct:  7, val: 'R$ 280' },
];

const goals = [
  { name: 'Reserva de emergência', curr: 8400, total: 15000 },
  { name: 'Viagem Europa',         curr: 3200, total: 12000 },
  { name: 'Notebook novo',         curr: 1800, total: 2500 },
];

const txns = [
  { desc: 'Salário',          date: 'Hoje',    type: 'in',  val: '+R$ 6.200,00' },
  { desc: 'Aluguel',          date: 'Ontem',   type: 'out', val: '−R$ 1.400,00' },
  { desc: 'iFood',            date: '19 ago',  type: 'out', val: '−R$ 87,50' },
  { desc: 'Supermercado',     date: '18 ago',  type: 'out', val: '−R$ 312,00' },
  { desc: 'Freelance',        date: '17 ago',  type: 'in',  val: '+R$ 800,00' },
  { desc: 'Netflix',          date: '15 ago',  type: 'out', val: '−R$ 55,90' },
];

export const OrganizarPage: React.FC = () => {
  return (
    <AppShell current="organizar">
      <style>{css}</style>
      <div className="op">
        <div className="op-header">
          <div className="op-eyebrow">Organizar</div>
          <div className="op-title">Visão financeira</div>
          <div className="op-sub">Seus dados agregados via Open Finance.</div>
        </div>

        <div className="op-grid">
          {/* Gastos por categoria */}
          <div className="op-block">
            <div className="op-block-title">Gastos por categoria</div>
            {cats.map(c => (
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
            {goals.map(g => {
              const pct = Math.round((g.curr / g.total) * 100);
              return (
                <div key={g.name} className="op-goal">
                  <div className="op-goal-top">
                    <span className="op-goal-name">{g.name}</span>
                    <span className="op-goal-pct">{pct}%</span>
                  </div>
                  <div className="op-goal-bar-wrap">
                    <div className="op-goal-bar" style={{ width: `${pct}%` }} />
                  </div>
                  <div className="op-goal-amounts">
                    R$ {g.curr.toLocaleString('pt-BR')} de R$ {g.total.toLocaleString('pt-BR')}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Extrato */}
          <div className="op-block wide">
            <div className="op-block-title">Últimas movimentações</div>
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
                  {txns.map((t, i) => (
                    <tr key={i}>
                      <td>{t.desc}</td>
                      <td>{t.date}</td>
                      <td>
                        <span className={`op-pill ${t.type}`}>
                          {t.type === 'in' ? 'Entrada' : 'Saída'}
                        </span>
                      </td>
                      <td>{t.val}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
};
