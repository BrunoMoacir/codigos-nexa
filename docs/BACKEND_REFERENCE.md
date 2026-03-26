# Backend Reference — Nexa

Documento de referência completo de todos os arquivos e pastas do diretório `backend/`.
Organizado por camada/módulo. Última atualização: 2026-03-26.

---

## Índice

1. [Estrutura Geral](#estrutura-geral)
2. [Raiz do Backend](#raiz-do-backend)
3. [app/ — Código da Aplicação](#app--código-da-aplicação)
   - [app/main.py — Entry Point](#appmainpy--entry-point)
   - [app/runner.py — Runner CLI](#apprunnerpy--runner-cli)
   - [app/core/ — Infraestrutura](#appcore--infraestrutura)
   - [app/api/v1/ — Camada de Roteamento](#appapiv1--camada-de-roteamento)
   - [app/forecast/ — F1: Previsão Financeira](#appforecast--f1-previsão-financeira)
   - [app/optimizer/ — F2: Otimização de Cartões](#appoptimizer--f2-otimização-de-cartões)
   - [app/architect/ — F3: Simulador de Metas](#apparchitect--f3-simulador-de-metas)
   - [app/divider/ — F4: Classificação PF/PJ](#appdivider--f4-classificação-pfpj)
   - [app/costs/ — F5: Raio-X Bancário](#appcosts--f5-raio-x-bancário)
   - [app/purchase/ — F7: Modo de Compra](#apppurchase--f7-modo-de-compra)
   - [app/negotiator/ — F13: Scripts de Negociação](#appnegotiator--f13-scripts-de-negociação)
   - [app/budget/ — M1.3: Orçamento Inteligente](#appbudget--m13-orçamento-inteligente)
   - [app/subscriptions/ — M1.5: Gestão de Assinaturas](#appsubscriptions--m15-gestão-de-assinaturas)
   - [app/fiscal/ — M4.1: Relatório Fiscal PJ](#appfiscal--m41-relatório-fiscal-pj)
   - [app/health_score/ — MX.1: Score de Saúde](#apphealth_score--mx1-score-de-saúde)
   - [app/goals/ — MX.2: Metas Financeiras](#appgoals--mx2-metas-financeiras)
   - [app/notifications/ — MX.3: Notificações](#appnotifications--mx3-notificações)
   - [app/peers/ — MX.4: Comparação com Pares](#apppeers--mx4-comparação-com-pares)
   - [app/agent/ — Agente de IA (ReAct)](#appagent--agente-de-ia-react)
   - [app/adapters/ — Adaptadores de Banco](#appadapters--adaptadores-de-banco)
   - [app/domain/ — Domínio](#appdomain--domínio)
   - [app/ml/ — Machine Learning](#appml--machine-learning)
4. [alembic/ — Migrações de Banco](#alembic--migrações-de-banco)
5. [data/ — Dados Estáticos e Seeds](#data--dados-estáticos-e-seeds)
6. [models/ — Modelos ML Serializados](#models--modelos-ml-serializados)
7. [scripts/ — Scripts Utilitários](#scripts--scripts-utilitários)
8. [tests/ — Suite de Testes](#tests--suite-de-testes)
9. [Padrões Arquiteturais](#padrões-arquiteturais)
10. [Fluxo de Dados Principal](#fluxo-de-dados-principal)

---

## Estrutura Geral

```
backend/
├── app/                        # Código da aplicação FastAPI
│   ├── main.py                 # Entry point: inicializa FastAPI, CORS, routers
│   ├── runner.py               # Runner CLI para jobs offline
│   ├── core/                   # Infraestrutura: config, DB, segurança, schemas
│   ├── api/v1/                 # Camada de roteamento HTTP
│   ├── forecast/               # F1: ETL pipeline + previsão de cashflow
│   ├── optimizer/              # F2: Otimização de cartões de crédito
│   ├── architect/              # F3: Simulador financiamento vs consórcio vs poupança
│   ├── divider/                # F4: Classificação PF vs PJ
│   ├── costs/                  # F5: Raio-X bancário (análise de tarifas)
│   ├── purchase/               # F7: Modo de compra inteligente
│   ├── negotiator/             # F13: Scripts de negociação bancária
│   ├── budget/                 # M1.3: Orçamento inteligente (50/30/20)
│   ├── subscriptions/          # M1.5: Detecção de assinaturas e parcelamentos
│   ├── fiscal/                 # M4.1: Relatório fiscal PJ/MEI
│   ├── health_score/           # MX.1: Score de saúde financeira
│   ├── goals/                  # MX.2: Metas financeiras
│   ├── notifications/          # MX.3: Notificações e alertas
│   ├── peers/                  # MX.4: Comparação com benchmarks
│   ├── agent/                  # Agente de IA conversacional (LangGraph ReAct)
│   ├── adapters/               # Adaptadores de banco
│   ├── domain/                 # Motor de cálculo financeiro central
│   └── ml/                     # Módulo de machine learning
├── alembic/                    # Migrações Alembic (PostgreSQL prod)
├── data/                       # Dados estáticos: cartões, taxas, seeds
├── models/                     # Modelos ML serializados (.pkl)
├── scripts/                    # Scripts utilitários (db, seed, ml, debug)
├── tests/                      # Suite de testes pytest
├── finance.duckdb              # Banco DuckDB local (desenvolvimento) — 8.3 MB, 6 tabelas
├── alembic.ini                 # Configuração do Alembic
├── pyproject.toml              # Dependências Poetry
├── requirements.txt            # Dependências pip
└── .env.example                # Template de variáveis de ambiente
```

---

## Raiz do Backend

### `finance.duckdb`
Banco de dados DuckDB local usado em desenvolvimento. Contém 6 tabelas: `users`, `transactions`, `pluggy_items`, `architect_simulations`, `health_score_history`, `financial_goals`. **Este é o arquivo canônico** — os outros `finance.duckdb` encontrados no projeto são vazios e foram removidos.

### `alembic.ini`
Configuração do Alembic para migrações no PostgreSQL (produção). Aponta para `alembic/env.py`. Em desenvolvimento usa DuckDB diretamente via `scripts/db/apply_migrations.py`.

### `pyproject.toml`
Gerenciamento de dependências com Poetry. Inclui: fastapi, uvicorn, sqlalchemy, duckdb, langchain, langgraph, catboost, pluggy-sdk, pydantic v2, alembic, jwt.

### `requirements.txt`
Lista flat de dependências para instalação via `pip install -r requirements.txt` (gerado a partir do `pyproject.toml`).

### `.env.example`
Template de variáveis de ambiente necessárias. Copiar para `.env` e preencher antes de rodar. Variáveis incluem: `DATABASE_URL`, `PLUGGY_CLIENT_ID`, `PLUGGY_CLIENT_SECRET`, `SECRET_KEY`, `OPENAI_API_KEY`.

### `streamlit_agent_test.py`
Script de teste manual da interface Streamlit para o agente conversacional. Roda localmente para validar a integração frontend ↔ agente.

---

## app/ — Código da Aplicação

### `app/main.py` — Entry Point

**O que faz:** Inicializa a aplicação FastAPI completa.

**Responsabilidades:**
- Cria a instância `FastAPI` com título, versão e documentação
- Configura CORS (Cross-Origin Resource Sharing) para permitir requisições do frontend
- Configura rate limiting via `SlowAPI` (ex: 100 req/min por IP)
- Inclui todos os routers agregados em `app/api/v1/router.py`
- No evento `startup`: cria as tabelas no DuckDB (se não existirem) via `database.create_tables()`
- Define endpoints utilitários: `GET /health` (liveness check) e `GET /version`

**Como usar:**
```bash
cd backend/
uvicorn app.main:app --reload --port 8000
# Documentação: http://localhost:8000/docs
```

---

### `app/runner.py` — Runner CLI

**O que faz:** Runner standalone para executar o pipeline ETL de forma offline (sem requisição HTTP).

**Responsabilidades:**
- Aceita `user_id` como argumento
- Busca as transações do usuário via Pluggy (ou mock)
- Executa o pipeline completo: `etl/runner.py → forecast/router.py`
- Útil para processamento em background (cron jobs, filas)

**Como usar:**
```bash
cd backend/
python app/runner.py --user-id <user_id>
```

---

### `app/core/` — Infraestrutura

Camada de infraestrutura compartilhada por todos os módulos.

---

#### `app/core/config.py`
**Configuração centralizada da aplicação.**

Usa `pydantic-settings` para carregar variáveis de ambiente com validação. Exporta um objeto `settings` global com:
- `DATABASE_URL`: URL do PostgreSQL (produção) ou path do DuckDB (dev)
- `PLUGGY_CLIENT_ID` / `PLUGGY_CLIENT_SECRET`: Credenciais da API Pluggy
- `SECRET_KEY`: Chave para assinar JWTs
- `OPENAI_API_KEY`: Chave para o modelo de linguagem do agente
- `ENVIRONMENT`: `"development"` ou `"production"` — controla qual banco e qual Pluggy (real vs mock)

---

#### `app/core/database.py`
**Configuração do SQLAlchemy e DuckDB.**

- Cria o `engine` SQLAlchemy apontando para DuckDB (dev) ou PostgreSQL (prod)
- Define `SessionLocal`: classe de sessão para uso com `get_db()`
- Define `Base`: classe base para todos os modelos ORM
- Exporta `create_tables()`: cria todas as tabelas a partir dos modelos ORM registrados
- Em produção, usa `DATABASE_URL` do `.env`; em desenvolvimento, resolve o path do `finance.duckdb` com fallback multi-candidato

---

#### `app/core/logging.py`
**Configuração do sistema de logs.**

Configura `structlog` para logs estruturados em JSON (produção) ou formato legível (desenvolvimento). Todos os módulos importam o logger daqui para manter consistência.

---

#### `app/core/security.py`
**Autenticação JWT e hashing de senhas.**

Funções exportadas:
- `hash_password(password: str) → str`: Usa bcrypt para hashear senha
- `verify_password(plain, hashed) → bool`: Verifica senha contra hash
- `create_access_token(data: dict) → str`: Gera JWT com expiração
- `get_current_user(token) → User`: Dependency do FastAPI — decodifica JWT e retorna usuário autenticado

---

#### `app/core/recurrence.py`
**Detecção de padrões recorrentes.**

Funções utilitárias usadas pelo ETL e pelo módulo de assinaturas:
- Detecta transações com mesmo valor (±5%) e mesma periodicidade (semanal/mensal)
- Calcula score de confiança da recorrência
- Identifica padrões por janela deslizante nos últimos 90 dias

---

#### `app/core/explain.py`
**Motor de explicação financeira.**

Gera explicações em linguagem natural para análises financeiras. Usado pelo agente para formatar respostas. Recebe métricas numéricas e retorna texto interpretativo (ex: "Seu gasto em alimentação está 23% acima da média para sua faixa de renda").

---

#### `app/core/shadow_invoices.py`
**Modelos e utilitários core para shadow invoices.**

Define o conceito central de "shadow invoice" (obrigação futura ainda não lançada como transação). Inclui:
- Dataclasses `ShadowInvoice`, `Subscription`, `Installment`
- Funções de cálculo: data de próxima cobrança, valor projetado, impacto no cashflow

---

#### `app/core/models/` — Modelos ORM

Modelos SQLAlchemy mapeados para tabelas no banco.

| Arquivo | Classe | Tabela | Campos Principais |
|---------|--------|--------|-------------------|
| `base.py` | `Base` | — | Classe base abstrata SQLAlchemy |
| `user.py` | `User` | `users` | `user_id` (UUID), `email`, `hashed_password`, `full_name`, `created_at` |
| `transaction.py` | `Transaction` | `transactions` | `transaction_id`, `user_id`, `amount`, `date`, `description`, `category`, `context_type` (PF/PJ), `is_recurring`, `is_installment`, `pj_subcategory` |
| `pluggy_item.py` | `PluggyItem` | `pluggy_items` | `item_id`, `user_id`, `bank_name`, `account_id`, `status`, `last_sync` |

`__init__.py` exporta todos os modelos para que `create_tables()` possa registrá-los.

---

#### `app/core/schemas/` — Schemas Pydantic

Contratos de entrada/saída da API (validação e serialização).

| Arquivo | Schemas | Uso |
|---------|---------|-----|
| `enums.py` | `BankTier`, `DataStatus`, `DataSource`, `TransactionStatus`, `TransactionCategory` | Enums usados em todos os schemas |
| `transaction.py` | `TransactionWebhook`, `TransactionBatchResult` | Recebimento de transações via webhook Pluggy |

`__init__.py` exporta todos os schemas e enums para importação centralizada.

---

#### `app/core/db/` — Camada de Acesso ao Banco

Implementa o **Repository Pattern**: abstrai queries SQL/DuckDB dos módulos de negócio.

| Arquivo | Função | Descrição |
|---------|--------|-----------|
| `session.py` | `get_db()` | Dependency FastAPI: abre/fecha sessão SQLAlchemy |
| `models.py` | — | Registro de todos os modelos ORM |
| `users.py` | `get_user_by_email()`, `create_user()`, `get_user_by_id()` | CRUD de usuários |
| `queries.py` | `get_transactions_for_user()`, filtros, agregações | Queries de transações com filtro por data, categoria, valor. Inclui fallback multi-candidato para resolver o path do DuckDB |

**Nota sobre `queries.py`:** Resolve o DuckDB via lista de candidatos de path (`backend/finance.duckdb`, `./finance.duckdb`, etc.) para garantir funcionamento independente do diretório de execução.

---

#### `app/core/db/migrations/` — Migrations SQL

Scripts SQL aplicados manualmente via `scripts/db/apply_migrations.py` (desenvolvimento com DuckDB).

| Arquivo | O que adiciona |
|---------|---------------|
| `001_add_context_fields.sql` | Colunas `context_type`, `pj_subcategory`, `context_confidence` em `transactions` |
| `002_create_context_overrides.sql` | Tabela `context_overrides` para overrides manuais de usuário |
| `003_create_architect_tables.sql` | Tabelas `architect_simulations`, `architect_metrics` |
| `004_create_health_score_history.sql` | Tabela `health_score_history` (histórico do score) |
| `005_create_financial_goals.sql` | Tabela `financial_goals` |

---

#### `app/core/integrations/` — Integrações Externas

| Arquivo | Classe | Descrição |
|---------|--------|-----------|
| `pluggy.py` | `PluggyClient` | Cliente real da API Open Finance Pluggy: `authenticate()`, `get_accounts()`, `get_transactions()`, `sync_item()` |
| `pluggy_mock.py` | `PluggyMockClient` | Implementação mock para desenvolvimento/testes: retorna dados realistas sem chamada à API real |

O `config.py` controla qual implementação é injetada com base em `ENVIRONMENT`.

---

### `app/api/v1/` — Camada de Roteamento

#### `app/api/v1/router.py`
**Agregador de todos os routers de feature.**

Inclui (via `include_router`) todos os routers dos módulos: forecast, optimizer, architect, divider, costs, purchase, negotiator, budget, goals, health_score, fiscal, subscriptions, agent, auth, pluggy, dashboard.

#### `app/api/v1/routes/`

| Arquivo | Endpoints | Descrição |
|---------|-----------|-----------|
| `auth.py` | `POST /auth/register`, `POST /auth/login` | Registro e login. Login retorna JWT Bearer token |
| `pluggy.py` | `POST /pluggy/connect`, `PATCH /pluggy/update`, `GET /pluggy/balances` | Integração bancária via Pluggy: criar conexão, atualizar, buscar saldos |
| `reconnect.py` | `POST /pluggy/reconnect` | Reconectar conta bancária (reautenticação Pluggy) |
| `analyze.py` | `GET /analyze/{user_id}` | Análise financeira geral |
| `bank_simulation.py` | `POST /bank/simulate` | Simulação de cenários bancários |
| `dashboard.py` | `GET /dashboard/{user_id}` | Dados agregados para o dashboard (saldo, cashflow, alertas) |

---

### `app/forecast/` — F1: Previsão Financeira

**Módulo central da Nexa.** Orquestra o ETL pipeline, projeção de cashflow, shadow invoices e score de saúde.

---

#### Routers

| Arquivo | Endpoint | Descrição |
|---------|----------|-----------|
| `router.py` | `GET /forecast/{user_id}` | **Principal**: executa pipeline completo e retorna `ForecastResponse` com cashflow 30 dias, safe-to-spend, shadow invoices, health score e risk assessment |
| `router_transactions.py` | `POST /transactions/webhook` | Recebe novas transações via webhook Pluggy, executa ingestor + classifier, persiste no banco |
| `router_shadow_invoice.py` | `GET /shadow-invoices/{user_id}` | Retorna lista de shadow invoices (assinaturas + parcelas futuras) |
| `router_alerts.py` | `GET /alerts/{user_id}` | Retorna alertas ativos (gasto excessivo, saldo crítico, etc.) |
| `router_safe_to_spend.py` | `GET /safe-to-spend/{user_id}` | Retorna quanto o usuário pode gastar com segurança hoje |

---

#### Schemas

| Arquivo | Schemas Principais |
|---------|--------------------|
| `schemas.py` | Tipos base compartilhados |
| `schemas_cashflow.py` | `DailyBalance`, `CashflowProjection`, `BurnRate` |
| `schemas_forecast.py` | `ForecastResponse` (resposta completa do `/forecast/{user_id}`) |
| `schemas_safe_to_spend.py` | `SafeToSpendResult` com breakdown do cálculo |
| `schemas_shadow_invoice.py` | `ShadowInvoice`, `Subscription`, `Installment` |

---

#### `app/forecast/cashflow/` — Motor de Cashflow

| Arquivo | Classe / Função | Descrição |
|---------|-----------------|-----------|
| `engine.py` | `CashflowEngine` | Agrega os demais componentes: retorna `CashflowProjection` completa |
| `projector.py` | `CashflowProjector` | Projeta saldos diários dos próximos 30 dias: soma receitas fixas, subtrai despesas fixas e variáveis com decaimento exponencial |
| `burn_rate.py` | `calculate_burn_rate()` | Calcula taxa de queima mensal (tendência de gasto) via regressão linear nos últimos 3 meses |
| `safe_to_spend.py` | `SafeToSpendCalculator` | Calcula margem segura para gastar: `(saldo atual) - (despesas fixas até fim do mês) - (buffer de emergência)` |

---

#### `app/forecast/etl/` — Pipeline ETL (8 Etapas)

**O coração do processamento de dados da Nexa.**

```
Pluggy API → [1. Ingestor] → [2. Classifier] → [3. Recurring Detector]
           → [4. PF/PJ Divider] → [5. Shadow Invoice] → [6. Data Quality]
           → [7. Income Profiler] → [8. Loader/Saver]
```

| Arquivo | Etapa | Classe | Responsabilidade |
|---------|-------|--------|-----------------|
| `runner.py` | Orquestrador | `ETLRunner` | Encadeia as 8 etapas, propaga contexto, trata erros por etapa |
| `ingestor.py` | 1 | `TransactionIngestor` | Normaliza transações brutas do Pluggy usando a estratégia de banco correspondente. Converte campos heterogêneos (ex: `valor` vs `amount`) para schema interno |
| `classifier.py` | 2 | `TransactionClassifier` | Classifica categoria da transação (alimentação, transporte, etc.) via modelo ML (CatBoost) + fallback por regras de palavras-chave. Retorna categoria + score de confiança |
| `recurring_detector.py` | 3 | `RecurringDetector` | Detecta padrões recorrentes: mesmo valor (±5%), mesma data (±5 dias), janela 90 dias. Marca `is_recurring=True` e `is_installment=True` |
| `income_profiler.py` | 7 | `IncomeProfiler` | Detecta padrões de renda: valores positivos recorrentes, frequência mensal/quinzenal, identifica salário vs freela vs aluguel |
| `spending_anomaly_detector.py` | — | `SpendingAnomalyDetector` | Detecta gastos anômalos: valores 3σ acima da média histórica por categoria |
| `mixed_use_detector.py` | — | `MixedUseDetector` | Detecta transações com uso misto PF+PJ (ex: combustível que pode ser pessoal ou comercial) |
| `data_quality.py` | 6 | `DataQualityChecker` | Valida completude dos dados: transações sem categoria, duplicatas, valores zerados, datas inválidas |
| `loader.py` | 8 | `TransactionLoader` | Persiste transações processadas no banco. Implementa upsert (insere ou atualiza) para evitar duplicatas |

---

#### `app/forecast/etl/bank_strategy/` — Estratégias por Banco

Implementa o **Strategy Pattern** para normalização banco-específica.

| Arquivo | Classe | Banco |
|---------|--------|-------|
| `base.py` | `BankStrategy` (ABC) | Interface abstrata: `normalize(raw_transaction) → Transaction` |
| `registry.py` | `BankStrategyRegistry` | Mapeia `bank_id → Strategy`. Carrega estratégias dinamicamente |
| `config/bank_profiles.yaml` | — | Configuração declarativa: mapeamento de campos por banco (ex: `itau.valor_transacao → amount`) |
| `strategies/default.py` | `DefaultStrategy` | Estratégia padrão para bancos sem implementação específica |
| `strategies/itau.py` | `ItauStrategy` | Normalização específica do Itaú: campos, encoding de categorias, timezone |
| `strategies/inter.py` | `InterStrategy` | Normalização específica do Inter |
| `strategies/nubank.py` | `NubankStrategy` | Normalização específica do Nubank |

---

#### `app/forecast/etl/dedup/` — Deduplicação

| Arquivo | Classe | Descrição |
|---------|--------|-----------|
| `base.py` | `DeduplicationStrategy` (ABC) | Interface: `deduplicate(transactions) → transactions` |
| `default.py` | `DefaultDeduplication` | Remove duplicatas por hash de (data, valor, descrição, conta). Mantém a versão mais recente |

---

### `app/optimizer/` — F2: Otimização de Cartões

**Analisa padrões de gasto e recomenda a melhor carteira de cartões de crédito.**

---

#### `app/optimizer/router.py`
`POST /optimizer/analyze` — Recebe `OptimizationRequest` (user_id, gastos por categoria), retorna `OptimizationReport` com cartões recomendados, ROI esperado e oportunidade de milhas.

---

#### Módulos Core

| Arquivo | Classe | Função |
|---------|--------|--------|
| `card_loader.py` | `CardLoader` | Carrega base de dados de cartões de `data/cards/knowledge_cards.json`: benefícios, cashback por categoria, anuidade, tier |
| `miles_valuator.py` | `MilesValuator` | Calcula valor de pontos/milhas em R$ para cada programa de fidelidade, usando `data/cards/miles_valuation.json` |
| `promotion_tracker.py` | `PromotionTracker` | Rastreia promoções ativas de transferência de pontos (ex: Amex → Latam 1:1.5). Usa `data/cards/transfer_promotions.json` |
| `profiler.py` | `SpendingProfiler` | Analisa gasto do usuário por categoria: quanto gasta mensalmente em alimentação, viagens, farmácia, etc. |
| `ranking.py` | `CardRanker` | Ranqueia cartões por ROI para o perfil do usuário: cashback + milhas + benefícios - anuidade |
| `multi_card_strategy.py` | `MultiCardStrategist` | Otimiza portfólio de cartões: qual cartão usar em cada categoria para maximizar retorno total |
| `opportunity_cost.py` | `OpportunityCostCalculator` | Calcula custo de oportunidade de usar cada cartão vs alternativa ótima |
| `simulator.py` | `CardSimulator` | Simula retorno esperado anual para uma combinação de cartões e perfil de gasto |

#### `app/optimizer/services/optimizer_service.py`
`OptimizerService` — Orquestrador: perfil → ranking → estratégia → relatório.

#### `app/optimizer/validators/`
- `input_validator.py`: Valida `OptimizationRequest` (limites de gasto, categorias válidas)
- `liquidity_checker.py`: Verifica se anuidades dos cartões recomendados cabem no orçamento

#### `app/optimizer/models.py`
Schemas Pydantic: `OptimizationRequest`, `CardRecommendation`, `OptimizationReport`.

#### `app/optimizer/models_orm.py`
ORM `OptimizationReport` para persistir relatórios gerados.

#### `app/optimizer/queries.py`
Queries para buscar transações do usuário agregadas por categoria (insumo do profiler).

---

### `app/architect/` — F3: Simulador de Metas

**Simula e compara 3 estratégias para aquisição de um bem: financiamento, consórcio e investimento/poupança.**

---

#### `app/architect/router.py`
| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/architect/simulate` | POST | Executa simulação comparativa das 3 estratégias |
| `/architect/simulations` | GET | Lista simulações anteriores do usuário |
| `/architect/simulations/{id}` | GET | Detalhes de uma simulação |
| `/architect/metrics` | GET | Métricas do usuário (capacidade de poupança, renda) |

---

#### `app/architect/calculators/` — Calculadoras Financeiras

| Arquivo | Classe | Cálculo |
|---------|--------|---------|
| `financing.py` | `FinancingCalculator` | Tabela Price / SAC: parcela mensal, total de juros, cronograma de amortização, comparativo de taxas |
| `consortium.py` | `ConsortiumCalculator` | Consórcio BR: contribuição mensal, probabilidade de contemplação (lance vs sorteio), tempo médio, custo total |
| `investment.py` | `InvestmentCalculator` | Crescimento composto: poupança mensal + taxa de retorno (CDI, IPCA+), quando atinge o valor alvo |
| `npv.py` | `NPVCalculator` | VPL (Valor Presente Líquido) e TIR para comparar as estratégias em termos de custo real |
| `leverage_optimizer.py` | `LeverageOptimizer` | Otimiza uso de alavancagem: relação dívida/renda, custo do capital, risco |

---

#### `app/architect/simulators/` — Simuladores

| Arquivo | Classe | Descrição |
|---------|--------|-----------|
| `strategy_engine.py` | `StrategyEngine` | **Core**: executa as 3 calculadoras em paralelo, identifica ponto de breakeven, recomenda estratégia ótima dado o perfil |
| `monte_carlo.py` | `MonteCarloSimulator` | Simula 10.000 cenários com variação de taxa de juros, crescimento salarial e inflação para estimar range de resultados |
| `sensitivity_analyzer.py` | `SensitivityAnalyzer` | Análise "e se": "O que muda se a taxa Selic subir 2%?" — gera tabela de sensibilidade |

---

#### `app/architect/connectors/` — Dados de Mercado

Conectores para dados externos usados nos cálculos.

| Arquivo | Classe | Fonte |
|---------|--------|-------|
| `bacen.py` | `BacenConnector` | API do Banco Central: SELIC, spread bancário |
| `anbima.py` | `AnbimaConnector` | ANBIMA: yields de títulos, curva de juros |
| `ipca.py` | `IPCAConnector` | IBGE via BACEN: inflação IPCA atual e histórica |
| `abac.py` | `AbacConnector` | ABAC (consórcios): taxas médias de administração |
| `real_estate.py` | `RealEstateConnector` | Dados de mercado imobiliário (FipeZAP) |
| `consortium_rate_provider.py` | `ConsortiumRateProvider` | Taxas de consórcio por categoria (imóvel, veículo) |
| `market_rates.py` | `MarketRateAggregator` | Agrega todos os conectores, aplica cache de 1 hora |
| `base.py` | `MarketRateConnector` (ABC) | Interface abstrata para conectores |

---

#### `app/architect/services/architect_service.py`
`ArchitectService` — Orquestrador: valida input → busca taxas de mercado → executa `StrategyEngine` → persiste resultados.

#### `app/architect/validators/`
- `input_validator.py`: Valida `SimulationRequest` (valor do bem, prazo, renda, entrada mínima)
- `liquidity_validator.py`: Verifica se o usuário tem capacidade financeira para cada estratégia

#### `app/architect/utils/`
- `cache.py`: Cache em memória para taxas de mercado (TTL 1h)
- `date_helpers.py`: Funções de data para cálculos financeiros (ex: dias úteis, meses corridos)
- `formatters.py`: Formatação de saída: `R$ 1.234,56`, `12,5% a.a.`

#### `app/architect/models.py`
Schemas Pydantic: `SimulationRequest`, `SimulationResponse`, `FinancingResult`, `ConsortiumResult`, `InvestmentResult`, `TimingScenario`.

#### `app/architect/models_orm.py`
ORM `ArchitectSimulation` e `ArchitectSimulationMetrics` para persistência de simulações.

---

### `app/divider/` — F4: Classificação PF/PJ

**Separa transações entre uso pessoal (PF) e empresarial (PJ/MEI).**

---

#### `app/divider/router.py`
- `GET /divider/{user_id}`: Classifica todas as transações do usuário
- `POST /divider/override`: Permite ao usuário corrigir classificações manualmente (salva em `context_overrides`)

#### `app/divider/classifier.py`
`PFPJClassifier` — Pipeline de classificação:
1. Verifica override manual do usuário (prioridade máxima)
2. Aplica modelo ML (`models/pf_pj_classifier.pkl`) com features de texto + valor + data
3. Se confiança < threshold: aplica regras heurísticas (`scripts/ml/pf_pj_fallback_rules.py`)
4. Retorna `context_type` ("PF" ou "PJ") + `context_confidence` (0.0–1.0)

#### `app/divider/subcategory_classifier.py`
`PJSubcategoryClassifier` — Para transações PJ, classifica subcategoria: `insumos`, `servicos`, `equipamentos`, `utilidades`, `pessoal`, `impostos`.

#### `app/divider/models.py`
Schemas: `ContextOverride`, `ClassificationResult`, `DividerReport`.

---

### `app/costs/` — F5: Raio-X Bancário

**Analisa tarifas bancárias cobradas, compara com o mercado e sugere economia.**

---

#### `app/costs/router.py`
`GET /costs/{user_id}` — Retorna `BankCostReport` com lista de tarifas detectadas, CBT (Custo Bancário Total), benchmark de mercado e oportunidades de redução.

#### `app/costs/fee_detector.py`
`FeeDetector` — Identifica tarifas em transações por padrões de descrição:
- Taxa de manutenção de conta
- IOF sobre crédito
- Tarifa de transferência TED/DOC
- Taxa de saque
- Cobrança de anuidade de cartão

#### `app/costs/bank_fee_analyzer.py`
`BankFeeAnalyzer` — Agrega tarifas detectadas:
- Soma por tipo de tarifa e por banco
- Calcula CBT mensal e anual
- Compara com benchmarks do mercado (`market_fees_db.py`)
- Gera oportunidades: "Trocar para conta digital economizaria R$ 47/mês"

#### `app/costs/market_fees_db.py`
Base de dados estática de tarifas médias por banco e tipo de conta (tradicionais vs digitais vs premium).

#### `app/costs/models.py`
Schemas: `FeeEntry`, `FeeType` (enum), `BankFeeSummary`, `BankCostReport`, `MarketBenchmark`.

---

### `app/purchase/` — F7: Modo de Compra Inteligente

**Recomenda a melhor forma de pagar uma compra específica.**

---

#### `app/purchase/router.py`
`GET /purchase/recommend?user_id=&amount=&category=` — Retorna `PaymentRecommendation`.

#### `app/purchase/purchase_advisor.py`
`PurchaseAdvisor` — Analisa as opções disponíveis:
- À vista com desconto vs parcelado sem juros
- Qual cartão usar (integra com optimizer)
- Financiamento curto prazo vs usar reserva
- Retorna ranking de opções com custo real de cada uma

#### `app/purchase/models.py`
Schemas: `PurchaseRequest`, `PaymentOption`, `PaymentRecommendation`.

---

### `app/negotiator/` — F13: Scripts de Negociação

**Gera roteiros personalizados para negociar redução de tarifas bancárias.**

---

#### `app/negotiator/router.py`
`GET /negotiator/script/{user_id}` — Retorna `NegotiationScript` com argumentos e roteiro de abordagem.

#### `app/negotiator/opportunity_detector.py`
`NegotiationOpportunityDetector` — Detecta alavancas de negociação:
- Tarifas acima da média de mercado
- Tempo como cliente (> 2 anos)
- Histórico de pagamentos em dia
- Volume de movimentação

#### `app/negotiator/script_generator.py`
`NegotiationScriptGenerator` — Gera roteiro personalizado em linguagem natural:
- Argumentos específicos para o banco
- Valor-alvo da redução
- Alternativas a mencionar (concorrentes)
- Perguntas de fechamento

#### `app/negotiator/models.py`
Schemas: `NegotiationOpportunity`, `NegotiationScript`, `NegotiationTactic`.

---

### `app/budget/` — M1.3: Orçamento Inteligente

**Analisa a distribuição de gastos contra o modelo 50/30/20.**

---

#### `app/budget/router.py`
`GET /budget/advice/{user_id}` — Retorna análise comparativa com o modelo ideal.

#### `app/budget/budget_advisor.py`
`BudgetAdvisor` — Classifica transações em:
- **Necessidades (50%)**: moradia, alimentação, transporte, saúde
- **Desejos (30%)**: lazer, restaurantes, assinaturas
- **Poupança/Investimento (20%)**: aportes, reserva de emergência

Compara percentuais reais com ideais e aponta desvios.

---

### `app/subscriptions/` — M1.5: Gestão de Assinaturas

**Detecta assinaturas ativas, esquecidas e aumentos de preço.**

---

#### `app/subscriptions/router.py`
`GET /subscriptions/{user_id}` — Lista todas as assinaturas detectadas com status (ativa, esquecida, aumento de preço).

#### `app/subscriptions/subscription_detector.py`
`SubscriptionDetector` — Identifica assinaturas por padrão de recorrência mensal + descrição (Netflix, Spotify, etc.). Detecta "assinaturas fantasma" (cobranças esquecidas).

#### `app/subscriptions/shadow_invoices/`

| Arquivo | Classe | Descrição |
|---------|--------|-----------|
| `runner.py` | `ShadowInvoiceRunner` | Orquestra detecção de assinaturas + parcelamentos |
| `subscription_detector.py` | `ShadowSubscriptionDetector` | Detecta assinaturas como shadow invoices (obrigações futuras) |
| `installment_detector.py` | `InstallmentDetector` | Detecta parcelamentos em curso e projeta parcelas futuras |
| `base.py` | `BaseShadowDetector` (ABC) | Interface abstrata |

---

### `app/fiscal/` — M4.1: Relatório Fiscal PJ

**Gera relatório fiscal para usuários PJ/MEI com estimativa de DAS.**

---

#### `app/fiscal/router.py`
`GET /fiscal/{user_id}` — Retorna `FiscalReport` com receitas, despesas dedutíveis e estimativa de impostos.

#### `app/fiscal/fiscal_report.py`
`FiscalReportGenerator` — Agrega transações classificadas como PJ:
- Separa receitas de despesas
- Identifica despesas dedutíveis
- Calcula base de cálculo para DAS (MEI) ou Simples Nacional
- Gera relatório mensal e acumulado anual

---

### `app/health_score/` — MX.1: Score de Saúde Financeira

**Calcula e acompanha o score de saúde financeira do usuário (0–100).**

---

#### `app/health_score/router.py`
`GET /health-score/{user_id}` — Retorna score atual + histórico + breakdown por dimensão.

#### `app/health_score/models.py`
ORM `HealthScoreHistory` (tabela de histórico). Schemas: `HealthScoreResult`, `HealthDimension`.

O score é composto por dimensões:
- **Reserva de emergência** (peso 25%): meses de despesas no caixa
- **Comprometimento de renda** (peso 25%): % da renda comprometida com dívidas
- **Regularidade de poupança** (peso 20%): consistência de aportes
- **Diversificação** (peso 15%): variedade de fontes de renda e investimentos
- **Controle de gastos** (peso 15%): gastos vs orçamento planejado

---

### `app/goals/` — MX.2: Metas Financeiras

**CRUD e acompanhamento de metas financeiras.**

---

#### `app/goals/router.py`
| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/goals` | POST | Cria nova meta |
| `/goals/{user_id}` | GET | Lista metas do usuário |
| `/goals/{id}` | PUT | Atualiza meta |
| `/goals/{id}` | DELETE | Remove meta |

#### `app/goals/tracker.py`
`GoalTracker` — Calcula progresso de cada meta com base no cashflow projetado: "Você atingirá essa meta em X meses no ritmo atual."

#### `app/goals/models.py`
ORM `FinancialGoal`: `goal_id`, `user_id`, `name`, `target_amount`, `current_amount`, `deadline`, `category`.

---

### `app/notifications/` — MX.3: Notificações

**Sistema de notificações e alertas financeiros.**

---

#### `app/notifications/router.py`
- `GET /notifications/{user_id}`: Lista notificações ativas
- `PATCH /notifications/{id}/read`: Marca como lida
- `PUT /notifications/preferences`: Atualiza preferências de notificação

#### `app/notifications/notifier.py`
`Notifier` — Gera notificações com base em eventos:
- Saldo abaixo de threshold
- Gasto acima da média em categoria
- Meta atingida
- Nova shadow invoice detectada
- Assinatura com aumento de preço

---

### `app/peers/` — MX.4: Comparação com Pares

**Compara o perfil financeiro do usuário com benchmarks da população.**

---

#### `app/peers/router.py`
`GET /peers/comparison/{user_id}` — Retorna comparativo por categoria de gasto.

#### `app/peers/peer_comparison.py`
`PeerComparison` — Compara gastos do usuário com médias do IBGE/POF (Pesquisa de Orçamentos Familiares) segmentadas por faixa de renda:
- "Você gasta 34% a mais em transporte que a média da sua faixa"
- "Seu comprometimento com moradia está dentro do recomendado"

---

### `app/agent/` — Agente de IA (ReAct)

**Assistente financeiro conversacional baseado em LangGraph (ReAct pattern) com 13 ferramentas.**

---

#### `app/agent/router.py`
`POST /agent/chat` — Recebe `{"user_id": "...", "message": "..."}`, retorna resposta do agente com raciocínio e resultado.

#### `app/agent/graph.py`
`AgentGraph` — Constrói o grafo LangGraph:
- **Nó de raciocínio**: LLM (GPT-4 / Claude) analisa a pergunta e decide qual ferramenta usar
- **Nó de ação**: Executa a ferramenta selecionada
- **Nó de resposta**: Formata a resposta final em linguagem natural
- Loop ReAct: razão → ação → observação → razão (até conclusão)

#### `app/agent/state.py`
`AgentState` — TypedDict do LangGraph: `user_id`, `messages`, `tool_calls`, `intermediate_steps`.

#### `app/agent/nodes/`

| Arquivo | Nó | Descrição |
|---------|-----|-----------|
| `explain.py` | `ExplainNode` | Explica conceitos financeiros (juros compostos, IPCA, etc.) |
| `forecast.py` | `ForecastNode` | Busca e interpreta a previsão de cashflow |
| `recurrence.py` | `RecurrenceNode` | Analisa padrões recorrentes nas transações |

#### `app/agent/tools/` — 13 Ferramentas do Agente

Cada ferramenta é uma função anotada com `@tool` (LangChain) que chama o serviço correspondente:

| Arquivo | Tool | Acessa |
|---------|------|--------|
| `get_financial_forecast.py` | `get_financial_forecast` | `/forecast/{user_id}` |
| `get_budget_advice.py` | `get_budget_advice` | `/budget/advice/{user_id}` |
| `get_card_optimization.py` | `get_card_optimization` | `/optimizer/analyze` |
| `get_spending_alerts.py` | `get_spending_alerts` | `/alerts/{user_id}` |
| `get_goals_summary.py` | `get_goals_summary` | `/goals/{user_id}` |
| `get_financing_simulation.py` | `get_financing_simulation` | `/architect/simulate` (estratégia: financiamento) |
| `get_timing_scenarios.py` | `get_timing_scenarios` | `/architect/simulate` (análise de timing) |
| `get_leverage_simulation.py` | `get_leverage_simulation` | `/architect/simulate` (estratégia: alavancagem) |
| `get_fiscal_report.py` | `get_fiscal_report` | `/fiscal/{user_id}` |
| `get_peer_comparison.py` | `get_peer_comparison` | `/peers/comparison/{user_id}` |
| `get_purchase_recommendation.py` | `get_purchase_recommendation` | `/purchase/recommend` |
| `get_bank_cost_analysis.py` | `get_bank_cost_analysis` | `/costs/{user_id}` |
| `get_negotiation_script.py` | `get_negotiation_script` | `/negotiator/script/{user_id}` |

---

### `app/adapters/` — Adaptadores de Banco

#### `app/adapters/bank_adapter.py`
`BankAdapter` — Camada de abstração entre o cliente Pluggy e o restante da aplicação. Converte respostas da API Pluggy (real ou mock) para o schema interno `Transaction`. Permite trocar de implementação sem alterar o código de negócio.

---

### `app/domain/` — Domínio

#### `app/domain/finance_engine.py`
`FinanceEngine` — Motor de cálculo financeiro central. Agrega operações matemáticas usadas por múltiplos módulos: cálculo de percentuais, agregações por categoria, projeções de crescimento. Evita duplicação de lógica entre módulos.

---

### `app/ml/` — Machine Learning

Pacote para utilitários ML compartilhados. Atualmente serve como namespace; a lógica de ML está nos módulos de uso (classifier no ETL, PF/PJ no divider).

---

## alembic/ — Migrações de Banco

Usado para migrations no **PostgreSQL (produção)** via Alembic.

| Arquivo | Descrição |
|---------|-----------|
| `alembic.ini` | Configuração: URL do banco, diretório de scripts |
| `env.py` | Ambiente Alembic: importa modelos ORM, configura `target_metadata` |
| `script.py.mako` | Template para novos arquivos de migration |

#### `alembic/versions/`

| Arquivo | Migration |
|---------|-----------|
| `40d4950fef06_initial_schema.py` | Schema inicial: tabelas `users`, `transactions`, `pluggy_items` |
| `a3d5b2d33ffb_add_goals_architect_optimizer_tables.py` | Adiciona tabelas `financial_goals`, `architect_simulations`, `optimizer_reports` |

**Como usar (produção):**
```bash
cd backend/
alembic upgrade head        # Aplica todas as migrations pendentes
alembic revision --autogenerate -m "descrição"  # Cria nova migration
alembic downgrade -1        # Reverte última migration
```

**Desenvolvimento (DuckDB):** Usar `scripts/db/apply_migrations.py` em vez do Alembic.

---

## data/ — Dados Estáticos e Seeds

Dados de referência usados em runtime pelos módulos.

### `data/cards/`

| Arquivo | Conteúdo |
|---------|----------|
| `knowledge_cards.json` | Base de dados de cartões de crédito: nome, emissor, anuidade, benefícios, cashback por categoria (alimentação, viagens, farmácia, etc.), tier (basic/gold/platinum/black) |
| `miles_valuation.json` | Valor de conversão de pontos/milhas para R$: Livelo, Smiles, TudoAzul, Multiplus. Atualizado manualmente |
| `transfer_promotions.json` | Promoções ativas de transferência de pontos entre programas: bônus, período de validade |

### `data/architect/`

| Arquivo | Conteúdo |
|---------|----------|
| `market_rates.json` | Taxas de mercado atuais: SELIC, CDI, IPCA, spread médio bancário |
| `selic_history.csv` | Histórico da taxa SELIC (série temporal) |
| `bank_spreads.json` | Spreads bancários por tipo de crédito (pessoal, imobiliário, veículos) |
| `consortium_history.csv` | Histórico de taxas de administração de consórcios |

### `data/`

| Arquivo | Conteúdo |
|---------|----------|
| `training_dataset_pf_pj.csv` | Dataset de treinamento do classificador PF/PJ: features de transação + label (PF/PJ) |
| `training_dataset_pf_pj.parquet` | Mesmo dataset em formato Parquet (mais eficiente para treinamento) |
| `transactions.duckdb` | DuckDB com dados de seed para migrations |

---

## models/ — Modelos ML Serializados

Modelos treinados em formato pickle, carregados em runtime. **Commitados no git** (82 KB total).

| Arquivo | Conteúdo | Carregado por |
|---------|----------|---------------|
| `pf_pj_classifier.pkl` | CatBoost classifier treinado para PF/PJ | `app/divider/classifier.py` |
| `feature_encoders.pkl` | Label encoders para variáveis categóricas | `app/divider/classifier.py` |
| `feature_scaler.pkl` | StandardScaler para features numéricas | `app/divider/classifier.py` |

**Para retreinar:**
```bash
cd backend/
python scripts/ml/create_labeled_dataset.py   # Gera dataset de treinamento
python scripts/ml/train_pf_pj_classifier.py   # Treina e salva novos .pkl
python scripts/ml/validate_pf_pj_classifier.py # Valida métricas (F1, precisão, recall)
```

---

## scripts/ — Scripts Utilitários

Scripts de linha de comando organizados por função. **Não fazem parte da aplicação** — são ferramentas operacionais.

**Como executar** (sempre a partir de `backend/`):
```bash
cd backend/
python scripts/<subpasta>/<arquivo>.py
```

---

### `scripts/db/` — Banco de Dados

| Arquivo | O que faz | Quando usar |
|---------|-----------|-------------|
| `apply_migrations.py` | Aplica os arquivos SQL de `app/core/db/migrations/` no DuckDB local em ordem numérica | Após clonar o repo ou criar novo `finance.duckdb` |
| `check_db.py` | Abre o DuckDB, lista tabelas e conta linhas. Útil para diagnóstico | Quando suspeitar que o banco está corrompido ou vazio |

---

### `scripts/seed/` — Dados de Teste

| Arquivo | O que faz |
|---------|-----------|
| `seed_auth_user.py` | Cria usuário de teste com email/senha hasheada no banco |
| `seed_mock_data.py` | Popula o banco com transações mock realistas (6 meses de histórico) |
| `seed_rich_mock_account.py` | Cria conta mock com perfil "rico": múltiplas fontes de renda, investimentos, cartões premium |
| `seed_golden_user.py` | Cria o "golden user" de referência para testes de regressão |
| `fix_user.py` | Corrige dados de usuário corrompidos (email duplicado, senha não hasheada) |

**Fluxo típico de setup local:**
```bash
python scripts/db/apply_migrations.py
python scripts/seed/seed_auth_user.py
python scripts/seed/seed_mock_data.py
```

---

### `scripts/ml/` — Machine Learning

| Arquivo | O que faz |
|---------|-----------|
| `create_labeled_dataset.py` | Gera dataset de treinamento a partir das transações do banco com labels manuais |
| `train_pf_pj_classifier.py` | Treina o CatBoost PF/PJ classifier e salva `.pkl` em `models/` |
| `validate_pf_pj_classifier.py` | Carrega o modelo salvo e avalia métricas (F1-score, matriz de confusão, precisão por classe) |
| `pf_pj_fallback_rules.py` | Define as regras heurísticas de fallback quando o modelo ML tem baixa confiança |

---

### `scripts/debug/` — Debug e Exploração

Scripts temporários e de diagnóstico. **Não usar em produção.**

| Arquivo | O que faz |
|---------|-----------|
| `verify_imports.py` | Testa todos os imports do projeto para detectar dependências faltando |
| `debug_validation.py` | Roda validação Pydantic com dados de teste para debugar schemas |
| `debug_pluggy_validation.py` | Testa a integração Pluggy: autenticação, fetch de contas, normalização |
| `test_api.py` | Faz chamadas HTTP para os endpoints locais e imprime respostas |
| `test_new_mock.py` | Testa novos dados mock antes de commitar |
| `test_manual_override.py` | Testa o fluxo de override manual de classificação PF/PJ |
| `exploration_script.py` | Script livre para exploração de dados no DuckDB |
| `streamlit_agent_test_advanced.py` | Interface Streamlit avançada para testar o agente conversacional com múltiplos cenários |

---

## tests/ — Suite de Testes

Todos os testes rodam com `pytest` a partir da raiz do projeto:
```bash
cd /path/to/projeto
pytest                        # Roda todos os testes configurados
pytest backend/tests/forecast # Roda apenas testes do forecast
pytest -k "test_classifier"   # Filtra por nome
pytest --tb=short             # Traceback curto (padrão pelo pytest.ini)
```

**Configuração:** `pytest.ini` na raiz define `testpaths = backend/tests`. O diretório `backend/tests/architect/` é ignorado por padrão (testes lentos — executar explicitamente quando necessário).

---

### `tests/conftest.py`
Fixtures compartilhadas por todos os testes:
- `db_session`: sessão DuckDB apontando para `tests/data/transactions.duckdb`
- `mock_user`: usuário de teste pré-criado
- `sample_transactions`: lista de transações de teste
- `mock_pluggy_client`: instância de `PluggyMockClient`

---

### `tests/fixtures/mocks/`

| Arquivo | Conteúdo |
|---------|----------|
| `factory.py` | Factory functions: `make_transaction()`, `make_user()`, `make_pluggy_item()` com valores padrão customizáveis |
| `itau.py` | Transações mock no formato bruto do Itaú (para testar o Ingestor) |
| `nubank.py` | Transações mock no formato bruto do Nubank |
| `bb.py` | Transações mock no formato bruto do Banco do Brasil |

---

### `tests/data/`

| Arquivo | Conteúdo |
|---------|----------|
| `transactions.duckdb` | Banco DuckDB de teste (780 KB). Contém dados de seed para os testes de integração. **Commitado no git** (excepcionalmente, pois é um fixture pequeno) |

---

### Testes Principais (raiz de `tests/`)

| Arquivo | O que testa |
|---------|------------|
| `test_etl_ingestor.py` | Ingestor ETL: normalização de formatos Itaú, Nubank, BB; campos obrigatórios; encoding |
| `test_classifier.py` | Classificador de categorias: acurácia por categoria, fallback por regras |
| `test_recurring_detector.py` | Detector de recorrência: detecção de assinaturas mensais, variação de ±5%, periodicidade |
| `test_subscription_detector.py` | Detector de assinaturas: serviços de streaming, assinaturas SaaS |
| `test_safe_to_spend.py` | Calculadora safe-to-spend: cenários de saldo crítico, despesas fixas altas |
| `test_cashflow_projection.py` | Projeção de cashflow: 30 dias, sazonalidade, receitas variáveis |
| `test_goal_tracker.py` | Tracker de metas: progresso, prazo estimado, metas atingidas |
| `test_health_score.py` | Score de saúde: cálculo por dimensão, histórico, variação |
| `test_shadow_pipeline.py` | Pipeline de shadow invoices: assinaturas + parcelamentos + cashflow |
| `test_runner.py` | ETL runner: execução end-to-end do pipeline completo |
| `test_endpoints_smoke.py` | Smoke tests de todos os endpoints: status 200/422/401 |
| `test_pluggy_integration.py` | Integração Pluggy (mock): autenticação, fetch, normalização |
| `test_e2e_full_pipeline.py` | E2E completo: Pluggy → ETL → cashflow → forecast |
| `test_f4_complete.py` | F4 (divider) completo: PF/PJ classification, overrides, subcategorias |
| `test_schemas_complete.py` | Validação de schemas Pydantic: campos obrigatórios, tipos, enums |
| `test_ultimate_etl_and_schemas.py` | Integração ETL + schemas: pipeline completo com validação de output |

---

### `tests/optimizer/` — Testes do F2

| Arquivo | Foco |
|---------|------|
| `test_api.py` | Endpoint `/optimizer/analyze` |
| `test_card_loader.py` | Carregamento da base de cartões |
| `test_profiler.py` | Análise de perfil de gasto por categoria |
| `test_ranking.py` | Algoritmo de ranking de cartões |
| `test_simulator.py` | Simulação de ROI |
| `test_roi.py` | Cálculos de retorno de milhas e cashback |
| `test_m2_5_category_cashback.py` | Cashback por categoria: alimentação, farmácia, postos |
| `test_m2_6_promotions.py` | Promoções de transferência de pontos |
| `test_optimizer_service.py` | Orquestrador do serviço |
| `test_input_validator.py` | Validação de entrada |
| `test_liquidity_checker.py` | Verificação de liquidez (anuidades vs orçamento) |

---

### `tests/architect/` — Testes do F3

Executar explicitamente: `pytest backend/tests/architect/`

| Arquivo | Foco |
|---------|------|
| `test_financing.py` | Calculadora de financiamento (Price/SAC) |
| `test_consortium.py` | Calculadora de consórcio |
| `test_investment.py` | Calculadora de investimento/poupança |
| `test_npv.py` | VPL e TIR |
| `test_strategy_engine.py` | Comparação das 3 estratégias |
| `test_monte_carlo.py` | Simulação Monte Carlo (10k cenários) |
| `test_sensitivity.py` | Análise de sensibilidade |
| `test_validators.py` | Validação de input de simulação |
| `test_connectors.py` | Conectores de dados de mercado |
| `test_m3_1_ipca.py` | Integração IPCA nos cálculos |
| `test_m3_4_timing.py` | Análise de timing ("quando comprar?") |
| `test_f3_completo.py` | F3 completo end-to-end |
| `test_integration.py` | Integração entre módulos F3 |
| `test_db.py` | Persistência de simulações |
| `test_api.py` / `test_service.py` | API e serviço |

---

### `tests/agent/`

| Arquivo | Foco |
|---------|------|
| `test_agent_tools_real.py` | Testa cada uma das 13 ferramentas do agente com dados reais |

### `tests/cashflow/`

| Arquivo | Foco |
|---------|------|
| `test_m1_3_budget.py` | Análise de orçamento 50/30/20 |

### `tests/notifications/`

| Arquivo | Foco |
|---------|------|
| `test_mx3_notifier.py` | Sistema de notificações: geração, entrega, preferências |

---

## Padrões Arquiteturais

### Strategy Pattern — Bank Strategies
`app/forecast/etl/bank_strategy/`: cada banco tem sua própria classe de normalização, registrada num `Registry`. O `Ingestor` recebe o `bank_id` e usa a estratégia correta automaticamente.

### Repository Pattern — DB Queries
`app/core/db/`: toda query ao banco passa por funções neste módulo. Os módulos de negócio (forecast, optimizer, etc.) nunca escrevem SQL diretamente.

### Multi-layer Fallback — Classificação
`app/forecast/etl/classifier.py` e `app/divider/classifier.py`:
1. Override manual (prioridade máxima)
2. Modelo ML (CatBoost)
3. Regras heurísticas (fallback)
4. Default (se tudo falhar)

### Plugin Pattern — Agent Tools
`app/agent/tools/`: cada ferramenta é um módulo independente com decorator `@tool`. Adicionar uma nova ferramenta é criar um novo arquivo e registrá-lo em `graph.py`.

### Dual Database — DuckDB vs PostgreSQL
- **DuckDB** (`finance.duckdb`): desenvolvimento local, sem servidor, migrations manuais
- **PostgreSQL**: produção via Docker Compose, migrations via Alembic

---

## Fluxo de Dados Principal

```
[Pluggy API / Mock]
        ↓
[app/adapters/bank_adapter.py]       ← Abstrai a fonte de dados
        ↓
[app/forecast/etl/runner.py]         ← Orquestra 8 etapas
    ├── [ingestor.py]                 ← Normaliza por banco (Strategy)
    ├── [classifier.py]              ← Categoriza (ML + fallback)
    ├── [recurring_detector.py]      ← Detecta recorrências
    ├── [divider/classifier.py]      ← Classifica PF/PJ
    ├── [subscriptions/runner.py]    ← Detecta shadow invoices
    ├── [data_quality.py]            ← Valida qualidade
    ├── [income_profiler.py]         ← Perfil de renda
    └── [loader.py]                  ← Persiste no DuckDB/PostgreSQL
        ↓
[app/forecast/cashflow/]             ← Projeta 30 dias
    ├── [projector.py]               ← Saldos diários
    ├── [burn_rate.py]               ← Taxa de queima
    └── [safe_to_spend.py]           ← Margem segura
        ↓
[GET /forecast/{user_id}]            ← ForecastResponse final
        ↓
[app/agent/graph.py]                 ← Agente ReAct interpreta resultado
        ↓
[Cliente / Frontend]
```
