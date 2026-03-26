# Nexa AI — Backend

Agente financeiro inteligente que usa dados do Open Finance (via Pluggy) para analisar saúde financeira, projetar fluxo de caixa, otimizar uso de cartões, simular decisões de compra de bens e conversar em linguagem natural via IA.

---

## Status das Funcionalidades

| Funcionalidade | Descrição | Status |
|---|---|---|
| **F1 — Core Engine** | ETL, cashflow 30 dias, safe-to-spend, shadow invoices, perfil financeiro | Completo |
| **F2 — Card Optimizer** | Ranqueamento de cartões, estratégia multi-cartão, custo de oportunidade | Completo |
| **F3 — Nexa Architect** | Simulação financeira (financiamento vs consórcio vs investimento), Monte Carlo, VPL | Completo |
| **F4 — Nexa Divider** | Classificação automática PF/PJ via Random Forest + fallback por regras, relatório fiscal MEI/PJ | Completo |
| **Income Profiler** | Estimativa real de renda mensal (filtra transferências, estornos, rendimentos) | Completo |
| **Spending Anomaly Detector** | Detecção de gastos anormais por categoria | Completo |
| **Budget Advisor (M1.3)** | Plano 50/30/20, análise de gastos por categoria, recomendações de ajuste | Completo |
| **Subscriptions (M1.5)** | Detecção automática de assinaturas recorrentes, listagem e resumo | Completo |
| **MX.1 — Health Score History** | Score financeiro com tendência e evolução temporal (IMPROVING/STABLE/DECLINING) | Completo |
| **MX.2 — Goals** | Sistema de metas financeiras com projeção de prazo e progresso | Completo |
| **MX.3 — Notificacoes Proativas** | Notificacoes por burn rate, anomalias, assinaturas, safe-to-spend e metas | Completo |
| **MX.4 — Peer Comparison** | Comparacao de gastos com benchmarks IBGE/POF por faixa de renda | Completo |
| **Agente conversacional (LangGraph + OpenAI)** | Agente ReAct com 8 ferramentas financeiras, endpoint `/chat`, teste Streamlit | Completo |

---

## Pendente / Proximos passos

| Item | Descricao |
|---|---|
| **Memoria de conversa no agente** | O agente nao tem persistencia de mensagens entre sessoes (comentario no `chat.py`: "Em prod, deve-se habilitar memoria entre mensagens!") |
| **Migracao para Claude / Anthropic** | O agente usa `ChatOpenAI (gpt-4o-mini)`. O projeto menciona Claude como opcao futura |
| **Testes do agente** | Apenas 1 teste de ferramenta (`test_get_card_optimization.py`). As outras 7 ferramentas nao tem testes automatizados |
| **Testes MX.1–MX.4** | Health Score History, Goals, Notificacoes e Peer Comparison nao tem cobertura de testes |
| **Autenticacao JWT / API Keys** | Nenhum endpoint tem autenticacao. `core/security.py` existe mas nao esta integrado nas rotas |
| **Rate limiting** | Nenhuma protecao contra abuso de endpoints (especialmente `/chat`) |
| **Producao: PostgreSQL** | O backend usa DuckDB (local). A migracao para PostgreSQL esta descrita mas nao implementada |
| **Redis para cache** | `REDIS_URL` esta no `.env` mas nao e usado. Cache de taxas BACEN/ANBIMA e feito em memoria |
| **Deploy / Docker** | Nao ha `Dockerfile`, `docker-compose.yml` ou configuracao de CI/CD |
| **Frontend** | Nenhum frontend existe no repositorio. So ha o `streamlit_agent_test.py` para testes manuais |
| **Rotas nao registradas** | `analyze.py`, `dashboard.py` e outras estao criadas mas comentadas no `router.py` |
| **Banco de estrategias de banco** | So ha estrategias para Nubank, Itau e Inter. Outros bancos usam `default.py` |

---

## Pre-requisitos

