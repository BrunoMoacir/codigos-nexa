# Upgrade: Recomendações Financeiras Inteligentes
**Versão:** 1.0  
**Data:** 2026-04-02  
**Escopo:** F7 (Compra Inteligente) · F3 (Architect) · F1 (Safe-to-Spend)

---

## 1. Diagnóstico: O que está errado hoje

### 1.1 Compra Inteligente sempre favorece à vista

O `PurchaseAdvisor` ordena opções por `net_cost = total_cost - reward_value`. Como pagamento à vista não tem juros, ele nunca perde para parcelado no ranking atual. O problema: **capital imobilizado tem custo**, e com Selic a ~13% ao ano, parcelado sem juros pode ser genuinamente mais barato.

**Exemplo real (compra R$ 5.000, 12x sem juros, CDI 13% a.a.):**
```
À vista:       net_cost = R$ 5.000
12x s/juros:   custo nominal = R$ 5.000
               capital liberado mês a mês → rende ~R$ 320 no CDI
               net_cost real = R$ 4.680 ← 6,4% mais barato
```

O sistema hoje escolhe à vista. O correto seria escolher parcelado.

### 1.2 Perfil do usuário não influencia nada no F7

O `PurchaseAdvisor` não recebe nem consulta o `UserProfile`. Um usuário CONSERVADOR com savings_rate de 25% e um usuário GASTADOR negativo recebem exatamente a mesma recomendação.

### 1.3 Histórico é ignorado na recomendação de compra

O sistema tem `SpendingAnomalyDetector`, `trend` no `UserProfile`, e histórico de gastos por categoria — nada disso é usado no `PurchaseAdvisor`. Se o usuário tem uma tendência CRESCENTE de gastos nos últimos 3 meses, a recomendação deveria ser mais conservadora.

### 1.4 Faturas próximas não são consultadas

O safe-to-spend olha o saldo projetado para 30 dias, mas não avisa sobre o peso da compra na **fatura que fecha em breve**. Um usuário pode ter safe-to-spend de R$ 3.000, mas se a fatura fecha em 5 dias com R$ 2.800 já comprometidos, pagar mais R$ 1.500 no cartão é um problema.

### 1.5 Limiares de risco são fixos

```python
# safe_to_spend.py — hardcoded para todos os usuários
HIGH:     < R$ 300
MEDIUM:   < R$ 1.000
LOW:      ≥ R$ 1.000
```

Para quem ganha R$ 3.000/mês, `LOW` começa em R$ 1.000 (33% da renda). Para quem ganha R$ 20.000/mês, `LOW` começa em R$ 1.000 (5% da renda) — completamente diferente. Os limiares deveriam ser **relativos à renda**.

---

## 2. Arquitetura da Solução

### 2.1 Novos componentes necessários

```
backend/app/purchase/
├── purchase_advisor.py          (existente — refatorar)
├── models.py                    (existente — adicionar campos)
├── opportunity_cost.py          (NOVO — custo de oportunidade de capital)
└── profile_context.py           (NOVO — contexto do perfil para recomendações)

backend/app/forecast/cashflow/
├── safe_to_spend.py             (existente — tornar limiares relativos à renda)
└── invoice_horizon.py           (NOVO — snapshot da fatura atual)
```

### 2.2 Fluxo novo do PurchaseAdvisor

```
PurchaseRequest (+ risk_profile opcional)
       │
       ├─ 1. Fetch transactions_df          (já existe)
       ├─ 2. Fetch UserProfile              (NOVO — UserProfileAnalyzer)
       ├─ 3. Fetch safe_to_spend            (já existe — melhorar limiares)
       ├─ 4. Fetch InvoiceHorizon           (NOVO — snapshot da fatura)
       ├─ 5. Fetch best card                (já existe)
       ├─ 6. Fetch financing rate           (já existe)
       │
       ├─ 7. Build payment options          (já existe)
       ├─ 8. Apply opportunity cost         (NOVO — ajusta net_cost real)
       ├─ 9. Apply profile filter           (NOVO — filtra/penaliza por perfil)
       ├─10. Apply invoice pressure         (NOVO — penaliza cartão se fatura pesada)
       ├─11. Pick recommendation            (já existe — mas com inputs melhores)
       └─12. Build reasoning                (melhorar — incluir contexto)
```

---

