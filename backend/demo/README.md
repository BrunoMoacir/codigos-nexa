# Demo HIVE — o produto inteiro, rodando

Dois apps Streamlit sobre os **serviços reais** do backend, alimentados por
personas cujos dados passaram pelo ETL de verdade — Pluggy-style → validação →
ingestor → classificador → PF/PJ → banco. Nada é mockado na camada de
inteligência.

| App | O que é |
|---|---|
| **`hive_app.py`** | O produto como o usuário o encontra: as 4 superfícies do frontend real (Panorama, Oportunidades, Organizar, Chat IA), com as **31 ferramentas** do agente, o gating de plano e a linha de procedência de cada resultado. É o teste manual do sistema inteiro. |
| `streamlit_app.py` | O harness anterior, focado no caminho ETL → feed → chat e nos loops de aprendizado (5 abas). Continua válido para inspecionar o footprint de banco. |

## Como rodar

```bash
cd backend

# 1. Pré-requisitos: Postgres do dev no ar e migrações aplicadas
python3 -m alembic upgrade head

# 2. Popular as 3 personas: ETL real + footprint COMPLETO de produção
python3 -m demo.seed              # base + enriquecimento (um comando)
# python3 -m demo.seed --base-only  # só transações, sem o footprint

# 3. Subir a interface
streamlit run demo/hive_app.py    # → http://localhost:8501
```

O **Chat** precisa de uma chave de LLM. `demo/ambiente.py` a procura em
`backend/.env` **e no `.env` da raiz** — o `app/core/config.py` só lê o
primeiro, e neste repositório o arquivo de desenvolvimento está na raiz. Sem
chave, as outras três superfícies funcionam inteiras e o Chat explica o que
falta (é o mesmo comportamento de produção: 503 com mensagem clara, nunca uma
resposta fabricada).

## O que o `hive_app.py` mostra

- **Panorama** — margem segura do dia, projeção de caixa event-driven de 30
  dias, renda detectada (não soma de créditos), health score, cluster
  comportamental com FSS, e os **8 estágios do ETL com os números desta conta**,
  incluindo o laudo de qualidade real (cobertura, completude, consistência).
- **Oportunidades** — o feed do `ProactiveNotifier` passado pelo
  `NotificationRelevanceFilter`, que é quem decide o que merece interromper o
  usuário. Abaixo, os detectores que o alimentam: alertas de gasto, calendário
  fiscal, radar de oportunidades, direitos esquecidos, promoções, revisão
  retroativa de compras e os detectores D1–D3 da Defesa do Consumidor.
- **Organizar** — KPIs de receita/gasto/saldo/poupança, gasto por mês, gasto por
  categoria, separação PF × PJ, burn rate, compromissos futuros (shadow
  invoices), lançamentos, e as 22 análises em 9 seções: perfil, dinheiro,
  planejamento, cartões, decisões grandes, bancos, defesa, fiscal e conta
  (planos, limites de uso e o inventário LGPD das 23 tabelas).
- **Chat IA** — o agente LangGraph real com as 31 ferramentas, o traço de quais
  ele decidiu chamar em cada resposta, a cota de 5 mensagens/dia do plano Free e
  o apagamento que limpa as linhas **e** os threads do checkpointer.

### Três coisas que a interface torna visíveis

**A procedência vira selo.** Cada ferramenta emite
`[NEXA] confianca=… | cobertura=… | fontes=… | degradado=…`. Em produção o
agente nunca repete essa linha — é informação de sistema. Aqui ela sai do corpo
do texto e vira o selo do card, que é a mesma decisão com a interface no lugar
do modelo: dá para ver de relance qual número é medição e qual saiu de um
caminho de fallback. `R$ 0,00 em tarifas` com `degradado=` não é "seu banco não
cobra tarifas".

**O gating aparece em vez de esconder.** O bloqueio de plano nasce desligado
(dark launch, doc 16): o produto registra o que TERIA bloqueado para medir o
impacto antes de cobrar. A tela faz igual — a ferramenta de plano superior
aparece com cadeado e o motivo, não some. Carla (Free) vê menos controles que
Bruno (Pro), que vê menos que Ana (Total).

**A identidade é a de produção.** Toda ferramenta roda dentro de
`usuario_da_requisicao` + `vincular_ao_usuario` — a camada determinística da
mitigação de prompt injection, a que sobrescreve o `user_id` que o modelo
passou pelo do usuário autenticado. No Chat, um `[user_id=…]` digitado na
mensagem é neutralizado antes de chegar ao LLM, e a interface avisa.

## As 3 personas (um ano de extrato cada)

| Persona | Perfil detectado | Plano | Extrato | Comprometido | O que ela acende |
|---|---|---|---|---|---|
| **Ana Souza** | `DIGITAL_NATIVO` (2º: `URBANO_FOODIE`) · FSS 23 ATENÇÃO | Total | ~500 tx / 12 meses | 90% da renda | Delivery quase diário, **seguro prestamista amarrado ao cartão (D1)**, R$ 52 mil parados na conta (Radar), 2 parcelamentos em curso, assinatura que subiu de preço, 13º e restituição de IR |
| **Bruno Lima (MEI)** | `MICROEMPREENDEDOR` · FSS 21 ATENÇÃO | Pro | ~550 tx / 12 meses | 87% da renda | Maquininha com meses cheios e fracos, mistura PF/PJ, DAS, **tarifas de conta PJ (Raio-X + D2)**, ferramentas B2B que acendem o detector de MEI |
| **Carla Mendes** | `ESTRESSE_FINANCEIRO` · FSS 65 **CRÍTICO** · resiliência 19 | Free | ~320 tx / 12 meses | **112% da renda** | Renda caindo 12 meses seguidos, rotativo e cheque especial **crescendo**, título de capitalização debitado sem pedir (D1), margem R$ 0/dia |

