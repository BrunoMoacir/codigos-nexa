# FUNCIONALIDADE 2: Nexa Optimizer — Documentação Técnica

**Status:** Especificação Aprovada — Não iniciado
**Dependência:** F1 (Nexa Core Engine) — obrigatório estar funcionando antes
**Stack:** Python, Polars, Pydantic v2, DuckDB, LangGraph
**Última Atualização:** 2026-02-23

---

## 1. Visão Geral

O **Nexa Optimizer** analisa o padrão real de consumo do usuário (via dados do Open Finance já processados pela F1) e recomenda cartões de crédito que maximizem milhas, cashback ou benefícios. A recomendação é **matematicamente justificada**: o sistema prova que trocar de cartão paga a anuidade e gera lucro líquido, ou recomenda não trocar caso isso comprometa a liquidez.

**Premissa central:** se a troca não for vantajosa numericamente, a Nexa diz para não trocar.

### Princípio de adequação ao perfil

Toda recomendação é **ancorada no perfil real do cliente**. O sistema não recomenda cartões genéricos — ele cruza o padrão de consumo observado com os benefícios de cada cartão e calcula o ganho específico para aquele usuário. A resposta ao usuário segue a lógica:

> "Você gasta em média R$ X/mês no débito ou em cartões atuais. O cartão Z te daria R$ Y/ano em benefícios nesse padrão de consumo, com anuidade isenta. Por isso, vale trocar."

Além da vantagem financeira, o sistema avalia **a chance real de o usuário conseguir o cartão** (elegibilidade), garantindo que só recomenda produtos acessíveis ao seu perfil de renda e comportamento. Um cartão com ótimo retorno teórico mas inacessível ao usuário não entra no ranking final.

---

## 2. Como se encaixa no projeto

### Posição no fluxo

```
Open Finance (Pluggy)
        │
        ▼
F1 — Nexa Core Engine          ← já está pronto
  ├── transactions_clean        → consumido pelo Profiler
  ├── shadow_invoice_events     → consumido pelo Simulator
  ├── daily_forecast            → consumido pelo Simulator
  └── safe_to_spend             → consumido pelo LiquidityChecker
        │
        ▼
F2 — Nexa Optimizer             ← este módulo
  ├── ConsumptionProfiler       (quem é o usuário hoje e nos próximos meses)
  ├── CardKnowledgeBase         (regras reais dos cartões)
  ├── CardSimulator             (retorno líquido por cartão)
  ├── CardRanking               (ordena por retorno + penaliza liquidez)
  └── OptimizerService          (orquestrador)
        │
        ▼
API: POST /optimizer/analyze/{user_id}
Agent Tool: get_card_optimization(user_id)
```

### Integração com F1 (padrão idêntico ao F3)

O `OptimizerService` **não chama F1 diretamente** — ele recebe os dados já calculados como parâmetros. A rota `optimizer.py` é responsável por buscar `safe_to_spend`, `shadow_invoices` e `transactions_clean` da F1 e passá-los ao service. Se `safe_to_spend=None`, o sistema usa `monthly_income` como fallback e registra um aviso na resposta.

---

## 3. Estrutura de arquivos

```
backend/
├── app/
│   ├── optimizer/                          ← módulo F2 (espelha app/architect/)
│   │   ├── __init__.py
│   │   ├── models.py                       ← schemas Pydantic (request/response/enums)
│   │   ├── profiler.py                     ← ConsumptionProfiler
│   │   ├── simulator.py                    ← CardSimulator (cálculo de retorno)
│   │   ├── ranking.py                      ← CardRanking (ordenação + penalidades)
│   │   ├── card_loader.py                  ← CardKnowledgeBase (lê data/cards/)
│   │   ├── validators/
│   │   │   ├── __init__.py
│   │   │   ├── input_validator.py          ← valida OptimizationRequest
│   │   │   └── liquidity_checker.py        ← verifica se troca compromete caixa
│   │   └── services/
│   │       ├── __init__.py
│   │       └── optimizer_service.py        ← orquestrador (ponto de entrada)
│   │
│   ├── api/v1/routes/
│   │   └── optimizer.py                    ← endpoints REST da F2
│   │
│   └── db/
│       └── queries/
│           └── optimizer_queries.py        ← DuckDB: salva/busca relatórios
│
├── data/
│   └── cards/
│       ├── knowledge_cards.json            ← seed: cartões com regras reais
│       └── schema.md                       ← documentação do schema da base
│
└── tests/
    └── optimizer/
        ├── __init__.py
        ├── test_profiler.py
        ├── test_simulator.py
        ├── test_ranking.py
        ├── test_card_loader.py
        ├── test_liquidity_checker.py
        ├── test_input_validator.py
        ├── test_optimizer_service.py
        └── test_api.py
```

