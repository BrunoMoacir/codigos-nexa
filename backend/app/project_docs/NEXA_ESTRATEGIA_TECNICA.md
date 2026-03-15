# NEXA AI — Estratégia Técnica e Roadmap de Engenharia
**Documento Interno — Março 2026**

---

## 1. Estado Atual do Projeto

### 1.1 Visão Geral da Stack

| Camada | Tecnologia Atual | Status |
|--------|-----------------|--------|
| Framework API | FastAPI 0.128 + Uvicorn | ✅ Produção |
| Banco de Dados | DuckDB (embedded) | ⚠️ MVP only |
| Cache | Redis | ❌ Configurado, não usado |
| Agent AI | LangGraph + GPT-4o-mini | ⚠️ Sem persistência entre sessões |
| LLM Target | Claude Sonnet (Anthropic) | ❌ Lib instalada, não integrado |
| Autenticação | JWT (python-jose + bcrypt) | ⚠️ Só no /chat |
| ORM / Migrations | SQLAlchemy + Alembic | ❌ Instalado, não migrado |
| Containerização | Docker + Docker Compose | ✅ Funcional |
| CI/CD | — | ❌ Inexistente |
| Frontend | Streamlit | ⚠️ Protótipo apenas |
| Open Finance | Pluggy API | ✅ Cliente real + mock |
| Testes | pytest (414 passing) | ⚠️ Lacunas nos tools do agente + MX |

### 1.2 Funcionalidades Implementadas

```
✅ F1  — Motor Core (ETL, cashflow, safe-to-spend, shadow invoices)
✅ F2  — Card Optimizer (ranking, multi-card, custo de oportunidade)
✅ F3  — Nexa Architect (simulador de compra, Monte Carlo, sensibilidade)
✅ F4  — Nexa Divider (classificador PF/PJ ML, relatório fiscal)
✅ MX.1 — Health Score History (série temporal)
✅ MX.2 — Metas Financeiras
✅ MX.3 — Notificações Proativas
✅ MX.4 — Comparação com Pares (IBGE/POF)
✅ Budget Advisor (50/30/20)
✅ Detecção de Assinaturas
✅ Detecção de Anomalias de Gasto
✅ Agente Conversacional (8 tools, LangGraph ReAct)
```

### 1.3 Estrutura de Arquivos Relevante

```
backend/
├── app/
│   ├── main.py                      # FastAPI entry point
│   ├── runner.py                    # NexaRunner — pipeline completo
│   ├── api/v1/
│   │   ├── router.py                # Registro central das rotas
│   │   └── routes/                  # 22 arquivos de endpoints
│   ├── agent/
│   │   ├── graph.py                 # Builder do agente LangGraph
│   │   ├── state.py                 # AgentState (Polars DataFrames)
│   │   └── tools/                   # 8 ferramentas financeiras
│   ├── etl/                         # Pipeline ETL (5 estágios)
│   ├── optimizer/                   # F2 — Otimizador de cartões
│   ├── architect/                   # F3 — Simulador de compras
│   ├── cashflow/                    # Engine de fluxo de caixa
│   ├── goals/ notifications/ peers/ # MX features
│   ├── integrations/open_finance/   # Pluggy real + mock
│   ├── db/
│   │   ├── queries.py               # DuckDB queries
│   │   └── migrations/              # 5 migrações SQL
│   └── core/
│       ├── config.py                # Pydantic Settings
│       └── security.py              # JWT/OAuth2 (IMPLEMENTADO)
├── models/                          # ML models serializados (.pkl)
├── data/
│   ├── cards/knowledge_cards.json   # Base de cartões (~2000+)
│   └── transactions.duckdb          # Dados de treino/teste
└── tests/                           # 60 arquivos, 414 tests
```

---

## 2. Dívidas Técnicas Críticas (Fazer Antes de Novas Features)

Estas são as ações que precisam ser feitas **antes de qualquer nova funcionalidade** — comprometem segurança, estabilidade e escalabilidade.

### 2.1 Autenticação em Todas as Rotas

**Problema:** `security.py` tem JWT completo mas só está no endpoint `/chat`.

