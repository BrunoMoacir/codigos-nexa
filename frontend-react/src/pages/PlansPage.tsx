import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { contaApi, ROTULO_JANELA, ROTULO_USO } from '../api/conta';
import { brl, dataLonga } from '../api/painel';
import axios from 'axios';
import { getErrorMessage } from '../api/errors';
import { getUserId } from '../api/session';
import { vendaNoApp } from '../native/plataforma';

const card: React.CSSProperties = { background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 12, padding: 18 };
const nota: React.CSSProperties = { fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 };
const botao: React.CSSProperties = { border: '1px solid #111', background: 'var(--text-primary)', color: 'var(--bg-surface)', borderRadius: 8, padding: '10px 12px', fontSize: 13, cursor: 'pointer', width: '100%' };
const faixa = (cor: 'ok' | 'aviso' | 'erro'): React.CSSProperties => ({
  fontSize: 13, borderRadius: 8, padding: 12, marginBottom: 12,
  ...(cor === 'ok' ? { color: '#166534', background: '#f0fdf4', border: '1px solid #bbf7d0' }
    : cor === 'aviso' ? { color: '#92400e', background: '#fffbeb', border: '1px solid #fde68a' }
      : { color: '#991b1b', background: '#fef2f2', border: '1px solid #fecaca' }),
});

const STATUS: Record<string, string> = {
  active: 'ativa', trialing: 'em teste', past_due: 'pagamento pendente', canceled: 'cancelada', incomplete: 'incompleta',
};

