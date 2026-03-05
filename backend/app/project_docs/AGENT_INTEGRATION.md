# AGENT_INTEGRATION.md
# Como toda a inteligência do projeto chega ao agente Nexa

> Versão: 2026-03-05
> Escopo: Mapeamento completo de módulos → ferramentas do agente → resposta ao usuário

---

## 1. Visão Geral da Arquitetura

```
Usuário (chat)
    │
    ▼
POST /api/v1/chat/
    │  (ChatRequest: user_id + message)
    ▼
build_financial_agent()          ← app/agent/graph.py
    │  LangGraph ReAct (GPT-4o-mini)
    │  System prompt instrui quando usar cada tool
    │
    ├─► get_financial_forecast    ← NexaRunner (pipeline F1 completo)
    ├─► get_budget_advice         ← BudgetAdvisor (M1.3)
    ├─► get_card_optimization     ← OptimizerService (F2)
    ├─► get_spending_alerts       ← NexaRunner + ProactiveNotifier (MX.3)
    └─► get_goals_summary         ← GoalTracker (MX.2)
```

O agente é um **ReAct loop**: recebe a mensagem, decide qual ferramenta chamar (ou nenhuma), executa, lê o resultado em texto, e responde em linguagem natural. Cada ferramenta retorna uma **string formatada** — nunca JSON bruto — para o LLM interpretar.

---

## 2. NexaRunner — O Pipeline Central (F1)

**Arquivo:** `app/runner.py`

Três tools (`get_financial_forecast`, `get_budget_advice`, `get_spending_alerts`) invocam o `NexaRunner` para obter dados frescos. O runner executa 9 etapas em sequência:

| Etapa | Módulo | Saída |
|-------|--------|-------|
| 1. Pluggy/Mock | `app/integrations/open_finance/` | Transações brutas |
| 2. Validação Pydantic | `app/schemas/transaction.py` | `TransactionBatchResult` |
| 3. ETL Ingestor | `app/etl/ingestor.py` | DataFrame limpo + DuckDB |
| 4. Classifier | `app/etl/classifier.py` | DataFrame com `category` |
| 5. PF/PJ Classifier | `app/etl/pf_pj_classifier.py` | DataFrame com `pf_pj_label` |
| 5.5 IncomeProfiler | `app/etl/income_profiler.py` | `IncomeProfile` (renda + padrão + confiança) |
| 6. RecurringDetector | `app/etl/recurring.py` | Padrões recorrentes |
| 7. Shadow Invoice | `app/etl/shadow_invoice.py` | Eventos futuros projetados |
| 8. CashflowProjector | `app/cashflow/projector.py` | DataFrame diário de saldo |
| 9. SafeToSpend + BurnRate | `app/cashflow/safe_to_spend.py` + `burn_rate.py` | `SafeToSpend`, `BurnRateResult` |

**O runner retorna um dict** com chaves: `status`, `metadata`, `transactions`, `analysis`, `projections`.

---

## 3. Mapeamento Ferramenta → Módulos → Features Implementadas

### 3.1 `get_financial_forecast`
**Arquivo:** `app/agent/tools/get_financial_forecast.py`
**Ativa quando:** usuário pergunta sobre situação financeira, saúde financeira, quanto pode gastar, resumo do perfil.

```
NexaRunner.run()
    ├── income_profile          ← IncomeProfiler (MI.2, MI.4, MI.7)
    │      • monthly_net_income, income_pattern, confidence
    │      • Exposto como texto: "Renda estimada: R$X/mês (padrão CLT, 80% confiança)"
    ├── safe_to_spend           ← SafeToSpendCalculator
    │      • safe_to_spend_total, safe_to_spend_daily, risk_level
    ├── user_profile            ← profiles.py
    │      • financial_health_score (0–100), trend, profile_type (MI.2)
    └── cashflow_forecast       ← CashflowProjector
           • expected_balance, monthly_income, monthly_expense
```

**Features ativas nesta tool:**
- MI.2 — Perfil de renda e health score diferenciado
- MI.4 — Estabilidade de renda no confidence do score
- MI.7 — income_profile exposto na saída (renda + padrão + confiança)

---

### 3.2 `get_budget_advice`
**Arquivo:** `app/agent/tools/get_budget_advice.py`
**Ativa quando:** usuário pergunta sobre orçamento, como dividir salário, regra 50/30/20, se gasta demais em algo.

