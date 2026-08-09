# 03 — Otimizador de Cartões (F2)

> Descobre quanto dinheiro o usuário deixa na mesa usando o cartão errado — e
> recomenda o cartão certo para o perfil real de gastos dele.

## Em palavras simples
 
A maioria das pessoas escolhe cartão por propaganda, não por matemática. A
Nexa olha onde você realmente gasta (mercado? iFood? viagem?) e calcula, em
R$/mês, quanto cada cartão do mercado devolveria em cashback ou milhas —
descontando anuidade e considerando se você é elegível (renda mínima). O
resultado: "trocando para o cartão X você recupera R$ 84/mês".

## A base de conhecimento

**81 cartões de 37 emissores** (`data/cards/knowledge_cards.json`). Cada
registro é um `CardRecord` com estes campos (exemplo real, Nubank Roxinho):

```json
{
  "card_id": "nubank-roxinho", "issuer": "Nubank", "flag": "MASTERCARD",
  "card_type": "CASHBACK", "min_income": 0, "base_annuity": 0.0,
  "waiver_rules": { "type": "always_free" },
  "cashback_pct": 0.01, "cashback_cap": null, "cashback_default_pct": 0.01,
  "cashback_categories": [],
  "points_per_brl": null, "points_conversion_rate": 0.0,
  "loyalty_program": null, "benefit_tags": [],
  "revolving_interest_monthly": 0.1599,
  "data_trust_score": 0.93, "last_updated": "2025-03-01"
}
```

Campos que movem o cálculo: `card_type` (CASHBACK / POINTS / INVESTBACK),
`cashback_categories` (taxa **por categoria**, com `cap_monthly`),
`waiver_rules` (`always_free` / `spend_threshold` / `transaction_count` /
`none`), `min_income`, `loyalty_program` e `data_trust_score` — este último
entra **diretamente** na confiança da simulação, ou seja, dado curado com
menos certeza produz recomendação com menos peso.

---

## Como é calculado

### 1. Gasto elegível e cenários

```
spend_annual = monthly_avg_spend × credit_spend_ratio × 12
```

Só a fração que o usuário efetivamente coloca no crédito (`credit_spend_ratio`)
entra na conta. Tudo é simulado em **três cenários** (`_SCENARIO_FACTORS`):

| Cenário | Fator sobre o gasto |
|---|---|
| `min` | × 0,8 |
| `expected` | × 1,0 |
| `max` | × 1,2 |

Isso produz `net_gain_min / expected / max` — o intervalo mostrado ao usuário
não é chute, é o mesmo motor rodado com o gasto ±20%.

### 2. Anuidade efetiva — o "achievability gate"

O ponto sutil: um cartão com isenção por gasto **não é gratuito** se o usuário
não vai atingir o gasto. `_compute_annuity` resolve com probabilidade, não com
booleano:

```
achievability = max(0, 1 − (threshold − spend_annual) / threshold)
```

(gasto acima do threshold → 1,0)

- `always_free` → anuidade 0, `waived = True`;
- `spend_threshold` → só isenta se **`achievability ≥ 0,80`**; abaixo disso a
  anuidade é cobrada **integralmente** (conservador);
- `transaction_count` → assume que não atinge (conservador declarado);
- `none`/desconhecido → anuidade sempre cobrada.

### 3. Valor do benefício

**Cashback por categoria (M2.5)** — quando o cartão tem
`cashback_categories` e há perfil conhecido:

```
scale  = gasto_elegível_mensal / Σ(spend_by_category)
scaled = gasto_da_categoria × scale

cb_categoria = scaled × rule.pct         (categoria com regra própria)
             ou scaled × default_pct     (categoria sem regra)

se rule.cap_monthly e cb > cap → cb = cap_monthly    ← teto POR CATEGORIA
total_anual = Σ(cb × 12)
se card.cashback_cap → total_anual = min(total_anual, cashback_cap × 12)  ← teto GLOBAL
```

