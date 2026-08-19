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
Selic ↑ derruba a valorização (−). Taxas são clampeadas em `[0, 5% a.m.]`
(~80% a.a.).

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
  editar o módulo. A variância do choque da Selic foi recalibrada em 2026-08
  contra a série SGS 4390 (127 meses): o valor anterior implicava desvio
  estacionário de 0,99 p.p./mês contra 0,33 observado, o que jogava 16% dos
  sorteios abaixo de zero.
- **O clamp é aplicado na SAÍDA, não dentro da recursão.** Truncar o estado
  realimentava o passo seguinte e o viés compunha: a Selic revertia para 15%
  em vez de 12% e o IPCA para 8,2% em vez de 5%. Selic mantém piso zero (taxa
  nominal de política); IPCA e valorização aceitam valores negativos, porque
  deflação e desvalorização existem.
- **Seguros usam taxas representativas**, não a tabela do segurador
  contratado — o próprio código diz que produção deveria usar a tabela real.
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
