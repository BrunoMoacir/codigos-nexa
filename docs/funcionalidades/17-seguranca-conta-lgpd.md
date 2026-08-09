# 17 — Segurança, Conta e LGPD

> Confiança É o produto: quem entrega o extrato bancário completo precisa de
> mais que promessa. Aqui está o que protege o usuário — e o que protege a
> Nexa dela mesma.

## Em palavras simples

Três perguntas que qualquer usuário (ou investidor) deveria fazer: (1) alguém
consegue ver os dados de outra pessoa? (2) o que acontece se eu esquecer a
senha ou quiser apagar tudo? (3) o que a Nexa faz com meus dados? Este
documento responde as três com o que está NO CÓDIGO, não em política de papel.

---

## Autenticação (`app/core/security.py`)

### Tokens

```python
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS   = 14
_BLACKLIST_PREFIX = "nexa:blacklist:"
```

O comentário do código registra o raciocínio da auditoria de 2026-07: para app
financeiro, access token longo + **fail-open do blacklist** (Redis fora do ar)
estendia demais a janela de exposição. A resposta foi encurtar o access para
30 min — assim, mesmo com o blacklist indisponível, a janela de um token
roubado é limitada por expiração, não por revogação.

Todo token carrega um **`jti` único** (UUID4), que é o que permite revogação
individual.

### Rotação de uso único do refresh token

`decode_refresh_token` valida, em ordem: assinatura → expiração → `type ==
refresh` → **não estar na blacklist**. Ao usar um refresh token, ele é
revogado e um novo é emitido. **Reusar um refresh já rotacionado = 401** — e
isso é indício de vazamento, não erro do usuário.

`revoke_token(jti, ttl)` faz `SETEX` no Redis com o TTL restante do token — a
entrada de blacklist expira junto com o token, sem crescimento indefinido. Se
o Redis estiver fora, o código **loga explicitamente** que o token **não** foi
blacklistado, em vez de falhar em silêncio.

### Anti-enumeração de contas

**Login** — um hash fictício é computado no import:

```python
_DUMMY_HASH = get_password_hash("__nexa_dummy_password_never_used__")
```

E-mail inexistente executa `verify_password` contra esse hash, **igualando o
tempo de resposta** ao caso de senha errada. Sem isso, o tempo de resposta
revelaria quais e-mails têm conta (bcrypt é lento de propósito, e a diferença
seria mensurável).

**Reset e verificação** — respondem **sempre 202** com a mesma mensagem, exista
ou não o e-mail. Inclusive quando o envio falha: `logger.exception(...)` e a
*resposta segue 202*.

### Tokens de conta (`core/account_tokens.py`)

```python
token = secrets.token_urlsafe(48)     # ~64 chars, 288 bits de entropia
armazenado = sha256(token)            # só o hash vai ao banco
```

| Propósito | TTL |
|---|---|
| Reset de senha | 60 min |
| Verificação de e-mail | 48 h (2880 min) |

Três propriedades importantes:

1. **Só o SHA-256 vai ao banco** — vazamento da tabela não dá acesso a
   nenhuma conta;
2. **Emitir um token novo invalida os anteriores** do mesmo propósito
   (`UPDATE ... SET used_at = now WHERE used_at IS NULL`) — o link mais recente
   é o único válido;
3. **`consume_token` nunca detalha o motivo da falha** — expirado, já usado,
   propósito errado e inexistente retornam todos `None`. O comentário nomeia o
   ataque evitado: *"evita oráculo de estado do token"*.

Detalhe de robustez: datas naive vindas do SQLite são tratadas como UTC antes
da comparação de expiração.

### Rate limits

| Endpoint | Limite |
|---|---|
| Login | 10/min |
| Registro | 5/min |
| Refresh | 20/min |
| Forgot / reset password | 5/min |
| Resend verification | 3/min |
| Chat do agente | 20/min |
| Global por IP | 60/min |

---

## Autorização anti-IDOR (`require_owner`)

Uma dependency única substitui o padrão repetido em todos os routers:

```python
def require_owner(user_id: str, current_user: str = Depends(get_current_user)) -> str:
    validate_user_id(user_id)                     # UUID v4 bem formado
    if current_user != user_id:
        raise HTTPException(403, "Acesso negado")
    return user_id
```

Duas coisas em uma: **validação de formato** (UUID v4) e **verificação de
propriedade**. Centralizar importa — a proteção IDOR não pode depender de cada
autor de router lembrar de escrever as duas linhas.

`require_plan` (doc 16) **embute** `require_owner`, então adicionar gate de
plano nunca remove a proteção IDOR por acidente.

