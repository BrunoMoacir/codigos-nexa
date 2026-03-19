# NEXA AI — Estratégia Técnica e Roadmap de Engenharia
**Documento Interno — Março 2026**

---

## 1. Estado Atual do Projeto

### 1.1 Visão Geral da Stack

| Camada | Tecnologia Atual | Status |
|--------|-----------------|--------|
| Framework API | FastAPI 0.128 + Uvicorn | ✅ Produção |
| Banco de Dados | PostgreSQL 16 + asyncpg | ✅ Migrado (Alembic) |
| Cache / Sessões | Redis + RedisSaver (LangGraph) | ✅ Ativo |
| Agent AI | LangGraph + Claude Sonnet 4.6 | ✅ Claude integrado + fallback OpenAI |
| LLM Fallback | GPT-4o-mini (OpenAI) | ✅ Fallback automático |
| Autenticação | JWT (python-jose + bcrypt) | ✅ 100% das rotas protegidas |
| Rate Limiting | slowapi | ✅ /chat 20/min, /token 10/min |
| ORM / Migrations | SQLAlchemy async + Alembic | ✅ Engine async + engine síncrono legado |
| Containerização | Docker + Docker Compose | ✅ Funcional |
| CI/CD | GitHub Actions | ✅ test + docker-build pipeline |
| Frontend | Streamlit | ⚠️ Protótipo apenas |
| Open Finance | Pluggy API | ✅ Cliente real + mock |
| Testes | pytest (414 passing) | ⚠️ Lacunas nos tools do agente + MX |
| PII / LGPD | — | ⏳ ST1 PII Sanitizer (Fase 2) |

### 1.2 Funcionalidades Implementadas

```
✅ F1   — Motor Core (ETL, cashflow, safe-to-spend, shadow invoices)
✅ F2   — Card Optimizer (ranking, multi-card, custo de oportunidade)
✅ F3   — Nexa Architect (simulador de compra, Monte Carlo, sensibilidade)
✅ F4   — Nexa Divider (classificador PF/PJ ML, relatório fiscal)
✅ F5   — Raio-X de Custos Bancários (FeeDetector, BankFeeAnalyzer, benchmarks BACEN)
✅ F7   — Modo Compra Inteligente (PurchaseAdvisor, orquestra F2+F3, PRICE parcelado)
✅ F13  — Negotiator Bot (detector de oportunidades, scripts via Claude, 3 triggers)
✅ MX.1 — Health Score History (série temporal)
✅ MX.2 — Metas Financeiras
✅ MX.3 — Notificações Proativas
✅ MX.4 — Comparação com Pares (IBGE/POF)
✅ Budget Advisor (50/30/20)
✅ Detecção de Assinaturas
✅ Detecção de Anomalias de Gasto
✅ Agente Conversacional (13 tools, LangGraph ReAct + Claude Sonnet 4.6)

⏳ F14  — Stress Test de Eventos de Vida ("E se eu for demitido?")
⏳ F15  — Cash Sweeping (arbitragem de liquidez entre contas)
⏳ ST1  — PII Sanitizer Layer (anonimização antes do LLM — LGPD)
⏳ ST2  — Ensemble Classifier F4 (ML + Claude Haiku para baixa confiança)
```

### 1.3 Estrutura de Arquivos Relevante

