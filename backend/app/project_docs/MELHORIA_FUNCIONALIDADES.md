# NEXA AI — Melhorias de Funcionalidades

> Propostas concretas para tornar cada funcionalidade mais completa e valiosa.
> Organizadas por impacto ao usuário × esforço de implementação.
>
> Gerado em: 2026-02-28 — Atualizado em: 2026-03-03

---

## RESUMO EXECUTIVO

| Funcionalidade | Melhorias propostas | Impacto estimado | Status |
|---|---|---|---|
| **F2 — Optimizer** | 6 melhorias (incluindo custo de oportunidade e estratégia multi-cartão) | 🔴 Alto | M2.1 ✅ M2.2 ✅ M2.4 ✅ M2.5 ✅ M2.6 ✅ |
| **F1 — Core Engine** | 5 melhorias (anomalias, alertas de velocidade, orçamento inteligente) | 🔴 Alto | M1.1 ✅ M1.2 ✅ M1.4→IncomeProfiler ✅ M1.5 ✅ |
| **F3 — Architect** | 4 melhorias (inflação, IR, custo de oportunidade cruzado) | 🟡 Médio | M3.1 ✅ M3.2 ✅ |
| **F4 — PF/PJ** | 3 melhorias (relatório fiscal, categorização PJ granular) | 🟡 Médio | — |
| **Cross-functional** | 4 melhorias (score temporal, metas, notificações) | 🔴 Alto | MX.1 ✅ MX.2 ✅ |
| **IncomeProfile — Integração** | 8 oportunidades de precisão derivadas do IncomeProfiler | 🔴 Alto | 8/8 ✅ |

---

## F2 — NEXA OPTIMIZER: Melhorias

### M2.1 — Calculadora de Custo de Oportunidade ("Quanto você deixou de ganhar")

**O problema:** O Optimizer atual recomenda o melhor cartão, mas não mostra ao usuário quanto ele **já perdeu** usando o cartão errado. Isso é o que mais motiva a troca.

**O que faz:**
Pega as transações reais do mês atual (ou dos últimos 3 meses) do cartão que o usuário já usa e simula quanto ele teria ganho se tivesse usado cada cartão da base.

**Exemplo de saída ao usuário:**
> *"Em janeiro você gastou R$ 3.200 no seu Nubank Roxinho (0,5 pts/R$). Se tivesse usado o C6 Carbon (2,0 pts/R$), teria acumulado 6.400 pontos a mais — equivalentes a R$ 102 em milhas. Nos últimos 3 meses, a diferença acumulada seria R$ 287."*

**Implementação técnica:**

```
Novo arquivo: app/optimizer/opportunity_cost.py

class OpportunityCostCalculator:
    def calculate(
        self,
        transactions_df: pl.DataFrame,      # transações reais do usuário
        current_card: CardRecord,            # cartão que ele usa hoje
        candidate_cards: list[CardRecord],   # cartões para comparar
        months: int = 3                      # janela de comparação
    ) -> OpportunityCostReport

OpportunityCostReport:
    current_card_id: str
    current_card_name: str
    period_months: int
    total_spent: float
    current_card_reward_value: float         # quanto ganhou no cartão atual
    opportunities: list[CardOpportunity]     # um por cartão candidato

CardOpportunity:
    card_id: str
    card_name: str
    hypothetical_reward_value: float         # quanto teria ganho
    difference: float                        # ganho a mais
    difference_annualized: float             # projeção anual da diferença
    breakdown_by_category: dict              # diferença por categoria de gasto
    explanation: str                         # texto para o LLM usar
```

**Lógica central:**
```python
# Para cada transação real do usuário no período:
for tx in transactions:
    # Pontos no cartão atual
    current_points = tx.amount * current_card.points_per_brl
    current_value = (current_points / 1000) * current_card.points_conversion_rate

    # Pontos no cartão candidato
    candidate_points = tx.amount * candidate.points_per_brl
    # Se o candidato tem cashback diferenciado na categoria da transação:
    if tx.category in candidate.cashback_categories:
        candidate_value = tx.amount * categoria_cashback_pct
    else:
        candidate_value = (candidate_points / 1000) * candidate.points_conversion_rate

    difference += candidate_value - current_value
```

**Integração:**
- Novo endpoint: `GET /api/v1/optimizer/opportunity-cost/{user_id}`
- Também injetado no `OptimizationReport` como campo `opportunity_cost_summary`
- O agente usa na `strategy_text`: *"Você está deixando de ganhar R$ X/mês..."*

**Prioridade: 🔴 ALTA** — É o argumento mais forte para convencer o usuário a trocar de cartão.

---

### M2.2 — Estratégia Multi-Cartão ("Carteira ideal")

**O problema:** O Optimizer atual recomenda UM cartão. Na prática, a melhor estratégia é usar 2-3 cartões, cada um otimizado para categorias diferentes de gasto.

**Exemplo:**
> *"Sua carteira ideal: use o Inter Black (1% cashback) para compras do dia-a-dia, o Nubank Ultravioleta (2 pts/R$) para gastos acima de R$ 500, e o XP Visa Infinite para compras internacionais (zero IOF). Retorno combinado estimado: R$ 1.240/ano vs R$ 480/ano com um cartão só."*

**Implementação técnica:**

```
Novo arquivo: app/optimizer/multi_card_strategy.py

class MultiCardStrategist:
    def optimize_portfolio(
        self,
        profile: UserProfile,
        eligible_cards: list[CardRecord],
        max_cards: int = 3                   # máximo de cartões na carteira
    ) -> CardPortfolio

CardPortfolio:
    cards: list[CardAssignment]              # cartão + categorias atribuídas
    total_annual_return: float               # retorno combinado
    total_annuity_cost: float                # custo total de anuidades
    net_annual_gain: float                   # retorno - anuidades
    vs_single_best: float                    # quanto a mais vs melhor cartão único
    explanation: str

CardAssignment:
    card: CardRecord
    assigned_categories: list[str]           # categorias de gasto direcionadas a este cartão
    monthly_spend_directed: float            # quanto do gasto mensal vai para este cartão
    annual_return_from_this_card: float      # retorno anual só deste cartão
    reason: str                              # "Melhor cashback em alimentação (2%)"
```