- Python 3.11+
- Conta na [Pluggy](https://pluggy.ai) com `CLIENT_ID` e `CLIENT_SECRET`
- Chave OpenAI (para o agente conversacional)

---

## Instalacao

```bash
cd backend
pip install -r requirements.txt
# ou
poetry install
```

---

## Variaveis de ambiente

Crie o arquivo `backend/.env`:

```env
# Pluggy (Open Finance)
PLUGGY_CLIENT_ID=seu_client_id
PLUGGY_CLIENT_SECRET=seu_client_secret
PLUGGY_BASE_URL=https://api.pluggy.ai

# OpenAI (agente conversacional)
OPENAI_API_KEY=sk-...

# URL do frontend (usada no redirect de reconexao)
FRONTEND_BASE_URL=http://localhost:3000

# Banco de dados (producao)
DATABASE_URL=postgresql://user:pass@localhost:5432/nexa

# Opcionais
REDIS_URL=redis://localhost:6379
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=yyy
AWS_S3_BUCKET=nexa-raw-events
LOG_LEVEL=INFO
APP_MODE=dev
```

---

## Como rodar

```bash
cd backend
uvicorn app.main:app --port 8000 --reload
```

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Health check: `http://localhost:8000/health`

### Teste do agente (Streamlit)

```bash
# Terminal 1
cd backend && uvicorn app.main:app --reload

# Terminal 2
cd backend && streamlit run streamlit_agent_test.py
```

O Streamlit abre uma interface com duas abas:
- **Chat do Agente**: testa as 8 ferramentas via chat (HTTP ou direto)
- **Endpoints Diretos**: chama REST endpoints que nao passam pelo agente

---

## Como rodar os testes

```bash
cd backend
pytest tests/ -v

# Com coverage
pytest tests/ --cov=app --cov-report=html
```

414 testes, 0 falhando.

---

## Endpoints da API

### Sistema

| Metodo | Rota | O que faz |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/version` | Versao da API |
| `GET` | `/docs` | Swagger UI |

### F1 — Saude financeira e previsao

| Metodo | Rota | O que faz |
|---|---|---|
| `GET` | `/api/v1/forecast/{user_id}` | Previsao completa: cashflow 30 dias, safe-to-spend, shadow invoices, perfil financeiro |
| `GET` | `/api/v1/shadow_invoice/{user_id}` | Lista obrigacoes futuras detectadas (assinaturas + parcelas) |
| `GET` | `/api/v1/shadow_invoice/{user_id}/summary` | Resumo de obrigacoes futuras |
| `GET` | `/api/v1/alerts/{user_id}` | Alertas ativos: token expirado, saldo negativo, caixa comprometido |
| `DELETE` | `/api/v1/alerts/{user_id}/{alert_id}` | Dispensar alerta |
| `GET` | `/api/v1/safe_to_spend/{user_id}` | Margem segura de gastos do dia |

### Transacoes

| Metodo | Rota | O que faz |
|---|---|---|
| `POST` | `/api/v1/transactions/webhook` | Recebe transacoes do Pluggy, valida e roda ETL |
| `GET` | `/api/v1/transactions/{user_id}` | Busca transacoes do usuario |

### F2 — Card Optimizer

| Metodo | Rota | O que faz |
|---|---|---|
| `POST` | `/api/v1/optimizer/recommend` | Ranqueia cartoes pelo perfil de gastos do usuario |
| `POST` | `/api/v1/optimizer/simulate` | Simula retorno de um cartao especifico para os gastos do usuario |
| `POST` | `/api/v1/optimizer/multi_card` | Estrategia multi-cartao: carteira otima de ate N cartoes |
| `POST` | `/api/v1/optimizer/opportunity_cost` | Calcula quanto o usuario perdeu usando o cartao atual vs alternativas |

### F3 — Nexa Architect (Simulacao de Compra)

| Metodo | Rota | O que faz |
|---|---|---|
| `POST` | `/api/v1/architect/simulate` | Compara financiamento vs consorcio vs investimento. Ranqueia por VPL. Busca taxas reais BACEN/ANBIMA. |
| `GET` | `/api/v1/architect/simulations` | Lista simulacoes anteriores do usuario |
| `GET` | `/api/v1/architect/simulations/{id}` | Detalhe de uma simulacao |
| `GET` | `/api/v1/architect/simulations/{id}/sensitivity` | Re-analise de sensibilidade com taxas atuais |
| `GET` | `/api/v1/architect/metrics` | Metricas do usuario |

### F4 — Classificacao PF/PJ e Fiscal

| Metodo | Rota | O que faz |
|---|---|---|
| `POST` | `/api/v1/context/override` | Salva correcao manual de classificacao PF/PJ |
| `GET` | `/api/v1/context/overrides/{user_id}` | Lista correcoes manuais do usuario |
| `GET` | `/api/v1/fiscal-report/{user_id}` | Relatorio fiscal PJ/MEI com DAS estimado, faturamento e despesas dedutivas |

### MX.1 — Health Score

| Metodo | Rota | O que faz |
|---|---|---|
| `GET` | `/api/v1/health-score/history/{user_id}` | Historico do score financeiro com tendencia (IMPROVING/STABLE/DECLINING) e variacoes em 30/90 dias |

### MX.2 — Metas Financeiras

| Metodo | Rota | O que faz |
|---|---|---|
| `POST` | `/api/v1/goals/{user_id}` | Criar nova meta financeira |
| `GET` | `/api/v1/goals/{user_id}` | Listar metas do usuario com projecoes |
| `GET` | `/api/v1/goals/{user_id}/{goal_id}` | Detalhe de uma meta com projecao completa |
| `PATCH` | `/api/v1/goals/{user_id}/{goal_id}/progress` | Atualizar progresso de uma meta |
| `DELETE` | `/api/v1/goals/{user_id}/{goal_id}` | Abandonar meta |

### MX.3 — Notificacoes Proativas

| Metodo | Rota | O que faz |
|---|---|---|
| `GET` | `/api/v1/notifications/{user_id}` | Notificacoes proativas ordenadas por prioridade (CRITICAL > WARNING > INFO) |

### MX.4 — Peer Comparison

| Metodo | Rota | O que faz |
|---|---|---|
| `GET` | `/api/v1/peers/compare/{user_id}` | Compara gastos com benchmarks IBGE/POF por faixa de renda. Retorna posicionamento por categoria e percentil de poupanca. |

### Orcamento e Assinaturas

| Metodo | Rota | O que faz |
|---|---|---|
| `GET` | `/api/v1/budget/{user_id}` | Plano 50/30/20 com analise de gastos por categoria (M1.3) |
| `GET` | `/api/v1/subscriptions/{user_id}` | Lista assinaturas recorrentes detectadas (M1.5) |

### Agente Conversacional

| Metodo | Rota | O que faz |
|---|---|---|
| `POST` | `/api/v1/chat/` | Conversa com o agente Nexa. O LLM decide qual ferramenta usar e responde em linguagem natural. |

### Utilitarios e desenvolvimento

| Metodo | Rota | O que faz |
|---|---|---|
| `POST` | `/api/v1/reconnect/{user_id}` | Gera URL de reconexao do consentimento Pluggy |
| `GET` | `/api/v1/banks/simulate/{bank}` | Dados bancarios mock para desenvolvimento |

---

## Exemplos de uso

### Chat com o agente

```bash
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "message": "Como estao minhas financas? Posso comprar um carro de R$ 60.000?"
  }'
