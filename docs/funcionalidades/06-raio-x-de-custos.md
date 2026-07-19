# 06 — Raio-X de Custos (F5)

> Mostra cada tarifa que o banco cobra de você — e se ela está acima do que o
> mercado cobra.

## Em palavras simples

Tarifa bancária é desenhada para passar despercebida: R$ 24,90 aqui, R$ 12 de
"manutenção" ali. O Raio-X varre o extrato, encontra todas as tarifas, soma o
custo anual ("você paga R$ 487/ano só de tarifas") e compara com um benchmark:
"a média de mercado para esse pacote é R$ 15 — o seu banco cobra R$ 25".
É a matéria-prima da indignação que move a Defesa do Consumidor (doc 10) e o
Negociador (doc 08).

## O que faz

- **Detecção de tarifas** (`costs/fee_detector.py`): identifica lançamentos de
  tarifa por padrão de descrição/valor (manutenção, pacote, TED, saque,
  anuidade, seguros embutidos).
- **Benchmark de mercado VIVO** (`costs/market_fees_db.py` +
  `costs/connectors/open_finance_fees.py`): tarifas e pacotes publicados
  obrigatoriamente por cada participante do Open Finance Dados Abertos
  (`opendata-accounts/personal-accounts`, ~28 instituições), com preço
  **típico ponderado pela fração de clientes por faixa** — não o teto de
  tabela. Job diário 02h15 (`market_fees_refresh`) atualiza
  `data/fees/market_fees_live.json`; matching tolerante de nomes; fallback
  na tabela estática curada.
- **Análise por banco** (`costs/bank_fee_analyzer.py`): consolida por
  instituição e alimenta o histórico.
- **Histórico e baseline coletivo**: job diário `fee_snapshot` (02h00) grava
  `bank_fee_history` (por usuário) e `bank_fee_trends` (baseline de mercado
  **anonimizado** por banco) — é o embrião do "flywheel de dados": quanto mais
  usuários, melhor o benchmark, e é o que alimenta D2/D4 e o futuro ranking
  público de bancos (V3).

## Como funciona (técnico)

- **Endpoint**: `GET /costs/{user_id}` — relatório com cada tarifa, total
  por período, comparação com benchmark e bandeiras de atenção.
- Detecção via Polars sobre `transactions_clean` (regex + heurísticas de
  valor/recorrência).
- Tool no agente: `get_bank_cost_analysis`.

## O que NÃO faz

- **Não classifica legalidade** — dizer se a tarifa é *indevida* é papel dos
  detectores de Defesa (D1/D2); o Raio-X mostra o custo e o desvio do mercado.
- **Não lê o contrato do usuário** — não sabe qual pacote foi contratado; o
  benchmark é por perfil típico, não pelo contrato específico.

## Gaps e limitações

- O baseline vivo cobre os participantes do Open Finance que publicam
  `personal-accounts` (~28 instituições hoje); bancos fora do diretório
  caem na tabela estática curada.
- `bank_fee_trends` (agregado anônimo dos usuários) segue como segunda
  fonte — ganha valor com massa de usuários e captura o que os bancos NÃO
  publicam (tarifas avulsas cobradas na prática).
- O job das 02h00 (`fee_snapshot`) e o das 02h15 (`market_fees_refresh`)
  são complementares: um mede o que os usuários pagam; o outro, o que os
  bancos publicam.
