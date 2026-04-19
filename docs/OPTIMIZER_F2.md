# Card Optimizer v2.1 — Arquitetura Implementada

> **Fonte de verdade:** este documento descreve o código tal como está implementado hoje.
> Última sincronização: 2026-04-19.

---

## Visão Geral

O Nexa Optimizer analisa o histórico de transações do usuário e recomenda cartões de crédito com base no retorno financeiro líquido real (pontos/cashback − anuidade), ajustado por risco de liquidez, confiança nos dados e elegibilidade.

### Camadas

```
Camada 1 — Ingestão e Validação         (InputValidator + ConsumptionProfiler)
Camada 2 — Scoring Multifatorial        (CardSimulator)
Camada 3 — Anti-Falsos-Positivos        (BenefitViabilityFilter + LiquidityChecker + _apply_anti_fp_gates)
Camada 4 — Ranking                      (CardRanking)
Camada 5 — Insights Acionáveis          (InsightGenerator)
```

**Arquivos principais:**

| Arquivo | Responsabilidade |
|---|---|
| `app/optimizer/profiler.py` | ConsumptionProfiler → UserProfile |
| `app/optimizer/simulator.py` | CardSimulator → CardSimulationResult |
| `app/optimizer/ranking.py` | CardRanking → lista ordenada |
| `app/optimizer/miles_valuator.py` | MilesValuator — P25/P50/P75 por programa |
| `app/optimizer/validators/liquidity_checker.py` | LiquidityChecker — thresholds v2.1 |
| `app/optimizer/insight_generator.py` | InsightGenerator — Camada 5 |
| `app/optimizer/services/optimizer_service.py` | OptimizerService — orquestrador |
| `app/optimizer/models.py` | Pydantic schemas |

---

## Camada 1 — Ingestão e Validação

### ConsumptionProfiler (`profiler.py`)

Analisa os últimos **90 dias** de `transactions_clean` e monta o `UserProfile`.

**Exclusões:** transações com `context_type == "PJ"` são excluídas do consumo pessoal.

**Campos calculados:**

```python
@dataclass
class UserProfile:
    monthly_avg_spend: float          # média de gasto mensal (últimos 90 dias)
    committed_percentage: float       # % do gasto médio já comprometido (shadow invoices)
    spend_by_category: dict           # gasto médio mensal por categoria
    spend_by_source: dict             # gasto por fonte (debit, credit, pix, ...)
    international_spend_monthly: float
    travel_spend_monthly: float
    estimated_monthly_income: float   # soma bruta de créditos (legado, pode estar inflado)
    data_coverage_months: int         # meses com dados completos
    spending_stability: float         # 1 − min(CV, 1.0) — invertido para leitura humana
    spend_stability_cv: float         # CV puro (std/mean) — usado pelo ConfidenceScorer
    income_profile: Optional[IncomeProfile]  # saída do IncomeProfiler (M1.x)
```

**`spending_stability` e `spend_stability_cv` são calculados juntos:**

```python
def _spending_stability(self, monthly_totals) -> tuple[float, float]:
    cv = float(std) / float(mean)
    stability = max(round(1.0 - min(cv, 1.0), 4), 0.0)
    return stability, round(min(cv, 1.0), 4)
```

### Hierarquia de Renda (`optimizer_service.py`)

Fontes em ordem de confiabilidade:

1. `request.monthly_income` — declarado pelo usuário (mais confiável)
2. `income_profile.monthly_net_income` quando `confidence >= 0.5` (IncomeProfiler)
3. `estimated_monthly_income` — soma bruta de créditos (fallback, pode estar inflado)

### Detecção de Issuer por Transações

```python
_ISSUER_PATTERNS = {
    "Nubank":          [r"\bnubank\b", r"\bnu\s+pagamentos\b"],
    "Banco Inter":     [r"\binter\b", r"\bbanco\s+inter\b"],
    "Itau":            [r"\bitau\b", r"\bita[uú]\b"],
    "C6 Bank":         [r"\bc6\s*bank\b", r"\bc6\b"],
    "Next (Bradesco)": [r"\bnext\b", r"\bbradesco\b"],
    "XP":              [r"\bxp\s+invest\b", r"\bxp\s+cartao\b"],
    "PicPay":          [r"\bpicpay\b"],
}
```