```
backend/
├── app/
│   ├── main.py                      # FastAPI entry point
│   ├── runner.py                    # NexaRunner — pipeline completo
│   ├── api/v1/
│   │   ├── router.py                # Registro central das rotas (20 rotas)
│   │   └── routes/                  # 23 arquivos de endpoints
│   ├── agent/
│   │   ├── graph.py                 # Builder do agente LangGraph
│   │   ├── state.py                 # AgentState (Polars DataFrames)
│   │   └── tools/                   # 13 ferramentas financeiras
│   ├── etl/                         # Pipeline ETL (5 estágios)
│   ├── optimizer/                   # F2 — Otimizador de cartões
│   ├── architect/                   # F3 — Simulador de compras
│   ├── cashflow/                    # Engine de fluxo de caixa
│   ├── purchase/                    # F7 — Modo Compra Inteligente
│   │   ├── models.py                # PaymentMethod, PurchaseRecommendation, LiquidityImpact
│   │   └── purchase_advisor.py      # PurchaseAdvisor (orquestra F2+F3+BACEN)
│   ├── costs/                       # F5 — Raio-X de Custos Bancários
│   │   ├── models.py                # FeeType, FeeEntry, BankCostReport
│   │   ├── fee_detector.py          # FeeDetector (regex + institution_id mapping)
│   │   ├── bank_fee_analyzer.py     # BankFeeAnalyzer (agrega por banco/tipo)
│   │   └── market_fees_db.py        # MarketFeesDB (benchmarks 16 bancos)
│   ├── negotiator/                  # F13 — Negotiator Bot
│   │   ├── models.py                # NegotiationTrigger, NegotiationScript, NegotiationReport
│   │   ├── opportunity_detector.py  # NegotiationOpportunityDetector (3 triggers)
│   │   └── script_generator.py      # NegotiationScriptGenerator (Claude API)
│   ├── goals/ notifications/ peers/ # MX features
│   ├── integrations/open_finance/   # Pluggy real + mock
│   ├── db/
│   │   ├── queries.py               # DuckDB queries + get_transactions_for_user()
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

### F5 — Raio-X de Custos Bancários ✅ IMPLEMENTADO

**Objetivo:** Mapear tarifas ocultas de cada banco e calcular o Custo Bancário Total (CBT).

**Arquivos criados:**
- `app/costs/models.py` — `FeeType` (9 categorias), `FeeEntry`, `BankFeeSummary`, `MarketBenchmark`, `BankCostReport`
- `app/costs/fee_detector.py` — `FeeDetector`: detecção via regex + mapeamento de `institution_id` (16 bancos)
- `app/costs/bank_fee_analyzer.py` — `BankFeeAnalyzer`: agrega por banco/tipo, calcula economia potencial banco a banco
- `app/costs/market_fees_db.py` — `MarketFeesDB`: benchmarks de 16 bancos (digitais = R$0, tradicionais R$24–R$44/mês)
- `app/api/v1/routes/costs.py` — `GET /costs/raio-x/{user_id}` com JWT
- `app/agent/tools/get_bank_cost_analysis.py` — 12ª tool do agente
- `app/db/queries.py` — adicionado `get_transactions_for_user()` como ponto único de acesso ao DuckDB

**Categorias detectadas:** `ANUIDADE_CARTAO`, `TARIFA_MANUTENCAO`, `TED_DOC`, `SAQUE`, `JUROS_ROTATIVO`, `SEGURO_PRESTAMISTA`, `PACOTE_SERVICOS`, `IOF`, `OUTROS_CUSTOS`

**Decisões técnicas:**
- `FeeDetector` usa Python loop (`iter_rows`) com regex ordenados do mais específico ao mais genérico — trade-off documentado (vectorização em Fase 2)
- Economia potencial calculada banco a banco (não total vs. mínimo) para corretude econômica
- `_BENCHMARK_DIGITAL_REFERENCE` usa `.model_copy()` para evitar mutação do singleton

---

### F6 — Negociador Automático de Taxas → incorporado ao F13

Ver seção F13 abaixo.

---

### F7 — Modo Compra Inteligente ✅ IMPLEMENTADO

**Objetivo:** Antes de uma compra, recomendar o melhor método de pagamento.

**Arquivos criados:**
- `app/purchase/models.py` — `PaymentMethod` enum, `PurchaseRequest`, `PaymentOption`, `LiquidityImpact`, `PurchaseRecommendation`
- `app/purchase/purchase_advisor.py` — `PurchaseAdvisor`: orquestra F2 (melhor cartão) + F3/BACEN (financiamento) + F1 (safe-to-spend)
- `app/api/v1/routes/purchase.py` — `POST /purchase/analyze` com JWT
- `app/agent/tools/get_purchase_recommendation.py` — 11ª tool do agente

**Opções comparadas:** PIX à vista, cartão à vista, cartão parcelado (sem juros), financiamento (fórmula PRICE via BACEN CDC).

**Decisões técnicas:**
- `net_cost: Optional[float]` calculado via `@model_validator(mode="after")` — evita default 0 ambíguo
- `RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]` reaproveitado de `safe_to_spend.py`
- `recommended_net_cost: float` no `PurchaseRecommendation` — evita IndexError na tool ao acessar `options[0]`
- Financiamento só é gerado para valores >= R$1.000 e parcelas > 6

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
Usuário → POST /chat → AgentGraph (ReAct, 1 agente, 13 tools) → Resposta
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

### F13 — Negotiator Bot ✅ IMPLEMENTADO

**Objetivo:** Gerar roteiros personalizados (chat, telefone ou e-mail) para o usuário negociar taxas com o banco, usando dados reais do Nexa como argumento.

**Arquivos criados:**
- `app/negotiator/models.py` — `NegotiationTrigger`, `NegotiationChannel`, `NegotiationOpportunity`, `NegotiationScript`, `NegotiationRequest`, `NegotiationReport`
- `app/negotiator/opportunity_detector.py` — `NegotiationOpportunityDetector`: cruza FeeDetector (F5) + BACEN + health score
- `app/negotiator/script_generator.py` — `NegotiationScriptGenerator`: chama Claude Sonnet 4.6 com prompt especializado → JSON parseado em `NegotiationScript`
- `app/api/v1/routes/negotiator.py` — `POST /negotiator/generate-script` com JWT
- `app/agent/tools/get_negotiation_script.py` — 13ª tool do agente

**Triggers detectados:**
| Trigger | Condição | Janela |
|---------|----------|--------|
| `JUROS_ROTATIVO_ALTO` | Juros rotativos >= R$20 pagos em qualquer banco | Últimos 3 meses |
| `ANUIDADE_ALTA` | Anuidade mensal equivalente > R$30/mês | Últimos 12 meses |
| `HEALTH_SCORE_ALTO` | Score >= 70 sem outros triggers | Genérico proativo |

**Decisões técnicas:**
- `_fetch_market_rate_monthly()` resolvida **uma vez** em `detect()` e passada como parâmetro — zero chamadas HTTP duplicadas ao BACEN
- Iteração de meses via `_month_offset(ref, n)` com aritmética direta de ano/mês — evita bug do `timedelta(days=30*n)` que pode mapear dois offsets no mesmo mês
- `anthropic.Anthropic()` instanciado uma vez no `__init__` de `NegotiationScriptGenerator` e reutilizado como `self._client`
- `_fallback_script()` garante output útil mesmo quando Claude está indisponível
- Canal recomendado normalizado via `try/except ValueError` para aceitar strings fora do enum

---

### F14 — Simulação de Eventos de Vida (Stress Test)

**Objetivo:** Responder "E se?" para cenários de impacto financeiro: demissão, filho, doença, separação. A IA projeta uma linha do tempo de sobrevivência financeira baseada nos dados reais do usuário.

**Base existente — F1 (Core Engine) é o núcleo:**
- `app/cashflow/engine.py` — projeta cashflow mensal
- `app/cashflow/safe_to_spend.py` — calcula margem disponível
- `app/cashflow/burn_rate.py` — taxa de consumo atual
- `app/goals/tracker.py` — metas existentes (reserva de emergência MX.2)

**O que construir:**

1. **`app/stress_test/scenarios.py`** — definição dos cenários pré-configurados:
```python
LIFE_EVENTS = {
    "DEMISSAO":    {"income_shock": -1.0,  "expense_shock": +0.10, "description": "Perda total da renda"},
    "FILHO":       {"income_shock": 0.0,   "expense_shock": +0.30, "description": "Nascimento de filho"},
    "DOENCA":      {"income_shock": -0.40, "expense_shock": +0.20, "description": "Afastamento médico 3 meses"},
    "SEPARACAO":   {"income_shock": -0.50, "expense_shock": +0.15, "description": "Separação conjugal"},
    "RENDA_QUEDA": {"income_shock": -0.50, "expense_shock": 0.0,   "description": "Queda de 50% na renda"},
}
```

2. **`app/stress_test/simulator.py`** — motor de simulação:
```python
class LifeEventSimulator:
    def simulate(
        self,
        user_id: str,
        event_type: str,           # "DEMISSAO", "FILHO", etc.
        income_shock: float,       # -0.50 = renda cai 50%
        expense_shock: float,      # +0.30 = despesas sobem 30%
        horizon_months: int = 12,  # quantos meses projetar
    ) -> StressTestResult:
        """
        1. Busca cashflow atual (F1)
        2. Aplica os shocks de renda e despesa
        3. Projeta mês a mês com reserva de emergência (MX.2)
        4. Retorna: meses de sobrevivência, quando vai a zero,
                    o que cortar primeiro (burn_rate por categoria)
        """
