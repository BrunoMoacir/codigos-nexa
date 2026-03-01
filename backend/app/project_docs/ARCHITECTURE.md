# Nexa Backend — Documentação de Arquitetura

> Gerado automaticamente em 2026-02-23

---

## Visão Geral

O Nexa é um sistema de **inteligência financeira pessoal** baseado em dados bancários reais via Open Finance (Pluggy). Ele ingere transações, classifica, detecta padrões e projeta o futuro financeiro do usuário com explicabilidade total.

**Princípio central:** nenhum número financeiro é exibido sem um evento que o justifique.

---

## Stack Tecnológica

| Camada | Tecnologia |
|--------|-----------|
| API | FastAPI 0.128.0 + Uvicorn |
| DataFrames | Polars (produção), Pandas (legado core/) |
| Banco de dados | DuckDB (local, `finance.duckdb`) |
| Validação | Pydantic v2 |
| ML / Classificação | Scikit-learn — Random Forest (pf_pj) |
| Open Finance | Pluggy API + MockPluggyClient |
| Testes | pytest + pytest-asyncio (414 testes) |

---

## Estrutura de Arquivos

```
backend/
├── app/
│   ├── main.py                           # Entrada FastAPI, registro de routers
│   ├── runner.py                         # NexaRunner — orquestrador principal
│   │
│   ├── api/v1/
│   │   ├── router.py                     # Registro central de todas as rotas
│   │   └── routes/
│   │       ├── transactions.py           # POST /transactions/webhook
│   │       ├── forecast.py               # GET /forecast/{user_id}
│   │       ├── shadow_invoice.py         # GET /shadow_invoice/{user_id}
│   │       ├── alerts.py                 # GET /alerts/{user_id}
│   │       ├── reconnect.py              # POST /reconnect/{user_id}
│   │       ├── context_override.py       # POST /context/override  (F4)
│   │       ├── architect.py              # POST /architect/simulate (F3)
│   │       ├── bank_simulation.py        # GET /banks/simulate/{bank} (dev)
│   │       └── dashboard.py             # GET /dashboard/summary
│   │
│   ├── core/
│   │   ├── config.py                     # Settings (env vars via Pydantic)
│   │   ├── recurrence.py                 # detect_recurring() + RecurringDetector
│   │   └── shadow_invoices.py            # detect_shadow_invoices() + ShadowInvoiceDetector (legado)
│   │
│   ├── domain/
│   │   └── finance_engine.py             # FinanceEngine: health_score, savings_rate
│   │
│   ├── cashflow/
│   │   ├── projector.py                  # CashflowProjector — simulação dia a dia
│   │   ├── safe_to_spend.py              # SafeToSpendCalculator — margem segura
│   │   └── engine.py                     # CashflowEngine — orquestra projector + calc
│   │
│   ├── etl/
│   │   ├── runner.py                     # Pipeline de 8 passos
│   │   ├── ingestor.py                   # Step 1: normalização de transações
│   │   ├── classifier.py                 # Step 2: categorização (CatBoost/regras)
│   │   ├── pf_pj_classifier.py           # Step 4: F4 — classificador PF/PJ
│   │   ├── data_quality.py               # Step 6: scoring de confiança (TODO)
│   │   ├── user_profile.py               # Step 7: análise de perfil (TODO)
│   │   └── shadow_invoices/              # Step 5: detecção de obrigações futuras
│   │       ├── runner.py                 # Orquestrador: subscription → installment
│   │       ├── base.py                   # Classe abstrata ShadowInvoiceDetector
│   │       ├── subscription_detector.py  # Detecta assinaturas recorrentes
│   │       └── installment_detector.py   # Detecta parcelamentos
│   │
│   ├── schemas/                          # Modelos Pydantic (request/response)
│   │   ├── transaction.py
│   │   ├── forecast.py
│   │   └── shadow_invoice.py
│   │
│   ├── db/
│   │   └── queries.py                    # DuckDB: get_connection, save, overrides
│   │
│   └── integrations/
│       └── open_finance/
│           ├── pluggy.py                 # PluggyClient (produção)
│           └── pluggy_mock.py            # MockPluggyClient (desenvolvimento)
│
├── tests/                                # 406 testes (pytest)
├── scripts/                              # Scripts auxiliares e debug
├── finance.duckdb                        # Banco de dados local DuckDB
└── requirements.txt
```

---

## Arquitetura — Diagrama de Fluxo