**Arquivo:** `app/core/security.py` — a função `get_current_user` já existe.

**O que fazer:** Adicionar `Depends(get_current_user)` em todas as rotas que retornam dados do usuário.

```python
# Padrão atual (inseguro):
@router.get("/forecast")
async def get_forecast(user_id: str):
    ...

# Padrão correto:
from app.core.security import get_current_user

@router.get("/forecast")
async def get_forecast(user_id: str = Depends(get_current_user)):
    ...
```

**Rotas que precisam ser protegidas:**
- `forecast.py`, `shadow_invoice.py`, `safe_to_spend.py`
- `optimizer.py`, `architect.py`, `fiscal_report.py`
- `health_score.py`, `goals.py`, `notifications.py`, `peers.py`
- `budget.py`, `subscriptions.py`, `alerts.py`
- `context_override.py`, `dashboard.py`

**Atenção:** O `SECRET_KEY` atual é o valor padrão de desenvolvimento. Deve ser trocado por uma variável de ambiente forte em produção.

---

### 2.2 Migração DuckDB → PostgreSQL

**Problema:** DuckDB é embedded e single-writer. Não suporta múltiplas instâncias da API (qualquer deploy com 2+ replicas vai corromper o banco).

**Estado atual:** `DATABASE_URL` já está no `config.py`. `psycopg2-binary`, `SQLAlchemy` e `Alembic` já estão no `requirements.txt`. Só falta migrar.

**Caminho de migração:**

1. **Criar `app/db/session.py` com SQLAlchemy async:**
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

2. **Converter as queries DuckDB para SQLAlchemy/asyncpg** — `app/db/queries.py` é o ponto central.

3. **Rodar `alembic init` e converter as 5 migrações SQL existentes** em migrações Alembic.

4. **Atualizar `docker-compose.yml`** para incluir serviço PostgreSQL:
```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: nexa
      POSTGRES_USER: nexa
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data

  api:
    depends_on:
      - db
```

---

### 2.3 Redis para Cache e Sessões do Agente

**Problema:** O agente usa `MemorySaver` (memória RAM) — a conversa some quando o processo reinicia. Taxas de mercado são buscadas a cada request.

**Estado atual:** `REDIS_URL` já está no `config.py`. Biblioteca `redis` já está nas dependências.

**O que implementar:**

**A. Cache de taxas de mercado** (BACEN, ANBIMA — mudam 1x/dia):
```python
import redis.asyncio as redis
from app.core.config import settings

cache = redis.from_url(settings.REDIS_URL)

async def get_selic_rate():
    cached = await cache.get("selic_rate")
    if cached:
        return float(cached)
    rate = await bacen_connector.fetch_selic()
    await cache.setex("selic_rate", 3600, rate)  # TTL 1h
    return rate
```

**B. Persistência do histórico de conversa do agente:**
```python
from langgraph.checkpoint.redis import RedisSaver

checkpointer = RedisSaver(redis_url=settings.REDIS_URL)
graph = create_react_agent(llm, tools, checkpointer=checkpointer)
```

**C. Rate limiting por usuário** (via Redis sliding window):
```python
async def check_rate_limit(user_id: str, limit: int = 60, window: int = 60):
    key = f"rate:{user_id}"
    count = await cache.incr(key)
    if count == 1:
        await cache.expire(key, window)
    if count > limit:
        raise HTTPException(429, "Rate limit exceeded")
```

---

### 2.4 Rate Limiting

**Problema:** Nenhum endpoint tem rate limiting. Um bot pode derrubar a API ou esgotar a cota do OpenAI/Anthropic.

**Solução rápida com `slowapi`** (já compatível com FastAPI):
```python
# requirements.txt: slowapi
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@router.post("/chat")
@limiter.limit("20/minute")  # 20 mensagens por minuto por IP
async def chat(request: Request, ...):
    ...
```

---

### 2.5 Rotas Comentadas para Ativar

No `app/api/v1/router.py`:
```python
# TODO: Ativar quando dependências forem resolvidas
# from app.api.v1.routes import pluggy_test  → testar conexão Pluggy
# from app.api.v1.routes import analyze      → análise ad-hoc
# from app.api.v1.routes import cashflow     → endpoints diretos de cashflow
```

