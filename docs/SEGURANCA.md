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

## 9. Cobrança, app nativo e integrações (2026-11)

| Superfície | Proteção |
|:---|:---|
| **Webhook Stripe** | Assinatura verificada (fail-closed em produção). Não confia no corpo do evento: relê a assinatura no Stripe. Dedupe por `event.id`. Conflito de dono (metadata × registro) não altera nada. Erro interno → 500 genérico, sem detalhe |
| **IDs do Stripe em URL** | `cs_…`/`sub_…` validados por regex antes de virarem caminho na API do Stripe com a nossa chave (sem path injection) |
| **Confirmação do Checkout** | `POST /billing/checkout/{id}/confirm` só aceita sessão criada para o mesmo usuário (403 se for de outra conta) |
| **Enforcement** | Só bloqueia com o Stripe configurado. Flag ligada sem chave não tranca ninguém sem caminho de pagamento |
| **Pluggy `POST /pluggy/items`** | `item_id` com formato UUID (sem path injection na API da Pluggy). O item precisa ter `clientUserId` igual ao usuário logado: antes, quem obtivesse o id do item de outra pessoa vinculava o banco dela à própria conta |
| **Web Push (SSRF)** | O endpoint de inscrição só é aceito em https:443 de um serviço de push conhecido (FCM, Mozilla, Apple, WNS). O host é lido pelo `urlparse` e pelo parser do urllib3 (o que conecta), e os dois têm de concordar; `\`, `@`, credencial na URL, espaço, controle e não-ASCII são recusados, porque é nessas URLs que os dois parsers divergem. O envio não segue redirecionamento. Antes, qualquer URL virava uma requisição do servidor; endpoints antigos fora da regra são revogados no próximo envio |
| **Token do widget nativo** | `hwt_` + 32 bytes aleatórios; só o SHA-256 no banco; escopo de uma rota (`GET /widget/margem`); 90 dias; um por aparelho; revogado no logout, `logout-all`, **reset de senha** e exclusão LGPD, e recusado se for anterior ao último corte de sessão (`sessions_valid_from`) ou se a conta estiver inativa. O reset de senha e o `logout-all` também revogam os aparelhos de push nativo. O JWT não abre a rota do widget e o token do widget não abre nenhuma outra |
| **Push FCM** | Conta de serviço só em variável de ambiente (segredo); notificação com visibilidade privada na tela de bloqueio; URL de destino forçada a rota interna; token inválido revogado sozinho; token transferido quando o aparelho troca de conta |
| **App nativo** | Sem código remoto (`server.url`), sem navegação para fora do WebView, sem texto puro, backup desligado, credenciais do widget no Keystore/Keychain (`ThisDeviceOnly`). Detalhes em [APP_NATIVO.md](APP_NATIVO.md) |
| **Agente de IA** | Ferramentas de plano superior respondem "RECURSO DO PLANO X" em vez de entregar o recurso pelo chat (o gating vale também pela conversa) |
| **Dependências do frontend** | `npm audit --omit=dev` = 0. Atualizações escolhidas só entre versões com ≥ 2 semanas de publicação e com proveniência verificada (axios publicado por GitHub Actions com SLSA) — defesa contra pacote comprometido recém-publicado |

## 10. Pendências conhecidas (não bloqueiam, anotadas)

- Rotação de SECRET_KEY sem derrubar sessões (exige suporte a múltiplas
  chaves de verificação) — baixa prioridade em monolito.
- Migração langchain 1.x (zera o baseline de CVEs).
- Retenção formal de logs de auditoria (definir prazo e sink imutável
  antes do primeiro usuário externo).
- Push iOS no navegador depende de instalar o PWA (limitação de plataforma); no app nativo vai pelo FCM.
- App nativo: o refresh token fica no `localStorage` do WebView (sandbox do
  app), não no Keychain/Keystore; certificate pinning não implementado — ver
  [APP_NATIVO.md](APP_NATIVO.md#riscos-residuais-decisões-conscientes).
