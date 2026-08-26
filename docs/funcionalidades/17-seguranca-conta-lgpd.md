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
    validate_user_id(user_id)                     # UUID v4 em produção
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

**Medido em 2026-08-25, na superfície inteira**: token de um usuário pedindo
dados de outro em **todas as 44 rotas GET com `{user_id}`** → 401/403 em
44 de 44, zero vazamento. Virou teste
(`test_seguranca_lgpd.py::TestIDORNaSuperficieInteira`), com guarda
anti-vacuidade: se a sonda passar a testar menos de 40 rotas, ela reprova.

Uma varredura irmã exige dependência de autenticação em **toda** rota que não
esteja numa allowlist de públicas — cada entrada com o motivo escrito
(login, webhooks assinados, health, catálogos). A primeira versão desse teste
era **vazia**: iterava `app.routes`, que traz wrappers de inclusão preguiçosa,
e inspecionava três rotas, todas públicas. Agora desce nos wrappers e alcança
134.

Nessa varredura apareceu `app/retention/router.py`: `GET
/retention/cancellation-impact/{user_id}` **sem dependência de autenticação
nenhuma**, com dado fabricado por `hash(user_id) % 5000`, e um
`POST /retention/pause-account` que respondia *"conta pausada com sucesso"*
sem fazer nada. Não estava montado — estava a um `include_router` de distância.
Removido.

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

### Trocar a senha derruba as sessões abertas (2026-08-25)

Era o gap declarado: *"revogar tudo exigiria claim `iat` + verificação por
request"*. A verificação **já estava sendo paga** — `get_current_user` carrega
a linha do usuário para checar `is_active`. O custo real era uma coluna.

`users.sessions_valid_from` é o corte: todo token com `iat` anterior a ele é
recusado. `update_user_password` grava senha e corte **na mesma transação**.

```
                antes do reset   depois
  access token       ok            401
  refresh token      ok            401
```

O refresh é a metade que importa: ele vive **14 dias**, e sem o corte a sessão
voltaria no próximo `/auth/refresh` — derrubar só o access daria meia hora de
alívio e devolveria a conta ao invasor.

`encerrar_sessoes(db, user_id)` expõe o mesmo corte para um futuro "sair de
todos os dispositivos". Diferente da blacklist por `jti`, este corte vive no
banco e **não tem fail-open**: não depende do Redis.

Limite honesto: `iat` tem granularidade de segundo, então um token emitido no
mesmo segundo do corte sobrevive. Sub-segundo, irrelevante diante de uma
sessão de 30 min — e a primeira versão desta comparação tinha uma tolerância
de 1 segundo que abria um buraco de um segundo inteiro, removida.

### Bloqueio de login por CONTA (`core/login_throttle.py`)

O rate limit do login é 10/min **por IP**. Isso não segura credential stuffing
distribuído: mil IPs testando dez senhas por minuto na mesma conta passam
inteiros por baixo, e cada requisição parece normal.

Segunda camada: **8 falhas em 15 min bloqueiam a conta** (429). Três decisões:

1. **A contagem é pelo e-mail SUBMETIDO, exista a conta ou não**, e a resposta
   é a mesma. Se só contas reais bloqueassem, o bloqueio responderia "esse
   e-mail existe" — o oráculo que o hash fictício de senha existe para evitar.
2. **O e-mail nunca vira chave em claro no Redis** — vai o SHA-256.
3. **O TTL é fixado na PRIMEIRA falha e não renovado.** Renovar a cada
   tentativa deixaria um atacante manter a conta bloqueada para sempre: o
   bloqueio viraria negação de serviço contra o dono.

Fail-open quando o Redis cai, como a blacklist — o limite por IP continua de pé.

### Catraca de CVE na árvore transitiva

O job `security-audit` audita só os pins **diretos** (`--no-deps`). A árvore
resolvida tinha **156 vulnerabilidades em 33 pacotes** quando isto foi medido
— urllib3, tornado, cryptography, aiohttp, pillow, setuptools — todas
invisíveis ali.

Corrigir os 33 é uma rodada de dependências, não de segurança de aplicação.
`scripts/audit_arvore_completa.py` compara a contagem com
`security_baseline.json` e **falha se subir**: não se paga a dívida hoje, não
se contrai a próxima. Ao corrigir dependências, `--atualizar-base` trava o
ganho.

---

## LGPD (`app/privacy/`)

