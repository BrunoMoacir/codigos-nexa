# FUNCIONALIDADE 2 — NEXA OPTIMIZER
# Documento de Implementação e Progresso

> **Objetivo:** Analisar o padrão real de consumo do usuário e recomendar o melhor cartão de crédito com cálculo matematicamente justificado.
>
> **Dependência:** F1 (Nexa Core Engine) — obrigatório estar funcionando antes ✅
>
> **Status atual:** 🔄 Em andamento — Passo 2.4 em progresso (106/106 testes passando, input_validator.py criado)
>
> **Última atualização:** 2026-02-26

---

## O QUE A F2 FAZ

O **Nexa Optimizer** responde a uma pergunta simples e valiosa: **"Qual cartão de crédito me dá mais retorno dado o meu padrão de gasto real?"**

### Princípio central

A recomendação é **matematicamente justificada** — o sistema prova que trocar de cartão gera lucro líquido **ou** diz explicitamente para não trocar. Se a troca não for vantajosa numericamente, a Nexa diz isso ao usuário.

### Exemplo de resposta ao usuário

> *"Você gasta em média R$ 1.800/mês no débito e R$ 1.400/mês em cartões de crédito. Com esse padrão, o cartão Nubank Ultravioleta te geraria aproximadamente R$ 480/ano em pontos. Seu gasto anual projetado de R$ 38.400 ultrapassa o threshold de isenção de R$ 36.000, então a anuidade seria zerada. No pior cenário (gasto 20% menor) o ganho ainda seria de R$ 384. Chance de aprovação: alta."*

### Fluxo de dados

```
Open Finance (Pluggy)
        │
        ▼
F1 — Nexa Core Engine  ← já pronto ✅
  ├── transactions_clean        → ConsumptionProfiler
  ├── shadow_invoice_events     → CardSimulator
  ├── daily_forecast            → CardSimulator
  └── safe_to_spend             → LiquidityChecker
        │
        ▼
F2 — Nexa Optimizer             ← este módulo
  ├── ConsumptionProfiler       (quem é o usuário + padrão real de consumo)
  ├── CardKnowledgeBase         (regras reais de cartões: anuidade, pontos, etc.)
  ├── CardSimulator             (ganho líquido por cartão em 3 cenários)
  ├── LiquidityChecker          (verifica se anuidade compromete caixa)
  ├── CardRanking               (ordena por retorno + penaliza risco)
  └── OptimizerService          (orquestra tudo)
        │
        ▼
POST /api/v1/optimizer/analyze/{user_id}   → OptimizationReport (JSON)
```

---

## ARQUIVOS A CRIAR

### 📦 Módulo principal — `backend/app/optimizer/`

---

#### ✅ `app/optimizer/models.py` — Schemas Pydantic
**Status:** PRONTO

Contém todos os tipos de entrada e saída. Sem lógica — só estrutura.

**Enums criados:**
- `CardType` — `POINTS` / `CASHBACK` / `INVESTBACK`
- `BenefitTag` — `TRAVEL`, `CASHBACK`, `LOUNGE`, `INSURANCE`, `INTERNACIONAL`, `PREMIUM`
- `CardFlag` — `VISA`, `MASTERCARD`, `ELO`, `AMEX`, `HIPERCARD`
- `RecommendationType` — `SWITCH_RECOMMENDED` / `KEEP_CURRENT` / `INSUFFICIENT_DATA`
- `LiquidityRisk` — `SAFE` / `WARNING` / `HIGH` / `CRITICAL`

**Schemas criados:**
- `WaiverRules` — Regras de isenção de anuidade (spend_threshold, always_free, none, transaction_count)
- `CardRecord` — Schema completo de um cartão (renda mínima, anuidade, programa de pontos/cashback, etc.)
- `OptimizationRequest` — Entrada: `user_id`, `current_cards`, `safe_to_spend`, `monthly_income`
- `CardSimulationResult` — Saída por cartão: ganho nas 3 faixas (min/expected/max), liquidez, elegibilidade, etc.
- `OptimizationReport` — Saída final com melhor cartão, todos os simulados, strategy_text, warnings

