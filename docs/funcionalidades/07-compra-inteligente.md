# 07 — Compra Inteligente (F7 / R1.a)

> No momento de pagar: Pix, débito, crédito à vista, parcelado ou CDC?
> Veredito em uma frase, com o custo líquido de cada opção.

## Em palavras simples

"Parcela em 12x sem juros ou paga no Pix com desconto?" — quase ninguém faz
essa conta, e ela muda com o SEU cartão (cashback), o SEU caixa (margem
segura) e o tamanho da compra. A Nexa responde na hora: "Pague com o cartão X
à vista — custo líquido R$ 2.940, R$ 180 mais barato que a pior opção. Cabe
no seu orçamento".

---

## Como é calculado

### 1. As quatro opções montadas

| Opção | `total_cost` | `monthly_cost` | `reward_value` |
|---|---|---|---|
| **PIX à vista** | valor | — | 0 (sem cashback) |
| **Cartão à vista** | valor | — | `valor × reward_rate` |
| **Cartão parcelado s/ juros** | valor | `valor / n` | `valor × reward_rate` |
| **CDC (crédito pessoal)** | `PMT × n` | `PMT` | 0 |

O `reward_rate` vem do melhor cartão do usuário na categoria, via F2 (doc 03).

**PMT do CDC** — Price padrão:

```
PMT = P × r / (1 − (1+r)^(−n))
```

A opção CDC **só é oferecida** quando `amount ≥ R$ 1.000`
(`_FINANCING_MIN_AMOUNT`) **e** `installments > 6`. Taxa: BACEN ao vivo, com
fallback **4,15% a.m.** (`_FINANCING_FALLBACK_MONTHLY_RATE`).

### 2. `net_cost_real` — tudo no mesmo instante de referência

Este é o núcleo do módulo, e o que diferencia a análise de uma calculadora
comum: **um real pago hoje não é um real pago daqui a doze meses**. As quatro
opções são trazidas a valor presente pelo CDI líquido de IR:

```
net_cost_real         = VPL(fluxo de pagamentos) − reward
opportunity_cost_gain = nominal − VPL      (quanto vale adiar o desembolso)
```

| Opção | fluxo | VPL |
|---|---|---|
| PIX à vista | paga hoje | preço (referência do zero) |
| Cartão à vista | paga na fatura (~1 mês) | `preço / (1+r)` |
| Cartão parcelado | meses 1..n | `Σ (P/n)/(1+r)^k` |
| CDC | meses 1..n | `Σ PMT/(1+r)^k` |

`purchase/opportunity_cost.py` ajusta cada opção de forma diferente:

**PIX / cartão à vista** — capital imobilizado é **custo**:

```
opportunity_cost = amount × cdi_net_mensal
net_cost_real    = amount − reward + opportunity_cost
```

**Cartão parcelado sem juros** — capital investido mês a mês é **benefício**:

```
ganho_k     = (P/n) × ((1 + r_net)^(n−k) − 1)     para k = 1..n
ganho_total = Σ ganho_k
net_cost_real = P − reward − ganho_total
```

Cada parcela `k` fica rendendo pelos `(n−k)` meses até ser paga. É a
formalização matemática do "parcelado sem juros é desconto disfarçado".

**CDC** — **sem ajuste**:

```
net_cost_real = total_cost − reward
```

com o comentário explícito no código: *"o banco já precificou o tempo — sem
ganho de oportunidade"*. Aplicar o ganho do CDI aqui seria contar o benefício
duas vezes.

O CDI é líquido de IR pela mesma **tabela regressiva** do resto do produto,
indexada pelo prazo em meses: ≤6 → 22,5% · ≤12 → 20% · ≤24 → 17,5% · >24 →
15%. CDI de fallback: **14,75% a.a.** (`_CDI_FALLBACK`).

**O ranking final é por `net_cost_real` crescente** — não por custo nominal.

### 3. Penalidades contextuais (ordenação, não bloqueio)

