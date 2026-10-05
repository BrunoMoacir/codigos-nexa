import apiClient, { TIMEOUTS } from './client';
import type { SyncJobState } from './pluggySync';

/** Conexões Open Finance (Pluggy). A lista persistida vem de painelApi.conexoes. */
export const conexoesApi = {
  /** Token do widget Pluggy Connect (503 quando o servidor não tem credenciais). */
  tokenDoWidget: async (): Promise<string> => {
    const { data } = await apiClient.post('/pluggy/connect-token');
    if (!data?.connect_token) throw new Error('A API não devolveu o token do widget.');
    return data.connect_token;
  },
  /**
   * Registra o item que o widget conectou. Era o iframe que fazia esse POST,
   * sem await e com o JWT congelado no HTML — a tela anunciava "conta
   * conectada" mesmo quando o salvamento falhava.
   */
  salvarItem: async (itemId: string, conector?: string | null): Promise<void> => {
    await apiClient.post('/pluggy/items', { item_id: itemId, connector_name: conector ?? null });
  },
  /** Lançamentos que o ETL descartou na última semana, e por quê. */
  qualidade: async (userId: string): Promise<{ total_rejeitadas: number; por_erro: Record<string, number>; diagnostico: string }> => {
    const { data } = await apiClient.get(`/data-quality/${userId}`);
    return data;
  },
  /** Cria item no sandbox e devolve o job de sync (acompanhar com followSyncJob). */
  criarSandbox: async (perfMultiplier: number): Promise<{ job: SyncJobState | null }> => {
    const { data } = await apiClient.post('/pluggy/sandbox', null, {
      params: { perf_multiplier: perfMultiplier },
      timeout: TIMEOUTS.lento,
    });
    return data;
  },
};

/** HTML do iframe do widget: só repassa o resultado ao app, sem token nem fetch. */
export function htmlDoWidget(connectToken: string, atualizarItem?: string): string {
  const cfg = JSON.stringify({ connectToken, ...(atualizarItem ? { updateItem: atualizarItem } : {}) });
  return `<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <script src="https://cdn.pluggy.ai/pluggy-connect/latest/pluggy-connect.js"></script>
  </head>
  <body style="margin:0;padding:0;background:#fff;">
    <div id="pluggy-container" style="width:100%;height:640px;"></div>
    <script>
      var cfg = ${cfg};
      var avisar = function (msg) { window.parent.postMessage(Object.assign({ origem: 'hive-pluggy' }, msg), '*'); };
      var pluggy = new PluggyConnect(Object.assign({}, cfg, {
        container: document.getElementById('pluggy-container'),
        onSuccess: function (itemData) {
          var item = (itemData && itemData.item) || {};
          avisar({ type: 'pluggy-success', itemId: item.id, connectorName: item.connector && item.connector.name });
        },
        onError: function (error) {
          avisar({ type: 'pluggy-error', code: error && (error.code || error.errorCode), message: error && (error.message || error.description) });
        },
        onClose: function () { avisar({ type: 'pluggy-close' }); },
      }));
      pluggy.init();
    </script>
  </body>
</html>`;
}
