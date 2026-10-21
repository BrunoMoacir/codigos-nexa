# 09 — Radar de Oportunidades (OPP)

> Encontra dinheiro parado rendendo zero (ou poupança rendendo pouco) e
> compara o mercado inteiro de renda fixa — por retorno LÍQUIDO após imposto,
> sem comissão de ninguém.

## Em palavras simples

Todo comparador de investimento que você conhece ganha comissão do banco que
ele recomenda. A Nexa não: o ranking é por quanto sobra NO SEU BOLSO depois do
IR, com dados publicados pelas próprias instituições no Open Finance. E antes
de comparar, ela detecta o problema: "você tem R$ 5.000 parados na conta além
da sua reserva — isso renderia R$ 480/ano líquidos num CDB 110%".

---

## Como é calculado

### 1. OPP.1 — Dinheiro parado (`services/idle_money_detector.py`)

```
emergency_reserve = reserve_months × avg_expenses_3m
idle_amount       = max(0, gross_idle_amount − emergency_reserve)
```

**A reserva protegida varia pela fragilidade financeira do usuário** (FSS):

| `fss_level` | Meses de despesa protegidos |
|---|---|
| SAUDAVEL | 6 |
| ATENCAO | 6 |
| ALERTA | **9** |
| CRITICO | **9** |
| desconhecido/ausente | 6 (padrão) |

O comentário no código é preciso sobre a semântica: *"aqui é uma margem de
segurança a NUNCA sugerir investir, não uma meta de poupança"* — e alerta para
não confundir com `goals/profile_advisor.py::_EMERGENCY_MONTHS_BY_FSS`, que
responde a pergunta diferente. Quem está em ALERTA/CRÍTICO tem **mais** dinheiro
blindado contra a sugestão de investir, não menos.

**Duas fontes de saldo bruto**, com fallback:

| `idle_source` | Origem |
|---|---|
| `REAL_BALANCE` | `account_balances` (conta CHECKING), com frescor de 7 dias |
| `CASHFLOW_PROXY` | soma cumulativa de **todas** as transações conhecidas |

A janela de **3 meses completos anteriores ao mês atual** é usada para
`avg_income`/`avg_expenses` e para dimensionar a reserva — não para o saldo.
O divisor é o número de meses que o dado **realmente cobre**, não a largura da
janela: com 1 mês de histórico a média é sobre 1 mês, e `months_analyzed`
carrega esse número. Mínimo de 2 meses (`_MIN_MONTHS`) para
`has_sufficient_data`, que também é negado quando o histórico é antigo demais
(nada na janela → `historico_desatualizado`).

> **Correção de 2026-08.** O filtro não tinha limite superior — pegava o mês
> corrente, pela metade — e o divisor era sempre 3, porque o cutoff é sempre 3
> meses atrás. Os dois juntos erravam em direções opostas conforme o formato do
> histórico. Com gasto real de R$ 4.800/mês (reserva correta R$ 28.800):
>
> | histórico | reserva calculada |
> |---|---|
> | 3 completos + mês corrente pela metade | R$ 21.600 |
> | 3 completos + mês corrente cheio | R$ 38.400 |
> | 1 mês | **R$ 9.600** |
> | só dado antigo (12 meses de 2025) | R$ 115.200 |
>
> O caso de 1 mês é o perigoso: a reserva protegida virava um terço da real, e
> o motor passaria a sugerir investir dinheiro que é reserva de emergência. E
> como `months` era constante, `has_sufficient_data` era sempre verdadeiro — o
> status `NO_DATA` era **inalcançável em produção**.
>
> Os 181 testes existentes passavam nos dois estados: as asserções sobre a
> reserva usavam a saída do próprio detector como valor esperado
> (`expected_months * result.avg_expenses_3m`), verificando a multiplicação e
> nunca o número. Foram reescritas para comparar contra a despesa conhecida do
> cenário.

O campo continua se chamando `avg_expenses_3m` por compatibilidade da API, mas
a média é sobre `months_analyzed` meses — que pode ser menor ou maior que 3.

**Confirmação temporal** (`opportunity_engine.py`) — evita alertar por
oscilação de um dia:

```
CONFIRMED   → idle_amount ≥ R$ 500 em ≥ 90% dos últimos 30 dias de snapshots
PRELIMINARY → cold start (< 30 dias) ou oscilação abaixo do threshold
```

O status é declarado ao usuário, com o texto explicando qual dos dois é.

### 2. OPP.2 — Catálogo vivo (`connectors/open_finance_products.py`)