Antes de ordenar, opções de cartão recebem penalidade quando o contexto pede.
A penalidade mexe no `net_cost_real` para **empurrar a opção para baixo no
ranking**, sem removê-la — o usuário continua vendo tudo.

**Pressão da fatura** (`_apply_invoice_penalty`, ver doc 02):

| Pressão | Efeito no `net_cost_real` das opções de cartão |
|---|---|
| CRITICAL | × 1,20 |
| HEAVY | × 1,10 |

**Burn rate** (`_apply_burn_rate_penalty`) — atinge só `CARTAO_PARCELADO`:

| Alerta | Efeito |
|---|---|
| CRITICAL | × 1,10 |
| WARNING | × 1,05 |

A lógica: parcelar compromete meses futuros, e quem já está gastando acima do
ritmo é justamente quem menos deveria assumir compromisso novo.

### 4. Escolha da recomendação (`_pick_recommendation`)

```
outflow_mensal(o) = monthly_cost   se parcelado (installments > 1)
                    total_cost     caso contrário
```

1. Sem `safe_to_spend` disponível (ou ≤ 0): devolve a de menor `net_cost_real`,
   pulando qualquer opção marcada `EVITAR`;
2. Filtra as opções cujo `outflow_mensal ≤ safe_to_spend` e devolve a mais
   barata entre elas;
3. **Se nenhuma cabe**: adiciona o aviso *"Esta compra (R$ X) excede sua margem
   atual (R$ Y). Considere adiar ou reduzir o valor."* e devolve mesmo assim a
   de menor custo real — informa, não bloqueia.

### 5. Impacto de liquidez (`_build_liquidity_impact`)

```
after = max(0, safe_to_spend − outflow_mensal)
```

| Risco | Condição |
|---|---|
| CRITICAL | `outflow_mensal > safe_to_spend` (não cabe) |
| HIGH | sobra `< R$ 300` |
| MEDIUM | sobra `< R$ 1.000` |
| LOW | sobra `≥ R$ 1.000` |

### 6. Contexto agregado

O `analyze()` puxa, para compor a explicação: perfil de renda
(`confidence ≥ 0,5`), perfil de consumo, safe-to-spend, invoice horizon,
melhor cartão, taxas de mercado, contexto de anomalias, burn rate, orçamento
50/30/20 e **metas ativas** — o raciocínio devolvido menciona quando a compra
atrapalha uma meta em andamento.

### 7. Revisão retroativa (`purchase/post_purchase.py`)

Varre compras à vista dos **últimos 14 dias** (`_LOOKBACK_DAYS`) com valor
**≥ R$ 300** (`_MIN_PURCHASE_BRL`), infere o método usado pela descrição
(`_infer_paid_method`) e roda o mesmo motor para calcular quanto o usuário
teria economizado com a opção ótima. Cada transação já analisada é marcada
como vista (`_mark_seen`), então o card não repete.

Vira card `PURCHASE_FOLLOWUP` no feed e tool `review_recent_purchases` no chat.

---

## Como funciona (técnico)

- **Endpoints**: `POST /purchase/analyze`,
  `GET /purchase/checkout-context/{user_id}` (resposta compacta para modal /
  share-sheet / extensão de navegador — veredito em uma frase, opção
  recomendada, risco de liquidez, lista curta),
  `GET /purchase/recent-review/{user_id}`.
- Confiança: `confidence_score` na resposta reflete a qualidade dos dados do
  usuário (histórico curto → confiança menor, dito explicitamente).
- Gating: 3 consultas/mês no plano Free (contador `purchase_checks`).

## O que NÃO faz

- **Não conhece promoções do lojista** (desconto Pix específico da loja) — o
  usuário informa o preço de cada modalidade se quiser precisão máxima.
- **Não executa o pagamento**.
- **Não recomenda rotativo/parcelamento de fatura** — nunca; se não cabe, o
  veredito é "não cabe", com o impacto mostrado.

## Correções de 2026-08

