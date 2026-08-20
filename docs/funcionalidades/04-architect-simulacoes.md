# 04 — Nexa Architect: Simulações de Grandes Decisões (F3)

> Para decisões de dezenas de milhares de reais — carro, imóvel — compara
> financiamento, consórcio e "investir e comprar à vista" com matemática de
> verdade: VPL, Monte Carlo com modelo macro e dominância estocástica.

## Em palavras simples

"Financio, faço consórcio ou junto dinheiro?" é a pergunta de maior valor
unitário da vida financeira, e ninguém responde com isenção (o banco quer
vender financiamento, a administradora quer vender consórcio). O Architect
simula os três caminhos com os SEUS números e devolve um ranking com intervalo
de confiança — "no cenário mediano, investir e comprar em 28 meses sai R$ 14
mil mais barato que financiar; em 95% das simulações, entre R$ 8k e R$ 19k".

---

## Como é calculado

### 1. Financiamento (`calculators/financing.py`)

**PRICE (Sistema Francês, parcela fixa):**

```
r   = (1 + taxa_anual)^(1/12) − 1          ← taxa mensal EQUIVALENTE, não /12
PMT = P × [ r(1+r)^n / ((1+r)^n − 1) ]
```

Note que a conversão anual→mensal é **geométrica** (`(1+i)^(1/12)−1`), não a
divisão por 12 que a maioria das planilhas usa. A tabela de amortização é
montada mês a mês: `juros = saldo × r`, `amortização = PMT − juros`,
`seguro = saldo × taxa_seguro`, com o saldo forçado a zero na última parcela.

**SAC** — amortização constante, com suporte a **correção monetária mensal do
saldo devedor** (TR/IPCA), modelando o SAC+TR típico do SFH (Caixa/SBPE).

**IOF real, em duas componentes** (Resolução BACEN 3.516/2007):

| Componente | Taxa |
|---|---|
| IOF fixo | 0,38% sobre o principal |
| IOF diário | 0,0082% por dia sobre o saldo de cada parcela, limitado a 365 dias |
| Teto | 3% do principal |

**Seguros obrigatórios** — taxa mensal sobre o saldo devedor, por tipo de bem:

| Bem | Taxa mensal | Observação |
|---|---|---|
| Imóvel | 0,035% | MIP + DFI combinados (faixa SUSEP/Caixa) |
| Veículo | 0,200% | seguro auto estimado |
| Moto | 0,180% | |
| Caminhão | 0,150% | |
| Outros | 0% | sem seguro padrão |

**CET (Custo Efetivo Total)** — não é a taxa contratual, é resolvido
numericamente por **Newton-Raphson**: acha a taxa mensal `r` tal que

```
principal_líquido = Σ parcela_t / (1+r)^t
onde  principal_líquido = principal − IOF_total − tarifa_administrativa
      parcela_t         = PMT_t + seguro_t
```

Ou seja, o CET reflete o que o tomador **realmente recebeu** contra o que vai
**realmente pagar**. Funciona igual para PRICE (parcelas iguais) e SAC
(parcelas decrescentes). Retorna 0,0 se não convergir.

### 2. Consórcio (`calculators/consortium.py`)

Custo nominal:

```
custo_total = valor_da_carta × (1 + taxa_admin + fundo_reserva)
```

Mas a parte difícil é **quando** você é contemplado — e isso é simulado, não
estimado. `_simulate_single_run` roda a assembleia mensal:

1. **Sorteio**: probabilidade `1 / participantes_restantes` de ser sorteado;
2. **Lances**: `(contemplados_por_mês − 1)` vagas disputadas. Os lances do
   grupo seguem **log-normal** (cauda direita realista — sempre positivo, com
   alguns lances muito agressivos), com a média decaindo exponencialmente:

```
média(t) = 0,35 × exp(−λ·t)     com  λ = ln(2) / (0,30 × prazo)
```

Ou seja: a média dos lances começa em 35% da carta e cai pela metade a cada
30% do prazo — modelando o fato real de que lances agressivos se concentram no
início do grupo. No final, quando `média < 1%`, os lances viram simbólicos
(uniforme 0–5%). O usuário é contemplado se seu lance ≥ o menor lance vencedor
do mês.

