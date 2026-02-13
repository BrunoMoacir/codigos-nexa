# 🗺️ NEXA AI - VISUAL ARCHITECTURE MAP

---

## VISÃO GERAL: COMO OS DADOS FLUEM

```
┌────────────────────────────────────────────────────────────────────┐
│                         USUÁRIO FINAL                              │
│                    "Quanto posso gastar?"                          │
└─────────────────────────────────┬────────────────────────────────┘
                                  │
                    ┌─────────────▼────────────┐
                    │  FastAPI (app/main.py)   │
                    │  localhost:8000          │
                    └─────────────┬────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
        ▼                         ▼                         ▼
    ┌────────┐         ┌────────────┐            ┌──────────────┐
    │ GET /..│         │ POST /...  │            │ Health check │
    └────┬───┘         └────┬───────┘            └────┬─────────┘
         │                  │                         │
         └──────────────────┼─────────────────────────┘
                            │
              ┌─────────────▼──────────────┐
              │  Pydantic Schemas         │
              │  (app/schemas/*)          │
              │  ✓ Validar tipos          │
              │  ✓ Converter valores      │
              └─────────────┬──────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
    ┌─────────┐     ┌──────────┐       ┌───────────────┐
    │ Runner  │     │ Agent    │       │ API Response  │
    │ (ETL    │     │ (Chat/   │       │ Builder       │
    │ Pipeline)     │ LLM)     │       │               │
    └────┬────┘     └────┬─────┘       └───────────────┘
         │              │
         └──────┬───────┘
                │
    ┌───────────▼──────────────────────────────────┐
    │            NexaRunner                        │
    │  (app/runner.py - Orquestrador Principal)   │
    └───────────┬──────────────────────────────────┘
                │
    ┌───────────┴──────────────────┬───────────────┐
    │                              │               │
    ▼                              ▼               ▼
┌─────────────┐         ┌──────────────────┐  ┌──────────┐
│  PLUGGY     │         │  ETL PIPELINE    │  │ DuckDB   │
│  (dados     │         │  (app/etl/)      │  │ (cache)  │
│   brutos)   │         │                  │  └──────────┘
└─────────────┘         └──────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
    ┌──────────┐       ┌─────────────┐      ┌─────────────┐
    │Validator │       │Classifier   │      │Recurring    │
    │          │       │(CatBoost)   │      │Detector     │
    │ bank val │       │             │      │             │
    └────┬─────┘       └──────┬──────┘      └──────┬──────┘
         └──────┬─────────────┴─────────────────────┘
                │
                ▼
         ┌─────────────────┐
         │ Shadow Invoice  │
         │ Detector (etl/) │
         │ Detecta futuros │
         └────────┬────────┘
                  │
      ┌───────────┼───────────┐
      │           │           │
      ▼           ▼           ▼
 ┌─────────┐ ┌──────────┐ ┌─────────┐
 │Cashflow │ │Safe-to-  │ │Profile  │
 │Projector│ │Spend     │ │Analyzer │
 │(30 dias)│ │Calculator│ │         │
 └────┬────┘ └────┬─────┘ └────┬────┘
      │           │            │
      └───────┬───┴────────┬───┘
              │            │
              ▼            ▼
        ┌──────────────────────┐
        │ ForecastResponse     │
        │ (Consolidado)        │
        │                      │
        │ ├─ financial_health  │
        │ ├─ cashflow          │
        │ ├─ safe_to_spend     │
        │ ├─ shadow_invoices   │
        │ └─ monthly_forecasts │
        └──────────┬───────────┘
                   │
                   ▼
           ┌──────────────┐
           │ Retorna JSON │
           │ Status: 200  │
           │ Content-Type │
           │application/json
           └──────────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │ FRONTEND             │
        │ Mostra resultado     │
        │ "Gaste R$ 107.67"    │
        └──────────────────────┘
```

---

## CAMADAS DA ARQUITETURA