---

## 4. Responsabilidade de cada arquivo

### `models.py` — Schemas Pydantic

Todos os tipos de entrada e saída do módulo. Nenhuma lógica — só estrutura.

**Enums:**
- `CardType`: `POINTS` / `CASHBACK` / `INVESTBACK`
- `BenefitTag`: `TRAVEL`, `CASHBACK`, `LOUNGE`, `INSURANCE`, `INTERNACIONAL`, `PREMIUM`
- `CardFlag`: `VISA`, `MASTERCARD`, `ELO`, `AMEX`, `HIPERCARD`
- `RecommendationType`: `SWITCH_RECOMMENDED` / `KEEP_CURRENT` / `INSUFFICIENT_DATA`
- `LiquidityRisk`: `SAFE` / `WARNING` / `HIGH` / `CRITICAL`

**Modelos de entrada:**
```
OptimizationRequest:
  user_id: str
  current_cards: list[str]          # IDs dos cartões que o usuário já tem (opcional)
  safe_to_spend: float | None       # injetado pela rota via F1
  monthly_income: float | None      # fallback se safe_to_spend=None
```

**Modelos de saída:**
```
CardSimulationResult:               # resultado por cartão
  card_id: str
  card_name: str
  issuer: str
  flag: CardFlag
  annuity_effective: float          # após aplicar waiver_rules
  annuity_waived: bool
  points_value_min: float           # cenário pessimista
  points_value_expected: float      # cenário esperado
  points_value_max: float           # cenário otimista
  net_gain_min: float               # pontos - anuidade (pessimista)
  net_gain_expected: float          # pontos - anuidade (esperado)
  net_gain_max: float               # pontos - anuidade (otimista)
  liquidity_impact: float           # quanto da anuidade compromete o safe_to_spend
  liquidity_risk: LiquidityRisk
  confidence_score: float           # 0.0–1.0
  eligibility_score: float          # 0.0–1.0 — probabilidade estimada de aprovação
  eligibility_reasons: list[str]    # fatores que embasam (ou limitam) a elegibilidade
  profile_match_reasons: list[str]  # por que este cartão se encaixa no perfil do usuário
  spending_anchor: dict             # gasto observado usado como base da recomendação
                                    # ex: {"debit_monthly": 1800, "credit_monthly": 1200,
                                    #      "main_categories": ["alimentacao", "transporte"]}
  explanation_steps: list[str]      # raciocínio passo a passo
  benefit_highlights: list[str]     # benefícios relevantes para este usuário

OptimizationReport:                 # saída final
  report_id: str
  user_id: str
  generated_at: datetime
  recommendation_type: RecommendationType
  best_card: CardSimulationResult | None
  all_cards: list[CardSimulationResult]
  user_profile_summary: dict        # resumo do perfil usado
  data_sources: list[str]           # ["shadow_invoice","forecast","transactions"]
  strategy_text: str                # explicação em linguagem natural (gerada pelo LLM)
  warnings: list[str]               # avisos (dados insuficientes, confiança baixa, etc.)
```

---

### `profiler.py` — ConsumptionProfiler

**Entrada:** `transactions_clean` (Polars DataFrame), `shadow_invoice_events`, `safe_to_spend`

**O que calcula:**

```
UserProfile:
  monthly_avg_spend: float              # média mensal ajustada (últimos 3 meses)
  committed_percentage: float           # % do gasto futuro já comprometido com parcelas/assinaturas
  spend_by_category: dict               # {"alimentacao": 1200, "lazer": 400, ...}
  international_spend_monthly: float    # estimativa de gasto em USD/mês
  travel_spend_monthly: float           # lazer + transporte relevante para milhas
  estimated_monthly_income: float       # inferido das entradas (créditos) detectadas pela F1
  data_coverage_months: int             # quantos meses de histórico disponíveis
  spending_stability: float             # 0–1 (baixa variabilidade = mais estável)
```

**Regras:**
- Usa os últimos 90 dias de `transactions_clean`
- Exclui transações `pf_pj_label = "PJ"` do cálculo de consumo pessoal
- Considera `shadow_invoice_events` para calcular `committed_percentage`
- `data_coverage_months < 2` → `confidence_score` penalizado

---

### `card_loader.py` — CardKnowledgeBase

Carrega e mantém em memória a base de cartões de `data/cards/knowledge_cards.json`.

**Interface:**
```python
class CardKnowledgeBase:
    def load(self) -> list[CardRecord]
    def filter_eligible(self, profile: UserProfile) -> list[CardRecord]
    def get_by_id(self, card_id: str) -> CardRecord | None
```

