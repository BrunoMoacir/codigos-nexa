# Upgrade: Recomendações Financeiras Inteligentes
**Versão:** 2.0  
**Data:** 2026-04-03  
**Escopo:** F7 (Compra Inteligente) · F3 (Architect) · F1 (Safe-to-Spend)

---

## ✅ Status de Implementação

| # | Mudança | Arquivo(s) | Status |
|---|---|---|---|
| 1 | Novos campos nos modelos | `purchase/models.py` | ✅ Feito |
| 2 | Limiares relativos à renda | `forecast/cashflow/safe_to_spend.py` | ✅ Feito |
| 3 | Custo de oportunidade CDI | `purchase/opportunity_cost.py` (novo) | ✅ Feito |
| 4 | Score de pressão de perfil | `purchase/profile_context.py` (novo) | ✅ Feito |
| 5 | Pressão de fatura | `forecast/cashflow/invoice_horizon.py` (novo) | ✅ Feito |
| 6 | Refatorar PurchaseAdvisor | `purchase/purchase_advisor.py` | ✅ Feito |
| 7 | Benchmark Architect por perfil | `architect/simulators/strategy_engine.py` | ⏳ Pendente |
| 8 | Inferir risk_profile + CardBonus real | `architect/services/architect_service.py` | ⏳ Pendente |

---

## 1. Diagnóstico: O que está errado hoje

### 1.1 Compra Inteligente sempre favorece à vista

O `PurchaseAdvisor` (`purchase/purchase_advisor.py:115`) ordena opções por:
```python
net_cost = total_cost - reward_value
```

Como pagamento à vista nunca tem juros, nunca perde no ranking. O problema é que **capital imobilizado tem custo real** — com Selic ~13% a.a., parcelado sem juros pode ser genuinamente mais barato.

**Exemplo: compra R$ 5.000, 12x sem juros, CDI 13% a.a.**
```
À vista:       net_cost nominal = R$ 5.000
12x s/juros:   net_cost nominal = R$ 5.000 (empate)
               capital liberado mês a mês → rende ~R$ 320 no CDI
               net_cost real    = R$ 4.680 ← 6,4% mais barato
```
O sistema hoje escolhe à vista. O correto seria parcelado.

### 1.2 Perfil financeiro não influencia nada no F7

O `PurchaseAdvisor` não recebe nem consulta o `UserProfile` (`forecast/etl/profiles.py`). Um usuário CONSERVADOR com savings_rate de 25% e um GASTADOR no vermelho recebem exatamente a mesma recomendação.

### 1.3 Histórico de comportamento é ignorado

O sistema já tem:
- `SpendingAnomalyDetector` — detecta padrões incomuns por categoria
- `UserProfile.trend` — CRESCENTE/ESTÁVEL/DECRESCENTE nos gastos
- `UserProfile.top_categories` — onde o usuário mais gasta
- `ConsumptionProfiler.committed_percentage` — % da renda já comprometida

Nada disso alimenta o `PurchaseAdvisor`.

### 1.4 Faturas próximas não são consideradas

O safe-to-spend olha o saldo projetado para 30 dias, mas ignora que uma compra no cartão **não sai do saldo hoje** — cai na fatura, que vence em X dias.

Usuário com:
- Saldo atual: R$ 8.000
- Fatura fecha em 4 dias com R$ 6.500 já comprometidos
- `safe_to_spend` calculado: R$ 1.200 (parece ok)
- Nova compra de R$ 900 no cartão

→ Sistema diz "acessível". Fatura vai para R$ 7.400, mais que o saldo. Rotativo.

### 1.5 Limiares de risco são absolutos para todo mundo

```python
# safe_to_spend.py:287-292 — hardcoded para todos os usuários
CRITICAL: safe_to_spend ≤ 0
HIGH:     safe_to_spend < R$ 300
MEDIUM:   safe_to_spend < R$ 1.000
LOW:      safe_to_spend ≥ R$ 1.000
```

Para renda de R$ 3.000/mês, R$ 1.000 de safe-to-spend = 33% da renda (confortável).  
Para renda de R$ 20.000/mês, R$ 1.000 de safe-to-spend = 5% da renda (crítico).  
Os limiares precisam ser **relativos à renda**.

### 1.6 Architect: risk_profile é declarado, nunca inferido

O `strategy_engine.py` já tem lógica de ajuste por perfil (`_apply_risk_profile_adjustment`, linha 872) — mas o `risk_profile` vem da request manual do usuário, nunca do histórico real de comportamento. Usuário que diz ser "moderado" mas gasta 95% da renda todo mês recebe a mesma simulação de alguém que realmente poupa.

### 1.7 Architect: benchmark de investimento é único para todos os perfis

