"""
caminho.py — Mapa completo do fluxo de dados do backend Nexa

Mostra: quais arquivos chamam quais, o que cada um faz,
e quais arquivos existem mas não estão conectados a nada.

Índice:
    1. PONTO DE ENTRADA
    2. FLUXO PRINCIPAL  (dados brutos → ETL → Cálculos → API)
       2.1  Etapa 1 — Ingestão de dados (Pluggy)
       2.2  Etapa 2 — Validação (Pydantic)
       2.3  Etapa 3 — Pipeline ETL
       2.4  Etapa 4 — Cálculos financeiros (cashflow)
       2.5  Etapa 5 — Serialização (schemas)
       2.6  Etapa 6 — Rotas da API
    3. MÓDULO F3: NEXA ARCHITECT
    4. MÓDULO AGENT (LangGraph) — DESABILITADO
    5. MÓDULOS DE SUPORTE
    6. ARQUIVOS FORA DO FLUXO (não importados por ninguém)
    7. DIAGRAMA TEXTUAL DE DEPENDÊNCIAS

═══════════════════════════════════════════════════════════════════════════════
1. PONTO DE ENTRADA
═══════════════════════════════════════════════════════════════════════════════

app/main.py
    O que faz  : Cria o app FastAPI, registra os routers.
    Chama      : app/api/v1/router.py            → todas as rotas /api/v1/*
                 app/api/v1/routes/dashboard.py  → GET /dashboard
    Chamado por: uvicorn (processo externo) — não é importado pelo código.

app/runner.py  (NexaRunner)
    O que faz  : Orquestrador completo do pipeline financeiro.
                 Pluggy → Validação → ETL → Shadow Invoice → Cashflow → Safe-to-Spend
    Chama      : app/integrations/open_finance/pluggy.py
                 app/integrations/open_finance/pluggy_mock.py
                 app/schemas/transaction.py   (TransactionBatchResult)
                 app/etl/__init__.py           (todos os estágios)
                 app/cashflow/projector.py
                 app/cashflow/safe_to_spend.py
    Chamado por: app/api/v1/routes/forecast.py
                 tests/test_runner.py
                 tests/test_pipeline_integration.py

═══════════════════════════════════════════════════════════════════════════════
2. FLUXO PRINCIPAL
═══════════════════════════════════════════════════════════════════════════════

───────────────────────────────────────────────────────────────────────────────
2.1  ETAPA 1 — INGESTÃO DE DADOS  (app/integrations/open_finance/)
───────────────────────────────────────────────────────────────────────────────

pluggy.py  (PluggyClient)
    O que faz  : Cliente HTTP para a API real do Pluggy.
                 Busca transações, gera URL de reconexão, etc.
    Chama      : app/core/config.py  (settings — credenciais)
    Chamado por: app/runner.py
                 app/api/v1/routes/reconnect.py

pluggy_mock.py  (MockPluggyClient)
    O que faz  : Substituto do PluggyClient com dados fixos para dev/testes.
                 Gera transações realistas sem chamada à API.
    Chama      : (nada internamente)
    Chamado por: app/runner.py
                 tests/*

───────────────────────────────────────────────────────────────────────────────
2.2  ETAPA 2 — VALIDAÇÃO  (app/schemas/transaction.py)
───────────────────────────────────────────────────────────────────────────────

transaction.py  (TransactionWebhook, TransactionBatchResult)
    O que faz  : Valida estrutura das transações vindas do Pluggy.
                 Separa válidas de rejeitadas (tolerante a erros).
    Chama      : app/schemas/enums.py
    Chamado por: app/runner.py
                 app/etl/ingestor.py
                 app/api/v1/routes/transactions.py
                 tests/*

───────────────────────────────────────────────────────────────────────────────
2.3  ETAPA 3 — PIPELINE ETL  (app/etl/)
───────────────────────────────────────────────────────────────────────────────

__init__.py
    O que faz  : Exporta a API pública do módulo ETL.
                 Re-exporta: TransactionIngestor, TransactionClassifier,
                 RecurringDetector, run_shadow_invoice_detection, PFPJClassifier,
                 DataQualityValidator, UserProfileAnalyzer, get_bank_strategy.
    Chama      : todos os submódulos listados abaixo
    Chamado por: app/runner.py
                 app/api/v1/routes/transactions.py
                 app/api/v1/routes/forecast.py

── Passo 3.1 ──────────────────────────────────────────────────────────────────

ingestor.py  (TransactionIngestor)
    O que faz  : Normaliza campos, deduplica e persiste no DuckDB.
                 Retorna Polars DataFrame com transações limpas.
    Chama      : app/etl/bank_strategy/registry.py  (get_bank_strategy)
                 app/schemas/transaction.py
    Chamado por: app/etl/__init__.py → app/runner.py
                 app/api/v1/routes/transactions.py
                 tests/test_etl_ingestor.py

    bank_strategy/  (estratégias por banco)
        base.py         → BankStrategy  (classe abstrata)
        registry.py     → factory: get_bank_strategy(bank_name)
        strategies/
            default.py  → Estratégia padrão (fallback)
            nubank.py   → Nubank
            itau.py     → Itaú
            inter.py    → Inter
        Chamado por: ingestor.py

    dedup/  (políticas de deduplicação)
        base.py         → DedupPolicy  (abstrata)
        default.py      → DefaultDedupPolicy
        Chamado por: ingestor.py

── Passo 3.2 ──────────────────────────────────────────────────────────────────

classifier.py  (TransactionClassifier)
    O que faz  : Classifica cada transação em 1 de 10 categorias
                 usando regras determinísticas (RULES mode).
                 Adiciona coluna `category` no DataFrame.
    Chama      : (nada internamente)
    Chamado por: app/etl/__init__.py → app/runner.py
                 app/api/v1/routes/transactions.py
                 tests/test_classifier.py

── Passo 3.3 ──────────────────────────────────────────────────────────────────

pf_pj_classifier.py  (PFPJClassifier, PFPJFallbackClassifier)
    O que faz  : Classifica transações como Pessoa Física (PF) ou
                 Pessoa Jurídica (PJ) usando modelo ML (Random Forest)
                 com fallback em regras determinísticas.
                 Adiciona coluna `pf_pj_label`  (PF / PJ / UNCERTAIN).
    Chama      : models/pf_pj_classifier.pkl   (sklearn via joblib)
                 models/feature_encoders.pkl
                 models/feature_scaler.pkl
    Chamado por: app/etl/__init__.py → app/runner.py
                 app/etl/runner.py
                 tests/test_f4_complete.py

── Passo 3.4 ──────────────────────────────────────────────────────────────────

recurring_detector.py  (RecurringDetector)
    O que faz  : Detecta padrões recorrentes: assinaturas e parcelamentos.
    Chama      : app/etl/shadow_invoices/subscription_detector.py
                 app/etl/shadow_invoices/installment_detector.py
    Chamado por: app/etl/__init__.py → app/runner.py
                 app/api/v1/routes/forecast.py
                 tests/test_recurring_detector.py

── Passo 3.5 ──────────────────────────────────────────────────────────────────

shadow_invoices/runner.py  (run_shadow_invoice_detection)
    O que faz  : Detecta obrigações futuras (shadow invoices): quanto o
                 usuário vai gastar nos próximos meses com assinaturas e parcelas.
    Chama      : shadow_invoices/subscription_detector.py
                 shadow_invoices/installment_detector.py
                 shadow_invoices/base.py
    Chamado por: app/etl/__init__.py → app/runner.py
                 app/etl/runner.py
                 app/api/v1/routes/shadow_invoice.py
                 tests/test_shadow_invoice.py
                 tests/test_shadow_pipeline.py

shadow_invoices/subscription_detector.py  (SubscriptionDetector)
    O que faz  : Identifica assinaturas recorrentes (Netflix, Spotify, etc.)
    Chamado por: recurring_detector.py
                 shadow_invoices/runner.py

shadow_invoices/installment_detector.py  (InstallmentDetector)
    O que faz  : Identifica parcelas de compras (ex: 3/12, 4/12)
    Chamado por: recurring_detector.py
                 shadow_invoices/runner.py

── Passo 3.6 — Suporte ────────────────────────────────────────────────────────

profiles.py  (UserProfileAnalyzer)
    O que faz  : Analisa perfil financeiro do usuário:
                 CONSERVATIVE / BALANCED / SPENDER + health score.
    Chama      : (nada internamente)
    Chamado por: app/etl/__init__.py
                 app/api/v1/routes/forecast.py

data_quality.py  (DataQualityValidator)
    O que faz  : Valida qualidade global dos dados processados.
    Chama      : (nada internamente)
    Chamado por: app/etl/__init__.py

runner.py  (run_etl_pipeline)
    O que faz  : Pipeline ETL alternativo com 8 passos completos (inclui F4).
                 Usado diretamente em testes e scripts.
    Chama      : app/etl/shadow_invoices/runner.py
                 app/etl/pf_pj_classifier.py
                 app/db/queries.py  (save_transactions_clean)
    Chamado por: tests/test_f4_complete.py

───────────────────────────────────────────────────────────────────────────────
2.4  ETAPA 4 — CÁLCULOS FINANCEIROS  (app/cashflow/)
───────────────────────────────────────────────────────────────────────────────

__init__.py
    Exporta: CashflowProjector, SafeToSpendCalculator, CashflowEngine,
             ProjectionSummary, SafeToSpendResult.
    Chamado por: app/runner.py
                 app/api/v1/routes/forecast.py

projector.py  (CashflowProjector)
    O que faz  : Projeta saldo diário para os próximos N dias.
                 Leva em conta transações históricas + shadow invoices.
                 Retorna Polars DataFrame com projeção dia-a-dia.
    Chama      : (nada internamente)
    Chamado por: app/cashflow/engine.py
                 app/runner.py
                 app/agent/nodes/forecast.py
                 tests/test_cashflow_projection.py

safe_to_spend.py  (SafeToSpendCalculator)
    O que faz  : Calcula quanto o usuário pode gastar hoje com segurança.
                 Gera SafeToSpendResult com score de risco.
    Chama      : (nada internamente)
    Chamado por: app/cashflow/engine.py
                 app/runner.py
                 app/agent/nodes/forecast.py
                 tests/test_safe_to_spend.py

engine.py  (CashflowEngine)
    O que faz  : Orquestra projector + safe_to_spend em uma chamada só.
    Chama      : app/cashflow/projector.py
                 app/cashflow/safe_to_spend.py
    Chamado por: app/cashflow/__init__.py
                 app/api/v1/routes/forecast.py

───────────────────────────────────────────────────────────────────────────────
2.5  ETAPA 5 — SERIALIZAÇÃO  (app/schemas/)
───────────────────────────────────────────────────────────────────────────────

__init__.py
    Exporta todos os modelos Pydantic de resposta da API.

forecast.py  (ForecastResponse, build_forecast_response)
    Chama      : app/schemas/cashflow.py
                 app/schemas/safe_to_spend.py
                 app/schemas/shadow_invoice.py

cashflow.py        → CashflowProjectionResponse, CashflowSummaryResponse, etc.
safe_to_spend.py   → SafeToSpendResponse, SafeToSpendDetailedResponse
shadow_invoice.py  → ShadowInvoiceResponse, ShadowInvoiceListResponse
enums.py           → CategoryType, TransactionType, BankTier, etc.
chat.py            → modelos de chat  (ver seção 6 — fora do fluxo)

    Todos chamados por: rotas correspondentes, runner.py, tests.

───────────────────────────────────────────────────────────────────────────────
2.6  ETAPA 6 — ROTAS DA API  (app/api/v1/routes/)
───────────────────────────────────────────────────────────────────────────────

router.py
    O que faz  : Registra todos os routers ativos.
    Chama      : routes/bank_simulation, transactions, forecast,
                 shadow_invoice, alerts, reconnect, context_override, architect
    Chamado por: app/main.py

transactions.py       POST /transactions/webhook
    Chama      : app/schemas/transaction.py
                 app/etl  (TransactionIngestor, TransactionClassifier)

forecast.py           GET  /forecast/{user_id}
    Chama      : app/runner.py  (NexaRunner)
                 app/etl  (múltiplos módulos)
                 app/cashflow  (CashflowEngine)
                 app/schemas/forecast.py
                 app/schemas/safe_to_spend.py
                 app/schemas/shadow_invoice.py
                 app/etl/profiles.py

shadow_invoice.py     GET  /shadow_invoice/{user_id}
                      GET  /shadow_invoice/{user_id}/summary
    Chama      : app/etl  (shadow detection)
                 app/schemas/shadow_invoice.py

safe_to_spend.py      GET  /safe_to_spend/{user_id}
    Chama      : app/cashflow  (SafeToSpendCalculator)
                 app/schemas/safe_to_spend.py

alerts.py             GET  /alerts/{user_id}
    Chama      : (lógica interna de alertas)

reconnect.py          POST /reconnect/{user_id}
    Chama      : app/integrations/open_finance/pluggy.py
                 app/core/config.py

context_override.py   POST /context/override   (F4 — Nexa Divider)
    Chama      : app/db/queries.py
                 (save_context_override, get_context_overrides, get_override_stats)

architect.py          POST /architect/simulate        (F3 — Nexa Architect)
                      GET  /architect/simulations
                      GET  /architect/simulations/{id}
                      GET  /architect/metrics
    Chama      : app/architect/models.py
                 app/architect/services/architect_service.py
                 app/architect/simulators/sensitivity_analyzer.py
                 app/db/queries/architect_queries.py

dashboard.py          GET  /dashboard
    Chama      : app/domain/finance_engine.py  (FinanceEngine)

bank_simulation.py    (rotas de dev/teste — simulação de banco)

═══════════════════════════════════════════════════════════════════════════════
3. MÓDULO F3: NEXA ARCHITECT  (app/architect/)
═══════════════════════════════════════════════════════════════════════════════

services/architect_service.py  (ArchitectService)
    O que faz  : Orquestra a simulação financeira completa (F3).
                 Busca taxas → valida input → roda estratégias
                 → analisa sensibilidade → persiste resultado.
    Chama      : app/architect/connectors/*
                 app/architect/models.py
                 app/architect/simulators/strategy_engine.py
                 app/architect/validators/*
    Chamado por: app/api/v1/routes/architect.py

connectors/
    base.py          → BaseConnector  (classe abstrata)
    bacen.py         → BacenConnector      — taxa SELIC  (API BACEN / fallback)
    anbima.py        → AnbimaConnector     — CDI         (ANBIMA / fallback)
    market_rates.py  → MarketRatesConnector — CET de financiamento por tipo de bem
    abac.py          → AbacConnector       — estatísticas de consórcio  (ABAC)
    Todos chamados por: architect_service.py

simulators/
    strategy_engine.py      → StrategyEngine: executa 3 estratégias
                               (financiamento / investimento / consórcio)
        Chama: architect/calculators/*
               architect/simulators/monte_carlo.py
               architect/utils/formatters.py
    sensitivity_analyzer.py → SensitivityAnalyzer: análise de sensibilidade
        Chamado por: routes/architect.py
    monte_carlo.py          → MonteCarloSimulator: simulação estocástica de risco
        Chamado por: strategy_engine.py

calculators/
    financing.py    → cálculos de financiamento  (PMT, amortização)
    investment.py   → retorno de investimento     (taxa composta, FV)
    npv.py          → VPL, TIR, VP de anuidade, FV de anuidade
    consortium.py   → métricas de consórcio       (parcela, taxa adm, contemplação)
    Todos chamados por: strategy_engine.py

validators/
    input_validator.py     → InputValidator: valida SimulationRequest
    liquidity_validator.py → LiquidityValidator: verifica liquidez
    Chamados por: architect_service.py

utils/
    formatters.py   → formata moeda e percentual
    date_helpers.py → cálculos de data
    cache.py        → rate limiting / cache de taxas de mercado
    Chamados por: calculators, validators

models.py  (SimulationRequest, SimulationResponse, etc.)
    Chamado por: architect_service, strategy_engine, validators, routes, tests

app/db/queries/architect_queries.py
    O que faz  : Salva e busca simulações no DuckDB  (F3).
    Chamado por: app/api/v1/routes/architect.py
                 tests/architect/test_db.py

═══════════════════════════════════════════════════════════════════════════════
4. MÓDULO AGENT (LangGraph) — DESABILITADO
═══════════════════════════════════════════════════════════════════════════════

app/agent/graph.py
    O que faz  : Constrói o grafo LangGraph do agente financeiro.
    Chama      : app/agent/state.py
                 app/agent/nodes/recurrence.py  → app/core/recurrence.py
                 app/agent/nodes/forecast.py    → app/cashflow/*
                 app/agent/nodes/explain.py     → app/core/explain.py
    Chamado por: routes/analyze.py  ← DESABILITADO (import comentado no router)

app/api/v1/routes/analyze.py
    NOTA: arquivo existe mas NÃO está registrado em router.py (TODO comentado).
          Reativar quando as dependências LangGraph forem resolvidas.

═══════════════════════════════════════════════════════════════════════════════
5. MÓDULOS DE SUPORTE
═══════════════════════════════════════════════════════════════════════════════

app/core/config.py  (Settings / settings)
    O que faz  : Configurações da aplicação via variáveis de ambiente.
    Chamado por: app/integrations/open_finance/pluggy.py
                 app/api/v1/routes/reconnect.py

app/core/recurrence.py  (detect_recurring)
    Chamado por: app/agent/nodes/recurrence.py

app/core/explain.py  (explain_safe_to_spend)
    Chamado por: app/agent/nodes/explain.py

app/core/logging.py
    Configuração de logs estruturados (structlog).
    Chamado por: uso pontual nos módulos

app/db/queries.py  (funções DuckDB)
    Funções disponíveis via app/db/queries/__init__.py:
        get_connection, get_context_overrides, save_context_override,
        get_override_stats, save_transactions_clean
    Chamado por: app/etl/runner.py
                 app/api/v1/routes/context_override.py

app/db/queries/__init__.py
    O que faz  : Re-exporta as funções de queries.py para compatibilidade
                 retroativa (queries.py existe como arquivo E como pacote).

app/domain/finance_engine.py  (FinanceEngine)
    O que faz  : Calcula health score e métricas financeiras gerais.
    Chamado por: app/api/v1/routes/dashboard.py

app/storage/raw_events.py
    O que faz  : Persiste webhooks brutos do Pluggy para auditoria.
    Chamado por: app/api/v1/routes/transactions.py  (uso pontual)

app/adapters/bank_adapter.py
    O que faz  : Converte dados de simulação para formato TransactionWebhook.
    Chama      : app/schemas/transaction.py
    Chamado por: uso interno em testes/scripts — pouco utilizado

═══════════════════════════════════════════════════════════════════════════════
6. ARQUIVOS FORA DO FLUXO  (existem no projeto mas não são importados)
═══════════════════════════════════════════════════════════════════════════════

Podem ser código de funcionalidades planejadas, experimentos ou legado.

  ARQUIVO                                    SITUAÇÃO
  ─────────────────────────────────────────  ──────────────────────────────────
  app/services/finance_engine_service.py     QUEBRADO — importa
                                             app.core_engine.* que não existe.
                                             Não importado por ninguém.

  app/engines/calculator.py                  DESCONECTADO — nenhum módulo ativo
  app/engines/reconciler.py                  importa estes arquivos.
  app/engines/shadow_invoice.py              Possivelmente código antigo
                                             substituído por app/cashflow/ e
                                             app/etl/shadow_invoices/.

  app/ml/models/catboost_classifier.py       DESCONECTADO — modelo ML não
  app/ml/models/neuralprophet_forecaster.py  utilizado pelo pipeline ativo.
                                             O PF/PJ usa sklearn (joblib).

  app/insights/engine.py                     DESCONECTADO — não importado.
                                             Possivelmente feature futura.

  app/api/v1/routes/analyze.py               DESABILITADO — arquivo existe,
                                             mas o import está comentado em
                                             router.py (TODO).
                                             Depende do agent/ (LangGraph).

  app/api/v1/routes/chat.py                  DESABILITADO — arquivo existe,
                                             mas não está no router.py.

  app/db/session.py                          POSSIVELMENTE INATIVO —
  app/db/models.py                           projeto usa DuckDB direto.
                                             SQLAlchemy parece não estar em uso
                                             no fluxo principal.

  app/core/security.py                       POSSIVELMENTE INATIVO —
  app/core/shadow_invoices.py                não aparecem em nenhum import
                                             rastreado.

═══════════════════════════════════════════════════════════════════════════════
7. DIAGRAMA TEXTUAL DE DEPENDÊNCIAS
═══════════════════════════════════════════════════════════════════════════════

  PLUGGY  (API externa)
       │
       ▼
  integrations/pluggy.py ──── integrations/pluggy_mock.py  (dev)
       │
       ▼
  schemas/transaction.py       validação Pydantic (TransactionBatchResult)
       │
       ▼
  etl/ingestor.py ─────────── etl/bank_strategy/  (Nubank, Itaú, Inter, Default)
       │                       etl/dedup/
       ▼
  etl/classifier.py            10 categorias por regras
       │
       ▼
  etl/pf_pj_classifier.py      ML + fallback → PF / PJ / UNCERTAIN
       │
       ▼
  etl/recurring_detector.py
       ├── etl/shadow_invoices/subscription_detector.py
       └── etl/shadow_invoices/installment_detector.py
                    │
                    ▼
  etl/shadow_invoices/runner.py    obrigações futuras detectadas
       │
       ▼
  cashflow/projector.py        saldo projetado dia-a-dia (30 dias)
       │
  cashflow/safe_to_spend.py    quanto pode gastar hoje com segurança
       │
  cashflow/engine.py           orquestra projector + safe_to_spend
       │
       ▼
  schemas/forecast.py  ┐
  schemas/cashflow.py  ├─ Serialização Pydantic
  schemas/shadow.py    ┘
       │
       ▼
  ┌──────────────────────────────────────────────┐
  │  API   (app/api/v1/routes/)                  │
  │                                              │
  │  GET  /forecast/{user_id}                    │
  │  GET  /shadow_invoice/{user_id}              │
  │  GET  /shadow_invoice/{user_id}/summary      │
  │  GET  /safe_to_spend/{user_id}               │
  │  GET  /alerts/{user_id}                      │
  │  POST /transactions/webhook                  │
  │  POST /reconnect/{user_id}                   │
  │  POST /context/override           (F4)       │
  │  POST /architect/simulate         (F3)       │
  │  GET  /architect/simulations      (F3)       │
  │  GET  /architect/metrics          (F3)       │
  │  GET  /dashboard                             │
  └──────────────────────────────────────────────┘

  Fluxo F3 (Nexa Architect) — separado do pipeline principal:

  routes/architect.py
       ├── architect/services/architect_service.py
       │       ├── architect/connectors/  (BACEN, ANBIMA, MarketRates, ABAC)
       │       ├── architect/simulators/strategy_engine.py
       │       │       ├── architect/calculators/  (financing, investment, npv, consortium)
       │       │       └── architect/simulators/monte_carlo.py
       │       └── architect/validators/  (input, liquidity)
       └── db/queries/architect_queries.py   (DuckDB — salva/busca simulações)

  Fluxo Agent/LangGraph — DESABILITADO:

  routes/analyze.py  ← import comentado no router.py  (TODO)
       └── agent/graph.py
               ├── agent/nodes/forecast.py    → cashflow/*
               ├── agent/nodes/recurrence.py  → core/recurrence.py
               └── agent/nodes/explain.py     → core/explain.py
"""
