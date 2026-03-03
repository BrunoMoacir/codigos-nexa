# Nexa AI — Backend

Agente financeiro inteligente que usa dados do Open Finance (via Pluggy) para analisar saúde financeira, projetar fluxo de caixa, otimizar uso de cartões e simular decisões de compra de bens.

---

## Status das Funcionalidades

| Funcionalidade | Descrição | Status |
|---|---|---|
| **F1 — Core Engine** | ETL, cashflow 30 dias, safe-to-spend, shadow invoices, perfil financeiro | ✅ Completo |
| **F2 — Card Optimizer** | Ranqueamento de cartões, estratégia multi-cartão, custo de oportunidade | ✅ Completo |
| **F3 — Nexa Architect** | Simulação financeira (financiamento vs consórcio vs investimento), Monte Carlo, VPL | ✅ Completo |
| **F4 — Nexa Divider** | Classificação automática PF/PJ via Random Forest + fallback por regras | ✅ Completo |
| **Income Profiler** | Estimativa real de renda mensal (filtra transferências, estornos, rendimentos) | ✅ Completo |
| **Spending Anomaly Detector** | Detecção de gastos anormais por categoria | ✅ Completo |
| Agente conversacional LLM | Agente LangGraph com Claude AI | Em desenvolvimento |

---

## Pré-requisitos