**`filter_eligible` aplica hard constraints:**
- `card.min_income <= profile.estimated_monthly_income × 12` → renda anual
- Remove cartões que o usuário já possui (passados em `current_cards`)
- Remove `secured_card=True` se `estimated_monthly_income` for suficiente para cartões convencionais
- Remove `consigned=True` se não houver indicador de vínculo empregatício formal

**`compute_eligibility_score` — score contínuo (0.0–1.0):**

Diferente do filtro binário acima, o `eligibility_score` expressa a probabilidade estimada de aprovação e é exibido ao usuário como indicador de confiança na recomendação:

```
income_ratio = profile.estimated_monthly_income × 12 / card.min_income
  Se income_ratio >= 2.0 → fator renda = 1.0   (renda muito acima do mínimo)
  Se income_ratio >= 1.5 → fator renda = 0.85
  Se income_ratio >= 1.0 → fator renda = 0.65  (renda no limite mínimo)
  Se income_ratio < 1.0  → cartão removido pelo hard filter (não chega aqui)

stability_factor = profile.spending_stability          # 0.0–1.0

existing_relationship_bonus:
  +0.10 se o usuário já tem outro produto do mesmo emissor (detectado via transactions)

eligibility_score = income_ratio_factor × stability_factor + existing_relationship_bonus
eligibility_score = min(eligibility_score, 1.0)
```

**`eligibility_reasons`** — lista de strings geradas para o LLM usar na justificativa:
- `"Renda estimada de R$ X/mês está acima do mínimo exigido (R$ Y/mês)"`
- `"Você já tem relacionamento com [Banco] — aumenta chance de aprovação"`
- `"Histórico de gastos estável nos últimos N meses"`
- `"Renda no limite mínimo — aprovação provável mas não garantida"`

---

### `simulator.py` — CardSimulator

**Entrada:** `CardRecord`, `UserProfile`, `safe_to_spend`

**O que calcula por cartão:**

```
1. Anuidade efetiva
   Se waiver_rules["type"] == "spend_threshold":
       gasto_projetado_anual = monthly_avg_spend × 12
       if gasto_projetado_anual >= waiver_rules["threshold"]:
           annuity_effective = 0.0
           annuity_waived = True
       else:
           annuity_effective = base_annuity

2. Valor dos pontos/cashback por cenário
   spend_annual = monthly_avg_spend × 12

   Pessimista  (multiplica por 0.8 — gasto 20% menor que esperado):
       points_value_min = (spend_annual × 0.8 × points_per_dollar) / 1000 × points_conversion_rate

   Esperado:
       points_value_expected = (spend_annual × points_per_dollar) / 1000 × points_conversion_rate

   Otimista (multiplica por 1.2 — gasto 20% maior):
       points_value_max = (spend_annual × 1.2 × points_per_dollar) / 1000 × points_conversion_rate

3. Ganho líquido por cenário
   net_gain = points_value - annuity_effective

4. Impacto de liquidez
   liquidity_impact = annuity_effective / 12 / safe_to_spend
   (proporção da parcela mensal da anuidade em relação à margem disponível)

5. Confidence score
   confidence_score =
       data_coverage_weight   (min(data_coverage_months, 6) / 6)
     × spending_stability     (da UserProfile)
     × bank_trust_score       (data_trust_score do CardRecord)
```

**`spending_anchor`** — ancora o cálculo no gasto real observado:

O simulador extrai do `UserProfile` o gasto base que justifica a recomendação e o registra em `spending_anchor` para que o LLM construa a justificativa personalizada:

```python
spending_anchor = {
    "debit_monthly": profile.spend_by_source.get("debit", 0),
    "credit_monthly": profile.spend_by_source.get("credit", 0),
    "total_monthly": profile.monthly_avg_spend,
    "main_categories": top_3_categories(profile.spend_by_category),
    "international_monthly": profile.international_spend_monthly,
    "travel_monthly": profile.travel_spend_monthly,
}
```

Isso permite que a `strategy_text` diga explicitamente: *"Com base nos R$ 1.800 que você gasta no débito e R$ 1.200 em cartões de crédito por mês..."*, ancorando a recomendação em dados reais do usuário.

**`profile_match_reasons`** — justificativas de aderência ao perfil:

O simulador gera automaticamente as razões pelas quais o cartão se encaixa no perfil, usadas tanto na `strategy_text` quanto no front-end:
- `"Seu gasto mensal de R$ X é suficiente para isentar a anuidade de R$ Y"`
- `"Você gasta R$ X/mês em [categoria] — o cashback diferenciado nessa categoria vale R$ Y/ano"`
- `"Seu gasto internacional de R$ X/mês é alto — o cartão oferece zero IOF para compras no exterior"`
- `"Você viaja frequentemente — o acesso a salas VIP (LoungeKey) incluso vale R$ X/ano"`