---

#### ✅ `app/optimizer/card_loader.py` — CardKnowledgeBase
**Status:** PRONTO

Carrega e mantém em memória a base de cartões do arquivo JSON.

**Métodos:**
```python
class CardKnowledgeBase:
    def load(self) -> list[CardRecord]
        # Lê knowledge_cards.json e parseia todos os cartões

    def get_by_id(self, card_id: str) -> CardRecord | None
        # Busca um cartão específico pelo ID

    def filter_eligible(self, annual_income, current_card_ids, ...) -> list[CardRecord]
        # Hard constraints:
        #   - Remove cartões com min_income > renda anual do usuário
        #   - Remove cartões que o usuário já possui
        #   - Remove consignados (sem vínculo empregatício formal)
        #   - Remove secured_card quando renda é suficiente para convencionais

    def compute_eligibility_score(self, card, annual_income, spending_stability, ...) -> tuple[float, list[str]]
        # Calcula score 0.0–1.0 de chance de aprovação
        # income_ratio >= 2.0 → 0.95 | >= 1.5 → 0.80 | >= 1.2 → 0.70 | >= 1.0 → 0.60
        # × spending_stability
        # + 0.10 se usuário tem produto do mesmo emissor
        # Retorna também lista de razões em linguagem natural
```

---

#### ✅ `app/optimizer/profiler.py` — ConsumptionProfiler
**Status:** PRONTO

Analisa o histórico real de transações e monta o perfil de consumo do usuário.

**Entrada:** `transactions_clean` (Polars DataFrame), `shadow_invoice_events`, `safe_to_spend`

**O que calcula (`UserProfile`):**
```python
class UserProfile:
    monthly_avg_spend: float              # Média mensal ajustada (últimos 3 meses)
    committed_percentage: float           # % comprometida com parcelas/assinaturas
    spend_by_category: dict               # {"alimentacao": 1200, "lazer": 400, ...}
    spend_by_source: dict                 # {"debit": 1800, "credit": 1200}
    international_spend_monthly: float    # Estimativa USD/mês
    travel_spend_monthly: float           # Gasto em lazer + transporte
    estimated_monthly_income: float       # Inferido de créditos detectados pela F1
    data_coverage_months: int             # Meses de histórico disponíveis
    spending_stability: float             # 0–1 (baixa variabilidade = mais estável)
```

**Regras:**
- Usa os últimos 90 dias de `transactions_clean`
- Exclui transações `pf_pj_label = "PJ"` do consumo pessoal
- Considera `shadow_invoice_events` para `committed_percentage`
- `data_coverage_months < 2` → `confidence_score` penalizado nos cartões

---

#### ✅ `app/optimizer/simulator.py` — CardSimulator
**Status:** PRONTO

Calcula o retorno financeiro real de cada cartão para o perfil específico do usuário.

**Entrada:** `CardRecord`, `UserProfile`, `safe_to_spend`

**Algoritmo por cartão:**
```
1. Anuidade efetiva
   Se waiver_rules.type == "spend_threshold":
       gasto_anual = monthly_avg_spend × 12
       if gasto_anual >= waiver_rules.threshold:
           annuity_effective = 0.0   (isento!)
       else:
           annuity_effective = base_annuity

2. Valor dos pontos/cashback (3 cenários ±20%)
   Para POINTS:
       points_value = (gasto_anual × fator × points_per_brl / 1000) × points_conversion_rate
   Para CASHBACK:
       cashback_value = gasto_anual × fator × cashback_pct
       if cashback_cap: cashback_value = min(cashback_value, cashback_cap × 12)

3. Ganho líquido
   net_gain = valor_beneficio - annuity_effective

4. Impacto de liquidez
   liquidity_impact = (annuity_effective / 12) / safe_to_spend
   if safe_to_spend <= 0: liquidity_impact = 1.0 (CRITICAL automático)

5. Confidence score
   coverage_weight   = min(data_coverage_months, 6) / 6
   stability_weight  = spending_stability
   bank_trust_weight = card.data_trust_score
   confidence_score  = coverage_weight × stability_weight × bank_trust_weight
   if data_coverage_months < 2: confidence_score × 0.5
   if committed_percentage > 80%: confidence_score × 0.7
```