## 3. Mudança 1: Custo de Oportunidade de Capital

**Arquivo:** `backend/app/purchase/opportunity_cost.py` (NOVO)

### Lógica

Para cada opção de pagamento, calcular o **custo de oportunidade** do capital imobilizado comparado a investir no CDI/SELIC.

**Para pagamento à vista (PIX ou cartão à vista):**
- Capital desembolsado no ato: `amount`
- Esse capital, se investido a `cdi_monthly`, renderia durante `horizon_months`
- `opportunity_cost = amount × ((1 + cdi_monthly)^horizon_months - 1)`
- `net_cost_real = amount - reward + opportunity_cost`

**Para parcelado sem juros (n parcelas):**
- Cada parcela `k` é paga no mês `k`. O capital de `(n-k) × parcela` fica investido por `(n-k)` meses.
- Ganho acumulado = `Σ_{k=1}^{n} parcela × ((1 + cdi_monthly)^(n-k) - 1)`
- `net_cost_real = amount - reward - ganho_cdi_acumulado`

**Para financiamento com juros:**
- Já paga juros explícitos — não tem custo de oportunidade adicional
- `net_cost_real = total_pago - reward` (sem mudança)

### Parâmetros

| Parâmetro | Fonte | Fallback |
|---|---|---|
| `cdi_monthly` | BACEN (Selic / 12) | 0.0108 (13% a.a.) |
| `horizon_months` | `installments` da compra | 1 para à vista |
| `apply_ir` | Perfil do usuário | True (15% IR sobre rendimento) |

### Impacto esperado

Com CDI a 13% a.a.:
- Compras ≥ R$ 1.000 parceladas em 6x+ **invariavelmente batem à vista** no custo real
- Compras < R$ 500 em 1-3x: diferença < R$ 15 — à vista pode ganhar por outros fatores
- Ponto de equilíbrio: ~R$ 300 em 3x vs à vista com desconto de 2%

---

## 4. Mudança 2: Contexto de Perfil na Recomendação

**Arquivo:** `backend/app/purchase/profile_context.py` (NOVO)

### Dados disponíveis no UserProfile (já calculado)

```python
# profiles.py — já existe
@dataclass
class UserProfile:
    profile_type: Literal["CONSERVADOR", "EQUILIBRADO", "GASTADOR"]
    savings_rate: float          # % de poupança atual
    financial_health_score: int  # 0–100
    trend: Literal["CRESCENTE", "ESTÁVEL", "DECRESCENTE"]
    top_categories: list[str]    # top 3 categorias de gasto
    monthly_avg_expenses: float  # média mensal de gastos
    income_net_monthly: float    # renda mensal líquida
```

### Regras por perfil

#### CONSERVADOR (savings_rate ≥ 20%)

O usuário já demonstra comportamento disciplinado. **Não forçar pressão.**

| Situação | Comportamento atual | Comportamento novo |
|---|---|---|
| safe_to_spend alto, compra confortável | Recomenda menor net_cost | Mantém — usuário tem folga |
| safe_to_spend médio | Recomenda parcelado | **Explica ganho CDI e deixa escolher** — não força nada |
| Compra > 30% da renda mensal | Sem aviso | **Warning: "Esta compra representa X% da sua renda. Você costuma ser conservador."** |
| Trend CRESCENTE | Sem impacto | **Nota: "Seus gastos estão em tendência crescente este mês."** |

**Não sugerir:**
- Financiamento CDC para perfil CONSERVADOR em compras discricionárias
- Parcelamento longo (>6x) quando safe_to_spend está MEDIUM

#### EQUILIBRADO (10% ≤ savings_rate < 20%)

Perfil neutro. Maximizar ganho financeiro com clareza.

- Mostrar diferença real em R$ entre opções (custo oportunidade explícito)
- Avisar se compra vai levar safe_to_spend para HIGH
- Não bloquear nenhuma opção — apenas informar

#### GASTADOR (savings_rate < 10%)

Usuário já no limite. **Ser mais direto sem ser paternalista.**

| Situação | Comportamento novo |
|---|---|
| safe_to_spend < 20% da renda mensal | Warning destacado: "Você já comprometeu X% da sua renda este mês." |
| Compra em categoria que é top_categories | "Você já gastou R$ X em [categoria] este mês — acima da média." |
| Trend CRESCENTE + safe_to_spend MEDIUM | Recomenda parcelado para preservar caixa |
| Financing CDC sugerido | Só mostrar se não houver outra opção — adicionar aviso sobre custo total |

