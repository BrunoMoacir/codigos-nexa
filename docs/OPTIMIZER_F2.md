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

# Nexa AI — Card Optimizer v2: Arquitetura Completa

> **Confidencial** · Março 2025 · Versão 2.1

---

## Índice

1. [Visão Geral e Princípios](#1-visão-geral-e-princípios)
2. [Diagrama de Fluxo Geral](#2-diagrama-de-fluxo-geral)
3. [Camada 1 — Ingestão e Validação de Dados](#3-camada-1--ingestão-e-validação-de-dados)
4. [Camada 2 — Scoring Multifatorial](#4-camada-2--scoring-multifatorial)
5. [Camada 3 — Motor Anti-Falsos-Positivos](#5-camada-3--motor-anti-falsos-positivos)
6. [Camada 4 — Otimizador de Portfólio Multi-Cartão](#6-camada-4--otimizador-de-portfólio-multi-cartão)
7. [Camada 5 — Geração de Insights Acionáveis](#7-camada-5--geração-de-insights-acionáveis)
8. [Sistema de Valuation Dinâmico de Pontos](#8-sistema-de-valuation-dinâmico-de-pontos)
9. [Catálogo de Cartões — Governança e Manutenção](#9-catálogo-de-cartões--governança-e-manutenção)
10. [Loop de Aprendizado Contínuo](#10-loop-de-aprendizado-contínuo)
11. [Definições de Qualidade e SLAs](#11-definições-de-qualidade-e-slas)
12. [Mapa de Decisões Críticas](#12-mapa-de-decisões-críticas)

---

## 1. Visão Geral e Princípios

### Missão do Card Optimizer

Dado o perfil real de gastos de um usuário, **identificar e ranquear os cartões de crédito que maximizam o retorno líquido mensal**, surfaçando apenas recomendações com alta probabilidade de materialização — sem inflar retornos com benefícios que o usuário não vai usar, pontos com valor otimista ou cartões que ele não conseguirá aprovar.

### Os 5 Princípios Inegociáveis

| # | Princípio | Implicação no código |
|---|-----------|---------------------|
| 1 | **Conservadorismo nos números** | Point values usam P25 do mercado, não média. Benefícios são descontados por utilização real. |
| 2 | **Confiança explícita** | Todo resultado carrega `confidence_score` (0–1). Insights só são surfaçados se `confidence ≥ 0.65`. |
| 3 | **Incerteza quantificada** | Outputs mostram intervalo: "R$40–R$80/mês", não "R$61/mês". |
| 4 | **Suficiência de dados obrigatória** | Menos de 2 meses de histórico → sem recomendação de troca de cartão principal. |
| 5 | **Ganho mínimo para ruído** | Recomendação só aparece se ganho > R$10/mês (≥ 2 semanas de assinatura Nexa). |

---

## 2. Diagrama de Fluxo Geral

```
┌─────────────────────────────────────────────────────────────────────┐
│                         ENTRADAS DO SISTEMA                         │
│                                                                     │
│  Transações Open Finance (F1)  ──►  ETL + Cashflow (Motor Core)     │
│  Renda declarada / IncomeProfiler                                   │
│  safe_to_spend (Forecast F1)                                        │
│  knowledge_cards.json (catálogo de cartões)                         │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  CAMADA 1 — INGESTÃO E VALIDAÇÃO                                    │
│                                                                     │
│  ① BuildUserSpendingProfile   ② BuildIncomeProfile                 │
│  ③ ComputeDataQualityFlags    ④ DetectIssuers                       │
│                                                                     │
│  ✓ Suficiência de dados?   ✓ Renda verificável?   ✓ CV aceitável?   │
│                                                                     │
│  SE FALHAR → retornar "dados insuficientes" com prazo               │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  CAMADA 2 — SCORING MULTIFATORIAL (por cartão)                      │
│                                                                     │
│  ① EligibilityScorer          income_ratio + issuer_bonus           │
│  ② CashbackScorer             category_rates × spend_amounts        │
│  ③ BenefitScorer              profile-aware utilization             │
│  ④ AnnuityScorer              waiver_achievability + liq_impact     │
│  ⑤ ConfidenceScorer           data_trust × coverage × commitment    │
│                                                                     │
│  → CardScore(gross, benefits, fee, net, confidence, eligibility)    │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  CAMADA 3 — MOTOR ANTI-FALSOS-POSITIVOS                             │
│                                                                     │
│  ① ConservativePointValuation  P25 do mercado, não média           │
│  ② BenefitUtilizationFilter    remove benefícios não-utilizáveis   │
│  ③ WaiverAchievabilityCheck    projeção de 12 meses de gasto       │
│  ④ ConfidenceGate              descarta scores com conf < 0.65      │
│  ⑤ LiquidityPenalizer          SAFE/WARNING/HIGH/CRITICAL          │
│  ⑥ MinGainFilter               descarta se ganho líquido < R$10    │
│                                                                     │
│  → EnrichedCardScore (ajustado, com bandas de incerteza)            │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  CAMADA 4 — OTIMIZADOR DE PORTFÓLIO MULTI-CARTÃO                    │
│                                                                     │
│  ① BestCardPerCategory         greedy, O(C × K)                    │
│  ② MarginalCostAnalysis        custo anual vs. ganho marginal       │
│  ③ WalletMinimizer             remove cartões redundantes           │
│  ④ OpportunityCostCalculator   vs. portfólio atual                 │
│                                                                     │
│  → PortfolioOptimization(assignments, wallet, opportunity_cost)     │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  CAMADA 5 — INSIGHTS ACIONÁVEIS                                     │
│                                                                     │
│  ① InsightGenerator            tipifica e prioriza por impacto     │
│  ② IntervalEstimator           gera banda low/mid/high             │
│  ③ EffortClassifier            Baixo / Médio / Alto                │
│  ④ ConfidenceGate final        confidence ≥ 0.65 para surfaçar     │
│                                                                     │
│  → ActionableInsight[] (ranqueados, com R$ e prazo)                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Camada 1 — Ingestão e Validação de Dados

### 3.1 Construção do SpendingProfile

O perfil é construído a partir das transações do F1 (ETL + Cashflow). Regras de qualidade aplicadas antes de qualquer scoring:

```
SpendingProfile
├── monthly_spends[]          Média móvel de 3 meses por categoria
├── total_monthly_brl         Soma de todas as categorias
├── spend_stability_cv        Coef. de variação mensal (std / mean)
├── data_months_covered       Quantos meses completos existem
├── pct_committed             (parcelas + assinaturas) / renda
├── debit_vs_credit_ratio     % de gastos no débito
└── international_spend_pct   % com IOF / descritores USD/EUR
```

**Regra de Suficiência de Dados:**

| Condição | Ação |
|----------|------|
| `data_months_covered ≥ 6` | Score completo, confiança máxima |
| `data_months_covered = 3–5` | Score completo, penalidade ×0.85 |
| `data_months_covered = 2` | Score básico, penalidade ×0.5, sem recomendação de troca de cartão principal |
| `data_months_covered < 2` | Bloqueio total. Retornar `INSUFFICIENT_DATA`. |

**Regra de Estabilidade:**

| `spend_stability_cv` | Interpretação | Penalidade no confidence |
|----------------------|---------------|--------------------------|
| ≤ 0.15 | Gastos muito estáveis | Nenhuma |
| 0.15–0.35 | Variação normal | ×0.90 |
| 0.35–0.60 | Alta variação | ×0.75 |
| > 0.60 | Padrão imprevisível | ×0.60 — desabilitar insights de troca |

### 3.2 Hierarquia de Renda (IncomeProfiler)

```
1º  monthly_income declarada pelo usuário         confiança = 1.00
2º  IncomeProfiler: maior crédito recorrente      confiança = 0.75–0.95
    (CLT: salário fixo; PJ: pagamentos regulares)
3º  Soma bruta de créditos nas transações         confiança = 0.40–0.60
```

**Penalidades por padrão de renda:**

| Padrão | Estabilidade | Penalidade na renda efetiva |
|--------|-------------|----------------------------|
| CLT | qualquer | Nenhuma |
| PJ / MISTO | ≥ 0.5 | Nenhuma |
| PJ / MISTO | < 0.5 | Renda efetiva ×0.85 — usada no filtro de elegibilidade |
| VARIÁVEL | < 0.3 | Renda efetiva ×0.70 — bloquear premium tier |

### 3.3 Detecção de Emissores

Regex aplicado em `transaction.description` para identificar relacionamentos bancários existentes. Emissores detectados recebem `+0.10` no `eligibility_score` do cartão correspondente.

```python
ISSUER_PATTERNS = {
    "nubank":       r"(nubank|nu pagamentos)",
    "inter":        r"(banco inter|bco inter)",
    "itau":         r"(itau|itaú|ibi|credicard)",
    "bradesco":     r"(bradesco|next)",
    "c6":           r"(c6 bank|c6bank)",
    "xp":           r"(xp investimentos|xp cartão)",
    "santander":    r"(santander)",
    "btg":          r"(btg|btg\+)",
    "bancodobrasil": r"(banco do brasil|bb|ourocard)",
}
```

---

## 4. Camada 2 — Scoring Multifatorial

### 4.1 Modelo de Score

O retorno mensal líquido de um cartão é composto por 4 dimensões independentes:

```
net_monthly_return =
    cashback_bruto(categoria_rates × spend_amounts)
  + benefits_value(utilization_adjusted)
  - annuity_cost(waiver_achievable)
  + tag_bonus(perfil_matched)
```

Cada dimensão é calculada de forma independente para permitir debugging granular e rastreabilidade do que gerou cada centavo do score.

### 4.2 CashbackScorer — Cálculo por Categoria

Para cartões com **pontos/milhas**, a taxa efetiva é calculada como:

```
effective_rate(categoria) = pontos_por_real(categoria) × point_value_brl
```

O `point_value_brl` é obtido do `PointValuationEngine` (ver Seção 8), que usa o **P25 do mercado**, não o valor otimista.

Para cartões com **cashback puro**:

```
effective_rate(categoria) = cashback_pct(categoria)
```

**Cálculo do cashback bruto mensal:**

```python
for spend in user.monthly_spends:
    cr = card.best_rate_for(spend.category)
    capped_amount = min(spend.amount, cr.monthly_cap or inf)
    cashback_bruto += capped_amount × cr.effective_rate
```

> **Atenção ao `monthly_cap`:** Alguns cartões têm teto de gasto por categoria para a taxa acelerada (ex: "2% até R$1.000/mês em supermercado"). O cálculo deve respeitar esse teto — ignorá-lo é a fonte mais comum de falso positivo no scoring.

### 4.3 BenefitScorer — Utilização Ajustada ao Perfil

Benefícios teóricos raramente têm utilização 100%. O `ProfileAwareBenefitUtilization` aplica fatores de desconto baseados no comportamento real:

| Tipo de benefício | Condição de utilização real | Fator padrão |
|------------------|----------------------------|--------------|
| Sala VIP (LOUNGE) | `flights_per_year ≥ 4` | `min(flights_per_month, 2) × R$70` |
| Sala VIP (LOUNGE) | `flights_per_year < 4` | **R$0.00** — descartado |
| Seguro viagem | `has_international_spend = True` | ×0.80 |
| Seguro viagem | `has_international_spend = False` | **R$0.00** — descartado |
| Cashback em parceiro | variável | ×0.35 a ×0.70 por perfil |
| Proteção de compras | universal | ×0.40 |
| Concierge 24h | universal | ×0.25 (raramente usado) |
| Seguro celular | `has_smartphone = True` | ×0.50 |

**Regra crítica:** Se o somatório dos benefícios for maior que 40% do retorno total projetado, aplicar um desconto adicional de 15% no total de benefícios. Isso previne que cartões premium com benefícios de luxo dominem o ranking para usuários que não os utilizarão.

### 4.4 AnnuityScorer — Custo Efetivo da Anuidade

```
monthly_annuity_cost = 0   se waiver_achievable = True
                     = base_annuity / 12   caso contrário
```

**Waiver Achievability Analysis:**

```python
def is_waiver_achievable(card, user_profile) -> tuple[bool, float]:
    if card.waiver_spend is None:
        return False, 0.0

    # Projeção de gasto anual baseada nos últimos 3 meses
    trend = compute_spend_trend(user_profile)  # slope mensal
    projected_annual = sum(
        user_profile.total_monthly_brl + trend * m
        for m in range(12)
    )

    gap = card.waiver_spend - projected_annual
    achievability = max(0, 1 - gap / card.waiver_spend)
    return achievability > 0.80, achievability
```

> **Anti-falso-positivo:** A isenção só é marcada como `achievable = True` se a projeção tiver ≥ 80% de probabilidade de alcançar o threshold. Projeções abaixo de 80% reduzem proporcionalmente o benefício da isenção — não é binário.

### 4.5 Elegibility Score

```
eligibility = min(1.0, income_effective / (min_income × 1.5))
            + issuer_bonus (0.10 se emissor detectado)
```

O fator `1.5` cria uma zona de aprovação confortável — recomendamos apenas cartões onde a renda é pelo menos 50% acima do mínimo exigido. Isso reduz drasticamente rejeições após a recomendação.

### 4.6 Confidence Score

```
confidence = data_trust_score
           × data_coverage_penalty    (×0.5 se < 2 meses)
           × commitment_penalty       (×0.7 se > 80% comprometido)
           × income_confidence        (da hierarquia do IncomeProfiler)
           × spend_stability_factor   (×0.75 se CV > 0.35)
```

O `data_trust_score` de cada cartão no catálogo reflete a clareza e estabilidade das regras do produto:
- `1.00` — Nubank: regras públicas, transparentes, imutáveis há anos
- `0.90` — Inter, XP, Itaú premium: bem documentados
- `0.80–0.85` — PicPay, Rappi, cartões co-branded: taxas mudam com frequência

---

## 5. Camada 3 — Motor Anti-Falsos-Positivos

Esta é a camada mais crítica. Cada filtro tem uma motivação específica baseada em erros observados no mercado de comparadores de cartões.

### 5.1 Conservative Point Valuation

**Problema:** Comparadores comuns usam o "melhor cenário" de valuation de milhas (ex: resgate em business class internacional). O usuário médio nunca atinge esse valor.

**Solução:** Usar o **P25 do mercado observado** para cada programa:

```python
POINT_VALUE_DISTRIBUTIONS = {
    # (P25, P50, P75)  — atualizado mensalmente via scraping MaxMilhas/passagens
    "smiles":         (0.014, 0.022, 0.038),
    "latam_pass":     (0.013, 0.021, 0.035),
    "livelo":         (0.015, 0.020, 0.028),
    "itau_multiplus": (0.013, 0.017, 0.023),
    "xp_pontos":      (0.020, 0.025, 0.032),
    "membership_amex":(0.017, 0.022, 0.030),
    "esfera":         (0.013, 0.018, 0.025),
}

def get_conservative_value(program: str) -> float:
    """Usa P25 para scoring. P50 para exibição ao usuário. P75 para cenário otimista."""
    return POINT_VALUE_DISTRIBUTIONS[program][0]  # P25
```

**Output para o usuário:** Mostrar intervalo `P25–P75`, não um ponto fixo.
> "Seus pontos Smiles valem **R$56 a R$169/mês** dependendo de como você resgatar."

### 5.2 Benefit Utilization Filter

Antes de qualquer benefit entrar no score, passar pelo filtro de viabilidade:

```python
class BenefitViabilityFilter:
    HARD_BLOCKS = {
        # tag: condição para bloquear completamente
        "LOUNGE":       lambda ctx: ctx.flights_per_year < 2,
        "INTERNACIONAL": lambda ctx: not ctx.has_international_spend,
        "HOTEL_ELITE":  lambda ctx: ctx.flights_per_year < 6,
        "SEGURO_VIAGEM": lambda ctx: not ctx.has_international_spend,
    }

    def filter(self, card: Card, ctx: UserIntelligenceContext) -> list[Benefit]:
        result = []
        for benefit in card.benefits:
            # Hard block por tag do benefício
            blocked = False
            for tag, condition in self.HARD_BLOCKS.items():
                if tag in getattr(card, "benefit_tags", []) and condition(ctx):
                    blocked = True
                    break
            if not blocked:
                result.append(benefit)
        return result
```

**Regra:** Benefícios bloqueados têm `monthly_value = 0.00` — não podem compensar anuidade alta.

### 5.3 Waiver Achievability Gate

Se a anuidade for > R$50/mês e a isenção **não** for atingível (achievability < 0.80), o cartão entra no ranking com o custo real da anuidade. Isso faz com que cartões premium de anuidade alta desçam no ranking para usuários com gasto insuficiente.

```
if not waiver_achievable and annuity > 600:
    # Aplicar fator de clareza: deixar óbvio na UI que a anuidade pesa
    annuity_clarity_flag = True
```

### 5.4 Confidence Gate

**Regra mais importante:** Nenhum insight é surfaçado ao usuário se `confidence_score < 0.65`.

| Confidence | Ação |
|-----------|------|
| ≥ 0.85 | Insight surfaçado com alta confiança |
| 0.65–0.84 | Surfaçado com disclaimer: "baseado em X meses de dados" |
| 0.50–0.64 | Convertido em pergunta: "Você costuma viajar? Isso pode mudar muito o resultado." |
| < 0.50 | **Bloqueado.** Não aparece ao usuário. |

### 5.5 Liquidity Penalizer

```python
def apply_liquidity_penalty(net_return: float, card: Card, safe_to_spend: float) -> tuple[float, LiquidityRisk]:
    monthly_fee = card.annual_fee_brl / 12
    impact = monthly_fee / safe_to_spend if safe_to_spend > 0 else 1.0

    if impact < 0.05:
        return net_return * 1.00, LiquidityRisk.SAFE
    elif impact < 0.10:
        return net_return * 0.90, LiquidityRisk.WARNING     # -10%
    elif impact < 0.20:
        return net_return * 0.60, LiquidityRisk.HIGH        # -40%
    else:
        return net_return * 0.20, LiquidityRisk.CRITICAL    # -80%
```

> **Lógica:** Um cartão que "rende" R$50/mês mas custa R$80/mês em anuidade que compromete 30% do safe_to_spend do usuário **não** é uma boa recomendação — mesmo se o retorno bruto parecer positivo.

### 5.6 Minimum Gain Filter

```
if adjusted_net_return - current_net_return < 10.00:
    suppress_insight()  # silently drop
```

Evita ruído de recomendações com ganho marginal (ex: "Troque para este cartão e economize R$3/mês"). O threshold de R$10 equivale a aproximadamente metade do preço da assinatura Nexa Free.

---

## 6. Camada 4 — Otimizador de Portfólio Multi-Cartão

### 6.1 Algoritmo Greedy por Categoria

**Complexidade:** O(C × K) onde C = número de categorias, K = número de cartões elegíveis.

**Por que greedy é ótimo aqui:** As categorias são independentes — o cashback em supermercado não afeta o cashback em viagem. A independência garante que a solução greedy seja globalmente ótima.

```
Para cada categoria de gasto:
    melhor_cartão = argmax(cashback_efetivo(cartão, categoria))
    melhor_taxa   = cashback_efetivo(melhor_cartão, categoria)
    ganho_marginal += spend(categoria) × (melhor_taxa - taxa_atual)
```

### 6.2 Análise de Custo Marginal

A introdução de um novo cartão no portfólio tem um custo: a anuidade. O cartão só entra no portfólio recomendado se o ganho marginal superar o custo:

```python
def should_include_card(card, category_gains, profile) -> bool:
    total_marginal_gain = sum(
        gain for cat, gain in category_gains.items()
        if best_card_for(cat) == card
    )
    monthly_cost = card.monthly_fee_brl if not waiver_achievable(card, profile) else 0
    return total_marginal_gain > monthly_cost * 1.20  # margem de segurança de 20%
```

O fator `1.20` é a margem de segurança: o ganho precisa superar o custo em **20%** para justificar a complexidade de gerenciar um cartão adicional.

### 6.3 Wallet Minimizer

Depois da otimização por categoria, verificar se algum cartão pode ser removido sem perda significativa:

```
Para cada cartão no portfólio recomendado (exceto o principal):
    Se o cartão só domina 1 categoria E o ganho nessa categoria < custo_marginal:
        Remover do portfólio
        Redirecionar categoria para o segundo melhor cartão
```

### 6.4 Cálculo do Opportunity Cost

```
opportunity_cost_mensal = retorno_portfólio_ótimo - retorno_portfólio_atual
opportunity_cost_anual  = opportunity_cost_mensal × 12
```

**Este número é o gancho principal do paywall:** "Você está deixando R$X/mês na mesa. Assine o Pro para ver o portfólio completo."

---

## 7. Camada 5 — Geração de Insights Acionáveis

### 7.1 Taxonomia de Insights

| Tipo | Gatilho | Ganho típico | Esforço |
|------|---------|--------------|---------|
| `TROCAR_PRIMARIO` | Melhor cartão ≠ atual, ganho > R$20/mês | Alto | Médio |
| `PORTFOLIO_MULTI` | 2+ cartões melhoram retorno > R$30/mês | Alto | Baixo |
| `ATIVAR_BENEFICIO` | Benefício com utilização < 0.3 e valor > R$20/mês | Médio | Baixo |
| `CANCELAR_CARTAO` | Cartão com retorno líquido < -R$15/mês | Médio | Baixo |
| `ATINGIR_ISENCAO` | Gap < 3 meses de gasto para waiver | Médio | Médio |
| `MUDAR_CATEGORIA` | Cartão existente melhor em categoria não usada | Baixo | Baixo |
| `SOLICITAR_UPGRADE` | Usuário atingiu 90%+ dos critérios do próximo tier | Alto | Alto |

### 7.2 Interval Estimator

Cada insight tem três cenários:

```python
@dataclass
class InsightInterval:
    conservative: float   # P25: cenário pessimista (usado para gate de R$10)
    expected: float       # P50: cenário mais provável (mostrado em destaque)
    optimistic: float     # P75: cenário otimista (mostrado como teto)
```

**Regra de display:**
- Se `optimistic / conservative < 1.5` → mostrar só o `expected` ("R$61/mês")
- Se `optimistic / conservative ≥ 1.5` → mostrar banda ("R$40–R$95/mês") + explicação

### 7.3 Priority Ranking

Os insights são ranqueados por **impacto ajustado por esforço:**

```
priority_score = monthly_gain × effort_multiplier × confidence_score

effort_multiplier:
    "Baixo"  → 1.20   (leve bônus: fácil de executar, alta conversão)
    "Médio"  → 1.00   (neutro)
    "Alto"   → 0.70   (penalidade: muita fricção reduz taxa de execução)
```

---

## 8. Sistema de Valuation Dinâmico de Pontos

### 8.1 O Problema

O valor de 1 ponto Smiles oscila entre R$0.010 (vouchers no app) e R$0.060 (business class internacional). Usar um único valor fixo é a maior fonte de erros em comparadores de cartão.

### 8.2 Arquitetura do PointValuationEngine

```
PointValuationEngine
├── Fontes de dados (atualização semanal)
│   ├── MaxMilhas: preços de resgate observados
│   ├── PassagensImperdíveis: ofertas de transferência
│   └── Sites oficiais dos programas (scraping ou API)
│
├── Distribuição por programa
│   ├── smiles:         (P25=0.014, P50=0.022, P75=0.038)
│   ├── latam_pass:     (P25=0.013, P50=0.021, P75=0.035)
│   ├── livelo:         (P25=0.015, P50=0.020, P75=0.028)
│   ├── xp_pontos:      (P25=0.020, P50=0.025, P75=0.032)
│   └── membership_amex:(P25=0.017, P50=0.022, P75=0.030)
│
├── Ajuste por perfil do usuário
│   ├── Viajante frequente (≥6 voos/ano): usar P50
│   ├── Viajante ocasional (2–5 voos/ano): usar P25
│   └── Não-viajante (< 2 voos/ano): cashback fixo ou P10
│
└── Promoções de transferência (bônus temporários)
    └── Quando há bônus ativo (ex: Livelo 100% para Smiles):
        value_temp = P50 × (1 + bonus_pct / 100)
        Mas usar em insights apenas se prazo > 14 dias
```

### 8.3 Regras de Atualização

| Evento | Ação |
|--------|------|
| Promoção de transferência detectada | Recalcular scores dos cartões afetados; gerar insight temporário |
| Desvalorização > 15% em 30 dias | Alertar usuários com ≥ 5.000 pontos no programa afetado |
| Atualização semanal de P50 | Recalcular rankings silenciosamente |
| Mudança de regras de acúmulo | Marcar `data_trust_score` como desatualizado; forçar revisão manual |

---

## 9. Catálogo de Cartões — Governança e Manutenção

### 9.1 Campos Críticos para a Inteligência

| Campo | Frequência de mudança | Consequência de desatualização |
|-------|-----------------------|-------------------------------|
| `category_rates` | Semestral | Score completamente errado |
| `base_annuity` | Anual | Retorno líquido errado |
| `waiver_spend` | Anual | Recomendação de upgrade indevida |
| `point_value` | Semanal | Over/undervaluação de pontos |
| `benefit_tags` / `benefits` | Semestral | Falso positivo em LOUNGE/INTERNACIONAL |
| `min_income` | Anual | Recomendação de cartão sem aprovação |
| `data_trust_score` | Manual | Confiança inflada em dados obsoletos |

### 9.2 Processo de Atualização

```
1. DETECÇÃO: Monitorar páginas dos emissores (scraping semanal)
             + Twitter/Reddit para reports de usuários (mudanças de regras)

2. VALIDAÇÃO: Comparar novo valor com valor anterior
              Se delta > 20%: flag para revisão humana antes de publicar

3. PUBLICAÇÃO: Atualizar knowledge_cards.py
               Recalcular scores de todos os usuários afetados
               Log de versão com timestamp e fonte da mudança

4. COMUNICAÇÃO: Se mudança reduz retorno do cartão principal do usuário:
               Gerar notificação proativa (MX.3)
               "O Itaucard mudou as regras de pontos. Seu retorno caiu R$X/mês."
```

### 9.3 data_trust_score — Critérios de Calibração

| Score | Critério |
|-------|---------|
| 1.00 | Regras públicas, transparentes, sem mudança há > 2 anos (Nubank) |
| 0.90–0.95 | Bem documentado, < 1 mudança/ano, sem cláusulas ambíguas |
| 0.85–0.89 | Documentação clara mas histórico de 1–2 mudanças/ano |
| 0.80–0.84 | Regras com asteriscos, benefícios condicionais complexos |
| < 0.80 | Taxas que mudam com frequência, programas de fidelidade instáveis |

---

## 10. Loop de Aprendizado Contínuo

### 10.1 Feedback de Execução de Insights

Quando o usuário executa uma recomendação (ex: solicita cartão novo), rastrear o outcome:

```
Insight gerado → Usuário viu → Usuário clicou → Usuário executou → Retorno realizado
                                                                  ↑
                                              Comparar com retorno projetado
```

**Métricas de qualidade:**

| Métrica | Target | Alarme |
|---------|--------|--------|
| Click-through rate (CTR) | > 25% | < 15% |
| Execution rate (clicked → executou) | > 40% | < 20% |
| Retorno realizado / projetado | 0.80–1.10 | < 0.65 ou > 1.30 |
| Falso positivo (sem economia real) | < 10% | > 20% |

### 10.2 Calibração de Benefit Utilization

Com dados suficientes de feedback:

```python
# Para cada tipo de benefício, comparar utilização declarada vs. real
# Exemplo: quantos usuários com LOUNGE realmente usaram sala VIP?

observed_utilization = count(users_with_lounge_who_used) / count(users_with_lounge)

# Atualizar Benefit.utilization_rate no catálogo se divergência > 15%
if abs(observed_utilization - catalog_utilization) > 0.15:
    update_catalog(benefit, utilization_rate=observed_utilization)
    recalculate_affected_scores()
```

### 10.3 Detecção de Viés no Ranking

Monitorar se algum cartão ou emissor aparece sistematicamente no topo para perfis onde não deveria:

```
Se emissor_X domina > 60% dos rankings no segmento_Y:
    Auditoria manual das taxas de categoria_Y para emissor_X
    Verificar se data_trust_score está inflado
```

---

## 11. Definições de Qualidade e SLAs

### 11.1 Definição de Falso Positivo

Um insight é classificado como **falso positivo** quando qualquer uma das condições abaixo é verdadeira:

1. **Ganho não realizável:** O retorno projetado assume benefícios que o perfil do usuário impossibilita (ex: LOUNGE para não-viajante)
2. **Cartão não aprovável:** O usuário não teria o cartão aprovado dado seu perfil de renda/estabilidade
3. **Isenção inalcançável:** A recomendação assume isenção de anuidade que o usuário não atingirá
4. **Point value otimista:** O retorno foi calculado com P75 de valuation em vez de P25
5. **Dados insuficientes:** Recomendação gerada com < 2 meses de histórico
6. **Ganho abaixo do threshold:** Insight surfaçado com ganho líquido < R$10/mês

### 11.2 Métricas de Operação

| Métrica | Target | Método de medição |
|---------|--------|------------------|
| Taxa de falsos positivos | < 8% | Feedback pós-execução |
| Confidence score médio dos insights surfaçados | > 0.78 | Monitoramento em tempo real |
| Retorno realizado / projetado | 0.80–1.10 | Comparação 90 dias após execução |
| Taxa de aprovação de cartões recomendados | > 72% | Parceria com emissores (futuro) |
| Ganho anual médio materializado por usuário | > R$600 | Cohort analysis mensal |

### 11.3 Níveis de Alerta

| Nível | Condição | Ação |
|-------|----------|------|
| `INFO` | Atualização semanal normal de point values | Log silencioso |
| `WARN` | `data_trust_score` de cartão ativo cai < 0.80 | Revisão em 48h |
| `WARN` | Falso positivo rate > 12% em 7 dias | Revisão dos filtros |
| `ALERT` | Point value muda > 30% em 7 dias | Recálculo imediato + notificação de usuários |
| `CRITICAL` | Cartão muda regras core (acúmulo, anuidade) | Pausar insights desse cartão; revisão manual |

---

## 12. Mapa de Decisões Críticas

### 12.1 Árvore de Decisão — Devo Surfaçar Este Insight?

```
INSIGHT CANDIDATO
       │
       ▼
   confidence < 0.65?
   ├─ SIM → DESCARTAR silenciosamente
   └─ NÃO
          │
          ▼
      ganho líquido ajustado < R$10/mês?
      ├─ SIM → DESCARTAR silenciosamente
      └─ NÃO
             │
             ▼
         data_months_covered < 2?
         ├─ SIM → DESCARTAR (tipo TROCAR_PRIMARIO)
         │        PERMITIR (tipo ATIVAR_BENEFICIO com disclaimer)
         └─ NÃO
                │
                ▼
            eligibility_score < 0.60?
            ├─ SIM → CONVERTER para "você pode não ser aprovado"
            │         Surfaçar como dica, não como recomendação
            └─ NÃO
                   │
                   ▼
               liquidity_risk = CRITICAL?
               ├─ SIM → BLOQUEAR insight de aquisição de novo cartão
               │         PERMITER insight de cancelamento
               └─ NÃO
                      │
                      ▼
                  ✅ SURFAÇAR com band estimate (P25–P75)
```

### 12.2 Regra de Ouro do Anti-Falso-Positivo

> **Se você está em dúvida se deve mostrar um insight, não mostre.**
>
> Um usuário que não vê uma recomendação perde um ganho potencial.
> Um usuário que vê uma recomendação errada perde a confiança na Nexa.
> **Confiança vale mais que completude.**

### 12.3 Fluxo de Dados — Resumo dos Campos por Camada

```
TRANSAÇÕES F1
└── category, amount, date, description, transaction_type

    ↓ BuildSpendingProfile
    monthly_spends[], total_monthly, stability_cv, pct_committed,
    data_months_covered, international_pct, debit_ratio

    ↓ IncomeProfiler
    monthly_income, pattern (CLT/PJ/MISTO/VARIÁVEL), stability, confidence

    ↓ EligibilityScorer
    eligibility_score = f(income_effective, min_income, issuer_bonus)

    ↓ CardScoringEngine
    cashback_bruto (per category), benefits_adjusted, annuity_cost, net_return

    ↓ Anti-FP Layer
    point_value (P25), benefits (viability-filtered), waiver (achievability-gated),
    confidence_score, liquidity_penalty, min_gain_filter

    ↓ PortfolioOptimizer
    best_card_per_category, marginal_cost_check, wallet_minimizer

    ↓ InsightGenerator
    type, gain_interval (P25/P50/P75), effort, priority_score, display_confidence

    ↓ USUÁRIO
    "Usar Bradesco Amex Gold em supermercado economiza R$24–R$32/mês — Esforço: Baixo"
```

---

*Nexa AI — Card Optimizer v2.1 — Arquitetura Confidencial*
*Última atualização: Março 2025*