**O sistema nunca retorna um número único** — sempre devolve faixa (min/expected/max) + confidence + explanation_steps.

---

### `ranking.py` — CardRanking

**Entrada:** `list[CardSimulationResult]`, `UserProfile`

**Algoritmo de ranking:**

```
score_base = net_gain_expected

Penalidades:
  Se liquidity_risk == CRITICAL:  score -= net_gain_expected × 0.8
  Se liquidity_risk == HIGH:      score -= net_gain_expected × 0.4
  Se liquidity_risk == WARNING:   score -= net_gain_expected × 0.1
  Se confidence_score < 0.4:      score × 0.5

Bônus de benefícios relevantes:
  Se usuário tem international_spend > 500/mês e cartão tem "INTERNACIONAL": +bônus
  Se usuário tem travel_spend > 800/mês e cartão tem "LOUNGE": +bônus

Penalidade de elegibilidade (baseada no eligibility_score do card_loader):
  Se eligibility_score < 0.5:  score × 0.4   (cartão provavelmente inacessível)
  Se eligibility_score < 0.7:  score × 0.75  (aprovação incerta)
  Se eligibility_score >= 0.7: sem penalidade

Retorno: lista ordenada por score (decrescente)
```

**Regra de não-recomendação:**
Se o `net_gain_expected` do melhor cartão for negativo, `recommendation_type = KEEP_CURRENT`.

**Regra de elegibilidade mínima:**
Se o melhor cartão tiver `eligibility_score < 0.4`, o ranking promove o próximo cartão com `eligibility_score >= 0.6` como recomendação principal, mesmo que o retorno seja ligeiramente menor. Não adianta recomendar o cartão perfeito se o usuário provavelmente não vai conseguir a aprovação.

---

### `validators/input_validator.py` — InputValidator

Valida `OptimizationRequest` com regras de negócio:

| Regra | Condição | Erro |
|---|---|---|
| R1 | `user_id` não vazio | `user_id é obrigatório` |
| R2 | `safe_to_spend` ≥ 0 se fornecido | `safe_to_spend não pode ser negativo` |
| R3 | `monthly_income` > 0 se fornecido | `renda mensal deve ser positiva` |
| R4 | Pelo menos um dos dois informado | `informe safe_to_spend ou monthly_income` |

---

### `validators/liquidity_checker.py` — LiquidityChecker

Classifica o risco da anuidade para o caixa do usuário:

| Condição | Nível |
|---|---|
| `liquidity_impact > 0.5` | CRITICAL |
| `liquidity_impact > 0.25` | HIGH |
| `liquidity_impact > 0.10` | WARNING |
| `liquidity_impact ≤ 0.10` | SAFE |

---

### `services/optimizer_service.py` — OptimizerService

Ponto único de entrada. Orquestra na ordem:

```
1. InputValidator.validate(request)
2. ConsumptionProfiler.build(transactions_df, shadow_invoices_df)
3. CardKnowledgeBase.load() → filter_eligible(profile)
4. CardSimulator.simulate(card, profile, safe_to_spend)  [para cada cartão]
5. LiquidityChecker.check(result)                        [para cada resultado]
6. CardRanking.rank(results, profile)
7. Determinar RecommendationType
8. Consolidar warnings
9. Persistir em optimization_reports (DuckDB)
10. Retornar OptimizationReport
```

---

### `api/v1/routes/optimizer.py` — Endpoints REST

```
POST  /api/v1/optimizer/analyze/{user_id}
      Análise completa. Rota responsável por:
        1. Buscar safe_to_spend e shadow_invoices via F1 (NexaRunner)
        2. Buscar transactions_clean do DuckDB
        3. Chamar OptimizerService
        4. Retornar OptimizationReport

GET   /api/v1/optimizer/reports/{user_id}
      Lista relatórios anteriores do usuário (DuckDB)

GET   /api/v1/optimizer/reports/{report_id}/detail
      Relatório específico com todos os cartões simulados

GET   /api/v1/optimizer/cards
      Lista todos os cartões disponíveis na base de conhecimento

GET   /api/v1/optimizer/health
      Health check do módulo
```

---

### `db/queries/optimizer_queries.py` — Queries DuckDB

```python
save_optimization_report(report: OptimizationReport) -> None
get_optimization_reports(user_id: str) -> list[dict]
get_optimization_report_by_id(report_id: str) -> dict | None
```

---

## 5. Banco de dados — tabelas DuckDB

### `optimization_reports`