```

O agente decide automaticamente quais ferramentas chamar (`get_financial_forecast` + `get_financing_simulation`) e responde em linguagem natural.

### Ferramentas do agente (8 disponíveis)

| Ferramenta | Quando e acionada |
|---|---|
| `get_financial_forecast` | Pergunta sobre situacao financeira geral, safe-to-spend, health score |
| `get_budget_advice` | Pergunta sobre orcamento, regra 50/30/20, usuario menciona renda |
| `get_card_optimization` | Pergunta sobre cartao de credito, pontos, cashback |
| `get_spending_alerts` | Pergunta sobre alertas, gastos estranhos, anomalias |
| `get_goals_summary` | Pergunta sobre metas, reserva de emergencia, progresso de poupanca |
| `get_financing_simulation` | Usuario menciona valor de bem para comprar, comparacao financiamento vs poupanca |
| `get_fiscal_report` | Usuario e MEI/PJ e pergunta sobre impostos, DAS, faturamento |
| `get_peer_comparison` | Pergunta como seus gastos se comparam com outras pessoas da mesma faixa de renda |

### Simulacao de compra de bem (F3)

```bash
curl -X POST http://localhost:8000/api/v1/architect/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "asset_type": "vehicle",
    "target_value": 60000,
    "down_payment": 12000,
    "months": 48,
    "monthly_income": 8000,
    "current_savings": 15000
  }'
```

Retorna as 3 estrategias ranqueadas por custo total (VPL), com analise de sensibilidade e simulacao Monte Carlo.

### Recomendacao de cartao (F2)

```bash
curl -X POST http://localhost:8000/api/v1/optimizer/recommend \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "monthly_income": 8000,
    "transactions": [...]
  }'