Recursos aninhados (ex.: registro de negociação) verificam o dono do objeto,
não só o `user_id` da URL. **31 testes dedicados**
(`test_security_hardening.py`) cobrem IDOR, timing, rotação e headers.

---

## Webhooks (entrada de terceiros)

**Pluggy** (`core/webhook_security.py`) e **Stripe** (`billing/stripe_client.py`):

- Segredo comparado em **tempo constante** (`hmac.compare_digest`);
- **Produção sem segredo configurado → 503 fail-closed** — nunca aceita
  requisição não assinada;
- **Identidade resolvida server-side**: pelo `item_id` (Pluggy) ou pelo vínculo
  Stripe. O `user_id` do payload **jamais** é confiado.

O Stripe tem ainda tolerância anti-replay de 5 min (detalhes no doc 16).

---

## Headers e transporte (`app/main.py`)

```python
_CSP_STRICT = "default-src 'none'; frame-ancestors 'none'"
```

CSP estrito para a API — respostas JSON não carregam recurso nenhum, então
`default-src 'none'` é o correto. As rotas de **docs** (Swagger/ReDoc, que
carregam de jsdelivr) recebem um CSP relaxado separado; o resto da API fica no
estrito.

Também aplicados: `X-Frame-Options: DENY`, COOP,
`Permissions-Policy: geolocation=(), microphone=(), camera=()`, e **HSTS apenas
em produção** — o comentário explica: em dev não há TLS e o header
"envenenaria" o navegador do desenvolvedor.

**Correlation IDs** por request.

### Validação de configuração — fail-closed no boot

`_validate_production_secrets` **recusa o boot** quando `APP_ENV=production` e:

- `SECRET_KEY` ainda é o valor mock (`nexa_secret_key_mock_123_do_not_use_in_prod`);
- `ALLOWED_ORIGINS` é `*`.

Em desenvolvimento, os mesmos casos apenas emitem warning. É a diferença entre
"o dev pode trabalhar" e "a produção não sobe insegura".

---

## LGPD (`app/privacy/`)

**Portabilidade (art. 18, V)** — `GET /privacy/export/{user_id}`: percorre um
**inventário estático de tabelas** e monta o export. Regra explícita no código:
**nunca exportar o hash de senha**. Tabelas indisponíveis são puladas com log
de debug, não quebram o export.

**Eliminação (art. 18, VI)** — `DELETE /privacy/erase/{user_id}`: `DELETE` por
`user_id` em cada tabela do inventário, **na ordem do inventário** (respeitando
FKs), mais a limpeza do DuckDB (`notification_state`, `notification_events`).
Irreversível, exige frase de confirmação. Retorna `ErasureResult` com
`rows_deleted`, `tables_purged` e `skipped` — auditável.

**Minimização em prática**: CPF/nascimento das consultas T3 **nunca
persistidos** e mascarados em logs (doc 11); e-mail mascarado no audit; perfil
comportamental de uso estritamente interno.

**Audit log** (`core/audit.py`) — eventos estruturados com `mask_email`:
login (sucesso/falha + motivo), registro, logout, reset solicitado/concluído,
e-mail verificado, export LGPD, eliminação LGPD, acesso a dados. Cada evento
carrega IP e `request_id`.

---

## Supply chain e prompt injection

- **`pip-audit` no CI**: CVE novo em dependência **quebra o build**.
- **Agente**: `user_id` imutável injetado pelo sistema + sanitização regex do
  corpo da mensagem + instrução no prompt (doc 15).

---

## O que NÃO faz / Gaps

- **Sem 2FA/MFA** — mitigado parcialmente por verificação de e-mail e rotação
  de refresh; TOTP/passkeys é o próximo degrau natural.
- **Revogação global pós-reset**: access tokens JWT emitidos ANTES do reset
  seguem válidos até expirar (janela ≤ 30 min) — revogar tudo exigiria claim
  `iat` + verificação por request (anotado como melhoria).
- **Blacklist depende do Redis**: com Redis fora, `revoke_token` loga o
  problema mas o logout não revoga de fato. A mitigação é o access de 30 min.
- **Criptografia em repouso é a do banco** (Postgres/disco) — não há
  criptografia por campo além dos tokens hasheados.
- **Verificação de e-mail é soft** — o login funciona sem verificar
  (`email_verified` existe; bloquear features para não-verificados é 1 linha no
  gating).
- **O `erase` é `DELETE` por inventário estático** — uma tabela nova precisa ser
  adicionada ao inventário manualmente, ou os dados sobrevivem à eliminação.
  Risco real de manutenção.
- **Sem observabilidade** (Sentry/Prometheus) — o audit loga, mas erro de
  produção não alerta ninguém; recomendado antes da beta.