```
                        ┌─────────────────────┐
                        │   FastAPI (main.py)  │
                        └──────────┬──────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                     │
     ┌────────▼──────┐   ┌────────▼────────┐   ┌───────▼──────┐
     │  /health      │   │  API v1 Router  │   │  /dashboard  │
     │  /version     │   └────────┬────────┘   └──────────────┘
     └───────────────┘            │
                                  │
         ┌────────────────────────┼──────────────────────────┐
         │                        │                           │
  ┌──────▼──────┐        ┌───────▼────────┐        ┌────────▼────────┐
  │ /transactions│        │   /forecast    │        │ /shadow_invoice │
  │  (webhook)  │        │   /{user_id}   │        │   /{user_id}    │
  └──────┬──────┘        └───────┬────────┘        └────────┬────────┘
         │                       │                           │
         └────────────┬──────────┘                           │
                      │                                       │
             ┌────────▼──────────────────────────────────────▼──┐
             │               NexaRunner (runner.py)              │
             │  mode="dev" → MockPluggyClient                    │
             │  mode="prod" → PluggyClient                       │
             └────────────────────┬──────────────────────────────┘
                                  │
             ┌────────────────────▼──────────────────────┐
             │           ETL Pipeline (etl/runner.py)    │
             │                                           │
             │  Step 1: Ingestor          (TODO)        │
             │  Step 2: Classifier        (TODO)        │
             │  Step 3: RecurringDetector (TODO)        │
             │  Step 4: PFPJClassifier    [ATIVO]       │
             │  Step 5: ShadowInvoices    [ATIVO]       │
             │    ├─ SubscriptionDetector               │
             │    └─ InstallmentDetector                │
             │  Step 6: DataQuality       (TODO)        │
             │  Step 7: UserProfile       (TODO)        │
             │  Step 8: Save to DB        [ATIVO]       │
             └────────────────────┬──────────────────────┘
                                  │
             ┌────────────────────▼──────────────────────┐
             │           Financial Analysis              │
             │                                           │
             │  CashflowEngine                          │
             │    ├─ CashflowProjector                  │
             │    │    → projection_df (30 dias)        │
             │    └─ SafeToSpendCalculator              │
             │         → safe_to_spend_daily            │
             │                                           │
             │  FinanceEngine                           │
             │    → health_score, savings_rate           │
             └────────────────────┬──────────────────────┘
                                  │
             ┌────────────────────▼──────────────────────┐
             │         ForecastResponse (JSON)           │
             │   { cashflow, safe_to_spend,              │
             │     shadow_invoices, financial_health }   │
             └───────────────────────────────────────────┘
```

---

## Módulos Principais

### 1. NexaRunner (`app/runner.py`)

Orquestrador de ponta a ponta. Inicializa todos os componentes do pipeline e coordena a execução completa.

```
NexaRunner(mode="dev"|"prod")
  ├── pluggy          → MockPluggyClient ou PluggyClient
  ├── ingestor        → TransactionIngestor
  ├── classifier      → TransactionClassifier
  ├── pf_pj_classifier → PFPJClassifier (F4)
  ├── recurring_detector → RecurringDetector
  ├── cashflow_projector → CashflowProjector
  └── safe_calc       → SafeToSpendCalculator
```

---

### 2. ETL Pipeline (`app/etl/runner.py`)

8 passos de transformação. Cada passo é opcionalmente pulável via `skip_steps=["step_name"]`.

| Step | Nome | Status | Função |
|------|------|--------|--------|
| 1 | `ingest` | TODO | Normalização e padronização de campos |
| 2 | `classify` | TODO | Categorização automática (CatBoost) |
| 3 | `recurring` | TODO | Detecção de recorrência básica |
| 4 | `pf_pj` | **ATIVO** | Classificação Pessoa Física / Jurídica |
| 5 | `shadow` | **ATIVO** | Detecção de obrigações futuras |
| 6 | `quality` | TODO | Score de confiança dos dados |
| 7 | `profile` | TODO | Análise de perfil financeiro |
| 8 | `save_db` | **ATIVO** | Persistência em `transactions_clean` |

**Função principal:**
```python
run_etl_pipeline(
    transactions_df: pl.DataFrame,
    user_id: str,
    account_id: str = None,
    skip_steps: list[str] = None
) -> pl.DataFrame
```

**User Overrides:** Após o Step 4, `apply_user_overrides(df, user_id)` busca correções manuais de PF/PJ do banco e as aplica ao DataFrame (sobrescreve predição do modelo, confidence = 1.0).

---

### 3. Shadow Invoice Detection (`app/etl/shadow_invoices/`)

Sistema de detecção de **obrigações financeiras futuras** a partir do histórico de transações.