**Score de pressão financeira (novo):**
```
pressure_score = (
    peso_savings_rate     # negativo quanto menor a taxa de poupança
  + peso_trend            # +penalidade se CRESCENTE
  + peso_health_score     # inversamente proporcional ao health_score
  + peso_safe_to_spend    # quanto menor vs renda, maior a pressão
)
```

Quanto maior o `pressure_score`, mais conservadora fica a recomendação automática — mas sem esconder opções, apenas reordenando e adicionando contexto.

---

## 5. Mudança 3: Pressão de Fatura (Invoice Horizon)

**Arquivo:** `backend/app/forecast/cashflow/invoice_horizon.py` (NOVO)

### O problema

O `safe_to_spend` hoje calcula o menor saldo projetado nos próximos 30 dias. Isso ignora que uma compra no cartão **não sai do saldo hoje** — ela cai na fatura, que vence em X dias.

Usuário com:
- Saldo atual: R$ 8.000
- Fatura fecha em 4 dias com R$ 6.500 já comprometidos
- safe_to_spend calculado: R$ 1.200 (parece ok)
- Compra nova de R$ 900 no cartão

O sistema diz "acessível". Mas a fatura vai para R$ 7.400, mais que o saldo. Usuário vai entrar no rotativo ou no limite.

### InvoiceHorizon

```python
@dataclass
class InvoiceHorizon:
    days_to_close: int           # dias para fechar a fatura atual
    current_invoice_amount: float  # total já comprometido na fatura aberta
    card_limit: Optional[float]  # limite do cartão (se disponível)
    installments_in_flight: float  # parcelas de compras anteriores que ainda vão cair
    projected_invoice_total: float # current + installments_in_flight + nova compra
    invoice_pressure: Literal["SAFE", "MODERATE", "HEAVY", "CRITICAL"]
```

### Como calcular

- `current_invoice_amount` → somar shadow invoices do tipo CARTAO com `next_due_date` dentro do ciclo atual
- `days_to_close` → detectar padrão de fechamento nos últimos 3 ciclos (ex: todo dia 15)
- `installments_in_flight` → shadow invoices do tipo INSTALLMENT com parcelas futuras

### Pressão de fatura

| Condição | Pressão |
|---|---|
| `days_to_close > 15` | Fatura ainda está no início — SAFE |
| `days_to_close ≤ 7` e fatura < 50% da renda | MODERATE |
| `days_to_close ≤ 7` e fatura 50–80% da renda | HEAVY |
| `days_to_close ≤ 7` e fatura > 80% da renda | CRITICAL |
| `days_to_close ≤ 3` (qualquer valor) | CRITICAL — fatura fecha em breve |

### Como usar na recomendação

```
if invoice_pressure == CRITICAL:
    → Desaconselhar cartão (à vista ou parcelado)
    → Recomendar PIX se disponível no safe_to_spend
    → Warning: "Sua fatura fecha em X dias com R$ Y comprometidos. 
       Adicionar R$ Z levaria a fatura para R$ W."

if invoice_pressure == HEAVY:
    → Preferir parcelamento longo (dilui impacto na fatura atual)
    → Ou recomendar PIX
    → Nota informativa sobre o estado da fatura

if invoice_pressure in (SAFE, MODERATE):
    → Comportamento padrão — custo de oportunidade decide
```

---

## 6. Mudança 4: Limiares de Risco Relativos à Renda

**Arquivo:** `backend/app/forecast/cashflow/safe_to_spend.py` (refatorar)

### Hoje (hardcoded absoluto)

```python
HIGH:     safe_to_spend < R$ 300
MEDIUM:   safe_to_spend < R$ 1.000
LOW:      safe_to_spend ≥ R$ 1.000
```

### Proposta (relativo à renda mensal)

```python
def _classify_risk_relative(
    safe_to_spend: float,
    income_monthly: float,
) -> RiskLevel:
    if income_monthly <= 0:
        # Fallback para limiares absolutos se renda desconhecida
        return _classify_risk_absolute(safe_to_spend)

    ratio = safe_to_spend / income_monthly

    if safe_to_spend <= 0 or min_projected_balance < 0:
        return "CRITICAL"
    elif ratio < 0.05:   # < 5% da renda
        return "HIGH"
    elif ratio < 0.15:   # 5–15% da renda
        return "MEDIUM"
    else:                # ≥ 15% da renda
        return "LOW"
```