```sql
CREATE TABLE optimization_reports (
    report_id               VARCHAR PRIMARY KEY,
    user_id                 VARCHAR NOT NULL,
    generated_at            VARCHAR NOT NULL,           -- ISO 8601
    recommendation_type     VARCHAR NOT NULL,           -- SWITCH_RECOMMENDED | KEEP_CURRENT | INSUFFICIENT_DATA
    best_card_id            VARCHAR,
    best_card_name          VARCHAR,
    net_gain_expected       DOUBLE,
    net_gain_min            DOUBLE,
    net_gain_max            DOUBLE,
    confidence_score        DOUBLE,
    liquidity_impact        DOUBLE,
    liquidity_risk          VARCHAR,
    data_sources            VARCHAR,                    -- JSON array serializado
    strategy_text           VARCHAR,
    warnings                VARCHAR,                    -- JSON array serializado
    full_report_json        VARCHAR                     -- OptimizationReport completo serializado
);
```

---

## 6. Base de conhecimento de cartões

### Schema de cada cartão (`data/cards/knowledge_cards.json`)

```json
{
  "card_id": "nubank-ultravioleta",
  "name": "Nubank Ultravioleta",
  "issuer": "Nubank",
  "flag": "MASTERCARD",
  "card_type": "POINTS",
  "public_target": "alta renda",
  "min_income": 200000,
  "requires_proof_of_income": false,
  "secured_card": false,
  "prepaid": false,
  "consigned": false,
  "base_annuity": 2856.00,
  "waiver_rules": {
    "type": "spend_threshold",
    "threshold": 200000,
    "description": "Anuidade isenta gastando R$ 200k/ano"
  },
  "cashback_pct": null,
  "cashback_cap": null,
  "cashback_categories": [],
  "points_per_brl": 2.0,
  "points_currency": "pontos",
  "points_conversion_rate": 16.0,
  "benefit_tags": ["TRAVEL", "LOUNGE", "INSURANCE", "INTERNACIONAL", "PREMIUM"],
  "benefits_detail": [
    "Acesso a salas VIP em aeroportos (LoungeKey)",
    "Seguro viagem internacional",
    "Concierge 24h",
    "Mastercard Black benefits"
  ],
  "revolving_interest_monthly": 0.1599,
  "installment_interest_monthly": 0.0299,
  "data_trust_score": 0.9,
  "request_link": "https://nubank.com.br/ultravioleta",
  "last_updated": "2026-02-01"
}
```

### Campos obrigatórios (todos os cartões devem ter)

| Campo | Tipo | Descrição |
|---|---|---|
| `card_id` | string | ID interno único (slug) |
| `name` | string | Nome comercial |
| `issuer` | string | Banco/fintech emissor |
| `flag` | enum | `VISA` / `MASTERCARD` / `ELO` / `AMEX` / `HIPERCARD` |
| `card_type` | enum | `POINTS` / `CASHBACK` / `INVESTBACK` |
| `public_target` | string | Público-alvo (ex: "baixa renda", "alta renda", "negativado") |
| `min_income` | float | Renda mínima anual (0 se sem restrição) |
| `requires_proof_of_income` | bool | Exige comprovante de renda |
| `secured_card` | bool | Cartão garantido (depósito) |
| `prepaid` | bool | Pré-pago |
| `consigned` | bool | Consignado |
| `base_annuity` | float | Anuidade cheia em R$ (0 se isento) |
| `waiver_rules` | object | Regras de isenção (ver abaixo) |
| `cashback_pct` | float\|null | Percentual de cashback (null se não aplicável) |
| `cashback_cap` | float\|null | Teto mensal do cashback em R$ |
| `cashback_categories` | array | Categorias com cashback diferenciado |
| `points_per_brl` | float\|null | Pontos por R$ gasto (null se não aplicável) |
| `points_currency` | string | Nome da moeda de pontos (ex: "pontos", "milhas", "cashback") |
| `points_conversion_rate` | float | R$ por 1.000 pontos/milhas |
| `benefit_tags` | array | Tags de benefícios (ver enum `BenefitTag`) |
| `benefits_detail` | array | Descrição textual dos benefícios |
| `revolving_interest_monthly` | float | Juros rotativo mensal (ex: 0.1599 = 15,99%) |
| `installment_interest_monthly` | float\|null | Juros parcelamento de fatura |
| `data_trust_score` | float | Confiança nos dados (0–1). 1.0 = dados verificados oficialmente |
| `request_link` | string\|null | URL de solicitação do cartão |
| `last_updated` | string | Data da última verificação das regras |

### `waiver_rules` — formatos suportados