```
NexaRunner.run()  (para transações reais)
    └── transactions_df
            │
            ▼
BudgetAdvisor.suggest(transactions_df, monthly_income)    ← M1.3
    ├── Agrupa gastos reais por categoria
    ├── Compara com limites 50/30/20
    ├── group_summary: [essenciais, desejos, poupança]
    │      • actual_spent, recommended_limit, pct_of_income, on_track
    └── suggested_cuts: top 3 categorias acima do limite
           • current_spending, suggested_limit, potential_saving
```

**Features ativas nesta tool:**
- M1.3 — BudgetAdvisor (50/30/20 com dados reais)

**Fallback:** Se o runner falhar, responde com cálculo manual simples (50/30/20 sem dados reais).

---

### 3.3 `get_card_optimization`
**Arquivo:** `app/agent/tools/get_card_optimization.py`
**Ativa quando:** usuário pergunta qual cartão pedir, pontos/milhas/cashback, se vale pagar anuidade.

```
OptimizerService.analyze(request, transactions_df, shadow_invoices_df)   ← F2
    ├── CardLoader → carrega catálogo de cartões (card_loader.py)
    │      • compute_eligibility_score() com penalidade PJ instável (MI.3)
    ├── OpportunityCostCalculator (M2.1)
    │      • Calcula custo de oportunidade de trocar de cartão
    ├── MultiCardStrategist (M2.2)
    │      • Detecta se usuário se beneficia de múltiplos cartões
    ├── MilesValuator (M2.3)
    │      • Valoração de milhas por programa (Smiles, Latam, etc.)
    ├── CashbackCategoryRules (M2.5)
    │      • Cashback diferenciado por categoria (supermercado, combustível, etc.)
    ├── PromotionTracker (M2.6)
    │      • Verifica promoções ativas de bônus de pontos
    ├── Simulator.calculate_current_card_roi() (M2.4)
    │      • ROI real do cartão atual vs. alternativas
    └── IncomeProfiler (MI.8)
           • Contexto de renda no output: fonte e nível de confiança
```

**Output para o LLM:**
```
Relatório de Otimização (ID: ...)
Recomendação Principal: UPGRADE
Estratégia: ...
Renda: R$X/mês (declarada pelo usuário — alta confiança)
Card Vencedor: Itaú Personnalité (ID: itau_personnalite)
Valor de Benefícios Projetado: R$ 480.00
Anuidade Efetiva: R$ 120.00
> Lucro Líquido Anual: R$ 360.00 <
Elegibilidade: Renda acima do mínimo; Perfil PJ estável
```

**Features ativas nesta tool:**
- F2 completo (M2.1–M2.6)
- MI.3 — Elegibilidade diferenciada para MEI/PJ
- MI.8 — Contexto de renda com nível de confiança

---

### 3.4 `get_spending_alerts`
**Arquivo:** `app/agent/tools/get_spending_alerts.py`
**Ativa quando:** usuário pergunta sobre alertas, gastos estranhos, o que deve se preocupar, anomalias.

```
NexaRunner.run()
    └── alerts[]   ← gerados por AlertEngine (severity: CRITICAL/WARNING/INFO)
           • Token expirado (Open Finance)
           • Saldo baixo
           • HIGH_COMMITMENT com income context (MI.6)

ProactiveNotifier.generate(ctx)    ← app/notifications/notifier.py (MX.3)
    ├── BURN_RATE_HIGH          ← BurnRateAnalyzer (M1.2, MI.5)
    ├── SAFE_TO_SPEND_LOW       ← SafeToSpendCalculator
    ├── ANOMALY_DETECTED        ← SpendingAnomalyDetector (MI.1 — threshold por renda)
    ├── SUBSCRIPTION_FORGOTTEN  ← RecurringDetector
    ├── GOAL_AT_RISK            ← GoalTracker (MX.2)
    ├── CARD_OPPORTUNITY        ← OptimizerService (F2)
    ├── SHADOW_INVOICE_DUE      ← ShadowInvoiceDetector
    ├── INCOME_IRREGULAR        ← IncomeProfiler (MI.4)
    └── HEALTH_SCORE_DROP       ← profiles.py (MX.1)
```

**Features ativas nesta tool:**
- MX.3 — 9 tipos de notificações proativas
- MI.1 — Anomalia calibrada por renda
- MI.5 — Burn rate com income_ratio
- MI.6 — Alerta HIGH_COMMITMENT com contexto de renda

---