Esses arquivos existem em `routes/` mas não estão registrados. Revisar e ativar.

---

### 2.6 CI/CD com GitHub Actions

**Problema:** Não existe pipeline automatizado. Qualquer push pode quebrar produção sem aviso.

**Criar `.github/workflows/ci.yml`:**
```yaml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r backend/requirements.txt
      - run: cd backend && pytest tests/ -x --tb=short

  docker-build:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t nexa-api .
```

---

## 3. Migração do Agente para Claude

### 3.1 Por que migrar

- `langchain-anthropic` já está instalado (`requirements.txt`)
- Claude tem tool use nativo mais confiável que GPT-4o-mini
- Context window maior (200K tokens) — ideal para análises financeiras longas
- Modelo de pricing mais previsível para produto consumer

### 3.2 Configuração Atual (GPT-4o-mini)

**Arquivo:** `app/agent/graph.py`

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.0,
    api_key=settings.OPENAI_API_KEY
)
```

### 3.3 Migração para Claude

**Adicionar ao `.env`:**
```
ANTHROPIC_API_KEY=sk-ant-...
```

**Adicionar ao `app/core/config.py`:**
```python
ANTHROPIC_API_KEY: str | None = None
LLM_PROVIDER: str = "openai"  # "openai" | "anthropic"
LLM_MODEL: str = "gpt-4o-mini"  # ou "claude-sonnet-4-6"
```

**Atualizar `app/agent/graph.py`:**
```python
from app.core.config import settings

def build_llm():
    if settings.LLM_PROVIDER == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=settings.LLM_MODEL or "claude-sonnet-4-6",
            temperature=0.0,
            api_key=settings.ANTHROPIC_API_KEY,
            max_tokens=4096
        )
    else:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.LLM_MODEL or "gpt-4o-mini",
            temperature=0.0,
            api_key=settings.OPENAI_API_KEY
        )

llm = build_llm()
```

### 3.4 Modelo por Tipo de Tarefa

| Tarefa | Modelo | Razão |
|--------|--------|-------|
| Chat principal do usuário | Claude Sonnet 4.6 | Custo/performance ideal |
| Classificação de transações | Claude Haiku 4.5 | Rápido, barato |
| Análises financeiras profundas / relatórios | Claude Opus 4.6 | Máxima qualidade |
| Alertas e notificações proativas | Claude Haiku 4.5 | Alta frequência, baixo custo |

### 3.5 Memória entre Sessões com Claude + Redis

O LangGraph com Claude funciona identicamente ao GPT — só trocar o LLM. A persistência da conversa fica no checkpointer:

```python
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.redis import RedisSaver

checkpointer = RedisSaver(redis_url=settings.REDIS_URL)

agent = create_react_agent(
    model=llm,
    tools=tools,
    checkpointer=checkpointer,
    state_modifier=system_prompt
)
```

O `thread_id` (mapeado para `user_id`) persiste a conversa entre sessões automaticamente.

---

## 4. Novas Funcionalidades — Integração Técnica

As funcionalidades F5–F12 do plano estratégico têm pontos de apoio já existentes no código. Abaixo, o mapa de integração de cada uma.

### F5 — Raio-X de Custos Bancários

**Objetivo:** Mapear tarifas ocultas de cada banco e calcular o Custo Bancário Total (CBT).

**Base existente:**
- `app/etl/ingestor.py` — já normaliza transações com campo `category`
- `app/etl/classifier.py` — classifica categorias (inclui "TARIFA" e "ANUIDADE")
- `app/cashflow/burn_rate.py` — analisa padrões de saída de dinheiro

**O que construir:**

1. **`app/costs/bank_fee_analyzer.py`** — extrator de tarifas:
```python
# Categorias a monitorar:
FEE_CATEGORIES = [
    "TARIFA_MANUTENCAO", "TED", "DOC", "ANUIDADE_CARTAO",
    "SEGURO_PRESTAMISTA", "SAQUE", "PACOTE_SERVICOS"
]