O `strategy_engine.py` usa sempre SELIC/CDI como taxa de retorno do SAVE_INVEST, independente do perfil de risco. Para um perfil agressivo, CDI subestima o retorno esperado e distorce a comparação a favor do financiamento.

### 1.8 CardOptimizationBonus no Architect usa valores fictícios

`architect_service.py:355-400` — o `_compute_card_optimization_bonus` usa hardcoded `pts_per_brl=2.0` e `point_value_brl=0.016` como "referência de mercado". O código inclusive marca isso como `"market_reference_estimate"` nos data_sources (linha 178), reconhecendo a limitação. A integração real com o cartão do usuário (F2/OptimizerService) ainda não existe.

---

## 2. Erros na versão anterior deste documento

### 2.1 Tipo "CARTAO" não existe nas shadow invoices

A v1.0 dizia: `"somar shadow invoices do tipo CARTAO"`.  
**Incorreto.** Os únicos tipos existentes são `"SUBSCRIPTION"` e `"INSTALLMENT"` (`schemas_shadow_invoice.py:74`). Não existe tipo `CARTAO`.

Para o `InvoiceHorizon`, a fonte correta é:
- Shadow invoices do tipo `INSTALLMENT` (parcelas em andamento)
- Shadow invoices do tipo `SUBSCRIPTION` (cobranças recorrentes mensais)
- Transações de crédito recentes ainda dentro do ciclo de fatura atual

### 2.2 Mapeamento GASTADOR → AGRESSIVO está conceitualmente errado

A v1.0 propôs:
```python
"GASTADOR": "AGRESSIVO"  # gastador geralmente aceita mais risco
```
**Incorreto.** GASTADOR (savings_rate < 10%) significa que o usuário gasta mais do que deveria, não que tem apetite a risco. Essas são dimensões independentes. Um gastador pode ser avesso a risco mas simplesmente ter pouca disciplina financeira. O mapeamento correto é:

```python
# Spending profile → default risk tolerance para Architect
"CONSERVADOR": "CONSERVADOR"  # poupa ≥ 20% → disciplinado, avesso a dívida
"EQUILIBRADO":  "MODERADO"    # poupa 10-20% → aceita algum risco
"GASTADOR":     "MODERADO"    # poupa < 10% → sem dados suficientes para inferir
                               # Tratado como moderado, com avisos sobre liquidez
```

O perfil GASTADOR gera avisos específicos mas não altera o benchmark de investimento — o risco de portfólio não é derivável do padrão de gastos.

### 2.3 Dois UserProfile diferentes existem no código

A v1.0 tratava `UserProfile` como um único objeto. Na verdade existem dois:

| Classe | Arquivo | Uso |
|---|---|---|
| `UserProfile` (financeiro) | `forecast/etl/profiles.py` | CONSERVADOR/EQUILIBRADO/GASTADOR, savings_rate, trend, health_score |
| `UserProfile` (consumo) | `optimizer/profiler.py` | committed_percentage, spend_by_category, spending_stability, data_coverage_months |

Para recomendações de compra, ambos são úteis:
- `profiles.py:UserProfile` → decide o nível de pressão/aviso
- `optimizer/profiler.py:UserProfile` → verifica `committed_percentage` e `spending_stability`

### 2.4 `risk_tolerance` vs `risk_profile` — nomenclatura inconsistente

A v1.0 propôs adicionar `risk_tolerance` ao `PurchaseRequest`. O Architect já usa `risk_profile` (enum `RiskProfile` com valores `"conservador"`, `"moderado"`, `"agressivo"` — minúsculas). Manter consistência: usar `risk_profile` no novo campo do `PurchaseRequest` também.

---

## 3. Mapa do que já existe (não recriar)

Antes de construir qualquer coisa nova, esses componentes já existem e devem ser **reutilizados**:

| Componente | Arquivo | O que fornece |
|---|---|---|
| `UserProfileAnalyzer` | `forecast/etl/profiles.py` | profile_type, savings_rate, trend, health_score, top_categories |
| `IncomeProfiler` | `forecast/etl/income_profiler.py` | monthly_net_income, income_pattern, confidence (0-1) |
| `ConsumptionProfiler` | `optimizer/profiler.py` | committed_percentage, spending_stability, data_coverage_months |
| `SpendingAnomalyDetector` | `forecast/etl/spending_anomaly_detector.py` | anomalias por categoria (UNUSUAL_AMOUNT, FREQUENCY_SPIKE) |
| `BudgetAdvisor` | `budget/budget_advisor.py` | 50/30/20 análise, surplus/déficit por grupo |
| `ShadowInvoice` | `forecast/schemas_shadow_invoice.py` | SUBSCRIPTION/INSTALLMENT, next_due_date, amount |
| `CashflowProjector` | `forecast/cashflow/projector.py` | projeção diária de saldo + eventos |
| `OptimizerService` | `optimizer/services/optimizer_service.py` | melhor cartão por categoria + reward_rate |
| `BacenConnector` | `architect/connectors/bacen.py` | SELIC atual |

