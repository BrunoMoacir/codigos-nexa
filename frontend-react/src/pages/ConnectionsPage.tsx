import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { AppShell } from '../components/layout/AppShell';
import { nexaApi } from '../api/nexa';

const card: React.CSSProperties = {
  background: 'var(--bg-surface)',
  border: '1px solid #ebebeb',
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

export const ConnectionsPage: React.FC = () => {
  const [perfMultiplier, setPerfMultiplier] = useState(100);
  const [connectToken, setConnectToken] = useState<string>('');
  const [widgetError, setWidgetError] = useState<string>('');
  const [widgetInfo, setWidgetInfo] = useState<string>('');
  const token = localStorage.getItem('jwt_token') || '';
  const apiBase = import.meta.env.VITE_API_URL || 'https://codigos-nexa-production.up.railway.app/api/v1';

  const itemsQuery = useQuery({
    queryKey: ['pluggy-items'],
    queryFn: () => nexaApi.getPluggyItems(),
  });

  useEffect(() => {
    const handler = (event: MessageEvent) => {
      const payload = event.data;
      if (!payload || typeof payload !== 'object') {
        return;
      }

      if (payload.type === 'pluggy-success') {
        setWidgetError('');
        setWidgetInfo('Conta conectada com sucesso. Atualize a lista para ver o item.');
        toast.success('Conta conectada com sucesso.');
        itemsQuery.refetch();
      }

      if (payload.type === 'pluggy-error') {
        const code = payload.errorCode || payload.code || payload.error?.code || 'desconhecido';
        const message = payload.message || payload.error?.message || 'Falha ao conectar conta na Pluggy.';
        const composed = `Erro Pluggy (${code}): ${message}`;
        setWidgetError(composed);
        setWidgetInfo('');
        toast.error(composed);
      }

      if (payload.type === 'pluggy-close') {
        setWidgetInfo('Widget fechado.');
      }
    };

    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [itemsQuery.refetch]);

  const syncMutation = useMutation({
    mutationFn: () => nexaApi.syncPluggyTransactions(),
    onSuccess: (data) => {
      const totals = data?.totals || {};
      toast.success(
        `Sync concluído: ${totals.saved || 0} transações em ${totals.accounts || 0} contas.`
      );
      itemsQuery.refetch();
    },
    onError: () => toast.error('Falha ao sincronizar transações.'),
  });

  const tokenMutation = useMutation({
    mutationFn: () => nexaApi.createPluggyToken(),
    onSuccess: (data) => {
      if (data?.connect_token) {
        setConnectToken(data.connect_token);
        toast.success('Token Pluggy gerado.');
      } else {
        toast.error('Token não retornado pela API.');
      }
    },
    onError: () => toast.error('Erro ao gerar token Pluggy.'),
  });

  const sandboxMutation = useMutation({
    mutationFn: () => nexaApi.createSandboxItem(perfMultiplier),
    onSuccess: () => {
      toast.success('Item sandbox criado com sucesso.');
      itemsQuery.refetch();
    },
    onError: () => toast.error('Erro ao criar item sandbox.'),
  });

  const items = useMemo(() => {
    const raw = itemsQuery.data?.results || itemsQuery.data?.items || [];
    return Array.isArray(raw) ? raw : [];
  }, [itemsQuery.data]);

  return (
    <AppShell
      current="connections"
      title="Conexões Open Finance"
      subtitle="Gerencie contas conectadas via Pluggy e sincronize dados reais."
    >
      <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr', gap: 12, marginBottom: 12 }}>
        <div style={card}>
          <div style={{ fontSize: 11, letterSpacing: 0.8, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8, fontWeight: 600 }}>
            Contas conectadas
          </div>
          {itemsQuery.isLoading && <p style={{ color: 'var(--text-muted)' }}>Carregando conexões...</p>}
          {!itemsQuery.isLoading && items.length === 0 && (
            <p style={{ color: 'var(--text-muted)' }}>Nenhuma conta conectada no momento.</p>
          )}
          {items.map((item: any) => {
            const connector = item.connector || {};
            const name = connector.name || item.connector_name || 'Banco';
            const status = item.status || 'UNKNOWN';
            const lastUpdated = (item.lastUpdatedAt || item.updated_at || '').toString().slice(0, 10);
            return (
              <div
                key={item.id || item.item_id || `${name}-${status}`}
                style={{
                  border: '1px solid #eee',
                  borderRadius: 10,
                  padding: 12,
                  marginBottom: 8,
                  display: 'flex',
                  justifyContent: 'space-between',
                  gap: 12,
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>{name}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Status: {status}</div>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                  {lastUpdated ? `Atualizado: ${lastUpdated}` : 'Sem atualização'}
                </div>
              </div>
            );
          })}
        </div>

        <div style={card}>
          <div style={{ fontSize: 11, letterSpacing: 0.8, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 10, fontWeight: 600 }}>
            Ações rápidas
          </div>
          <div style={{ display: 'grid', gap: 8 }}>
            <button
              style={button}
              onClick={() => tokenMutation.mutate()}
              disabled={tokenMutation.isPending}
            >
              {tokenMutation.isPending ? 'Gerando token...' : 'Gerar Token Pluggy'}
            </button>
            <button
              style={button}
              onClick={() => syncMutation.mutate()}
              disabled={syncMutation.isPending}
            >
              {syncMutation.isPending ? 'Sincronizando...' : 'Sincronizar transações'}
            </button>
            <button
              style={{ ...button, background: 'var(--bg-surface)', color: 'var(--text-primary)' }}
              onClick={() => itemsQuery.refetch()}
            >
              Atualizar lista
            </button>
          </div>

          <div style={{ marginTop: 14, borderTop: '1px solid #f0f0f0', paddingTop: 12 }}>
            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>Sandbox Pluggy</div>
            <select
              value={perfMultiplier}
              onChange={(e) => setPerfMultiplier(Number(e.target.value))}
              style={{ width: '100%', padding: 9, border: '1px solid #ddd', borderRadius: 8, marginBottom: 8 }}
            >
              <option value={1}>Padrão (1x)</option>
              <option value={100}>Médio (100x)</option>
              <option value={500}>Alto (500x)</option>
              <option value={1000}>Stress (1000x)</option>
            </select>
            <button
              style={{ ...button, width: '100%' }}
              onClick={() => sandboxMutation.mutate()}
              disabled={sandboxMutation.isPending}
            >
              {sandboxMutation.isPending ? 'Criando sandbox...' : 'Criar item Sandbox'}
            </button>
          </div>
        </div>
      </div>

      {connectToken && (
        <div style={card}>
          <div style={{ fontSize: 11, letterSpacing: 0.8, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8, fontWeight: 600 }}>
            Widget Pluggy
          </div>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 10 }}>
            Token gerado com sucesso. Use o widget oficial para conectar um banco real.
          </p>
          <div
            style={{
              fontSize: 12,
              color: '#92400e',
              background: '#fffbeb',
              border: '1px solid #fde68a',
              borderRadius: 8,
              padding: 10,
              marginBottom: 10,
            }}
          >
            Se o widget exibir "Aplicação demo", a própria Pluggy pode bloquear conexões reais neste ambiente e permitir apenas Sandbox.
          </div>
          {widgetError && (
            <div
              style={{
                fontSize: 12,
                color: '#991b1b',
                background: '#fef2f2',
                border: '1px solid #fecaca',
                borderRadius: 8,
                padding: 10,
                marginBottom: 10,
              }}
            >
              {widgetError}
            </div>
          )}
          {widgetInfo && (
            <div
              style={{
                fontSize: 12,
                color: '#1d4ed8',
                background: '#eff6ff',
                border: '1px solid #bfdbfe',
                borderRadius: 8,
                padding: 10,
                marginBottom: 10,
              }}
            >
              {widgetInfo}
            </div>
          )}
          <iframe
            title="pluggy-connect"
            srcDoc={`
<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <script src="https://cdn.pluggy.ai/pluggy-connect/latest/pluggy-connect.js"></script>
  </head>
  <body style="margin:0;padding:0;background:#fff;">
    <div id="pluggy-container" style="width:100%;height:640px;"></div>
    <script>
      const pluggy = new PluggyConnect({
        connectToken: '${connectToken}',
        container: document.getElementById('pluggy-container'),
        onSuccess: function(itemData) {
          fetch('${apiBase}/pluggy/items', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': 'Bearer ${token}',
            },
            body: JSON.stringify({
              item_id: itemData?.item?.id,
              connector_name: itemData?.item?.connector?.name,
            }),
          });
          window.parent.postMessage({ type: 'pluggy-success' }, '*');
        },
        onError: function(error) {
          window.parent.postMessage({
            type: 'pluggy-error',
            errorCode: error?.code || error?.errorCode,
            message: error?.message || error?.description,
            error,
          }, '*');
        },
        onClose: function() {
          window.parent.postMessage({ type: 'pluggy-close' }, '*');
        },
      });
      pluggy.init();
    </script>
  </body>
</html>
            `}
            style={{ width: '100%', height: 660, border: '1px solid #eee', borderRadius: 10 }}
          />
        </div>
      )}
    </AppShell>
  );
};