Parâmetros: grupo de 100 participantes, 2 contemplados/mês, **2.000
simulações**, seed opcional para reprodutibilidade. Lance embutido (`fixed`)
usa **25% da carta** (faixa real ABAC: 10–30%).

**Reajuste da carta** por índice, conforme o bem:

| Bem | Índice | Taxa a.a. |
|---|---|---|
| Imóvel | INCC | 7,0% |
| Veículo / moto / eletro | IPCA | 4,5% |
| Caminhão | IPCA + setorial | 5,0% |
| Serviço | IPCA serviços | 6,0% |

Saída: `contemplation_month_expected` (P50) + percentis **P10/P25/P50/P75/P90**
e a probabilidade acumulada de contemplação por marco. É por isso que o
intervalo do consórcio é largo — porque a realidade é.

### 3. Investir e comprar à vista (`calculators/investment.py`)

Acumulação com aporte mensal, **IR regressivo real** aplicado por prazo:

| Prazo de aplicação | Alíquota |
|---|---|
| até 180 dias | 22,5% |
| 181–360 dias | 20,0% |
| 361–720 dias | 17,5% |
| acima de 720 dias | 15,0% |

Dois modos de tributação são modelados:
- **Come-cotas** (fundos de longo prazo): 15% semestral sobre o rendimento,
  com o IR final incidindo só sobre o rendimento acumulado desde o último
  come-cotas — e a alíquota efetiva reportada é
  `total_ir_pago / rendimento_bruto`;
- **Por depósito** (renda fixa direta): cada aporte `k` é tributado pela
  alíquota do **seu próprio prazo de permanência** (`(n−k) × 30 dias`), não
  pelo prazo total. Aportes recentes pagam mais IR — como na vida real.

### 4. VPL, TIR e a taxa de desconto (`calculators/npv.py`)

```
VPL = −I₀ + Σ CF_t / (1 + r_efetiva)^t
```

Com suporte a **VPL real (equação de Fisher)** quando há inflação:

```
r_efetiva = (1 + r_nominal) / (1 + inflação) − 1
```

A TIR (`calculate_irr`) usa múltiplos chutes iniciais e **detecta
multiplicidade de raízes** pela regra de Descartes: se o fluxo troca de sinal
mais de uma vez, a TIR retornada é sinalizada como possivelmente não-única —
em vez de devolver um número silenciosamente ambíguo.

**A taxa de desconto vem do perfil de risco** (`_get_investment_rate`):

```
cdi_líquido      = CDI × 0,85            (IR 15%, prazo ≥ 720 dias)
taxa_agressiva   = min(CDI × 1,60,  18% a.a.)
```

Com `risk_score` disponível, a taxa é **interpolada continuamente**:

```
taxa = cdi_líquido + (taxa_agressiva − cdi_líquido) × risk_score
```

Isso elimina os saltos discretos entre perfis. Sem score, cai no mapeamento
por enum: CONSERVADOR → `cdi_líquido`; MODERADO (e `None`) → `× 1,10`;
AGRESSIVO → `taxa_agressiva`.

### 5. Risk Scorer (`validators/risk_scorer.py`)

Score 0–1 de tolerância a risco, como média ponderada de 6 componentes —
**com pesos diferentes por tipo de ativo**. Ex.:

| Componente | Imóvel | Veículo |
|---|---|---|
| Volatilidade da renda | 0,30 | 0,22 |
| Comprometimento da renda | 0,18 | 0,30 |
| Profundidade da reserva | 0,12 | 0,10 |
| Regularidade de poupança | 0,15 | 0,20 |
| Aderência ao horizonte | 0,18 | 0,10 |
| Proporção investida | 0,07 | 0,08 |

Faixas: `< 0,35 → CONSERVADOR`, `> 0,65 → AGRESSIVO`, meio → MODERADO.

Detalhe honesto: componentes obtidos por **proxy** (sem dado real do Open
Finance) são **limitados a 0,50** — `investment_ratio` estimado por
`income_stability × 0,5`, `savings_regularity` derivado do superávit médio do
extrato. Um score construído com fallbacks nunca alcança a confiança de um
score construído com dados reais, e o `risk_score_confidence` reporta isso
separadamente.

### 6. Monte Carlo macro (`simulators/macro_scenario.py`)

