# Nexa Optimizer — F2: Documentação Completa

> **Feature F2 — Nexa Optimizer**
> Motor de recomendação de cartões de crédito. Analisa o perfil de gastos e renda do usuário para recomendar o cartão (ou portfólio de cartões) que maximiza o retorno financeiro líquido, considerando anuidade, risco de liquidez e perfil de aprovação.

---

## Índice

1. [Visão Geral](#1-visão-geral)
2. [Arquitetura e Estrutura de Arquivos](#2-arquitetura-e-estrutura-de-arquivos)
3. [Fluxo Completo — Passo a Passo](#3-fluxo-completo--passo-a-passo)
   - 3.1 [Entrada da Requisição](#31-entrada-da-requisição)
   - 3.2 [Construção do Perfil de Gastos](#32-construção-do-perfil-de-gastos)
   - 3.3 [Determinação da Renda](#33-determinação-da-renda)
   - 3.4 [Filtragem de Cartões Elegíveis](#34-filtragem-de-cartões-elegíveis)
   - 3.5 [Simulação de Retornos](#35-simulação-de-retornos)
   - 3.6 [Score de Elegibilidade](#36-score-de-elegibilidade)
   - 3.7 [Ranking e Penalidades](#37-ranking-e-penalidades)
   - 3.8 [Geração do Relatório](#38-geração-do-relatório)
4. [Módulo: Profiler](#4-módulo-profiler)
5. [Módulo: CardLoader](#5-módulo-cardloader)
6. [Módulo: Simulator](#6-módulo-simulator)
7. [Módulo: Ranking](#7-módulo-ranking)
8. [Módulo: Validators](#8-módulo-validators)
9. [Features Avançadas](#9-features-avançadas)
   - 9.1 [M2.2 — Estratégia Multi-Cartão](#91-m22--estratégia-multi-cartão)
   - 9.2 [M2.3 — Valoração Dinâmica de Milhas](#92-m23--valoração-dinâmica-de-milhas)
   - 9.3 [M2.4 — Análise de ROI do Cartão Atual](#93-m24--análise-de-roi-do-cartão-atual)
   - 9.4 [M2.5 — Cashback por Categoria](#94-m25--cashback-por-categoria)
   - 9.5 [M2.6 — Rastreamento de Promoções de Transferência](#95-m26--rastreamento-de-promoções-de-transferência)
   - 9.6 [Custo de Oportunidade](#96-custo-de-oportunidade)
10. [Output — OptimizationReport](#10-output--optimizationreport)
11. [API REST — Endpoints](#11-api-rest--endpoints)
12. [Base de Conhecimento de Cartões](#12-base-de-conhecimento-de-cartões)
13. [Persistência — PostgreSQL](#13-persistência--postgresql)
14. [Integração com o Agente LLM](#14-integração-com-o-agente-llm)
15. [Constantes e Parâmetros de Configuração](#15-constantes-e-parâmetros-de-configuração)
16. [Testes](#16-testes)

---

## 1. Visão Geral

O Optimizer resolve a pergunta: **"Qual cartão de crédito rende mais para o meu perfil de gastos?"**

Para isso, ele:

- Analisa as transações reais dos últimos 90 dias do usuário
- Classifica o perfil de renda (CLT, PJ, misto, variável)
- Filtra os cartões para os quais o usuário tem renda mínima suficiente
- Simula o retorno líquido (pontos/cashback − anuidade) em 3 cenários (pessimista, realista, otimista)
- Penaliza cartões que comprometem demasiadamente a margem financeira do usuário
- Retorna ranking ordenado com explicações e alertas contextuais

O resultado é persistido no PostgreSQL e exposto via REST API, além de estar disponível como ferramenta do agente conversacional.

---

## 2. Arquitetura e Estrutura de Arquivos

```
backend/
├── app/
│   └── optimizer/
│       ├── __init__.py
│       ├── router.py                    # Endpoints REST (FastAPI)
│       ├── models.py                    # Schemas Pydantic (input/output)
│       ├── models_orm.py                # Modelo ORM SQLAlchemy
│       ├── queries.py                   # Persistência PostgreSQL
│       ├── profiler.py                  # Análise do perfil de gastos
│       ├── card_loader.py               # Carregamento e filtragem de cartões
│       ├── simulator.py                 # Cálculo de retorno por cartão
│       ├── ranking.py                   # Ordenação e ajuste de scores
│       ├── miles_valuator.py            # Valoração dinâmica de milhas (M2.3)
│       ├── multi_card_strategy.py       # Portfólio multi-cartão (M2.2)
│       ├── opportunity_cost.py          # Ganho perdido com cartão atual
│       ├── promotion_tracker.py         # Promoções de transferência (M2.6)
│       ├── validators/
│       │   ├── input_validator.py       # Validação de negócio da requisição
│       │   └── liquidity_checker.py     # Classificação de risco de anuidade
│       └── services/
│           └── optimizer_service.py     # Orquestrador principal
│
├── data/cards/
│   ├── knowledge_cards.json             # Base de dados de cartões
│   ├── miles_valuation.json             # Taxas de conversão por programa
│   └── transfer_promotions.json         # Promoções de transferência ativas
│
├── tests/optimizer/
│   ├── test_api.py
│   ├── test_api_getters.py
│   ├── test_card_loader.py
│   ├── test_input_validator.py
│   ├── test_liquidity_checker.py
│   ├── test_m2_5_category_cashback.py
│   ├── test_m2_6_promotions.py
│   ├── test_optimizer_service.py
│   ├── test_profiler.py
│   ├── test_ranking.py
│   ├── test_roi.py
│   └── test_simulator.py
│
└── app/agent/tools/
    └── get_card_optimization.py         # Integração com agente LLM
```

**Dependências externas do módulo:**
- `forecast/etl/income_profiler.py` — classificação de padrão de renda
- `forecast/` — `safe_to_spend` para avaliação de risco de liquidez

---

## 3. Fluxo Completo — Passo a Passo

```
POST /optimizer/analyze
         │
         ▼
┌─────────────────────┐
│  InputValidator      │  Valida regras de negócio (R1–R4)
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  ConsumptionProfiler │  Analisa transações dos últimos 90 dias
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Determinação de     │  Hierarquia: declarada → estimada → fallback
│  Renda Anual         │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  CardKnowledgeBase   │  Filtra cartões elegíveis (renda, posse, tipo)
│  filter_eligible()   │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  CardSimulator       │  Simula retorno líquido em 3 cenários por cartão
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  CardKnowledgeBase   │  Calcula score de aprovação (0.0–1.0)
│  compute_eligibility │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  CardRanking         │  Ordena por retorno ajustado por risco e confiança
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  _build_report()     │  Monta OptimizationReport com alertas e tipo de
│                      │  recomendação; persiste no PostgreSQL
└────────┬────────────┘
         │
         ▼
      OptimizationReport
```

### 3.1 Entrada da Requisição

**Schema:** `OptimizationRequest` ([models.py](../backend/app/optimizer/models.py))

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `user_id` | str | Sim | Identificador do usuário |
| `current_cards` | list[str] | Não | IDs dos cartões já possuídos |
| `safe_to_spend` | float | Condicional | Margem mensal disponível em R$ |
| `monthly_income` | float | Condicional | Renda mensal declarada em R$ |

> Pelo menos um entre `safe_to_spend` ou `monthly_income` deve ser informado (Regra R4).

### 3.2 Construção do Perfil de Gastos

Executado por `ConsumptionProfiler.build()` em [profiler.py](../backend/app/optimizer/profiler.py).

**Janela de análise:** últimos 90 dias (`_WINDOW_DAYS = 90`)

**Etapas:**
1. Filtra transações para os últimos 90 dias
2. Exclui transações em contexto PJ
3. Calcula cobertura em meses (`data_coverage_months`)
4. Computa média mensal de gastos
5. Calcula estabilidade de gastos (coeficiente de variação, 0.0–1.0)
6. Desmembra gastos por categoria
7. Desmembra gastos por fonte (débito vs. crédito)
8. Detecta gastos internacionais via regex (`_INTERNATIONAL_PATTERN`)
9. Identifica gastos em viagem (`_TRAVEL_CATEGORIES`: Lazer, Transporte)
10. Estima renda mensal a partir dos créditos
11. Calcula percentual comprometido com faturas recorrentes (shadow invoices)
12. Classifica padrão de renda via `IncomeProfiler`

**Output: `UserProfile`**

| Campo | Descrição |
|---|---|
| `monthly_avg_spend` | Média mensal de gastos em R$ |
| `spending_stability` | Score 0.0–1.0 (1.0 = muito estável) |
| `spend_by_category` | Dict: categoria → média mensal R$ |
| `spend_by_source` | Dict: débito/crédito → percentual |
| `international_spend_monthly` | Média mensal de gastos internacionais |
| `travel_spend_monthly` | Média mensal em categorias de viagem |
| `income_profile` | `IncomeProfile` com padrão, estabilidade e confiança |
| `data_coverage_months` | Meses de histórico disponíveis |
| `committed_percentage` | % da renda comprometida com despesas fixas |

### 3.3 Determinação da Renda

Lógica em [optimizer_service.py](../backend/app/optimizer/services/optimizer_service.py) (linhas 143–166):

```
Prioridade 1: request.monthly_income × 12   (declarada pelo usuário)
Prioridade 2: income_profile.monthly_net_income × 12  (se confiança ≥ 0.5)
Prioridade 3: profile.estimated_monthly_income × 12  (fallback — soma bruta de créditos)
```

### 3.4 Filtragem de Cartões Elegíveis

`CardKnowledgeBase.filter_eligible()` em [card_loader.py](../backend/app/optimizer/card_loader.py):

**Filtros aplicados:**
- Remove cartões já possuídos pelo usuário
- Exclui se `annual_income < card.min_income`
- Remove cartões garantidos/consignados se houver renda suficiente para cartões convencionais
- Remove consignados por padrão (pode ser desativado via parâmetro)

### 3.5 Simulação de Retornos

`CardSimulator.simulate()` em [simulator.py](../backend/app/optimizer/simulator.py):

**3 cenários por cartão:**

| Cenário | Multiplicador de gasto |
|---|---|
| `min` | 0.8× (pessimista) |
| `expected` | 1.0× (realista) |
| `max` | 1.2× (otimista) |

**Por cenário, calcula:**

1. **Anuidade efetiva** — Zero se `always_free` ou se limiar de isenção for atingido
2. **Valor do benefício:**
   - Cartões POINTS com `loyalty_program`: usa `MilesValuator` para taxa dinâmica
   - Cartões POINTS sem programa: usa `points_conversion_rate` fixo
   - Cartões CASHBACK com `cashback_categories` (M2.5): cashback por categoria com teto
   - Cartões CASHBACK simples: `cashback_pct` × gasto anual
3. **Ganho líquido** = `benefit_value − annuity_effective`
4. **Impacto de liquidez** = `(annuity_effective / 12) / safe_to_spend`
5. **Risco de liquidez** (via `LiquidityChecker`):
   - `CRITICAL`: > 50% da margem
   - `HIGH`: > 25%
   - `WARNING`: > 10%
   - `SAFE`: ≤ 10%
6. **Score de confiança:**
   - Base: `(coverage_months/6) × spending_stability × card.data_trust_score`
   - Penalidade ×0.5 se `coverage_months < 2`
   - Penalidade ×0.7 se `committed_percentage > 0.8`
   - Penalidade ×0.85 se `income_stability < 0.5` (renda variável)

### 3.6 Score de Elegibilidade

`CardKnowledgeBase.compute_eligibility_score()` em [card_loader.py](../backend/app/optimizer/card_loader.py):

**Componentes:**

| Fator de Renda | Condição | Score base |
|---|---|---|
| Excelente | ≥ 2.0× renda mínima | 0.95 |
| Bom | ≥ 1.5× renda mínima | 0.80 |
| Suficiente | ≥ 1.2× renda mínima | 0.70 |
| No limite | ≥ 1.0× renda mínima | 0.60 |

**Ajustes:**
- **Penalidade PJ instável** (MI.3): se renda PJ/MISTO e estabilidade < 0.5 → ×0.85
- **Score final base:** `income_factor × spending_stability`
- **Bônus de relacionamento bancário:** +0.10 se emissor detectado nas transações

### 3.7 Ranking e Penalidades

`CardRanking.rank()` em [ranking.py](../backend/app/optimizer/ranking.py):

**Fórmula de score ajustado:**

```
score = net_gain_expected
      − (|net_gain| × liquidity_penalty[risk_level])
      − (max(0, 0.4 − confidence_score) × net_gain × 0.5)   # penalidade baixa confiança
      + benefits_bonus   # bônus por benefícios relevantes ao perfil
      × eligibility_score   # multiplicador de aprovação
```

**Penalidades de liquidez:**

| Risco | Penalidade |
|---|---|
| CRITICAL | −80% do ganho |
| HIGH | −40% do ganho |
| WARNING | −10% do ganho |
| SAFE | 0% |

**Bônus de benefícios:**

| Condição | Bônus anual |
|---|---|
| Tag INTERNACIONAL + gasto internacional ≥ R$500/mês | +R$200 |
| Tag LOUNGE + gasto viagem ≥ R$800/mês | +R$300 |

**Regra de promoção pós-ordenação:** Se o 1º colocado tem `eligibility_score < 0.4` e existe outro cartão com score ≥ 0.6, esse cartão é promovido ao topo.

### 3.8 Geração do Relatório

`_build_report()` em [optimizer_service.py](../backend/app/optimizer/services/optimizer_service.py):

**Alertas gerados:**
- `data_coverage_months < 2` → "Dados insuficientes para projeção confiável"
- `safe_to_spend` ausente → "Risco de anuidade não avaliado com precisão"
- `monthly_income` ausente E confiança de renda < 0.5 → "Baixa confiança na estimativa de renda"

**Tipo de recomendação:**

| Condição | `recommendation_type` |
|---|---|
| Melhor cartão com `net_gain_expected ≤ 0` | `KEEP_CURRENT` |
| Pelo menos um cartão com `net_gain > 0` | `SWITCH_RECOMMENDED` |
| Nenhum cartão elegível encontrado | `INSUFFICIENT_DATA` |

---

## 4. Módulo: Profiler

**Arquivo:** [profiler.py](../backend/app/optimizer/profiler.py)

`ConsumptionProfiler` recebe DataFrames de transações e shadow invoices. Os métodos privados principais:

| Método | Descrição |
|---|---|
| `_coverage_months()` | Quantos meses de histórico há (mín. 0.5, máx. real) |
| `_monthly_expense_totals()` | Série temporal de gastos mensais |
| `_spend_by_category()` | Média mensal por categoria de transação |
| `_spend_by_source()` | Split débito vs. crédito |
| `_international_spend()` | Detecta transações em moeda estrangeira |
| `_travel_spend()` | Soma categorias de viagem |
| `_monthly_income()` | Estima renda a partir dos créditos |
| `_committed_percentage()` | % de renda comprometida com shadow invoices |

---

## 5. Módulo: CardLoader

**Arquivo:** [card_loader.py](../backend/app/optimizer/card_loader.py)

Carrega `knowledge_cards.json` e expõe duas operações principais:

- `filter_eligible(user_profile, annual_income, current_cards, ...)` → lista de `CardRecord` filtrados
- `compute_eligibility_score(card, annual_income, profile, issuers)` → `(float, list[str])`

**Estrutura `CardRecord`:**

| Campo | Tipo | Descrição |
|---|---|---|
| `card_id` | str | Identificador único |
| `name` | str | Nome do cartão |
| `issuer` | str | Emissor (banco) |
| `flag` | str | Bandeira: VISA, MC, ELO, AMEX |
| `card_type` | enum | POINTS \| CASHBACK \| INVESTBACK |
| `min_income` | float | Renda mínima anual exigida (R$) |
| `base_annuity` | float | Anuidade base (R$/ano) |
| `waiver_rules` | obj | Regras de isenção (tipo + limiar) |
| `points_per_brl` | float | Pontos por real gasto |
| `loyalty_program` | str | Programa (livelo, smiles, nu_pontos…) |
| `points_conversion_rate` | float | R$ por 1.000 pontos (fallback) |
| `cashback_pct` | float | % de cashback flat |
| `cashback_categories` | list | Regras por categoria (M2.5) |
| `benefit_tags` | list | TRAVEL, CASHBACK, LOUNGE, INSURANCE, INTERNACIONAL, PREMIUM |
| `data_trust_score` | float | Confiança nos dados do cartão (0.0–1.0) |

---

## 6. Módulo: Simulator

**Arquivo:** [simulator.py](../backend/app/optimizer/simulator.py)

`CardSimulator.simulate(card, profile, safe_to_spend)` retorna `CardSimulationResult`:

| Campo | Descrição |
|---|---|
| `card_id` | ID do cartão |
| `card_name` | Nome do cartão |
| `scenarios` | Dict com resultados para `min`, `expected`, `max` |
| `net_gain_expected` | Ganho líquido no cenário esperado (R$/ano) |
| `annuity_effective` | Anuidade após aplicação de regras de isenção |
| `liquidity_risk` | Enum: SAFE / WARNING / HIGH / CRITICAL |
| `liquidity_impact` | Fração da margem mensal consumida pela anuidade |
| `confidence_score` | Score composto 0.0–1.0 |
| `explanation` | Texto explicativo para o usuário |
| `reasoning` | Detalhamento técnico dos cálculos |

---

## 7. Módulo: Ranking

**Arquivo:** [ranking.py](../backend/app/optimizer/ranking.py)

`CardRanking.rank(simulations, profile)` aplica os ajustes de score e retorna lista ordenada de `CardSimulationResult`. Opera sobre a lista completa com uma passagem única, depois aplica a regra de promoção pós-sort.

---

## 8. Módulo: Validators

### InputValidator

**Arquivo:** [validators/input_validator.py](../backend/app/optimizer/validators/input_validator.py)

Regras de negócio validadas:

| Regra | Condição | Erro |
|---|---|---|
| R1 | `user_id` não pode ser vazio | ValueError |
| R2 | `safe_to_spend >= 0` se informado | ValueError |
| R3 | `monthly_income > 0` se informado | ValueError |
| R4 | Pelo menos um de `safe_to_spend` ou `monthly_income` deve ser informado | ValueError |

### LiquidityChecker

**Arquivo:** [validators/liquidity_checker.py](../backend/app/optimizer/validators/liquidity_checker.py)

Classifica o risco baseado em `liquidity_impact = (annuity/12) / safe_to_spend`:

| Threshold | Classificação |
|---|---|
| > 0.50 | CRITICAL |
| > 0.25 | HIGH |
| > 0.10 | WARNING |
| ≤ 0.10 | SAFE |

---

## 9. Features Avançadas

### 9.1 M2.2 — Estratégia Multi-Cartão

**Arquivo:** [multi_card_strategy.py](../backend/app/optimizer/multi_card_strategy.py)

Algoritmo guloso para encontrar combinação ótima de 1–5 cartões:

1. Para cada categoria de gasto, encontra o cartão com melhor retorno
2. Consolida até `max_cards` mantendo os maiores contribuidores
3. Reatribui categorias dos cartões descartados
4. Remove cartões com gasto direcionado < R$200/mês
5. Calcula retorno total do portfólio vs. melhor cartão único

**Endpoint:** `GET /optimizer/portfolio/{user_id}`

### 9.2 M2.3 — Valoração Dinâmica de Milhas

**Arquivo:** [miles_valuator.py](../backend/app/optimizer/miles_valuator.py)

Usa `miles_valuation.json` para aplicar taxas de conversão dependentes do cenário:

| Cenário | Tipo de resgate | Valor |
|---|---|---|
| pessimista | Produtos/cashback | Mais baixo |
| esperado | Transferência para parceiro aéreo | Médio |
| otimista | Transferência em promoção com bônus | Mais alto |

### 9.3 M2.4 — Análise de ROI do Cartão Atual

**Endpoint:** `GET /optimizer/roi/{card_id}`

Calcula:
- Anuidade paga anualmente
- Valor de recompensa gerado com o gasto atual
- ROI líquido (recompensa − anuidade)
- Meses para atingir limiar de isenção
- **Veredicto:** `VALE_A_PENA` | `MARGINAL` | `NAO_VALE`

### 9.4 M2.5 — Cashback por Categoria

**Implementação:** [simulator.py](../backend/app/optimizer/simulator.py) linhas 177–237

Para cartões com `cashback_categories`:
- Cada categoria tem percentual próprio de cashback
- Categorias sem regra usam `cashback_default_pct`
- Respeita tetos mensais por categoria
- Escala pelo percentual real da distribuição de gastos do usuário

### 9.5 M2.6 — Rastreamento de Promoções de Transferência

**Arquivo:** [promotion_tracker.py](../backend/app/optimizer/promotion_tracker.py)

Identifica promoções ativas (ex.: Livelo → LATAM com 80% de bônus):
- Rastreia elegibilidade por cartão
- Calcula valor extra vs. taxa normal
- Endpoints:
  - `GET /optimizer/promotions` — Lista todas as promoções
  - `GET /optimizer/promotions/opportunities` — Oportunidades do usuário

### 9.6 Custo de Oportunidade

**Arquivo:** [opportunity_cost.py](../backend/app/optimizer/opportunity_cost.py)

Mostra quanto o usuário deixou de ganhar:

> "Nos últimos 3 meses, você gastou R$9.600 com Nubank (0,5 pts/R$) = R$48.
> Com o C6 Carbon (2,0 pts/R$) teria ganho R$192.
> **Diferença: R$144 deixados na mesa.**"

**Endpoint:** `GET /optimizer/opportunity-cost`

---

## 10. Output — OptimizationReport

**Schema:** [models.py](../backend/app/optimizer/models.py)

| Campo | Tipo | Descrição |
|---|---|---|
| `report_id` | UUID | Identificador único do relatório |
| `user_id` | str | Usuário analisado |
| `best_card` | CardSimulationResult | Cartão mais rentável |
| `all_cards` | list[CardSimulationResult] | Ranking completo |
| `recommendation_type` | enum | SWITCH_RECOMMENDED \| KEEP_CURRENT \| INSUFFICIENT_DATA |
| `strategy_text` | str | Resumo legível para o usuário |
| `warnings` | list[str] | Alertas sobre qualidade dos dados ou riscos |
| `created_at` | datetime | Timestamp de geração |

---

## 11. API REST — Endpoints

**Prefixo:** `/optimizer`

| Método | Endpoint | Descrição |
|---|---|---|
| `POST` | `/analyze` | Análise principal — retorna OptimizationReport |
| `GET` | `/reports/{user_id}` | Histórico de relatórios do usuário |
| `GET` | `/reports/{report_id}/detail` | Detalhes completos de um relatório |
| `GET` | `/cards` | Lista todos os cartões da base de conhecimento |
| `GET` | `/opportunity-cost` | Calcula ganho perdido com cartão atual |
| `GET` | `/portfolio/{user_id}` | Estratégia multi-cartão (M2.2) |
| `GET` | `/roi/{card_id}` | ROI do cartão atual (M2.4) |
| `GET` | `/promotions` | Lista promoções de transferência (M2.6) |
| `GET` | `/promotions/opportunities` | Oportunidades de promoção do usuário |
| `GET` | `/health` | Health check |

---

## 12. Base de Conhecimento de Cartões

**Arquivo:** [data/cards/knowledge_cards.json](../backend/data/cards/knowledge_cards.json)

JSON com array de objetos `CardRecord`. Cada entrada define todas as características do cartão — taxas, programas de fidelidade, regras de isenção de anuidade e tags de benefício.

**Arquivos de suporte:**

| Arquivo | Conteúdo |
|---|---|
| `miles_valuation.json` | Taxas de conversão por programa e tipo de resgate |
| `transfer_promotions.json` | Promoções ativas com datas de vigência e multiplicadores |

---

## 13. Persistência — PostgreSQL

**ORM:** [models_orm.py](../backend/app/optimizer/models_orm.py)  
**Queries:** [queries.py](../backend/app/optimizer/queries.py)

**Tabela:** `optimization_reports`

| Coluna | Tipo | Descrição |
|---|---|---|
| `report_id` | UUID (PK) | Identificador único |
| `user_id` | str (indexed) | Usuário |
| `best_card_id` | str | ID do cartão recomendado |
| `net_gain_expected` | float | Ganho líquido esperado |
| `confidence_score` | float | Confiança da análise |
| `liquidity_risk` | str | Nível de risco de liquidez |
| `recommendation_type` | str | Tipo da recomendação |
| `report_json` | JSON | Relatório completo serializado |
| `created_at` | datetime | Timestamp |

**Operações:**
- `save_optimization_report()` — Upsert por `report_id`
- `get_optimization_reports(user_id)` — Histórico do usuário
- `get_optimization_report_by_id(report_id)` — Relatório específico

**Migration:** [alembic/versions/a3d5b2d33ffb_add_goals_architect_optimizer_tables.py](../backend/alembic/versions/a3d5b2d33ffb_add_goals_architect_optimizer_tables.py)

---

## 14. Integração com o Agente LLM

**Arquivo:** [agent/tools/get_card_optimization.py](../backend/app/agent/tools/get_card_optimization.py)

Quando o usuário pergunta sobre recomendações de cartão no chat, o agente:

1. Carrega transações reais do pipeline F1
2. Extrai perfil de renda se disponível
3. Obtém `safe_to_spend` do módulo de previsão
4. Chama `OptimizerService.analyze()`
5. Formata saída com contexto de renda para o LLM
6. Retorna top 3 cartões com breakdown de lucratividade

---

## 15. Constantes e Parâmetros de Configuração

| Constante | Arquivo | Valor | Descrição |
|---|---|---|---|
| `_WINDOW_DAYS` | profiler.py | 90 | Janela de análise em dias |
| `_TRAVEL_CATEGORIES` | profiler.py | `{"Lazer", "Transporte"}` | Categorias de viagem |
| `_INTERNATIONAL_PATTERN` | profiler.py | Regex | Detecta gastos internacionais |
| `_SCENARIO_FACTORS` | simulator.py | `{min: 0.8, expected: 1.0, max: 1.2}` | Multiplicadores por cenário |
| `_LIQUIDITY_PENALTY` | ranking.py | `{CRITICAL: 0.8, HIGH: 0.4, WARNING: 0.1, SAFE: 0.0}` | Penalidades de risco |
| `_INTL_SPEND_THRESHOLD` | ranking.py | R$500/mês | Limiar para bônus internacional |
| `_TRAVEL_SPEND_THRESHOLD` | ranking.py | R$800/mês | Limiar para bônus de lounge |
| `_INTL_BONUS` | ranking.py | R$200/ano | Bônus tag INTERNACIONAL |
| `_LOUNGE_BONUS` | ranking.py | R$300/ano | Bônus tag LOUNGE |
| `_PJ_INSTABILITY_THRESHOLD` | card_loader.py | 0.5 | Limiar de estabilidade PJ |
| `_PJ_INSTABILITY_PENALTY` | card_loader.py | 0.85 | Multiplicador penalidade PJ |

---

## 16. Testes

Suite completa em [tests/optimizer/](../backend/tests/optimizer/):

| Arquivo de Teste | Cobertura |
|---|---|
| `test_api.py` | Endpoint principal `/analyze` (happy path + erros) |
| `test_api_getters.py` | Endpoints de leitura (reports, cards, ROI) |
| `test_card_loader.py` | Filtragem de elegibilidade e score |
| `test_input_validator.py` | Regras R1–R4 |
| `test_liquidity_checker.py` | Classificação dos 4 níveis de risco |
| `test_m2_5_category_cashback.py` | Cashback por categoria (M2.5) |
| `test_m2_6_promotions.py` | Promoções de transferência (M2.6) |
| `test_optimizer_service.py` | Orquestração ponta a ponta |
| `test_profiler.py` | Construção do UserProfile |
| `test_ranking.py` | Penalidades e ordenação |
| `test_roi.py` | Análise de ROI do cartão atual (M2.4) |
| `test_simulator.py` | Simulação dos 3 cenários |

Testes E2E adicionais em:
- [tests/test_e2e_full_pipeline.py](../backend/tests/test_e2e_full_pipeline.py)
- [tests/test_e2e_production_ready.py](../backend/tests/test_e2e_production_ready.py)