```json
// Isenção por gasto mínimo anual
{ "type": "spend_threshold", "threshold": 200000, "description": "..." }

// Sempre isento
{ "type": "always_free", "description": "Sem anuidade" }

// Sem isenção
{ "type": "none", "description": "Anuidade sempre cobrada" }

// Isenção por número de transações
{ "type": "transaction_count", "count_monthly": 5, "description": "..." }
```

### Seed inicial — 8 cartões para o MVP

| Card ID | Nome | Tipo | Anuidade | Mínima p/ Isenção |
|---|---|---|---|---|
| `nubank-ultravioleta` | Nubank Ultravioleta | POINTS | R$ 2.856 | R$ 200k/ano |
| `nubank-roxinho` | Nubank Standard | POINTS | R$ 0 | sempre isento |
| `itau-personnalite` | Itaú Personnalité Visa Infinite | POINTS | R$ 5.544 | R$ 250k/ano |
| `c6-carbon` | C6 Carbon | POINTS | R$ 1.080 | R$ 100k/ano |
| `inter-black` | Inter Black | CASHBACK | R$ 0 | sempre isento |
| `xp-visa-infinite` | XP Visa Infinite | POINTS | R$ 2.388 | R$ 144k/ano |
| `picpay-card` | PicPay Card | CASHBACK | R$ 0 | sempre isento |
| `next-visa` | Next Visa | CASHBACK | R$ 0 | sempre isento |

> Todos os campos acima devem ser preenchidos com valores reais verificados antes de colocar em produção. `data_trust_score` começa em 0.7 para cartões cujos dados foram coletados manualmente.

---

## 7. Perfil do cliente e elegibilidade

### Por que o perfil é central

O sistema nunca recomenda um cartão no vácuo. Cada recomendação parte de três perguntas:

1. **O usuário consegue esse cartão?** — elegibilidade estimada por renda, estabilidade financeira e relacionamento com o emissor
2. **O cartão faz sentido para o padrão de consumo?** — matching entre categorias de gasto e benefícios do cartão
3. **O ganho é real, não teórico?** — cálculo ancorado no gasto observado (débito + crédito atual), não em médias genéricas

### Fontes de dados do perfil usadas na recomendação

| Dado do perfil | De onde vem | Usado para |
|---|---|---|
| `monthly_avg_spend` | `transactions_clean` (F1) | Base de cálculo de pontos/cashback |
| `spend_by_category` | `transactions_clean` (F1) | Matching com cashback por categoria |
| `estimated_monthly_income` | Créditos detectados pela F1 | Filtro de elegibilidade por renda mínima |
| `international_spend_monthly` | `transactions_clean` (F1) | Bônus para cartões INTERNACIONAL |
| `travel_spend_monthly` | `transactions_clean` (F1) | Bônus para cartões com LOUNGE |
| `spending_stability` | Variância dos gastos mensais | Fator no `eligibility_score` |
| `committed_percentage` | `shadow_invoice_events` (F1) | Penalidade no `confidence_score` |
| `safe_to_spend` | `daily_forecast` (F1) | Cálculo de `liquidity_impact` |

### Lógica de elegibilidade

O `eligibility_score` (0.0–1.0) é calculado no `card_loader.py` e representa a probabilidade estimada de aprovação. É diferente do `confidence_score` — este mede a qualidade dos dados; aquele mede o fit do usuário com o produto.

```
Hard filter (remove da lista):
  → renda anual < min_income do cartão

Score contínuo para cartões que passam no hard filter:
  income_ratio = renda_anual / min_income
    >= 2.0  →  0.95  (renda muito acima)
    >= 1.5  →  0.80
    >= 1.2  →  0.70
    >= 1.0  →  0.60  (renda no limite — aprovação provável, não garantida)

  × spending_stability (histórico estável = menos risco de inadimplência)
  + 0.10 se já tem produto do mesmo emissor detectado em transactions
  = eligibility_score (máximo 1.0)
```

**Regras de exibição ao usuário:**

| Faixa | Texto exibido |
|---|---|
| >= 0.80 | "Alta chance de aprovação" |
| 0.60–0.79 | "Boa chance de aprovação" |
| 0.40–0.59 | "Aprovação possível — verifique os requisitos" |
| < 0.40 | Cartão removido do ranking principal (pode aparecer em "outros") |

### Matching perfil-cartão

O `profile_match_reasons` é gerado pelo simulador cruzando o `UserProfile` com os `benefit_tags` e regras do cartão. Exemplos de matching automático:

```python
# Gasto em alimentação + cashback diferenciado nessa categoria
if "alimentacao" in top_categories and card.cashback_categories includes "alimentacao":
    reasons.append(f"Seu gasto de R$ {spend_alimentacao}/mês em alimentação rende "
                   f"{cashback_pct_categoria}% de cashback = R$ {valor}/ano")

# Volume total garante isenção de anuidade
if gasto_anual_projetado >= waiver_threshold:
    reasons.append(f"Seu gasto anual projetado de R$ {gasto_anual:.0f} isenta a "
                   f"anuidade de R$ {base_annuity:.0f}")

# Gasto internacional expressivo
if profile.international_spend_monthly > 300 and "INTERNACIONAL" in benefit_tags:
    reasons.append(f"Seu gasto de R$ {international}/mês no exterior se beneficia "
                   f"do câmbio diferenciado e zero IOF deste cartão")

# Frequência de viagens
if profile.travel_spend_monthly > 600 and "LOUNGE" in benefit_tags:
    reasons.append(f"Com seus gastos em viagens, o acesso a salas VIP incluso "
                   f"pode valer mais de R$ {lounge_value_estimated}/ano")
```

---

## 8. Fórmulas e cálculos

### Valor anual dos pontos

```
# Para cartões POINTS/MILHAS
pontos_gerados = gasto_anual × points_per_brl
valor_pontos   = (pontos_gerados / 1000) × points_conversion_rate

# Para cartões CASHBACK
valor_cashback = gasto_anual × cashback_pct
if cashback_cap:
    valor_cashback = min(valor_cashback, cashback_cap × 12)
```

### Ganho líquido

```
net_gain = valor_beneficio - annuity_effective

# Cenários (usando fator de variação de ±20% no gasto)
net_gain_min      = calcular(gasto × 0.8) - annuity_effective
net_gain_expected = calcular(gasto × 1.0) - annuity_effective
net_gain_max      = calcular(gasto × 1.2) - annuity_effective
```

### Impacto de liquidez

```
# Anuidade mensal proporcional vs margem diária × 30
annuity_monthly  = annuity_effective / 12
liquidity_impact = annuity_monthly / safe_to_spend
# se safe_to_spend <= 0: liquidity_impact = 1.0 (CRITICAL automático)
```

### Confidence score

```
coverage_weight    = min(data_coverage_months, 6) / 6        # 0.0–1.0
stability_weight   = spending_stability                       # 0.0–1.0 (da UserProfile)
bank_trust_weight  = card.data_trust_score                    # 0.0–1.0

confidence_score = coverage_weight × stability_weight × bank_trust_weight

# Penalidades adicionais:
if data_coverage_months < 2:  confidence_score *= 0.5
if committed_percentage > 80%: confidence_score *= 0.7  # caixa muito comprometido
```

---

## 8. Integração com o Agente (LangGraph)

### Tool a ser criada

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

### Quando o agente usa essa tool

O agente deve acionar `get_card_optimization` quando a pergunta do usuário contiver:
- "melhor cartão"
- "vale a pena trocar de cartão"
- "cartão de crédito"
- "milhas / cashback / pontos"
- "anuidade"

### Formato de resposta ao usuário (strategy_text)

O LLM gera a `strategy_text` com base nos campos estruturados do `OptimizationReport`. A resposta **deve sempre referenciar o gasto real observado** (do `spending_anchor`) como âncora da justificativa, e incluir a avaliação de elegibilidade:

```
Exemplo de resposta esperada:
"Analisando seus dados: você gasta em média R$ 1.800/mês no débito e
R$ 1.400/mês em cartões de crédito — total de R$ 3.200/mês. Com esse
padrão, o cartão X te geraria aproximadamente R$ 480/ano em pontos, com
anuidade isenta (seu gasto anual projetado de R$ 38.400 ultrapassa o
threshold de isenção de R$ 36.000).

Por que vale trocar: você está deixando de ganhar R$ 480/ano com o seu
cartão atual. O cartão X acumula 2 pontos por real gasto — com seus
R$ 3.200/mês, isso equivale a R$ 40/mês em pontos resgatáveis.

Chance de aprovação: alta (sua renda está bem acima do mínimo exigido e
você já tem histórico com o emissor).

No pior cenário (gasto 20% menor) o ganho ainda seria positivo: R$ 384.
Confiança da análise: 82% (baseada em 4 meses de histórico estável)."
```

**Campos que o LLM deve consumir para gerar a justificativa:**
- `spending_anchor` → âncora em valores reais do usuário
- `profile_match_reasons` → por que o cartão se encaixa
- `eligibility_reasons` → por que o usuário consegue (ou pode não conseguir)
- `net_gain_min/expected/max` → faixa de ganho
- `annuity_waived` + `waiver_rules.threshold` → argumento de isenção
- `benefit_highlights` → benefícios específicos ao perfil

---

## 9. Roteiro de implementação

### Passo 2.1 — Base de cartões e modelos (sem dependência de F1)