**Algoritmo (greedy por categoria):**
```python
# 1. Para cada categoria de gasto do usuário:
for category, monthly_spend in profile.spend_by_category.items():
    # 2. Calcular retorno de cada cartão elegível nessa categoria
    best_card = max(eligible_cards, key=lambda c: return_for_category(c, category, monthly_spend))
    # 3. Atribuir categoria ao melhor cartão
    assignments[best_card].add(category, monthly_spend)

# 4. Consolidar: se um cartão ficou com gasto < threshold mínimo, reatribuir
# 5. Verificar: anuidade de cada cartão é justificada pelo gasto direcionado?
# 6. Limitar a max_cards (remover os de menor contribuição marginal)
```

**Prioridade: 🔴 ALTA** — Diferencial competitivo enorme. Nenhum app brasileiro faz isso bem.

---

### M2.3 — Motor de Valoração de Milhas em Tempo Real

**O problema:** O sistema atual usa `points_conversion_rate` fixo (ex: R$ 16 por 1.000 pontos). Na realidade, o valor de milhas varia bastante dependendo do programa (Livelo, Smiles, TudoAzul) e do tipo de resgate (passagem doméstica vs internacional vs produtos).

**O que faz:**
Mantém uma tabela de valoração por programa de fidelidade com cenários (pessimista / esperado / otimista) e permite ao usuário escolher como pretende usar os pontos.

**Implementação:**

```
Novo arquivo: data/cards/miles_valuation.json

{
  "livelo": {
    "pessimistic_per_1000": 8.0,       # resgate em produtos
    "expected_per_1000": 16.0,          # transferência para aéreas
    "optimistic_per_1000": 28.0,        # promoção de transferência bonificada
    "last_updated": "2026-02-01"
  },
  "smiles": {
    "pessimistic_per_1000": 12.0,
    "expected_per_1000": 22.0,
    "optimistic_per_1000": 40.0,
    "last_updated": "2026-02-01"
  },
  "tudoazul": { ... },
  "latampass": { ... }
}
```

```
Atualizar: app/optimizer/simulator.py

# No cálculo de points_value, usar valoração por programa:
if card.loyalty_program in valuation_table:
    rates = valuation_table[card.loyalty_program]
    points_value_min = (points / 1000) * rates["pessimistic_per_1000"]
    points_value_expected = (points / 1000) * rates["expected_per_1000"]
    points_value_max = (points / 1000) * rates["optimistic_per_1000"]
```

**Novo campo no CardRecord:**
```json
{
  "loyalty_program": "livelo",           // novo campo
  "points_transfer_partners": ["LATAM", "Azul", "GOL", "TAP"],
  "current_transfer_bonus": null         // ou {"partner": "LATAM", "bonus_pct": 100, "expires": "2026-03-15"}
}
```

**Prioridade: 🟡 MÉDIA** — Melhora muito a precisão das recomendações de cartões POINTS.

---

### M2.4 — Rastreamento de ROI do Cartão Atual ("Sua anuidade está se pagando?")

**O problema:** Muitas pessoas pagam anuidade sem saber se estão aproveitando o suficiente do cartão para justificar o custo.

**O que faz:**
Calcula se o uso real do cartão atual está gerando valor suficiente para cobrir a anuidade.

**Saída ao usuário:**
> *"Você paga R$ 2.856/ano de anuidade no Ultravioleta. Com seu gasto médio de R$ 2.100/mês, você gera R$ 806/ano em pontos. Resultado: você está no prejuízo de R$ 2.050/ano. Para isentar a anuidade, precisaria gastar R$ 16.667/mês (hoje gasta R$ 2.100)."*

**Implementação:**

```
Novo método em app/optimizer/simulator.py:

class CardSimulator:
    def calculate_current_card_roi(
        self,
        card: CardRecord,
        profile: UserProfile
    ) -> CurrentCardROI

CurrentCardROI:
    card_id: str
    annuity_paid: float                      # anuidade que está pagando
    reward_value_generated: float            # valor gerado em pontos/cashback
    net_roi: float                           # reward - annuity (negativo = prejuízo)
    annuity_waived: bool                     # anuidade está isenta?
    spend_needed_for_waiver: float | None    # quanto falta gastar p/ isentar
    months_to_reach_waiver: float | None     # meses p/ alcançar threshold (se mantiver ritmo)
    benefits_used: list[str]                 # benefícios que o perfil indica uso
    benefits_unused: list[str]              # benefícios que o perfil não usa
    verdict: str                             # "VALE_A_PENA" | "NAO_VALE" | "MARGINAL"
    explanation: str
```

**Prioridade: 🟡 MÉDIA** — Complementa a recomendação de troca com dados concretos sobre o cartão atual.

---

### M2.5 — Cashback por Categoria Detalhado

**O problema:** Alguns cartões oferecem cashback diferenciado por categoria (ex: 2% em farmácia, 1% no resto). O sistema atual não cruza essas categorias com o perfil de gasto do usuário.

**O que faz:**
Expande o `cashback_categories` no CardRecord para incluir percentuais por categoria, e o simulador calcula o retorno real considerando a distribuição de gastos do usuário.

**Novo schema no CardRecord:**
```json
{
  "cashback_categories": [
    {"category": "alimentacao", "pct": 0.02, "cap_monthly": 50.0},
    {"category": "transporte", "pct": 0.015, "cap_monthly": null},
    {"category": "farmacia", "pct": 0.03, "cap_monthly": 30.0}
  ],
  "cashback_default_pct": 0.005
}
```

**No simulador:**
```python
total_cashback = 0
for category, spend in profile.spend_by_category.items():
    # Buscar cashback diferenciado
    cat_rule = find_category_rule(card.cashback_categories, category)
    if cat_rule:
        cb = spend * cat_rule.pct
        if cat_rule.cap_monthly:
            cb = min(cb, cat_rule.cap_monthly)
        total_cashback += cb
    else:
        total_cashback += spend * card.cashback_default_pct
```

**Prioridade: 🟡 MÉDIA** — Melhora precisão especialmente para cartões cashback (Inter, PicPay, Méliuz).

---

### M2.6 — Alertas de Promoções de Transferência Bonificada

**O problema:** Programas de fidelidade frequentemente oferecem bônus de transferência (ex: "Transfira Livelo para LATAM com 100% de bônus"). Isso dobra o valor dos pontos temporariamente.

