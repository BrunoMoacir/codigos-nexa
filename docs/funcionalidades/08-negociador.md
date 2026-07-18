# 08 — Negociador (F13)

> Detecta o que dá para negociar com o banco (juros, anuidade) e entrega o
> roteiro pronto da ligação — com números de mercado como argumento.

## Em palavras simples

Negociar com banco funciona muito mais do que as pessoas imaginam — mas
ninguém sabe o que falar. A Nexa detecta seus pontos negociáveis ("você pagou
R$ 240 de juros rotativos em 3 meses; a taxa média de mercado é X%") e gera um
roteiro personalizado: o que pedir, que número citar, o que responder se o
atendente disser não.

## O que faz

- **Detecção de oportunidades** (`negotiator/opportunity_detector.py`), 3
  gatilhos:
  - `JUROS_ROTATIVO_ALTO` — pagou juros de rotativo nos últimos 3 meses
    (benchmark vivo: SELIC via BacenConnector + séries SGS de crédito);
  - `ANUIDADE_ALTA` — anuidade > R$ 30/mês nos últimos 12 meses;
  - `HEALTH_SCORE_ALTO` — score ≥ 70 sem dívidas = poder de barganha para
    renegociação proativa (limite, taxas).
- **Roteiros por IA** (`negotiator/script_generator.py`): script
  personalizado por oportunidade (LLM com fallback de template), com dados do
  usuário e benchmark BACEN como argumento.
- **Histórico com follow-up** (`negotiation_history`): cada roteiro gerado é
  registrado; o usuário reporta o resultado (`PATCH /negotiator/history/{id}`
  — sucesso/parcial/recusado) e o ganho real vira métrica ("você já recuperou
  R$ X negociando").

## Como funciona (técnico)

- **Endpoints**: `POST /negotiator/generate-script`,
  `GET /negotiator/history/{user_id}`, `PATCH /negotiator/history/{id}`.
- Cruza FeeDetector (F5) + BACEN + health score. Confiança calculada por
  volume de dados e score.
- Tool no agente: `get_negotiation_script`. O total de ganho potencial
  alimenta o Placar de Economia (V1) e o contexto do T3.
- Gating: 0 no Free, 1 roteiro/mês no Pro, ilimitado no Total.

## O que NÃO faz

- **Não liga para o banco** — a execução é do usuário (F9, negociação
  assistida/automatizada, é visão de futuro com barreiras regulatórias).
- **Não promete resultado** — linguagem calibrada: "argumentos com base em
  dados", nunca "você vai conseguir".

## Gaps e limitações

- Anuidade usa média de mercado simplificada (`_ANUIDADE_MARKET_MONTHLY_AVG =
  30.0` hardcoded) — o cruzamento com a base de 81 cartões (que tem anuidades
  reais) é melhoria natural.
- Sem LLM configurado, o roteiro sai de template (funcional, menos
  personalizado).