**Campos gerados para o LLM:**
- `spending_anchor` — ancora o cálculo no gasto real observado
  ```python
  {"debit_monthly": 1800, "credit_monthly": 1200, "total_monthly": 3000,
   "main_categories": ["alimentacao", "transporte"], "international_monthly": 0}
  ```
- `profile_match_reasons` — por que o cartão se encaixa no perfil
  - *"Seu gasto anual projetado de R$ X isenta a anuidade de R$ Y"*
  - *"Seu gasto de R$ X/mês em [categoria] rende Z% de cashback = R$ W/ano"*
  - *"Seu gasto internacional de R$ X/mês se beneficia do zero IOF deste cartão"*

---

#### ✅ `app/optimizer/ranking.py` — CardRanking
**Status:** PRONTO

Ordena os cartões simulados aplicando penalidades de risco e elegibilidade.

**Algoritmo:**
```
score_base = net_gain_expected

Penalidades de liquidez:
  CRITICAL → score -= net_gain_expected × 0.8
  HIGH     → score -= net_gain_expected × 0.4
  WARNING  → score -= net_gain_expected × 0.1

Penalidade de confiança baixa:
  confidence_score < 0.4 → score × 0.5

Bônus de benefícios relevantes:
  international_spend > 500/mês e card tem INTERNACIONAL → +bônus
  travel_spend > 800/mês e card tem LOUNGE → +bônus

Penalidade de elegibilidade:
  eligibility_score < 0.5  → score × 0.4   (provavelmente inacessível)
  eligibility_score < 0.7  → score × 0.75  (aprovação incerta)
  eligibility_score >= 0.7 → sem penalidade

Retorno: lista ordenada por score (decrescente)
```

**Regras especiais:**
- Se `net_gain_expected` do melhor cartão for negativo → `KEEP_CURRENT`
- Se melhor cartão tiver `eligibility_score < 0.4` → promover próximo com score >= 0.6

---

#### ✅ `app/optimizer/validators/input_validator.py` — InputValidator
**Status:** PRONTO

Valida regras de negócio do `OptimizationRequest`:

| Regra | Condição | Erro |
|---|---|---|
| R1 | `user_id` não vazio | `user_id é obrigatório` |
| R2 | `safe_to_spend >= 0` se fornecido | `safe_to_spend não pode ser negativo` |
| R3 | `monthly_income > 0` se fornecido | `renda mensal deve ser positiva` |
| R4 | Pelo menos um dos dois informado | `informe safe_to_spend ou monthly_income` |

---

#### ✅ `app/optimizer/validators/liquidity_checker.py` — LiquidityChecker
**Status:** PRONTO

Classifica o risco da anuidade para o caixa do usuário:

| Condição (`liquidity_impact`) | Nível |
|---|---|
| > 0.50 | `CRITICAL` |
| > 0.25 | `HIGH` |
| > 0.10 | `WARNING` |
| ≤ 0.10 | `SAFE` |

---

#### ✅ `app/optimizer/services/optimizer_service.py` — OptimizerService
**Status:** PRONTO

Ponto único de entrada. Orquestra tudo na sequência correta:

```python
class OptimizerService:
    def analyze(self, request: OptimizationRequest, transactions_df, shadow_invoices_df) -> OptimizationReport:
        # 1. InputValidator.validate(request)
        # 2. ConsumptionProfiler.build(transactions_df, shadow_invoices_df)
        # 3. CardKnowledgeBase.load() → filter_eligible(profile)
        # 4. Para cada cartão:
        #    a. CardSimulator.simulate(card, profile, safe_to_spend)
        #    b. LiquidityChecker.check(result) → liquidity_risk
        #    c. CardKnowledgeBase.compute_eligibility_score(card, profile)
        # 5. CardRanking.rank(results, profile)
        # 6. Determinar RecommendationType
        # 7. Consolidar warnings
        # 8. Persistir em optimization_reports (DuckDB via optimizer_queries.py)
        # 9. Retornar OptimizationReport
```

---

### 🔌 API — `backend/app/api/v1/routes/optimizer.py`

**Status:** A CRIAR

**Endpoints a criar:**

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/api/v1/optimizer/analyze/{user_id}` | Análise completa — busca dados da F1. chama OptimizerService, retorna OptimizationReport |
| `GET` | `/api/v1/optimizer/reports/{user_id}` | Lista relatórios salvos do usuário (DuckDB) |
| `GET` | `/api/v1/optimizer/reports/{report_id}/detail` | Relatório completo por ID |
| `GET` | `/api/v1/optimizer/cards` | Lista todos os cartões da base de conhecimento |
| `GET` | `/api/v1/optimizer/health` | Health check do módulo |

**Responsabilidade da rota `POST /analyze/{user_id}`:**
1. Buscar `safe_to_spend` e `shadow_invoices` da F1 via NexaRunner/DuckDB
2. Buscar `transactions_clean` do DuckDB
3. Remontar `OptimizationRequest` com os dados reais
4. Chamar `OptimizerService.analyze()`
5. Retornar `OptimizationReport`

Se `safe_to_spend = None` → usa `monthly_income` como fallback + warning na resposta.

---

### 🗃️ Banco de dados — `backend/app/db/queries/optimizer_queries.py`

**Status:** ✅ PRONTO

Tabela criada: `optimization_reports`

```sql
CREATE TABLE IF NOT EXISTS optimization_reports (
    report_id               VARCHAR PRIMARY KEY,
    user_id                 VARCHAR NOT NULL,
    generated_at            VARCHAR NOT NULL,
    recommendation_type     VARCHAR NOT NULL,  -- SWITCH_RECOMMENDED | KEEP_CURRENT | INSUFFICIENT_DATA
    best_card_id            VARCHAR,
    best_card_name          VARCHAR,
    net_gain_expected       DOUBLE,
    net_gain_min            DOUBLE,
    net_gain_max            DOUBLE,
    confidence_score        DOUBLE,
    liquidity_impact        DOUBLE,
    liquidity_risk          VARCHAR,
    data_sources            VARCHAR,           -- JSON array
    strategy_text           VARCHAR,
    warnings                VARCHAR,           -- JSON array
    full_report_json        VARCHAR            -- OptimizationReport completo
)
```

**Funções criadas:**
- `save_optimization_report(report: dict)` — upsert por `report_id`
- `get_optimization_reports(user_id: str)` — lista por usuário, mais recente primeiro
- `get_optimization_report_by_id(report_id: str)` — relatório completo por ID

---

### 📚 Base de conhecimento — `backend/data/cards/knowledge_cards.json`

**Status:** ✅ PRONTO — 8 cartões seed

| Card ID | Nome | Tipo | Anuidade | Renda Mínima Anual | Isenção |
|---|---|---|---|---|---|
| `nubank-ultravioleta` | Nubank Ultravioleta | POINTS | R$ 2.856 | R$ 200k | Gasto R$ 200k/ano |
| `nubank-roxinho` | Nubank Standard | POINTS | R$ 0 | Sem restrição | Sempre isento |
| `itau-personnalite` | Itaú Personnalité Visa Infinite | POINTS | R$ 5.544 | R$ 250k | Gasto R$ 250k/ano |
| `c6-carbon` | C6 Carbon | POINTS | R$ 1.080 | R$ 60k | Gasto R$ 100k/ano |
| `inter-black` | Inter Black | CASHBACK | R$ 0 | R$ 60k | Sempre isento |
| `xp-visa-infinite` | XP Visa Infinite | POINTS | R$ 2.388 | R$ 120k | Gasto R$ 144k/ano |
| `picpay-card` | PicPay Card | CASHBACK | R$ 0 | Sem restrição | Sempre isento |
| `next-visa` | Next Visa | CASHBACK | R$ 0 | Sem restrição | Sempre isento |

**Schema de cada cartão:**
```json
{
  "card_id": "string (slug único)",
  "name": "string",
  "issuer": "string (banco/fintech)",
  "flag": "VISA | MASTERCARD | ELO | AMEX | HIPERCARD",
  "card_type": "POINTS | CASHBACK | INVESTBACK",
  "min_income": "float (renda mínima ANUAL em R$)",
  "base_annuity": "float (anuidade cheia em R$)",
  "waiver_rules": {
    "type": "spend_threshold | always_free | none | transaction_count",
    "threshold": "float (opcional)",
    "description": "string"
  },
  "cashback_pct": "float | null",
  "cashback_cap": "float | null (teto mensal em R$)",
  "points_per_brl": "float | null (pontos por R$ gasto)",
  "points_conversion_rate": "float (R$ por 1000 pontos)",
  "benefit_tags": ["TRAVEL", "LOUNGE", "INSURANCE", "INTERNACIONAL", "PREMIUM", "CASHBACK"],
  "data_trust_score": "float 0-1 (1.0 = dados verificados oficialmente)"
}
```

---

### 🤖 Agente — `backend/app/agent/tools/get_card_optimization.py`

**Status:** A CRIAR — depende do agente LangGraph estar ativo

**Tool a criar:**
```python
@tool
def get_card_optimization(user_id: str) -> str:
    """
    Analisa o perfil financeiro do usuário e recomenda cartões
    que maximizem retorno dado o padrão real de consumo e liquidez disponível.
    Retorna: relatório com recomendação, ganho esperado e explicação.
    """
    ...
