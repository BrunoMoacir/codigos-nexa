import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { protecaoApi } from '../api/protecao';
import { brl } from '../api/painel';
import { describeError } from '../api/errors';
import { getUserId } from '../api/session';

const card: React.CSSProperties = { background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 12, padding: 16 };
const nota: React.CSSProperties = { fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 };
const botao: React.CSSProperties = { border: '1px solid #111', background: 'var(--text-primary)', color: 'var(--bg-surface)', borderRadius: 8, padding: '8px 12px', fontSize: 13, cursor: 'pointer' };
const input: React.CSSProperties = { border: '1px solid var(--border-color)', borderRadius: 8, padding: 8, width: 110 };
const pct = (v: number | null | undefined) => (v == null ? '—' : `${v.toFixed(2).replace('.', ',')}%`);
const num = (t: string) => Number(t.replace(',', '.'));

function Erro({ erro, fallback }: { erro: unknown; fallback: string }) {
  const e = describeError(erro, fallback);
  return <div style={{ ...nota, color: '#991b1b' }}>{e.message}{e.kind === 'upgrade_required' && <> · <Link to="/planos">Ver planos</Link></>}</div>;
}

// Era um esqueleto: o otimizador de IR da carteira (T1) e a conta CDB × LCI
// (T2) não tinham superfície nenhuma.
export const TaxPage: React.FC = () => {
  const userId = getUserId();
  const irQ = useQuery({ queryKey: ['impostos', 'ir', userId], queryFn: () => protecaoApi.otimizarIr(userId), enabled: !!userId, retry: false });
  const [cdb, setCdb] = useState('13,5');
  const [meses, setMeses] = useState('13');
  const [lci, setLci] = useState('');
  const beM = useMutation({ mutationFn: () => protecaoApi.breakeven(num(cdb), Math.round(num(meses)), lci ? num(lci) : undefined) });

  const d = irQ.data;
  return (
    <AppShell current="impostos" title="Impostos" subtitle="IR dos seus investimentos e a conta que decide entre CDB e LCI/LCA.">
      <div style={{ display: 'grid', gap: 12 }}>
        <div style={card}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>Imposto de renda da sua carteira</div>
          {irQ.isLoading && <div style={nota}>Lendo seus investimentos…</div>}
          {irQ.isError && <Erro erro={irQ.error} fallback="Não foi possível analisar sua carteira." />}
          {d && (d.data_source === 'no_data' ? (
            <div style={nota}>{d.summary} <Link to="/connections">Conectar banco</Link></div>
          ) : (
            <div style={{ display: 'grid', gap: 10 }}>
              <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                <div><div style={nota}>Saldo investido</div><div style={{ fontSize: 20, fontWeight: 800 }}>{brl(d.total_current_balance)}</div></div>
                <div><div style={nota}>IR se resgatar tudo hoje</div><div style={{ fontSize: 20, fontWeight: 800 }}>{brl(d.total_estimated_ir_liability)}</div></div>
                <div><div style={nota}>Imposto que dá para evitar</div><div style={{ fontSize: 20, fontWeight: 800, color: '#166534' }}>{brl(d.total_estimated_tax_saving)}</div></div>
                {d.total_estimated_deferral_gain > 0 && (
                  <div><div style={nota}>Ganho por adiar o imposto</div><div style={{ fontSize: 20, fontWeight: 800 }}>{brl(d.total_estimated_deferral_gain)}</div></div>
                )}
              </div>
              <div style={{ fontSize: 13 }}>{d.summary}</div>
              {d.opportunities.map((o, i) => (
                <div key={i} style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 10, display: 'grid', gap: 4 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                    <strong style={{ fontSize: 13 }}>{o.title}</strong>
                    <strong style={{ fontSize: 13 }}>{brl(o.estimated_tax_saving_brl)}</strong>
                  </div>
                  <div style={nota}>{o.position_ref} · {o.benefit_kind === 'deferral' ? 'adiamento do imposto (ele ainda é devido depois)' : 'imposto que deixa de ser devido'}{o.action_deadline ? ` · ${o.action_deadline}` : ''}</div>
                  <div style={{ fontSize: 13 }}>{o.description}</div>
                  <div style={{ fontSize: 13 }}><strong>Ação:</strong> {o.recommended_action}</div>
                </div>
              ))}
              {d.portfolio.length > 0 && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr auto auto', gap: '4px 14px', fontSize: 12 }}>
                  <span style={nota}>Aplicação</span><span style={nota}>Saldo</span><span style={nota}>IR hoje</span>
                  {d.portfolio.map((p, i) => (
                    <div key={i} style={{ display: 'contents' }}>
                      <span>{p.bank_name} · {p.product_name}{p.is_exempt ? ' (isento)' : ''}</span>
                      <span>{brl(p.current_balance, 0)}</span>
                      <span>{brl(p.estimated_ir, 0)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        <div style={card}>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>CDB ou LCI/LCA?</div>
          <div style={nota}>A LCI/LCA é isenta de IR. Diga a taxa do CDB e o prazo: mostramos a taxa mínima de LCI que empata depois do imposto.</div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'end', marginTop: 10 }}>
            <label style={{ display: 'grid', gap: 4, fontSize: 12 }}>CDB (% a.a.)<input style={input} value={cdb} inputMode="decimal" onChange={e => setCdb(e.target.value)} /></label>
            <label style={{ display: 'grid', gap: 4, fontSize: 12 }}>Prazo (meses)<input style={input} value={meses} inputMode="numeric" onChange={e => setMeses(e.target.value)} /></label>
            <label style={{ display: 'grid', gap: 4, fontSize: 12 }}>LCI oferecida (opcional)<input style={input} value={lci} inputMode="decimal" onChange={e => setLci(e.target.value)} /></label>
            <button style={botao} disabled={!(num(cdb) > 0) || !(num(meses) > 0) || beM.isPending} onClick={() => beM.mutate()}>Calcular</button>
          </div>
          {beM.isError && <Erro erro={beM.error} fallback="Não foi possível calcular." />}
          {beM.data && (
            <div style={{ marginTop: 10, display: 'grid', gap: 4, fontSize: 13 }}>
              <div>IR no prazo: <strong>{pct(beM.data.ir_rate_pct)}</strong> · CDB líquido: <strong>{pct(beM.data.cdb_net_rate_pct)}</strong></div>
              <div>Qualquer LCI/LCA acima de <strong>{pct(beM.data.lci_breakeven_pct)}</strong> rende mais que esse CDB.</div>
              {beM.data.lci_advantage_pct != null && <div>A LCI oferecida rende {pct(Math.abs(beM.data.lci_advantage_pct))} {beM.data.lci_advantage_pct >= 0 ? 'a mais' : 'a menos'}.</div>}
              <div style={nota}>{beM.data.interpretation}</div>
            </div>
          )}
        </div>

        <div style={{ ...card, fontSize: 13 }}>
          Tem MEI? O DAS, a receita do negócio e o uso misto ficam em <Link to="/strategies">Estratégias → MEI / Fiscal</Link>. Os prazos do ano (IRPF, DAS, IPVA) estão no <Link to="/organizar">Organizar</Link>.
        </div>
      </div>
    </AppShell>
  );
};