- Python 3.11+
- Conta na [Pluggy](https://pluggy.ai) com `CLIENT_ID` e `CLIENT_SECRET`

---

## Instalação

```bash
cd backend
pip install -r requirements.txt
# ou
poetry install
```

---

## Variáveis de ambiente

Crie o arquivo `backend/.env`:

```env
# Pluggy (Open Finance)
PLUGGY_CLIENT_ID=seu_client_id
PLUGGY_CLIENT_SECRET=seu_client_secret
PLUGGY_BASE_URL=https://api.pluggy.ai

# URL do frontend (usada no redirect de reconexão)
FRONTEND_BASE_URL=http://localhost:3000

# Banco de dados (produção)
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

| Método | Rota | O que faz |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/version` | Versão da API |
| `GET` | `/docs` | Swagger UI |

### F1 — Saúde financeira e previsão

| Método | Rota | O que faz |
|---|---|---|
| `GET` | `/api/v1/forecast/{user_id}` | Previsão completa: cashflow 30 dias, safe-to-spend, shadow invoices, perfil financeiro |
| `GET` | `/api/v1/shadow_invoice/{user_id}` | Lista obrigações futuras detectadas (assinaturas + parcelas) |
| `GET` | `/api/v1/shadow_invoice/{user_id}/summary` | Resumo de obrigações futuras |
| `GET` | `/api/v1/alerts/{user_id}` | Alertas ativos: token expirado, saldo negativo, caixa comprometido |
| `DELETE` | `/api/v1/alerts/{user_id}/{alert_id}` | Dispensar alerta |
| `GET` | `/api/v1/safe_to_spend/{user_id}` | Margem segura de gastos do dia |

### Transações

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/api/v1/transactions/webhook` | Recebe transações do Pluggy, valida e roda ETL |
| `GET` | `/api/v1/transactions/{user_id}` | Busca transações do usuário |

### F2 — Card Optimizer

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/api/v1/optimizer/recommend` | Ranqueia cartões pelo perfil de gastos do usuário |
| `POST` | `/api/v1/optimizer/simulate` | Simula retorno de um cartão específico para os gastos do usuário |
| `POST` | `/api/v1/optimizer/multi_card` | Estratégia multi-cartão: carteira ótima de até N cartões |
| `POST` | `/api/v1/optimizer/opportunity_cost` | Calcula quanto o usuário perdeu usando o cartão atual vs alternativas |

### F3 — Nexa Architect (Simulação de Compra)

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/api/v1/architect/simulate` | Compara financiamento vs consórcio vs investimento. Ranqueia por VPL. Busca taxas reais BACEN/ANBIMA. |
| `GET` | `/api/v1/architect/simulations` | Lista simulações anteriores do usuário |
| `GET` | `/api/v1/architect/simulations/{id}` | Detalhe de uma simulação |
| `GET` | `/api/v1/architect/simulations/{id}/sensitivity` | Re-análise de sensibilidade com taxas atuais |
| `GET` | `/api/v1/architect/metrics` | Métricas do usuário |

### F4 — Classificação PF/PJ

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/api/v1/context/override` | Salva correção manual de classificação PF/PJ |
| `GET` | `/api/v1/context/overrides/{user_id}` | Lista correções manuais do usuário |

### Utilitários e desenvolvimento

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/api/v1/reconnect/{user_id}` | Gera URL de reconexão do consentimento Pluggy |
| `GET` | `/api/v1/banks/simulate/{bank}` | Dados bancários mock para desenvolvimento |
| `GET` | `/dashboard/summary` | Resumo financeiro básico |

---

## Exemplos de uso

### Simulação de compra de bem (F3)

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

Retorna as 3 estratégias ranqueadas por custo total (VPL), com análise de sensibilidade e simulação Monte Carlo.

### Recomendação de cartão (F2)

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
                        ┌───────────────────────────────────────┐
                        │          USUÁRIO / FRONTEND            │
                        └─────────────────┬─────────────────────┘
                                          │ HTTP
                        ┌─────────────────▼─────────────────────┐
                        │        FastAPI (app/main.py)           │
                        └──┬──────────────┬──────────────────┬──┘
                           │              │                  │
              ┌────────────▼──┐  ┌────────▼────────┐  ┌─────▼──────────────┐
              │  ETL Pipeline │  │ Cashflow Engine  │  │  Architect (F3)    │
              │  (5 estágios) │  │ projector.py     │  │  Financiamento,    │
              └──────┬────────┘  └────────┬─────────┘  │  Consórcio, Monte  │
                     │                   │             │  Carlo, VPL/TIR    │
              ┌──────▼────────┐  ┌────────▼─────────┐  └─────┬──────────────┘
              │  Ingestor     │  │  SafeToSpend     │        │
              │  Classifier   │  │  Projector       │  ┌─────▼──────────────┐
              │  PF/PJ ML     │  └──────────────────┘  │  Card Optimizer    │
              │  RecurrDet.   │                         │  (F2)              │
              │  ShadowInv.   │                         │  Ranking, Multi-   │
              │  IncomePrf.   │                         │  card, Opp. Cost   │
              └──────┬────────┘                         └────────────────────┘
                     │
              ┌──────▼──────────────────────────────────┐
              │              Data Layer                  │
              │  DuckDB (local)  │  PostgreSQL (prod)    │
              │  Polars DataFrames                       │
              └──────┬──────────────────────────────────┘
                     │
              ┌──────▼──────────────────────────────────┐
              │        External Integrations             │
              │  Pluggy Open Finance API                 │
              │  BACEN / ANBIMA (taxas de mercado)       │
              └──────────────────────────────────────────┘
```

### Padrões arquiteturais

- **Strategy Pattern** — Normalização por banco (`bank_strategy/`), conectores de taxas
- **Pipeline Pattern** — ETL em 5 estágios sequenciais
- **Repository Pattern** — Abstração de acesso a dados (`db/`)
- **Multi-layer Fallback** — ML → Regras → Defaults (PF/PJ, categorização)

---

## Estrutura do backend

```
backend/
├── app/
│   ├── main.py                        # FastAPI app
│   ├── runner.py                      # NexaRunner: orquestra pipeline completo
│   ├── api/v1/routes/                 # Endpoints
│   ├── etl/                           # Pipeline ETL (ingestão, classificação, shadow invoices)
│   │   ├── ingestor.py                # Normalização por banco
│   │   ├── classifier.py             # Categorização de transações
│   │   ├── pf_pj_classifier.py       # Classificação PF/PJ (ML + regras)
│   │   ├── income_profiler.py         # Estimativa real de renda mensal
│   │   ├── spending_anomaly_detector.py # Detecção de anomalias de gastos
│   │   ├── recurring_detector.py      # Detecção de padrões recorrentes
│   │   ├── bank_strategy/             # Estratégias específicas por banco
│   │   └── shadow_invoices/           # Detectores de assinaturas e parcelas
│   ├── cashflow/                      # Projeção de saldo e safe-to-spend
│   ├── optimizer/                     # F2: Card Optimizer
│   │   ├── profiler.py               # Perfil de gastos do usuário
│   │   ├── card_loader.py            # Base de cartões (knowledge_cards.json)
│   │   ├── ranking.py                # Ranqueamento de cartões
│   │   ├── simulator.py              # Simulação de retorno por cartão
│   │   ├── multi_card_strategy.py    # Estratégia multi-cartão ótima
│   │   ├── opportunity_cost.py       # Custo de oportunidade do cartão atual
│   │   └── services/optimizer_service.py # Orquestrador do Optimizer
│   ├── architect/                     # F3: Simulador de compra de bem
│   │   ├── calculators/              # Financiamento, consórcio, investimento, VPL
│   │   ├── connectors/               # BACEN, ANBIMA (taxas reais)
│   │   ├── simulators/               # Monte Carlo, análise de sensibilidade
│   │   └── services/architect_service.py # Orquestrador do Architect
│   ├── integrations/open_finance/    # Cliente Pluggy (real + mock)
│   ├── domain/                       # Finance engine: health score, savings rate
│   ├── schemas/                      # Modelos Pydantic
│   ├── db/                           # DuckDB queries e migrations
│   └── core/                         # Config, logging, segurança
├── models/                            # Modelos ML serializados (.pkl)
│   ├── pf_pj_classifier.pkl          # Random Forest PF/PJ
│   ├── feature_encoders.pkl
│   └── feature_scaler.pkl
├── data/                              # Datasets de treino e base de cartões
│   ├── cards/knowledge_cards.json    # Base de cartões brasileiros
│   └── architect/                    # Dados históricos SELIC, BACEN
├── scripts/                           # Scripts de treino e validação ML
└── tests/                             # 414 testes pytest
```

---

## Stack tecnológica

| Camada | Tecnologia |
|---|---|
| API | FastAPI 0.128.0 + Uvicorn |
| DataFrames | Polars (produção), Pandas (legado) |
| Banco de dados | DuckDB (local), PostgreSQL (produção) |
| Validação | Pydantic v2 |
| ML / Classificação | Scikit-learn (Random Forest PF/PJ) |
| Open Finance | Pluggy API + MockPluggyClient |
| Taxas de mercado | BACEN API + ANBIMA + dados históricos locais |
| Testes | pytest + pytest-asyncio (414 testes) |
| Agente (futuro) | LangGraph + LangChain + Claude AI (Anthropic) |

---

## Scripts utilitários

```bash
# Migrações de banco
python scripts/apply_migrations.py

# Treinar modelo PF/PJ
python scripts/train_pf_pj_classifier.py

# Validar modelo PF/PJ
python scripts/validate_pf_pj_classifier.py

# Criar dataset rotulado
python scripts/create_labeled_dataset.py

# Testar API manualmente
python scripts/test_api.py
```

---

## Documentação adicional

| Arquivo | Conteúdo |
|---|---|
| [backend/app/project_docs/ARCHITECTURE.md](backend/app/project_docs/ARCHITECTURE.md) | Arquitetura detalhada com diagramas de fluxo |
| [backend/app/project_docs/DOCUMENTACAO_COMPLETA.md](backend/app/project_docs/DOCUMENTACAO_COMPLETA.md) | Documentação técnica completa de todos os módulos |
| [backend/app/project_docs/MELHORIA_FUNCIONALIDADES.md](backend/app/project_docs/MELHORIA_FUNCIONALIDADES.md) | Melhorias implementadas por funcionalidade |
| [backend/app/project_docs/HOW_TO_TEST.md](backend/app/project_docs/HOW_TO_TEST.md) | Guia de testes (6 métodos) |
| [backend/app/project_docs/PRODUCTION_CHECKLIST.md](backend/app/project_docs/PRODUCTION_CHECKLIST.md) | Checklist para ir a produção |
| [backend/docs/pf_pj_validation_report.md](backend/docs/pf_pj_validation_report.md) | Relatório de validação do classificador PF/PJ |
