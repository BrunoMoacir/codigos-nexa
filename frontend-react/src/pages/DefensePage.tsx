import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { protecaoApi, ROTULO_SEVERIDADE } from '../api/protecao';
import type { AchadoDeDefesa } from '../api/protecao';
import { brl } from '../api/painel';
import { describeError } from '../api/errors';
import { getUserId } from '../api/session';

const card: React.CSSProperties = { background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 12, padding: 16 };
const nota: React.CSSProperties = { fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 };
const botao: React.CSSProperties = { border: '1px solid #111', background: 'var(--text-primary)', color: 'var(--bg-surface)', borderRadius: 8, padding: '8px 12px', fontSize: 13, cursor: 'pointer' };
const botaoSec: React.CSSProperties = { border: '1px solid var(--border-color)', background: 'var(--bg-surface)', color: 'var(--text-primary)', borderRadius: 8, padding: '6px 10px', fontSize: 12, cursor: 'pointer' };
const COR: Record<string, string> = { HIGH: '#b91c1c', MEDIUM: '#b45309', LOW: '#64748b' };

function Erro({ erro, fallback }: { erro: unknown; fallback: string }) {
  const e = describeError(erro, fallback);
  return <div style={{ ...nota, color: '#991b1b' }}>{e.message}{e.kind === 'upgrade_required' && <> · <Link to="/planos">Ver planos</Link></>}</div>;
}

