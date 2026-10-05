/**
 * Contratos da autenticação. Os demais tipos que moravam aqui descreviam
 * campos que o backend não manda (Alert.type 'danger', Transaction sem id…)
 * e foram substituídos pelos módulos tipados por tela: painel.ts,
 * organizar.ts, feed.ts, chat.ts, estrategias.ts, conexoes.ts, conta.ts e
 * protecao.ts, cada um escrito a partir das respostas reais.
 */

// ==================== AUTH ====================
export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  full_name?: string | null;
  /** Sessão longa (14 dias, uso único). Sem guardá-lo, o usuário caía a cada 30 min. */
  refresh_token?: string | null;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name?: string;
  /** Celular com DDI, só dígitos (ex.: 5511999998888). Opcional. */
  phone?: string;
  /** Aceite dos termos e da política de privacidade — exigido pelo backend. */
  accepted_terms: boolean;
}

/** O que POST /auth/register devolve de fato (não há e-mail na resposta). */
export interface RegisterResponse {
  message: string;
  user_id: string;
}