Issuers detectados nas descrições de transações recebem bônus de relacionamento bancário no `eligibility_score` (calculado em `CardKnowledgeBase.compute_eligibility_score`).

---

## Camada 2 — Scoring Multifatorial

### CardSimulator (`simulator.py`)

Simula 3 cenários de gasto (−20% / base / +20%) e calcula:

```python
_SCENARIO_FACTORS = {"min": 0.8, "expected": 1.0, "max": 1.2}
```

#### 2.1 — Anuidade Efetiva (WaiverAchievabilityCheck)

```python
_WAIVER_ACHIEVABILITY_GATE = 0.80
```

A isenção só é concedida se a probabilidade de atingir o threshold for >= 80%.

**Fórmula:**
```
achievability = max(0, 1 - gap / threshold)
gap = threshold - projected_annual_spend
```

**Mapeamento por tipo de waiver:**

| `waiver_rules.type` | Comportamento |
|---|---|
| `always_free` | Sempre isenta |
| `spend_threshold` | Calcula achievability >= 0.80 → isenta |
| `transaction_count` | Conservador — assume não atingido |
| `none` | Sempre cobra |

#### 2.2 — Valor dos Benefícios

**Cartões POINTS:**
1. Se `loyalty_program` definido → usa `MilesValuator.compute_points_value()` com P25/P50/P75
2. Fallback: `(spend × points_per_brl / 1000) × points_conversion_rate`

**Cartões CASHBACK / INVESTBACK:**
1. Se `cashback_categories` definido e perfil disponível → cashback por categoria (M2.5)
2. Fallback: `spend × cashback_pct`, limitado por `cashback_cap × 12`

**Cashback por categoria (M2.5):**
- Escala o gasto de cada categoria pelo fator `spend_annual_scaled / total_category_spend`
- Aplica `rule.pct` se encontrar a categoria em `cashback_categories`
- Usa `cashback_default_pct` (ou `cashback_pct`) para categorias sem regra específica
- Respeita `rule.cap_monthly` por categoria e `cashback_cap` geral

#### 2.3 — Ganho Líquido por Cenário

```
net_gain_min      = value_min      - annuity_effective
net_gain_expected = value_expected - annuity_effective
net_gain_max      = value_max      - annuity_effective
```

#### 2.4 — Impacto de Liquidez

```
liquidity_impact = (annuity_effective / 12) / safe_to_spend
```

- `annuity_effective == 0` → `liquidity_impact = 0.0`
- `safe_to_spend` ausente ou <= 0 com anuidade → `liquidity_impact = 1.0` (CRITICAL)

#### 2.5 — ConfidenceScorer

**Fórmula multiplicativa:**

```
confidence = data_trust_score
           × coverage_penalty
           × commitment_penalty
           × income_confidence
           × stability_factor
```

**Penalidades de cobertura:**

| Meses de dados | Multiplicador |
|---|---|
| >= 6 | × 1.00 (sem penalidade) |
| 3–5 | × 0.85 |
| 2 | × 0.50 |
| < 2 | × 0.25 |

**Penalidade de compromisso:**
- `committed_percentage > 0.80` → × 0.70

**Confiança de renda:**
- `income_conf = profile.income_profile.confidence` (ou 1.0 se ausente)
- score × income_conf

**Penalidade de estabilidade (CV):**

| CV (`spend_stability_cv`) | Multiplicador |
|---|---|
| <= 0.15 | × 1.00 |
| 0.15–0.35 | × 0.90 |
| 0.35–0.60 | × 0.75 |
| > 0.60 | × 0.60 |

---

## Camada 3 — Anti-Falsos-Positivos

### LiquidityChecker (`validators/liquidity_checker.py`)

**Thresholds v2.1 (mais conservadores que v1):**

```python
def check(self, liquidity_impact: float) -> LiquidityRisk:
    if liquidity_impact < 0.05:   return LiquidityRisk.SAFE
    elif liquidity_impact < 0.10: return LiquidityRisk.WARNING
    elif liquidity_impact < 0.20: return LiquidityRisk.HIGH
    else:                         return LiquidityRisk.CRITICAL
```

### BenefitViabilityFilter (`simulator.py`)

Hard blocks — benefícios bloqueados têm valor = 0 no ranking:

```python
HARD_BLOCKS = {
    BenefitTag.LOUNGE:        lambda p: p.travel_spend_monthly < 800,
    BenefitTag.INTERNACIONAL: lambda p: p.international_spend_monthly < 50,
}
```

### _apply_anti_fp_gates (`optimizer_service.py`)

Filtro a nível de **cartão** (não de insight):

- **MinGainFilter:** remove cartões com `net_gain_expected < 0` (anuidade não se paga)
- Cartões com confiança baixa **não são removidos aqui** — o ranking penaliza via × 0.5 se `confidence < 0.40`
- Os gates de confiança (0.65) e ganho mínimo (R$10/mês) são aplicados apenas no `InsightGenerator`

---

## Camada 4 — Ranking

### CardRanking (`ranking.py`)

**Algoritmo (multiplicativo v2.1):**

```python
# 1. Liquidez — multiplicativo
_LIQUIDITY_MULTIPLIER = {
    SAFE:     1.00,
    WARNING:  0.90,   # -10%
    HIGH:     0.60,   # -40%
    CRITICAL: 0.20,   # -80%
}
score = net_gain_expected × liquidity_multiplier

# 2. Bonus de beneficios (hard blocks validados no BenefitViabilityFilter)
_INTL_SPEND_THRESHOLD  = 500.0  # R$/mês
_TRAVEL_SPEND_THRESHOLD = 800.0  # R$/mês
_INTL_BONUS   = 200.0  # R$/ano
_LOUNGE_BONUS = 300.0  # R$/ano

if international_spend_monthly > 500 and INTERNACIONAL in benefit_tags:
    benefits_bonus += 200.0
if travel_spend_monthly > 800 and LOUNGE in benefit_tags:
    benefits_bonus += 300.0

# Regra 40%: se beneficios dominam > 40% do ganho base → desconto 15%
_BENEFIT_DOMINANCE_THRESHOLD = 0.40
_BENEFIT_DOMINANCE_DISCOUNT  = 0.85
if benefits_bonus > 0.40 × net_gain_expected:
    benefits_bonus *= 0.85

score += benefits_bonus

# 3. Penalidade de confiança
if confidence_score < 0.4: score *= 0.5

# 4. Penalidade de elegibilidade (escalonada)
if eligibility_score < 0.5:   score *= 0.4
elif eligibility_score < 0.7: score *= 0.75
```

**Regra pós-sort de elegibilidade mínima:**
Se o 1º cartão tem `eligibility_score < 0.40` e existe outro com `eligibility_score >= 0.60`, o mais elegível é promovido para o topo.

---

## PointValuationEngine — MilesValuator (`miles_valuator.py`)

**Princípio:** scoring usa P25 (conservador); display usa P50; intervalo P25–P75 mostrado quando P75/P25 >= 1.5.

**Distribuições por programa (R$/ponto):**

```python
POINT_VALUE_DISTRIBUTIONS = {
    "smiles":          (0.014, 0.022, 0.038),  # P25, P50, P75
    "latam_pass":      (0.013, 0.021, 0.035),
    "livelo":          (0.015, 0.020, 0.028),
    "itau_multiplus":  (0.013, 0.017, 0.023),
    "xp_pontos":       (0.020, 0.025, 0.032),
    "membership_amex": (0.017, 0.022, 0.030),
    "esfera":          (0.013, 0.018, 0.025),
    "nu_pontos":       (0.010, 0.015, 0.020),
    "atomos":          (0.010, 0.015, 0.022),
    "stix":            (0.012, 0.018, 0.025),
}
```

**Conversão:** P25 × 1000 = R$/1.000 pontos (ex: livelo P25 = 0.015 × 1000 = R$15/mil pts)

**Métodos disponíveis:**

| Método | Retorna |
|---|---|
| `get_rate(program, scenario)` | R$/1.000 pts para o cenário ("min"/"pessimistic" = P25, "expected" = P50, "max"/"optimistic" = P75) |
| `get_conservative_rate(program)` | P25 em R$/1.000 pts (para scoring) |
| `get_interval(program)` | (P25, P50, P75) × 1.000 |
| `compute_points_value(pts_per_brl, spend, program, scenario)` | Valor em R$ |
| `describe_scenario(program, scenario)` | Texto descritivo para o LLM |

**Fallback:** se programa não está em `POINT_VALUE_DISTRIBUTIONS`, busca no `data/cards/miles_valuation.json`.

