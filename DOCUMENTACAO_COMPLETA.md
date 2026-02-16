# NEXA AI — DOCUMENTAÇÃO TÉCNICA COMPLETA

> Gerado em: 2026-02-16
> Status do Projeto: MVP em andamento (F1 ✅ | F4 90% ✅ | F2 📋 | F3 📋)

---

## ÍNDICE

1. [Visão Geral do Projeto](#1-visão-geral-do-projeto)
2. [Stack Tecnológica](#2-stack-tecnológica)
3. [Estrutura de Diretórios](#3-estrutura-de-diretórios)
4. [Arquitetura do Sistema](#4-arquitetura-do-sistema)
5. [Pipeline ETL (5 Estágios)](#5-pipeline-etl-5-estágios)
6. [Funcionalidades Implementadas](#6-funcionalidades-implementadas)
7. [API — Endpoints Completos](#7-api--endpoints-completos)
8. [Schemas e Modelos de Dados](#8-schemas-e-modelos-de-dados)
9. [Componentes ML](#9-componentes-ml)
10. [Motores de Cálculo Financeiro](#10-motores-de-cálculo-financeiro)
11. [Testes e Cobertura](#11-testes-e-cobertura)
12. [Configuração e Deploy](#12-configuração-e-deploy)
13. [Roadmap e Próximos Passos](#13-roadmap-e-próximos-passos)
14. [Decisões de Arquitetura](#14-decisões-de-arquitetura)

---

## 1. VISÃO GERAL DO PROJETO

**Nexa AI** é uma plataforma de agente financeiro autônomo voltada para o público brasileiro. A proposta central é democratizar a inteligência de "Family Office" para pessoas comuns, combinando **IA generativa + matemática determinística** para:

- Prever o fluxo de caixa com 30+ dias de antecedência
- Detectar automaticamente obrigações financeiras recorrentes
- Recomendar otimizações de gastos e cartões
- Separar finanças pessoais (PF) de empresariais (PJ)
- Oferecer recomendações via agente inteligente com Claude AI

### Pilares da Plataforma

| Pilar | Funcionalidade | Status |
|-------|----------------|--------|
| **Prever o futuro** | Projeção diária de caixa + shadow invoices | ✅ F1 Completo |
| **Otimizar o presente** | Análise de cartões + recomendações | 📋 F2 Planejado |
| **Arquitetar riqueza** | Agente LLM para decisões financeiras | 📋 F3 Especificado |
| **Separar finanças** | Classificação automática PF/PJ | ✅ F4 90% |

---

## 2. STACK TECNOLÓGICA

### Framework & Runtime

| Componente | Versão | Propósito |
|------------|--------|-----------|
| **FastAPI** | 0.128.0 | Framework HTTP, documentação OpenAPI automática |
| **Uvicorn** | 0.40.0 | Servidor ASGI |
| **Python** | 3.11+ | Runtime principal |

### Processamento de Dados

| Componente | Versão | Propósito |
|------------|--------|-----------|
| **Polars** | 0.20.0 | DataFrame de alta performance (substitui Pandas) |
| **Pandas** | 2.0.0 | Suporte legado |
| **DuckDB** | 0.9.0+ | Banco SQL local in-process (OLAP) |
| **PostgreSQL** | 14+ | Persistência em produção (arquitetura pronta) |

### Validação & Serialização

| Componente | Versão | Propósito |
|------------|--------|-----------|
| **Pydantic** | 2.12.5 | Validação de schemas e type-checking |
| **Pydantic-Settings** | 2.1.0 | Configuração via variáveis de ambiente |

### ML & Analytics

| Componente | Versão | Propósito |
|------------|--------|-----------|
| **CatBoost** | 1.2+ | Categorização de transações |
| **Scikit-learn** | 1.3+ | Random Forest para classificação PF/PJ |
| **Joblib** | latest | Serialização de modelos |

### Agente & LLM

| Componente | Versão | Propósito |
|------------|--------|-----------|
| **LangGraph** | 0.0.40+ | Orquestração de agente com estado |
| **LangChain** | 0.1.0+ | Coordenação de chains LLM |
| **LangChain-Anthropic** | 0.1.0+ | Integração com Claude AI |

### Banco de Dados & ORM

| Componente | Versão | Propósito |
|------------|--------|-----------|
| **SQLAlchemy** | 2.0.25 | ORM |
| **Alembic** | 1.13.1 | Migrações de schema |
| **Psycopg2** | 2.9.9 | Driver PostgreSQL |

### Segurança & Infraestrutura

| Componente | Versão | Propósito |
|------------|--------|-----------|
| **Python-Jose** | 3.3.0 | JWT |
| **Passlib** | 1.7.4 | Hash de senhas |
| **Structlog** | 24.1.0 | Logs estruturados |
| **Redis** | 5.0.1 | Cache & filas (planejado) |
| **Boto3** | 1.34.0 | AWS S3 (planejado) |

### Testes

| Componente | Versão | Propósito |
|------------|--------|-----------|
| **Pytest** | 7.4.4 | Runner de testes |
| **Pytest-asyncio** | 0.23.3 | Suporte a testes assíncronos |
| **HTTPx** | 0.26.0 | Cliente HTTP para testes FastAPI |

### Serviços Externos

| Serviço | Propósito |
|---------|-----------|
| **Pluggy Open Finance API** | Busca transações bancárias reais |
| **Claude AI (Anthropic)** | LLM para recomendações e explicações |
| **BACEN** | Taxas do Banco Central (planejado) |
| **ANBIMA** | Índices de mercado (planejado) |

---

## 3. ESTRUTURA DE DIRETÓRIOS

```
codigos-nexa-19/
├── .env                                # Variáveis de ambiente
├── README.md                           # Visão geral do projeto
├── ARCHITECTURE_VISUAL_MAP.md          # Diagramas ASCII da arquitetura
├── API_IMPLEMENTATION_FINAL.md         # Especificação da API F1
├── FUNCIONALIDADE_3.md                 # Requisitos da F3 (Arquiteto)
├── PROJETO_CHECKOUT_FINAL.md           # Checklist de status
├── QUICK_REFERENCE.md                  # Cheat sheet para devs
├── finance.duckdb                      # Banco DuckDB local (dados de amostra)
│
└── backend/
    ├── pyproject.toml                  # Dependências Poetry
    ├── requirements.txt                # Dependências pip
    ├── .env                            # Config de ambiente
    ├── test_api.py                     # Script de teste manual da API
    ├── HOW_TO_TEST.md                  # Guia de testes (6 métodos)
    ├── ARCHITETURE.md                  # Documentação de arquitetura
    │
    ├── app/
    │   ├── main.py                     # Entry point FastAPI
    │   ├── runner.py                   # NexaRunner — orquestrador ETL
    │   │
    │   ├── api/v1/
    │   │   ├── router.py               # Roteador principal
    │   │   └── routes/
    │   │       ├── forecast.py         # GET /forecast/{user_id}
    │   │       ├── shadow_invoice.py   # GET /shadow_invoice/*
    │   │       ├── alerts.py           # GET /alerts/{user_id}
    │   │       ├── reconnect.py        # POST /reconnect/{user_id}
    │   │       ├── transactions.py     # POST /transactions/webhook
    │   │       ├── safe_to_spend.py    # Cálculo de margem segura
    │   │       ├── cashflow.py         # Endpoints de fluxo de caixa
    │   │       ├── chat.py             # Interface do agente (F3)
    │   │       ├── analyze.py          # Análise de cartões (F2)
    │   │       ├── context_override.py # Override PF/PJ (F4)
    │   │       ├── bank_simulation.py  # Mock dados bancários
    │   │       ├── dashboard.py        # Dashboard
    │   │       └── pluggy_test.py      # Testes integração Pluggy
    │   │
    │   ├── schemas/
    │   │   ├── transaction.py          # TransactionWebhook, BatchResult
    │   │   ├── forecast.py             # ForecastResponse, FinancialHealth
    │   │   ├── shadow_invoice.py       # ShadowInvoiceResponse
    │   │   ├── alerts.py               # AlertsResponse
    │   │   ├── safe_to_spend.py        # SafeToSpendResponse
    │   │   ├── cashflow.py             # CashflowResponse
    │   │   ├── chat.py                 # ChatRequest, ChatResponse
    │   │   └── enums.py                # ProfileType, RiskLevel, DataStatus
    │   │
    │   ├── etl/                        # Pipeline ETL 5 estágios
    │   │   ├── runner.py               # Runner do ETL
    │   │   ├── ingestor.py             # Estágio 1: Normalização
    │   │   ├── classifier.py           # Estágio 2: Categorização
    │   │   ├── pf_pj_classifier.py     # Estágio 2.5: PF/PJ
    │   │   ├── recurring_detector.py   # Estágio 3: Padrões recorrentes
    │   │   ├── shadow_invoices.py      # Estágio 4: Shadow invoices
    │   │   ├── profiles.py             # Perfil financeiro do usuário
    │   │   ├── loader.py               # Estágio 5: Persistência
    │   │   ├── data_quality.py         # Métricas de qualidade
    │   │   ├── bank_strategy/          # Estratégias por banco
    │   │   │   ├── base.py
    │   │   │   ├── registry.py
    │   │   │   └── strategies/
    │   │   │       ├── default.py
    │   │   │       ├── nubank.py
    │   │   │       ├── itau.py
    │   │   │       └── inter.py
    │   │   ├── dedup/                  # Deduplicação
    │   │   │   ├── base.py
    │   │   │   └── default.py
    │   │   └── shadow_invoices/        # Sub-detectores
    │   │       ├── base.py
    │   │       ├── subscription_detector.py
    │   │       ├── installment_detector.py
    │   │       └── runner.py
    │   │
    │   ├── cashflow/
    │   │   ├── engine.py               # CashflowEngine (nome legado)
    │   │   ├── projector.py            # Projeção de 30 dias
    │   │   ├── safe_to_spend.py        # Calculador de margem segura
    │   │   └── models.py               # Modelos de cálculo financeiro
    │   │
    │   ├── core/
    │   │   ├── config.py               # Settings (env vars)
    │   │   ├── logging.py              # Configuração de logs
    │   │   ├── security.py             # JWT e auth
    │   │   ├── recurrence.py           # Regras de recorrência
    │   │   ├── explain.py              # Geração de explicações
    │   │   └── shadow_invoices.py      # Lógica de shadow invoices
    │   │
    │   ├── analysis/
    │   │   ├── recurring_detector.py   # Algoritmos de detecção
    │   │   └── shadow_invoice_detector.py
    │   │
    │   ├── db/
    │   │   ├── models.py               # Modelos ORM SQLAlchemy
    │   │   ├── session.py              # Gerenciamento de conexão
    │   │   ├── queries.py              # Queries pré-construídas
    │   │   └── migrations/             # Scripts Alembic
    │   │
    │   ├── domain/
    │   │   └── finance_engine.py       # Lógica de negócio financeiro
    │   │
    │   ├── engines/
    │   │   ├── calculator.py           # Fórmulas financeiras (NPV, IRR)
    │   │   ├── reconciler.py           # Conciliação de transações
    │   │   └── shadow_invoice.py       # Motor de shadow invoices
    │   │
    │   ├── agent/                      # Agente LangGraph (F3)
    │   │   ├── graph.py                # Grafo de estado do agente
    │   │   ├── state.py                # Definição do FinancialState
    │   │   └── nodes/
    │   │       ├── forecast.py         # Nó de forecast
    │   │       ├── recurrence.py       # Nó de análise de recorrência
    │   │       └── explain.py          # Nó de explicações
    │   │
    │   ├── integrations/open_finance/
    │   │   ├── pluggy.py               # Cliente Pluggy (produção)
    │   │   └── pluggy_mock.py          # Mock Pluggy (dev)
    │   │
    │   ├── ml/models/                  # Armazenamento de modelos treinados
    │   ├── insights/engine.py          # Geração de insights
    │   ├── services/                   # Placeholder para serviços futuros
    │   └── storage/                    # Placeholder para abstração de storage
    │
    ├── models/                         # Modelos ML treinados (.pkl)
    │   ├── pf_pj_classifier.pkl        # Random Forest PF/PJ
    │   ├── feature_encoders.pkl        # Encoders de features
    │   └── feature_scaler.pkl          # Scaler de features
    │
    ├── data/                           # Dados de treinamento
    │   ├── training_dataset_pf_pj.csv
    │   ├── training_dataset_pf_pj.parquet
    │   └── transactions.duckdb
    │
    ├── scripts/
    │   ├── apply_migrations.py
    │   ├── create_labeled_dataset.py
    │   ├── train_pf_pj_classifier.py
    │   ├── validate_pf_pj_classifier.py
    │   ├── pf_pj_fallback_rules.py
    │   └── test_manual_override.py
    │
    ├── docs/
    │   ├── pf_pj_validation_report.md
    │   ├── pf_pj_validation_results.json
    │   └── f4_complete_test_results.json
    │
    └── tests/
        ├── conftest.py
        ├── test_cashflow_projection.py
        ├── test_classifier.py
        ├── test_etl_ingestor.py
        ├── test_f4_complete.py
        ├── test_pipeline_integration.py
        ├── test_pluggy_integration.py
        ├── test_recurring_detector.py
        ├── test_runner.py
        ├── test_runner_import.py
        ├── test_safe_to_spend.py
        ├── test_shadow_invoice.py
        └── test_shadow_pipeline.py
```

---

## 4. ARQUITETURA DO SISTEMA

```
                        ┌─────────────────────────────────────────────────┐
                        │                   USUÁRIO / FRONTEND              │
                        └───────────────────────┬─────────────────────────┘
                                                 │ HTTP
                        ┌────────────────────────▼─────────────────────────┐
                        │               FastAPI Application                  │
                        │         app/main.py  |  app/api/v1/router.py      │
                        └──────────┬────────────────────────────────────────┘
                                   │
              ┌────────────────────┼───────────────────────┐
              ▼                    ▼                        ▼
     ┌─────────────────┐  ┌───────────────────┐  ┌────────────────────┐
     │   ETL Pipeline   │  │  Cashflow Engine  │  │   Agent (F3)       │
     │  (5 estágios)   │  │  projector.py     │  │  LangGraph         │
     └────────┬────────┘  └────────┬──────────┘  └─────────┬──────────┘
              │                    │                         │
     ┌────────▼──────┐    ┌────────▼──────────┐    ┌────────▼──────────┐
     │   Ingestor    │    │  SafeToSpend      │    │  Claude AI API    │
     │   Classifier  │    │  Projector        │    │  (Anthropic)      │
     │   PF/PJ ML    │    └───────────────────┘    └───────────────────┘
     │   Recurrence  │
     │   ShadowInv.  │
     │   Loader      │
     └────────┬──────┘
              │
     ┌────────▼──────────────────────────────┐
     │              Data Layer                │
     │   DuckDB (local)  │  PostgreSQL (prod) │
     │   Polars DataFrames                    │
     └───────────────────────────────────────┘
              │
     ┌────────▼──────────────────────────────┐
     │           External Integrations        │
     │   Pluggy Open Finance API              │
     │   AWS S3 (raw events, planejado)       │
     │   Redis (cache, planejado)             │
     └───────────────────────────────────────┘
```

### Padrões Arquiteturais Utilizados

- **Strategy Pattern** — Normalização por banco (`bank_strategy/`)
- **Pipeline Pattern** — ETL em 5 estágios sequenciais
- **Repository Pattern** — Abstração de acesso a dados (`db/`)
- **Domain-Driven Design** — Separação clara de domínio financeiro (`domain/`, `engines/`)
- **Agent Pattern** — LangGraph para agente financeiro com estado

---

## 5. PIPELINE ETL (5 ESTÁGIOS)

### Visão Geral do Fluxo

```
Pluggy API (JSON)
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│  ESTÁGIO 1: INGESTOR (etl/ingestor.py)                      │
│  - Normaliza JSON do Pluggy → Polars DataFrame               │
│  - Estratégias específicas por banco (Nubank, Itaú, Inter)  │
│  - Deduplicação (hash-based)                                 │
│  - Tratamento de campos ausentes                             │
│  Output: DataFrame limpo                                     │
└─────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│  ESTÁGIO 2: CLASSIFIER (etl/classifier.py)                  │
│  - Normalização de texto (acentos, maiúsculas/minúsculas)   │
│  - Matching por palavras-chave por categoria                 │
│  - Scoring de confiança (% cobertura de texto)              │
│  - Fallback para "Outros"                                    │
│  Categorias: Alimentação, Transporte, Saúde, Educação,      │
│              Lazer, Moradia, Vestuário, Transferências,      │
│              Investimentos, Outros                           │
│  Output: DataFrame + coluna 'category' + 'ml_confidence'    │
└─────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│  ESTÁGIO 2.5: PF/PJ CLASSIFIER (etl/pf_pj_classifier.py)   │
│  - Extração de features (texto, valor, padrões temporais)   │
│  - Predição via Random Forest (modelo treinado .pkl)        │
│  - Fallback para regras se confiança < threshold            │
│  Regras de fallback:                                         │
│    1. Keywords (EMPRESA, LTDA, MEI, CNPJ...)                │
│    2. Threshold de valor                                     │
│    3. Padrões de merchant                                    │
│    4. Default: UNCERTAIN                                     │
│  Output: DataFrame + coluna 'pf_pj_label' (PF/PJ/UNCERTAIN) │
└─────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│  ESTÁGIO 3: RECURRING DETECTOR (etl/recurring_detector.py)  │
│  - Análise de série temporal                                 │
│  - Verificação de estabilidade de valor                      │
│  - Verificação de consistência de merchant                   │
│  - Scoring de confiança por padrão                          │
│  Detecta: assinaturas mensais, pagamentos fixos,            │
│           salários, parcelas (01/10, 02/10...)               │
│  Output: Lista de padrões recorrentes                        │
└─────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│  ESTÁGIO 4: SHADOW INVOICES (etl/shadow_invoices.py)        │
│  - Projeta cada padrão 30+ dias para frente                 │
│  - Cria eventos sintéticos "shadow"                         │
│  - Marca níveis de confiança                                 │
│  - Rastreia origem (assinatura vs parcela vs padrão)        │
│  Output: DataFrame com obrigações futuras projetadas         │
└─────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│  ESTÁGIO 5: LOADER (etl/loader.py)                         │
│  - Persiste no DuckDB (cache local)                         │
│  - Persiste no PostgreSQL (produção, se configurado)        │
│  - Rastreia métricas de qualidade                           │
│  - Atualiza status dos dados (TRUSTED/DEGRADED/UNTRUSTED)   │
│  Output: Confirmações de persistência                        │
└─────────────────────────────────────────────────────────────┘
```

### Estratégias por Banco (`bank_strategy/`)

| Banco | Arquivo | Tratamentos Especiais |
|-------|---------|----------------------|
| Padrão | `default.py` | Normalização genérica |
| Nubank | `nubank.py` | Formatação específica de descrições |
| Itaú | `itau.py` | Formatação específica de descrições |
| Inter | `inter.py` | Formatação específica de descrições |

### Métricas de Qualidade Rastreadas

- Total de registros processados
- Duplicatas removidas
- Score de qualidade (0–1)
- Registros por status (TRUSTED / DEGRADED / UNTRUSTED)
- Tempo de processamento

---

## 6. FUNCIONALIDADES IMPLEMENTADAS

### FUNCIONALIDADE 1 — CORE ENGINE ✅ (100%)

**Propósito:** Motor central de análise financeira — o coração da plataforma.

**Status:** Produção ready | 10/10 testes passando | ~4.000 linhas

#### O que foi implementado:

**1.1 Ingestão e Validação de Transações**
- Integração Pluggy Open Finance (mock + real)
- Validação tolerante em batch via Pydantic
- Normalização específica por banco
- Detecção e remoção de duplicatas

**1.2 Pipeline ETL Completo (5 estágios)**
Descrito em detalhes na seção 5 acima.

**1.3 Projeção de Fluxo de Caixa**
- Simulação diária (30+ dias)
- Avaliação de nível de risco por dia (LOW / MEDIUM / HIGH / CRITICAL)
- Rastreamento de saldo mínimo projetado
- Explicação narrativa para cada dia projetado

**1.4 Calculador Safe-to-Spend**
- Determina margem de gastos com buffer de 15%
- Considera shadow invoices (obrigações futuras)
- Gasto diário ajustado ao risco
- Previne déficits financeiros

**1.5 Qualidade de Dados e Persistência**
- Métricas de qualidade em tempo real
- Cache no DuckDB
- Arquitetura pronta para PostgreSQL
- Rastreamento de status dos dados

---

### FUNCIONALIDADE 4 — SEPARADOR PF/PJ ✅ (90%)

**Propósito:** Separar automaticamente transações pessoais (PF) das empresariais (PJ).

**Status:** Modelo ML treinado, testes 100% passando, integração em andamento.

#### O que foi implementado:

**4.1 Modelo Random Forest**
- Treinado com dataset rotulado (`training_dataset_pf_pj.csv`)
- Split 80/20 treino/teste
- Serializado em `pf_pj_classifier.pkl`
- Artefatos: encoders + scaler

**4.2 Features Extraídas**
- Descrição da transação (features de texto)
- Nome do merchant
- Magnitude do valor
- Padrões temporais (dia da semana, hora)
- Categoria (do classificador)
- Padrões históricos

**4.3 Sistema de Fallback Multicamadas**
1. Regra por keywords (`EMPRESA`, `LTDA`, `MEI`, `CNPJ`)
2. Threshold de valor
3. Padrões de merchant
4. Default para `UNCERTAIN` se nenhuma regra bate

**4.4 API de Classificação em Batch**
- Endpoint para classificação em lote
- Override manual por contexto
- Rastreamento de confiança por transação

**4.5 Validação**
- Relatório completo: `docs/pf_pj_validation_report.md`
- Resultados JSON: `docs/pf_pj_validation_results.json`
- Teste completo: `tests/test_f4_complete.py`

---

### FUNCIONALIDADE 2 — OTIMIZADOR 📋 (0% — Planejado)

**Propósito:** Análise e otimização de cartões de crédito.

**Dependência:** F1 completa ✅

**Features planejadas:**
- Análise e score de cartões
- Recomendações de consolidação
- Análise de anuidade vs benefícios
- Algoritmo de seleção de cartão ótimo
- Endpoint: `GET /analyze_cards/{user_id}`

---

### FUNCIONALIDADE 3 — ARQUITETO 📋 (0% código — Especificação completa)

**Propósito:** Agente LLM para recomendações financeiras contextualizadas.

**Dependência:** F1 completa ✅, chave Claude API

**Especificação:** `FUNCIONALIDADE_3.md` (100% escrito)

**Features planejadas (3 fases):**

| Fase | Conteúdo |
|------|---------|
| **MVP** | Calculadores determinísticos (NPV, IRR, financiamento) |
| **Fase 2** | Simulação Monte Carlo + calculadora consórcio |
| **Fase 3** | Hardening, performance, produção |

**Infraestrutura já preparada:**
- `agent/graph.py` — Grafo de estado LangGraph
- `agent/state.py` — FinancialState
- `agent/nodes/` — Nós de forecast, recorrência e explicações
- `api/v1/routes/chat.py` — Endpoint do agente

---

## 7. API — ENDPOINTS COMPLETOS

### Base URL: `http://localhost:8000`

### Saúde & Sistema

| Endpoint | Método | Resposta |
|----------|--------|----------|
| `/health` | GET | `{"status": "ok"}` |
| `/version` | GET | `{"version": "0.1.0"}` |
| `/docs` | GET | Swagger UI |
| `/redoc` | GET | ReDoc |

### Análise Financeira Core (F1)

| Endpoint | Método | Query Params | Propósito |
|----------|--------|-------------|-----------|
| `/api/v1/forecast/{user_id}` | GET | `?horizon_days=30` | Forecast completo 30 dias |
| `/api/v1/shadow_invoice/{user_id}` | GET | — | Lista de obrigações futuras |
| `/api/v1/shadow_invoice/{user_id}/summary` | GET | — | Resumo das shadow invoices |
| `/api/v1/alerts/{user_id}` | GET | — | Alertas ativos do usuário |
| `/api/v1/alerts/{user_id}/{alert_id}` | DELETE | — | Dispensar alerta |
| `/api/v1/reconnect/{user_id}` | POST | — | URL de reconexão Pluggy |

### Gestão de Transações

| Endpoint | Método | Body | Propósito |
|----------|--------|------|-----------|
| `/api/v1/transactions/webhook` | POST | WebhookPayload | Ingestão via webhook |
| `/api/v1/transactions/{user_id}` | GET | — | Buscar transações armazenadas |
| `/api/v1/transactions/context/override` | POST | ContextOverride | Override manual PF/PJ |

### Dashboard & Desenvolvimento

| Endpoint | Método | Propósito |
|----------|--------|-----------|
| `/api/v1/bank_simulation` | GET | Dados bancários mock |
| `/api/v1/dashboard/*` | GET | Dados de dashboard |
| `/api/v1/pluggy_test` | GET | Testes de integração Pluggy |

---

## 8. SCHEMAS E MODELOS DE DADOS

### TransactionWebhook (Input)
```python
class TransactionWebhook(BaseModel):
    id: str                      # ID único da transação
    date: date                   # Data da transação
    amount: float                # Valor (negativo = débito)
    description: str             # Descrição original
    merchant: Optional[str]      # Nome do merchant
    balance: Optional[float]     # Saldo após transação
    currency: str = "BRL"        # Moeda
    status: str = "POSTED"       # Status (POSTED/PENDING)
    type: str = "DEBIT"          # Tipo (DEBIT/CREDIT)
```

### TransactionBatchResult
```python
class TransactionBatchResult(BaseModel):
    total_received: int          # Total recebido
    total_valid: int             # Total válido
    total_rejected: int          # Total rejeitado
    rejection_rate: float        # Taxa de rejeição (0-1)
    valid_transactions: List     # Transações válidas
    rejection_reasons: Dict      # Motivos de rejeição agrupados
```

### ForecastResponse (Output Principal)
```python
class ForecastResponse(BaseModel):
    user_id: str
    generated_at: datetime
    financial_health: FinancialHealthSchema  # Perfil e score
    cashflow: CashflowSummary               # Resumo do fluxo
    safe_to_spend: SafeToSpendResult        # Margem de gastos
    shadow_invoices: ShadowInvoiceSummary   # Obrigações futuras
    monthly_forecasts: List[DailyForecast]  # Projeções diárias
```

### FinancialHealthSchema
```python
class FinancialHealthSchema(BaseModel):
    profile_type: ProfileType    # MUITO_CONSERVADOR/CONSERVADOR/EQUILIBRADO/AGRESSIVO/MUITO_AGRESSIVO
    health_score: int            # Score 0-100
    savings_rate: float          # Taxa de poupança
    total_income: float          # Renda total
    total_expenses: float        # Total de despesas
    monthly_avg_expenses: float  # Média mensal
    trend: str                   # ESTÁVEL/MELHORA/PIORA
```

### SafeToSpendResult
```python
class SafeToSpendResult(BaseModel):
    current_balance: float           # Saldo atual
    min_projected_balance: float     # Saldo mínimo projetado
    total_shadow_invoices: float     # Impacto total de shadow invoices
    safety_buffer: float             # Buffer de segurança (15%)
    safe_to_spend_total: float       # Total disponível para gastar
    safe_to_spend_daily: float       # Disponível por dia
    days: int                        # Horizonte em dias
    risk_level: RiskLevel            # LOW/MEDIUM/HIGH/CRITICAL
```

### ShadowInvoiceResponse
```python
class ShadowInvoiceResponse(BaseModel):
    invoices: List[ShadowInvoice]    # Lista de obrigações
    total_count: int
    total_monthly_impact: float
    subscriptions_count: int
    installments_count: int
```

### AlertsResponse
```python
class AlertsResponse(BaseModel):
    user_id: str
    alerts: List[Alert]
    total_count: int

class Alert(BaseModel):
    id: str
    type: str          # TOKEN_EXPIRY, NEGATIVE_BALANCE, HIGH_SPENDING...
    severity: str      # WARNING/ERROR/INFO
    message: str
    created_at: datetime
```

### Enums

```python
class ProfileType(str, Enum):
    MUITO_CONSERVADOR = "MUITO_CONSERVADOR"
    CONSERVADOR = "CONSERVADOR"
    EQUILIBRADO = "EQUILIBRADO"
    AGRESSIVO = "AGRESSIVO"
    MUITO_AGRESSIVO = "MUITO_AGRESSIVO"

class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class DataStatus(str, Enum):
    TRUSTED = "TRUSTED"
    DEGRADED = "DEGRADED"
    UNTRUSTED = "UNTRUSTED"
```

---

## 9. COMPONENTES ML

### 9.1 Classificador de Transações (CatBoost + Regras)

**Arquivo:** `etl/classifier.py`
**Modo:** Rule-based com scoring de confiança (CatBoost planejado)

**Categorias:**

| Categoria | Keywords de Exemplo |
|-----------|---------------------|
| Alimentação | restaurante, mercado, ifood, delivery |
| Transporte | uber, 99, combustivel, estacionamento |
| Saúde | farmacia, hospital, clinica, plano de saude |
| Educação | escola, faculdade, curso, livraria |
| Lazer | cinema, teatro, netflix, spotify |
| Moradia | aluguel, condominio, agua, luz, gas |
| Vestuário | roupa, calcado, moda, shopping |
| Transferências | pix, ted, doc, transferencia |
| Investimentos | corretora, fundo, acao, tesouro |
| Outros | (fallback) |

### 9.2 Classificador PF/PJ (Random Forest)

**Arquivos:** `etl/pf_pj_classifier.py`, `models/pf_pj_classifier.pkl`

**Pipeline de Features:**
```
Texto da transação → TF-IDF / embeddings
Merchant name      → Label encoding
Valor              → Normalização
Dia da semana      → One-hot encoding
Hora               → Bucketização
Categoria          → Label encoding
       │
       ▼
Random Forest Classifier
       │
       ▼
PF | PJ | UNCERTAIN (com score de confiança)
```

**Dados de Treinamento:**
- Arquivo: `data/training_dataset_pf_pj.csv`
- Formato Parquet também disponível
- Split: 80% treino / 20% teste

### 9.3 Detector de Recorrência

**Arquivo:** `etl/recurring_detector.py`

**Algoritmo:**
1. Agrupar transações por merchant + valor aproximado
2. Verificar espaçamento temporal (7/14/30 dias)
3. Verificar estabilidade do valor (±5%)
4. Calcular score de confiança
5. Retornar padrões com confiança > threshold

**Tipos detectados:**
- Assinaturas mensais (Netflix, Spotify, Amazon Prime)
- Pagamentos fixos (aluguel, condomínio)
- Salário (receitas periódicas)
- Parcelas (ex: `01/12`, `02/12`, ..., `12/12`)
- Impostos e taxas periódicas

### 9.4 Gerador de Shadow Invoices

**Arquivos:** `etl/shadow_invoices.py`, `etl/shadow_invoices/`

**Sub-detectores:**
- `subscription_detector.py` — Assinaturas recorrentes
- `installment_detector.py` — Parcelas de compras

**Algoritmo de Projeção:**
1. Para cada padrão detectado
2. Calcular próximas datas (baseado na frequência)
3. Criar eventos sintéticos com data futura
4. Atribuir tipo (SUBSCRIPTION / INSTALLMENT / PATTERN)
5. Registrar confiança e origem

---

## 10. MOTORES DE CÁLCULO FINANCEIRO

### 10.1 CashflowProjector

**Arquivo:** `cashflow/projector.py`

**Algoritmo:**
```python
def project(transactions, shadow_invoices, horizon_days=30):
    balance = current_balance
    daily_projections = []

    for day in range(1, horizon_days + 1):
        date = today + timedelta(days=day)

        # Agregar transações reais esperadas
        day_transactions = transactions.filter(date=date)

        # Agregar shadow invoices vencendo nesse dia
        day_shadows = shadow_invoices.filter(date=date)

        # Calcular balanço projetado
        balance += sum(day_transactions.amounts) + sum(day_shadows.amounts)

        # Determinar risco
        risk = calculate_risk(balance, min_threshold)

        # Criar registro diário
        daily_projections.append(DailyForecast(
            date=date,
            projected_balance=balance,
            risk_level=risk,
            events=[...],
            explanation=generate_explanation(...)
        ))

    return daily_projections
```

### 10.2 SafeToSpendCalculator

**Arquivo:** `cashflow/safe_to_spend.py`

**Fórmula:**
```
saldo_minimo_projetado = min(projeções diárias de saldo)
buffer_segurança = saldo_minimo_projetado × 0.15   (15%)
impacto_shadow = sum(shadow_invoices do período)
safe_to_spend_total = saldo_atual - buffer_segurança - |impacto_shadow|
safe_to_spend_diário = safe_to_spend_total / horizon_days

risk_level:
  LOW      → safe_to_spend_total > 30% do saldo
  MEDIUM   → safe_to_spend_total entre 10% e 30%
  HIGH     → safe_to_spend_total entre 0% e 10%
  CRITICAL → safe_to_spend_total < 0
```

### 10.3 Calculadoras Financeiras (F3)

**Arquivo:** `engines/calculator.py`

**Implementadas / Planejadas:**
- NPV (Valor Presente Líquido)
- IRR (Taxa Interna de Retorno)
- Análise financiamento vs. consórcio vs. poupança
- Simulação Monte Carlo (F3 Fase 2)

---

## 11. TESTES E COBERTURA

### Status: ✅ 100% PASSANDO (12/12 arquivos)

| Arquivo de Teste | Propósito | Status |
|-----------------|-----------|--------|
| `test_cashflow_projection.py` | Projetor de fluxo de caixa | ✅ PASS |
| `test_classifier.py` | Classificador de transações | ✅ PASS |
| `test_etl_ingestor.py` | Ingestor ETL | ✅ PASS |
| `test_f4_complete.py` | Classificador PF/PJ completo | ✅ PASS |
| `test_pipeline_integration.py` | Pipeline ponta a ponta | ✅ PASS |
| `test_pluggy_integration.py` | Integração Pluggy (mock) | ✅ PASS |
| `test_recurring_detector.py` | Detecção de recorrência | ✅ PASS |
| `test_runner.py` | NexaRunner orquestrador | ✅ PASS |
| `test_runner_import.py` | Validação de imports | ✅ PASS |
| `test_safe_to_spend.py` | Calculador safe-to-spend | ✅ PASS |
| `test_shadow_invoice.py` | Geração de shadow invoices | ✅ PASS |
| `test_shadow_pipeline.py` | Pipeline de shadow invoices | ✅ PASS |

### Áreas Cobertas pelos Testes

- ✅ Ingestão e normalização de dados
- ✅ Classificação de transações (10 categorias)
- ✅ Separação PF/PJ (ML + fallback)
- ✅ Detecção de padrões recorrentes
- ✅ Geração de shadow invoices
- ✅ Projeção de fluxo de caixa
- ✅ Cálculo de safe-to-spend
- ✅ Validação de endpoints API
- ✅ Validação de schemas Pydantic
- ✅ Integração ponta a ponta do pipeline

### Como Rodar os Testes

```bash
cd backend

# Todos os testes
pytest tests/ -v

# Arquivo específico
pytest tests/test_f4_complete.py -v
pytest tests/test_cashflow_projection.py -v

# Com coverage
pytest tests/ --cov=app --cov-report=html
```

---

## 12. CONFIGURAÇÃO E DEPLOY

### Variáveis de Ambiente

```bash
# backend/.env

# Pluggy Open Finance
PLUGGY_CLIENT_ID=seu_client_id
PLUGGY_CLIENT_SECRET=seu_client_secret
PLUGGY_BASE_URL=https://api.pluggy.ai   # ou sandbox

# Banco de dados
DATABASE_URL=postgresql://user:pass@localhost:5432/nexa

# Redis (opcional)
REDIS_URL=redis://localhost:6379

# AWS S3 (opcional)
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=yyy
AWS_S3_BUCKET=nexa-raw-events

# Aplicação
LOG_LEVEL=INFO      # ou DEBUG
APP_MODE=dev        # ou prod
```

### Execução Local

```bash
# Instalar dependências
cd backend
pip install -r requirements.txt
# ou
poetry install

# Rodar aplicação
python -m uvicorn app.main:app --reload --host localhost --port 8000

# Acessar
# API: http://localhost:8000/api/v1/
# Swagger: http://localhost:8000/docs
# ReDoc: http://localhost:8000/redoc
# Health: http://localhost:8000/health
```

### Deploy em Produção

```bash
# 4 workers para produção
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Scripts Utilitários

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
python test_api.py
```

---

## 13. ROADMAP E PRÓXIMOS PASSOS

### Concluído ✅

- [x] **F1 — Core Engine** (100%)
  - Ingestão de transações via Pluggy
  - Pipeline ETL 5 estágios
  - Projeção de fluxo de caixa 30 dias
  - Calculador safe-to-spend
  - 6 endpoints de API
  - 12 arquivos de teste
- [x] **F4 — Separador PF/PJ** (90%)
  - Modelo Random Forest treinado
  - Sistema de fallback por regras
  - Testes 100% passando
  - Relatório de validação

### Em Andamento 🔄

- [ ] **F4** — Integração final ao pipeline principal
- [ ] Integração PostgreSQL em produção

### Planejado 📋

- [ ] **F2 — Otimizador** — Análise e otimização de cartões
- [ ] **F3 — Arquiteto** — Agente LLM com Claude AI
  - Fase 1: Calculadoras NPV/IRR/financiamento
  - Fase 2: Monte Carlo + consórcio
  - Fase 3: Hardening & produção
- [ ] Cache Redis
- [ ] Storage S3 para eventos brutos
- [ ] Autenticação JWT
- [ ] Rate limiting
- [ ] Configuração CORS
- [ ] Monitoramento e alertas
- [ ] Deploy Kubernetes
- [ ] CI/CD pipeline

---

## 14. DECISÕES DE ARQUITETURA

### Princípios de Design

| Princípio | Descrição |
|-----------|-----------|
| **Determinístico > Estatístico** | Projeções baseadas em padrões detectados, não modelos probabilísticos |
| **Explicável** | Todo cálculo inclui narrativa/explicação legível |
| **Resiliente** | Multi-layer fallback: ML → Regras → Defaults |
| **Modular** | Separação clara de concerns: ETL, cashflow, API, agents |
| **Auditável** | Todas as transformações rastreadas com métricas |

### Por que essas tecnologias?

| Decisão | Alternativa Descartada | Motivo |
|---------|------------------------|--------|
| **Polars** em vez de Pandas | Pandas | 10x mais rápido, melhor paralelização |
| **DuckDB** em vez de SQLite | SQLite | Otimizado para OLAP, queries analíticas |
| **Pydantic v2** | Dataclasses / marshmallow | Type-safe com auto-validação, performance |
| **CatBoost** para categorização | Naive Bayes | Suporte nativo a features categóricas |
| **Random Forest** para PF/PJ | Deep learning | Interpretável, treina com poucos dados |
| **LangGraph** em vez de LangChain puro | Agentes sem estado | Orquestração com estado, mais controlável |

### Pontos de Integração

| Serviço | Tipo | Arquivo | Status |
|---------|------|---------|--------|
| Pluggy Open Finance | HTTP API | `integrations/open_finance/pluggy.py` | Mock ativo, real configurável |
| Claude AI (Anthropic) | LLM API | `agent/nodes/` | Infraestrutura pronta (F3) |
| BACEN / ANBIMA | HTTP API | — | Planejado |
| PostgreSQL | SQL | `db/session.py` | Arquitetura pronta |
| Redis | Cache | — | Planejado |
| AWS S3 | Object Storage | — | Planejado |

### Limitações Conhecidas

1. Pluggy apenas mock (sem conexões bancárias reais ainda)
2. Contexto single-user (sem multi-tenant)
3. Cartões de crédito apenas na F2 (não incluído no cashflow atual)
4. Sem histórico para comparação em primeira execução
5. Migrações manuais (sem auto-migrate na inicialização)

---

*Documentação gerada em 2026-02-16 por análise automatizada de todo o codebase.*