**O que faz:**
Mantém um registro de promoções ativas e alerta o usuário quando uma promoção torna a transferência vantajosa.

**Implementação:**

```
Novo arquivo: data/cards/transfer_promotions.json

[
  {
    "id": "livelo-latam-fev26",
    "loyalty_program": "livelo",
    "partner": "LATAM Pass",
    "bonus_pct": 100,
    "effective_rate_per_1000": 32.0,      # dobro do normal
    "start_date": "2026-02-15",
    "end_date": "2026-03-15",
    "min_points": 1000,
    "source": "manual",
    "last_verified": "2026-02-28"
  }
]
```

```
Novo arquivo: app/optimizer/promotion_tracker.py

class PromotionTracker:
    def get_active_promotions(self) -> list[TransferPromotion]
    def check_user_opportunities(
        self, user_cards: list[str], user_points_balance: dict
    ) -> list[PromotionAlert]
```

**Saída ao usuário:**
> *"🔥 Promoção ativa: Livelo → LATAM com 100% de bônus até 15/03. Seus pontos valem o dobro agora (R$ 32/mil vs R$ 16/mil normalmente). Se você tem pontos acumulados, vale transferir."*

**Prioridade: 🟢 BAIXA (V2)** — Alto valor percebido mas requer manutenção manual dos dados de promoções. Pode ser automatizado no futuro com web scraping.

---

## F1 — CORE ENGINE: Melhorias

### M1.1 — Detecção de Anomalias de Gasto

**O problema:** O sistema projeta o futuro mas não alerta sobre gastos anômalos no presente. Um gasto fora do padrão pode indicar fraude, cobrança indevida ou simplesmente um mês atípico.

**O que faz:**
Compara cada transação contra o padrão histórico do usuário naquela categoria e merchant.

**Implementação:**

```
Novo arquivo: app/etl/anomaly_detector.py

class AnomalyDetector:
    def detect(
        self,
        transactions_df: pl.DataFrame,
        history_df: pl.DataFrame,
        lookback_months: int = 3
    ) -> list[Anomaly]

Anomaly:
    transaction_id: str
    type: AnomalyType          # UNUSUAL_AMOUNT | NEW_MERCHANT | FREQUENCY_SPIKE | DUPLICATE_SUSPECT
    severity: str              # INFO | WARNING | ALERT
    description: str           # "Gasto de R$ 890 em Alimentação — 3x acima da sua média"
    baseline_value: float      # média ou mediana histórica
    actual_value: float        # valor da transação anômala
    deviation_factor: float    # quanto desviou (ex: 3.2x acima)
```

**Regras de detecção:**
```python
# 1. Valor fora do padrão por categoria
category_stats = history.group_by("category").agg(
    pl.col("amount").mean().alias("avg"),
    pl.col("amount").std().alias("std")
)
if tx.amount > avg + 2 * std:  # 2 desvios padrão
    anomalies.append(Anomaly(type="UNUSUAL_AMOUNT", severity="WARNING"))

# 2. Merchant nunca visto antes com valor alto
if tx.merchant not in known_merchants and abs(tx.amount) > 200:
    anomalies.append(Anomaly(type="NEW_MERCHANT", severity="INFO"))

# 3. Frequência anormal (ex: 3 gastos em restaurante no mesmo dia)
daily_count = transactions_today.filter(category=tx.category).count()
if daily_count > avg_daily_count * 3:
    anomalies.append(Anomaly(type="FREQUENCY_SPIKE", severity="WARNING"))

# 4. Possível cobrança duplicada (mesmo merchant, mesmo valor, <48h)
if has_similar_recent(tx, window_hours=48):
    anomalies.append(Anomaly(type="DUPLICATE_SUSPECT", severity="ALERT"))
```

**Integração:**
- Novo estágio no ETL (entre classificação e recurrence detection)
- Anomalias aparecem no `GET /alerts/{user_id}` com type `SPENDING_ANOMALY`
- Agente menciona proativamente: *"Notei um gasto incomum de R$ 890 em alimentação ontem — 3x acima do seu padrão. Foi intencional?"*

**Prioridade: 🔴 ALTA** — Proteção direta do usuário. Alto valor percebido.

---

### M1.2 — Alerta de Velocidade de Gasto ("Burn Rate")

**O problema:** O safe-to-spend diz quanto pode gastar no total, mas não avisa quando o ritmo de gasto está acelerando. O usuário pode estar gastando a margem rápido demais.

**O que faz:**
Compara o ritmo de gasto acumulado vs o ritmo esperado (linear) e alerta quando o usuário está gastando mais rápido do que deveria.

**Saída ao usuário:**
> *"⚠️ Você já gastou 72% do seu orçamento de alimentação e estamos no dia 15 do mês. No ritmo atual, vai ultrapassar em R$ 380 até o fim do mês."*

**Implementação:**

```
Novo arquivo: app/cashflow/burn_rate.py

class BurnRateAnalyzer:
    def analyze(
        self,
        transactions_df: pl.DataFrame,
        profile: UserProfile,
        current_day_of_month: int
    ) -> BurnRateReport

BurnRateReport:
    overall_burn_rate: float             # 0-1 (% do budget total já gasto)
    expected_burn_rate: float            # dia_atual / dias_no_mês
    burn_rate_ratio: float               # actual / expected (>1.2 = alerta)
    categories_over_pace: list[CategoryBurnRate]
    projected_overshoot: float           # quanto vai ultrapassar se manter ritmo
    alert_level: str                     # OK | ATTENTION | WARNING | CRITICAL

CategoryBurnRate:
    category: str
    spent_so_far: float
    monthly_budget: float                # média histórica como "budget implícito"
    pct_consumed: float
    projected_total: float               # extrapolação linear
    overshoot: float                     # quanto vai ultrapassar (0 se dentro)
```

**Lógica:**
```python
day_of_month = current_date.day
days_in_month = calendar.monthrange(year, month)[1]
expected_pct = day_of_month / days_in_month

for category, budget in historical_avg_by_category.items():
    spent = transactions_this_month.filter(category=category).sum()
    actual_pct = spent / budget
    if actual_pct > expected_pct * 1.2:  # 20% acima do ritmo esperado
        over_pace.append(CategoryBurnRate(...))
```

