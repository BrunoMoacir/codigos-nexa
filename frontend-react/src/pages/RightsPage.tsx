import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { AppShell } from '../components/layout/AppShell';
import { protecaoApi } from '../api/protecao';
import type { Direito } from '../api/protecao';
import { brl } from '../api/painel';
import { getErrorMessage } from '../api/errors';
import { getUserId } from '../api/session';

const card: React.CSSProperties = { background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 12, padding: 16 };
const nota: React.CSSProperties = { fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 };
const botao: React.CSSProperties = { border: '1px solid #111', background: 'var(--text-primary)', color: 'var(--bg-surface)', borderRadius: 8, padding: '8px 12px', fontSize: 13, cursor: 'pointer' };
const input: React.CSSProperties = { border: '1px solid var(--border-color)', borderRadius: 8, padding: 8 };
const ok: React.CSSProperties = { fontSize: 13, color: '#166534', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 8, padding: 10 };
const erro: React.CSSProperties = { ...nota, color: '#991b1b' };

/** Consulta do SVR/BACEN com o desafio de segurança respondido pelo usuário. */
function ConsultaSvr({ userId }: { userId: string }) {
  const [cpf, setCpf] = useState('');
  const [nasc, setNasc] = useState('');
  const [resposta, setResposta] = useState('');
  const captchaM = useMutation({ mutationFn: () => protecaoApi.captchaSvr(userId) });
  const consultaM = useMutation({
    mutationFn: () => protecaoApi.consultarSvr(userId, {
      cpf: cpf.replace(/\D/g, ''), data_nascimento: nasc, captcha_hash: captchaM.data!.hash, captcha_resposta: resposta.trim(),
    }),
    onError: () => { setResposta(''); captchaM.mutate(); }, // o desafio vale uma tentativa
  });

  if (consultaM.data) {
    return (
      <div style={{ display: 'grid', gap: 6 }}>
        <div style={consultaM.data.tem_valor_a_receber ? ok : { ...nota, fontSize: 13 }}>
          {consultaM.data.tem_valor_a_receber ? 'Há valores a receber em seu nome!' : 'Nenhum valor a receber hoje.'} ({consultaM.data.consultado_em_nome_de})
        </div>
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12 }}>{consultaM.data.proximos_passos.map((p, i) => <li key={i}>{p}</li>)}</ul>
        <div style={nota}>Fonte: {consultaM.data.fonte}</div>
      </div>
    );
  }
  return (
    <div style={{ display: 'grid', gap: 8 }}>
      <div style={nota}>A consulta é feita no serviço público do Banco Central. CPF e data de nascimento não ficam guardados na HIVE.</div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <input style={input} placeholder="CPF" inputMode="numeric" value={cpf} onChange={e => setCpf(e.target.value)} aria-label="CPF" />
        <input style={input} type="date" value={nasc} onChange={e => setNasc(e.target.value)} aria-label="Data de nascimento" />
      </div>
      {!captchaM.data ? (
        <button style={{ ...botao, justifySelf: 'start' }} disabled={captchaM.isPending || cpf.replace(/\D/g, '').length !== 11 || !nasc}
          onClick={() => captchaM.mutate()}>{captchaM.isPending ? 'Carregando…' : 'Continuar'}</button>
      ) : (
        <div style={{ display: 'grid', gap: 6 }}>
          <img src={`data:image/png;base64,${captchaM.data.imagem_base64}`} alt="Desafio de segurança do Banco Central" style={{ maxWidth: 220, border: '1px solid var(--border-color)', borderRadius: 6 }} />
          <div style={nota}>{captchaM.data.instrucao}</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <input style={input} value={resposta} onChange={e => setResposta(e.target.value)} placeholder="Caracteres da imagem" aria-label="Resposta do desafio" />
            <button style={botao} disabled={!resposta.trim() || consultaM.isPending} onClick={() => consultaM.mutate()}>{consultaM.isPending ? 'Consultando…' : 'Consultar'}</button>
          </div>
        </div>
      )}
      {captchaM.isError && <div style={erro}>{getErrorMessage(captchaM.error, 'O serviço do Banco Central não respondeu.')}</div>}
      {consultaM.isError && <div style={erro}>{getErrorMessage(consultaM.error, 'A consulta falhou.')} Um novo desafio foi carregado.</div>}
    </div>
  );
}

