# Nexa — Modelo de Segurança

> Auditoria e hardening de 2026-07-12. Este documento é o mapa vivo do
> modelo de segurança: o que existe, os trade-offs conscientes e o
> baseline de riscos aceitos. Atualize-o junto com qualquer mudança de
> superfície de segurança.

## 1. Autenticação e sessão

- **Senhas**: bcrypt via passlib; hash fictício no login para equalizar o
  tempo de resposta quando o email não existe (anti-enumeração).
- **Access token**: JWT HS256, **30 minutos**, claims `sub`, `jti`, `type=access`.
- **Refresh token**: 14 dias, `type=refresh`, aceito SOMENTE em
  `POST /auth/refresh`. **Rotação com uso único**: cada refresh usado é
  revogado no ato (blacklist Redis) e um novo par é emitido; reuso → 401
  (indício de vazamento — o portador legítimo refaz login).
- **Revogação**: blacklist Redis por `jti` (logout e rotação). Redis fora
  do ar → fail-open **consciente** (disponibilidade > revogação imediata),
  mitigado pelo access de 30 min.
- **Por request**: além da assinatura, `get_current_user` verifica
  existência e `is_active` do usuário no banco; refresh token nunca é
  aceito como credencial de API.

## 2. Autorização

- `require_owner` em todos os endpoints de dados: o `user_id` do path
  precisa ser o dono do token (403 caso contrário).
- Recursos aninhados verificam dono do objeto (ex: simulações do
  Architect comparam `sim.user_id` com o usuário autenticado).
- **Chat/LLM**: o `user_id` autenticado é injetado como contexto imutável
  do sistema; o agente é instruído a ignorar qualquer user_id vindo da
  mensagem (mitigação de prompt injection nas 28 tools).

## 3. Entrada de dados — webhook Pluggy

- `POST /transactions/webhook` exige segredo compartilhado
  (`PLUGGY_WEBHOOK_SECRET`) via header `X-Webhook-Token` ou `?token=`,
  comparado em **tempo constante**.
- Produção sem segredo configurado → **503 fail-closed** (preferimos o
  webhook fora do ar a aceitar escrita anônima).
- **Identidade nunca vem do chamador**: `item_id` do payload é resolvido
  server-side via `pluggy_items` (gravado quando o usuário autenticado
  conectou o banco). Item desconhecido → 404, nada é escrito. O query
  param `user_id` só funciona em `APP_MODE=dev` (mocks locais).

## 4. Transporte e headers

Middleware global (`app/main.py`):
`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer`, `Permissions-Policy` restritiva,
`Cross-Origin-Opener-Policy: same-origin`, CSP estrito
(`default-src 'none'`) para a API e relaxado apenas em `/docs`/`/redoc`
(Swagger usa CDN). **HSTS** (2 anos, includeSubDomains) apenas em
produção. CORS: `*` só em dev; produção exige `ALLOWED_ORIGINS` (validator
recusa boot com `*`).

## 5. LGPD — direitos do titular

- `GET /privacy/export/{user_id}` — portabilidade (art. 18 V): todos os
  dados do titular em JSON, tabela a tabela, sem hash de senha.
- `DELETE /privacy/erase/{user_id}` — eliminação (art. 18 VI):
  irreversível, exige a frase `EXCLUIR MEUS DADOS`, apaga o inventário
  completo (`app/privacy/service.py::_DATA_INVENTORY` — **inclua tabelas
  novas com user_id lá**) + estado DuckDB de notificações + a conta.
- Ambos exigem token do próprio titular e geram evento de auditoria
  (`PRIVACY_EXPORT` / `PRIVACY_DELETION`).
- **PII em logs**: emails são mascarados (`g*****l@dominio`) na trilha de
  auditoria; o logger `nexa.audit` deve apontar para sink imutável em prod.

## 6. Rate limiting

Global 60/min por IP (storage Redis — efetivo multi-instância), registro
5/min, login 10/min, refresh 20/min. Nos testes o limiter é desativado
pelo conftest (4 instâncias).

## 7. Dependências (SCA)

- Job `security-audit` no CI: `pip-audit` sobre os pins exatos do
  `requirements.txt`. **Qualquer CVE novo quebra o build.**
- Upgrades de 2026-07-12 (validados com a suíte completa verde):
  fastapi 0.139 / starlette 1.3.1, python-multipart 0.0.31,
  python-jose 3.5.0, requests 2.33, python-dotenv 1.2.2,
  pydantic-settings 2.14.2, duckdb 1.4.4, scikit-learn 1.8.0,
  pyarrow 23.0.1.

### Baseline aceito (ignores no CI — revisar a cada trimestre)

| ID | Pacote | Racional |
|----|--------|----------|
| PYSEC-2026-83 | langgraph 0.2.28 | Fix só na linha 1.x (reescrita do agente). Migração planejada. |
| CVE-2024-8309 | langchain 0.2.16 | Vetor é `SQLDatabaseChain` — **não usado** (agente = `create_react_agent` + tools próprias). Fix 0.2.19 nunca foi publicado no PyPI. |
| CVE-2024-7774 | langchain 0.2.16 | Path traversal em store local não utilizado. Sem fix na série 0.2. |
| CVE-2026-55443 | langchain 0.2.16 | Fix só em 1.3.9. |
| PYSEC-2026-76 | langchain-openai 0.1.25 | Fix só em 1.1.14. |

**Dívida planejada:** migrar o agente para langchain/langgraph 1.x zera o
baseline. Até lá, os vetores conhecidos não estão no caminho de uso.

## 8. Incidente conhecido — chaves vazadas no git (2026-07-12)

`.env` (raiz, **tracked**) e `backend/.env.example` continham chaves
reais de OpenAI e Anthropic. Os arquivos foram sanitizados, e o
`.gitignore` passou a cobrir `.env` — mas **o histórico do git preserva
as chaves**. Ações obrigatórias do operador:

1. **Revogar/rotacionar as duas chaves** nos consoles da OpenAI e da
   Anthropic (feito? ☐).
2. `git rm --cached .env` + commit (tira o arquivo do versionamento;
   o local continua funcionando).
3. Se o repositório for público ou for tornado público: reescrever o
   histórico (`git filter-repo --path .env --invert-paths` e equivalente
   para o example) e forçar push — com repo privado, a rotação (passo 1)
   é o mitigador suficiente.

## 9. Pendências conhecidas (não bloqueiam, anotadas)

- Rotação de SECRET_KEY sem derrubar sessões (exige suporte a múltiplas
  chaves de verificação) — baixa prioridade em monolito.
- Migração langchain 1.x (zera o baseline de CVEs).
- Retenção formal de logs de auditoria (definir prazo e sink imutável
  antes do primeiro usuário externo).
- Push iOS depende de instalação do PWA (limitação de plataforma).
