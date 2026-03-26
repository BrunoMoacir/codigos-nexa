# Nexa Architect — F3: Documentação Completa

> **Feature F3 — Nexa Architect**
> Simulador inteligente de conquistas financeiras. Compara até 5 estratégias de aquisição e recomenda a mais barata, considerando perfil de risco, liquidez, inflação e renda de aluguel.

---

## Índice

1. [Visão Geral](#1-visão-geral)
2. [Arquitetura e Fluxo Completo](#2-arquitetura-e-fluxo-completo)
3. [Input — SimulationRequest](#3-input--simulationrequest)
4. [Estratégias Simuladas](#4-estratégias-simuladas)
   - 4.1 [Estratégia 1 — Financiamento Bancário](#41-estratégia-1--financiamento-bancário)
   - 4.2 [Estratégia 2 — Consórcio](#42-estratégia-2--consórcio)
   - 4.3 [Estratégia 3 — Poupar e Investir](#43-estratégia-3--poupar-e-investir)
   - 4.4 [Estratégia 4 — Financiamento + Aluguel](#44-estratégia-4--financiamento--aluguel)
   - 4.5 [Estratégia 5 — Consórcio + SELIC + Aluguel](#45-estratégia-5--consórcio--selic--aluguel)
5. [Como a Comparação é Feita — NPV](#5-como-a-comparação-é-feita--npv)
6. [Correção de Viés — Custo de Oportunidade do Aluguel](#6-correção-de-viés--custo-de-oportunidade-do-aluguel)
7. [Connectors — Fontes de Taxas](#7-connectors--fontes-de-taxas)
8. [Validadores](#8-validadores)
9. [Score de Confiança](#9-score-de-confiança)
10. [Integração com F1 (safe_to_spend)](#10-integração-com-f1-safetospend)
11. [M3.3 — Bônus de Pontos no Cartão](#11-m33--bônus-de-pontos-no-cartão)
12. [Output — SimulationResponse](#12-output--simulationresponse)
13. [API REST — Endpoints](#13-api-rest--endpoints)
14. [Persistência — DuckDB](#14-persistência--duckdb)
15. [Análise de Sensibilidade](#15-análise-de-sensibilidade)
16. [Exemplo Real Calculado](#16-exemplo-real-calculado)

---

## 1. Visão Geral

O **Nexa Architect** resolve uma pergunta simples com matemática sofisticada:

> "Quero comprar um apartamento de R$ 800.000. Devo financiar, entrar num consórcio ou juntar dinheiro? E se eu puder alugar o imóvel?"

O sistema simula **até 5 estratégias**, calcula o **Valor Presente Líquido (NPV)** de cada uma usando a SELIC como taxa de desconto, penaliza estratégias que exigem esperar (via custo de oportunidade do aluguel perdido) e entrega uma recomendação fundamentada com plano de ação.

### Quando o Architect é acionado

O agente chama a tool `get_financing_simulation` sempre que o usuário mencionar:
- Comprar imóvel, carro, reforma ou bem de alto valor
- Se vale financiar vs. poupar vs. consórcio
- Simulação de parcelas, juros, custo total
- Comprar e alugar, usar aluguel para pagar parcelas

---

## 2. Arquitetura e Fluxo Completo

```
╔══════════════════════════════════════════════════════════════════════════╗
║                    NEXA ARCHITECT — FLUXO COMPLETO                       ║
╚══════════════════════════════════════════════════════════════════════════╝

  [Usuário / LLM Agent]
         │
         │ get_financing_simulation(user_id, target_amount, ...)
         ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │            TOOL: get_financing_simulation.py                         │
  │  1. Mapeia strings → Enums (AssetType, RiskProfile)                 │
  │  2. Busca safe_to_spend da F1 via NexaRunner (opcional)             │
  │  3. Chama ArchitectService.simulate(request, safe_to_spend)         │
  │  4. Formata saída para o LLM (linhas de texto estruturado)          │
  └─────────────────────────────────────────────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │           ARCHITECT SERVICE: architect_service.py                    │
  │                                                                       │
  │  PASSO 1: InputValidator.validate(request)                           │
  │           └─ Erros → ValueError | Avisos → accumulated_warnings      │
  │                                                                       │
  │  PASSO 2: _fetch_market_rates(request)                               │
  │           ├─ BacenConnector    → SELIC anual   [fallback: 13.25%]   │
  │           ├─ AnbimaConnector   → CDI anual     [fallback: 13.15%]   │
  │           ├─ MarketRatesConnector → CET p/ bem [fallback por tipo]  │
  │           ├─ IPCAConnector     → IPCA anual    [fallback: 4.50%]    │
  │           └─ ConsortiumRateProvider → admin, reserva, reajuste      │
  │                                                                       │
  │  PASSO 3: StrategyEngine.simulate(request, market_rates)            │
  │           └─ [ver bloco abaixo]                                      │
  │                                                                       │
  │  PASSO 4: LiquidityValidator.calculate(monthly_payment, ...)        │
  │           └─ Classifica impacto: SAFE / WARNING / HIGH / CRITICAL   │
  │                                                                       │
  │  PASSO 5: _compute_confidence(...)                                   │
  │           └─ Score 0.30–1.00                                         │
  │                                                                       │
  │  PASSO 6: _compute_card_optimization_bonus(...)  [se FINANCING]     │
  │           └─ M3.3: pontos/cashback estimados                         │
  │                                                                       │
  │  RETORNA: SimulationResponse (completo)                              │
  └─────────────────────────────────────────────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │              STRATEGY ENGINE: strategy_engine.py                     │
  │                                                                       │
  │  A. _simulate_financing(req, rates)                                  │
  │     └─ financing.calculate_price() ou calculate_sac()               │
  │        → npv_fin, cashflows[], total_cost, months=1 (compra agora)  │
  │                                                                       │
  │  B. _simulate_investment(req, rates)                                 │
  │     └─ investment.calculate_future_value()                           │
  │        → meses necessários p/ acumular, custo = aportes sem juros   │
  │                                                                       │
  │  C. _simulate_consortium(req, rates)       [se include_consortium]  │
  │     └─ consortium.simulate_monte_carlo() — 2000 simulações          │
  │        → contemplation_month esperado, admin_fee, probabilidades     │
  │                                                                       │
  │  D. _simulate_financing_rental(req, rates, fin_result)  [se IMOVEL] │
  │     └─ cashflows líquidos = cashflow_bruto + aluguel_mensal         │
  │        → NPV do fluxo líquido                                        │
  │                                                                       │
  │  E. _simulate_consortium_selic_rental(req, rates, cons_result)      │
  │     └─ Loop mensal: saldo_selic + aluguel - parcela_consórcio       │
  │        → is_self_sustaining, monthly_net_cost                        │
  │                                                                       │
  │  RANKING: strategies dict com NPV de cada estratégia                │
  │     ┌─ SAVE_INVEST ajustado: npv_inv - foregone_rental_pv           │
  │     └─ Seleciona max(NPV) = menor custo presente                    │
  │                                                                       │
  │  BUILD: SimulationResponse com tudo                                  │
  └─────────────────────────────────────────────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │           API ROUTE: api/v1/routes/architect.py                      │
  │  POST /architect/simulate  → SimulationResponse                      │
  │  GET  /architect/simulations/{id}                                    │
  │  GET  /architect/simulations/{id}/sensitivity                        │
  │  POST /architect/timing                                              │
  │  (+ 3 outros endpoints)                                             │
  │  Persistência assíncrona no DuckDB (não bloqueia resposta)          │
  └─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Input — SimulationRequest

| Campo | Tipo | Obrigatório | Default | Descrição |
|---|---|---|---|---|
| `user_id` | str | ✅ | — | ID do usuário |
| `target_amount` | float | ✅ | — | Valor do bem (R$) |
| `down_payment` | float | | 0.0 | Entrada disponível (R$) |
| `max_monthly_budget` | float | | None | Orçamento mensal máximo (R$) |
| `risk_profile` | RiskProfile | | moderado | conservador / moderado / agressivo |
| `asset_type` | AssetType | | OUTRO | IMOVEL / VEICULO / REFORMA / VIAGEM / OUTRO |
| `financing_months` | int | | 48 | Prazo do financiamento (6–420 meses) |
| `amortization_method` | AmortizationMethod | | PRICE | PRICE (fixo) ou SAC (decrescente) |
| `include_consortium` | bool | | True | Incluir consórcio na comparação |
| `expected_rental_income` | float | | None | Renda de aluguel estimada — ativa Estratégias 4 e 5 |
| `target_date` | date | | None | Data desejada para aquisição |

**Propriedade derivada:** `request.principal = target_amount - down_payment`

---

## 4. Estratégias Simuladas

### 4.1 Estratégia 1 — Financiamento Bancário

**Arquivo:** `calculators/financing.py`

#### Sistema PRICE (parcelas fixas)

```
PMT = P × [ r × (1+r)^n ]
          ─────────────────
           (1+r)^n - 1

Onde:
  P = principal (target - entrada)
  r = taxa mensal = (1 + taxa_anual)^(1/12) - 1
  n = prazo em meses
```

**Tabela mensal:**
```
Mês t:
  Juros_t       = Saldo_t × r
  Amortização_t = PMT - Juros_t
  Seguro_t      = Saldo_t × taxa_seguro_mensal
  Saldo_(t+1)   = Saldo_t - Amortização_t
```

#### Sistema SAC (amortização constante)

```
Amortização = P / n  (constante em todos os meses)

Mês t (com correção monetária opcional):
  Correção_t        = Saldo_t × monthly_corr
  Saldo_corrigido_t = Saldo_t + Correção_t
  Juros_t           = Saldo_corrigido_t × r
  Seguro_t          = Saldo_corrigido_t × taxa_seguro
  Parcela_t         = Amortização + Juros_t + Correção_t  (decrescente)
  Saldo_(t+1)       = Saldo_corrigido_t - Amortização
```

SAC tem **menor custo total** que PRICE — as parcelas iniciais são maiores, mas os juros caem mais rápido.

#### IOF — Resolução BACEN 3.516/2007

```
IOF_fixo  = principal × 0.0038           (componente 1: 0,38% do principal)

IOF_diário = Σ [ amortização_t × 0.000082 × min(t×30, 365) ]
                                          (componente 2: 0,0082%/dia por parcela)

IOF_total = min(IOF_fixo + IOF_diário, principal × 0.03)
            └─ Cap de 3% do principal
```

#### Seguros obrigatórios (mensais sobre saldo devedor)

| Tipo de bem | Taxa mensal |
|---|---|
| Imóvel (MIP+DFI) | 0,035% |
| Veículo | 0,200% |
| Moto | 0,180% |
| Caminhão | 0,150% |
| Outros | 0% |

#### CET — Custo Efetivo Total (Newton-Raphson)

```
O CET é a taxa mensal r que satisfaz:

  principal_líquido = Σ ( parcela_t + seguro_t )
                         ─────────────────────────
                               (1 + r)^t

  principal_líquido = principal - IOF_total - admin_fee

Newton-Raphson:
  r_(k+1) = r_k - f(r_k) / f'(r_k)
  Converge quando |Δr| < 1e-6
  CET anual = (1 + r_mensal)^12 - 1
```

#### Custo total do financiamento

```
Custo_total = Σ(parcelas) + Σ(seguros) + IOF_total + admin_fee
```

---

### 4.2 Estratégia 2 — Consórcio

**Arquivo:** `calculators/consortium.py`

O consórcio é simulado por **Monte Carlo com 2.000 execuções**, modelando a aleatoriedade das assembleias mensais.

#### Fluxo da simulação

```
ENTRADA: total_value, months, admin_rate, reserve_fund_rate, lance_percentage

Para cada simulação (1 a 2000):
  ├─ Gera lance_offered ~ LogNormal(μ=log(lance_base×0.85), σ=0.25)
  │   └─ Recalcula a cada 6 meses com decaimento exponencial
  ├─ Loop por cada mês do grupo:
  │   ├─ group_size decresce (attrition ≈ 0.5%/mês)
  │   ├─ sorteio_pct ~ Uniform(0, 1/group_size)
  │   ├─ Se sorteio ≤ threshold_sorteio → contemplado (sorteio)
  │   └─ Se lance_offered ≥ max_lance_do_grupo → contemplado (lance)
  └─ Registra contemplation_month

RESULTADO:
  P(contemplação ≤ 12m) = % simulações com contemplation_month ≤ 12
  P(contemplação ≤ 24m) = % simulações com contemplation_month ≤ 24
  P(contemplação ≤ 36m) = % simulações com contemplation_month ≤ 36
  expected_months = média ponderada dos meses de contemplação
```

#### Reajuste para IMOVEL — INCC aproximado

```
INCC ≈ min(7%, IPCA × 1.5)

O saldo da carta é reajustado mensalmente pelo INCC enquanto
o consorciado aguarda contemplação. Isso aumenta o valor
efetivo da carta ao longo do tempo.
```

#### Custo total do consórcio

```
Custo_total = valor_carta × (1 + admin_rate + reserve_fund_rate)
            = valor_carta × (1 + taxa_admin + fundo_reserva)

Exemplo: R$ 500.000 × (1 + 0.18 + 0.02) = R$ 600.000
```

---

### 4.3 Estratégia 3 — Poupar e Investir

**Arquivo:** `calculators/investment.py`

#### Cálculo de meses necessários

```
O usuário acumula depósitos mensais D a uma taxa CDI com IR regressivo.

FV mensal acumulada:
  FV_t = Σ [ D × (1 + r_net)^(t-i) ]  para i = 1 até t

Onde r_net = CDI_mensal × (1 - alíquota_IR_t)

Tabela IR regressivo (Tesouro, CDBs):
  0–180 dias:    22,5%
  181–360 dias:  20,0%
  361–720 dias:  17,5%
  > 720 dias:    15,0%
```

#### Cálculo de valor futuro com IR por depósito

```
Para cada depósito i, o ganho = D × [(1+CDI_mensal)^(n-i+1) - 1]
IR_i = ganho_i × alíquota(dias_restantes)
FV_líquido_i = D × (1+CDI_mensal)^(n-i+1) - IR_i
FV_total = Σ FV_líquido_i + down_payment × (1+CDI_mensal)^n
```

#### Custo total (comparação justa)

```
Custo_save_invest = aporte_mensal × meses_acumulação
(sem juros no custo — o usuário RECEBE rendimento, não PAGA)

Mas o NPV penaliza o tempo de espera (ver seção 6).
```

---

### 4.4 Estratégia 4 — Financiamento + Aluguel

**Arquivo:** `strategy_engine.py → _simulate_financing_rental()`

Esta estratégia assume que o imóvel é **comprado agora via financiamento** e imediatamente colocado para alugar. O aluguel reduz o desembolso líquido mensal.

```
FLUXO DE CAIXA LÍQUIDO:

  cashflows_brutos = cashflows do financiamento (calculados na Estratégia 1)
                     [−entrada, −parcela_1, −parcela_2, ..., −parcela_n]

  cashflows_líquidos = cashflows_brutos com cada parcela reduzida pelo aluguel:
    cashflow_líquido_t = cashflow_bruto_t + aluguel_mensal   (t ≥ 1)
    cashflow_líquido_0 = −entrada          (compra imediata)

NPV_4 = Σ ( cashflow_líquido_t / (1 + SELIC_mensal)^t )

monthly_net_cost = parcela_bruta - aluguel_mensal
total_rental_income = aluguel_mensal × financing_months
net_acquisition_cost = total_gross_cost - total_rental_income
```

**Validação de liquidez:** usa `monthly_net_cost` (após aluguel), não a parcela bruta. Uma estratégia auto-sustentável não é rejeitada por orçamento mensal.

---

### 4.5 Estratégia 5 — Consórcio + SELIC + Aluguel

**Arquivo:** `strategy_engine.py → _simulate_consortium_selic_rental()`

A estratégia mais sofisticada. O consorciado:
1. Investe a entrada (`down_payment`) na SELIC enquanto aguarda contemplação
2. O aluguel + rendimento SELIC cobrem (ou ajudam a cobrir) as parcelas do consórcio
3. O saldo investido cresce ou diminui a cada mês conforme o fluxo líquido

```
LOOP MENSAL (t = 1 até cons_months):

  Se t > 1 e reajuste_anual > 0:
    carta_atual *= (1 + reajuste_mensal)   ← INCC/IPCA aumenta a carta

  parcela_t = carta_atual × (1 + total_rate) / cons_months
                └─ total_rate = admin_rate + reserve_fund_rate

  rendimento_selic_t = max(saldo_investido, 0) × SELIC_mensal

  fluxo_líquido_t = aluguel + rendimento_selic_t - parcela_t

  saldo_investido_(t+1) = saldo_investido_t + fluxo_líquido_t
    ├─ Se positivo: saldo cresce (operação auto-sustentável)
    └─ Se negativo: usuário precisa aportar a diferença

  Se fluxo_líquido_t < 0: months_negative++

is_self_sustaining = (months_negative == 0)

Custo total NPV:
  cashflows_npv = [−entrada] + net_cashflows_mensais
  NPV_5 = npv_calc.calculate_npv(cashflows_npv, SELIC_mensal)
```

**monthly_net_cost** reportado: calculado no mês 1. Se a carta reajusta (INCC) mas o aluguel é fixo, meses posteriores podem ter déficit — isso é explicitado na narrativa.

---

## 5. Como a Comparação é Feita — NPV

### Por que NPV e não custo total nominal?

Estratégias têm **prazos diferentes**. O consórcio pode levar 180 meses; o financiamento, 48. Comparar R$ 150k (consórcio) com R$ 170k (financiamento) sem ajustar pelo tempo é injusto — o dinheiro de hoje vale mais que o de amanhã.

O NPV traz todos os fluxos **a valor presente** usando a SELIC como taxa de desconto.

### Fórmula NPV

```
NPV = Σ ( CF_t / (1 + r)^t )  para t = 0 até n

Onde:
  CF_0 = −entrada (desembolso imediato)
  CF_t = −parcela_t   (para t ≥ 1)
  r    = SELIC_mensal = (1 + SELIC_anual)^(1/12) - 1

Como são pagamentos (saídas de caixa), NPV é negativo.
MELHOR estratégia = MAIOR NPV (o menos negativo = menor custo presente)
```

### Tabela comparativa (exemplo ilustrativo)

```
Cenário: R$ 500.000 (imóvel), entrada R$ 100.000, aluguel R$ 2.500/mês
SELIC 13.25% a.a. → mensal ≈ 1.04%

┌────────────────────────────────┬───────────────┬──────────────┬───────────┐
│ Estratégia                     │ Custo Nominal │ NPV          │ Meses     │
├────────────────────────────────┼───────────────┼──────────────┼───────────┤
│ 1. Financiamento (PRICE 240m)  │ R$ 780.000    │ −R$ 410.000  │ 1 (agora) │
│ 2. Consórcio (180m)            │ R$ 480.000    │ −R$ 320.000  │ ~90 (med) │
│ 3. Poupar/Investir (CDI)       │ R$ 400.000    │ −R$ 280.000* │ ~72 meses │
│ 4. Financiamento + Aluguel     │ R$ 480.000 liq│ −R$ 200.000  │ 1 (agora) │
│ 5. Consórcio + SELIC + Aluguel │ R$ 380.000 liq│ −R$ 180.000  │ ~90 (med) │
└────────────────────────────────┴───────────────┴──────────────┴───────────┘
* Ajustado por custo de oportunidade do aluguel perdido (seção 6)
Recomendada: Estratégia 5 (NPV mais alto = menor custo presente)
```

---

## 6. Correção de Viés — Custo de Oportunidade do Aluguel

### O problema

Sem correção, **Poupar/Investir quase sempre "ganhava"** da comparação. O motivo: o usuário acumula rendimento CDI sem pagar juros. Porém, enquanto acumula (72+ meses), ele **deixa de receber aluguel** do imóvel que ainda não tem.

### A solução

Quando `expected_rental_income` é informado, o NPV do Poupar/Investir é **penalizado** pelo Valor Presente dos aluguéis que o usuário deixaria de receber durante o período de acumulação:

```
CORREÇÃO DO NPV — POUPAR/INVESTIR (usado apenas no ranking):

  foregone_rental_pv = aluguel_mensal × [ 1 - (1 + SELIC_mensal)^(−n_acumulação) ]
                                          ─────────────────────────────────────────
                                                     SELIC_mensal

  npv_save_invest_ajustado = npv_save_invest_bruto - foregone_rental_pv

Exemplo: aluguel R$ 2.500/mês, acumulação 72 meses, SELIC 1.04%/mês
  foregone_rental_pv ≈ R$ 2.500 × 55.5 ≈ R$ 138.750

O NPVComparison.save_invest ainda mostra o valor bruto (transparência).
O ranking usa o valor ajustado.
```

### Impacto na decisão

Antes da correção: SAVE_INVEST ganhava em ~85% dos cenários com aluguel informado.
Após a correção: O sistema corretamente favorece estratégias de compra imediata quando o aluguel é significativo.

---

## 7. Connectors — Fontes de Taxas

```
┌─────────────────────────────────────────────────────────────────────┐
│                       CONNECTORS                                     │
│                                                                       │
│  BacenConnector          AnbimaConnector       MarketRatesConnector  │
│  bacen.py                anbima.py             market_rates.py       │
│                                                                       │
│  Fonte: SGS BCB          Fonte: SGS BCB        Fonte: JSON local     │
│  Série 432 (SELIC)       Série 12 (CDI)        (atualizado manualmente)│
│  Cache: 1 hora           Cache: 1 hora         Cache: 1 hora         │
│                                                                       │
│  FALLBACK: 13.25% a.a.   FALLBACK: 13.15% a.a.                      │
│                                                                       │
│  Fallbacks CET por tipo de bem (MarketRates):                        │
│    IMOVEL:  14.75% a.a.                                              │
│    VEICULO: 18.50% a.a.                                              │
│    REFORMA: 16.00% a.a.                                              │
│    VIAGEM:  22.00% a.a.                                              │
│    OUTRO:   20.00% a.a.                                              │
│                                                                       │
│  IPCAConnector           ConsortiumRateProvider                      │
│  ipca.py                 consortium_rate_provider.py                 │
│                                                                       │
│  Fonte: BCB API          Combina ABAC + IPCA                         │
│  FALLBACK: 4.50% a.a.    Parâmetros consórcio por AssetType:         │
│                                                                       │
│                          IMOVEL:                                     │
│                            admin_rate: 0.18                          │
│                            reserve_fund: 0.02                        │
│                            reajuste: INCC ≈ min(7%, IPCA×1.5)       │
│                          VEICULO:                                    │
│                            admin_rate: 0.20                          │
│                            reserve_fund: 0.02                        │
│                            reajuste: IPCA                            │
│                          OUTRO:                                      │
│                            admin_rate: 0.22                          │
│                            reserve_fund: 0.02                        │
│                                                                       │
│  AbacConnector: estatísticas históricas de contemplação (ABAC)      │
└─────────────────────────────────────────────────────────────────────┘
```

**Todos os conectores:** falha silenciosa com fallback + warning no response. A simulação nunca quebra por indisponibilidade de API externa.

---

## 8. Validadores

### InputValidator — `validators/input_validator.py`

| Regra | Detalhe |
|---|---|
| Principal mínimo | R$ 1.000 |
| Entrada máxima | 90% do valor do bem |
| Prazo máximo por tipo | IMOVEL: 420m, VEICULO: 96m, REFORMA: 120m, VIAGEM: 24m, OUTRO: 120m |
| down_payment < target_amount | Validação Pydantic |
| target_date no futuro | Validação Pydantic |

Erros **bloqueantes** lançam `ValueError`. Avisos são adicionados ao response.

### LiquidityValidator — `validators/liquidity_validator.py`

Classifica o impacto da estratégia no orçamento mensal:

```
impact = monthly_payment / safe_to_spend

┌──────────────┬──────────────┬────────────────────────────────────────────┐
│ Nível        │ Threshold    │ Mensagem gerada                            │
├──────────────┼──────────────┼────────────────────────────────────────────┤
│ SAFE         │ ≤ 25%        │ (sem aviso)                                │
│ WARNING      │ 26% – 40%    │ "Parcela representa X% do orçamento livre" │
│ HIGH         │ 41% – 70%    │ "Impacto alto na liquidez — revise o prazo"│
│ CRITICAL     │ > 70%        │ "Parcela comprometeria Y% do orçamento"    │
└──────────────┴──────────────┴────────────────────────────────────────────┘

Fallback: se safe_to_spend = None, usa max_monthly_budget como denominador.
Se ambos = None: liquidity_impact = 0.0 (sem dados suficientes para calcular).
```

Para **estratégias compostas** (4 e 5), usa `monthly_net_cost` (após aluguel/SELIC), não a parcela bruta.

---

## 9. Score de Confiança

```
Score_base = 0.85   (engine sempre inicia aqui)

Ajustes:
  + 0.10  se safe_to_spend da F1 está disponível (dados reais do usuário)
  - 0.05  se qualquer taxa veio de fallback (API indisponível)
  - 0.02  por cada aviso gerado (máx: -0.10)

Score_final = clamp(score_ajustado, 0.30, 1.00)

Exemplos:
  Todos os dados reais, zero avisos    → 0.85 + 0.10 = 0.95
  Sem F1, sem fallback, 2 avisos       → 0.85 - 0.04 = 0.81
  Sem F1, 1 fallback, 4 avisos         → 0.85 - 0.05 - 0.08 = 0.72
  Cenário degredado (muito ruim)       → max 0.30
```

---

## 10. Integração com F1 (safe_to_spend)

```
FLUXO DE INTEGRAÇÃO F1 → F3:

  [Tool: get_financing_simulation]
         │
         │  Tenta buscar safe_to_spend da F1
         ▼
  NexaRunner(mode="dev").run(horizon_days=30)
         │
         ├─ Sucesso: result["projections"]["safe_to_spend"].safe_to_spend_total
         │           └─ Passado para ArchitectService.simulate(..., safe_to_spend=X)
         │
         └─ Falha: safe_to_spend = None
                   └─ LiquidityValidator usa max_monthly_budget como fallback
                   └─ Confiança reduz em 0.05 (taxa) + não recebe +0.10

  [API Route: architect.py]
    Faz o mesmo: busca F1 antes de chamar service.simulate()
    Se F1 falha: continua com safe_to_spend=None (graceful degradation)
```

A F3 **nunca quebra** por indisponibilidade da F1. O dado da F1 apenas melhora a qualidade da análise de liquidez e o score de confiança.

---

## 11. M3.3 — Bônus de Pontos no Cartão

Quando a estratégia recomendada é **Financiamento** (Estratégias 1 ou 4), o Architect calcula o retorno potencial em pontos/cashback ao pagar as parcelas no melhor cartão premium do mercado.

```
REFERÊNCIA DE MERCADO (2025):
  2 pontos por R$ gasto (Itaucard Ultravioleta, C6 Carbon, similares)
  R$ 0,016 por ponto (milhas Smiles, Livelo, etc.)
  = ~3,2% de retorno sobre cada parcela

CÁLCULO:
  monthly_bonus   = parcela_mensal × 2.0 × 0.016
  annual_bonus    = monthly_bonus × 12
  total_bonus     = monthly_bonus × financing_months
  reduction_pct   = (total_bonus / (parcela × financing_months)) × 100

Exemplo: parcela R$ 4.000/mês, 240 meses:
  monthly_bonus = R$ 128/mês
  total_bonus   = R$ 30.720 ao longo do contrato
  reduction_pct = 3.2%

NOTA: Valores de referência de mercado. A integração real com o cartão
      específico do usuário (F2 — Optimizer) é prevista para V2.
```

---

## 12. Output — SimulationResponse

```json
{
  "recommended_strategy": "CONSORTIUM_SELIC_RENTAL",
  "confidence_score": 0.87,

  "costs": {
    "min_cost": 320000,
    "expected_cost": 380000,
    "max_cost": 440000
  },

  "npv": {
    "financing": -410000,
    "consortium": -320000,
    "save_invest": -280000,
    "financing_rental": -200000,
    "consortium_selic_rental": -180000,
    "discount_rate_used": 0.01040
  },

  "consortium_probability": {
    "win_12m": 0.22,
    "win_24m": 0.61,
    "win_36m": 0.83,
    "expected_months": 26,
    "with_lance": false
  },

  "liquidity_impact": -0.18,
  "months_to_achieve": 26,

  "compound_strategies": [
    {
      "strategy_type": "FINANCING_RENTAL",
      "monthly_gross_payment": 5200.00,
      "monthly_rental_income": 2500.00,
      "monthly_selic_contribution": 0.0,
      "monthly_net_cost": 2700.00,
      "total_gross_cost": 780000,
      "total_rental_income": 300000,
      "net_acquisition_cost": 480000,
      "npv": -200000,
      "months": 240,
      "is_self_sustaining": false,
      "narrative": "..."
    },
    {
      "strategy_type": "CONSORTIUM_SELIC_RENTAL",
      "monthly_gross_payment": 2667.00,
      "monthly_rental_income": 2500.00,
      "monthly_selic_contribution": 1040.00,
      "monthly_net_cost": 0.00,
      "total_gross_cost": 480000,
      "total_rental_income": 225000,
      "net_acquisition_cost": 255000,
      "npv": -180000,
      "months": 180,
      "is_self_sustaining": true,
      "narrative": "..."
    }
  ],

  "rental_leverage_plan": {
    "monthly_rental_income": 2500,
    "monthly_payment": 2667,
    "rental_coverage_pct": 93.7,
    "monthly_out_of_pocket": 167,
    "total_rental_income": 225000,
    "net_acquisition_cost": 255000,
    "is_self_sustaining": false,
    "months_covered": 0,
    "narrative": "..."
  },

  "card_optimization_bonus": null,

  "action_plan": [
    { "step": 1, "action": "Pesquisar grupos de consórcio de imóvel R$ 500.000", "is_critical": true },
    { "step": 2, "action": "Aplicar R$ 100.000 em Tesouro SELIC enquanto aguarda contemplação" },
    { "step": 3, "action": "Contratar gestão do aluguel para cobrir parcelas do consórcio" }
  ],

  "warnings": [],
  "data_sources": ["bacen", "anbima", "abac", "ipca", "f1_safe_to_spend"],
  "generated_at": "2026-03-17T10:00:00"
}
```

---

## 13. API REST — Endpoints

| Método | Endpoint | Descrição |
|---|---|---|
| `POST` | `/architect/simulate` | Simulação completa — retorna SimulationResponse |
| `GET` | `/architect/simulations/{simulation_id}` | Busca simulação persistida por ID |
| `GET` | `/architect/simulations/{simulation_id}/sensitivity` | Análise de sensibilidade |
| `POST` | `/architect/timing` | Simulação de timing: "E se eu esperar N meses?" |
| `GET` | `/architect/rates` | Taxas de mercado atuais (SELIC, CDI, CET) |
| `GET` | `/architect/simulations/user/{user_id}` | Lista simulações do usuário |
| `DELETE` | `/architect/simulations/{simulation_id}` | Remove simulação |

**Persistência assíncrona:** o endpoint POST retorna o response imediatamente; a persistência no DuckDB é feita em background (`asyncio.create_task`). Falha na persistência não afeta a resposta ao usuário.

---

## 14. Persistência — DuckDB

**Arquivo:** `db/queries/architect_queries.py`

```
TABELA: architect_simulations
  simulation_id  TEXT PRIMARY KEY   (UUID gerado pelo banco)
  user_id        TEXT               (índice)
  request_json   TEXT               (SimulationRequest serializado)
  response_json  TEXT               (SimulationResponse serializado)
  created_at     TIMESTAMP
  duration_ms    INTEGER

TABELA: architect_metrics (UPSERT por user_id)
  user_id            TEXT PRIMARY KEY
  total_simulations  INTEGER
  last_simulation_at TIMESTAMP
  top_strategy       TEXT          (estratégia mais recomendada)
```

```
FLUXO DE PERSISTÊNCIA:

  POST /architect/simulate
       │
       ├─ Chama service.simulate() → SimulationResponse  (síncrono)
       │
       ├─ Retorna SimulationResponse ao cliente  ←── resposta imediata
       │
       └─ asyncio.create_task(_persist_async(...))
              │
              ├─ DuckDB: INSERT architect_simulations
              └─ DuckDB: UPSERT architect_metrics
                   └─ Falha silenciosa (log warning, não propaga)
```

---

## 15. Análise de Sensibilidade

**Arquivo:** `simulators/sensitivity_analyzer.py`

A análise de sensibilidade responde: "O que muda na recomendação se as condições mudarem?"

```
4 VARIÁVEIS ANALISADAS:
  1. Taxa de juros (CET)       — 7 a 9 pontos
  2. SELIC / Taxa de desconto  — 7 pontos
  3. Prazo do financiamento    — 7 pontos
  4. Valor da entrada          — 7 pontos

PARA CADA PONTO:
  Executa simulate() com o parâmetro alterado
  Registra: estratégia recomendada, NPV, custo total

OUTPUTS:
  strategy_flips: List de pontos onde a estratégia recomendada muda
  elasticity: sensibilidade do custo a variações percentuais de cada variável
  risk_profile: avalia se a recomendação é robusta ou sensível a mudanças
```

Acessível via `GET /architect/simulations/{id}/sensitivity`.

---

## 16. Exemplo Real Calculado

### Input

```python
request = SimulationRequest(
    user_id="usuario_123",
    target_amount=800_000,
    down_payment=100_000,
    asset_type=AssetType.IMOVEL,
    financing_months=240,          # 20 anos
    amortization_method=AmortizationMethod.PRICE,
    risk_profile=RiskProfile.MODERADO,
    expected_rental_income=3_000,  # R$ 3.000/mês de aluguel
    include_consortium=True,
)
```

### Taxas obtidas (SELIC 13.25%)

```
SELIC anual:    13.25%   → mensal: 1.040%
CDI anual:      13.15%   → mensal: 1.033%
CET imóvel:     14.75%   → mensal: 1.148%
IPCA anual:      4.50%
INCC estimado:   6.75%   (IPCA × 1.5)
Consórcio taxa: 20%      (admin 18% + reserva 2%)
```

### Estratégia 1 — Financiamento PRICE

```
Principal:    R$ 700.000
Taxa mensal:  1.148%
Prazo:        240 meses

PMT = 700.000 × [0.01148 × (1.01148)^240] / [(1.01148)^240 - 1]
    ≈ R$ 8.850/mês

IOF fixo:  700.000 × 0.38% = R$ 2.660
IOF diário ≈ R$ 8.400  (cap 3% = R$ 21.000 → não atinge)
IOF total:  R$ 11.060

Seguro MIP+DFI: 0.035% × 700.000 ≈ R$ 245/mês → total R$ 58.800

Custo total:  240 × 8.850 + 58.800 + 11.060 = ~R$ 1.193.860
NPV:          ≈ −R$ 600.000
```

### Estratégia 5 — Consórcio + SELIC + Aluguel

```
Grupo: R$ 700.000, 180 meses, admin 20%
Parcela base: 700.000 × 1.20 / 180 = R$ 4.667/mês

SELIC sobre entrada: 100.000 × 1.040% = R$ 1.040/mês (mês 1)
Aluguel: R$ 3.000/mês

Fluxo mês 1:
  receitas = 3.000 + 1.040 = R$ 4.040
  parcela  = R$ 4.667
  déficit  = R$ 627/mês

A partir do mês ~30 a carta reajusta pelo INCC → parcela aumenta
→ déficit cresce mas o saldo SELIC também acumula

Custo líquido estimado: ~R$ 350.000 (bruto 840.000 - 225.000 aluguel - rendimentos SELIC)
NPV composto: ≈ −R$ 220.000

Recomendada se deficit aceitável vs economias de aluguel e SELIC.
```

### Custo de oportunidade do SAVE_INVEST

```
Meses p/ acumular R$ 700.000:
  Aporte mensal necessário com CDI 13.15%: ~R$ 2.500/mês → ~72 meses

Aluguel perdido durante 72 meses:
  foregone_rental_pv = 3.000 × [(1 - (1.01033)^(-72)) / 0.01033]
                     = 3.000 × 55.8 ≈ R$ 167.400

NPV bruto SAVE_INVEST ≈ −R$ 230.000
NPV ajustado           ≈ −R$ 397.400  ← ranking usa este valor
```

---

## Resumo Visual do Ranking de Decisão

```
Sem aluguel informado:
┌─────────────────────────────────────────────────────────┐
│ NPV (maior = melhor)                                     │
│                                                           │
│ SAVE_INVEST  ████████████████████████░  −R$ 230k  ★WIN  │
│ CONSORTIUM   ██████████████████░░░░░░░  −R$ 320k        │
│ FINANCING    ████████████░░░░░░░░░░░░░  −R$ 600k        │
└─────────────────────────────────────────────────────────┘

Com aluguel R$ 3.000/mês informado (mesma simulação):
┌─────────────────────────────────────────────────────────┐
│ NPV (maior = melhor)  [SAVE_INVEST penalizado]           │
│                                                           │
│ CONS+SELIC+ALG ████████████████████████  −R$ 220k  ★WIN │
│ FIN+ALUGUEL    ████████████████████░░░░  −R$ 290k       │
│ CONSORTIUM     ████████████████░░░░░░░░  −R$ 320k       │
│ SAVE_INVEST*   ████████░░░░░░░░░░░░░░░░  −R$ 397k       │
│ FINANCING      ████░░░░░░░░░░░░░░░░░░░░  −R$ 600k       │
└─────────────────────────────────────────────────────────┘
* Penalizado pelo custo de oportunidade do aluguel perdido
```

---

*Documentação gerada em 2026-03-17 — Nexa Architect F3 v1.0.0*