```

3. **Nova rota:** `POST /api/v1/stress-test/simulate`

4. **Nova tool no agente:** `get_life_event_stress_test`:
   _"Nexa, quanto tempo eu sobrevivo se perder meu emprego?"_
   _"E se minha renda cair 50%?"_

---

### F15 — Arbitragem de Liquidez (Cash Sweeping)

**Objetivo:** Identificar saldo parado em contas de baixo rendimento e calcular o custo de oportunidade diário de não mover o dinheiro para conta/investimento de maior retorno.

**Base existente:**
- `app/cashflow/safe_to_spend.py` — calcula margem disponível (saldo "ocioso")
- `app/architect/connectors/bacen.py` — taxa SELIC/CDI em tempo real
- `app/architect/connectors/anbima.py` — CDI diário
- `app/notifications/notifier.py` — infraestrutura de alertas

**O que construir:**

1. **`app/liquidity/cash_sweeper.py`** — motor de análise:
```python
@dataclass
class SweepOpportunity:
    idle_balance: float          # Saldo parado (acima do safe_to_spend)
    current_yield_annual: float  # Rendimento atual (0% em CC sem rendimento)
    target_yield_annual: float   # CDI ou Selic disponível
    daily_cost: float            # Quanto perde por dia (CDI × idle_balance / 365)
    monthly_cost: float          # Projeção mensal
    recommendation: str          # Banco/produto recomendado (ex: "Nuconta 100% CDI")