O reescalonamento por `scale` existe para que a soma das categorias respeite o
gasto elegível de crédito, em vez de somar o gasto total do usuário. E os dois
tetos são aplicados nessa ordem: por categoria primeiro, global depois.

Sem `cashback_categories`, cai no flat: `spend × cashback_pct`, com o mesmo
teto global.

**Pontos/milhas** — `points = spend × points_per_brl`, valorizados pelo
`MilesValuator` do programa; se o programa for desconhecido, fallback para
`(points / 1000) × points_conversion_rate` do próprio cartão.

### 4. Valoração de milhas — distribuição P25/P50/P75

`miles_valuator.py` guarda, por programa, a tripla **(P25, P50, P75) em
R$/ponto** — sincronizada com `miles_valuation.json`:

| Programa | P25 | P50 | P75 |
|---|---|---|---|
| smiles | 0,012 | 0,022 | 0,040 |
| livelo | 0,008 | 0,016 | 0,028 |
| nu_pontos | 0,008 | 0,014 | 0,022 |
| atomos | 0,007 | 0,014 | 0,024 |
| latam_pass | 0,013 | 0,021 | 0,035 |
| itau_multiplus | 0,013 | 0,017 | 0,023 |
| xp_pontos | 0,020 | 0,025 | 0,032 |
| membership_amex | 0,017 | 0,022 | 0,030 |
| esfera | 0,013 | 0,018 | 0,025 |
| stix | 0,012 | 0,018 | 0,025 |

**Qual percentil entra em cada cenário** — `get_rate` aceita os nomes do
simulador como alias:

| Cenário do simulador | Percentil da taxa | Fator de gasto | Resultado |
|---|---|---|---|
| `min` (alias de `pessimistic`) | **P25** | × 0,8 | `points_value_min` |
| `expected` | **P50** | × 1,0 | `points_value_expected` |
| `max` (alias de `optimistic`) | **P75** | × 1,2 | `points_value_max` |

Os cenários extremos **compõem duas variações**: a taxa do percentil **e** o
fator de gasto. O `min` não é "o mesmo gasto valorizado conservadoramente" — é
gasto 20% menor valorizado a P25. O intervalo resultante é, portanto, mais
largo do que a dispersão só das milhas.

> ⚠️ **O ranking usa P50, não P25.** O score parte de `net_gain_expected`, que
> vem de `values["expected"]` — P50. Os métodos `get_conservative_rate()` (P25)
> e `get_interval()` (banda P25–P75 quando `P75/P25 ≥ 1,5`) existem, mas
> **nenhum dos dois é chamado em lugar algum do código** — só aparecem na
> própria definição e no exemplo do docstring do módulo. A docstring de
> `get_conservative_rate` afirma *"Usado pelo scoring de ranking — princípio 1
> da arquitetura: 'Point values usam P25 do mercado, não média'"*, e essa
> afirmação está **desatualizada em relação ao código**. O princípio
> conservador está declarado, mas não implementado no caminho de ranking; o
> P25 só aparece através de `net_gain_min`, que é exibido, não ranqueado.

### 5. Ganho líquido e risco de liquidez

```
net_gain_expected = valor_do_benefício(expected) − annuity_effective
```

```
liquidity_impact = (annuity_effective / 12) / safe_to_spend
```

Regras de borda: anuidade zero → impacto 0 (independente do safe-to-spend);
`safe_to_spend` nulo/≤0 com anuidade → impacto **1,0** (CRITICAL). Essa
segunda regra é uma limitação conhecida e documentada no código: sem a F1
disponível, todo cartão com anuidade viraria CRITICAL, então o
`OptimizerService` usa `monthly_income` como fallback antes de simular.

### 6. Confiança da simulação — multiplicativa

```
confidence = data_trust_score
           × coverage_penalty
           × commitment_penalty
           × income_confidence
           × stability_factor
```

