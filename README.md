<div align="center">

# NEXA AI

### **Seu Dinheiro. Seu Lado.**

*O advogado financeiro que os bancos não querem que você tenha.*

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Tests](https://img.shields.io/badge/Tests-414%20passing-success?style=flat-square)](tests/)
[![Coverage](https://img.shields.io/badge/Coverage-89%25-brightgreen?style=flat-square)](docs/PF_PJ_VALIDATION_REPORT.md)
[![License](https://img.shields.io/badge/License-Proprietary-red?style=flat-square)](LICENSE)

[Início Rápido](#-início-rápido) •
[Funcionalidades](#-funcionalidades) •
[API](#-endpoints-da-api) •
[Arquitetura](#-arquitetura-técnica) •
[Documentação](#-documentação)

---

</div>

## 📋 Índice

<details>
<summary><strong>Clique para expandir</strong></summary>

- [Visão Geral](#-visão-geral)
- [O Problema](#-o-problema)
- [A Solução](#-a-solução)
- [Início Rápido](#-início-rápido)
- [Funcionalidades](#-funcionalidades)
- [Diferencial Competitivo](#-diferencial-competitivo)
- [Métricas Analisadas](#-métricas-analisadas)
- [Arquitetura Técnica](#-arquitetura-técnica)
- [Stack Tecnológica](#-stack-tecnológica)
- [Estrutura do Projeto](#-estrutura-do-projeto)
- [Endpoints da API](#-endpoints-da-api)
- [Agente de IA](#-agente-de-ia)
- [Banco de Dados](#-banco-de-dados)
- [Testes](#-testes)
- [Exemplos de Uso](#-exemplos-de-uso)
- [Modelo de Negócio](#-modelo-de-negócio)
- [Estratégias de Crescimento](#-estratégias-de-crescimento)
- [Roadmap](#-roadmap)
- [Documentação](#-documentação)
- [Status do Projeto](#-status-do-projeto)

</details>

---

## 🎯 Visão Geral

A **Nexa AI** é uma plataforma de inteligência financeira pessoal que combina **Open Finance**, **Machine Learning** e **IA conversacional** para revelar quanto os bancos lucram com você — e transformar essa informação em ações concretas de economia, recuperação e otimização.

> **Não somos outro banco. Somos o advogado contra todos os bancos.**

---

## 💸 O Problema

O brasileiro médio:

| Perda Anual | Causa |
|:---:|:---|
| **R$ 800** | Tarifas bancárias evitáveis |
| **R$ 2.000** | Uso do cartão errado |
| **R$ 3.500** | Lucro oculto do banco sobre o cliente |

**Total: R$ 6.300/ano perdidos sem perceber.**

---

## ✅ A Solução

```
30 segundos  →  Conectamos todos os seus bancos via Open Finance
60 segundos  →  Mostramos onde seu dinheiro está sendo drenado
Instantes    →  O agente de IA negocia para você recuperar esse dinheiro
```

Com **base legal**, **carta gerada automaticamente** e **probabilidade de sucesso calculada**.

---

## 🚀 Início Rápido

### Pré-requisitos

| Requisito | Versão |
|:---|:---|
| Python | 3.11+ |
| PostgreSQL | 16 |
| Redis | 5.0+ (opcional) |
| Node.js | 20+ (frontend) |

### Instalação com Docker Compose

```bash
# Clone o repositório
git clone https://github.com/nexa-ai/nexa.git
cd nexa

# Configure as variáveis de ambiente
cp backend/.env.example backend/.env
# Edite backend/.env com suas credenciais

# Inicie os serviços
docker-compose up --build
```

| Serviço | URL |
|:---|:---|
| API | http://localhost:8000 |
| Frontend | http://localhost:3000 |
| Swagger UI | http://localhost:8000/docs |

### Instalação Manual

<details>
<summary><strong>Backend</strong></summary>

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --port 8000 --reload
```

</details>

<details>
<summary><strong>Frontend</strong></summary>

```bash
cd frontend-react
npm install
npm run dev
```

</details>

### Variáveis de Ambiente

```env
# Obrigatórios
DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/nexa
SECRET_KEY=sua-chave-secreta-forte-aqui

# LLM (escolha um)
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Open Finance
PLUGGY_CLIENT_ID=seu_client_id
PLUGGY_CLIENT_SECRET=seu_client_secret

# Opcionais
REDIS_URL=redis://localhost:6379/0
FRONTEND_BASE_URL=http://localhost:3000
```

> 📄 Veja [docs/SETUP_LOCAL.md](docs/SETUP_LOCAL.md) para configuração completa.

---

## ⚡ Funcionalidades

### Verticais de Valor

A Nexa opera em **quatro dimensões**, cada uma atacando um ponto onde o sistema financeiro extrai valor do usuário:

<table>
<tr>
<td width="50%">

#### 🔍 Revelar o que está oculto

- **Raio-X de Custos** — Detecta tarifas invisíveis, serviços não contratados e cobranças em duplicidade
- **Transparência Radical** — Exibe quanto cada banco lucrou com o usuário no último ano
- **Detector de Venda Casada** — Identifica seguros e pacotes embutidos ilegalmente (art. 39 CDC)

</td>
<td width="50%">

#### 💰 Recuperar o que foi perdido

- **Recuperador de Cobranças** — Gera carta de contestação com base legal e correção monetária
- **Monitor de Direitos** — Consulta SVR, FGTS, PIS/PASEP automaticamente
- **Detector de Juros Abusivos** — Compara taxas com médias BACEN + jurisprudência STJ

</td>
</tr>
<tr>
<td width="50%">

#### 📈 Otimizar cada real

- **Modo Compra Inteligente** — Qual cartão usar, parcelar ou não, Pix ou crédito
- **Card Optimizer** — Ranqueia 2.000+ cartões pelo perfil real de gastos
- **Nexa Architect** — Simula financiamento vs consórcio vs investimento com Monte Carlo

</td>
<td width="50%">

#### 🛡️ Proteger no longo prazo

- **Safe-to-Spend** — Margem diária de gastos em tempo real
- **Shadow Invoice Detector** — Parcelas e assinaturas que comprometem o caixa futuro
- **Score Nexa** — Score financeiro com tendência 30/90 dias

</td>
</tr>
</table>

### Catálogo de Funcionalidades

#### Motor Core

| ID | Funcionalidade | Status |
|:---|:---|:---:|
| F1 | ETL Pipeline 8 estágios + Cashflow 30 dias + Safe-to-Spend | ✅ |
| F2 | Card Optimizer — 2.000+ cartões, multi-card, custo de oportunidade | ✅ |
| F3 | Nexa Architect — Financiamento vs Consórcio vs Investimento, Monte Carlo | ✅ |
| F4 | PF/PJ Classifier — Random Forest + regras, relatório fiscal MEI | ✅ |
| F5 | Raio-X de Custos — Análise de tarifas, benchmark 16 bancos | ✅ |

#### Experiência e Engajamento

| ID | Funcionalidade | Status |
|:---|:---|:---:|
| MX.1 | Health Score com tendência e histórico temporal | ✅ |
| MX.2 | Metas Financeiras — CRUD, projeção de prazo, progresso | ✅ |
| MX.3 | Notificações Proativas — burn rate, anomalias, oportunidades | ✅ |
| MX.4 | Peer Comparison — benchmarks IBGE/POF por faixa de renda | ✅ |
| F7 | Modo Compra Inteligente — qual cartão usar, parcelar ou não | ✅ |
| F11 | Agente Conversacional — ReAct com 13 ferramentas financeiras | ✅ |
| F13 | Negociador — scripts gerados por Claude para negociar com banco | ✅ |

<details>
<summary><strong>📅 Roadmap: Funcionalidades Futuras</strong></summary>

#### Piloto Automático (Fase 2)

| ID | Funcionalidade |
|:---|:---|
| F6 | Sweep automático — move sobra para investimento |
| F8 | Radar de Produtos — monitora 200+ instituições |
| F9 | Portabilidade de Crédito Assistida |
| F10 | Pagamento Otimizado |
| F12 | Modo Família — até 4 membros |

#### Transparência e Defesa (Fase 3)

| ID | Funcionalidade |
|:---|:---|
| D1 | Detector de Venda Casada (art. 39 CDC) |
| D2 | Recuperador de Cobranças Indevidas |
| D3 | Detector de Juros Abusivos |
| D5 | Central de Evidências (PROCON/juizado) |

#### Inteligência Fiscal (Fase 3)

| ID | Funcionalidade |
|:---|:---|
| T1 | Otimizador de IR em Tempo Real |
| T2 | Modo Imposto Zero — LCI/LCA, debêntures |
| T3 | Monitor de Direitos Esquecidos |

</details>

---

## 🏆 Diferencial Competitivo

### Matriz Competitiva

| Dimensão | Nexa | Bancos | Apps de Controle | Comparadores |
|:---|:---:|:---:|:---:|:---:|
| **Modelo de receita** | Assinatura do usuário | Tarifas + spread | Freemium / comissão | Comissão de banco |
| **Neutralidade** | ✅ Total | ❌ Conflito | ⚠️ Parcial | ❌ Conflito |
| **Ação automática** | ✅ Contesta, negocia | ❌ | ❌ Só visualiza | ❌ Só compara |
| **Open Finance nativo** | ✅ Multi-banco | ⚠️ Só o próprio | ⚠️ Manual | ⚠️ Parcial |
| **Base legal integrada** | ✅ CDC, BACEN, STJ | ❌ | ❌ | ❌ |
| **IA conversacional** | ✅ 13 ferramentas | ❌ | ❌ | ❌ |
| **Score alternativo** | ✅ Fluxo de caixa real | ⚠️ Score próprio | ❌ | ❌ |

### Por que não é copiável

> **1. Neutralidade estrutural** — Bancos nunca vão recomendar o concorrente. Apps que ganham comissão não podem ser neutros. A Nexa cobra do usuário — a única estrutura que garante trabalhar exclusivamente para quem paga.

> **2. Flywheel de dados** — Cada novo usuário melhora o benchmark de tarifas e o detector de venda casada. Meses de dados históricos que nenhum concorrente pode replicar retroativamente.

> **3. Complexidade técnica** — 14 módulos de análise, ETL de 8 estágios, 2.000+ cartões, simulador Monte Carlo, agente ReAct com 13 ferramentas. Não é um wrapper de API.

> **4. Confiança do usuário** — Uma vez que o usuário confia na Nexa como seu advogado, o custo de troca é altíssimo.

> **5. Nexa Score como bureau alternativo** — Com massa crítica, o Score Nexa baseado em fluxo de caixa real vira um selo de qualidade que força bancos a baixarem juros. Nenhum concorrente tem os dados de Open Finance para replicar isso.

---

## 📊 Métricas Analisadas

A Nexa calcula e monitora **40+ indicadores financeiros** individuais.

<details>
<summary><strong>Saúde Financeira</strong></summary>

| Métrica | Descrição |
|:---|:---|
| Safe-to-Spend diário | Margem segura de gastos considerando obrigações futuras |
| Burn Rate | Taxa de consumo de renda mensal por categoria |
| Score Nexa | Score financeiro composto (0-100) com tendência 30/90 dias |
| Shadow Invoices | Valor total de compromissos futuros não vencidos |
| Runway financeiro | Meses de sobrevivência com reservas atuais |
| Savings Rate | Percentual real da renda sendo poupado |
| Liquidity Ratio | Ativos líquidos sobre compromissos de curto prazo |

</details>

<details>
<summary><strong>Fluxo de Caixa e Previsão</strong></summary>

| Métrica | Descrição |
|:---|:---|
| Cashflow projetado (30 dias) | Projeção diária com bandas de confiança |
| Receita estimada real | Renda após filtrar transferências e rendimentos não recorrentes |
| Despesas recorrentes | Valor e frequência de cada recorrência identificada |
| Anomalia de gasto | Desvio estatístico vs histórico pessoal |
| Percentual comprometido | Fração da renda alocada em compromissos fixos |

</details>

<details>
<summary><strong>Custo Bancário e Tarifas</strong></summary>

| Métrica | Descrição |
|:---|:---|
| Total de tarifas pagas | Soma de todas as cobranças classificadas como tarifa |
| Custo de oportunidade | Quanto renderia se investido |
| Spread bancário estimado | Diferença entre taxa captada e cobrada |
| Total que o banco lucrou | Tarifa + spread + câmbio no período |
| Tarifas acima da média | Comparativo com benchmark dos 16 principais bancos |

</details>

<details>
<summary><strong>Cartões e Recompensas</strong></summary>

| Métrica | Descrição |
|:---|:---|
| Cashback gerado vs potencial | Quanto ganhou vs quanto ganharia com o cartão ideal |
| Custo de oportunidade | Valor perdido por não usar o cartão mais adequado |
| ROI por cartão | Retorno efetivo considerando anuidade e benefícios |
| Estratégia multi-cartão | Carteira ótima de N cartões para o perfil |

</details>

<details>
<summary><strong>Simulações e Decisões</strong></summary>

| Métrica | Descrição |
|:---|:---|
| VPL das estratégias | Valor Presente Líquido comparativo |
| TIR do financiamento | Taxa Interna de Retorno efetiva |
| CET real | Custo Efetivo Total incluindo IOF e seguros |
| Intervalo Monte Carlo (95%) | Faixa de resultado com 95% de confiança |
| Sensibilidade a juros | Variação do VPL para cada +1% na taxa |

</details>

---

## 🏗️ Arquitetura Técnica

```
┌──────────────────────────────────────────────────────────────────┐
│                     USUÁRIO / FRONTEND (React 19)                │
│            TailwindCSS · React Query · Framer Motion             │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTPS / JWT
┌────────────────────────────▼─────────────────────────────────────┐
│                  FastAPI 0.109 — app/main.py                     │
│         Rate Limiting (SlowAPI) · CORS · Correlation IDs         │
│              JWT Auth · Audit Log · Health/Readiness             │
└──────┬──────────┬──────────┬──────────┬──────────────────────────┘
       │          │          │          │
┌──────▼───┐ ┌───▼──────┐ ┌─▼────────┐ ┌▼──────────────────────┐
│   ETL    │ │ Cashflow │ │Architect │ │  Agent (LangGraph)   │
│ Pipeline │ │  Engine  │ │   F3     │ │  ReAct + Claude 4.6  │
│ 8 stages │ │Safe2Spend│ │MonteCarlo│ │  13 Financial Tools  │
└──────┬───┘ └───┬──────┘ └──────────┘ └───────────────────────┘
       │         │
┌──────▼─────────▼──────────────────────────────────────────────┐
│                    MÓDULOS ANALÍTICOS                          │
│  F2 Card Optimizer  ·  F5 Cost Analysis  ·  F7 Smart Purchase │
│  F13 Negotiator  ·  MX.1-4  ·  Budget  ·  Goals  ·  Fiscal    │
└──────────────────────────┬────────────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────────────┐
│                      DATA LAYER                                │
│          PostgreSQL 16 + SQLAlchemy 2.0 + Alembic              │
│          Polars DataFrames  ·  Redis (cache + rate limit)      │
└──────────────────────────┬────────────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────────────┐
│                  INTEGRAÇÕES EXTERNAS                          │
│   Pluggy (Open Finance)  ·  BACEN/ANBIMA (taxas de mercado)   │
│   Claude Sonnet 4.6 (IA)  ·  GPT-4o-mini (fallback)           │
└───────────────────────────────────────────────────────────────┘
```

### Padrões Arquiteturais

| Padrão | Aplicação |
|:---|:---|
| **Feature-driven** | Cada funcionalidade em `/app/{feature}/` isolado |
| **Pipeline Pattern** | ETL 8 estágios: Ingest → Classify → Detect → Validate → Persist |
| **Strategy Pattern** | Parsing por banco: Nubank, Itaú, Inter, default |
| **ReAct Agent** | LangGraph: pensa → chama ferramenta → observa → repete |
| **Multi-layer Fallback** | ML → Regras → Defaults em classificadores |
| **Repository Pattern** | Abstração de dados via SQLAlchemy + DI |

---

## 🛠️ Stack Tecnológica

<table>
<tr>
<td width="50%">

### Backend

| Camada | Tecnologia |
|:---|:---|
| API | FastAPI 0.109 + Uvicorn |
| Database | PostgreSQL 16 + SQLAlchemy 2.0 |
| Cache | Redis 5.0 + SlowAPI |
| DataFrames | Polars 0.20 |
| ML | Scikit-learn, CatBoost |
| Open Finance | Pluggy API |
| Taxas | BACEN API + ANBIMA |
| IA | LangGraph + Claude 4.6 |
| Auth | JWT + bcrypt + Redis |
| Logging | structlog 24.1 |

</td>
<td width="50%">

### Frontend

| Camada | Tecnologia |
|:---|:---|
| Framework | React 19 + TypeScript |
| Build | Vite |
| Styling | TailwindCSS 4 |
| State | Zustand 5 + React Query 5 |
| Charts | Recharts 3 |
| Animation | Framer Motion 12 |
| Testing | Vitest + Playwright |

### DevOps

| Camada | Tecnologia |
|:---|:---|
| Container | Docker |
| CI/CD | GitHub Actions |
| Deploy | Railway |
| Tests | pytest 7.4 |

</td>
</tr>
</table>

---

## 📁 Estrutura do Projeto

```
nexa/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app, lifespan, middleware
│   │   ├── core/
│   │   │   ├── config.py              # Pydantic Settings
│   │   │   ├── security.py            # JWT, bcrypt
│   │   │   ├── database.py            # SQLAlchemy engine
│   │   │   └── integrations/
│   │   │       └── pluggy.py          # Cliente Open Finance
│   │   ├── api/v1/routes/             # 20+ routers
│   │   ├── forecast/                  # F1: ETL + Cashflow
│   │   │   ├── etl/
│   │   │   │   ├── ingestor.py
│   │   │   │   ├── classifier.py
│   │   │   │   ├── recurring_detector.py
│   │   │   │   └── bank_strategy/
│   │   │   └── cashflow/
│   │   │       ├── engine.py
│   │   │       └── safe_to_spend.py
│   │   ├── optimizer/                 # F2: Card Optimizer
│   │   ├── architect/                 # F3: Monte Carlo + VPL
│   │   ├── divider/                   # F4: PF/PJ Classifier
│   │   ├── costs/                     # F5: Raio-X de Tarifas
│   │   ├── purchase/                  # F7: Compra Inteligente
│   │   ├── negotiator/                # F13: Scripts Claude
│   │   ├── goals/                     # MX.2: Metas
│   │   ├── health_score/              # MX.1: Score
│   │   ├── notifications/             # MX.3: Alertas
│   │   ├── peers/                     # MX.4: Benchmark
│   │   └── agent/                     # LangGraph ReAct
│   │       ├── graph.py
│   │       └── tools/                 # 13 ferramentas
│   ├── alembic/versions/              # Migrations
│   ├── models/                        # Modelos ML (.pkl)
│   └── tests/                         # 414 testes
├── frontend-react/
│   └── src/
│       ├── components/
│       ├── pages/
│       ├── api/
│       └── hooks/
├── docs/                              # 13 arquivos de documentação
├── data/
│   └── cards/knowledge_cards.json     # 2.000+ cartões
├── docker-compose.yml
└── .github/workflows/ci.yml
```

---

## 🔌 Endpoints da API

### Sistema

| Método | Rota | Descrição |
|:---:|:---|:---|
| `GET` | `/health` | Health check |
| `GET` | `/readiness` | Readiness check (DB + Redis) |
| `GET` | `/version` | Versão da API |
| `GET` | `/docs` | Swagger UI |

### Autenticação

| Método | Rota | Descrição |
|:---:|:---|:---|
| `POST` | `/api/v1/auth/register` | Cadastro de usuário |
| `POST` | `/api/v1/auth/token` | Login → JWT |
| `POST` | `/api/v1/auth/logout` | Logout (revoga token) |

### Open Finance

| Método | Rota | Descrição |
|:---:|:---|:---|
| `GET` | `/api/v1/pluggy/institutions` | Lista instituições |
| `POST` | `/api/v1/pluggy/connect` | Conecta conta bancária |
| `GET` | `/api/v1/pluggy/accounts/{user_id}` | Contas conectadas |
| `GET` | `/api/v1/pluggy/transactions/{user_id}` | Transações |

<details>
<summary><strong>Ver todos os endpoints</strong></summary>

### F1 — Saúde Financeira

| Método | Rota | Descrição |
|:---:|:---|:---|
| `GET` | `/api/v1/forecast/{user_id}` | Cashflow + safe-to-spend + perfil |
| `GET` | `/api/v1/safe_to_spend/{user_id}` | Margem segura do dia |
| `GET` | `/api/v1/shadow_invoice/{user_id}` | Obrigações futuras |
| `GET` | `/api/v1/alerts/{user_id}` | Alertas ativos |

### F2 — Card Optimizer

| Método | Rota | Descrição |
|:---:|:---|:---|
| `POST` | `/api/v1/optimizer/recommend` | Ranqueia cartões |
| `POST` | `/api/v1/optimizer/simulate` | ROI de cartão específico |
| `POST` | `/api/v1/optimizer/multi_card` | Carteira ótima |
| `POST` | `/api/v1/optimizer/opportunity_cost` | Custo de oportunidade |

### F3 — Nexa Architect

| Método | Rota | Descrição |
|:---:|:---|:---|
| `POST` | `/api/v1/architect/simulate` | Compara estratégias (VPL + Monte Carlo) |
| `GET` | `/api/v1/architect/simulations` | Histórico |
| `GET` | `/api/v1/architect/simulations/{id}/sensitivity` | Análise de sensibilidade |

### F5 — Raio-X de Custos

| Método | Rota | Descrição |
|:---:|:---|:---|
| `GET` | `/api/v1/costs/{user_id}` | Tarifas vs benchmark |

### F7 — Compra Inteligente

| Método | Rota | Descrição |
|:---:|:---|:---|
| `POST` | `/api/v1/purchase/recommend` | Melhor forma de pagamento |

### MX — Engajamento

| Método | Rota | Descrição |
|:---:|:---|:---|
| `GET` | `/api/v1/health-score/history/{user_id}` | Score com tendência |
| `POST` | `/api/v1/goals/{user_id}` | Criar meta |
| `GET` | `/api/v1/goals/{user_id}` | Listar metas |
| `GET` | `/api/v1/peers/compare/{user_id}` | Benchmark IBGE/POF |
| `GET` | `/api/v1/budget/{user_id}` | Plano 50/30/20 |

### Agente

| Método | Rota | Descrição |
|:---:|:---|:---|
| `POST` | `/api/v1/chat/` | Chat com agente (13 ferramentas) |

</details>

> 📄 Referência completa em [docs/ENDPOINTS_SUMMARY.md](docs/ENDPOINTS_SUMMARY.md)

---

## 🤖 Agente de IA

O agente usa o padrão **ReAct**: o LLM decide qual ferramenta chamar, observa o resultado e responde em linguagem natural.

### 13 Ferramentas Financeiras

| Ferramenta | Quando é acionada |
|:---|:---|
| `get_financial_forecast` | Saúde financeira, safe-to-spend, projeção de caixa |
| `get_budget_advice` | Orçamento, regra 50/30/20, revisão de gastos |
| `get_card_optimization` | Qual cartão usar, pontos, cashback |
| `get_spending_alerts` | Alertas ativos, gastos anômalos |
| `get_goals_summary` | Metas, reserva de emergência, progresso |
| `get_financing_simulation` | Financiamento vs consórcio vs investimento |
| `get_timing_scenarios` | "E se eu esperar X meses para comprar?" |
| `get_leverage_simulation` | Aluguel + aplicação vs comprar financiado |
| `get_fiscal_report` | Impostos MEI/PJ, DAS, faturamento |
| `get_peer_comparison` | Gasto vs pares da mesma faixa de renda |
| `get_purchase_recommendation` | Melhor forma de pagamento |
| `get_bank_cost_analysis` | Tarifas, benchmark de bancos |
| `get_negotiation_script` | Script para negociar com o banco |

---

## 🗄️ Banco de Dados

PostgreSQL 16 com 3 migrations Alembic.

```sql
-- Principais tabelas
users                    -- Usuários
transactions_clean       -- Transações processadas (índice: user_id, date)
financial_goals          -- Metas financeiras
architect_simulations    -- Histórico de simulações F3
chat_messages            -- Histórico do agente
pluggy_items             -- Contas Open Finance
health_score_history     -- Série temporal do Score
context_overrides        -- Correções manuais PF/PJ
```

### Migrations

```bash
cd backend
alembic upgrade head                              # Aplicar todas
alembic revision --autogenerate -m "descricao"    # Nova migration
alembic downgrade -1                              # Reverter última
```

---

## 🧪 Testes

```bash
cd backend

# Rodar todos os testes
pytest tests/ -v

# Com coverage
pytest tests/ --cov=app --cov-report=html

# Feature específica
pytest tests/test_architect/ -v
pytest tests/test_optimizer/ -v
```

### Cobertura

| Módulo | Arquivos de Teste |
|:---|:---:|
| F2 — Card Optimizer | 12 |
| F3 — Architect | 18 |
| F1 — Cashflow / ETL | 6 |
| MX.1–MX.4 | 4 |
| Agente / Tools | 1 |
| E2E | 2 |

> ✅ **414 testes — 0 falhando**

CI/CD via GitHub Actions em push para `main`/`develop` e PRs.

---

## 📖 Exemplos de Uso

### Chat com o Agente

```bash
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "message": "Como estão minhas finanças? Posso comprar um carro de R$ 60.000?"
  }'
```

O agente chama automaticamente `get_financial_forecast` + `get_financing_simulation` e responde com análise completa.

### Simulação de Compra (F3)

```bash
curl -X POST http://localhost:8000/api/v1/architect/simulate \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "asset_type": "vehicle",
    "target_value": 60000,
    "down_payment": 12000,
    "months": 48,
    "monthly_income": 8000,
    "current_savings": 15000
  }'
```

**Retorna:** 3 estratégias ranqueadas por VPL com análise de sensibilidade e intervalo Monte Carlo (95%).

### Recomendação de Cartão (F2)

```bash
curl -X POST http://localhost:8000/api/v1/optimizer/recommend \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "monthly_income": 8000,
    "spending_profile": {
      "alimentacao": 1200,
      "viagens": 800,
      "combustivel": 400
    }
  }'
```

---

## 💼 Modelo de Negócio

> **A Nexa cobra do usuário, não do banco.** Isso garante neutralidade total.

| Plano | Preço | Capacidades |
|:---|:---:|:---|
| **Free** | R$ 0/mês | 1 banco, dashboard básico, 3 consultas Compra Inteligente, 5 msgs IA/dia |
| **Pro** | R$ 19,90/mês | Bancos ilimitados, Raio-X, Radar, Negociador (1/mês), chat ilimitado |
| **Total** | R$ 39,90/mês | Tudo do Pro + Transparência Radical, Piloto Automático, Modo Família |

### Unit Economics Target

| Métrica | Target |
|:---|:---:|
| ARPU | R$ 25/mês |
| CAC | R$ 40–80 |
| LTV (12 meses) | R$ 300 |
| LTV:CAC | > 4:1 |
| Margem bruta | 75%+ |
| Payback | < 3 meses |

---

## 🚀 Estratégias de Crescimento

### 1. B2B2C — Bem-Estar Financeiro Corporativo

O CAC no B2C financeiro é R$80-150/usuário. O canal B2B2C muda a economia do negócio.

> **O modelo:** vender a Nexa como benefício corporativo (estilo Gympass, mas para finanças). O RH distribui o app internamente — em uma única venda, a Nexa ganha 10.000-50.000 usuários com CAC próximo de zero.

| Aspecto | Detalhe |
|:---|:---|
| **Proposta para o RH** | Funcionários endividados faltam mais e produzem menos. Estresse financeiro custa ~R$15.000/ano por funcionário em perda de produtividade (PwC). A Nexa resolve isso. |
| **Pricing B2B2C** | R$ 5–15 por funcionário/mês. Empresa de 10.000 funcionários = R$100k–150k MRR em um contrato. |
| **Efeito colateral** | O funcionário conecta contas pessoais. Quando sai da empresa, já está viciado e migra para plano individual. |
| **Escala** | 10 contratos corporativos = 50.000–100.000 usuários com CAC zero. Equivale a R$5–10M de investimento em marketing B2C. |

### 2. Nexa Score — Bureau de Crédito Alternativo

O Serasa olha para o passado (inadimplência). A Nexa olha para o presente (fluxo de caixa real em tempo real).

> **O conceito:** criar um Score de Crédito Alternativo baseado nos 40+ indicadores da Nexa. Quando o usuário pedir empréstimo, compartilha o Nexa Score — que prova via Open Finance que ele é bom pagador — e força o banco a oferecer taxa menor.

| Fase | O que acontece |
|:---|:---|
| **Fase 1 (interna)** | Score Nexa é gamificação — o usuário sobe de nível melhorando hábitos financeiros. Gera engajamento. |
| **Fase 2 (compartilhável)** | Com 500k+ usuários, o Score vira exportável. O usuário mostra ao banco ao pedir crédito. |
| **Fase 3 (bureau)** | Instituições financeiras consultam o Score Nexa como alternativa ao Serasa. A Nexa cobra por verificação. Receita sem comprometer neutralidade (o usuário decide compartilhar). |

**Por que funciona:** uma pessoa que poupa 15% da renda e tem burn rate saudável é objetivamente menos arriscada do que alguém com Serasa 800 mas no limite do cheque especial. O Score Nexa captura isso — o Serasa não.

### 3. Nexa Wrapped — Viralização Orgânica

O brasileiro ama comparar e compartilhar. O Spotify Wrapped provou que dados pessoais em formato visual são o mecanismo viral mais poderoso que existe.

> **O modelo:** todo dezembro (e trimestralmente para Pro/Total), gerar um dashboard visual personalizado com os dados financeiros do usuário.

**Conteúdo do Wrapped:**

```
📊 Quanto cada banco ganhou com você este ano
💸 Top 5 tarifas que você pagou e poderia evitar
🏆 Total que a Nexa te economizou
📈 Sua evolução no Score Nexa
👥 Como você se compara com outros usuários Nexa
```

**Card compartilhável:**

```
"Eu economizei R$ 4.200 contra os bancos este ano com a @NexaAI.
 Veja quanto VOCÊ está perdendo."
 [Botão: Descubra grátis]
```

| Métrica | Impacto esperado |
|:---|:---|
| **Custo de produção** | Zero (dados já existem, template é estático) |
| **Share rate** | 15-25% dos usuários ativos compartilham (benchmark Spotify: 20%) |
| **Viralidade** | Cada share atinge ~300 pessoas (média de alcance Instagram/WhatsApp) |
| **Conversão** | 3-5% dos que veem fazem download (indignação com o próprio banco) |

### 4. Expansão LatAm — O Playbook Mexicano

O México tem sistema bancário tão concentrado e custoso quanto o Brasil, mas com digitalização mais atrasada — janela de oportunidade.

> **Por que México:** Open Banking regulado (Ley Fintech 2018), 60M de adultos sub-bancarizados, CONDUSEF (dados públicos de reclamações), e os mesmos problemas de tarifas abusivas.

| Dimensão | Brasil | México |
|:---|:---|:---|
| **População bancarizada** | 180M | 90M |
| **Concentração bancária** | 5 bancos = 80% | 7 bancos = 80% |
| **Open Finance** | Fase 4 (avançado) | Fase 2 (em andamento) |
| **Tarifa média anual** | R$ 800 | ~MXN 3.000 (~R$ 900) |
| **Regulador** | BACEN | CNBV + CONDUSEF |

**Timing:** provar o modelo no Brasil (2026-2027), adaptar ETL + conectores para o mercado mexicano (2028), escalar com a infraestrutura já validada.

**Impacto no valuation:** VCs globais (Ribbit Capital, a16z, SoftBank) investem em teses "LatAm", não "Brasil". Provar que o modelo replica no México transforma a Nexa de "fintech brasileira" em "plataforma LatAm" — multiplicador de valuation de 2-3x.

---

## 🗺️ Roadmap

### Fase 1 — Fundação ✅

- [x] ETL Pipeline 8 estágios
- [x] Card Optimizer (2.000+ cartões)
- [x] Nexa Architect (Monte Carlo + VPL)
- [x] Classificador PF/PJ (89% acurácia)
- [x] Raio-X de Custos
- [x] Modo Compra Inteligente
- [x] Score Nexa, Metas, Notificações
- [x] Agente conversacional (13 ferramentas)
- [x] Auth JWT, rate limiting, audit log
- [x] 414 testes passando

### Fase 2 — Piloto Automático (Q2–Q3 2026)

- [ ] Sweep automático (Open Finance Fase 4)
- [ ] Radar de Produtos — 200+ instituições
- [ ] Portabilidade de crédito assistida
- [ ] Modo Família (até 4 membros)
- [ ] Widget de safe-to-spend
- [ ] Nexa Score exportável (bureau alternativo)
- [ ] Nexa Wrapped trimestral (Pro/Total)

### Fase 3 — Defesa e Viralização (Q3–Q4 2026)

- [ ] Detector de Venda Casada
- [ ] Recuperador de Cobranças
- [ ] Detector de Juros Abusivos
- [ ] Central de Evidências
- [ ] Wrapped Financeiro Anual (viralização massiva)
- [ ] B2B2C — primeiros contratos corporativos

### Fase 4 — Escala (2027)

- [ ] Otimizador de IR em tempo real
- [ ] Monitor de Direitos Esquecidos
- [ ] B2B2C — escala nacional (50+ empresas)
- [ ] Nexa Score aceito por instituições financeiras
- [ ] Expansão LatAm (México)
- [ ] API de inteligência financeira para terceiros

---

## 📚 Documentação

| Arquivo | Conteúdo |
|:---|:---|
| [SETUP_LOCAL.md](docs/SETUP_LOCAL.md) | Setup local detalhado |
| [ENDPOINTS_SUMMARY.md](docs/ENDPOINTS_SUMMARY.md) | Referência completa de endpoints |
| [QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md) | Cheatsheet do dev |
| [ARCHITECT_F3.md](docs/ARCHITECT_F3.md) | Documentação do módulo Architect |
| [NEXA_ARCHITECT_V2_SPEC.md](docs/NEXA_ARCHITECT_V2_SPEC.md) | Spec v2.0: modelos estocásticos |
| [NEXA_ESTRATEGIA_TECNICA.md](docs/NEXA_ESTRATEGIA_TECNICA.md) | Estratégia técnica do produto |
| [BACKEND_REFERENCE.md](docs/BACKEND_REFERENCE.md) | Referência de arquivos do backend |
| [PF_PJ_VALIDATION_REPORT.md](docs/PF_PJ_VALIDATION_REPORT.md) | Validação do classificador (89%) |
| [FRONTEND_GRAFICOS.md](docs/FRONTEND_GRAFICOS.md) | Spec dos componentes visuais |

---

## 📈 Status do Projeto

| Componente | Status |
|:---|:---:|
| Backend API (FastAPI) | ✅ Produção |
| Banco PostgreSQL + Migrations | ✅ Produção |
| Autenticação JWT | ✅ Produção |
| Rate Limiting + Audit | ✅ Produção |
| ETL Pipeline | ✅ Produção |
| Card Optimizer | ✅ Produção |
| Nexa Architect (F3) | ✅ Produção |
| PF/PJ Classifier | ✅ Produção |
| Agente IA (Claude 4.6) | ✅ Produção |
| Frontend React | ✅ Produção |
| CI/CD GitHub Actions | ✅ Ativo |
| Deploy Railway | ✅ Configurado |
| Memória do agente | 🔧 Em desenvolvimento |
| B2B2C corporativo | 📅 Fase 3 |
| Nexa Score (bureau) | 📅 Fase 2–3 |
| Expansão México | 📅 Fase 4 |

---

<div align="center">

### Nexa AI

**14 funcionalidades implementadas. 30 no roadmap. 4 vetores de escala. 1 missão.**

*Trabalhar para você, não para o banco.*

---

**Março 2026 · Confidencial**

</div>