class CashSweeper:
    def analyze(self, user_id: str) -> SweepOpportunity | None:
        # 1. Calcula saldo "ocioso" (current_balance - safe_to_spend_total)
        # 2. Busca CDI/SELIC do dia (BACEN connector)
        # 3. Calcula custo diário de oportunidade
        # 4. Retorna recomendação se idle_balance > R$100
```

2. **Nova rota:** `GET /api/v1/liquidity/sweep-analysis/{user_id}`

3. **Integração com MX.3 (notificações):** `notifier.py` dispara alerta diário
   _"Você deixou R$2.000 parados ontem. Isso custou R$0,73. Mova para o banco Y (100% CDI)."_

4. **Nova tool no agente:** `get_liquidity_sweep`

---

### ST1 — PII Sanitizer Layer (Privacidade por Design)

**Objetivo:** Garantir que nenhum dado pessoal identificável (nome de estabelecimento específico, ID de transação real, CPF, endereço) chegue ao LLM. Conformidade LGPD + confiança do usuário.

**Princípio:** O agente recebe apenas **contexto semântico** — nunca o log bruto da Pluggy.

**O que construir:**

1. **`app/agent/pii_sanitizer.py`** — pipeline de anonimização:
```python
class PIISanitizer:
    # Regras de sanitização:
    # "FARMÁCIA DROGASIL #247 SÃO PAULO" → "Farmácia (R$ 50)"
    # "TRANSF PIX JOÃO SILVA 123.456.789-00" → "Transferência PIX recebida (R$ 1.200)"
    # "MERCADO PINHEIROS SP LTDA" → "Supermercado (R$ 180)"
    # IDs de transação reais → hash anônimo
    # Saldo exato → faixa (ex: "entre R$3k e R$5k")

    def sanitize_transactions(self, df: pl.DataFrame) -> pl.DataFrame:
        """Retorna df com descrições e IDs anonimizados"""

    def sanitize_context(self, context: dict) -> dict:
        """Sanitiza o contexto completo antes de enviar ao LLM"""
```

2. **Integrar no pipeline do agente** (`agent/graph.py`): aplicar sanitizer **antes** de montar o contexto que vai para o LLM.

3. **Adicionar campo `pii_sanitized: bool`** no log de auditoria para rastreabilidade LGPD.

---

### ST2 — Ensemble de Modelos para Classificação F4

**Objetivo:** Usar o modelo de ML (Random Forest já treinado) para casos de alta confiança no classificador PF/PJ, e acionar o LLM (Claude Haiku — barato) somente para os casos com `ml_confidence < 0.70`. Economiza tokens e aumenta precisão.

**Base existente:**
- `app/etl/classifier.py` — classificador atual com campo `ml_confidence`
- `backend/models/` — modelos serializados `.pkl`

**O que construir:**

1. **`app/etl/ensemble_classifier.py`** — orquestrador:
```python
class EnsembleClassifier:
    CONFIDENCE_THRESHOLD = 0.70  # Abaixo disso → chamar LLM

    def classify(self, df: pl.DataFrame) -> pl.DataFrame:
        # 1. Roda ML classifier em todos os registros
        # 2. Alta confiança (>= 0.70): aceita resultado do ML
        # 3. Baixa confiança (< 0.70): envia descrição para Claude Haiku
        #    com prompt: "Esta transação é PF ou PJ? Responda apenas PF ou PJ."
        # 4. Combina resultados, anota source: "ML" | "LLM"
        # 5. Retorna df com coluna pf_pj_label e classification_source