class BankFeeAnalyzer:
    def analyze(self, transactions: list[Transaction], user_id: str) -> BankCostReport:
        # Agrupa por banco (já disponível em transactions.issuer)
        # Soma tarifas por categoria
        # Retorna CBT por banco
```

2. **`app/costs/market_fees_db.py`** — base de tarifas de mercado (JSON estático + atualização mensal):
```python
# Similar ao knowledge_cards.json para cartões
# data/fees/bank_fees.json — tarifas públicas dos principais bancos
```

3. **Nova rota:** `app/api/v1/routes/costs.py` → `GET /api/v1/costs/raio-x`

4. **Nova tool no agente:** `get_bank_cost_analysis` em `app/agent/tools/`

**Dados necessários:** Expandir `knowledge_cards.json` para incluir tarifas de conta (não só cartões).

---

### F6 — Negociador Automático de Taxas

**Objetivo:** Gerar scripts de negociação personalizados com argumentos baseados em dados reais.

**Base existente:**
- `app/optimizer/ranking.py` — já compara taxas do usuário com mercado
- `app/architect/connectors/` — acessa taxas reais (BACEN, ANBIMA)
- `app/peers/peer_comparison.py` — benchmarks de mercado

**O que construir:**

1. **`app/negotiator/script_generator.py`** — gerador de scripts via Claude:
```python
class NegotiationScriptGenerator:
    def generate(self, context: NegotiationContext) -> NegotiationScript:
        # context contém: taxa atual, taxa de mercado, histórico, score
        # Chama Claude com prompt especializado
        # Retorna: script de negociação, argumentos, melhor momento para ligar
```

2. **`app/negotiator/opportunity_detector.py`** — detecta quando negociar:
```python
# Triggers:
# - Taxa do cartão > média mercado em X%
# - Anuidade cobrada > media dos últimos 12 meses
# - Usuário pagou em dia por 6+ meses (maior poder de barganha)
# - Banco ofereceu produto pior ao usuário
```

3. **Nova rota:** `POST /api/v1/negotiator/generate-script`

4. **Integração com MX.3 (notificações):** `app/notifications/notifier.py` já tem estrutura para adicionar novo tipo de alerta "OPORTUNIDADE_NEGOCIACAO".

---

### F7 — Modo Compra Inteligente

**Objetivo:** Antes de uma compra, recomendar o melhor método de pagamento.

**Base existente — F3 (Nexa Architect) é o núcleo:**
- `app/architect/calculators/` — já calcula NPV, custo de financiamento, parcelamento
- `app/optimizer/` — já ranqueia cartões por categoria de gasto
- `app/optimizer/multi_card_strategy.py` — já otimiza cartões por tipo de compra
- `app/cashflow/safe_to_spend.py` — já calcula margem disponível

**O que construir:**

1. **`app/purchase/purchase_advisor.py`** — orquestrador da análise:
```python
class PurchaseAdvisor:
    def analyze(self, amount: float, category: str, user_id: str) -> PurchaseRecommendation:
        # 1. Chama optimizer para melhor cartão (já existe)
        # 2. Chama architect para simular parcelamento (já existe)
        # 3. Compara Pix à vista vs cartão vs empréstimo
        # 4. Verifica impacto no safe_to_spend (já existe)
        # 5. Retorna recomendação unificada
```

2. **Nova rota:** `POST /api/v1/purchase/analyze` (reutiliza F2 + F3 internamente)

3. **Nova tool no agente:** `get_purchase_recommendation` — ferramenta que o usuário pode chamar via chat ("Vou comprar uma TV de R$3.000, qual a melhor forma?")

**Este é o de menor esforço novo** — 80% da lógica já existe em F2 e F3, só falta o orquestrador unificado.

---

### F8 — Radar de Produtos Financeiros

**Objetivo:** Monitorar o mercado e alertar sobre produtos melhores do que os que o usuário possui.

**Base existente:**
- `app/architect/connectors/` — conectores de mercado (BACEN, ANBIMA, IPCA)
- `app/notifications/notifier.py` — já tem infraestrutura de alertas
- `data/cards/knowledge_cards.json` — base de ~2000 cartões

**O que construir:**

1. **`data/products/`** — expandir a base de dados:
```
data/
├── cards/knowledge_cards.json       # ✅ Já existe
├── products/
│   ├── savings_accounts.json        # CDB, LCI, LCA por instituição
│   ├── personal_loans.json          # Taxas de empréstimo pessoal
│   ├── checking_accounts.json       # Tarifas de conta corrente
│   └── credit_cards_full.json       # Cartões com cashback/milhas detalhados
```

2. **`app/radar/product_radar.py`** — motor de monitoramento:
```python
class ProductRadar:
    def scan_opportunities(self, user_profile: UserProfile) -> list[Opportunity]:
        # Compara o que o usuário tem vs. mercado
        # Filtra por elegibilidade (renda, score)
        # Ordena por economia potencial
        # Integra com notifier para gerar alertas
