# Demo Nexa — Teste Ponta a Ponta (Streamlit)

Um app Streamlit que simula o produto **em produção**: três superfícies reais
(Dashboard, Feed e Chat) alimentadas por dados de personas que **passaram pelo
ETL de verdade** — Pluggy-style → validação → ingestor → classificador →
PF/PJ → banco. Nada é mockado na camada de inteligência.

## Como rodar

```bash
cd backend

# 1. Pré-requisitos: Postgres do dev no ar e migrações aplicadas
#    (o mesmo banco que os testes usam)
python3 -m alembic upgrade head

# 2. Popular as 3 personas passando pelo ETL real
python3 -m demo.seed

# 3. Subir a interface
streamlit run demo/streamlit_app.py
#    → abre em http://localhost:8501
```

Para o **Chat** funcionar, configure uma chave de LLM no `backend/.env`
(`ANTHROPIC_API_KEY=...` com `LLM_PROVIDER=anthropic`). Sem chave, o Dashboard
e o Feed funcionam normalmente e o Chat mostra as perguntas de exemplo.

## As 3 personas (desenhadas para acender inteligências diferentes)

| Persona | Perfil | Plano | O que ela exercita |
|---|---|---|---|
| **Ana Souza** | CLT, delivery pesado | Total | Renda estável detectada, safe-to-spend alto, assinatura que subiu de preço, poupança sub-CDI, dinheiro parado, calendário fiscal (IR) |
| **Bruno Lima** | MEI | Pro | Classificador PF/PJ, renda via maquininha, DAS/fiscal MEI, mistura de gastos pessoais e do negócio |
| **Carla Mendes** | Renda caindo | Free | **FSS crítico → cluster ESTRESSE_FINANCEIRO**, juros abusivos (rotativo/cheque especial crescentes), margem apertada, tarifa recorrente |

## As 3 superfícies

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