```

2. **Substituir chamada** em `runner.py` de `TransactionClassifier` para `EnsembleClassifier` quando `ANTHROPIC_API_KEY` disponível.

3. **Logging:** Registrar quantos % foram classificados por ML vs. LLM para monitoramento de custo.

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

### Fase 1 — Estabilização ✅ CONCLUÍDA (Março 2026)

| # | Tarefa | Status |
|---|--------|--------|
| 1 | JWT em todas as rotas (16 arquivos) | ✅ |
| 2 | SECRET_KEY via pydantic settings | ✅ |
| 3 | PostgreSQL async (asyncpg) + Alembic | ✅ |
| 4 | Redis checkpointer no agente (fallback MemorySaver) | ✅ |
| 5 | Rate limiting: slowapi (`/chat` 20/min, `/token` 10/min) | ✅ |
| 6 | GitHub Actions CI (test + docker build) | ✅ |
| 7 | Migração LLM: `_build_llm()` com Claude + fallback OpenAI | ✅ |
| 8 | Rota `analyze.py` ativada | ✅ |
| 9 | `ANTHROPIC_API_KEY`, `REDIS_URL`, `LLM_PROVIDER` no config | ✅ |

### Fase 2 — Novas Features (Meses 2–6)

Ordem recomendada por custo/benefício:

| Prioridade | Feature | Reutiliza | Status |
|-----------|---------|-----------|--------|
| 1 | F7 Modo Compra Inteligente | F2 + F3 (80% pronto) | ✅ |
| 2 | F5 Raio-X de Custos Bancários | ETL classifier + knowledge_cards | ✅ |
| 3 | F13 Negotiator Bot | health_score + BACEN + Claude | ✅ |
| 4 | **F14 Stress Test Eventos de Vida** | F1 cashflow engine + MX.2 | ⏳ |
| 5 | **F15 Cash Sweeping** | safe_to_spend + BACEN CDI + notifier | ⏳ |
| 6 | F8 Radar de Produtos | knowledge_cards + notifier | ⏳ |
| 7 | F9 Transparência Radical | F5 + income_profiler | ⏳ |
| 8 | F11 Score Nexa | health_score (já existe) | ⏳ |

### Melhorias Técnicas em Paralelo (Fase 2)

| Melhoria | Descrição | Status |
|----------|-----------|--------|
| **ST1 PII Sanitizer** | Anonimizar dados antes do LLM (LGPD) | ⏳ |
| **ST2 Ensemble F4** | ML > 70% confiança + Claude Haiku para casos difíceis | ⏳ |

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

- [x] `SECRET_KEY` via pydantic settings (lê do `.env`, não hardcoded)
- [ ] `SECRET_KEY` com valor forte (64 chars) em produção — **pendente configuração do .env**
- [ ] Credenciais do `.env` fora do repositório (usar GitHub Secrets ou vault)
- [x] JWT em 100% das rotas com dados de usuário (16 rotas protegidas)
- [x] Rate limiting em `/chat` (20/min) e `/api/v1/auth/token` (10/min)
- [ ] HTTPS obrigatório (nginx com Let's Encrypt ou CloudFlare)
- [ ] CORS restrito ao domínio do frontend
- [ ] Logs sem PII (CPF, saldo, nome do usuário) — **ST1 PII Sanitizer pendente**
- [ ] Chave Pluggy rotacionada antes de qualquer demo pública
- [ ] Chave OpenAI com limite de gasto configurado
- [ ] PostgreSQL com usuário de menor privilégio (só SELECT/INSERT/UPDATE na schema nexa)

---

---

*Documento gerado em Março 2026 — última atualização 19/03/2026.*
*Fase 1 (Estabilização) concluída. F5, F7 e F13 implementados. Próximas: F14, F15, ST1, ST2.*