**Integração:**
- Injetado no `GET /forecast/{user_id}` como campo `burn_rate`
- Aparece nos alertas quando `burn_rate_ratio > 1.3`
- Agente usa proativamente: *"Cuidado com alimentação este mês — ritmo 40% acima do normal."*

**Prioridade: 🔴 ALTA** — Transformação de dados passivos em insight acionável.

---

### M1.3 — Orçamento Inteligente por Categoria

**O problema:** O sistema conhece o padrão de gasto do usuário mas não sugere orçamentos. O usuário não sabe quanto deveria gastar por categoria.

**O que faz:**
Baseado no histórico de 3+ meses, sugere limites por categoria usando a regra 50/30/20 adaptada ao perfil real.

**Saída:**
> *"Com base nos seus últimos 3 meses, seu padrão de gasto é: Essenciais 58% (acima do ideal de 50%), Lazer 28% (dentro do esperado), Poupança 14% (abaixo do ideal de 20%). Sugestão: reduza R$ 380/mês em alimentação para equilibrar."*

**Implementação:**

```
Novo arquivo: app/cashflow/budget_advisor.py

class BudgetAdvisor:
    def suggest_budget(
        self,
        profile: UserProfile,
        transactions_df: pl.DataFrame
    ) -> BudgetSuggestion

BudgetSuggestion:
    income: float
    current_allocation: dict[str, CategoryAllocation]
    suggested_allocation: dict[str, CategoryAllocation]
    savings_gap: float                   # quanto falta para meta de poupança
    actionable_cuts: list[BudgetCut]     # cortes sugeridos com justificativa
    rule_applied: str                    # "50/30/20 adaptado"

CategoryAllocation:
    category: str
    current_amount: float
    current_pct: float
    suggested_amount: float
    suggested_pct: float
    status: str                          # WITHIN | OVER | UNDER

BudgetCut:
    category: str
    current: float
    suggested: float
    saving: float
    reasoning: str                       # "Seu gasto em delivery é 2x a média"
```

**Classificação de categorias na regra 50/30/20:**
```python
ESSENTIALS = ["moradia", "alimentacao", "transporte", "saude", "educacao"]  # 50%
WANTS = ["lazer", "vestuario"]                                              # 30%
SAVINGS = ["investimentos", "poupanca"]                                     # 20%
```

**Prioridade: 🟡 MÉDIA** — Valor educativo alto, mas requer cuidado para não ser paternalista.

---

### M1.4 — Análise de Estabilidade de Renda

**O problema:** Para freelancers e autônomos, a renda é irregular. O safe-to-spend atual assume renda estável.

**O que faz:**
Detecta padrões de renda (CLT fixo vs freelancer variável) e ajusta o safe-to-spend com buffer proporcional à variabilidade.

**Implementação:**

```
Novo campo no UserProfile (via profiler):

income_pattern: IncomePattern
    type: str                    # "CLT_FIXED" | "VARIABLE" | "MIXED" | "UNKNOWN"
    coefficient_of_variation: float  # desvio padrão / média (0 = fixo, >0.3 = muito variável)
    min_monthly_income: float    # pior mês dos últimos 6
    max_monthly_income: float    # melhor mês dos últimos 6
    suggested_buffer_pct: float  # buffer sugerido (15% para CLT, 30% para variável)
```

**Impacto no safe-to-spend:**
```python
if income_pattern.type == "VARIABLE":
    safety_buffer = 0.30  # 30% ao invés de 15%
    # Usa min_monthly_income como base ao invés de média
    base_income = income_pattern.min_monthly_income
```

**Prioridade: 🟡 MÉDIA** — Muito relevante para o público brasileiro (muitos CLT + freela).

---

### M1.5 — Detecção de Assinaturas Esquecidas

**O problema:** Pessoas pagam assinaturas que não usam mais (streaming, apps, etc.).

**O que faz:**
Identifica assinaturas recorrentes e destaca as que podem ser desnecessárias baseado em heurísticas.

**Heurísticas de "possivelmente esquecida":**
```python
# 1. Mesma categoria, múltiplos serviços (ex: 3 streamings de vídeo)
if count_subscriptions_in_category("streaming_video") > 2:
    flag("Você tem 3 serviços de streaming de vídeo — R$ X/mês total")

# 2. Valor muito baixo (< R$ 15) — fácil de esquecer
if subscription.amount < 15:
    flag(f"{subscription.merchant}: R$ {amount}/mês — ainda usa?")

# 3. Aumentou de preço recentemente
if current_amount > previous_amount * 1.1:
    flag(f"{merchant} aumentou de R$ {old} para R$ {new} (+{pct}%)")
```

**Saída:**
> *"Encontrei 8 assinaturas ativas totalizando R$ 287/mês. Destaque: você tem Netflix (R$ 55), Disney+ (R$ 34) e Amazon Prime Video (R$ 15) — 3 serviços de streaming somando R$ 104/mês. Vale revisar se usa todos."*

**Prioridade: 🟡 MÉDIA** — Alto valor percebido, implementação simples sobre a detecção de recorrência já existente.

---

## F3 — NEXA ARCHITECT: Melhorias

### M3.1 — Ajuste por Inflação

**O problema:** O simulador compara valores nominais. R$ 100 mil daqui a 10 anos valem muito menos que R$ 100 mil hoje.

**O que faz:**
Adiciona projeção de inflação (IPCA) nos cálculos de investimento e mostra o valor real (ajustado).

**Implementação:**

```
Novo conector: app/architect/connectors/ipca.py

class IPCAConnector(BaseConnector):
    # Fonte: SGS série 433 (IPCA acumulado 12 meses)
    # Fallback: 4.5% a.a. (meta do BCB)

Atualizar: strategy_engine.py

# No cálculo de investimento:
fv_nominal = calculate_fv(pmt, rate, months)
fv_real = fv_nominal / (1 + ipca_annual) ** (months / 12)

# Exibir ambos:
"Em 5 anos você acumula R$ 180.000 (nominal) / R$ 148.000 (valor de hoje)"
```

**Prioridade: 🟡 MÉDIA** — Melhora muito a qualidade da comparação em prazos longos.

---

### M3.2 — Impacto do Imposto de Renda nos Investimentos

**O problema:** O simulador projeta rendimento bruto. Na prática, investimentos em renda fixa têm IR regressivo (22,5% a 15%).

**O que faz:**
Aplica a tabela regressiva de IR sobre o rendimento projetado.

