import { useCallback, useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { AppShell } from '../components/layout/AppShell';
import { painelApi, dataLonga, diasDesde, ROTULO_ORIGEM } from '../api/painel';
import { conexoesApi, htmlDoWidget } from '../api/conexoes';
import { followSyncJob, pluggySyncApi } from '../api/pluggySync';
import type { SyncJobState } from '../api/pluggySync';
import { describeError, getErrorMessage } from '../api/errors';
import { getUserId } from '../api/session';

const card: React.CSSProperties = {
  background: 'var(--bg-surface)',
  border: '1px solid var(--border-color)',
  borderRadius: 12,
  padding: 18,
};
const button: React.CSSProperties = {
  border: '1px solid #111',
  background: 'var(--text-primary)',
  color: 'var(--bg-surface)',
  borderRadius: 8,
  padding: '10px 12px',
  fontSize: 13,
  cursor: 'pointer',
};
const rotulo: React.CSSProperties = { fontSize: 11, letterSpacing: 0.8, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8, fontWeight: 600 };
const faixa = (cor: 'erro' | 'aviso' | 'info'): React.CSSProperties => ({
  fontSize: 12, borderRadius: 8, padding: 10, marginBottom: 10,
  ...(cor === 'erro' ? { color: '#991b1b', background: '#fef2f2', border: '1px solid #fecaca' }
    : cor === 'aviso' ? { color: '#92400e', background: '#fffbeb', border: '1px solid #fde68a' }
      : { color: '#1d4ed8', background: '#eff6ff', border: '1px solid #bfdbfe' }),
});

/** Dados que dependem do extrato: invalidar depois de um sync. */
const CHAVES_DO_EXTRATO = [['painel'], ['organizar'], ['feed'], ['metas'], ['goals'], ['estrategias'], ['optimizer'], ['fiscal'], ['costs'], ['peers']];

export const ConnectionsPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [perfMultiplier, setPerfMultiplier] = useState(100);
  const [widget, setWidget] = useState<{ token: string; atualizar?: string } | null>(null);
  const [widgetErro, setWidgetErro] = useState('');
  const [syncProgress, setSyncProgress] = useState<SyncJobState | null>(null);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);

  // Lista persistida: funciona mesmo sem credenciais da Pluggy (o /items
  // responde 503 e a tela dizia "Nenhuma conta conectada").
  const conexoesQ = useQuery({ queryKey: ['pluggy', 'conexoes'], queryFn: painelApi.conexoes });
  const conexoes = conexoesQ.data?.connections || [];
  const qualidadeQ = useQuery({
    queryKey: ['pluggy', 'qualidade', getUserId()],
    queryFn: () => conexoesApi.qualidade(getUserId()),
    enabled: conexoes.length > 0, retry: false,
  });
  const pluggyOk = conexoesQ.data?.pluggy_configured ?? false;

  const terminarSync = useCallback((state: SyncJobState) => {
    if (state.status === 'ERROR') {
      // a mensagem de progresso ("Baixando transações…") aparecia como erro
      toast.error(state.error || state.message || 'Falha ao sincronizar transações.');
      return;
    }
    const totais = state.totals || { saved: 0, accounts: 0 };
    (state.status === 'PARTIAL' ? toast : toast.success)(
      state.message || `Sincronizado: ${totais.saved} lançamentos em ${totais.accounts} conta(s).`,
    );
    conexoesQ.refetch();
    qualidadeQ.refetch();
    CHAVES_DO_EXTRATO.forEach(queryKey => queryClient.invalidateQueries({ queryKey }));
  }, [conexoesQ, qualidadeQ, queryClient]);

  const acompanhar = useCallback(async (job: SyncJobState): Promise<SyncJobState> => {
    setSyncProgress(job);
    if (job.done) return job;
    return followSyncJob({ jobId: job.job_id, cursor: job.cursor, onState: setSyncProgress });
  }, []);

  const syncMutation = useMutation({
    mutationFn: async (jobExistente?: SyncJobState) => acompanhar(jobExistente ?? await pluggySyncApi.startSyncJob()),
    onSuccess: terminarSync,
    onError: (err) => toast.error(getErrorMessage(err, 'Falha ao sincronizar transações.')),
    onSettled: () => setSyncProgress(null),
  });

  // Sync em andamento é retomado ao reabrir a tela (antes se perdia o progresso).
  const retomado = useRef(false);
  useEffect(() => {
    if (retomado.current || !pluggyOk) return;
    retomado.current = true;
    pluggySyncApi.listSyncJobs(1)
      .then(({ jobs }) => { if (jobs[0] && !jobs[0].done) syncMutation.mutate(jobs[0]); })
      .catch(() => { /* histórico indisponível: nada a retomar */ });
  }, [pluggyOk, syncMutation]);

  const salvarItemM = useMutation({
    mutationFn: ({ itemId, conector }: { itemId: string; conector?: string | null }) => conexoesApi.salvarItem(itemId, conector),
    onSuccess: () => {
      toast.success('Banco conectado. Buscando os lançamentos…');
      setWidget(null);
      conexoesQ.refetch();
      syncMutation.mutate(undefined);
    },
    onError: (err) => setWidgetErro(`O banco conectou, mas não conseguimos registrar a conexão: ${getErrorMessage(err)}`),
  });

  // O iframe só repassa o resultado; quem registra é o app, com a sessão atual.
  useEffect(() => {
    const handler = (event: MessageEvent) => {
      if (event.source !== iframeRef.current?.contentWindow) return;
      const msg = event.data;
      if (!msg || typeof msg !== 'object' || msg.origem !== 'hive-pluggy') return;
      if (msg.type === 'pluggy-success' && msg.itemId) {
        setWidgetErro('');
        salvarItemM.mutate({ itemId: String(msg.itemId), conector: msg.connectorName });
      } else if (msg.type === 'pluggy-error') {
        setWidgetErro(`Erro da Pluggy${msg.code ? ` (${msg.code})` : ''}: ${msg.message || 'falha ao conectar a conta.'}`);
      } else if (msg.type === 'pluggy-close') {
        setWidget(null);
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [salvarItemM]);

  const tokenMutation = useMutation({
    mutationFn: (atualizar?: string) => conexoesApi.tokenDoWidget().then(token => ({ token, atualizar })),
    onSuccess: (w) => { setWidgetErro(''); setWidget(w); },
    onError: (err) => toast.error(getErrorMessage(err, 'Não foi possível abrir o widget da Pluggy.')),
  });

  const sandboxMutation = useMutation({
    mutationFn: async () => {
      const { job } = await conexoesApi.criarSandbox(perfMultiplier);
      // o sync do sandbox também é um job — antes o app dizia "criado com
      // sucesso" e ignorava o resultado do sync
      return job ? acompanhar(job) : null;
    },
    onSuccess: (state) => {
      toast('Sandbox ativo: os lançamentos são fictícios, para teste.', { icon: '⚠️' });
      if (state) terminarSync(state); else conexoesQ.refetch();
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Não foi possível criar o item sandbox.')),
    onSettled: () => setSyncProgress(null),
  });

  const ocupado = syncMutation.isPending || sandboxMutation.isPending;

  return (
    <AppShell current="connections" title="Conexões Open Finance" subtitle="Bancos conectados via Pluggy e sincronização do extrato.">
      {conexoesQ.isError && (
        <div style={faixa('erro')}>
          {getErrorMessage(conexoesQ.error, 'Não foi possível carregar suas conexões.')}{' '}
          <button style={{ ...button, padding: '4px 10px', fontSize: 12 }} onClick={() => conexoesQ.refetch()}>Tentar de novo</button>
        </div>
      )}
      {conexoesQ.data && !pluggyOk && (
        <div style={faixa('aviso')}>
          O Open Finance não está configurado neste servidor (faltam as credenciais da Pluggy). Dá para ver as conexões já registradas, mas conectar banco, sincronizar e criar sandbox ficam indisponíveis.
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 12, marginBottom: 12 }}>
        <div style={card}>
          <div style={rotulo}>Bancos conectados</div>
          {conexoesQ.data && <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 10 }}>Origem dos dados: <strong>{ROTULO_ORIGEM[conexoesQ.data.data_source]}</strong></div>}
          {conexoesQ.isLoading && <p style={{ color: 'var(--text-muted)' }}>Carregando conexões…</p>}
          {conexoesQ.data && conexoes.length === 0 && <p style={{ color: 'var(--text-muted)' }}>Nenhum banco conectado ainda.</p>}
          {qualidadeQ.data && (
            <div style={{ fontSize: 12, color: qualidadeQ.data.total_rejeitadas > 0 ? '#b45309' : 'var(--text-muted)', marginBottom: 10 }}>
              Qualidade do extrato (últimos 7 dias): {qualidadeQ.data.diagnostico}
            </div>
          )}
          {conexoes.map(c => {
            const diasParaVencer = c.consent_expires_estimate ? -(diasDesde(c.consent_expires_estimate) ?? 0) : null;
            const vencendo = diasParaVencer !== null && diasParaVencer <= 30;
            return (
              <div key={c.item_id} style={{ border: '1px solid var(--border-color)', borderRadius: 10, padding: 12, marginBottom: 8, display: 'grid', gap: 4 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                  <strong style={{ fontSize: 14 }}>{c.connector_name || 'Banco'}</strong>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{ROTULO_ORIGEM[c.source]}</span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  Conectado em {dataLonga(c.connected_at?.slice(0, 10))}
                  {c.consent_expires_estimate && <> · consentimento até ~{dataLonga(c.consent_expires_estimate)}</>}
                </div>
                {vencendo && c.source === 'open_finance' && (
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 12, color: '#b45309' }}>{diasParaVencer! <= 0 ? 'Consentimento vencido' : `Vence em ${diasParaVencer} dia(s)`}</span>
                    <button style={{ ...button, padding: '4px 10px', fontSize: 12 }} disabled={!pluggyOk || tokenMutation.isPending}
                      onClick={() => tokenMutation.mutate(c.item_id)}>Renovar consentimento</button>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div style={card}>
          <div style={rotulo}>Ações</div>
          <div style={{ display: 'grid', gap: 8 }}>
            <button style={button} onClick={() => tokenMutation.mutate(undefined)} disabled={!pluggyOk || tokenMutation.isPending}>
              {tokenMutation.isPending ? 'Abrindo widget…' : 'Conectar um banco'}
            </button>
            <button style={button} onClick={() => syncMutation.mutate(undefined)} disabled={!pluggyOk || ocupado || conexoes.length === 0}>
              {syncMutation.isPending ? `Sincronizando… ${syncProgress?.progress ?? 0}%` : 'Sincronizar extrato'}
            </button>
          </div>

          {syncProgress && (
            <div style={{ marginTop: 12 }}>
              <div style={{ height: 6, background: 'var(--border-color)', borderRadius: 999 }}>
                <div style={{ height: 6, width: `${syncProgress.progress}%`, background: 'var(--text-primary)', borderRadius: 999, transition: 'width 240ms ease' }} />
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 6 }}>
                {syncProgress.message || 'Sincronizando…'}
                {syncProgress.items.total > 1 && ` (${syncProgress.items.done}/${syncProgress.items.total} conexões)`}
              </div>
            </div>
          )}

          <div style={{ marginTop: 14, borderTop: '1px solid var(--border-color)', paddingTop: 12 }}>
            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>Sandbox da Pluggy (teste)</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>Cria um banco fictício com lançamentos de teste.</div>
            <select value={perfMultiplier} onChange={(e) => setPerfMultiplier(Number(e.target.value))} aria-label="Volume do sandbox"
              style={{ width: '100%', padding: 9, border: '1px solid var(--border-color)', borderRadius: 8, marginBottom: 8 }}>
              <option value={1}>Padrão (1x)</option>
              <option value={100}>Médio (100x)</option>
              <option value={500}>Alto (500x)</option>
              <option value={1000}>Stress (1000x)</option>
            </select>
            <button style={{ ...button, width: '100%' }} onClick={() => sandboxMutation.mutate()} disabled={!pluggyOk || ocupado}>
              {sandboxMutation.isPending ? 'Criando sandbox…' : 'Criar banco sandbox'}
            </button>
          </div>
        </div>
      </div>

      {widget && (
        <div style={card}>
          <div style={rotulo}>{widget.atualizar ? 'Renovar consentimento' : 'Conectar banco'}</div>
          <div style={faixa('aviso')}>
            Se o widget mostrar "Aplicação demo", a Pluggy pode estar permitindo só o sandbox neste ambiente.
          </div>
          {widgetErro && <div style={faixa('erro')}>{widgetErro}</div>}
          {salvarItemM.isPending && <div style={faixa('info')}>Registrando a conexão…</div>}
          <iframe
            ref={iframeRef}
            title="pluggy-connect"
            srcDoc={htmlDoWidget(widget.token, widget.atualizar)}
            style={{ width: '100%', height: 660, border: '1px solid var(--border-color)', borderRadius: 10 }}
          />
        </div>
      )}
      {tokenMutation.isError && describeError(tokenMutation.error).kind === 'unavailable' && (
        <div style={faixa('aviso')}>{getErrorMessage(tokenMutation.error)}</div>
      )}
    </AppShell>
  );
};