// Era um esqueleto vazio: o checkout do Stripe voltava para /planos?checkout=…
// e o usuário via só o título "Planos".
export const PlansPage: React.FC = () => {
  const userId = getUserId();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [retorno] = useState<'success' | 'cancel' | null>(() => {
    const c = params.get('checkout');
    return c === 'success' || c === 'cancel' ? c : null;
  });
  // o session_id some da URL logo abaixo; guardado aqui para a confirmação
  const [sessaoDoCheckout] = useState(() => params.get('session_id') || '');

  // Confirma a volta do Checkout no backend (que lê a sessão no Stripe): o
  // plano libera na hora, sem depender do webhook chegar.
  const confirmacaoQ = useQuery({
    queryKey: ['billing', 'confirmacao', sessaoDoCheckout],
    queryFn: () => contaApi.confirmar(userId, sessaoDoCheckout),
    enabled: retorno === 'success' && !!sessaoDoCheckout && !!userId,
    retry: 2,
    staleTime: Infinity,
  });
  useEffect(() => {
    if (confirmacaoQ.isSuccess) queryClient.invalidateQueries({ queryKey: ['billing', 'assinatura', userId] });
  }, [confirmacaoQ.isSuccess, queryClient, userId]);

  const planosQ = useQuery({ queryKey: ['billing', 'planos'], queryFn: contaApi.planos, staleTime: Infinity });
  const assinaturaQ = useQuery({ queryKey: ['billing', 'assinatura', userId], queryFn: () => contaApi.assinatura(userId), enabled: !!userId });

  // Volta do Stripe: mostra o resultado uma vez, recarrega a assinatura e
  // tira o ?checkout da URL (recarregar a página não repete o aviso).
  useEffect(() => {
    const c = params.get('checkout');
    if (c === 'success' || c === 'cancel') {
      queryClient.invalidateQueries({ queryKey: ['billing', 'assinatura', userId] });
      params.delete('checkout');
      params.delete('session_id');
      setParams(params, { replace: true });
    }
  }, [params, setParams, queryClient, userId]);

  const portalM = useMutation({
    mutationFn: () => contaApi.portal(userId),
    onSuccess: (url) => { window.location.href = url; },
  });
  const checkoutM = useMutation({
    mutationFn: (plano: 'pro' | 'total') => contaApi.checkout(userId, plano),
    onSuccess: (url) => { window.location.href = url; },
    // 409 = já existe assinatura paga: troca de plano é pelo portal (um
    // segundo checkout seria uma segunda cobrança mensal)
    onError: (erro) => {
      if (axios.isAxiosError(erro) && erro.response?.status === 409) portalM.mutate();
    },
  });

  const a = assinaturaQ.data;
  // no app nativo a assinatura é feita pelo site (regras das lojas — ver native/plataforma.ts)
  const podeComprar = vendaNoApp();
  const pagamentosAtivos = (a?.billing_enabled ?? false) && podeComprar;

  return (
    <AppShell current="planos" title="Planos" subtitle="O que cada plano inclui e quanto do seu limite você já usou.">
      {retorno === 'success' && (
        confirmacaoQ.data && confirmacaoQ.data.plan !== 'free'
          ? <div style={faixa('ok')}>Pagamento confirmado — seu plano {confirmacaoQ.data.plan === 'total' ? 'Total' : 'Pro'} já está ativo.</div>
          : confirmacaoQ.isPending && sessaoDoCheckout
            ? <div style={faixa('ok')}>Confirmando o pagamento…</div>
            : <div style={faixa('aviso')}>Recebemos o seu pedido. Se o pagamento foi por boleto ou ainda está em análise, o plano é liberado assim que o pagamento for confirmado.</div>
      )}
      {retorno === 'cancel' && <div style={faixa('aviso')}>Pagamento cancelado — nada foi cobrado.</div>}
      {((checkoutM.isError && !(axios.isAxiosError(checkoutM.error) && checkoutM.error.response?.status === 409)) || portalM.isError) && (
        <div style={faixa('erro')}>{getErrorMessage(portalM.error || checkoutM.error, 'Não foi possível abrir o pagamento.')}</div>
      )}
      {!podeComprar && <div style={faixa('aviso')}>No app você acompanha o seu plano e os limites. Para assinar ou trocar de plano, entre na sua conta pelo site da HIVE.</div>}
      {podeComprar && a && !pagamentosAtivos && <div style={faixa('aviso')}>Pagamentos ainda não estão ativos neste ambiente — os planos aparecem só para consulta.</div>}

      <div style={{ ...card, marginBottom: 12 }}>
        <div style={{ fontWeight: 700, marginBottom: 6 }}>Seu plano</div>
        {assinaturaQ.isLoading && <div style={nota}>Carregando…</div>}
        {assinaturaQ.isError && <div style={{ ...nota, color: '#991b1b' }}>{getErrorMessage(assinaturaQ.error, 'Não foi possível carregar sua assinatura.')}</div>}
        {a && (
          <div style={{ display: 'grid', gap: 6 }}>
            <div style={{ fontSize: 20, fontWeight: 800, textTransform: 'capitalize' }}>{a.plan}</div>
            <div style={nota}>
              Assinatura {STATUS[a.status] || a.status}
              {a.current_period_end && ` · ${a.cancel_at_period_end ? 'termina' : 'renova'} em ${dataLonga(a.current_period_end.slice(0, 10))}`}
            </div>
            {!a.enforcement_enabled && <div style={nota}>Limites em modo observação: por enquanto nada é bloqueado.</div>}
            {a.usage.length > 0 && (
              <div style={{ display: 'grid', gap: 4, marginTop: 6 }}>
                {a.usage.map(u => (
                  <div key={u.key} style={{ fontSize: 13 }}>
                    {ROTULO_USO[u.key] || u.key}: <strong>{u.used}</strong> de {u.limit} {ROTULO_JANELA[u.window] || u.window}
                  </div>
                ))}
              </div>
            )}
            {a.plan !== 'free' && pagamentosAtivos && (
              <button style={{ ...botao, width: 'auto', marginTop: 8 }} disabled={portalM.isPending} onClick={() => portalM.mutate()}>
                {portalM.isPending ? 'Abrindo…' : 'Gerenciar assinatura (cartão, troca, cancelamento)'}
              </button>
            )}
          </div>
        )}
      </div>

      {planosQ.isError && <div style={faixa('erro')}>{getErrorMessage(planosQ.error, 'Não foi possível carregar os planos.')}</div>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
        {(planosQ.data || []).map(p => {
          const atual = a?.plan === p.plan_id;
          const pago = p.plan_id === 'pro' || p.plan_id === 'total';
          return (
            <div key={p.plan_id} style={{ ...card, display: 'grid', gap: 10, alignContent: 'start', borderColor: atual ? 'var(--text-primary)' : undefined }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <div style={{ fontSize: 18, fontWeight: 800 }}>{p.name}</div>
                <div style={{ fontSize: 16, fontWeight: 700 }}>{p.price_brl_monthly > 0 ? `${brl(p.price_brl_monthly)}/mês` : 'Grátis'}</div>
              </div>
              <div style={nota}>{p.tagline}</div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.6 }}>
                {p.features.map(f => <li key={f}>{f}</li>)}
              </ul>
              {atual ? (
                <div style={{ fontSize: 13, fontWeight: 700 }}>✓ Seu plano</div>
              ) : pago && a && a.plan !== 'free' ? (
                // já assina outro plano pago: a troca (com proporcionalidade) é no portal
                <button style={botao} disabled={!pagamentosAtivos || portalM.isPending} onClick={() => portalM.mutate()}>
                  {portalM.isPending ? 'Abrindo…' : `Trocar para ${p.name}`}
                </button>
              ) : pago ? (
                <button style={botao} disabled={!pagamentosAtivos || checkoutM.isPending}
                  onClick={() => checkoutM.mutate(p.plan_id as 'pro' | 'total')}>
                  {checkoutM.isPending && checkoutM.variables === p.plan_id ? 'Abrindo o pagamento…' : `Assinar ${p.name}`}
                </button>
              ) : null}
            </div>
          );
        })}
      </div>
    </AppShell>
  );
};