### Por que os números são esses

O volume e o comprometimento foram **calibrados medindo**, não escolhidos:

- **Densidade (26–45 lançamentos/mês).** Com os ~17/mês de antes, o
  `DataQualityValidator` via lacunas em metade dos dias (cobertura temporal
  0,55) e o `SpendingAnomalyDetector` não alcançava os "≥ 5 lançamentos por
  categoria" que ele exige antes de comparar com média e desvio. Hoje a
  qualidade sai `EXCELLENT` para as três.
- **Comprometimento.** Empilhar gasto sem renda correspondente levou Bruno a
  108% com saldo negativo e margem R$ 0, e zerou a taxa de poupança da Ana —
  o que trocou o cluster das duas. Renda e balanço precisam contar a mesma
  história: R$ 52 mil parados na conta e 93% da renda comprometida são a mesma
  pessoa em duas versões diferentes.
- **A Carla é a única a 112%**, e de propósito: é o que sustenta FSS CRÍTICO,
  resiliência 19 e health score 0. O gasto dela **cresce** ao longo do ano
  (fator 4 do `resilience_score` zera 20 pontos quando a despesa sobe), que é
  como a espiral acontece de fato — a renda cai, o crédito cobre a diferença,
  e o custo do crédito faz o gasto subir sozinho no mês seguinte.

### Dado sujo de propósito

O extrato real não chega limpo, e o pipeline tem de absorver isso sem
contaminar análise. Cada persona recebe:

- uma **duplicata exata** (mesma conta, data, valor e descrição) — o
  `dedup_hash` a colapsa, e é por isso que o seed reporta `válidas=504 →
  persistidas=503`;
- o **mesmo comerciante escrito de três jeitos** (`PG *NETFLX 4471`,
  `NETFLIX.COM 8891`, `NETFLIX COM BR *ASSIN`) — a normalização de merchant
  precisa reduzir os três ao mesmo;
- um **lançamento retroativo** fora de ordem cronológica, como quando o
  agregador reprocessa um mês antigo.

## As 5 superfícies do `streamlit_app.py` (harness anterior)

- **📊 Dashboard** — `demo.services.dashboard_data`: roda `run_from_db` (o
  pipeline real), o `UserProfileAnalyzer` (health score), o `LifestyleClassifier`
  (cluster ML híbrido) e o `FSSCalculator`. Mostra margem segura, renda
  detectada, projeção de caixa 30 dias, gastos por categoria e separação PF/PJ.
- **🔔 Feed** — `demo.services.build_feed`: usa o **`ProactiveNotifier` e o
  `NotificationRelevanceFilter` reais**, exatamente como o produto, porém a
  partir dos dados da persona (via `run_from_db`) em vez do Pluggy mock que o
  router HTTP usa. Os cards (burn rate, fiscal, poupança sub-CDI, promoções…)
  são gerados e filtrados pela mesma lógica de produção.
- **💬 Chat** — o **agente LangGraph real** (`build_financial_agent`, 31
  ferramentas) com o `[user_id=...]` da persona. Cada pergunta chama as
  ferramentas reais sobre os dados semeados.
- **🗄️ Meus Dados** — o **footprint completo** que a Nexa armazena: múltiplas
  contas e saldos, evolução do health score (6 meses), tarifas pagas,
  negociações com desfecho, desafios/badges, correções PF/PJ e histórico de
  chat. É como o banco de dados de uma conta usada há meses.
- **🧬 Aprendizado** — a **meta-inteligência**: os loops fechados que
  computam a partir dos dados reais — calibração do Negociador (fator de
  realização por gatilho), peso das recomendações por taxa de aceitação, e a
  série temporal de `intelligence_metrics`. Vazios sem dados; **vivos** com o
  footprint semeado.

## O que o footprint completo popula (tabelas de produção)

`demo/seed_full.py` preenche tudo que um usuário real acumula:
`account_balances` (várias contas), `health_score_history`, `bank_fee_history`,
`negotiation_history` (com desfecho), `recommendation_feedback`,
`chat_messages`, `user_challenges` + `user_badges`, `context_overrides`.
Isso faz os **loops de aprendizado saírem do zero**: com desfechos de
negociação reais, a calibração computa um fator (ex.: JUROS_ROTATIVO → 0,53);
com aceites/rejeições, os pesos de recomendação se ajustam.

## O que este harness comprova

O caminho completo funciona ponta a ponta com dados realistas:

```
raw (Pluggy-style) → from_raw_batch → ingestor.process → classifier.predict
   → pf_pj_classifier → transactions_clean (Postgres)
       → run_from_db → forecast / safe-to-spend / health score
       → ProactiveNotifier + relevance filter → feed
       → LangGraph agent (31 tools) → chat
```

## Notas honestas (coisas que o teste revelou)

- A tabela de tarifas de mercado e o catálogo de investimentos são **vivos**
  (Open Finance); rodar o demo offline usa o fallback curado.
- Personas com pouco histórico ou sinais fracos podem cair em
  `NAO_CLASSIFICADO` — é o classificador real recusando forçar um rótulo.
- Alguns detectores dependem de tabelas de runtime (`user_challenges`,
  `opportunity_snapshots`); sem elas, degradam com log e o feed segue.
- O `run_from_db` retorna **todos** os meses; o mês corrente é semeado só até
  hoje (sem datas futuras), para o burn rate refletir consumo parcial real.