- [ ] Criar `app/optimizer/models.py` com todos os enums e schemas
- [ ] Criar `data/cards/knowledge_cards.json` com os 8 cartões do seed
- [ ] Criar `app/optimizer/card_loader.py` (load + filter_eligible)
- [ ] Criar `app/db/queries/optimizer_queries.py` + tabela `optimization_reports`
- [ ] Escrever `tests/optimizer/test_card_loader.py`

### Passo 2.2 — Profiler (depende de F1)

- [ ] Criar `app/optimizer/profiler.py` (ConsumptionProfiler)
- [ ] Conectar com `transactions_clean` do DuckDB
- [ ] Conectar com `shadow_invoice_events` da F1
- [ ] Escrever `tests/optimizer/test_profiler.py`

### Passo 2.3 — Simulador e Ranking (depende de Profiler)

- [ ] Criar `app/optimizer/simulator.py` (CardSimulator)
- [ ] Criar `app/optimizer/validators/liquidity_checker.py`
- [ ] Criar `app/optimizer/ranking.py` (CardRanking)
- [ ] Escrever `tests/optimizer/test_simulator.py`
- [ ] Escrever `tests/optimizer/test_ranking.py`
- [ ] Escrever `tests/optimizer/test_liquidity_checker.py`

### Passo 2.4 — Validação e Orquestrador

- [ ] Criar `app/optimizer/validators/input_validator.py`
- [ ] Criar `app/optimizer/services/optimizer_service.py`
- [ ] Escrever `tests/optimizer/test_optimizer_service.py`

### Passo 2.5 — API e Integração

- [ ] Criar `app/api/v1/routes/optimizer.py`
- [ ] Registrar rota no `app/api/v1/router.py`
- [ ] Escrever `tests/optimizer/test_api.py`
- [ ] Atualizar `PRODUCTION_CHECKLIST.md` marcando F2 como iniciado

### Passo 2.6 — Agente (depende do agente LangGraph estar ativo)

- [ ] Criar tool `get_card_optimization(user_id)` em `app/agent/`
- [ ] Adicionar nó ao grafo LangGraph
- [ ] Testar via `POST /chat`

---

## 10. Definition of Done

- [ ] ≥ 8 cartões reais cadastrados com `data_trust_score` verificado
- [ ] Recomendação leva em conta `shadow_invoice_events` na projeção de gasto
- [ ] Resultado sempre inclui faixa (min/expected/max) e `confidence_score`
- [ ] Sistema recomenda `KEEP_CURRENT` quando `net_gain_expected < 0`
- [ ] Sistema recomenda `KEEP_CURRENT` quando `liquidity_risk == CRITICAL`
- [ ] **Todo `CardSimulationResult` inclui `eligibility_score`, `eligibility_reasons`, `profile_match_reasons` e `spending_anchor`**
- [ ] **`strategy_text` referencia sempre o gasto real observado (débito + crédito atual) como âncora da justificativa**
- [ ] **Cartões com `eligibility_score < 0.4` não aparecem como recomendação principal**
- [ ] **`filter_eligible` aplica hard filter de renda + remove cartões já possuídos**
- [ ] **Ranking penaliza cartões com `eligibility_score < 0.7`**
- [ ] Relatórios persistidos no DuckDB
- [ ] Todos os endpoints documentados no Swagger (`/docs`)
- [ ] Chat responde corretamente: `"Qual o melhor cartão para mim?"` com justificativa baseada no gasto real do usuário, chance de aprovação e ganho líquido calculado

---

## 11. Status de implementação

| Componente | Arquivo | Status |
|---|---|---|
| Schemas Pydantic | `app/optimizer/models.py` | Não iniciado |
| CardKnowledgeBase | `app/optimizer/card_loader.py` | Não iniciado |
| ConsumptionProfiler | `app/optimizer/profiler.py` | Não iniciado |
| CardSimulator | `app/optimizer/simulator.py` | Não iniciado |
| CardRanking | `app/optimizer/ranking.py` | Não iniciado |
| InputValidator | `app/optimizer/validators/input_validator.py` | Não iniciado |
| LiquidityChecker | `app/optimizer/validators/liquidity_checker.py` | Não iniciado |
| OptimizerService | `app/optimizer/services/optimizer_service.py` | Não iniciado |
| API Routes | `app/api/v1/routes/optimizer.py` | Não iniciado |
| DB Queries | `app/db/queries/optimizer_queries.py` | Não iniciado |
| Seed de cartões | `data/cards/knowledge_cards.json` | Não iniciado |
| Testes | `tests/optimizer/` | Não iniciado |
| Tool do agente | `app/agent/nodes/` | Não iniciado |

**Progresso:** 0 / 13 componentes