**Tabela IR para renda fixa (Brasil):**
```python
IR_TABLE = [
    (180,   0.225),   # até 180 dias: 22,5%
    (360,   0.200),   # 181 a 360 dias: 20%
    (720,   0.175),   # 361 a 720 dias: 17,5%
    (99999, 0.150),   # acima de 720 dias: 15%
]
```

**Implementação:**
```python
def apply_ir(gross_gain: float, holding_days: int) -> float:
    rate = next(r for days, r in IR_TABLE if holding_days <= days)
    return gross_gain * (1 - rate)
```

**Impacto na comparação:**
- Financiamento: sem alteração (não tem IR)
- Investimento: rendimento líquido menor → pode mudar a recomendação
- Consórcio: sem alteração

**Prioridade: 🔴 ALTA** — IR pode mudar completamente a recomendação. Sem isso, o cálculo de investimento é otimista demais.

---

### M3.3 — Custo de Oportunidade Cruzado com F2

**O problema:** O Architect compara estratégias de aquisição, mas não considera que o dinheiro gasto em parcelas poderia estar gerando retorno em cartão de crédito.

**O que faz:**
Calcula quanto de pontos/cashback o usuário ganharia se pagasse as parcelas no cartão de crédito (quando possível).

**Exemplo:**
> *"Se você financiar e pagar as parcelas de R$ 2.800/mês no cartão Ultravioleta, gera ~R$ 540/ano em pontos — reduzindo o custo efetivo do financiamento."*

**Implementação:**
- O Architect chama o Optimizer para simular o retorno do cartão ótimo sobre o valor da parcela
- Campo novo no `SimulationResponse`: `card_optimization_bonus`
- Ajusta o NPV do financiamento para incluir o retorno do cartão

**Prioridade: 🟢 BAIXA** — Sofisticado, mas depende de F2 estar maduro.

---

### M3.4 — Cenário "E se eu esperar X meses?"

**O problema:** O sistema diz "invista" ou "financie" agora. Mas às vezes esperar 6 meses acumulando entrada muda completamente a equação.

**O que faz:**
Simula múltiplos cenários de "timing": comprar agora vs esperar 3/6/12 meses acumulando entrada.

**Implementação:**

```
Novo método em strategy_engine.py:

def simulate_timing_scenarios(
    self,
    request: SimulationRequest,
    monthly_savings: float,              # quanto o usuário pode poupar/mês
    scenarios: list[int] = [0, 3, 6, 12] # meses de espera
) -> list[TimingScenario]

TimingScenario:
    wait_months: int
    accumulated_down_payment: float      # entrada original + poupança × meses
    new_principal: float                 # target - nova entrada
    recommended_strategy: StrategyType
    total_cost_npv: float                # custo total em valor presente
    monthly_payment: float               # nova parcela (menor se esperou)
    comparison_text: str
```

**Saída:**
> *"Se comprar agora: parcela de R$ 2.800/mês por 48 meses (custo total R$ 134.400). Se esperar 6 meses poupando R$ 2.000/mês: entrada de R$ 32.000 → parcela de R$ 2.100/mês por 42 meses (custo total R$ 120.200). Economia de R$ 14.200."*

**Prioridade: 🟡 MÉDIA** — Insight valioso para quem está planejando compras grandes.

---

## F4 — PF/PJ CLASSIFIER: Melhorias

### M4.1 — Relatório Fiscal Automatizado

**O problema:** O sistema separa PF/PJ mas não gera relatório útil para a declaração de IR.

**O que faz:**
Gera um resumo mensal/anual das transações PJ com categorização fiscal.

**Saída:**
```
Relatório Fiscal — Janeiro/2026
================================
Receitas PJ:     R$ 12.400 (4 transações)
Despesas PJ:     R$  3.200 (12 transações)
  - Software:    R$    800
  - Marketing:   R$  1.200
  - Transporte:  R$    400
  - Outros:      R$    800
Lucro estimado:  R$  9.200
DAS estimado:    R$    920 (Simples Nacional — faixa 1)
```

**Prioridade: 🟡 MÉDIA** — Muito útil para MEIs e microempresas. Requer categorização PJ mais granular.

---

### M4.2 — Categorização PJ Granular

**O problema:** Hoje a classificação é binária (PF/PJ/UNCERTAIN). Transações PJ não têm subcategorias.

**Novas categorias PJ:**
```python
PJ_CATEGORIES = [
    "receita_servicos",        # NFs de serviço
    "receita_produtos",        # vendas de produtos
    "despesa_software",        # SaaS, ferramentas
    "despesa_marketing",       # anúncios, design
    "despesa_transporte",      # combustível, uber pro trabalho
    "despesa_equipamento",     # hardware, móveis
    "despesa_pessoal_pj",      # pró-labore, salário de funcionário
    "despesa_imposto",         # DAS, ISS, INSS
    "despesa_bancaria",        # tarifas, juros
    "despesa_outros_pj",       # não categorizado
]
```

**Prioridade: 🟡 MÉDIA** — Prerequisito para M4.1 (relatório fiscal).

---

### M4.3 — Detecção de Uso Misto

**O problema:** Algumas transações são parcialmente PF e parcialmente PJ (ex: plano de celular usado para trabalho e pessoal).

**O que faz:**
Identifica transações que podem ter uso misto e sugere % de rateio.

**Heurísticas:**
```python
MIXED_USE_CANDIDATES = {
    "telefone": 0.50,           # 50% PJ é comum
    "internet": 0.30,           # 30% PJ se trabalha de casa
    "combustivel": 0.40,        # 40% PJ se usa carro para trabalho
    "energia": 0.20,            # 20% PJ se home office
}
```

**Prioridade: 🟢 BAIXA** — Nicho específico, mas útil para declaração de IR.

---

## MELHORIAS CROSS-FUNCTIONAL

### MX.1 — Score Financeiro com Evolução Temporal

**O problema:** O health_score existe mas é um snapshot. O usuário não sabe se está melhorando ou piorando.

**O que faz:**
Persiste o score a cada execução e mostra evolução: gráfico de linha + tendência.

**Implementação:**

```sql
CREATE TABLE health_score_history (
    user_id VARCHAR NOT NULL,
    date VARCHAR NOT NULL,
    health_score INTEGER,
    savings_rate DOUBLE,
    profile_type VARCHAR,
    safe_to_spend DOUBLE,
    PRIMARY KEY (user_id, date)
);
```