function Achado({ a }: { a: AchadoDeDefesa }) {
  const [aberto, setAberto] = useState(false);
  return (
    <div style={{ border: '1px solid var(--border-color)', borderLeft: `3px solid ${COR[a.severity] || '#64748b'}`, borderRadius: 10, padding: 12, display: 'grid', gap: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
        <strong style={{ fontSize: 14 }}>{a.title}</strong>
        <span style={{ fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap' }}>{brl(a.amount_disputed)}</span>
      </div>
      <div style={nota}>{a.bank_name} · {ROTULO_SEVERIDADE[a.severity] || a.severity} · confiança {Math.round(a.confidence * 100)}%</div>
      <div style={{ fontSize: 13 }}>{a.description}</div>
      <div style={{ fontSize: 13 }}><strong>O que fazer:</strong> {a.recommended_action}</div>
      {a.requires_user_confirmation && <div style={{ ...nota, color: '#b45309' }}>Confirme no seu extrato antes de contestar — é um indício, não uma certeza.</div>}
      {a.estimated_vs_claimed && <div style={nota}>{a.estimated_vs_claimed}</div>}
      <button style={{ ...botaoSec, justifySelf: 'start' }} onClick={() => setAberto(v => !v)}>{aberto ? 'Ocultar base legal e provas' : 'Ver base legal e provas'}</button>
      {aberto && (
        <div style={{ display: 'grid', gap: 4 }}>
          <div style={nota}><strong>Base legal:</strong> {a.legal_basis}</div>
          {a.evidence_points.length > 0 && <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12 }}>{a.evidence_points.map((p, i) => <li key={i}>{p}</li>)}</ul>}
        </div>
      )}
    </div>
  );
}

// Era um esqueleto: os detectores D1–D6 e o dossiê (carta, PROCON, JEC)
// existiam no backend sem nenhum caminho na interface.
export const DefensePage: React.FC = () => {
  const userId = getUserId();
  const defesaQ = useQuery({ queryKey: ['defesa', userId], queryFn: () => protecaoApi.defesa(userId), enabled: !!userId, retry: false });
  const portQ = useQuery({ queryKey: ['defesa', 'portabilidade', userId], queryFn: () => protecaoApi.portabilidade(userId), enabled: !!userId, retry: false });
  const [doc, setDoc] = useState<'contestation_letter' | 'procon_narrative' | 'jec_petition'>('contestation_letter');
  const dossieM = useMutation({ mutationFn: () => protecaoApi.dossie(userId) });
  const zipM = useMutation({ mutationFn: () => protecaoApi.baixarDossie(userId) });

  const d = defesaQ.data;
  return (
    <AppShell current="defesa" title="Defesa do consumidor" subtitle="Cobranças indevidas, venda casada, juros abusivos — e os documentos para contestar.">
      <div style={{ display: 'grid', gap: 12 }}>
        <div style={card}>
          {defesaQ.isLoading && <div style={nota}>Analisando seu extrato…</div>}
          {defesaQ.isError && <Erro erro={defesaQ.error} fallback="Não foi possível analisar seu extrato." />}
          {d && (
            <div style={{ display: 'grid', gap: 10 }}>
              <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                <div><div style={nota}>Valor contestável</div><div style={{ fontSize: 24, fontWeight: 800 }}>{brl(d.total_disputed_amount)}</div></div>
                <div><div style={nota}>Indícios</div><div style={{ fontSize: 24, fontWeight: 800 }}>{d.total_findings}</div></div>
                <div><div style={nota}>Graves</div><div style={{ fontSize: 24, fontWeight: 800, color: d.high_severity ? '#b91c1c' : undefined }}>{d.high_severity}</div></div>
              </div>
              <div style={{ fontSize: 13 }}>{d.summary}</div>
              {d.total_findings === 0 && <div style={nota}>Nenhum indício de cobrança indevida no seu extrato. A análise roda de novo a cada sincronização.</div>}
              <div style={{ display: 'grid', gap: 8 }}>{d.findings.map((a, i) => <Achado key={`${a.detector}-${i}`} a={a} />)}</div>
              <div style={nota}>{d.disclaimer}</div>
            </div>
          )}
        </div>

        {d && d.total_findings > 0 && (
          <div style={card}>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>Documentos para contestar</div>
            <div style={nota}>Carta ao banco, relato para o PROCON / consumidor.gov.br e um modelo de petição para o Juizado Especial Cível. São modelos — revise antes de enviar.</div>
            <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
              <button style={botao} disabled={zipM.isPending} onClick={() => zipM.mutate()}>{zipM.isPending ? 'Gerando…' : 'Baixar todos (ZIP)'}</button>
              <button style={botaoSec} disabled={dossieM.isPending} onClick={() => dossieM.mutate()}>{dossieM.isPending ? 'Gerando…' : 'Ler aqui'}</button>
            </div>
            {zipM.isError && <Erro erro={zipM.error} fallback="Não foi possível gerar o ZIP." />}
            {dossieM.isError && <Erro erro={dossieM.error} fallback="Não foi possível gerar o dossiê." />}
            {dossieM.data && (
              <div style={{ marginTop: 10 }}>
                <div style={{ display: 'flex', gap: 6, marginBottom: 8, flexWrap: 'wrap' }}>
                  {([['contestation_letter', 'Carta ao banco'], ['procon_narrative', 'PROCON'], ['jec_petition', 'Juizado (JEC)']] as const).map(([k, rot]) => (
                    <button key={k} style={{ ...botaoSec, fontWeight: doc === k ? 700 : 400 }} onClick={() => setDoc(k)}>{rot}</button>
                  ))}
                  <button style={botaoSec} onClick={() => navigator.clipboard?.writeText(dossieM.data[doc])}>Copiar</button>
                </div>
                <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, lineHeight: 1.5, background: 'var(--bg-hover)', borderRadius: 8, padding: 12, maxHeight: 420, overflow: 'auto', margin: 0 }}>{dossieM.data[doc]}</pre>
                <div style={{ ...nota, marginTop: 6 }}>{dossieM.data.disclaimer}</div>
              </div>
            )}
          </div>
        )}

        <div style={card}>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>Portabilidade de crédito</div>
          {portQ.isLoading && <div style={nota}>Comparando suas taxas com o mercado…</div>}
          {portQ.isError && <Erro erro={portQ.error} fallback="Não foi possível analisar portabilidade." />}
          {portQ.data && (
            <div style={{ display: 'grid', gap: 8 }}>
              <div style={{ fontSize: 13 }}>{portQ.data.summary}</div>
              {portQ.data.findings.map((a, i) => <Achado key={`p-${i}`} a={a} />)}
              {portQ.data.total_findings === 0 && <div style={nota}>Nenhuma dívida com taxa acima do mercado que valha portar.</div>}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
};