---

## Camada 5 — Insights Acionáveis

### InsightGenerator (`insight_generator.py`)

#### Gates (aplicados após geração de todos os insights)

```python
_INSIGHT_CONFIDENCE_GATE  = 0.65   # confiança mínima para surfaçar
_INSIGHT_MIN_MONTHLY_GAIN = 10.0   # R$/mês — gate no P25 (conservative)
```

Insights com `confidence_score < 0.65` **ou** `gain_interval.conservative < R$10/mês` são descartados silenciosamente.

#### Taxonomia e Gates de Ativação

```python
_TRIGGER_GAIN_TROCAR_PRIMARIO  = 20.0   # R$/mês
_TRIGGER_GAIN_PORTFOLIO_MULTI  = 30.0   # R$/mês
_TRIGGER_GAIN_ATIVAR_BENEFICIO = 20.0   # R$/mês
_TRIGGER_LOSS_CANCELAR_CARTAO  = -15.0  # R$/mês (prejuízo — enum existe, lógica não implementada)
```

#### Tipos Implementados

**TROCAR_PRIMARIO**
- Condição: `best.card_id != current_card_id` e ganho mensal > R$20/mês
- `monthly_gain = (best.net_gain_expected / 12) - current_monthly_return`
- Effort: MEDIO

**PORTFOLIO_MULTI**
- Condição: 2+ cartões com `net_gain_expected > 0` e ganho incremental > R$30/mês
- `portfolio_gain = soma_top2 / 12 - melhor_individual / 12`
- Effort: BAIXO

**ATIVAR_BENEFICIO**
- Para cada cartão nos top 5, por cada `benefit_tag`:
  - LOUNGE: se `travel_spend_monthly > 800` → estima R$70/mês
  - INTERNACIONAL: se `international_spend_monthly > 500` → estima R$25/mês
- Effort: BAIXO

**ATINGIR_ISENCAO**
- Para cada cartão top 5 com `annuity_waived = False` e `annuity_effective / 12 >= R$10/mês`
- `gain_interval` baseado na anuidade mensal: conservative = × 0.8, expected = × 1.0, optimistic = × 1.0
- Effort: MEDIO

**Não implementados (enum existe, lógica ausente):**
- `CANCELAR_CARTAO` — requer dados do cartão atual do usuário
- `MUDAR_CATEGORIA` — requer histórico de uso por categoria vs cartão atual
- `SOLICITAR_UPGRADE` — requer critérios de tier por emissor na base

#### priority_score

```python
_EFFORT_MULTIPLIER = {
    InsightEffort.BAIXO: 1.20,  # fácil de executar → sobe no ranking
    InsightEffort.MEDIO: 1.00,
    InsightEffort.ALTO:  0.70,  # alta fricção → desce
}

priority_score = monthly_gain × effort_multiplier × confidence_score
```

#### InsightInterval

```python
class InsightInterval(BaseModel):
    conservative: float  # P25 — usado no MinGainFilter
    expected: float      # P50 — mostrado em destaque ao usuário
    optimistic: float    # P75

    @property
    def show_band(self) -> bool:
        # True quando otimista / conservador >= 1.5 (incerteza alta)
        return (optimistic / conservative) >= 1.5 if conservative > 0 else False
```

---

## Fluxo Completo (OptimizerService)

```
1. InputValidator.validate(request)
2. ConsumptionProfiler.build(transactions_df, shadow_invoices_df) → UserProfile
3. Hierarquia de renda: declared > income_profile (conf>=0.5) > estimated
4. CardKnowledgeBase.filter_eligible(annual_income, current_cards)
5. Para cada cartão:
   a. CardSimulator.simulate(card, profile, safe_to_spend) → CardSimulationResult
   b. CardKnowledgeBase.compute_eligibility_score(card, income, stability, issuers, income_profile)
6. _apply_anti_fp_gates(results) → remove net_gain < 0
7. CardRanking.rank(results, profile) → lista ordenada
8. InsightGenerator.generate(ranked, profile, current_card_id) → insights com gates
9. _build_report() → OptimizationReport (salvo no DuckDB)
```

### Warnings automáticos no relatório