```
Novo endpoint: GET /api/v1/health-score/history/{user_id}?months=6

Resposta:
{
  "current_score": 72,
  "trend": "IMPROVING",           // IMPROVING | STABLE | DECLINING
  "change_30d": +5,
  "change_90d": +12,
  "history": [
    {"date": "2025-12", "score": 60},
    {"date": "2026-01", "score": 67},
    {"date": "2026-02", "score": 72}
  ]
}
```

**Prioridade: 🔴 ALTA** — Gamificação leve que aumenta retenção.

---

### MX.2 — Sistema de Metas Financeiras

**O problema:** O sistema analisa o presente mas não ajuda o usuário a planejar o futuro.

**O que faz:**
Permite definir metas (ex: "juntar R$ 50k para entrada de apartamento em 2 anos") e acompanha o progresso.

**Implementação:**

```sql
CREATE TABLE financial_goals (
    goal_id VARCHAR PRIMARY KEY,
    user_id VARCHAR NOT NULL,
    name VARCHAR NOT NULL,               -- "Entrada do apartamento"
    target_amount DOUBLE NOT NULL,
    current_amount DOUBLE DEFAULT 0,
    target_date VARCHAR,
    monthly_contribution_needed DOUBLE,  -- calculado automaticamente
    status VARCHAR DEFAULT 'ACTIVE',     -- ACTIVE | COMPLETED | ABANDONED
    created_at VARCHAR NOT NULL
);
```

```
Novo arquivo: app/goals/tracker.py

class GoalTracker:
    def create_goal(self, user_id, name, target_amount, target_date) -> Goal
    def update_progress(self, goal_id, transactions_df) -> GoalProgress
    def get_projections(self, goal_id) -> GoalProjection

GoalProjection:
    on_track: bool
    projected_completion_date: date
    monthly_needed: float
    current_monthly_actual: float
    gap: float                           # quanto falta por mês
    suggestion: str                      # "Aumente R$ 200/mês para atingir a meta"
```

**Integração com F3:**
- Meta de compra de imóvel → aciona automaticamente o Architect para simular financiamento vs investimento
- Meta de viagem → Optimizer sugere cartão que acumula milhas relevantes

**Prioridade: 🔴 ALTA** — Feature de produto que cria engajamento de longo prazo.

---

### MX.3 — Notificações Proativas Inteligentes

**O problema:** O sistema só gera insights quando o usuário pede. Muito do valor vem de alertar proativamente.

**O que faz:**
Gera notificações baseadas em regras + eventos detectados.

**Tipos de notificação:**

```python
NOTIFICATION_RULES = [
    # Alerta de gasto
    ("BURN_RATE_HIGH", "Você já gastou {pct}% do orçamento de {category} no dia {day}"),
    ("ANOMALY_DETECTED", "Gasto incomum: R$ {amount} em {merchant} — {factor}x acima do padrão"),
    ("SUBSCRIPTION_INCREASE", "{merchant} aumentou de R$ {old} para R$ {new}"),

    # Oportunidade
    ("CARD_OPPORTUNITY", "Nos últimos 3 meses você deixou de ganhar R$ {amount} — vale trocar de cartão"),
    ("WAIVER_ALERT", "Faltam R$ {amount} para isentar a anuidade do {card} — gaste mais R$ {daily}/dia"),
    ("TRANSFER_PROMO", "Livelo → LATAM com {bonus}% de bônus até {date} — seus pontos valem o dobro"),

    # Saúde financeira
    ("SCORE_IMPROVED", "Seu score financeiro subiu de {old} para {new} — parabéns! 🎉"),
    ("GOAL_PROGRESS", "Meta '{goal}': {pct}% concluída — faltam R$ {remaining}"),
    ("SAFE_TO_SPEND_LOW", "Sua margem segura caiu para R$ {amount}/dia — cuidado nos próximos dias"),
]
```

**Prioridade: 🔴 ALTA** — Transforma a Nexa de "ferramenta que consulto" para "assistente que me avisa".

---

### MX.4 — Comparação Anônima com Perfis Similares

**O problema:** O usuário não sabe se gasta muito ou pouco em comparação com outras pessoas na mesma faixa.

**O que faz:**
Compara o perfil do usuário com benchmarks agregados e anônimos.

**Saída:**
> *"Você gasta 35% da renda em moradia — a média para sua faixa de renda é 28%. Em contrapartida, seu gasto com lazer (12%) está abaixo da média (18%). Seu índice de poupança (14%) está na faixa 'bom' — top 40% dos perfis similares."*

**Nota:** Para o MVP, os benchmarks podem ser hardcoded baseados em pesquisas do IBGE/POF. Em produção, usar dados agregados anônimos da própria base.

**Prioridade: 🟢 BAIXA (V2)** — Requer massa de dados ou dados públicos do IBGE. Valor alto mas implementação depende de escala.

---

## INTEGRAÇÃO DO INCOMEPROFILE — Oportunidades de Precisão

> **Contexto:** O `IncomeProfiler` (`app/etl/income_profiler.py`) foi implementado como módulo foundational. Ele filtra transferências, estornos e rendimentos, classifica o padrão de renda (CLT | PJ | MIXED | UNKNOWN) e retorna `confidence` (0–1). Abaixo, todas as integrações pendentes — ordenadas por impacto.

---

### MI.1 — Calibrar Thresholds de Anomalia por % da Renda ✅ FEITO

**Arquivo:** `app/etl/spending_anomaly_detector.py`

**O problema:** Thresholds fixos descontextualizados da renda:
- `_NEW_MERCHANT_MIN_VALUE = R$ 200` — para renda de R$ 2k/mês é 10% (relevante); para R$ 15k/mês é 1,3% (ruído)
- `_UNUSUAL_SIGMA = 2.0` — detecta desvios da média histórica de gastos, mas quem tem renda PJ variável tem gastos naturalmente mais voláteis → alertas em excesso

**O que mudar:**
```python
# Aceitar monthly_income opcional em SpendingAnomalyDetector.detect()
# Derivar threshold dinâmico:
new_merchant_threshold = monthly_income * 0.05 if monthly_income else _NEW_MERCHANT_MIN_VALUE
# → R$ 200 fixo se renda desconhecida
# → R$ 500 para renda de R$ 10k/mês (5%)
# → R$ 100 para renda de R$ 2k/mês (5%)
```