### 3.5 `get_goals_summary`
**Arquivo:** `app/agent/tools/get_goals_summary.py`
**Ativa quando:** usuário pergunta sobre metas, reserva de emergência, progresso de poupança.

```
GoalTracker.list_goals(user_id)    ← app/goals/tracker.py (MX.2)
    ├── Lê financial_goals do DuckDB
    ├── Calcula progresso: current_amount / target_amount
    ├── Projection: estimated_completion_date (baseada em monthly_savings)
    └── status: ON_TRACK / AT_RISK / COMPLETED / PAUSED
```

**Output para o LLM:**
```
Suas Metas Financeiras (2 ativa(s))

Reserva de Emergência
  [████████░░] 80%
  R$ 16.000 de R$ 20.000 (faltam R$ 4.000)
  Estimativa: 2026-07-01

Viagem Europa
  [███░░░░░░░] 30%
  R$ 3.000 de R$ 10.000 (faltam R$ 7.000)
  Com R$ 700/mês → 10 meses para atingir
```

**Features ativas nesta tool:**
- MX.2 — GoalTracker completo com projeção de data

---

## 4. Features com Inteligência mas SEM Tool no Agente (Lacunas)

Estas features existem como endpoints REST, mas **o agente não as usa ainda**:

| Feature | Módulo | Endpoint REST | Tool Faltante |
|---------|--------|---------------|---------------|
| F3 — Architect | `app/architect/` | `POST /architect/simulate` | `get_financing_simulation` |
| F4 — Fiscal PJ | `app/etl/fiscal_report.py` | `GET /fiscal-report/{user_id}` | `get_fiscal_report` |
| MX.4 — Peers | `app/peers/peer_comparison.py` | `GET /peers/compare/{user_id}` | `get_peer_comparison` |
| MX.1 — Health Score History | `app/db/queries.py` | `GET /health-score/history/{user_id}` | (integrar em `get_financial_forecast`) |
| M1.5 — Subscriptions | `app/api/v1/routes/subscriptions.py` | `GET /subscriptions/{user_id}` | (integrar em `get_spending_alerts`) |
| M3.3 — Card Optimization Bonus no Architect | `app/architect/services/architect_service.py` | resposta do `/architect/simulate` | (integrar em `get_financing_simulation`) |

### Tools sugeridas para fechar as lacunas:

```python
# Tool 6 — F3 Architect
@tool
def get_financing_simulation(user_id, goal_amount, strategy="FINANCING"):
    """Simula financiamento vs. poupança vs. consórcio para um objetivo."""
    # Chama ArchitectService.simulate()
    # Inclui card_optimization_bonus (M3.3) se strategy == FINANCING

# Tool 7 — Fiscal PJ
@tool
def get_fiscal_report(user_id):
    """Gera relatório fiscal para MEI/PJ: deduções, categorias PJ, impostos."""
    # Chama FiscalReportService

# Tool 8 — Peer Comparison
@tool
def get_peer_comparison(user_id, monthly_income):
    """Compara gastos do usuário com benchmarks IBGE para a faixa de renda."""
    # Chama PeerComparator.compare()
```

---

## 5. IncomeProfiler — Módulo Transversal

**Arquivo:** `app/etl/income_profiler.py`

O `IncomeProfiler` é o módulo mais transversal do sistema. Ele aparece em:

| Onde é usado | Como aparece |
|---|---|
| `NexaRunner` (etapa 5.5) | Gera `income_profile` com renda, padrão e confiança |
| `get_financial_forecast` | Exibe renda estimada ao usuário |
| `get_card_optimization` | Adiciona contexto de renda no output (MI.8) |
| `SpendingAnomalyDetector` | Calibra threshold de anomalia por renda (MI.1) |
| `BurnRateAnalyzer` | Calcula `income_ratio` (burn % da renda) (MI.5) |
| `CardLoader` | Qualifica elegibilidade por estabilidade de renda (MI.3) |
| `AlertEngine` | Dispara `INCOME_IRREGULAR` quando confiança < 50% |
| `ProactiveNotifier` | `INCOME_IRREGULAR` notification via IncomeProfiler |

**Outputs do IncomeProfiler:**
```python
IncomeProfile(
    monthly_net_income=8500.0,          # Renda líquida estimada
    income_pattern=IncomePattern.CLT,   # CLT | MEI | AUTONOMO | IRREGULAR | UNKNOWN
    confidence=0.82,                     # 0.0–1.0
    income_sources=[...],               # Transações identificadas como renda
)
```