---

## 4. Componentes novos necessários

```
backend/app/purchase/
├── purchase_advisor.py          (existente — refatorar)
├── models.py                    (existente — adicionar campos)
├── opportunity_cost.py          (NOVO — custo de oportunidade de capital)
└── profile_context.py           (NOVO — regras de adequação ao perfil)

backend/app/forecast/cashflow/
├── safe_to_spend.py             (existente — limiares relativos à renda)
└── invoice_horizon.py           (NOVO — pressão da fatura atual)
```

---

## 5. Fluxo novo do PurchaseAdvisor

```
PurchaseRequest
       │
       ├─ 1. Fetch transactions_df                    (já existe)
       ├─ 2. Fetch IncomeProfile        ─┐            (já existe — IncomeProfiler)
       ├─ 3. Fetch UserProfile (financeiro)├─ paralelo (já existe — UserProfileAnalyzer)
       ├─ 4. Fetch ConsumptionProfile   ─┘            (já existe — ConsumptionProfiler)
       ├─ 5. Fetch safe_to_spend                      (já existe — melhorar limiares)
       ├─ 6. Fetch InvoiceHorizon                     (NOVO)
       ├─ 7. Fetch best card                          (já existe — OptimizerService)
       ├─ 8. Fetch financing rate                     (já existe — BacenConnector)
       │
       ├─ 9.  Build payment options                   (já existe)
       ├─10.  Apply opportunity cost → net_cost_real  (NOVO)
       ├─11.  Score profile fit por opção             (NOVO — profile_context.py)
       ├─12.  Apply invoice pressure                  (NOVO — penaliza cartão)
       ├─13.  Pick recommendation                     (refatorar)
       └─14.  Build reasoning contextualizado         (refatorar)
```

---

## 6. Mudança 1: Custo de Oportunidade de Capital

**Arquivo:** `backend/app/purchase/opportunity_cost.py` (NOVO)

### Fórmula

O custo de oportunidade compara o que o capital **poderia render** no CDI vs o que rende de fato dado o plano de pagamento.

**Referência:** taxa CDI mensal líquida = `(1 + cdi_annual)^(1/12) - 1`, com IR de 15% aplicado ao rendimento (prazo ≥ 720 dias) ou 22,5% (< 180 dias).

**Opção 1 — PIX / cartão à vista:**
- Desembolso integral hoje. Capital não pode ser investido.
- `opportunity_cost = amount × cdi_net_monthly × n_meses_equivalentes`
- Onde `n_meses_equivalentes = 1` (curto prazo — simplificação conservadora)
- `net_cost_real = amount - reward + opportunity_cost`

**Opção 2 — Cartão parcelado sem juros (n parcelas):**
- Cada parcela `P/n` paga no mês `k`. Antes de pagar, o capital deferred rende.
- Ganho por parcela `k` (paga no mês k, referenciado ao mês n):
  - `ganho_k = (P/n) × ((1 + r_net)^(n-k) - 1)` onde r_net = cdi líquido mensal
- Ganho total = `Σ_{k=1}^{n} (P/n) × ((1 + r_net)^(n-k) - 1)`
- `net_cost_real = P - reward - ganho_total`

> **Nota:** esta fórmula calcula o ganho de manter capital investido mês a mês comparado ao desembolso imediato. Quanto mais longo o parcelamento e maior a taxa CDI, maior o ganho.

**Opção 3 — Financiamento com juros (CDC):**
- Juros são explícitos no `total_cost`. Não há ganho de oportunidade — o banco já precificou o tempo.
- `net_cost_real = total_cost - reward` (sem mudança)

### Parâmetros de entrada

| Parâmetro | Fonte | Fallback |
|---|---|---|
| `cdi_annual` | `BacenConnector.get_selic()` (SELIC ≈ CDI) | 0.1300 (13% a.a.) |
| `ir_rate` | Prazo do parcelamento via tabela regressiva | 0.225 (<180d), 0.20, 0.175, 0.15 |
| `apply_ir` | `PurchaseRequest.apply_opportunity_cost` | True |

### Impacto esperado com CDI 13% a.a. (r_net ≈ 1,02%/mês após IR)

