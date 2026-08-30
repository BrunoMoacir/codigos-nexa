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

## As 3 personas (desenhadas para acender inteligências diferentes)

| Persona | Perfil | Plano | O que ela exercita |
|---|---|---|---|
| **Ana Souza** | CLT, delivery pesado | Total | Renda estável detectada, safe-to-spend alto, assinatura que subiu de preço, poupança sub-CDI, dinheiro parado, calendário fiscal (IR) |
| **Bruno Lima** | MEI | Pro | Classificador PF/PJ, renda via maquininha, DAS/fiscal MEI, mistura de gastos pessoais e do negócio |
| **Carla Mendes** | Renda caindo | Free | **FSS crítico → cluster ESTRESSE_FINANCEIRO**, juros abusivos (rotativo/cheque especial crescentes), margem apertada, tarifa recorrente |

## O teste automatizado

`tests/demo/test_hive_app.py` dirige o app pelo harness oficial do Streamlit
(`streamlit.testing.v1.AppTest`) — sem browser. Em três camadas:

1. **Catálogo** (sem banco, sem rede): a interface e `AGENT_TOOLS` dizem a mesma
   coisa; todo card aponta para um doc que existe; nenhum parâmetro tem padrão
   fora da própria faixa.
2. **Render** (precisa das personas semeadas): as 4 superfícies das 3 personas
   sobem sem exceção e sem erro na tela, com números de verdade, e o gating de
   plano muda o que aparece.
3. **Execução**: clicar em "Executar" roda a ferramenta real; a linha `[NEXA]`
   fica fora do corpo e vira selo. Com chave de LLM, uma volta completa do
   agente — inclusive o teste de `user_id` forjado.

```bash
python3 -m pytest tests/demo/ -v
```

`demo/features.py` ainda verifica **na importação** que o catálogo da interface
e o registro `AGENT_TOOLS` estão sincronizados: ferramenta nova sem lugar na
tela, ou card apontando para tool removida, e o app não sobe — com a lista do
que divergiu.

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
