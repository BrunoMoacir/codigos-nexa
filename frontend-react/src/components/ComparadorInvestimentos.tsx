import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { feedApi, rotuloLiquidez } from '../api/feed';
import { brl } from '../api/painel';
import { describeError } from '../api/errors';

const cardStyle: React.CSSProperties = { background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 12, padding: 18 };
const nota: React.CSSProperties = { fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 };
const input: React.CSSProperties = { border: '1px solid var(--border-color)', borderRadius: 8, padding: 7, width: 120, background: 'transparent', color: 'inherit' };
const pct = (v: number) => `${v.toFixed(2).replace('.', ',')}%`;

/**
 * Drill-down do Radar: "e se eu aplicar X por N meses?" — Tesouro × CDB ×
 * poupança e o banco que mais combina com o perfil. As rotas existiam
 * (OPP.4/OPP.5 + Bank Match) e nenhuma tela chamava.
 */
export const ComparadorInvestimentos: React.FC<{ userId: string; valorInicial?: number }> = ({ userId, valorInicial }) => {
  const [aberto, setAberto] = useState(false);
  const [valorTxt, setValorTxt] = useState(String(Math.round(valorInicial && valorInicial > 0 ? valorInicial : 10000)));
  const [meses, setMeses] = useState(12);
  const valor = Number(valorTxt.replace(/\./g, '').replace(',', '.')) || 0;

  const compQ = useQuery({
    queryKey: ['opp', 'comparativo', valor, meses],
    queryFn: () => feedApi.comparativo(valor, meses),
    enabled: aberto && valor > 0, staleTime: 30 * 60 * 1000,
  });
  const bancoQ = useQuery({
    queryKey: ['opp', 'banco-ideal', userId, valor, meses],
    queryFn: () => feedApi.bancoIdeal(userId, valor, meses),
    enabled: aberto && valor > 0 && !!userId, staleTime: 30 * 60 * 1000, retry: false,
  });

  if (!aberto) {
    return (
      <button onClick={() => setAberto(true)} style={{ ...cardStyle, cursor: 'pointer', textAlign: 'left', color: 'inherit', font: 'inherit' }}>
        <strong style={{ fontSize: 14 }}>Comparar onde aplicar →</strong>
        <div style={nota}>Tesouro, CDB e poupança para o valor e o prazo que você escolher, e o banco que mais combina com você.</div>
      </button>
    );
  }

  const erroBanco = bancoQ.error ? describeError(bancoQ.error, 'Não foi possível montar o ranking de bancos.') : null;
  return (
    <div style={{ ...cardStyle, display: 'grid', gap: 12 }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'end', flexWrap: 'wrap' }}>
        <label style={{ display: 'grid', gap: 4, fontSize: 12 }}>Valor (R$)<input style={input} value={valorTxt} inputMode="decimal" onChange={e => setValorTxt(e.target.value)} /></label>
        <label style={{ display: 'grid', gap: 4, fontSize: 12 }}>Prazo
          <select style={input} value={meses} onChange={e => setMeses(Number(e.target.value))}>
            {[3, 6, 12, 24, 36].map(m => <option key={m} value={m}>{m} meses</option>)}
          </select>
        </label>
      </div>

      {compQ.isLoading && <div style={nota}>Comparando…</div>}
      {compQ.isError && <div style={{ ...nota, color: '#b91c1c' }}>{describeError(compQ.error, 'Não foi possível comparar.').message}</div>}
      {compQ.data && (
        <div style={{ display: 'grid', gap: 6 }}>
          {compQ.data.entries.map(e => (
            <div key={e.label} style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 13, fontWeight: e.label === compQ.data!.winner ? 700 : 400 }}>
              <span>{e.label} <span style={nota}>· {pct(e.annual_rate_net_pct)} líquido · {rotuloLiquidez(e.liquidity)}{e.is_exempt ? ' · isento de IR' : ''}{e.fgc_covered ? ' · FGC' : ''}</span></span>
              <span>+{brl(e.net_yield_brl)}</span>
            </div>
          ))}
          <div style={{ fontSize: 13 }}>{compQ.data.recommendation}</div>
        </div>
      )}

      <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: 10, display: 'grid', gap: 6 }}>
        <strong style={{ fontSize: 13 }}>Banco que mais combina com você</strong>
        {bancoQ.isLoading && <div style={nota}>Montando o ranking…</div>}
        {erroBanco && <div style={nota}>{erroBanco.message}{erroBanco.kind === 'upgrade_required' && <> · <Link to="/planos">Ver planos</Link></>}</div>}
        {bancoQ.data && (
          <>
            <div style={{ fontSize: 13 }}>{bancoQ.data.switch_recommendation}</div>
            {bancoQ.data.ranking.slice(0, 3).map((b, i) => (
              <div key={b.bank_name} style={{ fontSize: 12 }}>
                <strong>{i + 1}. {b.bank_name}</strong>{b.is_user_current_bank ? ' (seu banco)' : ''} — nota {Math.round(b.match_score)} · {b.reasons[0]}
              </div>
            ))}
            {bancoQ.data.user_current_bank && bancoQ.data.user_current_bank_rank && bancoQ.data.user_current_bank_rank > 3 && (
              <div style={nota}>Seu {bancoQ.data.user_current_bank} está em {bancoQ.data.user_current_bank_rank}º.</div>
            )}
          </>
        )}
      </div>
      <div style={nota}>{compQ.data?.disclaimer || bancoQ.data?.disclaimer}</div>
    </div>
  );
};