**Prioridade: 🔴 ALTA** — Reduz ruído de alertas para usuários de alta renda e aumenta sensibilidade para baixa renda.

---

### MI.2 — UserProfileAnalyzer: Renda Filtrada no Health Score ✅ FEITO

**Arquivo:** `app/etl/profiles.py`

**O problema:** `_calculate_health_score()` usava `total_income` (soma bruta de créditos), inflando savings_rate em 2-3× para usuários multi-banco.

**O que foi feito (2026-03-01):**
- `analyze()` aceita `income_profile: IncomeProfile | None = None`
- Novo método `_resolve_income_reference()`: usa `income_profile.monthly_net_income × n_meses` se `confidence ≥ 0.5`, senão fallback bruto
- `UserProfile` recebe campo `income_net_monthly: float | None` — `None` sinaliza que foi usado fallback bruto
- `_calculate_trend()` reescrita para comparar totais mensais (não por transação)
- Comentários de threshold no health_score corrigidos
- `_determine_profile_type()` teve parâmetro morto `expenses` removido

---

### MI.3 — compute_eligibility_score: Penalizar Renda PJ Instável ✅ FEITO

**Arquivo:** `app/optimizer/card_loader.py`

**O problema:** `compute_eligibility_score()` trata renda CLT e PJ identicamente:
```python
income_ratio = annual_income / card.min_income
# >= 2.0 → 0.95 pts  — igual para CLT fixo e PJ variável com mesma média
```
Para cartões com anuidade alta, PJ com `income_stability < 0.5` tem risco real de não conseguir pagar anuidade em meses ruins.

**O que mudar:**
```python
# Receber income_profile opcional e aplicar penalidade ao score
if income_profile and income_profile.income_pattern == IncomePattern.PJ:
    stability_penalty = max(0.0, (0.5 - income_profile.income_stability) * 0.3)
    eligibility_score -= stability_penalty
    reason = f"Renda PJ com estabilidade {income_profile.income_stability:.0%} — risco de inadimplência em anuidade alta"
```

**Prioridade: 🔴 ALTA** — Evita recomendar cartões premium para usuários com renda variável que não conseguirão sustentar a anuidade.

---

### MI.4 — CardSimulator: income_stability no Confidence Score ✅ FEITO

**Arquivo:** `app/optimizer/simulator.py`

**O problema:** `_compute_confidence()` usa `spending_stability` e `coverage_months`, mas ignora `income_profile.income_stability`. Usuário com gasto estável e renda PJ errática (stability 0.3) parece confiável quando não é.

**O que mudar:**
```python
# Adicionar income_stability ao cálculo de confidence
income_weight = 0.20  # novo fator
income_factor = income_profile.income_stability if income_profile else 0.5
confidence = (
    spending_stability * 0.40 +
    bank_trust         * 0.40 +
    income_factor      * income_weight  # renda instável → confidence baixa
)
```

**Prioridade: 🟡 MÉDIA** — Melhora a qualidade das simulações para autônomos e freelancers.

---

### MI.5 — BurnRateAnalyzer: Alertar por % da Renda Real ✅ FEITO

**Arquivo:** `app/cashflow/burn_rate.py`

**O problema:** Os thresholds de alerta comparam gasto contra média histórica, não contra renda:
```python
_ATTENTION_RATIO = 1.10  # gasto > 110% da média histórica
_WARNING_RATIO   = 1.30
_CRITICAL_RATIO  = 1.50
```
Se `monthly_income` estiver disponível, faz muito mais sentido alertar quando `total_spent > monthly_income * ratio`.

**O que mudar:** Quando `monthly_income` disponível, calcular `income_ratio = total_spent / monthly_income` e usar para o `alert_level` ao lado (ou no lugar) do ratio histórico. Já existe `income_ratio` no `BurnRateReport` — basta usá-lo para derivar o `alert_level` quando disponível.

**Prioridade: 🟡 MÉDIA** — Alerta mais preciso para quem tem renda irregular.

---

### MI.6 — Alertas Contextualizados com Renda Real ✅ FEITO

**Arquivo:** `app/api/v1/routes/alerts.py`

**O problema:** O alerta de `HIGH_COMMITMENT` diz "X% do caixa comprometido", sem referência de renda.

**O que mudar:** Quando `income_profile.confidence ≥ 0.5`, contextualizar os alertas:
- Hoje: *"80% do caixa comprometido com shadow invoices"*
- Com renda: *"R$ 3.400 em shadow invoices representa 40% da sua renda mensal estimada (R$ 8.500)"*

**Prioridade: 🟡 MÉDIA** — Transforma alertas genéricos em insights acionáveis.

---

### MI.7 — forecast.py: Expor income_profile na Resposta ✅ FEITO

**Arquivo:** `app/api/v1/routes/forecast.py`

**O problema:** O endpoint `/forecast/{user_id}` retorna `total_income` e `savings_rate` mas não expõe `income_profile.confidence`. O frontend não sabe distinguir estimativa confiável de estimativa grosseira.

**O que adicionar:**
```json
"income_estimate": {
  "monthly_net_income": 8500.0,
  "income_pattern": "CLT",
  "confidence": 0.85,
  "confidence_label": "Alta",
  "note": null
}
// Quando confidence < 0.5:
"income_estimate": {
  "monthly_net_income": 4200.0,
  "confidence": 0.28,
  "confidence_label": "Baixa",
  "note": "Informe sua renda mensal para melhorar a precisão das recomendações"
}
```

**Prioridade: 🟢 BAIXA** — Melhora transparência para o frontend e usuário final.

---

### MI.8 — Agent Tool: LLM recebe confidence da Renda ✅ FEITO

**Arquivo:** `app/agent/tools/get_card_optimization.py`

**O problema:** A tool retorna a otimização mas não sinaliza ao LLM quando a renda usada tinha `confidence < 0.5`. O agente apresenta recomendações como se fossem certeiras quando a base de renda é frágil.

**O que mudar:** Incluir no retorno da tool:
```python
"income_confidence": report.income_confidence,  # float ou None
"income_warning": (
    "Renda estimada com baixa confiança. Confirme sua renda mensal para recomendações mais precisas."
    if income_confidence and income_confidence < 0.5 else None
)
```
O LLM então pode perguntar ao usuário antes de apresentar as recomendações.

