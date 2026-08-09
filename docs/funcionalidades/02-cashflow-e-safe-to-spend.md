# 02 — Cashflow e Safe-to-Spend (F1)

> Responde a pergunta mais básica e mais difícil de finanças pessoais:
> **"quanto eu posso gastar hoje sem me enrolar no fim do mês?"**

## Em palavras simples

O saldo da conta mente: ele não sabe que sua fatura fecha dia 10, que o aluguel
sai dia 15 e que faltam 3 parcelas da geladeira. A Nexa projeta seu caixa 30
dias à frente considerando tudo isso e devolve **um número por dia** ("sua
margem segura hoje é R$ 87/dia"). É o coração do produto — aparece no
dashboard, no widget da homescreen e em praticamente todas as outras análises.

## O que faz

- Projeção de fluxo de caixa 30 dias (`cashflow/projector.py`)
- Safe-to-spend com buffer de proteção (`cashflow/safe_to_spend.py`)
- Burn rate por categoria + escalada por renda (`cashflow/burn_rate.py`)
- Pressão da fatura de cartão (`cashflow/invoice_horizon.py`)
- Alertas (`router_alerts.py`) e widget PWA (`router_safe_to_spend.py`)

---

## Como é calculado

### 1. Projeção de caixa — simulação event-driven, não estatística

`CashflowProjector.project()` é **determinístico por princípio declarado**:
*"nenhum saldo é projetado sem um evento financeiro que o justifique"*. Não há
regressão nem média móvel — é uma simulação dia a dia.

**Passo 1 — saldo inicial.** Usa `current_balance` se informado; senão, o
`balance` da **última transação cronológica**. Se nem isso existir, levanta
erro em vez de chutar zero.

**Passo 2 — calendário.** `horizon_days = 30` dias a partir do dia seguinte à
última transação real:
`calendar[i] = last_date + timedelta(days=i+1)`.

**Passo 3 — indexação de eventos.** As shadow invoices são convertidas num
dicionário `{data → [eventos]}` (lookup O(1) por dia). Cada evento carrega
`type`, `merchant`, `amount`, `origin`.

**Passo 4 — o núcleo matemático.** Um laço simples:

```
saldo[t] = saldo[t−1] + Σ(amount dos eventos do dia t)
```

Cada linha da projeção guarda a **lista de eventos causadores** e um
`risk_flag = "NEGATIVE_BALANCE"` quando `saldo < 0`. É isso que permite ao
produto explicar *por que* o dia 17 fica apertado, em vez de só mostrar uma
curva.

### 2. Safe-to-spend — a fórmula

`SafeToSpendCalculator.calculate()`:

```
buffer_pct     = |Σ expenses| × 0,15          (safety_buffer_pct = 15%)
safety_buffer  = max(buffer_pct, R$ 200)      (min_buffer_absolute)

safe_to_spend_total = max(0, min(saldo_projetado) − safety_buffer)
safe_to_spend_daily = safe_to_spend_total / 30
```

Dois detalhes que definem o comportamento do produto:

- **Usa o MÍNIMO da projeção, não o saldo final.** Se o saldo despenca no dia
  17 e se recupera no 28, a margem é calculada sobre o vale do dia 17. A
  promessa é "você não fica negativo em nenhum dia do período", não "você
  termina o mês positivo".
- **Buffer é o maior entre 15% das obrigações e R$ 200.** Quem tem poucas
  obrigações futuras (15% daria R$ 30) ainda recebe um colchão mínimo de
  R$ 200 contra o imprevisto.

### 3. Classificação de risco — duas escalas

**Absoluta** (`_classify_risk`):

| Nível | Condição |
|---|---|
| CRITICAL | `min(saldo_projetado) < 0` **ou** `safe_to_spend ≤ 0` |
| HIGH | `safe_to_spend < R$ 300` |
| MEDIUM | `safe_to_spend < R$ 1.000` |
| LOW | `safe_to_spend ≥ R$ 1.000` |

**Relativa à renda** (`_classify_risk_relative`, exposta como
`risk_level_relative` quando há renda disponível):

| Nível | Condição |
|---|---|
| CRITICAL | saldo projetado negativo ou `safe_to_spend ≤ 0` |
| HIGH | `safe_to_spend / renda_mensal < 5%` |
| MEDIUM | entre 5% e 15% |
| LOW | `≥ 15%` |

As duas coexistem de propósito: R$ 800 de margem é confortável para quem ganha
R$ 3 mil (26% da renda → LOW) e apertado para quem ganha R$ 20 mil (4% →
HIGH). Sem `income_monthly`, a relativa faz fallback para a absoluta.

### 4. Burn rate — ritmo de gasto vs. ritmo esperado

`BurnRateAnalyzer.analyze()`. O conceito central:

```
expected_burn_rate = dia_atual / dias_no_mês        (ex.: 15/31 = 0,48)
overall_burn_rate  = total_gasto_mês / total_budget
burn_rate_ratio    = overall_burn_rate / expected_burn_rate
```

O **budget é implícito**: não é um valor que o usuário define, é a **média dos
últimos 3 meses por categoria** (`history_months = 3`). Sem histórico, o
budget vira o próprio gasto do mês corrente — o que faz o ratio nunca divergir
e, portanto, **nenhum alerta ser emitido** (decisão consciente: não alertar
quem não tem base de comparação).

**Faixas do alerta geral:**

| Nível | `burn_rate_ratio` |
|---|---|
| OK | < 1,10 |
| ATTENTION | 1,10 – 1,30 |
| WARNING | 1,30 – 1,50 |
| CRITICAL | ≥ 1,50 |

**Escalada por renda (MI.5)** — roda em paralelo e o alerta final é o **mais
severo dos dois**:

```
projeção_mensal = (gasto_até_hoje / dia_atual) × dias_no_mês
projected_income_ratio = projeção_mensal / renda_mensal
```

| Nível | `projected_income_ratio` |
|---|---|
| OK | < 75% |
| ATTENTION | 75 – 90% |
| WARNING | 90 – 100% |
| CRITICAL | ≥ 100% (vai gastar mais do que ganha no mês) |

Isso pega o caso que o ratio histórico não pega: alguém gastando **exatamente
como sempre gastou**, mas cujo padrão já comprometia a renda inteira.

**Categorias fora do ritmo**: uma categoria entra na lista quando
`(gasto_categoria / budget_categoria) / expected_burn_rate ≥ 1,20` — 20% acima
do ritmo. O overshoot projetado é
`max(0, (gasto/dia × dias_no_mês) − budget)`, e a lista sai ordenada pelo pior.
Todo o cálculo é vetorizado em Polars; o `iter_rows` só acontece na coleta
final do resultado já filtrado.

**Supressão de falso positivo**: nos dias 1 e 2 do mês (`_MIN_ALERT_DAY = 3`)
nenhum alerta é emitido — com `expected = 1/31 = 0,03`, qualquer gasto produz
ratio absurdo.

### 5. Pressão da fatura (`invoice_horizon.py`)

Modela o que a projeção de saldo sozinha não vê: o cartão de crédito já
comprometido mas ainda não debitado.

```
total_committed = gastos_do_ciclo_atual
                + parcelas_do_próximo_ciclo (INSTALLMENT)
                + assinaturas_mensais (SUBSCRIPTION)

ratio = total_committed / renda_mensal
```

Classificação, **em ordem de prioridade**:

| Nível | Regra |
|---|---|
| CRITICAL | `days_to_close ≤ 3` (qualquer compra nova é arriscada) |
| CRITICAL | `ratio > 80%` **e** `days_to_close ≤ 10` |
| HEAVY | `ratio > 60%` **e** `days_to_close ≤ 10` |
| MODERATE | `ratio > 50%` **ou** `days_to_close ≤ 7` |
| SAFE | demais casos |

**O dia de fechamento é inferido, não informado** (`_detect_days_to_close`):
filtra despesas com `payment_method` contendo "crédito", agrupa por dia do mês
e usa o dia de maior acúmulo como proxy do fechamento, limitado a `[1, 28]`.
Se o dia já passou no mês corrente, projeta para o mês seguinte. Qualquer
falha ou dados insuficientes → fallback de **15 dias**.

### 6. Hierarquia de confiança da renda

A renda usada em todos os cálculos acima segue uma cascata explícita
(`CashflowEngine.analyze`):

1. `monthly_income` declarado pelo usuário (vence sempre);
2. `income_profile.monthly_net_income`, **desde que
   `confidence ≥ 0,5`** (`_INCOME_CONFIDENCE_THRESHOLD`);
3. nada — os cálculos relativos à renda simplesmente não são emitidos
   (`income_ratio = None`, `risk_level_relative = None`) em vez de usar um
   número ruim.

### 7. Widget PWA (`GET /safe-to-spend/{user_id}/widget`)

Payload de ~200 bytes, reaproveitando o cache Redis de 15 min do endpoint
completo:

```
days_left = dias_no_mês − dia_atual + 1
remaining = max(0, safe_to_spend_total − spent_to_date)
daily     = remaining / days_left
```

Semáforo:

| Status | Regra | Cor |
|---|---|---|
| CRITICO | `pct_consumed ≥ 95%` ou `daily ≤ 0` | `#ef4444` |
| ATENCAO | `pct_consumed ≥ 75%` ou `risk_level ∈ {HIGH, CRITICAL}` | `#eab308` |
| OK | demais | `#22c55e` |

A cor vem pronta em hex para o widget renderizar sem lógica própria.

O endpoint principal calcula ainda o limite mensal de orçamento como
`max(0, renda_total − |shadow_invoices| − safety_buffer)`.

---

## Como funciona (técnico)

- `CashflowEngine` (`cashflow/engine.py`) orquestra na ordem:
  `CashflowProjector` → `SafeToSpendCalculator` → `BurnRateAnalyzer` →
  `BudgetAdvisor`. Aceita `reference_date` explícita (backtesting mantém todos
  os calculadores alinhados) e `include_daily_data=False` para resposta
  compacta.
- **Endpoints**: `GET /forecast/{user_id}` (análise completa),
  `GET /safe_to_spend/{user_id}`, `GET /safe-to-spend/{user_id}/widget`,
  `GET /shadow_invoice/{user_id}`, `GET /alerts/{user_id}`,
  `GET /dashboard/summary`.
- Consome o resultado do ETL via runner (`app/runner.py` → cache por usuário).
- **Explicabilidade** (`core/explain.py`): o número sai com a explicação em
  português de como foi calculado.

## O que NÃO faz

- **Não prevê rendas irregulares com ML** — a projeção assume recorrência
  detectada; um autônomo com renda caótica recebe projeção conservadora, não
  um modelo probabilístico de renda.
- **Não considera limite do cartão/cheque especial** como "dinheiro
  disponível" (decisão de produto: crédito não é margem).
- **Não faz replanejamento automático** quando o usuário estoura a margem —
  gera alerta, mas a decisão é do usuário.

## Gaps e limitações

- **Horizonte fixo de 30 dias** — `horizon_days` é parâmetro, mas 90/180 dias
  exigiria modelar sazonalidade (13º, IPVA, férias), que a simulação
  event-driven atual não tem.
- **A projeção só aplica eventos vindos das shadow invoices.** Rendas futuras
  recorrentes entram apenas se estiverem representadas como evento; a
  simulação não infere "vai cair salário dia 5" por conta própria.
- **O dia de fechamento da fatura é heurístico** (dia de maior acúmulo, teto
  no dia 28, fallback 15 dias) — quem tem múltiplos cartões com datas
  diferentes é modelado como um só.
- **Burn rate precisa de 3 meses** para ter budget implícito; abaixo disso o
  alerta é silenciado por construção.
- A qualidade é refém do ETL: conta recém-conectada (< 3 meses de histórico)
  produz margens com confiança baixa — o produto sinaliza, mas o número
  aparece mesmo assim.
- **Multi-conta parcial**: a projeção soma contas conectadas, mas não modela
  transferências programadas entre elas.