| Compra | Parcelas | Ganho CDI | Net cost real | vs à vista |
|---|---|---|---|---|
| R$ 500 | 3x | R$ 5,10 | R$ 494,90 | -1,0% |
| R$ 2.000 | 6x | R$ 61,60 | R$ 1.938,40 | -3,1% |
| R$ 5.000 | 12x | R$ 307,00 | R$ 4.693,00 | -6,1% |
| R$ 10.000 | 18x | R$ 909,00 | R$ 9.091,00 | -9,1% |

Abaixo de R$ 300 em 1-3x a diferença é irrelevante (<R$5) — à vista pode ganhar por desconto negociado.

---

## 7. Mudança 2: Contexto de Perfil na Recomendação

**Arquivo:** `backend/app/purchase/profile_context.py` (NOVO)

### Inputs disponíveis (já existem, só conectar)

```python
# De forecast/etl/profiles.py
financial_profile.profile_type          # CONSERVADOR / EQUILIBRADO / GASTADOR
financial_profile.savings_rate          # % poupança real dos últimos meses
financial_profile.financial_health_score  # 0–100
financial_profile.trend                 # CRESCENTE / ESTÁVEL / DECRESCENTE
financial_profile.top_categories        # top 3 categorias de gasto
financial_profile.monthly_avg_expenses  # média mensal histórica

# De forecast/etl/income_profiler.py
income_profile.monthly_net_income       # renda líquida estimada (R$/mês)
income_profile.confidence               # 0–1 (qualidade da estimativa)

# De optimizer/profiler.py (ConsumptionProfiler)
consumption_profile.committed_percentage  # % da renda já comprometida
consumption_profile.spending_stability    # 0–1 (estabilidade dos gastos)
consumption_profile.data_coverage_months  # meses de dados disponíveis
```

### Score de pressão financeira

```python
def compute_pressure_score(
    savings_rate: float,
    trend: str,
    health_score: int,
    committed_pct: float,
    safe_to_spend_ratio: float,  # safe_to_spend / monthly_income
) -> float:
    """
    Retorna score 0.0 (sem pressão) a 1.0 (máxima pressão).
    Quanto maior, mais conservadora deve ser a recomendação.
    """
    score = 0.0

    # Savings rate (até 0.40)
    if savings_rate < 0:
        score += 0.40       # gastando mais do que ganha
    elif savings_rate < 5:
        score += 0.30
    elif savings_rate < 10:
        score += 0.20
    elif savings_rate < 20:
        score += 0.05

    # Tendência de gastos (até 0.20)
    if trend == "CRESCENTE":
        score += 0.20
    elif trend == "ESTÁVEL":
        score += 0.00

    # Comprometimento da renda (até 0.25)
    if committed_pct > 0.90:
        score += 0.25
    elif committed_pct > 0.80:
        score += 0.15
    elif committed_pct > 0.70:
        score += 0.05

    # Safe-to-spend vs renda (até 0.15)
    if safe_to_spend_ratio < 0.05:
        score += 0.15
    elif safe_to_spend_ratio < 0.15:
        score += 0.08

    return min(1.0, score)
```

### Efeito do pressure_score nas opções

O score **não bloqueia opções** — apenas muda a classificação e o texto. O usuário sempre vê todas as opções disponíveis.

| pressure_score | profile_fit das opções | Efeito no ranking |
|---|---|---|
| < 0.2 | Todas OK | Custo de oportunidade decide |
| 0.2–0.4 | Financiamento CDC → CAUTELA | Warning leve sobre custo total |
| 0.4–0.6 | Financiamento → CAUTELA; Parcelado longo → OK | Aviso sobre comprometimento |
| > 0.6 | Financiamento → EVITAR; Parcelado > 6x → CAUTELA | Recomendação ativa para preservar caixa |

### Regras específicas por perfil

#### CONSERVADOR (savings_rate ≥ 20%)
- Não sugerir Financiamento CDC em compras discricionárias (lazer, vestuário, eletrônicos)
- Não sugerir parcelamento > 6x quando `safe_to_spend_ratio < 0.15`
- Aviso se a compra representa > 30% da `monthly_avg_expenses` do mês

#### EQUILIBRADO (10% ≤ savings_rate < 20%)
- Mostrar diferença de `net_cost_real` em R$ de forma explícita no reasoning
- Avisar se a compra levaria `safe_to_spend` para HIGH
- Sem restrições de método — informação decide

#### GASTADOR (savings_rate < 10%)
- Se `top_categories` inclui a categoria da compra: incluir quanto já foi gasto nessa categoria no mês vs. média histórica
- Se trend == CRESCENTE: nota prominente sobre o padrão de gastos
- Financiamento CDC: só incluir no ranking se não houver alternativa acessível
- Se `committed_pct > 80%`: destacar comprometimento de renda no reasoning

---

## 8. Mudança 3: InvoiceHorizon (Pressão de Fatura)