Não é ruído aleatório em cima de uma taxa fixa — é um **VAR(1) de três
variáveis** (Selic, IPCA, valorização do ativo) calibrado com médias
brasileiras 2015–2025:

```
x_t = μ + A·(x_{t−1} − μ) + ε_t,     ε ~ N(0, Σ)
```

Médias anuais: Selic 12%, IPCA 5% (meta BCB), valorização 6% (FIPE-ZAP imóvel),
convertidas para mensal geometricamente.

Matriz de persistência e efeitos cruzados:

```
        Selic   IPCA   Valorização
Selic  [ 0,92   0,00    0,00 ]      ← exógena (política monetária)
IPCA   [ 0,08   0,85    0,00 ]      ← responde à Selic defasada (+8%)
Valor. [−0,10   0,15    0,72 ]      ← cai com Selic (−10%), sobe com IPCA (+15%)
```

A covariância dos resíduos codifica os sinais: Selic ↑ acompanha IPCA (+), e
Selic ↑ derruba a valorização (−). As três variâncias foram calibradas contra
as séries reais do BCB (2016–2026): Selic pela SGS 4390, IPCA pela SGS 433 e
valorização pelo IVG-R (SGS 21340). O teto é 5% a.m. (~80% a.a.); o piso é 0
para a Selic e livre para IPCA e valorização.

Cada trajetória gerada é usada para calcular o VPL de **cada estratégia**,
produzindo distribuições completas — e não um número.

**Motor genérico** (`simulators/monte_carlo.py`): 2.000 iterações padrão,
distribuições normal/uniforme/log-normal, percentis P10/P25/P75/P90/P95, seed
para reprodutibilidade — em **stdlib pura, sem numpy** (decisão de deploy
enxuto). O módulo de consórcio e o macro usam numpy por serem vetorizados.

### 7. Dominância Estocástica de Segunda Ordem (SSD) — o desempate honesto

Comparar VPL mediano esconde o pior caso. O Architect calcula a **matriz SSD**
par a par (`_compute_ssd_matrix`):

> A domina B em SSD quando `∫F_B(t)dt ≥ ∫F_A(t)dt` para todo x.

Implementação: grade comum de **500 pontos** entre o mínimo e o máximo dos dois
arrays de VPL; a integral acumulada de `(F_B − F_A)` precisa ser ≥ 0 em todos
os pontos (tolerância `1e-4`).

Quando existe um dominador único, o produto pode afirmar algo muito mais forte
do que "tem VPL maior":

> "*X* domina *Y* e *Z* em dominância estocástica de segunda ordem — preferível
> para **qualquer** agente avesso a risco, independente do grau de aversão."

Isso captura a forma completa da distribuição, não apenas o ponto central. Se
nenhuma estratégia domina, o resultado é declarado **inconclusivo** em vez de
forçar um vencedor.

Complementarmente, `prob_best` reporta `P(esta estratégia tem o maior VPL)`,
somando 1,0 entre as estratégias.

### 8. Ranking e ajuste do custo de oportunidade

`StrategyEngine.simulate()` compara até 5 estratégias por VPL:
`FINANCING`, `CONSORTIUM`, `SAVE_INVEST`, `FINANCING_RENTAL`,
`CONSORTIUM_SELIC_RENTAL`.

Ajuste importante e explícito no código: quem escolhe "juntar dinheiro" para
comprar um imóvel **continua pagando aluguel** nesse meio-tempo. Então

```
npv_save_invest_comparável = npv_save_invest − PV(aluguel_pago_no_período)
```

Sem esse termo, "investir e comprar depois" venceria artificialmente toda
comparação imobiliária.