```

**Gatilhos para o agente acionar esta tool:**
- "melhor cartão"
- "vale a pena trocar de cartão"
- "cartão de crédito"
- "milhas / cashback / pontos"
- "anuidade"

---

## TESTES A CRIAR

todos ficam em `backend/tests/optimizer/`

| Arquivo | O que cobre | Status |
|---|---|---|
| `test_card_loader.py` | `CardKnowledgeBase` (load, filter, eligibility) | ✅ PRONTO — 16 testes passando |
| `test_profiler.py` | `ConsumptionProfiler` (cálculo de UserProfile) | ✅ PRONTO — 31 testes passando |
| `test_liquidity_checker.py` | `LiquidityChecker` (4 faixas de risco) | ✅ PRONTO — 4 testes passando |
| `test_simulator.py` | `CardSimulator` (cálculo de retorno e anuidade) | ✅ PRONTO — 21 testes passando |
| `test_ranking.py` | `CardRanking` (ordenação e penalidades) | ✅ PRONTO — 18 testes passando |
| `test_input_validator.py` | `InputValidator` (4 regras de negócio) | ✅ PRONTO — 9 testes passando |
| `test_optimizer_service.py` | `OptimizerService` (orquestrador E2E) | ✅ PRONTO — 2 testes passando |
| `test_api.py` | Endpoints REST do optimizer | ⏳ A CRIAR |

---

## PROGRESSO — CHECKLIST

### 2.1 Base de cartões e modelos ✅

- [x] `app/optimizer/models.py` — enums e schemas Pydantic
- [x] `data/cards/knowledge_cards.json` — 8 cartões seed
- [x] `app/optimizer/card_loader.py` — CardKnowledgeBase
- [x] `app/db/queries/optimizer_queries.py` — queries DuckDB
- [x] `tests/optimizer/test_card_loader.py` — 16/16 passando

### 2.2 Profiler ✅

- [x] `app/optimizer/profiler.py` — ConsumptionProfiler
- [x] `tests/optimizer/test_profiler.py`

### 2.3 Simulador e Ranking ✅

- [x] `app/optimizer/validators/liquidity_checker.py`
- [x] `app/optimizer/simulator.py` — CardSimulator
- [x] `app/optimizer/ranking.py` — CardRanking
- [x] `tests/optimizer/test_liquidity_checker.py`
- [x] `tests/optimizer/test_simulator.py`
- [x] `tests/optimizer/test_ranking.py`

### 2.4 Validação e Orquestrador ✅

- [x] `app/optimizer/validators/input_validator.py`
- [x] `app/optimizer/services/optimizer_service.py`
- [x] `tests/optimizer/test_input_validator.py`
- [x] `tests/optimizer/test_optimizer_service.py`

### 2.5 API e Integração ⏳

- [ ] `app/api/v1/routes/optimizer.py`
- [ ] Registrar no `app/api/v1/router.py`
- [ ] `tests/optimizer/test_api.py`
- [ ] Atualizar `PRODUCTION_CHECKLIST.md`

### 2.6 Agente LangGraph ⏳

- [ ] `app/agent/tools/get_card_optimization.py`
- [ ] Integrar no grafo LangGraph
- [ ] Testar via `POST /chat`

---

## COMO TESTAR (Linux)

### Rodar testes com o venv do projeto

```bash
# Ativando o venv (da raiz do projeto)
source venv/bin/activate