**Arquivo:** `backend/app/forecast/cashflow/invoice_horizon.py` (NOVO)

### Estrutura

```python
@dataclass
class InvoiceHorizon:
    days_to_close: int              # dias até fechar a fatura atual
    current_cycle_committed: float  # soma das transações de cartão no ciclo atual
    installments_in_flight: float   # parcelas de INSTALLMENT shadow invoices futuras
    subscriptions_monthly: float    # soma de SUBSCRIPTION shadow invoices do próximo mês
    monthly_income: float           # referência de renda para calcular pressão relativa
    invoice_pressure: Literal["SAFE", "MODERATE", "HEAVY", "CRITICAL"]
```

### Como calcular

**`days_to_close`:** identificar padrão de fechamento nas últimas 3-6 faturas do histórico. Ex: se a fatura fecha todo dia 15 e hoje é dia 12, `days_to_close = 3`. Fallback: 15 dias.

**`current_cycle_committed`:** somar transações de cartão de crédito (amount < 0) que ocorreram após a data de fechamento da última fatura. Fonte: `transactions_df` filtrado por data.

**`installments_in_flight`:** somar todos os `ShadowInvoiceResponse` do tipo `INSTALLMENT` cujo `next_due_date` está dentro do próximo ciclo.

**`subscriptions_monthly`:** somar todos os `ShadowInvoiceResponse` do tipo `SUBSCRIPTION` esperados no próximo mês.

### Classificação de pressão

```python
def classify_invoice_pressure(
    current_cycle_committed: float,
    installments_in_flight: float,
    subscriptions_monthly: float,
    monthly_income: float,
    days_to_close: int,
) -> str:
    total_committed = current_cycle_committed + installments_in_flight + subscriptions_monthly
    ratio = total_committed / monthly_income if monthly_income > 0 else 1.0

    if days_to_close <= 3:
        return "CRITICAL"   # fatura fecha em < 3 dias — qualquer cartão é arriscado
    elif ratio > 0.80 and days_to_close <= 10:
        return "CRITICAL"   # fatura pesada e fechando em breve
    elif ratio > 0.60 and days_to_close <= 10:
        return "HEAVY"
    elif ratio > 0.50 or days_to_close <= 7:
        return "MODERATE"
    else:
        return "SAFE"
```

### Efeito na recomendação de pagamento

| invoice_pressure | Comportamento |
|---|---|
| CRITICAL | Desaconselhar cartão; recomendar PIX se safe_to_spend permite; warning com números concretos |
| HEAVY | Preferir PIX ou parcelamento longo (dilui impacto no ciclo atual); nota informativa |
| MODERATE | Informação no reasoning; sem mudança no ranking |
| SAFE | Comportamento padrão — custo de oportunidade decide |

---

## 9. Mudança 4: Limiares de Risco Relativos à Renda

**Arquivo:** `backend/app/forecast/cashflow/safe_to_spend.py` (refatorar `_classify_risk`)

### Hoje (absoluto — linha 287)

```python
CRITICAL: safe_to_spend ≤ 0 ou min_balance < 0
HIGH:     safe_to_spend < R$ 300
MEDIUM:   safe_to_spend < R$ 1.000
LOW:      safe_to_spend ≥ R$ 1.000
```

### Novo (relativo — campo adicional, não substituir o atual)

Manter o `risk_level` existente para não quebrar consumers. Adicionar `risk_level_relative`:

```python
def _classify_risk_relative(
    safe_to_spend: float,
    min_projected_balance: float,
    income_monthly: float,
) -> RiskLevel:
    if min_projected_balance < 0 or safe_to_spend <= 0:
        return "CRITICAL"
    if income_monthly <= 0:
        return _classify_risk_absolute(safe_to_spend)  # fallback

    ratio = safe_to_spend / income_monthly
    if ratio < 0.05:    # < 5% da renda mensal
        return "HIGH"
    elif ratio < 0.15:  # 5–15% da renda mensal
        return "MEDIUM"
    else:               # ≥ 15% da renda mensal
        return "LOW"
```

Adicionar `income_monthly: Optional[float]` ao `SafeToSpendResult` e `risk_level_relative: Optional[RiskLevel]`.

### Exemplos comparativos

| Renda | safe_to_spend | Hoje | Novo |
|---|---|---|---|
| R$ 3.000 | R$ 500 | MEDIUM | LOW (17% — confortável para essa renda) |
| R$ 3.000 | R$ 120 | HIGH | HIGH (4% — apertado) |
| R$ 15.000 | R$ 800 | MEDIUM | HIGH (5,3% — crítico para essa renda) |
| R$ 15.000 | R$ 2.500 | LOW | LOW (17% — ok) |
| R$ 8.000 | R$ 300 | HIGH | HIGH (3,75% — muito apertado) |