```

3. **Job periódico** (cron ou Celery) para atualizar dados de mercado e rodar o radar para todos os usuários ativos.

---

### F9 — Transparência Radical

**Objetivo:** Mostrar quanto cada banco ganha com o usuário.

**Base existente:**
- `app/etl/income_profiler.py` — já estima a renda real do usuário
- `app/costs/` (F5) — já calcula tarifas pagas

**O que construir:**

1. **`app/transparency/bank_profit_estimator.py`**:
```python
# Modelo de estimativa de lucro do banco:
# Lucro = Float (saldo médio × CDI overnight)
#       + Spread de crédito (taxa cobrada − custo de funding)
#       + Tarifas diretas
#       + Interchange do cartão (0.7-1.5% de cada compra)
#       + Cross-sell (seguros, capitalização embutidos)
```

2. **`app/transparency/value_delivered.py`**:
```python
# Valor entregue = cashback + milhas + benefícios usados
# ROI para o usuário = valor_entregue / lucro_do_banco
```

3. **Geração de "card compartilhável"** (PNG/HTML) — integrar com uma biblioteca de templating para criar imagem do resultado (para viralizar nas redes).

---

### F10 — Piloto Automático Financeiro (Fase 2)

**Objetivo:** Executar ações automáticas com permissão do usuário.

**Pré-requisitos técnicos antes de implementar:**
- Open Finance Fase 3 (pagamento iniciado pelo terceiro) — regulação BACEN em andamento
- Aprovação no sandbox da Pluggy para payment initiation
- Revisão jurídica sobre responsabilidade nas execuções automáticas

**Base a preparar agora:**
1. **Schema de regras de automação** — `app/schemas/automation_rules.py`
2. **Engine de avaliação de regras** — `app/autopilot/rule_engine.py` (sem execução por ora, só avaliação)
3. **Simulação do que o piloto automático teria feito** — mostrar no dashboard como prova de valor antes de habilitar execução real

---

### F11 — Score Nexa (Fase 2)

**Base existente:**
- `app/api/v1/routes/health_score.py` + `app/db/migrations/004_create_health_score_history.sql` — já tem health score com histórico!
- `app/cashflow/budget_advisor.py` — já analisa comportamento financeiro
- `app/peers/peer_comparison.py` — já compara com benchmarks

**O score Nexa pode ser construído diretamente sobre o health score existente**, expandindo os fatores:

```python
# Fatores atuais do health_score → expandir para Score Nexa:
# + Consistência de poupança (últimos 12 meses)
# + Diversificação de receitas
# + Gestão de crédito (não só uso, mas histórico de negociação)
# + Metas alcançadas (já rastreadas em MX.2)
# + Resposta a alertas (aceitou sugestões?)
```

---

### F12 — Modo Casal/Família (Fase 2)

**Impacto no modelo de dados:**
- Novo campo `household_id` nas tabelas de usuário
- Novo endpoint `POST /api/v1/households/` para criar e vincular contas
- Queries agregadas por `household_id` em vez de `user_id`

**Maior complexidade:** permissões — o que cada membro pode ver das finanças do outro.

---

## 5. Arquitetura Multi-Agente (Evolução do Agente Atual)

### 5.1 Estado Atual

```
Usuário → POST /chat → AgentGraph (ReAct, 1 agente, 8 tools) → Resposta
```

O agente atual usa `create_react_agent` do LangGraph — funciona bem para MVP.

### 5.2 Arquitetura Proposta (sem precisar reescrever tudo)

O LangGraph já suporta grafos com múltiplos nós. A migração é incremental:

```python
# app/agent/graph.py — evolução do grafo atual