**Prioridade: 🟢 BAIXA** — Melhora a qualidade da conversa do agente.

---

### Tabela de Status — Integrações do IncomeProfile

| # | Arquivo | O que integrar | Status |
|---|---|---|---|
| MI.1 | `spending_anomaly_detector.py` | Thresholds dinâmicos por % da renda | ✅ **Feito** (2026-03-02) |
| MI.2 | `etl/profiles.py` | Renda filtrada no health_score e savings_rate | ✅ **Feito** (2026-03-01) |
| MI.3 | `optimizer/card_loader.py` | Penalizar score de PJ com income_stability < 0.5 | ✅ **Feito** (2026-03-02) |
| MI.4 | `optimizer/simulator.py` | income_stability no confidence do cartão simulado | ✅ **Feito** (2026-03-02) |
| MI.5 | `cashflow/burn_rate.py` | alert_level por % da renda quando disponível | ✅ **Feito** (2026-03-02) |
| MI.6 | `api/v1/routes/alerts.py` | Contextualizar alertas com renda absoluta e % | ✅ **Feito** (2026-03-02) |
| MI.7 | `api/v1/routes/forecast.py` | Expor income_profile (pattern + confidence) na resposta | ✅ **Feito** (2026-03-02) |
| MI.8 | `agent/tools/get_card_optimization.py` | Sinalizar confidence ao LLM | ✅ **Feito** (2026-03-02) |

---

## PRIORIZAÇÃO FINAL — Roadmap Sugerido

### Sprint 1 (Impacto imediato — F2 + F1) — ✅ CONCLUÍDA

| # | Melhoria | Funcionalidade | Esforço | Status |
|---|---|---|---|---|
| 1 | M2.1 — Custo de Oportunidade | F2 | 2-3 dias | ✅ Feito |
| 2 | M1.1 — Detecção de Anomalias | F1 | 2-3 dias | ✅ Feito |
| 3 | M3.2 — IR nos Investimentos | F3 | 1 dia | ✅ Feito |
| 4 | M1.2 — Burn Rate | F1 | 1-2 dias | ✅ Feito |
| 4b | M1.4→ IncomeProfiler (renda real filtrada) | F1/Cross | 2 dias | ✅ Feito |
| 4c | MI.2 — Health score com renda filtrada | F1/IncomeProfile | 0.5 dia | ✅ Feito |
| 5 | MX.1 — Score com Evolução | Cross | 1-2 dias | ✅ Feito (2026-03-03) |

### Sprint 2 (Diferenciação — F2 avançado + IncomeProfile cascade)

| # | Melhoria | Funcionalidade | Esforço | Status |
|---|---|---|---|---|
| 6 | MI.1 — Thresholds de anomalia por % da renda | F1/IncomeProfile | 0.5 dia | ✅ Feito |
| 7 | MI.3 — Penalizar PJ instável em card_loader | F2/IncomeProfile | 0.5 dia | ✅ Feito |
| 8 | MI.4 — income_stability no simulator confidence | F2/IncomeProfile | 0.5 dia | ✅ Feito |
| 9 | MI.5 — BurnRate: alert_level por % da renda | F1/IncomeProfile | 0.5 dia | ✅ Feito |
| 10 | MI.6 — Alertas contextualizados com renda | API/IncomeProfile | 1 dia | ✅ Feito |
| 11 | M2.2 — Multi-Cartão | F2 | 3-4 dias | ✅ Feito |
| 12 | M2.5 — Cashback por Categoria | F2 | 1-2 dias | ✅ Feito (2026-03-03) |
| 13 | M2.4 — ROI do Cartão Atual | F2 | 1-2 dias | ✅ Feito (2026-03-03) |
| 14 | M1.5 — Assinaturas Esquecidas | F1 | 1 dia | ✅ Feito (2026-03-03) |
| 15 | MX.2 — Metas Financeiras | Cross | 2-3 dias | ✅ Feito (2026-03-03) |

### Sprint 3 (Completude)

| # | Melhoria | Funcionalidade | Esforço | Status |
|---|---|---|---|---|
| 16 | MI.7 — forecast.py expõe income_profile | API/IncomeProfile | 0.5 dia | ✅ Feito |
| 17 | MI.8 — Agent tool sinaliza confidence ao LLM | Agent/IncomeProfile | 0.5 dia | ✅ Feito |
| 18 | MX.1 — Score com Evolução Temporal | Cross | 1-2 dias | ⏳ Pendente |
| 19 | M2.3 — Valoração de Milhas | F2 | 1-2 dias | ⏳ Pendente |
| 20 | M3.1 — Inflação (IPCA) | F3 | 1 dia | ✅ Feito (2026-03-03) |
| 21 | M3.4 — "E se eu esperar?" | F3 | 2-3 dias | ⏳ Pendente |
| 22 | M1.3 — Orçamento Inteligente | F1 | 2 dias | ⏳ Pendente |
| 23 | MX.3 — Notificações Proativas | Cross | 2-3 dias | ⏳ Pendente |

### V2 (Futuro)

| # | Melhoria | Funcionalidade |
|---|---|---|
| 17 | M2.6 — Promoções de Transferência | F2 | ✅ Feito (2026-03-03) |
| 18 | M3.3 — Custo de Oportunidade Cruzado | F3 |
| 19 | M4.1 — Relatório Fiscal | F4 |
| 20 | M4.2 — Categorização PJ Granular | F4 |
| 21 | M4.3 — Uso Misto | F4 |
| 22 | MX.4 — Comparação com Pares | Cross |

---

## COMO USAR ESTE DOCUMENTO

1. **Escolha a sprint** — comece pela Sprint 1 (maior impacto, menor esforço)
2. **Para cada melhoria**, este doc contém:
   - O problema que resolve
   - Exemplo concreto de saída ao usuário
   - Especificação técnica (modelos, algoritmos, integração)
   - Prioridade e esforço estimado
3. **Me peça para implementar** qualquer melhoria — digo qual arquivo criar, que testes escrever, e como integrar com o código existente
4. **Itere** — depois de implementar, podemos refinar e expandir

---

*Documento gerado em 2026-02-28 com base na análise completa do codebase Nexa AI.*