---

## 10. Mudança 5: Integrar Anomalias à Recomendação

**Não criar nada novo.** O `SpendingAnomalyDetector` já existe. O `PurchaseAdvisor` deve consultá-lo e reagir.

### O que consultar

Se a categoria da compra atual tem anomalias recentes:
- `UNUSUAL_AMOUNT` na mesma categoria → adicionar ao reasoning: "Você já teve um gasto incomum em [categoria] recentemente."
- `FREQUENCY_SPIKE` na mesma categoria → warning: "Você está fazendo compras em [categoria] com frequência acima do seu padrão."

### Impacto no score

Anomalias ativas na categoria da compra **não bloqueiam** a recomendação — apenas aumentam o `pressure_score` em +0.10 por anomalia ativa (máx +0.20), e adicionam contexto ao reasoning.

---

## 11. Mudança 6: Reasoning contextualizado

**Arquivo:** `purchase/purchase_advisor.py` — método `_build_reasoning`

O texto final deve responder 3 perguntas em ordem:
1. **O que recomendo e por quê** (custo real, ganho CDI se aplicável)
2. **Como isso afeta sua situação atual** (safe_to_spend, fatura, comprometimento)
3. **O que devo alertar com base no seu histórico** (trend, categoria, anomalias)

**Exemplo — CONSERVADOR, compra R$ 2.000, 6x sem juros:**
> "Para R$ 2.000 em Eletrônicos, o **parcelamento em 6x sem juros** tem custo real de R$ 1.938 — R$ 62 mais barato que à vista, porque o capital liberado rende ~R$ 62 no CDI líquido durante as 6 parcelas.
>
> Seu safe-to-spend é de R$ 4.200 (35% da renda) e sua fatura fecha em 18 dias com R$ 980 comprometidos — há folga confortável para as parcelas de R$ 333/mês.
>
> Perfil: seus gastos estão estáveis e você poupa 22% da renda — a compra não altera esse equilíbrio."

**Exemplo — GASTADOR, fatura pesada, trend CRESCENTE:**
> "Para R$ 1.500 em Vestuário, o **PIX à vista** é recomendado agora.
>
> ⚠️ Sua fatura fecha em 3 dias com R$ 3.800 comprometidos (76% da sua renda). Colocar mais R$ 1.500 no cartão elevaria a fatura para R$ 5.300.
>
> Seus gastos em Vestuário este mês já somam R$ 890 — 2,4× sua média histórica de R$ 370. Seus gastos gerais estão em tendência crescente há 2 meses."

---

## 12. Mudanças nos modelos

### `PurchaseRequest` (`models.py`) — adicionar campos opcionais

```python
# NOVOS (todos opcionais — não quebram clientes existentes)
risk_profile: Optional[Literal["conservador", "moderado", "agressivo"]] = None
apply_opportunity_cost: bool = True   # desligar para debug/testes
```

> Usar `risk_profile` (não `risk_tolerance`) para manter consistência com o Architect.

### `PaymentOption` (`models.py`) — adicionar campos

```python
# NOVOS
opportunity_cost_gain: float = 0.0        # ganho CDI ao não desembolsar à vista
net_cost_real: Optional[float] = None     # net_cost - opportunity_cost_gain
profile_fit: Literal["IDEAL", "OK", "CAUTELA", "EVITAR"] = "OK"
```

### `SafeToSpendResult` (`safe_to_spend.py`) — adicionar campos

```python
# NOVOS (opcionais — não quebram o campo existente risk_level)
income_monthly: Optional[float] = None
risk_level_relative: Optional[RiskLevel] = None
```

### `PurchaseRecommendation` (`models.py`) — adicionar campos

```python
# NOVOS
invoice_horizon: Optional[InvoiceHorizon] = None
pressure_score: Optional[float] = None       # 0.0–1.0
profile_summary: Optional[str] = None        # texto curto do perfil detectado
cdi_rate_used: Optional[float] = None
```

---

## 13. Mudanças no Architect (F3)

### 13.1 Inferir risk_profile do histórico

`architect/services/architect_service.py` — no método `simulate()`, antes da linha 133:

```python
# Se risk_profile não informado, inferir do histórico
if not request.risk_profile and transactions_df is not None:
    fin_profile = UserProfileAnalyzer().analyze(transactions_df, income_profile)
    request = request.model_copy(update={
        "risk_profile": _map_spending_to_risk(fin_profile.profile_type)
    })
    accumulated_warnings.append(
        f"Perfil de risco inferido do histórico: {request.risk_profile.value} "
        f"(savings_rate={fin_profile.savings_rate:.0f}%)."
    )

def _map_spending_to_risk(profile_type: str) -> RiskProfile:
    return {
        "CONSERVADOR": RiskProfile.CONSERVADOR,
        "EQUILIBRADO":  RiskProfile.MODERADO,
        "GASTADOR":     RiskProfile.MODERADO,  # não infere agressivo sem confirmação
    }.get(profile_type, RiskProfile.MODERADO)
```

