# PRODUCTION CHECKLIST — Nexa AI

> Tudo que falta para o projeto ir para produção.
> Baseado na leitura direta do código — nada aqui é especulação.
>
> Última atualização: 2026-02-23
> Seção 7 (Qualidade de código): **COMPLETA**

---

## Resumo executivo

| Categoria | Itens | Impacto |
|---|---|---|
| [Bloqueadores absolutos](#1-bloqueadores-absolutos) | 6 | Impede produção |
| [Objetivo central: a IA](#2-objetivo-central-a-ia) | 5 | Produto não existe sem isso |
| [Dados e persistência](#3-dados-e-persistência) | 5 | Endpoints funcionam com mock hoje |
| [Segurança](#4-segurança) | 4 | Expõe dados de todos os usuários |
| [Infraestrutura](#5-infraestrutura) | 5 | Não roda em servidor |
| [Funcionalidades incompletas](#6-funcionalidades-incompletas) | 4 | Produto incompleto |
| [~~Qualidade de código~~](#7-qualidade-de-código) | ~~5~~ **0** | ✅ Resolvido em 2026-02-23 |

---

## 1. Bloqueadores absolutos

> Sem qualquer um desses, o sistema não pode ir a ar.

### 1.1 Endpoints retornam dados mock, não dados reais do usuário

**Arquivo:** [backend/app/api/v1/routes/forecast.py](backend/app/api/v1/routes/forecast.py#L71-L100)

A função `fetch_user_transactions()` ignora o `user_id` recebido e sempre executa `NexaRunner(mode="dev")`, que usa o `MockPluggyClient`. Todo usuário que chamar `GET /forecast/{user_id}` recebe os mesmos dados fictícios.

```python
# O que está hoje (linha 87):
runner = NexaRunner(mode="dev")  # Usa Pluggy mock para teste
```

**O que precisa ser feito:**
- Implementar busca real no banco por `user_id`
- Conectar ao `PluggyClient` real com credenciais do usuário específico

---

### 1.2 `GET /transactions/{user_id}` retorna 501

**Arquivo:** [backend/app/api/v1/routes/transactions.py](backend/app/api/v1/routes/transactions.py#L249-L257)

O endpoint que retorna as transações de um usuário está implementado com `raise HTTPException(501)`. Qualquer client que tentar buscar transações recebe erro.

**O que precisa ser feito:**
- Implementar query no banco por `user_id`

---

### 1.3 Webhook não persiste nada no banco

**Arquivo:** [backend/app/api/v1/routes/transactions.py](backend/app/api/v1/routes/transactions.py#L193-L197)

Após rodar o ETL, o passo de salvar no banco está comentado como TODO:

```python
# TODO: Implementar salvamento no Postgres
# await save_to_postgres(categorized_df)
```

O webhook recebe as transações, processa com ETL, e descarta tudo. Não há persistência. Toda vez que a API reinicia, os dados somem.

**O que precisa ser feito:**
- Implementar `save_to_postgres(categorized_df)` ou equivalente no DuckDB persistente

---

### 1.4 Nenhum endpoint tem autenticação

**Arquivo:** [backend/app/core/security.py](backend/app/core/security.py) — arquivo vazio (1 linha)

Qualquer pessoa com a URL pode chamar `GET /forecast/qualquer_user_id` e receber dados financeiros. Não há JWT, sessão, API key, nem nenhuma forma de verificar identidade.

**O que precisa ser feito:**
- Implementar middleware ou dependency de autenticação JWT
- Proteger no mínimo: `/forecast`, `/transactions`, `/shadow_invoice`, `/alerts`, `/architect/simulate`, `/context/override`
- Definir como o `user_id` é validado (hoje é parâmetro de URL livre)

---

### 1.5 Pluggy real nunca foi testado

**Arquivo:** [backend/app/integrations/open_finance/pluggy.py](backend/app/integrations/open_finance/pluggy.py)

O cliente real do Pluggy existe, mas todos os testes e todos os fluxos da API usam `MockPluggyClient`. Não há garantia de que o cliente real funcione com credenciais reais, payloads reais, ou que o fluxo de reconexão OAuth funcione de ponta a ponta.

**O que precisa ser feito:**
- Testar `PluggyClient` com credenciais reais em ambiente sandbox
- Validar que `POST /reconnect/{user_id}` gera URL de reconexão funcional
- Validar que o webhook do Pluggy chega com o formato esperado

---

### 1.6 Banco de dados sem decisão definitiva

O projeto usa DuckDB localmente (funciona) mas tem código PostgreSQL paralelo inativo (`app/db/session.py`, `app/db/models.py`) e `scripts/apply_migrations.py` nunca executado. Em produção, DuckDB em arquivo local não escala e não suporta múltiplos processos simultâneos.

**O que precisa ser feito:**
- Decisão: manter DuckDB (só para um processo) ou migrar para PostgreSQL
- Se PostgreSQL: aplicar migrations, conectar `session.py` ao fluxo, remover DuckDB do caminho crítico
- Se DuckDB: documentar a limitação e garantir deployment single-process

---

## 2. Objetivo central: a IA

> O produto se propõe a ser uma IA financeira. Hoje não há nenhum LLM integrado.

### 2.1 Não existe LLM no projeto

O módulo `app/core/explain.py` gera "explicações" via texto hardcoded com f-strings:

```python
# backend/app/core/explain.py — linha 20
explanation = (
    f"Você pode gastar até R$ {daily:,.2f} por dia com segurança "
    f"nos próximos {days} dias.\n\n"
    ...
)
```

Isso não é IA. É um template de texto. Nenhum modelo de linguagem é chamado em nenhum ponto do projeto.

**O que precisa ser feito:**
- Escolher e integrar um LLM (Anthropic Claude, OpenAI, etc.)
- Criar um nó de geração de linguagem natural no agente que use o LLM
- Adicionar a chave de API ao `.env` e ao `config.py`

---

### 2.2 O agente LangGraph está desabilitado e com bugs

**Arquivo:** [backend/app/api/v1/router.py](backend/app/api/v1/router.py#L44-L46)

```python
# TODO: Ativar quando dependências forem resolvidas
# from app.api.v1.routes import analyze
```

Além de estar comentado, o agente tem um bug de estado:

- `state.py` define o campo como `transactions` (linha 6)
- `forecast_node` espera `transactions_df` (arquivo `nodes/forecast.py`, linha 10)

Isso causaria `KeyError` na primeira execução.

**O que precisa ser feito:**
- Resolver dependências do LangGraph
- Corrigir o mismatch de campos no `FinancialState`
- Registrar `analyze.router` no `router.py`
- Testar o grafo completo (recurrence → forecast → explain)

---

### 2.3 O agente não tem acesso ao F3 (simulador de carro/casa)

O objetivo do produto inclui responder "como comprar um carro/casa mais barato". O `ArchitectService` (F3) implementa exatamente isso. Mas o agente não tem nenhuma tool/node que chame o `ArchitectService`.

**O que precisa ser feito:**
- Criar uma tool `simulate_purchase(target_value, asset_type, down_payment, months)` que chama `ArchitectService`
- Adicionar essa tool ao agente como um nó ou ferramenta disponível
- O agente precisa ser capaz de decidir quando chamar essa tool baseado na pergunta do usuário

---

### 2.4 Não existe interface de conversa

**Arquivo:** [backend/app/api/v1/routes/chat.py](backend/app/api/v1/routes/chat.py) — arquivo vazio

Não há endpoint de chat. O usuário não tem como enviar uma pergunta em linguagem natural e receber uma resposta.

**O que precisa ser feito:**
- Implementar `POST /chat` que recebe `{"user_id": "...", "message": "quanto posso gastar este mês?"}`
- Conectar ao agente LangGraph
- Retornar resposta em linguagem natural
- Registrar a rota no `router.py`

---

### 2.5 O agente não tem memória de conversa

Mesmo quando o agente for implementado, cada chamada será independente. Sem memória de conversa, o usuário não pode fazer perguntas de acompanhamento como "e se eu aumentar a entrada para 30%?".

**O que precisa ser feito:**
- Implementar histórico de conversa (pode ser simples: lista de mensagens por sessão no banco)
- Passar o histórico ao LLM para contexto

---

## 3. Dados e persistência

### 3.1 ETL `run_etl_pipeline()` tem 5 passos como TODO

**Arquivo:** [backend/app/etl/runner.py](backend/app/etl/runner.py)

Os comentários `# TODO` nos passos 1, 2, 3, 6 e 7 indicam que `DataIngestor`, `TransactionClassifier`, `RecurringDetector`, `DataQualityValidator` e `UserProfileAnalyzer` existem mas não são chamados nessa função.

**O que precisa ser feito:**
- Integrar os módulos faltantes no `run_etl_pipeline()`
- Ou consolidar com o `NexaRunner` (que já faz isso corretamente) e remover a duplicação

---

### 3.2 F4 não está integrado no `run_etl_pipeline()`

O `PFPJClassifier` está integrado no `NexaRunner` mas não no `run_etl_pipeline()` de `app/etl/runner.py`. As duas funções existem em paralelo com comportamentos diferentes.

**O que precisa ser feito:**
- Unificar os dois pipelines ou documentar claramente qual usar em qual contexto

---

### 3.3 Sem associação entre `item_id` do Pluggy e `user_id` interno

O webhook recebe `item_id` do Pluggy mas o sistema precisa saber a qual `user_id` esse item pertence. Não há tabela de mapeamento `item_id → user_id`.

**O que precisa ser feito:**
- Criar tabela `user_connections (user_id, item_id, institution_id, created_at, status)`
- Popular essa tabela quando o usuário conecta sua conta via Pluggy
- Usar esse mapeamento no webhook para associar transações ao usuário correto

---

### 3.4 Sem limpeza ou expiração de dados

Não há política de retenção de dados. Com o tempo, o banco vai acumular todas as transações históricas sem limite.

**O que precisa ser feito:**
- Definir política de retenção (ex: manter últimos 12 meses)
- Implementar job de limpeza periódica

---

### 3.5 DuckDB em arquivo não suporta múltiplos workers

Em produção com `uvicorn --workers 4`, múltiplos processos tentariam abrir o mesmo arquivo DuckDB simultaneamente, causando erro de lock.

**O que precisa ser feito:**
- Migrar para PostgreSQL, ou
- Garantir deployment com `--workers 1` (limita escalabilidade), ou
- Usar DuckDB em modo in-memory com PostgreSQL para persistência

---

## 4. Segurança

### 4.1 Sem CORS configurado

**Arquivo:** [backend/app/main.py](backend/app/main.py)

O `main.py` não tem `CORSMiddleware`. Se houver um frontend web, todas as requisições vão falhar por CORS.

**O que precisa ser feito:**
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=[...], ...)
```

---

### 4.2 Sem rate limiting

Qualquer IP pode fazer requisições ilimitadas à API. Um atacante pode enumerar `user_id`s ou sobrecarregar os endpoints de simulação (F3 usa Monte Carlo com 2000 iterações por chamada).

**O que precisa ser feito:**
- Adicionar rate limiting por IP e/ou por `user_id` (ex: `slowapi` para FastAPI)

---

### 4.3 Sem validação do webhook do Pluggy

O endpoint `POST /transactions/webhook` aceita qualquer payload sem verificar se veio realmente do Pluggy. Qualquer pessoa pode enviar transações falsas.

**O que precisa ser feito:**
- Validar assinatura HMAC do webhook (Pluggy envia header `x-pluggy-signature`)

---

### 4.4 Credenciais no `.env` sem rotação

**Arquivo:** [backend/.env](backend/.env)

O `.gitignore` do backend protege o `.env`, mas não há mecanismo de rotação de credenciais nem suporte a secrets managers (AWS Secrets Manager, Vault, etc.).

**O que precisa ser feito:**
- Documentar processo de rotação de `PLUGGY_CLIENT_ID` / `PLUGGY_CLIENT_SECRET`
- Considerar suporte a secrets manager para ambientes de produção

---

## 5. Infraestrutura

### 5.1 Sem Dockerfile

Não há `Dockerfile` nem `docker-compose.yml`. Não é possível fazer deploy em nenhum serviço de container (Railway, Render, AWS ECS, etc.) sem criar do zero.

**O que precisa ser feito:**
- Criar `Dockerfile` para o backend
- Criar `docker-compose.yml` para desenvolvimento local com banco de dados

---

### 5.2 Sem variáveis de ambiente documentadas

**Arquivo:** [backend/app/core/config.py](backend/app/core/config.py)

O `config.py` define `PLUGGY_CLIENT_ID`, `PLUGGY_CLIENT_SECRET`, `PLUGGY_BASE_URL` e `FRONTEND_BASE_URL`. Mas quando o LLM e o banco forem adicionados, novas variáveis serão necessárias. Não há `.env.example` no projeto.

**O que precisa ser feito:**
- Criar `.env.example` com todas as variáveis necessárias (sem valores reais)
- Atualizar `config.py` com `LLM_API_KEY`, `DATABASE_URL`, `JWT_SECRET`, etc.

---

### 5.3 Sem health check completo

O `GET /health` retorna apenas `{"status": "ok"}` sem verificar se o banco, o Pluggy ou outros serviços estão acessíveis.

**O que precisa ser feito:**
- Health check deve verificar: conexão com banco, conectividade com Pluggy (opcional), versão da aplicação

---

### 5.4 Sem CI/CD

Não há pipeline de CI (GitHub Actions, etc.) que rode os 414 testes automaticamente em cada push.

**O que precisa ser feito:**
- Criar `.github/workflows/test.yml` que rode `pytest tests/` em cada PR

---

### 5.5 Sem logs estruturados em produção

O projeto usa `logging` padrão do Python com `logger.info(f"...")`. Em produção, logs precisam ser estruturados (JSON) para indexação em ferramentas como Datadog, CloudWatch, etc.

**O que precisa ser feito:**
- Configurar `structlog` (já está como dependência) em `app/core/logging.py` e aplicar em todos os módulos
- Garantir que logs em produção saiam como JSON

---

## 6. Funcionalidades incompletas

### 6.1 F2 — Card Optimizer: 0% implementado

**Arquivo:** [backend/app/api/v1/routes/analyze.py](backend/app/api/v1/routes/analyze.py) — sem lógica de cartões

Nenhuma lógica de análise de cartão existe. O escopo sequer está definido.

**O que precisa ser feito:**
- Definir escopo: o que exatamente o otimizador decide? (custo-benefício por cartão, cashback vs anuidade vs milhas?)
- Implementar calculadora de benefícios por cartão
- Criar endpoint `GET /api/v1/cards/optimize/{user_id}`
- Escrever testes

---

### 6.2 Previsões mensais não implementadas

**Arquivo:** [backend/app/api/v1/routes/forecast.py](backend/app/api/v1/routes/forecast.py#L254)

```python
monthly_forecasts=[]  # TODO: Implementar previsões mensais
```

O `ForecastResponse` tem campo `monthly_forecasts` que sempre retorna lista vazia.

**O que precisa ser feito:**
- Implementar agregação mensal a partir dos dados diários do `CashflowProjector`

---

### 6.3 Alertas por notificação não existem

O endpoint `GET /alerts/{user_id}` retorna alertas quando consultado, mas não há sistema de push. O usuário só recebe alertas se perguntar — nada é enviado proativamente.

**O que precisa ser feito:**
- Definir canal de notificação (push mobile, email, webhook para o app)
- Implementar job que rode periodicamente e dispare alertas críticos

---

### 6.4 Reconexão de consentimento não testada

O endpoint `POST /reconnect/{user_id}` existe e chama `PluggyClient.generate_connect_token()`. Mas como o cliente real nunca foi testado, não há garantia que o fluxo de reconexão funcione com usuários reais.

**O que precisa ser feito:**
- Testar o fluxo completo de reconexão com um item Pluggy real
- Validar que a URL gerada abre o widget de reconexão corretamente

---

## 7. Qualidade de código

### ✅ 7.1 Aviso de compatibilidade Pydantic v2 — RESOLVIDO (2026-02-23)

`config.py`, `alerts.py` e `reconnect.py` migrados de `class Config` para `model_config = ConfigDict(...)` / `SettingsConfigDict(...)`. Warnings zerados nos testes.

---

### ✅ 7.2 Modelo sklearn treinado numa versão antiga — RESOLVIDO (2026-02-23)

Modelo retreinado com `scripts/train_pf_pj_classifier.py` usando a versão atual do sklearn. Os 3 `.pkl` em `backend/models/` foram atualizados.

---

### ✅ 7.3 Arquivos mortos no projeto — RESOLVIDO (2026-02-23)

Deletados:

| Arquivo | Status |
|---|---|
| `app/engines/` (diretório inteiro) | Deletado |
| `app/insights/` (diretório inteiro) | Deletado |
| `app/ml/models/catboost_classifier.py` | Deletado |
| `app/ml/models/neuralprophet_forecaster.py` | Deletado |
| `app/services/finance_engine_service.py` | Deletado |
| `backend/caminho.py` | Deletado |
| `app/db/session.py` e `app/db/models.py` | Pulado — não é responsabilidade desta sprint |

---

### ✅ 7.4 README não documenta o projeto real — RESOLVIDO (2026-02-23)

README reescrito do zero com: o que o sistema faz, instalação, variáveis de ambiente, como rodar, todos os endpoints com descrição, exemplo de uso da API de simulação, estrutura de pastas, links para docs adicionais.

---

### ✅ 7.5 `ARCHITECTURE.md` desatualizado — RESOLVIDO (2026-02-23)

Corrigido: CatBoost removido do stack (é sklearn), contagem de testes atualizada (406→414), `mock_pluggy.py` corrigido, `app/analysis/` removido (não existe), status de F1/F2/F3/F4 atualizado, seção de TODOs reflete o estado real do código.

---

## Ordem de execução recomendada

### Fase 1 — Fundação (sem isso nada funciona de verdade)
1. Decisão de banco de dados (DuckDB ou PostgreSQL) + persistência funcionando
2. Mapeamento `item_id → user_id` (tabela de conexões)
3. Webhook salvando dados no banco
4. `GET /transactions/{user_id}` retornando dados reais
5. `GET /forecast/{user_id}` usando dados reais do usuário
6. Autenticação JWT nos endpoints

### Fase 2 — O produto de IA (o objetivo central)
7. Integrar LLM (Claude API ou equivalente)
8. Corrigir e reativar o agente LangGraph
9. Implementar `POST /chat`
10. Conectar F3 (Architect) como tool do agente
11. Memória de conversa

### Fase 3 — Produção
12. Dockerfile + docker-compose
13. CI/CD com testes automáticos
14. CORS configurado
15. Rate limiting
16. Validação de assinatura do webhook Pluggy
17. Health check completo
18. Variáveis de ambiente documentadas (`.env.example`)

### Fase 4 — Completar produto
19. F2 — Card Optimizer
20. Alertas proativos (push/email)
21. Previsões mensais no forecast
22. Testar Pluggy real end-to-end

### Fase 5 — Limpeza
23. Migrar Pydantic v2
24. Retreinar modelo sklearn
25. Deletar arquivos mortos
26. Atualizar README e ARCHITECTURE.md