# Navegar para o backend
cd backend

# Rodar os testes do Optimizer
pytest tests/optimizer/ -v

# Rodar todos os testes do projeto
pytest tests/ -v
```

### Ou usando o python do venv diretamente

```bash
/home/bruno/Área\ de\ trabalho/nexa/codigos-nexa/venv/bin/python \
  -m pytest backend/tests/optimizer/ -v
```

### Rodar a API e testar via Swagger

```bash
source venv/bin/activate
cd backend
uvicorn app.main:app --reload --host localhost --port 8000
# Acessar: http://localhost:8000/docs
```

---

## ESTRUTURA FINAL DE ARQUIVOS

Quando tudo estiver pronto, a estrutura do módulo será:

```
backend/
├── app/
│   ├── optimizer/
│   │   ├── __init__.py                   ✅
│   │   ├── models.py                     ✅ (schemas Pydantic)
│   │   ├── card_loader.py                ✅ (CardKnowledgeBase)
│   │   ├── profiler.py                   ✅ (ConsumptionProfiler)
│   │   ├── simulator.py                  ✅ (CardSimulator)
│   │   ├── ranking.py                    ✅ (CardRanking)
│   │   ├── validators/
│   │   │   ├── __init__.py               ✅
│   │   │   ├── input_validator.py        ✅
│   │   │   └── liquidity_checker.py      ✅
│   │   └── services/
│   │       ├── __init__.py               ✅
│   │       └── optimizer_service.py      ✅
│   │
│   ├── api/v1/routes/
│   │   └── optimizer.py                  ⏳
│   │
│   └── db/queries/
│       └── optimizer_queries.py          ✅
│
├── data/
│   └── cards/
│       └── knowledge_cards.json          ✅ (8 cartões seed)
│
└── tests/
    └── optimizer/
        ├── __init__.py                   ✅
        ├── test_card_loader.py           ✅ (16 testes passando)
        ├── test_profiler.py              ✅
        ├── test_liquidity_checker.py     ✅
        ├── test_simulator.py             ✅
        ├── test_ranking.py               ✅
        ├── test_input_validator.py       ✅
        ├── test_optimizer_service.py     ✅
        └── test_api.py                   ⏳
```

---

*Documento mantido durante a implementação da F2. ✅ = pronto e testado, ⏳ = a criar.*