| Fator | Faixas |
|---|---|
| Cobertura de dados | ≥ 6 meses: 1,0 · 3–5: ×0,85 · 2: ×0,50 · < 2: ×0,25 |
| Comprometimento | `committed_percentage > 80%` → ×0,7 |
| Confiança da renda | o `confidence` do `IncomeProfiler` entra direto como multiplicador |
| Estabilidade (CV do gasto) | ≤0,15: 1,0 · ≤0,35: ×0,90 · ≤0,60: ×0,75 · >0,60: ×0,60 |
| Gasto estimado | `spend_is_estimated` → **teto de 0,50** |

Detalhe de implementação anotado no próprio código: `income_conf` **não** pode
usar `or 1.0`, porque `0.0` é falsy — uma confiança de renda explicitamente
zero precisa penalizar, não ser tratada como "ausente".

### 7. Elegibilidade (`card_loader.compute_eligibility_score`)

```
score = income_factor × spending_stability
        (+0,10 se o emissor já aparece nas transações do usuário)
```

`income_factor` por faixa de `annual_income / card.min_income`:

| Razão renda/mínimo | Fator | Mensagem ao usuário |
|---|---|---|
| ≥ 2,0 | 0,95 | "bem acima do mínimo exigido" |
| ≥ 1,5 | 0,80 | "acima do mínimo exigido" |
| ≥ 1,2 | 0,70 | "cobre o mínimo exigido" |
| < 1,2 | 0,60 | "no limite mínimo — aprovação provável mas não garantida" |
| `min_income = 0` | 1,00 | — |

**Penalidade de renda variável (MI.3)**: `income_pattern ∈ {PJ, MIXED}` **e**
`income_stability < 0,5` → `income_factor × 0,85`, com a razão explicada ao
usuário ("histórico irregular pode reduzir chances de aprovação").

### 8. Ranking — o score final

`CardRanking._compute_score`, na ordem exata:

```
1.  score = net_gain_expected × liquidity_multiplier
2.  score += benefits_bonus          (com regra dos 40%)
3.  score += trend_bonus             (tendência de categoria / queda de renda)
4.  score += bônus do cluster primário  (e penalidades multiplicativas)
5.  score += bônus dos ≤2 clusters secundários (só aditivos, peso 50%)
6.  score += life_stage_bonus × life_stage_confidence
7.  se confidence_score < 0,4  → score × 0,5
8.  se eligibility_score < 0,5 → score × 0,4
    senão se < 0,7             → score × 0,75
```

**Multiplicador de liquidez:**

| Risco | Multiplicador |
|---|---|
| SAFE | 1,00 |
| WARNING | 0,90 |
| HIGH | 0,60 |
| CRITICAL | 0,20 |

**Bônus de benefício com "filtro de viabilidade"**: um benefício só vale se o
perfil o usa de verdade —

```
gasto internacional > R$ 500/mês  e  tag INTERNACIONAL → +R$ 200/ano
gasto em viagem     > R$ 800/mês  e  tag LOUNGE        → +R$ 300/ano
```

**Regra anti-falso-positivo dos 40%**: se `benefits_bonus > 0,40 ×
net_gain_expected`, o bônus é descontado em 15% (`× 0,85`). Impede que um
cartão financeiramente ruim suba no ranking só por acumular selos de
benefício.

**Bônus de tendência** (`_trend_bonus`): categorias `SUBINDO`/`REEMERGINDO`
com gasto ≥ R$ 50/mês e tag relevante rendem

```
incremento = current_monthly × (min(ratio, 2,0) − 1)     [REEMERGINDO → ratio efetivo 1,3]
bônus_anual = min(incremento × 0,02 × 12,  R$ 300)
```