**Nota:** o Architect hoje recebe `safe_to_spend` mas não recebe `transactions_df`. Para que a inferência funcione, o router (`architect/router.py`) precisará buscar as transações antes de chamar o service — o mesmo fluxo que já existe no F7.

### 13.2 Benchmark de investimento por perfil

`architect/simulators/strategy_engine.py` — no método `_simulate_investment()`:

```python
# Hoje: usa sempre cdi_annual
# Novo: ajuste por perfil de risco
def _get_investment_rate(cdi_annual: float, risk_profile: RiskProfile) -> float:
    """
    Retorna taxa de retorno esperada de investimentos por perfil.
    Não é garantia — é o benchmark de comparação para o SAVE_INVEST.
    """
    if risk_profile == RiskProfile.CONSERVADOR:
        # Renda fixa pós-fixada: CDI líquido (IR 15%)
        return cdi_annual * 0.85
    elif risk_profile == RiskProfile.MODERADO:
        # Mix conservador: CDI + 10% upside para exposição a crédito privado/FII
        return cdi_annual * 0.85 * 1.10
    else:  # AGRESSIVO
        # Exposição a renda variável: IBOVESPA histórico ~15% real, cap em CDI+60%
        return min(cdi_annual * 1.60, 0.18)  # cap em 18% a.a.
```

Isso impacta o NPV do `SAVE_INVEST` e pode mudar qual estratégia vence para perfil agressivo (onde investir pode superar financiamento).

### 13.3 Capacidade histórica de pagamento no consórcio

`architect/calculators/consortium.py` — adicionar verificação antes de simular:

```python
# Verificar se o usuário tem renda histórica suficiente
# (não apenas declarado — vindo do IncomeProfiler)
if income_net_monthly and income_net_monthly > 0:
    max_safe_payment = income_net_monthly * 0.25  # regra dos 25%
    if monthly_payment > max_safe_payment:
        viability_warnings.append(
            f"Parcela do consórcio (R$ {monthly_payment:.0f}) representa "
            f"{monthly_payment/income_net_monthly:.0%} da renda histórica "
            f"(R$ {income_net_monthly:.0f}) — acima dos 25% recomendados."
        )
```

### 13.4 Integrar CartãoOptimizationBonus com F2 real

`architect_service.py:355` — o `_compute_card_optimization_bonus` usa valores fixos de mercado. A V2 deveria chamar o `OptimizerService` para pegar o cartão real do usuário:

```python
# Fase 3: integração real com F2
if request.user_id:
    try:
        opt_report = OptimizerService().analyze(opt_req, transactions_df)
        if opt_report.best_card:
            pts_per_brl = opt_report.best_card.points_per_brl_actual
            point_value = opt_report.best_card.point_value_brl
            best_card_name = opt_report.best_card.card_name
    except Exception:
        pass  # mantém fallback de mercado
```

---

## 14. Gaps adicionais identificados na revisão

### 14.1 `confidence_score` não reflete qualidade do perfil

Hoje o `confidence_score` do `PurchaseAdvisor` (`purchase_advisor.py:416-430`) só considera:
- tem transações (+0.40)
- tem safe_to_spend (+0.30)
- tem income (+0.30)
- penalidade por warnings (-0.05 cada)

Não considera:
- `data_coverage_months` do ConsumptionProfiler (1 mês de dados é muito menos confiável que 6)
- `income_profile.confidence` do IncomeProfiler
- `spending_stability` (gastos muito instáveis → recomendações menos confiáveis)

Adicionar ao `_compute_confidence`:
```python
if consumption_profile:
    if consumption_profile.data_coverage_months < 2:
        score *= 0.70   # dados insuficientes
    if consumption_profile.spending_stability < 0.5:
        score *= 0.85   # gastos instáveis
if income_profile and income_profile.confidence < 0.5:
    score *= 0.80       # renda estimada com baixa confiança
```

### 14.2 BudgetAdvisor não é surfaced na Compra Inteligente

O `BudgetAdvisor` (`budget/budget_advisor.py`) já calcula quanto o usuário está acima/abaixo da regra 50/30/20 por grupo (Essenciais, Desejos, Poupança). Na recomendação de compra, se a categoria da compra pertence ao grupo "Desejos" e o usuário já está acima de 30% da renda nesse grupo, o reasoning deveria mencionar isso.

### 14.3 Parcelado sem juros: não é universal