### Exemplos comparativos

| Renda | safe_to_spend | Hoje | Novo |
|---|---|---|---|
| R$ 3.000 | R$ 500 | MEDIUM | LOW (17% da renda — confortável) |
| R$ 3.000 | R$ 250 | HIGH | HIGH (8% da renda — apertado) |
| R$ 15.000 | R$ 800 | MEDIUM | HIGH (5% da renda — crítico para essa renda) |
| R$ 15.000 | R$ 2.500 | LOW | LOW (17% da renda — ok) |

---

## 7. Mudança 5: Reasoning mais rico

**Arquivo:** `backend/app/purchase/purchase_advisor.py` — método `_build_reasoning`

### Hoje

Texto genérico: "Para uma compra de R$ X em Y, a opção com menor custo líquido é Z."

### Novo — reasoning contextualizado

O texto final deve incorporar todos os fatores que influenciaram a recomendação:

**Exemplo para CONSERVADOR, compra R$ 2.000, 6x sem juros:**
> "Para R$ 2.000 em Eletrônicos, o **parcelamento em 6x sem juros** tem custo real de R$ 1.887 — R$ 113 mais barato que à vista, porque o capital liberado rende ~R$ 113 no CDI durante o período.
>
> Seu perfil CONSERVADOR e safe-to-spend de R$ 4.200 (32% da renda) indicam folga confortável para absorver as parcelas de R$ 333/mês sem pressão.
>
> Sua fatura fecha em 18 dias com R$ 1.200 já comprometidos — ainda há espaço."

**Exemplo para GASTADOR, fatura prestes a fechar:**
> "Para R$ 1.500 em Vestuário, o **PIX à vista** é recomendado agora.
>
> ⚠️ Sua fatura fecha em 3 dias com R$ 3.800 comprometidos (89% da sua renda). Colocar mais R$ 1.500 no cartão elevaria a fatura para R$ 5.300.
>
> Seus gastos em Vestuário este mês já somam R$ 890 — 2,4× sua média histórica de R$ 370."

---

## 8. Mudanças nos modelos

### PurchaseRequest (models.py)

Adicionar campos opcionais — mantém compatibilidade retroativa:

```python
class PurchaseRequest(BaseModel):
    user_id: str
    amount: float
    category: str
    installments: int = 1
    monthly_income: Optional[float] = None
    
    # NOVOS (opcionais — não quebram clientes existentes)
    risk_tolerance: Optional[Literal["CONSERVADOR", "EQUILIBRADO", "AGRESSIVO"]] = None
    apply_opportunity_cost: bool = True   # pode desligar para debug
    horizon_months: Optional[int] = None  # override do período para custo de oportunidade
```

### PaymentOption (models.py)

```python
class PaymentOption(BaseModel):
    method: PaymentMethod
    label: str
    total_cost: float
    monthly_cost: Optional[float] = None
    installments: Optional[int] = None
    reward_value: float = 0.0
    net_cost: Optional[float] = None  # já existe
    
    # NOVOS
    opportunity_cost_gain: float = 0.0   # quanto o capital rende se não desembolsado à vista
    net_cost_real: Optional[float] = None  # net_cost - opportunity_cost_gain (o número que importa)
    profile_fit: Literal["IDEAL", "OK", "CAUTELA", "EVITAR"] = "OK"  # adequação ao perfil
    notes: str = ""
```

### PurchaseRecommendation (models.py)

```python
class PurchaseRecommendation(BaseModel):
    # ... campos existentes ...
    
    # NOVOS
    invoice_horizon: Optional[InvoiceHorizon] = None
    profile_context: Optional[ProfileRecommendationContext] = None
    cdi_rate_used: Optional[float] = None  # taxa usada no custo de oportunidade
```

---

## 9. Mudanças no Architect (F3)

### 9.1 Custo de oportunidade já existe — mas incompleto

O `strategy_engine.py` já calcula NPV e compara estratégias. O gap é que o perfil de risco do usuário real (vindo do histórico) não é conectado ao `risk_profile` do Architect.