A taxa de 2% é deliberadamente genérica ("bônus de ordenação, não de
simulação"). Já a **renda em queda** penaliza: `direction = CAINDO` com
anuidade > R$ 400 →
`penalidade = min(anuidade × queda × 0,5, anuidade × 0,20)`.

**Ajustes por cluster comportamental** (primário; secundários entram só com os
termos aditivos, a 50% de peso, porque penalidade é identidade do cluster
principal):

| Cluster | Ajuste |
|---|---|
| `EXPLORADOR_GLOBAL` | +25% do `benefits_bonus` se LOUNGE/TRAVEL; +10% extra se perfil de viagem FREQUENTE/INTENSO |
| `URBANO_FOODIE` | se gasto em alimentação > R$ 500: `+ food_spend × 0,005 × (1,5 se GOURMET/ENTUSIASTA)` |
| `INVESTIDOR_CAUTELOSO` | anuidade > R$ 500 **e** ROI < 2× → × 0,90 |
| `FAMILIA_ESTRUTURADA` | supermercado+saúde+educação > R$ 400 → `+ family_spend × 0,004` |
| `DIGITAL_NATIVO` | anuidade 0 → +80; ≤ R$ 200 → +30; > R$ 500 com ROI < 2,5× → × 0,85 |
| `MICROEMPREENDEDOR` | anuidade 0 → +100; ≤ R$ 200 → +40; > R$ 400 com ROI < 2× → × 0,80; tag CASHBACK → +50 |
| `ESTRESSE_FINANCEIRO` | anuidade 0 → +60; **anuidade > R$ 200 → × 0,70** |

**Refinamento por estágio de vida** (só com `confidence ≥ 0,50`, e o bônus é
multiplicado pela própria confiança):

| Estágio | Bônus |
|---|---|
| `FAMILIA_BEBE` | farmácia+supermercado > R$ 200 → `spend × 0,006` |
| `NOMADE_DIGITAL` | tag INTERNACIONAL → +80 (economia de IOF); TRAVEL com gasto > R$ 300 → `+ travel × 0,004` |
| `INVESTIDOR_PREMIUM` | anuidade 0 → +60; ROI ≥ 2× → +50; anuidade > R$ 600 com ROI < 1,5× → **−70** |
| `SOLTEIRO_URBANO` | delivery+alimentação > R$ 300 → `spend × 0,005`; anuidade 0 → +30 |

**Regra pós-ordenação (segurança do usuário)**: se o 1º colocado tiver
`eligibility_score < 0,4` e existir outro com `≥ 0,6`, o elegível é promovido
ao topo. Recomendar o cartão matematicamente ótimo que o usuário não consegue
obter é pior do que recomendar o segundo melhor.

### 9. Multi-cartão (`multi_card_strategy.py`)

Constrói a carteira ótima escolhendo o melhor cartão **por categoria**, e
então poda: cartão com gasto direcionado `< R$ 200/mês`
(`_MIN_DIRECTED_SPEND_MONTHLY`) é removido — carregar plástico para R$ 50/mês
de gasto não compensa. Resultado:

```
net_annual_gain = Σ retorno_por_categoria − Σ anuidades_efetivas
vs_single_best  = net_annual_gain − melhor_cartão_único
```

`vs_single_best` é o número honesto: quanto a complexidade de 2 cartões
realmente compra em relação a simplesmente usar o melhor único.

### 10. Custo de oportunidade (`opportunity_cost.py`)

Compara o cartão atual contra todos os candidatos sobre a janela de **3 meses**
(padrão), usando o mesmo motor de recompensa (inclusive tetos normalizados por
`cap_monthly × months`):

```
difference             = recompensa_candidato − recompensa_atual
difference_monthly     = difference / months
difference_annualized  = difference × (12 / months)
```

### 11. Insights acionáveis (`insight_generator.py`)

Um insight só é gerado acima de gatilhos mínimos — o produto não interrompe
ninguém por R$ 3/mês:

| Insight | Gatilho |
|---|---|
| `TROCAR_PRIMARIO` | ganho ≥ R$ 20/mês |
| `PORTFOLIO_MULTI` | ganho ≥ R$ 30/mês |
| `ATIVAR_BENEFICIO` | ganho ≥ R$ 20/mês |
| `MUDAR_CATEGORIA` | ganho ≥ R$ 15/mês **e** gasto na categoria ≥ R$ 200/mês (máx. 2 insights de categoria) |
| Upgrade premium | `eligibility ≥ 0,85` e anuidade ≥ R$ 300/ano |

Filtros globais: `confidence ≥ 0,65` (`_INSIGHT_CONFIDENCE_GATE`) e ganho
mensal ≥ R$ 10 (`_INSIGHT_MIN_MONTHLY_GAIN`). O card `WAIVER_ALERT` calcula o
`monthly_gap` que falta para isentar a anuidade.

---

## Como funciona (técnico)

- **Endpoints**: `POST /optimizer/recommend`, `/simulate`, `/multi_card`,
  `/opportunity_cost`; `GET /optimizer/cards`, `GET /optimizer/roi/{card_id}`.
- Fluxo do `optimizer_service.py`: enriquece transações
  (`TransactionFeatureEnricher` — categoria canônica, merchant normalizado) →
  `profiler.py` constrói `UserProfile` → `simulator.py` calcula retorno por
  cartão → `ranking.py` ordena → `insight_generator.py` gera cards.
- Feedback loop: `models_orm.py` persiste relatórios; `recommendation_feedback`
  registra aceite/rejeição, consumido pelo job `intelligence_metrics` (doc 18).
- Categorias de cashback usam o vocabulário canônico do classificador
  (`alimentacao`, `supermercado`, `farmacia`, `viagem`, `transporte`,
  `streaming`...) — regra de integridade: categoria fora do vocabulário nunca
  casaria com gasto real.
- **Promoções de transferência** (`promotion_tracker.py`, R4.b): promoções
  bonificadas ativas com staleness guard (curadoria > 45 dias não alerta),
  matching por programa de fidelidade, card `TRANSFER_PROMO` no feed
  (engine 6/6h, dedup 3 dias) e tool `get_transfer_promotions` no chat.

## O que NÃO faz

- **Não solicita o cartão pelo usuário** — recomenda e explica; a contratação
  é no canal do emissor (`request_link` quando disponível).
- **Não conhece o limite aprovado** que o usuário teria — elegibilidade é
  estimativa por renda/estabilidade, não consulta ao bureau.
- **Não rastreia pontos acumulados** nos programas (saldo de milhas do
  usuário não é lido — Open Finance não expõe).

## Gaps e limitações

- **Base curada manualmente**: benefícios de cartão mudam com frequência;
  cada registro tem `last_updated` e `data_trust_score`, mas não há job de
  revisão automática (recomendado: revisão trimestral; não existe API pública
  de metadados de cartões no Brasil).
- **Valores de milhas são tabela estática** — `POINT_VALUE_DISTRIBUTIONS` tem
  parte sincronizada com `miles_valuation.json` (Mar/2026) e parte como
  "estimativa de mercado" hardcoded (latam_pass, itau_multiplus, xp_pontos,
  amex, esfera, stix). Não há coleta automática de cotação de milhas.
- **⚠️ O princípio "ranking usa P25" está declarado mas não implementado.**
  `get_conservative_rate()` e `get_interval()` são código morto (nenhuma
  chamada no repositório); o ranking usa P50 via `net_gain_expected`. Ou o
  ranking passa a usar o P25 como a docstring promete, ou a docstring precisa
  ser corrigida — hoje o código e a documentação interna se contradizem.
- **A taxa de 2% do bônus de tendência é genérica**, não a taxa real do cartão
  na categoria — assumido como bônus de ordenação.
- **Sem `safe_to_spend`, todo cartão com anuidade vira CRITICAL** no cálculo
  de liquidez; o serviço mitiga usando renda como fallback, mas a limitação
  está no simulador.
- **Isenção por `transaction_count` nunca é concedida** (assume que o usuário
  não atinge) — conservador, porém pessimista para quem transaciona muito.
- Cobertura: 81 cartões cobre o mercado relevante, mas não a cauda longa
  (regionais pequenos, variantes corporativas).