```

---

## Arquitetura

```
                        +---------------------------------------+
                        |          USUARIO / FRONTEND            |
                        +------------------+--------------------+
                                           | HTTP
                        +------------------v--------------------+
                        |        FastAPI (app/main.py)           |
                        +---+----------+----------+-------------+
                            |          |          |
             +--------------v--+  +----v------+  +----v-------------------+
             |  ETL Pipeline   |  | Cashflow  |  |  Architect (F3)        |
             |  (5 estagios)   |  | Engine    |  |  Financiamento,        |
             +-------+---------+  +----+------+  |  Consorcio, Monte      |
                     |                |          |  Carlo, VPL/TIR        |
             +-------v---------+  +----v------+  +----+-------------------+
             |  Ingestor       |  | SafeToSpd |       |
             |  Classifier     |  | Projector |  +----v-------------------+
             |  PF/PJ ML       |  +-----------+  |  Card Optimizer (F2)   |
             |  RecurrDet.     |                 |  Ranking, Multi-card   |
             |  ShadowInv.     |                 +------------------------+
             |  IncomePrf.     |
             +-------+---------+
                     |
             +-------v-----------------------------------------+
             |     MX Modules                                   |
             |  MX.1 Health Score  MX.2 Goals  MX.3 Notifier   |
             |  MX.4 Peer Compare  Budget  Subscriptions        |
             +-------------------------------------------------++
                     |
             +-------v-----------------------------------------+
             |     Agent Layer (LangGraph ReAct)               |
             |  8 ferramentas + OpenAI gpt-4o-mini             |
             |  Endpoint: POST /chat/                          |
             +-------------------------------------------------++
                     |
             +-------v-----------------------------------------+
             |              Data Layer                          |
             |  DuckDB (local)  |  PostgreSQL (prod)           |
             |  Polars DataFrames                               |
             +-------+-----------------------------------------+
                     |
             +-------v-----------------------------------------+
             |        External Integrations                     |
             |  Pluggy Open Finance API                         |
             |  BACEN / ANBIMA (taxas de mercado)               |
             +-------------------------------------------------+
```

### Padroes arquiteturais

- **Strategy Pattern** — Normalizacao por banco (`bank_strategy/`), conectores de taxas
- **Pipeline Pattern** — ETL em 5 estagios sequenciais
- **Repository Pattern** — Abstracao de acesso a dados (`db/`)
- **Multi-layer Fallback** — ML -> Regras -> Defaults (PF/PJ, categorizacao)
- **ReAct Agent** — Agente LangGraph com decisao automatica de ferramentas

---

## Estrutura do backend

```
backend/
+-- app/
|   +-- main.py                        # FastAPI app
|   +-- runner.py                      # NexaRunner: orquestra pipeline completo
|   +-- api/v1/routes/                 # Endpoints (16 routers registrados)
|   +-- agent/                         # Agente LangGraph ReAct
|   |   +-- graph.py                   # build_financial_agent() — monta o agente
|   |   +-- state.py                   # AgentState
|   |   +-- tools/                     # 8 ferramentas do agente
|   |   +-- nodes/                     # Nos do grafo (explain, forecast, recurrence)
|   +-- etl/                           # Pipeline ETL
|   |   +-- ingestor.py                # Normalizacao por banco
|   |   +-- classifier.py             # Categorizacao de transacoes
|   |   +-- pf_pj_classifier.py       # Classificacao PF/PJ (ML + regras)
|   |   +-- income_profiler.py         # Estimativa real de renda mensal
|   |   +-- spending_anomaly_detector.py # Deteccao de anomalias
|   |   +-- recurring_detector.py      # Padroes recorrentes
|   |   +-- fiscal_report.py           # Relatorio fiscal MEI/PJ
|   |   +-- mixed_use_detector.py      # Deteccao de despesas mistas PF/PJ
|   |   +-- pj_subcategory_classifier.py # Sub-categorizacao PJ
|   |   +-- bank_strategy/             # Estrategias especificas: Nubank, Itau, Inter, default
|   |   +-- shadow_invoices/           # Detectores de assinaturas e parcelas
|   +-- cashflow/                      # Projecao de saldo e safe-to-spend
|   |   +-- projector.py
|   |   +-- safe_to_spend.py
|   |   +-- budget_advisor.py          # Plano 50/30/20
|   |   +-- burn_rate.py
|   +-- optimizer/                     # F2: Card Optimizer
|   |   +-- profiler.py
|   |   +-- card_loader.py             # Base de cartoes (knowledge_cards.json)
|   |   +-- ranking.py
|   |   +-- simulator.py
|   |   +-- multi_card_strategy.py
|   |   +-- opportunity_cost.py
|   |   +-- services/optimizer_service.py
|   +-- architect/                     # F3: Simulador de compra de bem
|   |   +-- calculators/               # Financiamento, consorcio, investimento, VPL
|   |   +-- connectors/                # BACEN, ANBIMA (taxas reais)
|   |   +-- simulators/                # Monte Carlo, sensibilidade
|   |   +-- services/architect_service.py
|   +-- goals/                         # MX.2: Metas financeiras
|   |   +-- tracker.py
|   +-- notifications/                 # MX.3: Notificacoes proativas
|   |   +-- notifier.py
|   +-- peers/                         # MX.4: Comparacao com pares
|   |   +-- peer_comparison.py
|   +-- integrations/open_finance/    # Cliente Pluggy (real + mock)
|   +-- domain/                       # Finance engine: health score, savings rate
|   +-- schemas/                      # Modelos Pydantic
|   +-- db/                           # DuckDB queries e migrations (5 migrations)
|   +-- core/                         # Config, logging, seguranca
+-- models/                            # Modelos ML serializados (.pkl)
|   +-- pf_pj_classifier.pkl          # Random Forest PF/PJ
|   +-- feature_encoders.pkl
|   +-- feature_scaler.pkl
+-- data/                              # Datasets de treino e base de cartoes
|   +-- cards/knowledge_cards.json    # Base de cartoes brasileiros
|   +-- architect/                    # Dados historicos SELIC, BACEN
+-- scripts/                           # Scripts de treino e validacao ML
+-- tests/                             # 414 testes pytest
+-- streamlit_agent_test.py            # Interface de teste do agente (Streamlit)
```

---

## Stack tecnologica

| Camada | Tecnologia |
|---|---|
| API | FastAPI 0.128.0 + Uvicorn |
| DataFrames | Polars (producao), Pandas (legado) |
| Banco de dados | DuckDB (local), PostgreSQL (producao) |
| Validacao | Pydantic v2 |
| ML / Classificacao | Scikit-learn (Random Forest PF/PJ) |
| Open Finance | Pluggy API + MockPluggyClient |
| Taxas de mercado | BACEN API + ANBIMA + dados historicos locais |
| Agente IA | LangGraph + LangChain + OpenAI (gpt-4o-mini) |
| Testes | pytest + pytest-asyncio (414 testes) |
| Interface de teste | Streamlit (`streamlit_agent_test.py`) |

---

## Scripts utilitarios

```bash
# Migracoes de banco
python scripts/db/apply_migrations.py

