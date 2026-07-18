# 04 — Nexa Architect: Simulações de Grandes Decisões (F3)

> Para decisões de dezenas de milhares de reais — carro, imóvel — compara
> financiamento, consórcio e "investir e comprar à vista" com matemática de
> verdade: VPL, Monte Carlo e análise de sensibilidade.

## Em palavras simples

"Financio, faço consórcio ou junto dinheiro?" é a pergunta de maior valor
unitário da vida financeira, e ninguém responde com isenção (o banco quer
vender financiamento, a administradora quer vender consórcio). O Architect
simula os três caminhos com os SEUS números e devolve um ranking com intervalo
de confiança — "no cenário mediano, investir e comprar em 28 meses sai R$ 14
mil mais barato que financiar; em 95% das simulações, entre R$ 8k e R$ 19k".

## O que faz

- **3 estratégias comparadas** por Valor Presente Líquido (`calculators/`):
  `financing.py` (Price/SAC, CET), `consortium.py` (com modelagem
  probabilística de contemplação), `investment.py` (acumular rendendo CDI).
- **Monte Carlo próprio** (`simulators/monte_carlo.py`): motor genérico em
  stdlib (sem numpy — decisão de deploy enxuto), distribuições normal/
  uniforme/log-normal, percentis P10–P95, seed para reprodutibilidade.
- **Análise de sensibilidade** (`sensitivity_analyzer.py`): como o resultado
  muda se juros/inflação variarem.
- **Cenários macro** (`macro_scenario.py`) com taxas reais: conectores BACEN
  (SELIC/SGS), ANBIMA, spreads por banco (`data/architect/`).
- **Alavancagem** (`leverage_optimizer.py`): usar crédito barato para não
  descapitalizar investimento que rende mais.
- **Plano de ação** (`action_plan_builder.py`): passos concretos da estratégia
  vencedora.
- **Histórico e feedback**: simulações persistidas
  (`architect_simulations`), endpoint de sensibilidade por simulação,
  calibração via `services/calibration_pipeline.py`.

## Como funciona (técnico)

- **Endpoints**: `POST /architect/simulate`,
  `GET /architect/simulations[/{id}/sensitivity]`.
- Entrada mínima: tipo de ativo, valor alvo, entrada, prazo, renda mensal,
  poupança atual. O motor puxa taxas vivas dos conectores (com fallback fixo
  se API do BACEN cair — padrão multi-layer fallback).
- ~17 mil linhas no módulo (`app/architect/`) — maior módulo do backend;
  validators próprios, pipelines, LLM opcional para narrativa
  (`services/llm_reasoner.py`, import dinâmico).

## O que NÃO faz

- **Não executa nada** — não contrata financiamento nem consórcio.
- **Não considera o imóvel/carro como investimento** (valorização do ativo
  não entra no VPL — decisão conservadora declarada).
- **Não modela crédito com garantia** (home equity) nem FGTS como entrada —
  no roadmap.

## Gaps e limitações

- Contemplação de consórcio é modelada por distribuição histórica
  (`data/architect/consortium_history.csv`) — administradoras variam muito;
  o intervalo é honesto mas largo.
- Monte Carlo em stdlib é adequado até ~10k iterações por request; acima
  disso, vale vetorizar (numpy) ou pré-computar.
- A narrativa LLM é opcional e best-effort — sem chave de API, o relatório
  sai numérico (completo, porém menos didático).
