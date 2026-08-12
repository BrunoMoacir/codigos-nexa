/**
 * Sync assíncrono da Pluggy — cliente de long-polling e streaming (SSE).
 *
 * A Pluggy entrega os dados quando o banco responde (segundos a minutos,
 * com MFA no meio). O backend transforma isso num job; aqui a UI acompanha
 * o progresso por um dos dois canais, ambos usando o mesmo cursor:
 *
 *   followSyncJob() → tenta SSE e cai para long-polling se o stream falhar
 *                     (proxy corporativo, HTTP/1 sem streaming, etc.)
 *
 * Por que não usar EventSource: ele não manda header Authorization, e token
 * em query string acaba gravado nos logs de acesso. Usamos fetch +
 * ReadableStream, que aceita headers normalmente.
 */

import apiClient, { API_BASE_URL } from './client';

export type SyncJobStatus = 'PENDING' | 'RUNNING' | 'SUCCESS' | 'PARTIAL' | 'ERROR';

export interface SyncJobItemDetail {
  item_id: string;
  status?: string;
  item_status?: string;
  accounts?: number;
  received?: number;
  valid?: number;
  saved?: number;
  error?: string;
  errors?: string[];
}

export interface SyncJobState {
  job_id: string;
  status: SyncJobStatus;
  phase: string;
  progress: number;
  message: string | null;
  error: string | null;
  cursor: number;
  done: boolean;
  changed?: boolean;
  reused?: boolean;
  items: { total: number; done: number };
  totals: { accounts: number; received: number; valid: number; saved: number };
  detail: SyncJobItemDetail[];
  created_at: string | null;
  updated_at: string | null;
  finished_at: string | null;
}

const LONG_POLL_TIMEOUT_S = 25;
// Folga sobre o timeout do servidor: a resposta vem em ~25s, o axios global
// corta em 15s — por isso cada poll leva o seu próprio timeout.
const POLL_HTTP_TIMEOUT_MS = (LONG_POLL_TIMEOUT_S + 10) * 1000;

export const pluggySyncApi = {
  /** Enfileira o sync. Devolve o job existente se já houver um em andamento. */
  startSyncJob: async (force = false): Promise<SyncJobState> => {
    const { data } = await apiClient.post('/pluggy/sync/jobs', null, {
      params: { force },
    });
    return data;
  },

  /** Últimos jobs do usuário (histórico da tela de conexões). */
  listSyncJobs: async (limit = 10): Promise<{ jobs: SyncJobState[] }> => {
    const { data } = await apiClient.get('/pluggy/sync/jobs', { params: { limit } });
    return data;
  },

  /** Um ciclo de long-polling: só responde quando o job passa de `cursor`. */
  pollSyncJob: async (
    jobId: string,
    cursor = 0,
    signal?: AbortSignal
  ): Promise<SyncJobState> => {
    const { data } = await apiClient.get(`/pluggy/sync/jobs/${jobId}`, {
      params: { cursor, timeout: LONG_POLL_TIMEOUT_S },
      timeout: POLL_HTTP_TIMEOUT_MS,
      signal,
    });
    return data;
  },
};

interface FollowOptions {
  jobId: string;
  cursor?: number;
  onState: (state: SyncJobState) => void;
  signal?: AbortSignal;
}

/** Parser de `text/event-stream`: quebra o buffer em frames `\n\n`. */
function parseSseFrame(frame: string): { event: string; data: unknown } | null {
  let event = 'message';
  const dataLines: string[] = [];

  for (const line of frame.split('\n')) {
    if (line.startsWith(':')) continue; // comentário/keep-alive
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
  }

  if (!dataLines.length) return null;
  try {
    return { event, data: JSON.parse(dataLines.join('\n')) };
  } catch {
    return null;
  }
}

/** Consome o SSE até o job terminar. Lança se o stream cair no meio. */
async function streamSyncJob({ jobId, cursor = 0, onState, signal }: FollowOptions): Promise<SyncJobState> {
  const token = localStorage.getItem('jwt_token');
  const url = `${API_BASE_URL}/pluggy/sync/jobs/${jobId}/stream?cursor=${cursor}`;

  const response = await fetch(url, {
    headers: {
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(`stream indisponível (HTTP ${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let last: SyncJobState | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    let split = buffer.indexOf('\n\n');
    while (split !== -1) {
      const frame = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      split = buffer.indexOf('\n\n');

      const parsed = parseSseFrame(frame);
      if (!parsed) continue;

      if (parsed.event === 'state' || parsed.event === 'done') {
        last = parsed.data as SyncJobState;
        onState(last);
        if (parsed.event === 'done') {
          reader.cancel().catch(() => {});
          return last;
        }
      } else if (parsed.event === 'error') {
        throw new Error('job não encontrado');
      }
      // `ping` e `timeout` só mantêm a conexão de pé / pedem reconexão.
    }
  }

  if (last?.done) return last;
  throw new Error('stream encerrado antes do fim do job');
}

/** Long-polling em laço até o job terminar. Fallback do SSE. */
async function pollSyncJobUntilDone({ jobId, cursor = 0, onState, signal }: FollowOptions): Promise<SyncJobState> {
  let current = cursor;

  while (true) {
    const state = await pluggySyncApi.pollSyncJob(jobId, current, signal);
    if (state.cursor > current) {
      current = state.cursor;
      onState(state);
    }
    if (state.done) return state;
    if (signal?.aborted) throw new Error('acompanhamento cancelado');
  }
}

/**
 * Acompanha o job até o fim: SSE primeiro, long-polling se o stream falhar.
 *
 * A retomada usa o cursor do último estado recebido, então a troca de canal
 * (ou uma reconexão) não perde nem duplica evento.
 */
export async function followSyncJob(options: FollowOptions): Promise<SyncJobState> {
  let cursor = options.cursor ?? 0;

  const track = (state: SyncJobState) => {
    cursor = state.cursor;
    options.onState(state);
  };

  try {
    return await streamSyncJob({ ...options, onState: track });
  } catch (err) {
    if (options.signal?.aborted) throw err;
    // Stream indisponível (proxy sem streaming, conexão cortada): o job
    // continua rodando no servidor — só mudamos a forma de olhar para ele.
    console.warn('[pluggySync] SSE indisponível, usando long-polling:', err);
    return pollSyncJobUntilDone({ ...options, cursor, onState: track });
  }
}