**Regra de uso:** Se `confidence >= 0.5`, usa a estimativa. Se `< 0.5`, marca como UNKNOWN e o agente sabe que a análise é menos precisa.

---

## 6. Fluxo Completo de uma Conversa Real

**Pergunta do usuário:** "Minha renda é R$ 8.500. Qual cartão devo pedir?"

```
1. POST /api/v1/chat/  { user_id: "u123", message: "Minha renda é R$ 8.500. Qual cartão devo pedir?" }

2. LangGraph ReAct:
   - LLM lê system prompt → identifica trigger de "get_card_optimization"
   - Extrai monthly_income=8500 da mensagem
   - Chama: get_card_optimization(user_id="u123", monthly_income=8500)

3. get_card_optimization executa:
   a. Cria OptimizationRequest(user_id, monthly_income=8500)
   b. Monta transactions_df vazio (sem dados Pluggy nesta chamada direta)
   c. OptimizerService.analyze():
      - CardLoader carrega cartões elegíveis para renda R$8.500
      - compute_eligibility_score() avalia cada cartão
      - Simulator calcula net_gain_expected para cada um
      - MultiCardStrategist verifica se combinação de 2 cartões supera o melhor único
      - MilesValuator converte pontos em R$ para programas relevantes
      - PromotionTracker verifica bônus ativos
   d. IncomeProfiler contexto: "Renda: R$8.500/mês (declarada — alta confiança)"
   e. Retorna string formatada com vencedor, ROI, top 3 alternativas

4. LLM recebe o resultado da tool e gera resposta em linguagem natural:
   "Com renda de R$ 8.500/mês, o cartão mais vantajoso para você é o Itaú Personnalité.
    Você teria um lucro líquido anual de R$ 360 em benefícios, descontada a anuidade de
    R$ 120. Como segundo melhor, o Nubank Ultraviolet oferece R$ 280/ano de retorno líquido..."

5. Resposta: ChatResponse { response: "Com renda de R$ 8.500/mês..." }
```

---

## 7. Estrutura de Dados Persistidos no DuckDB

O agente indiretamente acessa estes dados via as tools:

| Tabela | Alimentada por | Lida por |
|--------|---------------|----------|
| `transactions` | Webhook Pluggy + NexaRunner | NexaRunner, PeerComparator, SubscriptionRoute |
| `health_score_history` | `profiles.py` após cada análise | `GET /health-score/history/` (falta tool) |
| `financial_goals` | `POST /goals/{user_id}` | GoalTracker → `get_goals_summary` |
| `architect_simulations` | ArchitectService | `GET /architect/simulate` (falta tool) |

---

## 8. Parâmetros que o LLM Extrai da Mensagem do Usuário

O sistema prompt instrui o LLM a extrair automaticamente:

| Parâmetro | Extraído de | Usado em |
|-----------|------------|----------|
| `user_id` | Context da sessão | Todas as tools |
| `monthly_income` | "minha renda é R$ X" / "ganho X/mês" | `get_budget_advice`, `get_card_optimization`, `get_financial_forecast` |
| `safe_to_spend` | "gasto X por mês no cartão" | `get_card_optimization` |
| `monthly_savings` | "consigo poupar X por mês" | `get_goals_summary` |
| `horizon_days` | "projeção para 60 dias" | `get_financial_forecast` |

**Regra fundamental do system prompt:** Se o usuário forneceu o dado na mensagem, o LLM USA diretamente na chamada da tool. Nunca pede de novo.

---

## 9. Resumo: O que Está Wired vs. O que Falta

### Completamente wired no agente (5 tools):
- F1 (NexaRunner completo) via `get_financial_forecast`
- M1.2 (BurnRate) via `get_spending_alerts`
- M1.3 (BudgetAdvisor) via `get_budget_advice`
- F2 completo (M2.1–M2.6) via `get_card_optimization`
- MX.2 (GoalTracker) via `get_goals_summary`
- MX.3 (ProactiveNotifier, 9 tipos) via `get_spending_alerts`
- MI.1–MI.8 (todos os melhoramentos de inteligência de renda) via tools acima

### Existe como REST mas NÃO no agente (3 lacunas prioritárias):
- F3 Architect → precisa de `get_financing_simulation`
- F4 Fiscal PJ → precisa de `get_fiscal_report`
- MX.4 Peers → precisa de `get_peer_comparison`
