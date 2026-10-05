import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { AppShell } from '../components/layout/AppShell';
import { protecaoApi } from '../api/protecao';
import { brl } from '../api/painel';
import { ROTULO_SELO } from '../api/organizar';
import { getErrorMessage } from '../api/errors';
import { getUserId } from '../api/session';

const card: React.CSSProperties = { background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 12, padding: 16 };
const nota: React.CSSProperties = { fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 };
const botao: React.CSSProperties = { border: '1px solid #111', background: 'var(--text-primary)', color: 'var(--bg-surface)', borderRadius: 8, padding: '8px 12px', fontSize: 13, cursor: 'pointer' };
const botaoSec: React.CSSProperties = { border: '1px solid var(--border-color)', background: 'var(--bg-surface)', color: 'var(--text-primary)', borderRadius: 8, padding: '8px 12px', fontSize: 13, cursor: 'pointer' };

/** Imagem do card buscada com o token da sessão (<img src> direto levaria 401). */
function useImagem(caminho: string, ativo: boolean) {
  const q = useQuery({ queryKey: ['viral', 'img', caminho], queryFn: () => protecaoApi.imagem(caminho), enabled: ativo, staleTime: 10 * 60 * 1000 });
  const url = useMemo(() => (q.data ? URL.createObjectURL(q.data) : null), [q.data]);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  return { url, blob: q.data, erro: q.error };
}

function Compartilhar({ userId, card: tipo, blob, nome }: { userId: string; card: 'savings_card' | 'wrapped'; blob?: Blob; nome: string }) {
  const m = useMutation({
    mutationFn: async () => {
      if (!blob) return 'sem-imagem';
      const arquivo = new File([blob], nome, { type: blob.type || 'image/svg+xml' });
      const nav = navigator as Navigator & { canShare?: (d: ShareData) => boolean };
      if (nav.share && nav.canShare?.({ files: [arquivo] })) {
        await nav.share({ files: [arquivo], title: 'Meu resumo na HIVE' });
        await protecaoApi.registrarCompartilhamento(userId, tipo, 'web_share');
        return 'compartilhado';
      }
      protecaoApi.baixar(blob, nome);
      await protecaoApi.registrarCompartilhamento(userId, tipo, 'download');
      return 'baixado';
    },
  });
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
      <button style={botao} disabled={!blob || m.isPending} onClick={() => m.mutate()}>{m.isPending ? '…' : 'Compartilhar imagem'}</button>
      {m.data === 'baixado' && <span style={nota}>Imagem baixada — é só postar.</span>}
      {m.isError && <span style={{ ...nota, color: '#991b1b' }}>{getErrorMessage(m.error, 'Não foi possível compartilhar.')}</span>}
    </div>
  );
}

// Era um esqueleto: Placar de Economia (V1) e Wrapped do ano (V2) não tinham
// tela de geração nem de compartilhamento.
export const WrappedPage: React.FC = () => {
  const userId = getUserId();
  const anoAtual = new Date().getFullYear();
  const [ano, setAno] = useState(anoAtual);
  const wrappedQ = useQuery({ queryKey: ['viral', 'wrapped', userId, ano], queryFn: () => protecaoApi.wrapped(userId, ano), enabled: !!userId });
  const placarQ = useQuery({ queryKey: ['viral', 'placar', userId], queryFn: () => protecaoApi.placar(userId), enabled: !!userId });
  const imgWrapped = useImagem(`/viral/wrapped/${userId}/${ano}/svg`, !!userId);
  const imgPlacar = useImagem(`/viral/savings-card/${userId}/svg`, !!userId);

  const w = wrappedQ.data;
  return (
    <AppShell current="wrapped" title="Seu ano na HIVE" subtitle="O que você pagou, o que dá para recuperar e o que conquistou.">
      <div style={{ display: 'grid', gap: 12 }}>
        <div style={card}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
            <div style={{ fontWeight: 700 }}>Wrapped {ano}{w?.is_partial_year ? ' (até agora)' : ''}</div>
            <div style={{ display: 'flex', gap: 6 }}>
              {[anoAtual - 1, anoAtual].map(a => (
                <button key={a} style={{ ...botaoSec, fontWeight: a === ano ? 700 : 400 }} onClick={() => setAno(a)}>{a}</button>
              ))}
            </div>
          </div>
          {wrappedQ.isLoading && <div style={nota}>Montando sua retrospectiva…</div>}
          {wrappedQ.isError && <div style={{ ...nota, color: '#991b1b' }}>{getErrorMessage(wrappedQ.error, 'Não foi possível gerar o Wrapped.')}</div>}
          {w && (
            <div style={{ display: 'grid', gap: 10 }}>
              <div style={{ fontSize: 15 }}>{w.summary_tagline}</div>
              <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                <div><div style={nota}>Tarifas pagas no ano</div><div style={{ fontSize: 20, fontWeight: 800 }}>{brl(w.total_fees_paid_year)}</div></div>
                <div><div style={nota}>Economia identificada</div><div style={{ fontSize: 20, fontWeight: 800 }}>{brl(w.total_savings_identified)}</div></div>
                {w.score_delta != null && <div><div style={nota}>Score Nexa</div><div style={{ fontSize: 20, fontWeight: 800 }}>{w.score_start} → {w.score_end}</div></div>}
              </div>
              {w.highlights.map((h, i) => (
                <div key={i} style={{ borderTop: '1px solid var(--border-color)', paddingTop: 8 }}>
                  <div style={{ fontSize: 13, fontWeight: 700 }}>{h.title}: {h.value_formatted}</div>
                  <div style={nota}>{h.description}</div>
                </div>
              ))}
              {w.badges_earned.length > 0 && <div style={{ fontSize: 13 }}>Conquistas: {w.badges_earned.map(b => ROTULO_SELO[b] || b).join(', ')}</div>}
              {imgWrapped.url && <img src={imgWrapped.url} alt={`Card do Wrapped ${ano}`} style={{ maxWidth: 360, width: '100%', borderRadius: 12 }} />}
              <Compartilhar userId={userId} card="wrapped" blob={imgWrapped.blob} nome={`hive-wrapped-${ano}.svg`} />
              <div style={nota}>{w.disclaimer}</div>
            </div>
          )}
        </div>

        <div style={card}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>Placar de economia</div>
          {placarQ.isError && <div style={{ ...nota, color: '#991b1b' }}>{getErrorMessage(placarQ.error, 'Não foi possível gerar o placar.')}</div>}
          {placarQ.data && (
            <div style={{ display: 'grid', gap: 8 }}>
              <div style={{ fontSize: 22, fontWeight: 800 }}>{brl(placarQ.data.total_annual_savings_brl)}/ano</div>
              <div style={{ fontSize: 13 }}>{placarQ.data.tagline}</div>
              {placarQ.data.sources.map((s, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                  <span>{s.name}</span><strong>{brl(s.annual_savings_brl)}</strong>
                </div>
              ))}
              {imgPlacar.url && <img src={imgPlacar.url} alt="Card do placar de economia" style={{ maxWidth: 360, width: '100%', borderRadius: 12 }} />}
              <Compartilhar userId={userId} card="savings_card" blob={imgPlacar.blob} nome="hive-placar.svg" />
              <div style={nota}>{placarQ.data.disclaimer}</div>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
};