### O inventário é DESCOBERTO do banco (correção de 2026-08-25)

Era uma lista mantida à mão, com a instrução "ao adicionar uma tabela nova com
`user_id`, inclua-a aqui". Medido, ela errava **nos dois sentidos ao mesmo
tempo**:

| fora do inventário, com dado do titular | no inventário, inexistente |
|---|---|
| `auth_tokens` — **2851 linhas** | `daily_digest_log` |
| `rejected_transactions` — **200 linhas** | `notification_delivery_log` |
| `shadow_invoices` — 4 | `push_subscriptions` |
| `user_subscriptions` — 3 | `user_settings` |
| `architect_simulation_feedback`, `pluggy_sync_jobs` | `bank_fee_trends` (sem `user_id`) |

`rejected_transactions` guarda descrição e valor de transações recusadas pelo
ETL — dado financeiro pessoal sobrevivendo à eliminação do art. 18 VI. E as
cinco inexistentes falhavam no `DELETE`, caíam no `except` e viravam
`skipped`, indistinguíveis de uma falha real.

`inventario_de_dados()` agora **descobre** toda tabela com coluna `user_id` via
`sqlalchemy.inspect` (Postgres e SQLite). O que não deve ser apagado fica em
`_NAO_APAGAR`, com motivo escrito — hoje vazia. `users` sai por último, e o que
falha por chave estrangeira volta para uma segunda passada em vez de ser
pulado. O que sobrar loga em **ERROR**, não debug: ali ficou dado do titular.

O teste `test_toda_tabela_com_user_id_entra_no_inventario` é a guarda: uma
tabela nova entra sozinha, e excluí-la exige dizer por quê.

**Portabilidade (art. 18, V)** — `GET /privacy/export/{user_id}`: percorre o
**mesmo inventário descoberto** e monta o export. Exportar menos do que se
apaga esconderia dado do titular dele mesmo. Regra explícita no código:
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
- ~~Revogação global pós-reset~~ — **feito em 2026-08-25**. Ver abaixo.
- **Blacklist depende do Redis**: com Redis fora, `revoke_token` loga o
  problema mas o logout não revoga de fato. A janela real do fail-open, por
  tipo de token: **access 30 min; refresh 14 DIAS** — a rotação revoga o
  refresh pelo tempo restante dele, então um refresh vazado e já rotacionado
  segue aceito por até duas semanas. O docstring dizia "TTL máximo de 24h",
  errado por um fator de 14 justamente no caso perigoso. Corrigido em
  2026-08-25.
- **Consertar a revogação derrubou 54 testes de integração** — que passavam
  justamente por causa do defeito: `test_logout` deslogava o token
  **compartilhado** da sessão e, como deslogar não tinha efeito, os ~50 testes
  seguintes continuavam usando o mesmo token. Agora o logout usa token próprio
  e verifica que ele **morre** — antes só conferia o 204, que é a metade que
  não importa.
- **Fora do docker, a revogação estava inteiramente inerte**: `REDIS_URL`
  aponta para o hostname do compose (`redis://redis:6379`), que não resolve, e
  `_is_token_revoked` devolvia `False` para tudo — logout não revogava e reuso
  de refresh não era detectado, com um Redis rodando em localhost o tempo todo.
  `get_redis` passa a tentar `127.0.0.1` como fallback **apenas fora de
  produção**: em produção um Redis que não resolve é incidente e tem de
  aparecer como tal.
- **Criptografia em repouso é a do banco** (Postgres/disco) — não há
  criptografia por campo além dos tokens hasheados.
- **Verificação de e-mail é soft** — o login funciona sem verificar
  (`email_verified` existe; bloquear features para não-verificados é 1 linha no
  gating).
- **`pip-audit` audita só os pins DIRETOS** (`--no-deps`), não a árvore
  resolvida. E o baseline de `--ignore-vuln` cobria 5 de 9 CVEs reportados, com
  um ignore obsoleto: o job **reprovava**, e reprovava desde antes da auditoria
  de 2026-08-25. Baseline revisado (12 IDs, todos da família
  langchain/langgraph 0.2.x, cujo fix exige a migração para 1.x) e o
  comentário agora diz quando a lista deve ser esvaziada.
- **Sem observabilidade** (Sentry/Prometheus) — o audit loga, mas erro de
  produção não alerta ninguém; recomendado antes da beta.