**Quatro integrações estavam mortas** — cada uma estourando em toda chamada e
sendo engolida pelo `except` do seu fetcher, sem nada na resposta denunciando:

| chamada | erro |
|---|---|
| `IncomeProfiler().analyze()` | a classe só tem `build` |
| `CashflowProjector().project(horizon_days=30)` | é parâmetro do **construtor** |
| `from app.core.db.session import get_db_session` | o módulo exporta `get_db` |
| `OptimizerService` | recebia `request.monthly_income` cru (None sem digitação) |

Consequência: `safe_to_spend` ficava sempre em zero, então **todo usuário lia
"esta compra excede sua margem disponível (R$ 0,00)"** e recebia liquidez
`CRITICAL` — inclusive quem tem folga de sobra. E sem renda resolvida o
otimizador recusava, o `reward_rate` ficava em zero e o cashback nunca entrava
na conta: cartão à vista empatava com PIX até em centavos.

Num usuário com R$ 9.000 de renda e R$ 2.800 de aluguel, antes e depois:

| | antes | depois |
|---|---|---|
| fontes de contexto vivas | 4 de 10 | **9** |
| `confidence_score` | 0,40 | **1,00** |
| `safe_to_spend` | R$ 0,00 | **R$ 10.262,50** |
| risco de liquidez | CRITICAL | **LOW** |
| cashback considerado | R$ 0,00 | **R$ 66,75** |

Também corrigido:

- **Preço diferenciado por modalidade** (`cash_price`, `installments_total`).
  Era a pergunta de abertura da feature e não havia onde informá-la.
- **Float do cartão à vista**: recebia a mesma penalidade do PIX, como se
  saísse do bolso hoje. Compra no cartão é paga na fatura ~30 dias depois.
- **Expoente das parcelas**: era `(n−k)`, convenção de pagamento no ato.
  Parcela de cartão cai na fatura seguinte, então é `k`.
- **CDC na mesma régua**: era medido em reais nominais somados enquanto as
  outras opções ganhavam crédito de tempo (R$ 222 de inconsistência em
  R$ 3.000/12x).
- **Penalidade de ritmo travada pela capacidade**: burn rate mede RITMO, não
  capacidade, e dispara com facilidade — um usuário gastando 12% da renda já
  sai como WARNING, e aluguel aparece "acima do ritmo" todo dia 10. O mesmo
  relatório dizia "risco LOW, margem de R$ 10.262" e encarecia o parcelado em
  11%. Agora ritmo só reordena quando a folga é menor que R$ 1.000.

## Gaps e limitações

- **O desconto à vista depende do usuário informar** `cash_price` — a Nexa não
  conhece a promoção da loja. Sem ele, os dois preços são tratados como iguais.
- **A sensibilidade do burn rate não foi corrigida**, só isolada aqui. O
  detector acusa WARNING com 12% da renda gasta e trata despesa fixa mensal
  como "acima do ritmo" — é defeito da feature de alertas, não do F7.
- **O float do cartão é 1 mês fixo**, premissa declarada e não medição: o real
  varia de ~1 a ~40 dias conforme a compra caia antes ou depois do fechamento.
  O `InvoiceHorizon` sabe o dia de fechamento quando há dado — quando souber, é
  de lá que o número deve vir.
- **CDC usa taxa média de mercado** (BACEN, fallback 4,15% a.m.) — a taxa real
  do usuário pode ser melhor ou pior; o Negociador (doc 08) ajuda a melhorar.
- **O `reward_rate` é uma taxa única**, não a taxa da categoria específica da
  compra — a granularidade por categoria existe no F2, mas aqui entra
  agregada.
- **Penalidades são multiplicadores fixos** (1,05 / 1,10 / 1,20) calibrados por
  julgamento, não por dado — funcionam como desempate, não como precificação.
- **A revisão retroativa olha 14 dias e compras ≥ R$ 300** (constantes de
  produto); janelas maiores viram ruído, e o método de pagamento é
  *inferido da descrição*, o que pode errar.