O `_build_card_parcelado_option` (`purchase_advisor.py:274`) assume que o cartão sempre oferece parcelamento sem juros. Na prática:
- Nem todos os estabelecimentos oferecem parcelamento sem juros
- Alguns cartões não têm parcelamento sem juros em todas as categorias
- O número de parcelas disponíveis depende do estabelecimento

Adicionados ao `PurchaseRequest`: `merchant_accepts_installments: bool = True` e `max_interest_free_installments: Optional[int] = None` — ambos opcionais, mas quando fornecidos melhoram a precisão.

### 14.4 PIX com desconto não é calculado

O `_build_pix_option` tem `notes = "Sem juros, sem cashback. Melhor para negociar desconto à vista com o vendedor."` mas não calcula o desconto. Adicionar campo opcional `pix_discount_pct: float = 0.0` ao `PurchaseRequest` — quando fornecido pelo usuário (ex: "o vendedor me deu 5% de desconto"), o custo do PIX é ajustado:

```python
pix_net_cost = amount × (1 - pix_discount_pct) + opportunity_cost
```

Isso pode fazer PIX vencer parcelado mesmo com CDI alto, dependendo do desconto negociado.

---

## 15. O que NÃO mudar

- **API contract existente:** todos os campos novos são opcionais
- **Lógica de NPV do Architect:** a matemática está correta — só melhorar os inputs
- **`safe_to_spend_total` existente:** adicionar `risk_level_relative` como campo extra, não substituir
- **Monte Carlo do consórcio:** a simulação está bem implementada
- **`_apply_risk_profile_adjustment` do StrategyEngine:** a lógica está correta — só melhorar o input (risk_profile inferido vs declarado)

---

## 16. Ordem de implementação

### Fase 1 — Impacto alto, risco baixo (sem quebrar interface)
1. `safe_to_spend.py` — adicionar `risk_level_relative` com limiares por renda
2. `purchase/models.py` — adicionar campos opcionais (`opportunity_cost_gain`, `net_cost_real`, `risk_profile`, `profile_fit`)
3. `purchase/opportunity_cost.py` — NOVO, cálculo isolado, testável independente
4. `purchase_advisor.py` — aplicar opportunity cost no cálculo; `net_cost_real` passa a ordenar

### Fase 2 — Integração de perfil (lógica de negócio nova)
5. `purchase/profile_context.py` — NOVO, `compute_pressure_score` + regras por perfil
6. `purchase_advisor.py` — fetch `UserProfile` + `ConsumptionProfiler`; aplicar `pressure_score`
7. `forecast/cashflow/invoice_horizon.py` — NOVO, snapshot da fatura
8. `purchase_advisor.py` — integrar `InvoiceHorizon`; reescrever `_build_reasoning`
9. `purchase_advisor.py` — melhorar `_compute_confidence` com qualidade do perfil

### Fase 3 — Architect e refinamentos
10. `architect/router.py` — buscar transactions antes de chamar o service
11. `architect/services/architect_service.py` — inferir `risk_profile` se não informado
12. `architect/simulators/strategy_engine.py` — `_get_investment_rate` por perfil
13. `architect/calculators/consortium.py` — verificação de capacidade histórica
14. `architect/services/architect_service.py` — integração real F3↔F2 no CardOptimizationBonus

---

## 17. Resumo das mudanças por arquivo

| Arquivo | Tipo | Mudança |
|---|---|---|
| `purchase/opportunity_cost.py` | NOVO | Cálculo de custo de oportunidade CDI por forma de pagamento |
| `purchase/profile_context.py` | NOVO | `pressure_score` + regras de profile_fit por opção |
| `forecast/cashflow/invoice_horizon.py` | NOVO | Snapshot da fatura atual; pressão por dias/% comprometido |
| `purchase/models.py` | REFATORAR | Campos opcionais em PaymentOption, PurchaseRequest, PurchaseRecommendation |
| `purchase/purchase_advisor.py` | REFATORAR | Orquestrar novos componentes; `_build_reasoning` contextualizado; `_compute_confidence` melhorado |
| `forecast/cashflow/safe_to_spend.py` | REFATORAR | `risk_level_relative` relativo à renda; campo `income_monthly` no resultado |
| `architect/router.py` | REFATORAR | Buscar transactions_df antes de chamar service (habilita inferência de perfil) |
| `architect/services/architect_service.py` | REFATORAR | Inferir `risk_profile` + integração real F3↔F2 no CardOptimizationBonus |
| `architect/simulators/strategy_engine.py` | REFATORAR | `_get_investment_rate` diferenciado por perfil de risco |
| `architect/calculators/consortium.py` | REFATORAR | Verificação de capacidade histórica de pagamento |