| Condição | Warning gerado |
|---|---|
| `data_coverage_months < 2` | "Histórico muito curto para alta confiança" |
| `safe_to_spend` ausente | "Risco de anuidade não pôde ser avaliado" |
| `monthly_income` não declarado e `income_conf < 0.5` | "Informar renda melhora a precisão" |

---

## Modelos de Dados

### CardRecord (entrada da base de conhecimento)

```python
class CardRecord(BaseModel):
    card_id: str
    name: str
    issuer: str
    flag: CardFlag          # VISA | MASTERCARD | ELO | AMEX | HIPERCARD
    card_type: CardType     # POINTS | CASHBACK | INVESTBACK
    public_target: str
    min_income: float               # renda anual mínima em R$
    requires_proof_of_income: bool
    secured_card: bool
    prepaid: bool
    consigned: bool
    base_annuity: float
    waiver_rules: WaiverRules       # type | threshold | count_monthly | description
    cashback_pct: Optional[float]           # cashback flat (fallback)
    cashback_cap: Optional[float]           # teto mensal geral
    cashback_default_pct: Optional[float]   # M2.5: taxa para categorias sem regra
    cashback_categories: list[CashbackCategoryRule]  # M2.5: regras por categoria
    points_per_brl: Optional[float]
    points_conversion_rate: float           # R$/1.000 pontos (fallback)
    loyalty_program: Optional[str]          # M2.3: chave para MilesValuator
    benefit_tags: list[BenefitTag]
    benefits_detail: list[str]
    data_trust_score: float = 0.7
    last_updated: str
```

### CardSimulationResult (saída por cartão)

```python
class CardSimulationResult(BaseModel):
    card_id, card_name, issuer, flag
    annuity_effective: float
    annuity_waived: bool
    points_value_min, points_value_expected, points_value_max: float
    net_gain_min, net_gain_expected, net_gain_max: float
    liquidity_impact: float       # (annuity/12) / safe_to_spend
    liquidity_risk: LiquidityRisk
    confidence_score: float
    eligibility_score: float
    eligibility_reasons: list[str]
    profile_match_reasons: list[str]
    spending_anchor: dict
    explanation_steps: list[str]
    benefit_highlights: list[str]  # max 3 (primeiros de benefits_detail)
    benefit_tags: list[BenefitTag]
```

### OptimizationReport (saída final)

```python
class OptimizationReport(BaseModel):
    report_id: str
    user_id: str
    generated_at: datetime
    recommendation_type: RecommendationType  # SWITCH_RECOMMENDED | KEEP_CURRENT | INSUFFICIENT_DATA
    best_card: Optional[CardSimulationResult]
    all_cards: list[CardSimulationResult]
    insights: list[ActionableInsight]
    strategy_text: str
    warnings: list[str]
    data_sources: list[str]
```

---

## O que ainda não está implementado

| Feature | Status | Blocker |
|---|---|---|
| `CANCELAR_CARTAO` insight | Não implementado | Requer dados do cartão atual do usuário |
| `MUDAR_CATEGORIA` insight | Não implementado | Requer análise de categoria vs cartão ativo |
| `SOLICITAR_UPGRADE` insight | Não implementado | Requer critérios de tier por emissor na base |
| Loop de Aprendizado Contínuo | Não implementado | Necessita histórico de conversões de recomendação |
| Atualização dinâmica de `POINT_VALUE_DISTRIBUTIONS` | Manual | Planejado via scraping MaxMilhas/PassagensImperdíveis |
| Tracker de promoções de pontos | Não implementado | Afetaria confiança do cenário otimista |

---

## Princípios de Design

1. **Conservadorismo sobre otimismo** — P25 para scoring, P50 para display; gate de achievability >= 80% antes de isentar anuidade.
2. **Multiplicativo, não subtrativo** — penalidades de liquidez e confiança multiplicam o score (não subtraem valores fixos), preservando a ordem relativa entre cartões.
3. **Gates no nível certo** — MinGainFilter (net_gain < 0) a nível de cartão; ConfidenceGate (0.65) e MinMonthlyGain (R$10/mês) apenas a nível de insight.
4. **Regra de ouro do anti-FP** — em caso de dúvida, não mostrar o insight. Confiança vale mais que completude.
5. **Hard blocks explícitos** — LOUNGE sem `travel_spend_monthly >= R$800` e INTERNACIONAL sem `international_spend_monthly >= R$50` nunca contam como bonus no ranking.