/** Restituição do IR via autorização gerada pelo próprio usuário no e-CAC. */
function ConsultaIr({ userId }: { userId: string }) {
  const [token, setToken] = useState('');
  const m = useMutation({ mutationFn: () => protecaoApi.consultarIr(userId, token.trim()) });
  return (
    <div style={{ display: 'grid', gap: 8 }}>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <input style={{ ...input, minWidth: 260 }} value={token} onChange={e => setToken(e.target.value)} placeholder="Token de compartilhamento do e-CAC" aria-label="Token do e-CAC" />
        <button style={botao} disabled={!token.trim() || m.isPending} onClick={() => m.mutate()}>{m.isPending ? 'Consultando…' : 'Consultar restituição'}</button>
      </div>
      {m.isError && <div style={erro}>{getErrorMessage(m.error, 'A consulta à Receita falhou.')}</div>}
      {m.data && (
        <div style={{ display: 'grid', gap: 4 }}>
          <div style={m.data.status === 'encontrada' ? ok : { fontSize: 13 }}>
            {m.data.status === 'encontrada' ? `Restituição encontrada${m.data.valor != null ? `: ${brl(m.data.valor)}` : ''}`
              : m.data.status === 'sem_restituicao' ? 'Nenhuma restituição pendente.'
                : 'A consulta à Receita ainda não está configurada neste servidor.'}
          </div>
          {m.data.situacao_descricao && <div style={nota}>{m.data.situacao_descricao}</div>}
          {m.data.detalhe && <div style={nota}>{m.data.detalhe}</div>}
          {m.data.proximos_passos.length > 0 && <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12 }}>{m.data.proximos_passos.map((p, i) => <li key={i}>{p}</li>)}</ul>}
        </div>
      )}
    </div>
  );
}

function CardDireito({ d, userId }: { d: Direito; userId: string }) {
  return (
    <div style={{ ...card, display: 'grid', gap: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
        <strong style={{ fontSize: 14 }}>{d.title}</strong>
        {d.estimated_amount != null && <strong>{brl(d.estimated_amount)}</strong>}
      </div>
      <div style={{ fontSize: 13 }}>{d.description}</div>
      {d.relevance_reason && <div style={nota}>{d.relevance_reason}</div>}
      {d.category === 'svr_bacen' && d.capability === 'assisted_real' ? <ConsultaSvr userId={userId} />
        : d.category === 'ir_restituicao' ? (
          <>
            <ol style={{ margin: 0, paddingLeft: 18, fontSize: 12 }}>{d.action_steps.map((p, i) => <li key={i}>{p}</li>)}</ol>
            <ConsultaIr userId={userId} />
          </>
        ) : (
          <ol style={{ margin: 0, paddingLeft: 18, fontSize: 12 }}>{d.action_steps.map((p, i) => <li key={i}>{p}</li>)}</ol>
        )}
      <div style={nota}>
        Canal oficial: <a href={d.official_url} target="_blank" rel="noopener noreferrer">{d.official_channel}</a>
        {d.warning && <> · {d.warning}</>}
      </div>
    </div>
  );
}

// Era um esqueleto: SVR/BACEN com desafio, restituição via e-CAC, FGTS e PIS
// existiam só no backend.
export const RightsPage: React.FC = () => {
  const userId = getUserId();
  const q = useQuery({ queryKey: ['direitos', userId], queryFn: () => protecaoApi.direitos(userId), enabled: !!userId });
  return (
    <AppShell current="direitos" title="Direitos esquecidos" subtitle="Dinheiro esquecido em bancos, restituição do IR, FGTS e PIS — consultado nos canais oficiais.">
      <div style={{ display: 'grid', gap: 12 }}>
        {q.isLoading && <div style={card}><span style={nota}>Carregando…</span></div>}
        {q.isError && <div style={card}><span style={erro}>{getErrorMessage(q.error, 'Não foi possível carregar.')}</span></div>}
        {q.data?.context_note && <div style={{ ...card, fontSize: 13 }}>{q.data.context_note}</div>}
        {q.data?.rights.map(d => <CardDireito key={d.category} d={d} userId={userId} />)}
        {q.data && <div style={nota}>{q.data.disclaimer}</div>}
      </div>
    </AppShell>
  );
};