# Treinar modelo PF/PJ
python scripts/ml/train_pf_pj_classifier.py

# Validar modelo PF/PJ
python scripts/ml/validate_pf_pj_classifier.py

# Criar dataset rotulado
python scripts/ml/create_labeled_dataset.py

# Testar API manualmente
python scripts/debug/test_api.py
```

---

## Documentacao adicional

| Arquivo | Conteudo |
|---|---|
| [docs/SETUP_LOCAL.md](docs/SETUP_LOCAL.md) | Setup local sem Docker, fallback DuckDB, troubleshooting |
| [docs/ENDPOINTS_SUMMARY.md](docs/ENDPOINTS_SUMMARY.md) | Referencia completa de todos os endpoints (parametros, responses, curl) |
| [docs/QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md) | Cheatsheet do dev: comandos, estrutura, como adicionar rotas |
| [docs/FRONTEND_GRAFICOS.md](docs/FRONTEND_GRAFICOS.md) | Spec dos componentes visuais com mapeamento de endpoints |
| [docs/NEXA_ESTRATEGIA_TECNICA.md](docs/NEXA_ESTRATEGIA_TECNICA.md) | Estrategia tecnica do produto |
| [docs/ARCHITECT_F3.md](docs/ARCHITECT_F3.md) | Documentacao do modulo Architect (F3) — implementacao atual |
| [docs/NEXA_ARCHITECT_V2_SPEC.md](docs/NEXA_ARCHITECT_V2_SPEC.md) | Especificacao tecnica v2.0: modelos estocasticos, data layer, risk engine, behavioral finance |
| [docs/PF_PJ_VALIDATION_REPORT.md](docs/PF_PJ_VALIDATION_REPORT.md) | Relatorio de validacao do classificador PF/PJ (89% acuracia) |
| [docs/BACKEND_REFERENCE.md](docs/BACKEND_REFERENCE.md) | Referencia completa de todos os arquivos e pastas do backend — o que cada um faz, como usar |