Varre **todos os participantes do diretório Open Finance** (~45 endpoints
segundo o comentário do conector, aferido em 2026-07; teto de segurança
`_MAX_INSTITUTIONS = 80`)
em paralelo, com paginação, filtro pessoa física, canonicalização de marca
("ITAU UNIBANCO S A" = "Itaú") e dedup por `(banco, tipo, liquidez)`.
Números de validação ao vivo reportados no projeto (~78 produtos de ~23
instituições em ~13s) referem-se a uma execução pontual do job — não são
verificáveis a partir do repositório, já que `product_catalog.json` é gerado em
runtime e não versionado.

**Duas regras de sanidade sobre a taxa publicada:**

```
plausibilidade:  30% ≤ cdi_pct ≤ 200%      → fora disso, o produto é descartado
teaser:          cdi_pct > 130%            → product["promotional"] = True
```

O comentário justifica os 130%: *"acima de 130% do CDI é quase sempre teaser
promocional (prazo curto…)"*. A flag não elimina o produto — ela o **rebaixa
no ranking** (ver abaixo).

Job diário 02h30 persiste em `product_catalog.json`; fallback é o catálogo
curado versionado. O comparator recarrega por mtime/TTL — o job atualiza sem
restart.

### 3. IR regressivo real (`fiscal/ir_pf_calculator.py`)

O mesmo motor usado pelo módulo de impostos (doc 12). Cobre 8 tipos:
`CDB`, `LCI`, `LCA`, `CRI`, `CRA`, `DEBENTURE_INCENTIVADA`, `POUPANCA`,
`TESOURO_SELIC` — dos quais **6 são isentos** para PF (todos menos CDB e
Tesouro).

Conversão convencional de mercado: `holding_days = holding_months × 30`.

**Tesouro SELIC** tem tratamento próprio, incluindo a **taxa de custódia B3**:

```
period_rate  = (1 + selic_annual)^anos − 1
gross_yield  = principal × period_rate

avg_position = principal + gross_yield / 2         ← estoque médio
custody_base = max(avg_position − 10.000, 0)       ← limite isento
custody_fee  = custody_base × custody_annual × anos

taxable_yield = max(gross_yield − custody_fee, 0)
ir_brl        = taxable_yield × aliquota_regressiva
net_yield     = gross_yield − custody_fee − ir_brl
```

Duas sutilezas: a custódia incide sobre o **estoque médio** (não sobre o
principal inicial), e é **deduzida antes do IR** — que é o tratamento correto.
Sem isso, o Tesouro apareceria melhor do que é.

**Breakeven LCI vs CDB**:

```
cdb_net_rate   = taxa_bruta_cdb × (1 − aliquota_ir_do_prazo)
lci_breakeven  = cdb_net_rate
```

Ou seja: a LCI precisa apenas superar a taxa **líquida** do CDB, porque rende
100% da própria taxa sem IR. É o "Modo Imposto Zero" (T2, doc 12).

### 4. Ranking líquido (`services/bank_comparator.py`)

Ordena por `annual_rate_net_pct` — **taxa após IR e custos**, nunca a taxa
bruta de vitrine.

```
monthly_gain = amount × ((1 + net_annual_pct/100)^(1/12) − 1)
annual_gain  = ir_result.net_yield_brl
```

**A chave de ordenação é uma tupla, e a ordem dos campos é a política do
produto:**

```python
# perfil que precisa de liquidez diária (FSS frágil):
(not eligible,  liquidity_days > 1,  promotional,  −net_rate)

# padrão:
(not eligible,  promotional,  −net_rate)
```

Lendo em português: **inelegíveis vão para o fim; teasers promocionais vêm
depois de todas as taxas permanentes; só então ordena por rendimento líquido
decrescente.** Um CDB de 135% do CDI por 30 dias **nunca** aparece em primeiro
lugar, mesmo tendo o maior número. E para perfil frágil, liquidez diária tem
prioridade sobre rendimento — antes de "render mais", vem "poder sacar".

Tesouro SELIC entra como item sintético do mesmo ranking (OPP.3), comparado de
igual para igual.

### 5. Poupança vs CDI (`services/savings_rate.py`)

Implementa a **regra oficial da Lei 12.703/2012**, com os dois ramos:

```
se SELIC_meta_anual > 8,5% a.a.:
    remuneração_mensal = 0,5% + TR                 [regra antiga]
senão:
    remuneração_mensal = 70% × SELIC_mensalizada + TR
```

O código destaca um detalhe frequentemente errado: **a TR entra nos dois
ramos**, não é exclusiva de um. O resultado carrega qual ramo foi aplicado
(`SELIC_GT_8_5` / `SELIC_LTE_8_5`) — auditável. Poupança abaixo do CDI gera o
card `SAVINGS_BELOW_CDI`.

### 6. Bank Match (`services/bank_match.py`)

Responde "qual banco é melhor **para mim**", combinando 4 componentes.
**Os pesos mudam com o perfil**:

