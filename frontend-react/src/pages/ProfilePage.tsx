import React, { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { AppShell } from '../components/layout/AppShell';
import { contaApi, FRASE_DE_EXCLUSAO } from '../api/conta';
import type { Canal, Frequencia, Preferencias } from '../api/conta';
import { painelApi, ROTULO_ORIGEM } from '../api/painel';
import { logout, logoutAll } from '../api/auth';
import { getErrorMessage } from '../api/errors';
import { session } from '../api/session';
import { getPushState, subscribeToPush, unsubscribeFromPush } from '../pwa/push';
import type { PushState } from '../pwa/push';

const card: React.CSSProperties = { background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 12, padding: 16 };
const label: React.CSSProperties = { fontSize: 11, letterSpacing: 0.8, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8, fontWeight: 600 };
const nota: React.CSSProperties = { fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 };
const botao: React.CSSProperties = { border: '1px solid #111', background: 'var(--text-primary)', color: 'var(--bg-surface)', borderRadius: 8, padding: '8px 12px', fontSize: 13, cursor: 'pointer' };
const botaoSec: React.CSSProperties = { border: '1px solid var(--border-color)', background: 'var(--bg-surface)', color: 'var(--text-primary)', borderRadius: 8, padding: '8px 12px', fontSize: 13, cursor: 'pointer' };
const perigo: React.CSSProperties = { ...botao, background: '#b91c1c', borderColor: '#991b1b', color: '#fff' };

const CANAIS: [Canal, string][] = [['in_app', 'No app'], ['email', 'E-mail'], ['push', 'Notificação no celular/navegador']];
const FREQUENCIAS: [Frequencia, string][] = [['realtime', 'Na hora'], ['daily', 'Resumo diário'], ['weekly', 'Resumo semanal'], ['off', 'Desligado']];
const ROTULO_PUSH: Record<PushState, string> = {
  unsupported: 'Este navegador não recebe notificações push.',
  'not-configured': 'Alertas push ainda não estão configurados no servidor.',
  denied: 'Notificações bloqueadas nas configurações do navegador.',
  subscribed: 'Ativados neste aparelho.',
  unsubscribed: 'Desativados neste aparelho.',
};

// O Perfil dizia "Logado" se houvesse qualquer texto em jwt_token (mesmo
// vencido) e "Dados reais" por uma flag local; não havia como mexer nas
// preferências, exportar ou apagar os dados, nem sair de outros aparelhos.
export const ProfilePage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const userId = session.userId;
  const email = session.userEmail;
  const nome = session.userName || (email.includes('@') ? email.split('@')[0] : 'Usuário');

  const conexoesQ = useQuery({ queryKey: ['pluggy', 'conexoes'], queryFn: painelApi.conexoes, enabled: !!userId });
  const assinaturaQ = useQuery({ queryKey: ['billing', 'assinatura', userId], queryFn: () => contaApi.assinatura(userId), enabled: !!userId });
  const prefsQ = useQuery({ queryKey: ['settings', userId], queryFn: () => contaApi.preferencias(userId), enabled: !!userId });

  const [prefs, setPrefs] = useState<Preferencias | null>(null);
  useEffect(() => { if (prefsQ.data) setPrefs(prefsQ.data); }, [prefsQ.data]);
  const salvarM = useMutation({
    mutationFn: (p: Preferencias) => contaApi.salvarPreferencias(userId, {
      notification_channels: p.notification_channels,
      notification_frequency: p.notification_frequency,
      digest_time: p.digest_time,
    }),
    onSuccess: (p) => { queryClient.setQueryData(['settings', userId], p); toast.success('Preferências salvas.'); },
  });

  const [push, setPush] = useState<PushState>('unsupported');
  const [pushBusy, setPushBusy] = useState(false);
  useEffect(() => { getPushState().then(setPush).catch(() => setPush('unsupported')); }, []);
  const alternarPush = async () => {
    setPushBusy(true);
    try {
      setPush(push === 'subscribed' ? await unsubscribeFromPush() : await subscribeToPush());
    } catch (err) {
      toast.error(getErrorMessage(err, 'Não foi possível mudar os alertas push.'));
    } finally {
      setPushBusy(false);
    }
  };

  const exportarM = useMutation({
    mutationFn: () => contaApi.exportarDados(userId),
    onSuccess: () => toast.success('Arquivo com seus dados baixado.'),
  });
  const [frase, setFrase] = useState('');
  const excluirM = useMutation({
    mutationFn: () => contaApi.excluirDados(userId, frase.trim()),
    onSuccess: () => {
      session.clear();
      queryClient.clear();
      toast.success('Sua conta e seus dados foram apagados.');
      navigate('/login', { replace: true });
    },
  });
  const sairM = useMutation({
    mutationFn: (todos: boolean) => (todos ? logoutAll() : logout()),
    onSettled: () => { queryClient.clear(); navigate('/login', { replace: true }); },
  });

  const alternarCanal = (c: Canal) => prefs && setPrefs({
    ...prefs,
    notification_channels: prefs.notification_channels.includes(c)
      ? prefs.notification_channels.filter(x => x !== c)
      : [...prefs.notification_channels, c],
  });

  return (
    <AppShell current="profile" title="Perfil e privacidade" subtitle="Sua conta, como a HIVE fala com você e o que fazer com seus dados.">
      <div style={{ display: 'grid', gap: 12 }}>
        <div style={{ ...card, display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ width: 58, height: 58, borderRadius: 999, background: 'var(--text-primary)', color: 'var(--bg-surface)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, fontWeight: 700 }}>
            {nome[0]?.toUpperCase() || 'U'}
          </div>
          <div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{nome}</div>
            <div style={{ fontSize: 14, color: 'var(--text-muted)', marginTop: 2 }}>{email || '—'}</div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
          <div style={card}>
            <div style={label}>Plano</div>
            {assinaturaQ.data ? (
              <>
                <div style={{ fontSize: 16, fontWeight: 700, textTransform: 'capitalize' }}>{assinaturaQ.data.plan}</div>
                <Link to="/planos" style={{ fontSize: 13 }}>Ver planos e uso →</Link>
              </>
            ) : <div style={nota}>{assinaturaQ.isError ? getErrorMessage(assinaturaQ.error) : 'Carregando…'}</div>}
          </div>
          <div style={card}>
            <div style={label}>Origem dos dados</div>
            {conexoesQ.data ? (
              <>
                <div style={{ fontSize: 14, fontWeight: 600 }}>{ROTULO_ORIGEM[conexoesQ.data.data_source]}</div>
                <div style={nota}>{conexoesQ.data.total} banco(s) conectado(s) · <Link to="/connections">gerenciar</Link></div>
              </>
            ) : <div style={nota}>{conexoesQ.isError ? getErrorMessage(conexoesQ.error) : 'Carregando…'}</div>}
          </div>
          <div style={card}>
            <div style={label}>Alertas push</div>
            <div style={nota}>{ROTULO_PUSH[push]}</div>
            {(push === 'subscribed' || push === 'unsubscribed') && (
              <button style={{ ...botaoSec, marginTop: 8 }} disabled={pushBusy} onClick={alternarPush}>
                {pushBusy ? '…' : push === 'subscribed' ? 'Desativar neste aparelho' : 'Ativar neste aparelho'}
              </button>
            )}
          </div>
        </div>

        <div style={card}>
          <div style={label}>Como a HIVE avisa você</div>
          {prefsQ.isError && <div style={{ ...nota, color: '#991b1b' }}>{getErrorMessage(prefsQ.error, 'Não foi possível carregar as preferências.')}</div>}
          {prefs && (
            <div style={{ display: 'grid', gap: 10 }}>
              <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
                {CANAIS.map(([c, rot]) => (
                  <label key={c} style={{ fontSize: 13, display: 'flex', gap: 6, alignItems: 'center' }}>
                    <input type="checkbox" checked={prefs.notification_channels.includes(c)} onChange={() => alternarCanal(c)} /> {rot}
                  </label>
                ))}
              </div>
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
                <select value={prefs.notification_frequency} aria-label="Frequência"
                  onChange={e => setPrefs({ ...prefs, notification_frequency: e.target.value as Frequencia })}
                  style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 8 }}>
                  {FREQUENCIAS.map(([f, rot]) => <option key={f} value={f}>{rot}</option>)}
                </select>
                {(prefs.notification_frequency === 'daily' || prefs.notification_frequency === 'weekly') && (
                  <label style={{ fontSize: 13 }}>às{' '}
                    <input type="time" value={prefs.digest_time} onChange={e => setPrefs({ ...prefs, digest_time: e.target.value })}
                      style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 6 }} />
                  </label>
                )}
                <button style={botao} disabled={salvarM.isPending} onClick={() => salvarM.mutate(prefs)}>
                  {salvarM.isPending ? 'Salvando…' : 'Salvar'}
                </button>
              </div>
              {salvarM.isError && <div style={{ ...nota, color: '#991b1b' }}>{getErrorMessage(salvarM.error, 'Não foi possível salvar.')}</div>}
              {prefs.notification_channels.includes('push') && push !== 'subscribed' && (
                <div style={nota}>Para receber push, ative também os alertas neste aparelho (acima).</div>
              )}
            </div>
          )}
        </div>

        <div style={card}>
          <div style={label}>Sessões</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button style={botaoSec} disabled={sairM.isPending} onClick={() => sairM.mutate(false)}>Sair</button>
            <button style={botaoSec} disabled={sairM.isPending} onClick={() => sairM.mutate(true)}>Sair de todos os aparelhos</button>
          </div>
          <div style={{ ...nota, marginTop: 6 }}>"Todos os aparelhos" encerra também as sessões abertas em outros celulares e navegadores.</div>
        </div>

        <div style={card}>
          <div style={label}>Seus dados (LGPD)</div>
          <div style={{ display: 'grid', gap: 12 }}>
            <div>
              <button style={botaoSec} disabled={exportarM.isPending} onClick={() => exportarM.mutate()}>
                {exportarM.isPending ? 'Preparando arquivo…' : 'Baixar todos os meus dados (JSON)'}
              </button>
              {exportarM.isError && <div style={{ ...nota, color: '#991b1b' }}>{getErrorMessage(exportarM.error, 'Não foi possível exportar.')}</div>}
            </div>
            <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#b91c1c' }}>Excluir conta e dados</div>
              <div style={nota}>
                Apaga para sempre a conta, os lançamentos, as metas, as conversas e as conexões bancárias. Não dá para desfazer.
                Para confirmar, digite <strong>{FRASE_DE_EXCLUSAO}</strong>.
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                <input value={frase} onChange={e => setFrase(e.target.value)} placeholder={FRASE_DE_EXCLUSAO} aria-label="Frase de confirmação"
                  style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 8, minWidth: 220 }} />
                <button style={perigo} disabled={frase.trim() !== FRASE_DE_EXCLUSAO || excluirM.isPending} onClick={() => excluirM.mutate()}>
                  {excluirM.isPending ? 'Apagando…' : 'Excluir definitivamente'}
                </button>
              </div>
              {excluirM.isError && <div style={{ ...nota, color: '#991b1b' }}>{getErrorMessage(excluirM.error, 'Não foi possível excluir.')}</div>}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
};