Hoje o usuário passa `risk_profile` manualmente na request. Deveria ser **inferido automaticamente** do `UserProfile.profile_type` se não informado:

```python
# architect/services/architect_service.py
if not request.risk_profile:
    user_profile = UserProfileAnalyzer().analyze(transactions_df, income_profile)
    request.risk_profile = _map_spending_profile_to_risk(user_profile.profile_type)

def _map_spending_profile_to_risk(profile_type: str) -> str:
    return {
        "CONSERVADOR": "CONSERVADOR",
        "EQUILIBRADO":  "MODERADO",
        "GASTADOR":     "AGRESSIVO",  # gastador geralmente aceita mais risco
    }.get(profile_type, "MODERADO")
```

### 9.2 Benchmark de investimento por perfil

Hoje o `strategy_engine.py` usa sempre SELIC/CDI como taxa de retorno do investimento. Para perfil AGRESSIVO, o benchmark correto é diferente:

| Perfil | Benchmark de investimento | Justificativa |
|---|---|---|
| CONSERVADOR | CDI líquido (IR 15%) | Renda fixa pós-fixada |
| MODERADO | CDI líquido + 10% upside | Mix renda fixa + variável |
| AGRESSIVO | CDI + 30-50% upside | Exposição a renda variável |

Isso impacta o NPV do SAVE_INVEST e pode mudar qual estratégia vence.

### 9.3 Histórico de pagamentos no consórcio

O consórcio hoje não verifica se o usuário tem capacidade histórica de manter os pagamentos mensais. Adicionar:

```
viability_check += verificar se monthly_payment_consorcio 
                    <= 25% do income_net_monthly histórico
                    (não apenas declarado)
```

---

## 10. Ordem de implementação sugerida

### Fase 1 — Alto impacto, baixo risco (1–2 semanas)
1. **Limiares relativos à renda** no `SafeToSpendCalculator` — mudança isolada, nenhuma interface quebra
2. **Conectar UserProfile ao PurchaseAdvisor** — só adicionar o fetch, sem mudar a lógica de decisão ainda
3. **Adicionar `net_cost_real` com custo de oportunidade** em `PaymentOption` — campo novo, não quebra nada

### Fase 2 — Recomendação mais inteligente (2–3 semanas)
4. **InvoiceHorizon** — novo componente, integrar ao PurchaseAdvisor
5. **Regras de perfil na recomendação** — `_pick_recommendation` passa a usar `UserProfile`
6. **Reasoning contextualizado** — reescrever `_build_reasoning` com todos os inputs

### Fase 3 — Architect e refinamentos (2 semanas)
7. **Inferência automática do risk_profile** no Architect
8. **Benchmark de investimento por perfil** no strategy_engine
9. **Verificação de capacidade histórica** no consórcio

---

## 11. O que NÃO mudar

- **API contract existente**: todos os novos campos são opcionais — clientes antigos continuam funcionando
- **Lógica de NPV do Architect**: a matemática está correta — só melhorar os inputs
- **SafeToSpendCalculator**: manter o `safe_to_spend_total` existente; adicionar classificação relativa como campo separado (`risk_level_relative`) para não quebrar consumers existentes
- **Monte Carlo do consórcio**: a simulação está bem implementada

---

## 12. Resumo das mudanças por arquivo

| Arquivo | Tipo | Mudança |
|---|---|---|
| `purchase/opportunity_cost.py` | NOVO | Cálculo de custo de oportunidade de capital por forma de pagamento |
| `purchase/profile_context.py` | NOVO | Regras de adequação da recomendação ao perfil do usuário |
| `forecast/cashflow/invoice_horizon.py` | NOVO | Snapshot da fatura atual e pressão sobre o ciclo |
| `purchase/models.py` | REFATORAR | Novos campos em `PaymentOption`, `PurchaseRequest`, `PurchaseRecommendation` |
| `purchase/purchase_advisor.py` | REFATORAR | Orquestrar novos componentes; novo `_build_reasoning` |
| `forecast/cashflow/safe_to_spend.py` | REFATORAR | Limiares relativos à renda; manter campo original |
| `architect/services/architect_service.py` | REFATORAR | Inferir `risk_profile` do histórico se não informado |
| `architect/simulators/strategy_engine.py` | REFATORAR | Benchmark de investimento por perfil de risco |