```
┌─────────────────────────────────────────────────────────────────┐
│                      APRESENTAÇÃO                               │
│  FastAPI HTTP Endpoints (app/api/v1/routes/*.py)                │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│                      VALIDAÇÃO                                  │
│  Pydantic Schemas (app/schemas/*.py)                            │
│  ✓ Converte tipos, ✓ Valida, ✓ Documentação OpenAPI            │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│                    LÓGICA DE NEGÓCIO                            │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ NexaRunner (app/runner.py)                              │  │
│  │ Orquestrador do pipeline completo                       │  │
│  └──────────────────────────────────┬───────────────────────┘  │
│                                     │                           │
│     ┌───────────────────────────────┼───────────────────────┐   │
│     │                               │                       │   │
│     ▼                               ▼                       ▼   │
│  ┌────────────┐            ┌─────────────────┐      ┌──────────┐│
│  │ ETL Layer  │            │ Engine Layer    │      │Agent     ││
│  │(app/etl/)  │            │(app/cashflow/)  │      │Layer     ││
│  │            │            │                 │      │(F3)      ││
│  │• Ingestor  │            │• Projector      │      └──────────┘│
│  │• Classifier│            │• SafeToSpend    │                  │
│  │• Recurring │            │• Calculator     │                  │
│  │• Shadow    │            └─────────────────┘                  │
│  └────────────┘                                                 │
│                                                                  │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│                      DADOS & STORAGE                            │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ DuckDB (Local Cache)          Postgres (Produção)       │  │
│  │ transactions_clean            raw_events               │  │
│  │ categories                    user_overrides             │  │
│  │ patterns                      context_classification    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│                      INTEGRAÇÕES EXTERNAS                       │
│  • Pluggy Open Finance (Transações)                             │
│  • Claude API (Recomendações - F3)                             │
│  • Redis (Cache/Queue - TODO)                                  │
│  • S3 (Raw events - TODO)                                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## MAPA: QUAL ARQUIVO EDITAR?

```
┌─────────────────────────────────────────────────────────────────┐
│                        QUERO ADICIONAR                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ 🔨 Novo ENDPOINT                                                │
│    → backend/app/api/v1/routes/xyz.py (novo arquivo)           │
│    → adicione em router.py → include_router(xyz.router)         │
│                                                                  │
│ 📝 Nova VALIDAÇÃO                                               │
│    → backend/app/schemas/xyz.py (novo arquivo)                 │
│    → use em routes: data: XyzSchema                             │
│                                                                  │
│ 🔄 Novo PROCESSAMENTO ETL                                       │
│    → backend/app/etl/new_processor.py                           │
│    → chame do runner.py                                         │
│                                                                  │
│ 📊 Novo CÁLCULO FINANCEIRO                                      │
│    → backend/app/cashflow/new_calc.py                           │
│    → chame do runner.py                                         │
│                                                                  │
│ 🤖 Nova REGRA DE ML                                             │
│    → backend/app/ml/models/ (salve modelo .pkl)                │
│    → carregue em etl/classifier.py                              │
│                                                                  │
│ 🧠 Nueva CONVERSAÇÃO / AGENT                                    │
│    → backend/app/agent/nodes/new_node.py                        │
│    → adicione ao graph.py                                       │
│                                                                  │
│ 📡 Nueva INTEGRAÇÃO EXTERNA (LLM, etc)                          │
│    → backend/app/integrations/new_service/                      │
│    → importe em runner.py ou agent/                             │
│                                                                  │
│ 💾 Nueva TABELA NO BANCO                                        │
│    → backend/app/db/models.py (defina ORM)                      │
│    → backend/migrations/ (crie migration)                       │
│    → alembic upgrade head                                       │
│                                                                  │
│ 🧪 Novo TESTE                                                   │
│    → backend/tests/test_xyz.py                                  │
│    → pytest tests/test_xyz.py                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## FLUXO: ADICIONAR ENDPOINT

```
1. CREATE FILE
   backend/app/api/v1/routes/my_endpoint.py
   
   ├─ from fastapi import APIRouter
   ├─ router = APIRouter(prefix="/my", tags=["My"])
   ├─ @router.get("/{user_id}")
   ├─ async def my_handler(user_id: str) -> MyResponse:
   │   return {"result": "..."}
   └─ @router.get("", tags=["Health"])
      def health(): return {"status": "ok"}

2. REGISTER ROUTE
   backend/app/api/v1/router.py
   
   ├─ from app.api.v1.routes import my_endpoint
   └─ api_router.include_router(my_endpoint.router)

3. CREATE SCHEMA (optional but recommended)
   backend/app/schemas/my_schema.py
   
   ├─ from pydantic import BaseModel
   └─ class MyResponse(BaseModel):
      result: str

4. TEST
   ├─ curl http://localhost:8000/api/v1/my/user_123
   └─ or via Swagger: http://localhost:8000/docs

5. SUCCESS!
   New endpoint live and documented
```

