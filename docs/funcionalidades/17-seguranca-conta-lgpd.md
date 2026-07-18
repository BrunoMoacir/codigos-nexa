# 17 — Segurança, Conta e LGPD

> Confiança É o produto: quem entrega o extrato bancário completo precisa de
> mais que promessa. Aqui está o que protege o usuário — e o que protege a
> Nexa dela mesma.

## Em palavras simples

Três perguntas que qualquer usuário (ou investidor) deveria fazer: (1) alguém
consegue ver os dados de outra pessoa? (2) o que acontece se eu esquecer a
senha ou quiser apagar tudo? (3) o que a Nexa faz com meus dados? Este
documento responde as três com o que está NO CÓDIGO, não em política de
papel.

## Autenticação e conta

| Mecanismo | Implementação |
|---|---|
| **Login** | JWT HS256 30min + refresh token 14 dias com **rotação de uso único** — reusar um refresh já rotacionado = 401 (indício de vazamento); blacklist Redis por `jti` |
| **Anti-enumeração** | Login com e-mail inexistente executa hash fictício para equalizar o tempo de resposta (sem timing attack); reset/verificação respondem **sempre 202** com a mesma mensagem |
| **Reset de senha** | `POST /auth/forgot-password` + `/reset-password`: token de 288 bits, uso único, 60min, **só o SHA-256 vai ao banco**; emitir novo link invalida o anterior; senha nova ≥ 8 chars |
| **Verificação de e-mail** | `POST /auth/verify-email` + `/resend-verification`: token 48h, uso único; register dispara automaticamente; flag `email_verified` no usuário (enforcement soft — bloquear features para não-verificados é 1 linha no gating) |
| **Rate limits** | login 10/min · registro 5/min · refresh 20/min · forgot/reset 5/min · resend 3/min · global 60/min por IP (Redis) |

## Autorização (anti-IDOR)

- `require_owner` em TODOS os endpoints de dados: o `user_id` da URL precisa
  ser o dono do token — ver dados de outro usuário retorna 403 sempre.
- Recursos aninhados (ex.: registro de negociação) verificam o dono do objeto.
- 31 testes dedicados (`test_security_hardening.py`) cobrem IDOR, timing,
  rotação, headers.

## Webhooks (entrada de terceiros)

- **Pluggy** e **Stripe**: segredo comparado em tempo constante; produção sem
  segredo configurado → **503 fail-closed** (nunca aceita não-assinado);
  identidade do usuário resolvida server-side (item_id / vínculo Stripe),
  jamais confiada no payload.

## Headers e transporte

- CSP estrita, HSTS (produção), X-Frame-Options DENY, COOP,
  Permissions-Policy; CORS `*` proibido em produção (o validador de config
  **recusa o boot**); correlation IDs por request.

## LGPD (direitos do titular — `app/privacy/`)

- **Portabilidade** (art. 18 V): `GET /privacy/export/{user_id}` — export
  completo dos dados.
- **Eliminação** (art. 18 VI): `DELETE /privacy/erase/{user_id}` —
  irreversível, exige frase de confirmação.
- **Minimização em prática**: CPF/nascimento das consultas T3 nunca
  persistidos e mascarados em logs; e-mail mascarado no audit; perfil
  comportamental de uso interno.
- **Audit log** (`core/audit.py`): eventos estruturados — login
  (sucesso/falha/motivo), registro, logout, reset solicitado/concluído,
  e-mail verificado, export/eliminação LGPD, acesso a dados.

## Supply chain e prompt injection

- `pip-audit` no CI: CVE novo em dependência **quebra o build**.
- Agente: `user_id` imutável injetado pelo sistema; instruções para ignorar
  user_id vindo da mensagem (doc 15).

## O que NÃO faz / Gaps

- **Sem 2FA/MFA** — mitigado parcialmente por verificação de e-mail e
  rotação de refresh; TOTP/passkeys é o próximo degrau natural.
- **Revogação global pós-reset**: access tokens JWT emitidos ANTES do reset
  seguem válidos até expirar (janela ≤ 30min) — revogar tudo exigiria claim
  `iat` + verificação por request (anotado como melhoria).
- **Criptografia em repouso é a do banco** (Postgres/disco) — não há
  criptografia por campo além dos tokens hasheados.
- **Sem observabilidade** (Sentry/Prometheus) — o audit loga, mas erro de
  produção não alerta ninguém; recomendado antes da beta.
- Verificação de e-mail é soft — login funciona sem verificar (decisão
  reversível em 1 linha).