| Componente | Padrão | Perfil frágil (FSS) | Perfil investidor |
|---|---|---|---|
| Rendimento (`yield`) | 0,40 | **0,25** | **0,50** |
| Tarifas (`fees`) | 0,30 | **0,40** | 0,20 |
| Cartões (`card`) | 0,15 | 0,10 | 0,15 |
| Fit comportamental (`fit`) | 0,15 | **0,25** | 0,15 |

O comentário no código resume a decisão: para perfil frágil, *"sobrevivência >
rendimento"* — tarifa evitada vale mais que meio ponto de CDI.

**Score de cartões por banco** — integração leve e deliberada com o F2: conta
quantos cartões do emissor existem no catálogo e mede a força do melhor:

```
strength = 1,0
         + 0,5  se não tem anuidade
         + 0,5  se tem tag alinhada ao cluster
                (TRAVEL/LOUNGE → EXPLORADOR_GLOBAL; FOOD/CASHBACK → URBANO_FOODIE)
```

Não roda a simulação completa do OptimizerService (que exigiria renda e
transações) — *"aqui basta saber se o banco sustenta uma boa estratégia de
cartão"*. Falha aberta: sem catálogo, nota neutra (`_NEUTRAL_SCORE = 50`).

Existe ainda uma **diferença mínima de score** exigida para recomendar troca de
banco — evita sugerir migração por diferença irrelevante.

**Tarifas**: usa as reais do usuário quando detectadas (`_detect_real_fees` via
FeeDetector), caindo no projetado do scorecard quando não há dado — e o
resultado marca quais bancos tiveram tarifa real vs. projetada.

---

## Como funciona (técnico)

- **Endpoints**: `GET /opportunities/{user_id}`, `/{user_id}/banks`,
  `/{user_id}/bank-match`, `/products` (catálogo público — qualquer um pode
  auditar), `/savings-vs-cdi`, `/treasury-vs-cdb-vs-savings`;
  `POST /opportunities/compare`.
- **OPP.5 Passos práticos** (`services/switch_steps.py`): onde clicar para
  executar a troca, por produto.
- **Scorecard por banco** (`services/bank_scorecard.py`) e risco do emissor
  (`calculators/issuer_risk.py`).
- Job diário `opportunity_scan` (03h00) grava `opportunity_snapshots` e gera
  cards `IDLE_MONEY_DETECTED` / `SAVINGS_BELOW_CDI` (dedup 1×/mês).
- Disclaimer regulatório em todas as respostas (não é recomendação CVM).
- Gating: endpoints por usuário exigem plano Pro.

## O que NÃO faz

- **Não executa a aplicação** (F6 sweep automático depende da fase de
  iniciação de pagamento do Open Finance).
- O primeiro contrato do F6 está disponível em
  `POST /api/v1/opportunities/{user_id}/sweep/preview`: ele calcula uma
  proposta limitada ao `idle_amount` após a reserva de emergência, exige
  consentimento e não movimenta dinheiro. A execução permanece bloqueada até
  existir iniciação de pagamento Open Finance fase 4.
- **Não compara fundos, ações ou previdência** — escopo é renda fixa bancária
  (CDB/RDB/LCI/LCA) + Tesouro SELIC.
- **Não recebe comissão** — estruturalmente: nenhum link é afiliado.

## Gaps e limitações

- **Os meses de reserva por FSS (6/6/9/9) não foram validados com
  produto/jurídico** — o próprio código anota isso como risco em aberto.
- **`CASHFLOW_PROXY` soma todas as transações conhecidas** como saldo — se o
  extrato não começa do zero real da conta, o saldo ocioso estimado erra. O
  `REAL_BALANCE` (quando disponível e fresco há ≤ 7 dias) é sempre preferido.
- **Cobertura** = participantes do Open Finance com renda fixa publicada
  (~23 instituições hoje; cresce com a adesão). Corretoras fora do diretório
  e produtos de plataforma exigiriam fontes adicionais (ANBIMA).
- **Qualidade dos dados publicados varia por instituição** (faixas vazias,
  valores estranhos) — a normalização é defensiva e descarta o
  ininterpretável, com a faixa de plausibilidade 30–200% do CDI.
- **O corte de 130% para "promocional" é heurístico**, não uma classificação
  informada pelo emissor — um CDB legitimamente acima de 130% seria rebaixado
  junto com os teasers.
- **`holding_days = meses × 30`** é aproximação convencional; próximo às
  fronteiras da tabela de IR (180/360/720 dias), a alíquota pode divergir do
  caso real por alguns dias.
- **Rating de crédito do emissor**: produtos do catálogo vivo saem com rating
  "N/A" (o opendata não publica rating; o FGC cobre até R$ 250k e isso é dito).