---

## STACK TÉCNICO: O QUE CADA TECH FAZ

```
┌────────────────────────────────────────────────────────────────┐
│ LAYER                    │ TECHNOLOGY         │ PAPEL          │
├────────────────────────────────────────────────────────────────┤
│ Web Framework            │ FastAPI 0.128      │ HTTP server    │
│ ASGI Server              │ Uvicorn 0.40       │ Runs FastAPI   │
│ Validation               │ Pydantic 2.12      │ Schema checks  │
├────────────────────────────────────────────────────────────────┤
│ Data Processing          │ Polars 0.20        │ Fast DataFrame │
│ Data Storage (Local)     │ DuckDB             │ SQL queries    │
│ Data Storage (Prod)      │ PostgreSQL 14+     │ Persistence   │
├────────────────────────────────────────────────────────────────┤
│ ORM                      │ SQLAlchemy 2.0     │ DB abstraction │
│ Migrations               │ Alembic 1.13       │ Schema versioning
├────────────────────────────────────────────────────────────────┤
│ Classification ML        │ CatBoost 1.2       │ Categorize txns│
│ Pattern Detection        │ Scikit-learn 1.3   │ Find patterns  │
│ ML Storage               │ Pickle+S3 (TBD)    │ Save models    │
├────────────────────────────────────────────────────────────────┤
│ Agent Orchestration      │ LangGraph 0.x      │ Conversa AI    │
│ LLM Integration          │ Claude/GPT-4       │ Recommendations│
├────────────────────────────────────────────────────────────────┤
│ Open Finance             │ Pluggy + Belvo     │ Get transactions
│ Cache                    │ Redis (TBD)        │ Speed up       │
│ Cloud Storage            │ AWS S3 (TBD)       │ Raw events     │
├────────────────────────────────────────────────────────────────┤
│ Logging                  │ Structlog 24.1     │ Structured logs│
│ Security                 │ Python-jose 3.3    │ JWT tokens     │
│ Testing                  │ Pytest 7.4         │ Run tests      │
└────────────────────────────────────────────────────────────────┘
```

---

## FUNCIONALIDADES E O QUE CADA UMA USA

```
┌─────────────────────┬──────────────────┬──────────────────────┐
│ FUNCIONALIDADE      │ USA MODULES      │ STATUS               │
├─────────────────────┼──────────────────┼──────────────────────┤
│ F1: Core Engine     │ • api/routes/    │ ✅ COMPLETA (100%)   │
│ (Forecast)          │ • schemas/       │                      │
│                     │ • etl/           │                      │
│                     │ • cashflow/      │                      │
│                     │ • runner.py      │                      │
├─────────────────────┼──────────────────┼──────────────────────┤
│ F2: Optimizer       │ • api/routes/    │ ⏳ TODO (0%)         │
│ (Card analysis)     │ • schemas/       │ Est: 3-4 horas       │
│                     │ • ml/models/     │                      │
│                     │ • (new module)   │                      │
├─────────────────────┼──────────────────┼──────────────────────┤
│ F3: Architect       │ • agent/         │ ⏳ TODO (0%)         │
│ (LLM recommend)     │ • integrations/  │ Est: 4-5 horas       │
│                     │ • Claude API     │                      │
├─────────────────────┼──────────────────┼──────────────────────┤
│ F4: Divider PF/PJ   │ • etl/           │ ⏳ TODO (0%)         │
│ (Separation)        │ • ml/models/     │ Est: 6-8 horas       │
│                     │ • schemas/       │                      │
│                     │ • db/            │                      │
└─────────────────────┴──────────────────┴──────────────────────┘
```

---

## DEPENDENCY GRAPH: QUAL MÓDULO DEPENDE DE QUAL