# Nó 1: Orquestrador (já existe, é o agente principal)
# Nó 2: Agente Analista (cálculos pesados — F3, Monte Carlo)
# Nó 3: Agente de Mercado (F8 Radar, busca de produtos)
# Nó 4: Agente Proativo (roda em background, gera notificações)

from langgraph.graph import StateGraph, END

workflow = StateGraph(AgentState)
workflow.add_node("orchestrator", orchestrator_agent)
workflow.add_node("analyst", analyst_agent)
workflow.add_node("market", market_agent)
workflow.add_conditional_edges(
    "orchestrator",
    route_to_specialist,  # decide qual agente chamar
    {"analyst": "analyst", "market": "market", "end": END}
)
```

### 5.3 Agente Proativo (Background)

**Arquivo a criar:** `app/agent/proactive_agent.py`

```python
# Roda periodicamente (cron job ou APScheduler)
# Para cada usuário ativo:
#   1. Busca dados recentes
#   2. Roda análise com Claude Haiku (barato)
#   3. Se encontrar insight relevante → salva em notifications
#   4. Usuário vê na próxima vez que abrir o app

from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job("interval", hours=6)
async def run_proactive_scan():
    users = await get_active_users()
    for user_id in users:
        insights = await proactive_agent.scan(user_id)
        await notifier.save_insights(user_id, insights)
```

---

## 6. Cobertura de Testes — Lacunas

### 6.1 Status Atual

```
✅ F2 (Optimizer)    → 15 arquivos de teste
✅ F3 (Architect)    → 21 arquivos de teste
✅ F4 (PF/PJ)        → test_f4_complete.py (33KB)
✅ ETL Pipeline      → test_ultimate_etl_and_schemas.py (39KB)
✅ E2E               → test_e2e_full_pipeline.py (30KB)

❌ Agent tools       → só 1 teste (get_card_optimization)
❌ MX.1 Health Score → sem testes
❌ MX.2 Goals        → test_goal_tracker.py existe mas incompleto
❌ MX.3 Notifications → sem testes
❌ MX.4 Peers        → sem testes
❌ Novas rotas F5-F9 → a criar junto com as features
```

### 6.2 Testes Prioritários a Criar

```
tests/agent/
├── test_tool_forecast.py
├── test_tool_budget.py
├── test_tool_alerts.py
├── test_tool_goals.py
├── test_tool_peer_comparison.py
├── test_tool_fiscal_report.py
└── test_agent_memory_persistence.py   # Após migrar para Redis

tests/
├── test_health_score_history.py       # MX.1
├── test_notifications.py              # MX.3
├── test_peers_benchmark.py            # MX.4
└── test_security_endpoints.py         # JWT em todas as rotas
```

---

## 7. Variáveis de Ambiente

Arquivo `.env` atual e o que adicionar:

```bash
# Existentes (manter)
PLUGGY_CLIENT_ID=...
PLUGGY_CLIENT_SECRET=...
PLUGGY_BASE_URL=https://api.pluggy.ai
OPENAI_API_KEY=...

# Adicionar imediatamente
ANTHROPIC_API_KEY=sk-ant-...          # Para migração do agente
SECRET_KEY=<string aleatória 64 chars> # TROCAR o valor padrão atual
DATABASE_URL=postgresql+asyncpg://nexa:senha@db:5432/nexa
REDIS_URL=redis://redis:6379/0
APP_ENV=production                     # production | development
LOG_LEVEL=INFO

