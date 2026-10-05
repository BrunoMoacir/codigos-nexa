/**
 * Erros da API em linguagem de gente.
 *
 * Antes, todo erro do chat virava "Verifique se o backend está ativo" — o
 * mesmo texto para cota do plano Free esgotada (402), rate limit (429), LLM
 * não configurado (503) e timeout. E o 402 do gating traz `detail` como
 * OBJETO, que o `getErrorMessage` antigo, que só aceitava string, descartava.
 */
import axios from 'axios';

export type ApiErrorKind =
  | 'network'
  | 'timeout'
  | 'unauthorized'
  | 'forbidden'
  | 'not_found'
  | 'validation'
  | 'upgrade_required'
  | 'rate_limited'
  | 'unavailable'
  | 'gateway_timeout'
  | 'server'
  | 'unknown';

export interface UpgradeInfo {
  reason?: string;
  required_plan?: string;
  price_brl_monthly?: number | null;
}

export interface ApiErrorInfo {
  kind: ApiErrorKind;
  status?: number;
  message: string;
  upgrade?: UpgradeInfo;
}

const PLAN_LABEL: Record<string, string> = { free: 'Free', pro: 'Pro', total: 'Total' };

function detailToText(detail: unknown): string | undefined {
  if (!detail) return undefined;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    // 422 do FastAPI: [{loc, msg, type}]
    const msgs = detail
      .map((d) => {
        if (d && typeof d === 'object' && 'msg' in d) {
          const loc = Array.isArray((d as { loc?: unknown[] }).loc)
            ? (d as { loc: unknown[] }).loc.filter((x) => x !== 'body').join('.')
            : '';
          return loc ? `${loc}: ${(d as { msg: string }).msg}` : (d as { msg: string }).msg;
        }
        return typeof d === 'string' ? d : '';
      })
      .filter(Boolean);
    return msgs.length ? msgs.join('; ') : undefined;
  }
  if (typeof detail === 'object') {
    const obj = detail as Record<string, unknown>;
    if (typeof obj.reason === 'string') return obj.reason;
    if (typeof obj.message === 'string') return obj.message;
    if (typeof obj.detail === 'string') return obj.detail;
  }
  return undefined;
}

export function describeError(error: unknown, fallback = 'Algo deu errado. Tente de novo.'): ApiErrorInfo {
  if (!axios.isAxiosError(error)) {
    return { kind: 'unknown', message: error instanceof Error && error.message ? error.message : fallback };
  }
  if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
    return {
      kind: 'timeout',
      message: 'A análise está demorando mais que o normal. Ela pode ter terminado no servidor — tente recarregar em instantes.',
    };
  }
  if (!error.response) {
    return { kind: 'network', message: 'Não foi possível falar com o servidor. Verifique sua conexão.' };
  }

  const status = error.response.status;
  const body = error.response.data as { detail?: unknown } | undefined;
  const detail = body?.detail;
  const texto = detailToText(detail);

  if (status === 402) {
    const up = (detail && typeof detail === 'object' ? detail : {}) as UpgradeInfo;
    const plano = PLAN_LABEL[up.required_plan || ''] || up.required_plan || 'superior';
    return {
      kind: 'upgrade_required',
      status,
      upgrade: up,
      message: `${texto || 'Este recurso não está incluído no seu plano.'} Disponível no plano ${plano}.`,
    };
  }
  if (status === 401) return { kind: 'unauthorized', status, message: 'Sua sessão expirou. Entre de novo.' };
  if (status === 403) return { kind: 'forbidden', status, message: texto || 'Você não tem acesso a este recurso.' };
  if (status === 404) return { kind: 'not_found', status, message: texto || 'Não encontrado.' };
  if (status === 422 || status === 400) return { kind: 'validation', status, message: texto || 'Dados inválidos.' };
  if (status === 429) {
    return { kind: 'rate_limited', status, message: 'Muitas requisições em pouco tempo. Aguarde um minuto e tente de novo.' };
  }
  if (status === 503) return { kind: 'unavailable', status, message: texto || 'Serviço temporariamente indisponível.' };
  if (status === 504) return { kind: 'gateway_timeout', status, message: texto || 'O servidor demorou demais para responder.' };
  if (status >= 500) return { kind: 'server', status, message: texto || fallback };
  return { kind: 'unknown', status, message: texto || fallback };
}

export function getErrorMessage(error: unknown, fallback?: string): string {
  return describeError(error, fallback).message;
}

export function isUpgradeRequired(error: unknown): boolean {
  return describeError(error).kind === 'upgrade_required';
}