```
                    ┌─────────────────┐
                    │  HTTP Request   │
                    └────────┬────────┘
                             ▼
                    ┌─────────────────┐
                    │  FastAPI Route  │
                    │  (api/routes/)  │
                    └────────┬────────┘
                             ▼
                    ┌─────────────────┐
                    │  Pydantic       │
                    │  (schemas/)     │
                    └────────┬────────┘
                             ▼
            ┌────────────────────────────┐
            │  NexaRunner                │
            │  (app/runner.py)           │
            └────┬──────────────┬─────────┘
                 │              │
         ┌───────▼──────┐   ┌───▼─────────────┐
         │ ETL Pipeline │   │ Cashflow Engine │
         │ (etl/)       │   │ (cashflow/)     │
         ├──────────────┤   └────┬────────────┘
         │• Ingestor    │        │
         │• Classifier  │   ┌────▼──────────┐
         │• Recurring   │   │ DuckDB / PG   │
         │• Shadow      │   │ (db/)         │
         └───┬──────────┘   └───┬───────────┘
             │                  │
    ┌────────▼──────────────────▼───────┐
    │ ML Models (ml/models/)            │
    │ • CatBoost classifier             │ 
    │ • Random Forest (PF/PJ - F4)      │
    └──────────────────────────────────┘

INTEGRATIONS (external):
    Pluggy → TransactionIngestor
    Claude → Agent (F3)
    Redis  → Cache (TBD)
    S3     → Storage (TBD)
```

---

## DEPLOYMENT REGIONS (Conceitual - Futuro)

```
┌──────────────────────────────────────────────────────────────┐
│ CLOUD DEPLOYMENT STRUCTURE (Post-MVP)                        │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─ Frontend (React/Next.js)                                │
│  │  └─→ Vercel / CloudFlare                                 │
│  │                                                           │
│  ├─ API Gateway                                             │
│  │  └─→ AWS API Gateway / CloudFlare Workers               │
│  │                                                           │
│  ├─ Backend (FastAPI)                                       │
│  │  └─→ ECS / Kubernetes / Lambda                          │
│  │      └─→ Auto-scaling                                    │
│  │      └─→ Load balancer     →........                     │
│  │                                    │                     │
│  ├─ PostgreSQL                    ┌───┴────────┐            │
│  │  └─→ AWS RDS / CloudSQL        │ Read-Only  │            │
│  │                                │ Replicas   │            │
│  ├─ Redis Cache                   └────────────┘            │
│  │  └─→ ElastiCache / Upstash                              │
│  │                                                           │
│  ├─ S3 / Cloud Storage                                      │
│  │  └─→ aws.s3 / gs: cloud storage                         │
│  │      └─→ Backup + Raw events storage                   │
│  │                                                           │
│  └─ Monitoring / Logging                                    │
│     └─→ DataDog / New Relic / CloudWatch                   │
│         └─→ Error tracking (Sentry)                         │
│         └─→ Performance monitoring                          │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## 🎯 NEXT STEPS VISUALIZATION

```
┌──────────────────────────────────────────────────────────────┐
│ HOJE/AMANHÃ: Começar F2 + F3                                 │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─ F2: OPTIMIZER (3-4h)                                     │
│  │  ├─ Análise de cartões                                   │
│  │  ├─ Score por cartão                                     │
│  │  ├─ Recomendação fusão                                   │
│  │  └─ Teste + Documentação                                 │
│  │                                                           │
│  ├─ F3: ARCHITECT (4-5h)                                     │
│  │  ├─ Integração Claude                                    │
│  │  ├─ Tools do agent                                       │
│  │  ├─ Recomendações gerais                                │
│  │  └─ Teste + Documentação                                 │
│  │                                                           │
│  └─ TOTAL: 7-9 horas                                         │
│                                                               │
├──────────────────────────────────────────────────────────────┤
│ DEPOIS: F4 (Divider) + Database Integration                 │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─ F4: DIVIDER (6-8h)                                       │
│  │  ├─ Feature engineering                                  │
│  │  ├─ Random Forest training                              │
│  │  ├─ Decision rules                                       │
│  │  └─ Integração com F1                                    │
│  │                                                           │
│  └─ DATABASE (3-4h)                                          │
│     ├─ Migrate DuckDB → PostgreSQL                          │
│     ├─ Alembic migrations                                   │
│     └─ Persistência real                                    │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

**Imprime este arquivo e cola na parede! 📌**
