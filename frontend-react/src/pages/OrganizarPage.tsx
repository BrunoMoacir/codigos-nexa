import { useState } from 'react';
import { useInfiniteQuery, useMutation, useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { painelApi, brl, dataCurta, dataLonga, diasDesde, rotuloMes } from '../api/painel';
import { organizarApi, ROTULO_SELO } from '../api/organizar';
import { estrategiasApi } from '../api/estrategias';
import { getErrorMessage } from '../api/errors';
import { getUserId } from '../api/session';

// ─── Sparkline SVG ────────────────────────────────────────────────────────────
function AreaChart({ data, color = '#D4A820', h = 80 }: { data: number[]; color?: string; h?: number }) {
  if (!data.length) return null;
  const w = 400;
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const range = max - min || 1;
  const pad = 8;
  const n = Math.max(data.length - 1, 1); // um mês só dividia por zero
  const pts = data.map((v, i) => {
    const x = pad + (i / n) * (w - pad * 2);
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

  .op-msg { font-size: 0.78rem; color: rgba(243,239,234,0.5); line-height: 1.5; }
  .op-msg.erro { color: #F8AEA0; }
  .op-msg.aviso { color: #F4CE80; }
  .op-btn {
    background: rgba(212,168,32,0.12); color: #D4A820; border: 1px solid rgba(212,168,32,0.3);
    border-radius: 8px; padding: 7px 12px; font-size: 0.75rem; font-weight: 700; cursor: pointer; font-family: inherit;
  }
  .op-btn:disabled { opacity: 0.5; cursor: default; }
  .op-chip {
    display: inline-block; font-size: 0.66rem; font-weight: 700; padding: 3px 8px; border-radius: 999px;
    background: rgba(243,239,234,0.06); color: rgba(243,239,234,0.6); margin: 0 6px 6px 0;
  }
  .op-chip.ouro { background: rgba(212,168,32,0.14); color: #D4A820; }
  .op-list-row { display: flex; justify-content: space-between; gap: 12px; padding: 8px 0; border-bottom: 1px solid rgba(243,239,234,0.05); }
  .op-list-row:last-child { border-bottom: none; }
  .op-list-main { font-size: 0.82rem; color: #F3EFEA; }
  .op-list-sub { font-size: 0.68rem; color: rgba(243,239,234,0.35); margin-top: 2px; }
  .op-list-val { font-size: 0.82rem; font-weight: 700; white-space: nowrap; font-variant-numeric: tabular-nums; }
`;

const CAT_COLORS = ['#D4A820','#2EC8A4','#60B0F2','#F07A64','#ECB040','#B088E0'];

const NOME_GRUPO: Record<string, string> = { essenciais: 'Essenciais', desejos: 'Estilo de vida', poupanca: 'Poupança' };

function Painel({ titulo, selo, children }: { titulo: string; selo?: string; children: React.ReactNode }) {
  return (
    <div className="op-panel">
      <div className="op-panel-head">
        <span className="op-panel-title">{titulo}</span>
        {selo && <span className="op-panel-badge">{selo}</span>}
      </div>
      {children}
    </div>
  );
}

function Estado({ q, vazio }: { q: { isLoading: boolean; error: unknown }; vazio?: string }) {
  if (q.isLoading) return <div className="op-skel" style={{ height: 60 }} />;
  if (q.error) return <div className="op-msg erro">{getErrorMessage(q.error)}</div>;
  return vazio ? <div className="op-msg">{vazio}</div> : null;
}

// O Organizar somava os 100 primeiros lançamentos no navegador (≈ 2 meses e
// meio de um extrato de um ano), completava o que faltasse com DEMO_* sem
// avisar e rotulava o gráfico com meses fixos. Agora: o resumo mensal vem do
// servidor (GET /transactions/{uid}/summary), cada painel mostra o próprio
// erro, e as seções que o backend já calculava ganharam lugar na tela.
export const OrganizarPage: React.FC = () => {
  const navigate = useNavigate();
  const userId = getUserId();
  const [rendaInformada, setRendaInformada] = useState('');
  const [compraTxt, setCompraTxt] = useState('');
  const [compraParcelas, setCompraParcelas] = useState(1);
  const valorCompra = Number(compraTxt.replace(/\./g, '').replace(',', '.')) || 0;
  const compraM = useMutation({ mutationFn: () => estrategiasApi.contextoDeCompra(userId, valorCompra, compraParcelas) });
  const opts = { enabled: !!userId };

  const resumoQ = useQuery({ queryKey: ['painel', 'resumo', userId], queryFn: () => painelApi.resumo(userId, 12), ...opts });
  const metasQ = useQuery({ queryKey: ['metas', userId, 'ACTIVE'], queryFn: () => organizarApi.metas(userId, 'ACTIVE'), ...opts });
  const renda = Number(rendaInformada.replace(',', '.')) || undefined;
  const orcamentoQ = useQuery({
    queryKey: ['organizar', 'orcamento', userId, renda ?? 'estimada'],
    queryFn: () => organizarApi.orcamento(userId, renda), retry: false, ...opts,
  });
  const assinaturasQ = useQuery({ queryKey: ['organizar', 'assinaturas', userId], queryFn: () => organizarApi.assinaturas(userId), ...opts });
  const compromissosQ = useQuery({ queryKey: ['organizar', 'compromissos', userId], queryFn: () => organizarApi.compromissos(userId), ...opts });
  const desafiosQ = useQuery({ queryKey: ['organizar', 'desafios', userId], queryFn: () => organizarApi.desafios(userId), ...opts });
  const selosQ = useQuery({ queryKey: ['organizar', 'selos', userId], queryFn: () => organizarApi.selos(userId), ...opts });
  const fiscalQ = useQuery({ queryKey: ['organizar', 'sazonalidade', userId], queryFn: () => organizarApi.sazonalidade(userId), ...opts });

  const PAGINA = 15;
  const lancamentosQ = useInfiniteQuery({
    queryKey: ['organizar', 'lancamentos', userId, PAGINA],
    queryFn: ({ pageParam }) => painelApi.lancamentos(userId, PAGINA, pageParam),
    initialPageParam: 0,
    getNextPageParam: (ultima) => (ultima.has_more ? ultima.offset + ultima.limit : undefined),
    ...opts,
  });

  const resumo = resumoQ.data;
  const totais = resumo?.totals;
  const meses = resumo?.months || [];
  const idadeDoDado = diasDesde(resumo?.data_as_of);
  const maiorCategoria = resumo?.by_category?.[0]?.total || 1;
  const lancamentos = lancamentosQ.data?.pages.flatMap(p => p.transactions) || [];
  const totalLancamentos = lancamentosQ.data?.pages[0]?.total ?? 0;

  if (resumo && resumo.n_transactions === 0) {
    return (
      <AppShell current="organizar">
        <style>{css}</style>
        <div className="op">
          <div className="op-cta">
            <div>
              <div className="op-cta-text">Nenhum lançamento ainda</div>
              <div className="op-cta-sub">Conecte um banco pelo Open Finance para organizar suas finanças com os seus dados.</div>
            </div>
            <button className="op-cta-btn" onClick={() => navigate('/connections')}>Conectar banco →</button>
          </div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell current="organizar">
      <style>{css}</style>
      <div className="op">

        {resumoQ.error && <div className="op-msg erro">{getErrorMessage(resumoQ.error)}</div>}
        {idadeDoDado !== null && idadeDoDado > 7 && (
          <div className="op-msg aviso">
            O extrato vai até {dataLonga(resumo?.data_as_of)} ({idadeDoDado} dias atrás) —{' '}
            <Link to="/connections" style={{ color: '#D4A820' }}>sincronize o banco</Link> para incluir o que veio depois.
          </div>
        )}

        {/* ── KPIs do período ── */}
        {resumoQ.isLoading ? (
          <div className="op-kpis">
            {[1,2,3,4].map(i => <div key={i} className="op-skel" style={{ height: 90 }} />)}
          </div>
        ) : totais && (
          <div className="op-kpis">
            <div className="op-kpi">
              <span className="op-kpi-label">Entradas</span>
              <span className="op-kpi-val green">{brl(totais.income, 0)}</span>
              <span className="op-kpi-delta">{meses.length} meses de extrato</span>
            </div>
            <div className="op-kpi">
              <span className="op-kpi-label">Saídas</span>
              <span className="op-kpi-val red">{brl(totais.expenses, 0)}</span>
              <span className="op-kpi-delta">{resumo?.n_transactions.toLocaleString('pt-BR')} lançamentos</span>
            </div>
            <div className="op-kpi">
              <span className="op-kpi-label">Saldo do período</span>
              {/* com sinal: o saldo negativo aparecia sem o "−" */}
              <span className={`op-kpi-val ${totais.net >= 0 ? 'green' : 'red'}`}>{brl(totais.net, 0)}</span>
              <span className="op-kpi-delta">entradas − saídas</span>
            </div>
            <div className="op-kpi">
              <span className="op-kpi-label">Taxa de poupança</span>
              <span className={`op-kpi-val ${totais.savings_rate_pct >= 0 ? 'gold' : 'red'}`}>
                {totais.savings_rate_pct.toFixed(1).replace('.', ',')}%
              </span>
              <span className="op-kpi-delta">do que entrou, quanto sobrou</span>
            </div>
          </div>
        )}

        {/* ── Gráfico + Categorias ── */}
        <div className="op-row">
          <Painel titulo="Gastos mensais" selo={meses.length ? `${rotuloMes(meses[0].month)} – ${rotuloMes(meses[meses.length - 1].month)}` : undefined}>
            {meses.length ? (
              <>
                <AreaChart data={meses.map(m => m.expenses)} color="#D4A820" h={120} />
                <div className="op-chart-labels">
                  {meses.map(m => <span key={m.month} className="op-chart-label">{rotuloMes(m.month)}</span>)}
                </div>
              </>
            ) : <Estado q={resumoQ} vazio="Sem gastos no período." />}
          </Painel>

          <Painel titulo="Por categoria">
            {resumo?.by_category?.length ? (
              <div className="op-cats">
                {resumo.by_category.slice(0, 6).map((c, i) => (
                  <div key={c.category} className="op-cat-row">
                    <div className="op-cat-dot" style={{ background: CAT_COLORS[i % CAT_COLORS.length] }} />
                    <span className="op-cat-name">{c.category}</span>
                    <div className="op-cat-track">
                      <div className="op-cat-fill" style={{ width: `${(c.total / maiorCategoria) * 100}%`, background: CAT_COLORS[i % CAT_COLORS.length] }} />
                    </div>
                    <span className="op-cat-val">{brl(c.total, 0)}</span>
                  </div>
                ))}
              </div>
            ) : <Estado q={resumoQ} vazio="Sem gastos categorizados." />}
          </Painel>
        </div>

        {/* ── Orçamento 50/30/20 + Compromissos ── */}
        <div className="op-row">
          <Painel titulo="Orçamento 50/30/20" selo={orcamentoQ.data ? `renda ${orcamentoQ.data.income_source}` : undefined}>
            {orcamentoQ.data ? (
              <>
                <div className="op-msg" style={{ marginBottom: 10 }}>
                  Renda considerada: <strong>{brl(orcamentoQ.data.income)}</strong>
                  {orcamentoQ.data.income_source === 'estimada' && ' (estimada pelo seu extrato)'}
                </div>
                {orcamentoQ.data.group_summary.map(g => (
                  <div key={g.group} className="op-goal-row">
                    <div className="op-goal-top">
                      <span className="op-goal-name">{NOME_GRUPO[g.group] || g.group}</span>
                      <span className="op-goal-pct">{g.current_pct.toFixed(0)}% <span style={{ opacity: 0.5 }}>/ {g.target_pct.toFixed(0)}%</span></span>
                    </div>
                    <div className="op-goal-track">
                      <div className="op-goal-fill" style={{
                        width: `${Math.min(100, g.target_pct ? (g.current_pct / g.target_pct) * 100 : 0)}%`,
                        background: g.group === 'poupanca' ? '#2EC8A4' : g.current_pct > g.target_pct ? '#F07A64' : undefined,
                      }} />
                    </div>
                  </div>
                ))}
                {orcamentoQ.data.summary_text && <div className="op-msg" style={{ marginTop: 8 }}>{orcamentoQ.data.summary_text}</div>}
              </>
            ) : orcamentoQ.error ? (
              <>
                <div className="op-msg erro" style={{ marginBottom: 8 }}>{getErrorMessage(orcamentoQ.error)}</div>
                <input className="op-btn" style={{ width: 160, textAlign: 'left' }} inputMode="decimal"
                  placeholder="Renda mensal (R$)" value={rendaInformada} onChange={e => setRendaInformada(e.target.value)} />
              </>
            ) : <Estado q={orcamentoQ} />}
          </Painel>

          <Painel titulo="Já comprometido" selo="parcelas e assinaturas futuras">
            {compromissosQ.data ? (
              <div className="op-msg">
                <div className="op-kpi-val red" style={{ fontSize: '1.3rem' }}>{brl(Math.abs(compromissosQ.data.total_monthly_committed))}/mês</div>
                {compromissosQ.data.installments} parcela(s) e {compromissosQ.data.subscriptions} assinatura(s) que o saldo da conta ainda não mostra.
              </div>
            ) : <Estado q={compromissosQ} />}
            <div style={{ marginTop: 14 }}>
              {assinaturasQ.data?.subscriptions.length ? assinaturasQ.data.subscriptions.map(a => (
                <div key={a.name} className="op-list-row">
                  <div>
                    <div className="op-list-main">{a.name}</div>
                    <div className="op-list-sub">
                      {a.category || 'assinatura'}{a.last_seen ? ` · última cobrança ${dataCurta(a.last_seen)}` : ''}
                      {a.price_changed ? ' · preço mudou' : ''}{a.needs_attention ? ' · vale revisar' : ''}
                    </div>
                  </div>
                  <div className="op-list-val">{brl(a.amount)}</div>
                </div>
              )) : <Estado q={assinaturasQ} vazio="Nenhuma assinatura recorrente detectada." />}
            </div>
          </Painel>
        </div>

        {/* ── Lançamentos + Metas ── */}
        <div className="op-row">
          <Painel titulo="Movimentações" selo={totalLancamentos ? `${lancamentos.length} de ${totalLancamentos.toLocaleString('pt-BR')}` : undefined}>
            {lancamentos.length ? (
              <>
                <div className="op-txn-list">
                  {lancamentos.map(t => {
                    const tipo = t.amount >= 0 ? 'in' : 'out';
                    return (
                      <div key={t.id} className="op-txn-row">
                        <div className={`op-txn-icon ${tipo}`}>{tipo === 'in' ? '↑' : '↓'}</div>
                        <div className="op-txn-info">
                          <div className="op-txn-desc">{t.description}</div>
                          <div className="op-txn-date">{dataCurta(t.date)} · {t.category || 'Outros'}</div>
                        </div>
                        <div className={`op-txn-val ${tipo}`}>{tipo === 'in' ? '+' : '−'}{brl(Math.abs(t.amount))}</div>
                      </div>
                    );
                  })}
                </div>
                {lancamentosQ.hasNextPage && (
                  <button className="op-btn" style={{ marginTop: 10 }} disabled={lancamentosQ.isFetchingNextPage}
                    onClick={() => lancamentosQ.fetchNextPage()}>
                    {lancamentosQ.isFetchingNextPage ? 'Carregando…' : 'Carregar mais'}
                  </button>
                )}
              </>
            ) : <Estado q={lancamentosQ} vazio="Nenhum lançamento." />}
          </Painel>

          <Painel titulo="Metas" selo={metasQ.data ? `${metasQ.data.goals.length} ativa(s)` : undefined}>
            {metasQ.data?.goals.length ? (
              <div className="op-goals">
                {metasQ.data.goals.map(g => (
                  <div key={g.goal_id} className="op-goal-row">
                    <div className="op-goal-top">
                      <span className="op-goal-name">{g.name}</span>
                      <span className="op-goal-pct">{Math.round(g.progress_pct)}%</span>
                    </div>
                    <div className="op-goal-track">
                      <div className="op-goal-fill" style={{ width: `${Math.min(100, g.progress_pct)}%` }} />
                    </div>
                    <div className="op-goal-sub">
                      {brl(g.current_amount, 0)} de {brl(g.target_amount, 0)}
                      {g.target_date ? ` · até ${dataLonga(g.target_date)}` : ''}
                    </div>
                  </div>
                ))}
              </div>
            ) : <Estado q={metasQ} vazio="Nenhuma meta ativa." />}
            <button className="op-btn" style={{ marginTop: 12 }} onClick={() => navigate('/goals')}>
              Gerenciar metas — criar, aportar, encerrar
            </button>
          </Painel>
        </div>

        {/* ── Vou comprar… (F7 em uma frase) ── */}
        <Painel titulo="Vou comprar…" selo="como pagar, antes de passar o cartão">
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <input className="op-btn" style={{ width: 140, textAlign: 'left' }} inputMode="decimal" placeholder="Valor (R$)"
              value={compraTxt} onChange={e => setCompraTxt(e.target.value)} aria-label="Valor da compra" />
            <select className="op-btn" value={compraParcelas} onChange={e => setCompraParcelas(Number(e.target.value))} aria-label="Parcelas">
              {[1, 2, 3, 6, 10, 12].map(n => <option key={n} value={n}>{n === 1 ? 'à vista' : `${n}x`}</option>)}
            </select>
            <button className="op-btn" disabled={!(valorCompra > 0) || compraM.isPending} onClick={() => compraM.mutate()}>
              {compraM.isPending ? 'Analisando…' : 'Ver a melhor forma'}
            </button>
          </div>
          {compraM.isError && <div className="op-msg erro" style={{ marginTop: 8 }}>{getErrorMessage(compraM.error)}</div>}
          {compraM.data && (
            <div style={{ marginTop: 10 }}>
              <div className="op-list-main">{compraM.data.verdict}</div>
              {compraM.data.options.slice(0, 4).map(o => (
                <div key={`${o.method}-${o.label}`} className="op-list-row">
                  <div className="op-list-sub">{o.label}</div>
                  <div className="op-list-val">{brl(o.net_cost)}</div>
                </div>
              ))}
              <Link to="/strategies" style={{ color: '#D4A820', fontSize: '0.75rem' }}>Análise completa (desconto à vista, parcelas, fatura) →</Link>
            </div>
          )}
        </Painel>

        {/* ── Desafios + Calendário fiscal ── */}
        <div className="op-row">
          <Painel titulo="Desafios do mês" selo={desafiosQ.data ? `${desafiosQ.data.completed_total} concluído(s) no total` : undefined}>
            {desafiosQ.data?.challenges.length ? desafiosQ.data.challenges.map(d => (
              <div key={d.id} className="op-goal-row">
                <div className="op-goal-top">
                  <span className="op-goal-name">{d.title}</span>
                  <span className="op-goal-pct">{d.status === 'COMPLETED' ? '✓' : d.status === 'SEM_DADOS' ? '—' : `${Math.round(d.pct_progress)}%`}</span>
                </div>
                <div className="op-goal-track"><div className="op-goal-fill" style={{ width: `${Math.min(100, d.pct_progress)}%` }} /></div>
                <div className="op-goal-sub">{d.target_label}</div>
              </div>
            )) : <Estado q={desafiosQ} vazio="Sem desafios para este mês." />}
            {!!selosQ.data?.badges.length && (
              <div style={{ marginTop: 12 }}>
                {selosQ.data.badges.map(b => (
                  <span key={b.badge_type} className="op-chip ouro" title={`conquistado em ${dataLonga(b.earned_at)}`}>
                    {ROTULO_SELO[b.badge_type] || b.badge_type}
                  </span>
                ))}
              </div>
            )}
          </Painel>

          <Painel titulo="Calendário fiscal" selo="prazos que geram multa">
            {fiscalQ.data?.events.length ? fiscalQ.data.events.map(e => (
              <div key={e.event_code} className="op-list-row">
                <div>
                  <div className="op-list-main">{e.name}{e.is_obligation && <span className="op-chip" style={{ marginLeft: 6 }}>obrigação</span>}</div>
                  <div className="op-list-sub">{e.description}</div>
                  <div className="op-list-sub" style={{ color: '#D4A820' }}>→ {e.action_hint}</div>
                </div>
                <div className="op-list-val">
                  {dataCurta(e.deadline)}
                  <div className="op-list-sub">{e.days_until_deadline === 0 ? 'hoje' : `em ${e.days_until_deadline} dia(s)`}</div>
                </div>
              </div>
            )) : <Estado q={fiscalQ} vazio="Nenhum prazo fiscal nas próximas semanas." />}
          </Painel>
        </div>
      </div>
    </AppShell>
  );
};