O engine também calcula o **break-even CET**: a partir de que taxa de
financiamento a decisão vira ("financiar só compensa se você conseguir CET
abaixo de X%").

### 9. Análise de sensibilidade (`simulators/sensitivity_analyzer.py`)

Varre 4 variáveis, recalculando o VPL vencedor em cada ponto:

| Variável | Faixa (delta) | Passos | Unidade |
|---|---|---|---|
| Taxa de juros (CET) | −2 p.p. a +2 p.p. | 9 | p.p. |
| Prazo | −6 a +6 meses | 7 | meses |
| Entrada | −10% a +10% | 9 | R$ |
| CDI | −2 p.p. a +2 p.p. | 9 | p.p. |

Para cada variável calcula `npv_range` (amplitude do VPL vencedor ao longo da
curva) e `elasticity` (variação do VPL por unidade de delta), e ordena por
impacto — o `most_sensitive_variable` é o gráfico de tornado do usuário:
"sua decisão depende principalmente da taxa de juros que você conseguir".

### 10. Taxas vivas e fallback

Conectores em `app/architect/connectors/`: `bacen.py` (SELIC/SGS),
`bacen_credit.py`, `anbima.py`, `ipca.py`, `inpc.py`, `abac.py` (consórcio),
`real_estate.py`, `olinda_interest_rate.py`, `market_rates.py`,
`consortium_rate_provider.py`. Todos seguem o padrão multi-layer fallback:
API viva → tabela fixa versionada em `data/architect/`.

---

## Como funciona (técnico)

- **Endpoints**: `POST /architect/simulate`,
  `GET /architect/simulations[/{id}/sensitivity]`.
- Entrada mínima: tipo de ativo, valor alvo, entrada, prazo, renda mensal,
  poupança atual.
- ~17 mil linhas no módulo (`app/architect/`) — maior módulo do backend;
  validators próprios (`risk_scorer`), pipelines, `services/calibration_pipeline.py`,
  cache em `utils/cache.py`, LLM opcional para narrativa
  (`services/llm_reasoner.py`, import dinâmico).
- `StrategyEngine` é **matemática pura**: não faz chamadas de rede nem de banco
  — recebe o request do usuário + as taxas de mercado já resolvidas. Isso
  torna o motor testável de forma determinística.
- Simulações persistidas em `architect_simulations`; feedback via
  `feedback_queries.py`.

## O que NÃO faz

- **Não executa nada** — não contrata financiamento nem consórcio.
- **Não considera o imóvel/carro como investimento no VPL padrão** — a
  valorização entra nas trajetórias macro, mas a comparação base é
  conservadora por decisão declarada.
- **Não modela crédito com garantia** (home equity) nem FGTS como entrada —
  no roadmap.

## Gaps e limitações

- **Os parâmetros macro são constantes hardcoded** (Selic 12%, IPCA 5%,
  valorização 6%, matriz VAR calibrada em 2015–2025). Não há recalibração
  automática do VAR com dados novos — mudança de regime macroeconômico exige
  editar o módulo. `_A` e `_SIGMA_E` foram calibradas em 2026-08 por MQO nas
  séries reais (fev/2016–jun/2026, 125 meses); as médias (12%/5%/6%) continuam
  sendo premissa. Persistências estimadas: Selic 0,9166 (o chute de 0,92 se
  confirmou), IPCA 0,4199 (o chute era 0,85 — o modelo guardava choque de
  inflação o dobro do tempo). O efeito da Selic sobre o IPCA seguinte é
  **negativo** (−0,29), não positivo: política apertada derruba inflação
  futura. As correlações contemporâneas dos choques, que o código supunha
  fortes, são praticamente nulas nos resíduos (0,02, 0,12, 0,07) — o sinal
  econômico está em `_A`, não em `_SIGMA_E`.
- **A linha da valorização em `_A` NÃO é calibrada, e não dá para calibrar com
  o IVG-R.** O MQO estima 1,0148 para a própria defasagem (t = 135): raiz
  unitária, que faria o processo deixar de reverter à média. Não é economia — é
  alisamento. O índice é apurado por filtro de estado: os incrementos mensais do
  fim da série são 6,64 / 6,64 / 6,65 / 6,65 e ρ₁ das variações mensais é 0,999.
  Não há informação mensal ali. Não existe índice residencial brasileiro mensal,
  público e não alisado com API estável (o FipeZAP não expõe uma), então a
  persistência mensal fica em 0,72 por escolha de modelo — valor que garante
  reversão — e a **dispersão é calibrada no horizonte anual**, o mais curto em
  que o IVG-R ainda mede algo. Teste trava o raio espectral em < 0,95.
- **A dispersão da valorização é calibrada no ANUAL (8,36 p.p.), não no mensal.**
  Calibrar σ mensal contra um índice de avaliação importa a suavização: o modelo
  saía com 4,11 p.p. de desvio anual contra os 8,36 observados em 25 anos —
  subestimando o risco de valorização pela metade. Índices de avaliação
  subestimarem volatilidade de curto prazo é conhecido na literatura de imóveis.
  O modelo produz 23% de anos com desvalorização contra 8% observados: a série
  real é assimétrica à direita e o VAR é gaussiano — limitação conhecida.
- **A média de 6% a.a. da valorização segue sendo premissa.** Medido: o IVG-R
  rendeu 8,65% a.a. nominais em 25 anos contra IPCA de 6,10%, ou seja **+2,41%
  reais**. A janela 2016–2026 isolada dá 3,52% nominais (−1,5% reais) — é uma
  década ruim específica, não uma expectativa. Os 6% nominais com IPCA de 5%
  equivalem a ~1% real.
- Variâncias, contra as séries reais do mesmo período (σ mensal, p.p.):

  | variável | modelo antigo | série real | fonte |
  |---|---|---|---|
  | Selic | 0,99 | 0,3298 | SGS 4390 |
  | IPCA | 0,5467 | 0,3830 | SGS 433 |
  | valorização | 0,7041 | 0,5079 | IVG-R, SGS 21340 |

  A Selic inflada jogava 16% dos sorteios abaixo de zero; o IPCA inflado dava
  22,8% de meses em deflação contra 9,4% observados. A calibração é numérica
  (iteração de Σ' = D·Σ·D até convergir), não em forma fechada — refazer se
  `_A` mudar.
- **A média de valorização (6% a.a.) é premissa de produto, não medição.** O
  IVG-R rendeu 3,52% a.a. nominais no mesmo período. Como toda comparação
  "comprar vs. investir" depende dessa premissa, ela merece decisão explícita
  — não foi alterada aqui.
- **O clamp é aplicado na SAÍDA, não dentro da recursão.** Truncar o estado
  realimentava o passo seguinte e o viés compunha: a Selic revertia para 15%
  em vez de 12% e o IPCA para 8,2% em vez de 5%. Selic mantém piso zero (taxa
  nominal de política); IPCA e valorização aceitam valores negativos, porque
  deflação e desvalorização existem.
- **Seguros usam taxas representativas**, não a tabela do segurador
  contratado — o próprio código diz que produção deveria usar a tabela real.
- **O motor e a curva de sensibilidade compartilham UMA base de custo**
  (`app/architect/simulators/cost_basis.py`) desde 2026-08. Antes cada um
  montava o fluxo por conta própria e divergiam: financiamento sem
  `asset_type` (zera o seguro obrigatório) e sem o IOF de entrada
  (R$ 2.376 num veículo de R$ 64 mil); consórcio sem seis parâmetros de
  grupo, entre eles o reajuste da carta (R$ 8.568, 4,6% do VPL, e
  contemplação 31 meses diferente). A única divergência que permanece é
  `num_simulations`, explícita e parametrizada. A paridade é testada contra o
  `StrategyEngine` de verdade — uma réplica escrita no teste foi justamente o
  que deixou o IOF passar na primeira correção.
- **Um default por taxa** (`app/architect/rate_defaults.py`). Cada consumidor
  tinha o seu embutido no `.get(chave, literal)`: `best_cet_annual` aparecia
  como 0,15, 0,1950 e 0,20, `consortium_admin_rate` como 0,17 e 0,18 — a mesma
  queda de conector produzia números diferentes conforme o caminho do código.
  Leitura passa por `rate()`, que registra em log quando cai no default, e as
  rotas respondem `rates_from_fallback: true` em vez de deixar dado de
  referência visualmente idêntico a dado de hoje.
- **O lance do usuário afeta a contemplação** desde 2026-08. `bid_strategy`
  caía no default `"fixed"`, que DESCARTAVA o `bid_amount` e usava 25% fixos
  da carta; como nenhum caller passava a estratégia, todo usuário era simulado
  com o mesmo lance — com R$ 0 ou R$ 120 mil de entrada — enquanto o fluxo de
  caixa abatia a entrada real. Agora o embutido e o lance próprio se somam
  (limitados à carta), e a entrada move a mediana de 116 para 15 meses no
  intervalo testado.
- **O ritmo de contemplação é repartido entre sorteio e lance** (`sorteio_share`,
  centrado em 50/50 — a mesma proporção que o modelo sempre teve implicitamente,
  quando `contemplated_per_month=2` dava 1 vaga de cada). Sem repartir, as vagas
  de lance eram `contemplacoes_do_mes − 1`, sempre zero abaixo de 2 contemplações
  por mês — que é o caso de TODO consórcio de imóvel.
- **A incerteza dos dois parâmetros não medidos é PROPAGADA para o intervalo.**
  Nem a divisão sorteio/lance nem a fração de lance embutido são publicadas pela
  ABAC, e o dataset do BACEN que traria isso (`PANORAMA_DE_CONSORCIOS`, no
  Olinda) responde HTTP 500 nos endpoints de dado. Em vez de reportar precisão
  inexistente, sorteia-se um par por bloco de simulações dentro das faixas
  declaradas (embutido 10–30%, a faixa que a própria ABAC cita; sorteio
  35–65%), de modo que o P10–P90 inclua o desconhecimento sobre o grupo e não
  só o azar do cotista. Num lance de 40% da carta o intervalo vai de 24 para 50
  meses de largura. Passar `sorteio_share` explícito desliga a propagação — é o
  que a curva de sensibilidade faz, porque ali o objetivo é isolar uma variável.
- **O alvo de quem poupa ANDA.** `_simulate_investment` mirava
  `target_amount` — o preço de hoje, congelado — enquanto o aluguel pago durante
  a espera era corrigido pelo IPCA mês a mês, oito linhas acima no mesmo método.
  O modelo encarecia a espera de um lado e a congelava do outro, sempre a favor
  de SAVE_INVEST, que é a estratégia concorrente do financiamento. Num imóvel de
  R$ 300 mil com 240 meses o aporte pedido era **R$ 0,00** — a entrada rendendo
  sozinha ultrapassava o alvo parado. Agora o alvo cresce pela valorização
  (imóvel) ou pelo IPCA (demais bens: não há índice específico no projeto, e
  congelar afirma que o preço não muda). Quando o bem sobe mais rápido do que o
  dinheiro rende, a resposta é `target_unreachable` em vez de um prazo de 120
  meses inventado. A busca do prazo é por bisseção: a versão iterativa roda até
  1200 meses em Python e, com o alvo móvel, multiplicou por 5 o tempo da suíte.
- **`paths.appreciation` deixou de ser código morto.** A terceira variável do
  VAR era gerada, calibrada, clampada e descartada — `_compute_raw_npvs` lia só
  Selic e IPCA. Agora é ela que move o alvo por trajetória na simulação macro,
  o que também resolve o item anterior de forma estocástica.
- **A contemplação não é mais Monte Carlo.** O número de vagas por assembleia e
  o grupo restante não dependem de nenhum sorteio, então o risco por mês é
  determinístico e o laço estava re-caminhando 2000 vezes o mesmo caminho.
  `_hazard_por_assembleia` calcula o risco uma vez e amostra dele: mesma
  distribuição (Kolmogorov–Smirnov em 7 configurações, p entre 0,13 e 0,97),
  ~600x mais rápido e sem ruído nos percentis.
- **Consórcio: o grupo é sintético** (lance médio inicial 35% com
  decaimento). Administradoras variam muito; o intervalo P10–P90 é honesto,
  mas largo. O ritmo de contemplação NÃO é mais fixo: deriva de
  `group_size / months`, que é a invariante do produto (toda cota é
  contemplada uma vez, espalhada pelo prazo). Com o ritmo fixo de 2/mês
  anterior, um grupo de 150 cotas em 180 meses esvaziava no mês 75 e a
  mediana de contemplação caía de 90 para 37 meses.
- **Lance embutido fixo em 25%** da carta — não é parametrizado pelo produto
  específico do usuário.
- **Monte Carlo em stdlib** (motor genérico) é adequado até ~10k iterações por
  request; acima disso vale vetorizar ou pré-computar.
- **TIR pode ser não-única** em fluxos com múltiplas trocas de sinal — o código
  detecta e sinaliza, mas ainda retorna um valor.
- Componentes do risk score obtidos por proxy são **limitados a 0,50**, o que
  é conservador e correto, mas significa que usuário sem Open Finance completo
  raramente é classificado AGRESSIVO.
- A narrativa LLM é opcional e best-effort — sem chave de API, o relatório
  sai numérico (completo, porém menos didático).
