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

## O que faz

- **OPP.1 Dinheiro parado** (`services/idle_money_detector.py`): saldo médio
  3 meses − N meses de gastos − reserva de emergência; threshold R$ 500 por
  30+ dias. Personalizado pelo FSS (perfil frágil → prioriza liquidez diária).
- **OPP.2 Catálogo vivo do mercado** (`connectors/open_finance_products.py`):
  varre **todos os participantes do diretório Open Finance** (45 endpoints
  hoje) em paralelo, com paginação, filtro pessoa física, canonicalização de
  marca ("ITAU UNIBANCO S A" = "Itaú"), dedup por (banco, tipo, liquidez) e
  **flag `promotional`** para taxas-teaser >130% CDI — validado ao vivo: ~78
  produtos de ~23 instituições em ~13s. Job diário 02h30 persiste em
  `product_catalog.json`; fallback: catálogo curado versionado.
- **Ranking líquido** (`services/bank_comparator.py`): IR regressivo real
  (via `IRPFCalculator`), LCI/LCA isentas comparadas de igual para igual,
  Tesouro SELIC incluído (taxa de custódia B3 considerada). **Teasers
  promocionais são rebaixados** — taxa de vitrine nunca é a recomendação nº 1.
- **OPP.3/OPP.4** comparadores dedicados: Tesouro vs CDB vs poupança;
  poupança abaixo do CDI (regra SELIC+TR real) → card `SAVINGS_BELOW_CDI`.
- **OPP.5 Passos práticos** (`services/switch_steps.py`): onde clicar para
  executar a troca, por produto.
- **Bank Match** (`services/bank_match.py`): "qual banco é melhor para MIM?" —
  pondera rendimento ajustado a risco + tarifas típicas (F5) + força dos
  cartões do emissor (F2) + fit comportamental (FSS), com explicação por
  componente.
- **Scorecard por banco** (`services/bank_scorecard.py`) e catálogo público
  transparente (`GET /opportunities/products` — qualquer um pode auditar).

## Como funciona (técnico)

- **Endpoints**: `GET /opportunities/{user_id}`, `/{user_id}/banks`,
  `/{user_id}/bank-match`, `/products`, `/savings-vs-cdi`,
  `/treasury-vs-cdb-vs-savings`; `POST /opportunities/compare`.
- Job diário `opportunity_scan` (03h00) grava `opportunity_snapshots` e gera
  cards `IDLE_MONEY_DETECTED`/`SAVINGS_BELOW_CDI` (dedup 1×/mês).
- Comparator recarrega o catálogo por mtime/TTL — o job atualiza sem restart.
- Disclaimer regulatório em todas as respostas (não é recomendação CVM).
- Gating: endpoints por usuário exigem plano Pro.

## O que NÃO faz

- **Não executa a aplicação** (F6 sweep automático depende da fase de
  iniciação de pagamento do Open Finance).
- **Não compara fundos, ações ou previdência** — escopo é renda fixa bancária
  (CDB/RDB/LCI/LCA) + Tesouro SELIC.
- **Não recebe comissão** — estruturalmente: nenhum link é afiliado.

## Gaps e limitações

- Cobertura = participantes do Open Finance com renda fixa publicada (~23
  instituições hoje; cresce com a adesão). Corretoras fora do diretório e
  produtos de plataforma exigiriam fontes adicionais (ANBIMA).
- Qualidade dos dados publicados varia por instituição (alguns publicam
  faixas vazias/valores estranhos) — a normalização é defensiva e descarta o
  ininterpretável, com plausibilidade 30–200% CDI.
- Rating de crédito do emissor: produtos do catálogo vivo saem com rating
  "N/A" (o opendata não publica rating; FGC cobre até R$ 250k e isso é dito).