# Fase 2
AWS_S3_BUCKET=nexa-raw-events          # Para raw_events.py
CELERY_BROKER_URL=redis://redis:6379/1 # Para jobs assíncronos
```

---

## 8. Roadmap Técnico por Fase

### Fase 1 — Estabilização (Semanas 1–4)

Prioridade: tornar o que existe seguro e escalável.

| # | Tarefa | Arquivo(s) | Esforço |
|---|--------|-----------|---------|
| 1 | Adicionar JWT em todas as rotas | `routes/*.py` | 1 dia |
| 2 | Trocar SECRET_KEY por env var real | `.env`, `security.py` | 2h |
| 3 | Migrar para PostgreSQL + Alembic | `db/`, `docker-compose.yml` | 3 dias |
| 4 | Ativar Redis + persistir sessão do agente | `agent/graph.py`, `.env` | 1 dia |
| 5 | Implementar rate limiting com slowapi | `main.py`, `routes/chat.py` | 4h |
| 6 | Criar GitHub Actions CI | `.github/workflows/ci.yml` | 4h |
| 7 | Migrar LLM para Claude Sonnet | `agent/graph.py`, `config.py` | 4h |
| 8 | Ativar rotas comentadas (analyze, cashflow) | `router.py` | 2h |
| 9 | Escrever testes para agent tools + MX | `tests/agent/`, `tests/` | 3 dias |

### Fase 2 — Novas Features (Meses 2–6)

Ordem recomendada por custo/benefício:

| Prioridade | Feature | Reutiliza |
|-----------|---------|-----------|
| 1 | F7 Modo Compra Inteligente | F2 + F3 (80% pronto) |
| 2 | F5 Raio-X de Custos | ETL classifier + knowledge_cards |
| 3 | F8 Radar de Produtos | knowledge_cards + notifier |
| 4 | F9 Transparência Radical | F5 + income_profiler |
| 5 | F6 Negociador de Taxas | F5 + architect connectors + Claude |
| 6 | F11 Score Nexa | health_score (já existe) |

### Fase 3 — Escala (Meses 7–18)

| Tarefa | Dependência |
|--------|-------------|
| App mobile (React Native/Flutter) | API estável + auth completo |
| Arquitetura multi-agente | Redis + Claude migrado |
| Agente proativo (background jobs) | APScheduler ou Celery |
| F10 Piloto Automático | Open Finance Fase 3 (regulação BACEN) |
| F12 Modo Família | Novo modelo de dados (household_id) |

---

## 9. Decisões Arquiteturais Relevantes

### Por que não reescrever o agente do zero?

O LangGraph com `create_react_agent` é simples e funciona. A migração para multi-agente pode ser feita **adicionando nós ao grafo existente** — não é necessário reescrever. O sistema de tools já está modular (`agent/tools/`).

### Por que manter Polars?

`AgentState` usa Polars para processar DataFrames dentro do agente. Polars é significativamente mais rápido que Pandas para as operações financeiras feitas aqui (group by, aggregation, filter). Não mudar.

### Por que DuckDB pode ficar para analytics interno?

Mesmo após migrar para PostgreSQL como banco principal, DuckDB pode ser mantido como **data warehouse analítico local** — leitura de grandes volumes de transações históricas para relatórios e treinamento de ML. São casos de uso diferentes.

### Por que não usar Celery ainda?

Para o volume atual (MVP, <10K usuários), APScheduler rodando no mesmo processo da FastAPI é suficiente para jobs periódicos. Celery adiciona complexidade operacional que não se justifica antes de Fase 3.

---

## 10. Checklist de Segurança para Produção

- [ ] `SECRET_KEY` rotacionado (não usar o valor padrão do código)
- [ ] Credenciais do `.env` fora do repositório (usar GitHub Secrets ou vault)
- [ ] JWT em 100% das rotas com dados de usuário
- [ ] Rate limiting em `/chat` e `/api/v1/auth/token`
- [ ] HTTPS obrigatório (nginx com Let's Encrypt ou CloudFlare)
- [ ] CORS restrito ao domínio do frontend
- [ ] Logs sem PII (CPF, saldo, nome do usuário)
- [ ] Chave Pluggy rotacionada antes de qualquer demo pública
- [ ] Chave OpenAI com limite de gasto configurado
- [ ] PostgreSQL com usuário de menor privilégio (só SELECT/INSERT/UPDATE na schema nexa)

---

*Documento gerado em Março 2026 — manter atualizado conforme implementações avançam.*