```
run_shadow_invoice_detection(df) → pl.DataFrame
  │
  ├── SubscriptionDetector.detect(df)
  │     Critérios: amount fixo (<10% variação), ≥3 meses, sem palavras-chave de exclusão
  │     Confidence: 0.9
  │     Exemplos: Netflix, Spotify, Adobe, Notion, iCloud
  │
  └── InstallmentDetector.detect(df)
        Critérios keyword: "parc", "parcela", "/12", "x ", ≥3 ocorrências, ≥2 meses
        Critérios padrão:  ≥4 ocorrências, ≥3 meses, <5% variação (fallback)
        Confidence: 0.9 (keyword) | 0.7 (padrão)
```

**Output schema:**
```
type           : "SUBSCRIPTION" | "INSTALLMENT"
amount         : float (negativo, é despesa)
next_due_date  : datetime (próxima ocorrência projetada)
metadata       : {description, occurrences}
confidence     : float (0.7–0.9)
```

---

### 4. CashflowProjector (`app/cashflow/projector.py`)

Simulação financeira **determinística e explicável**. Nenhum dado estatístico — apenas eventos reais detectados.

**Algoritmo:**
```
1. Saldo inicial = último balance da conta (ou current_balance explícito)
2. Calendário = [hoje+1, hoje+2, ..., hoje+N]
3. Indexar shadow_invoices por next_due_date → dict {date: [eventos]}
4. Para cada dia:
     balance[t+1] = balance[t] + sum(amounts dos eventos do dia)
5. risk_flag = "NEGATIVE_BALANCE" se balance < 0
```

**Retorno:** `pl.DataFrame` com colunas:
- `date` — data projetada
- `projected_balance` — saldo calculado
- `events` — lista de eventos causadores (rastreabilidade)
- `expenses` — soma financeira do dia
- `risk_flag` — flag de risco

---

### 5. SafeToSpendCalculator (`app/cashflow/safe_to_spend.py`)

Responde: **"quanto posso gastar hoje sem comprometer minhas obrigações futuras?"**

**Fórmula:**
```
buffer = MAX(total_obrigações × 15%, R$ 200,00)
safe_to_spend_total = min_projected_balance - buffer
safe_to_spend_daily = safe_to_spend_total / horizon_days
```

**Classificação de risco:**
| Condição | Nível |
|----------|-------|
| `safe_to_spend ≤ 0` ou saldo mínimo < 0 | CRITICAL |
| `safe_to_spend < 300` | HIGH |
| `safe_to_spend < 1000` | MEDIUM |
| `safe_to_spend ≥ 1000` | LOW |

---

### 6. FinanceEngine (`app/domain/finance_engine.py`)

Calcula métricas de saúde financeira.

```
calculate_summary(income, expenses) → {
    income, expenses, savings_rate, health_score
}

health_score (0–100):
  + 50 pts  se savings_rate ≥ 30%
  + 30 pts  se income > expenses
  + 20 pts  se expense_ratio < 50%
```

---

### 7. Banco de Dados (`app/db/queries.py`)

DuckDB local (`backend/finance.duckdb`). Todas conexões usam path absoluto calculado via `Path(__file__)`.

**Funções disponíveis:**

| Função | Descrição |
|--------|-----------|
| `get_connection()` | Retorna conexão DuckDB |
| `save_transactions_clean(df, user_id, account_id)` | Upsert das transações processadas |
| `get_context_overrides(user_id)` | Lista overrides PF/PJ do usuário |
| `save_context_override(...)` | Salva/atualiza override (transação atômica) |
| `get_override_stats(user_id)` | Contagem de overrides por context_type |

**Tabelas principais:**

```sql
transactions_clean (
    transaction_id           VARCHAR PRIMARY KEY,
    user_id                  VARCHAR,
    account_id               VARCHAR,
    description              VARCHAR,
    amount                   DOUBLE,
    date                     DATE,
    transaction_type         VARCHAR,
    category                 VARCHAR,
    is_recurring             BOOLEAN,
    is_installment           BOOLEAN,
    context_type             VARCHAR,    -- "PF" | "PJ"
    context_confidence       DOUBLE,
    context_override_by_user BOOLEAN,
    processed_at             TIMESTAMP
)

context_overrides (
    id                       VARCHAR PRIMARY KEY,
    transaction_id           VARCHAR,
    user_id                  VARCHAR,
    original_context         VARCHAR,
    corrected_context        VARCHAR,
    reason                   VARCHAR,
    created_at               TIMESTAMP
)
```

---

## Endpoints da API

### Core (Produção)

| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/api/v1/transactions/webhook` | Recebe batch de transações do Pluggy |
| `GET` | `/api/v1/transactions/{user_id}` | Busca transações (501 — não implementado) |
| `GET` | `/api/v1/forecast/{user_id}` | Previsão financeira consolidada |
| `GET` | `/api/v1/shadow_invoice/{user_id}` | Lista obrigações futuras detectadas |
| `GET` | `/api/v1/shadow_invoice/{user_id}/summary` | Resumo numérico das obrigações |
| `GET` | `/api/v1/alerts/{user_id}` | Alertas ativos do usuário |
| `POST` | `/api/v1/reconnect/{user_id}` | Gera URL de reconexão Pluggy |
| `POST` | `/api/v1/context/override` | Salva correção manual PF/PJ (F4) |
| `POST` | `/api/v1/architect/simulate` | Simulação financeira (F3) |

### Desenvolvimento / Utilidade

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/api/v1/banks/simulate/{bank}` | Simula dados de um banco (mock) |
| `GET` | `/dashboard/summary` | Resumo financeiro básico |
| `GET` | `/health` | Health check |
| `GET` | `/version` | Versão da API |
| `GET` | `/docs` | Swagger UI (automático) |

---

## Fluxo Completo — Webhook → Forecast

```
1. INGESTÃO
   POST /api/v1/transactions/webhook
   Body: { connector: {id: "201"}, results: [...transações...] }
         ↓
   Validação Pydantic (TransactionBatchResult)
   → conta valid/rejected, calcula rejection_rate
   → aciona alerta se rate > threshold

2. ETL PIPELINE
   run_etl_pipeline(df, user_id, account_id)
         ↓
   Step 4: PFPJClassifier → adiciona pf_pj_label, pf_pj_confidence
   Step 5: run_shadow_invoice_detection → detecta assinaturas + parcelamentos
   Step 8: save_transactions_clean → persiste em DuckDB

3. FORECAST
   GET /api/v1/forecast/{user_id}
         ↓
   NexaRunner.run(user_id)
         ↓
   CashflowProjector.project(transactions_df, shadow_invoices_df)
   → projection_df: 30 linhas (uma por dia)
         ↓
   SafeToSpendCalculator.calculate(projection_df)
   → safe_to_spend_daily: valor seguro por dia
         ↓
   FinanceEngine.calculate_summary(income, expenses)
   → health_score, savings_rate
         ↓
   ForecastResponse {
     cashflow: { horizon_days, starting_balance, ending_balance,
                 worst_balance, risk_level, daily_data },
     safe_to_spend: { current_balance, safe_to_spend_daily,
                      safety_buffer, risk_level },
     shadow_invoices: { invoices, total_monthly_impact,
                        subscriptions_count, installments_count },
     financial_health: { health_score, savings_rate, profile_type }
   }
```

---

## Integração Pluggy

O sistema opera em dois modos:

| Modo | Cliente | Quando usar |
|------|---------|------------|
| `dev` | `MockPluggyClient` | Desenvolvimento / testes locais |
| `prod` | `PluggyClient` | Produção com dados reais |

**Variáveis de ambiente necessárias (`.env`):**
```
PLUGGY_CLIENT_ID=...
PLUGGY_CLIENT_SECRET=...
PLUGGY_BASE_URL=https://api.pluggy.ai
FRONTEND_BASE_URL=http://localhost:3000
```

**Autenticação Pluggy:** `POST /auth` com `clientId` + `clientSecret` → recebe `apiKey` (Bearer token). Token salvo em memória por instância.

---

## Fases do Produto

| Fase | Nome | Status |
|------|------|--------|
| F1 | Cashflow / Safe-to-Spend | Completo — 414 testes passando |
| F2 | Card Optimizer | Não iniciado |
| F3 | Nexa Architect (Simulações) | Completo — 355 testes passando |
| F4 | Nexa Divider (PF/PJ) | Completo (isolado) — integrado no NexaRunner |

---

## TODOs Conhecidos

- ETL `run_etl_pipeline()` em `etl/runner.py`: steps 1, 2, 3, 6, 7 marcados como TODO (NexaRunner já os executa corretamente)
- `GET /transactions/{user_id}` retorna 501 (sem persistência real ainda)
- `GET /forecast/{user_id}` usa dados mock (NexaRunner mode="dev") — precisa buscar dados reais por user_id
- Webhook `POST /transactions/webhook` não persiste no banco (step de save comentado como TODO)
- LangGraph Agent (`routes/analyze.py`) — estrutura pronta, import desabilitado no router; sem LLM integrado
- F2 Card Optimizer — não iniciado
- Autenticação JWT — `security.py` vazio, nenhum endpoint protegido
