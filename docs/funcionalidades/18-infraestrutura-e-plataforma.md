# 18 — Infraestrutura e Plataforma

> O que sustenta tudo: os robôs que rodam de madrugada, o cache, os padrões
> de resiliência e a máquina de testes que mantém 2.285+ testes verdes.

## Em palavras simples

Grande parte do valor da Nexa chega SEM o usuário abrir o app: às 2h da manhã
um robô fotografa as tarifas, às 2h30 outro atualiza o catálogo de
investimentos do mercado inteiro, às 3h outro procura dinheiro parado, às 7h
sai o e-mail com o resumo do dia. Esta camada é o relógio que faz tudo isso
acontecer com segurança — inclusive quando há vários servidores rodando ao
mesmo tempo.

## Scheduler e jobs (`core/scheduler.py` + `app/jobs/`)

APScheduler com **lock distribuído Redis** (`SET NX EX`, padrão Job Guard com
fallback em memória) — em multi-instância, cada job roda UMA vez. Ativado por
`SCHEDULER_ENABLED=true`.

| Horário | Job | Entrega |
|---|---|---|
| 02h00 | `fee_snapshot` | Histórico de tarifas por usuário + baseline anonimizado de mercado (alimenta D2/D4/V3) |
| 02h30 | `product_catalog_refresh` | Catálogo vivo de renda fixa via Open Finance (varredura completa do diretório) |
| 03h00 | `opportunity_scan` | Dinheiro parado e poupança sub-CDI por usuário → cards |
| 04h00 | `health_score_snapshot` | Série temporal do score (tendências 30/90d) |
| 05h30 | `intelligence_metrics` | **Monitoramento de acurácia + loops de aprendizado** (ver abaixo) |
| a cada 6h | `notification_scheduler` | Gera + entrega notificações (e-mail/in-app/push) |
| 07h00 | `daily_digest` | E-mail diário idempotente |

## Loops de aprendizado e monitoramento de acurácia (`intelligence_metrics`)

O gap histórico era "os dados de feedback existem mas nada os consome". O job
das 05h30 fecha isso em duas frentes:

**1. Loop fechado do Negociador (F13).** O detector estima `potential_gain`
por heurística; usuários reportam o desfecho real (`PATCH /negotiator/history/
{id}`: sucesso/parcial/recusado + ganho). `compute_calibration()` calcula, por
tipo de gatilho, o **fator de realização** = mediana de (ganho real ÷
estimado) — com "recusado" contando como 0 (o fator reflete a taxa real de
sucesso, não só os vencedores). Só vira fator com ≥5 desfechos; limitado a
[0.2, 1.2] contra outliers. O router do Negociador aplica o fator ao ganho
apresentado **e declara a origem** ao usuário ("estimativa ajustada por 12
negociações reais") — nunca calibração silenciosa. Persistido em
`data/negotiator_calibration.json` (runtime, gitignored).

**2. Monitoramento de acurácia em produção.** Grava série temporal em
`intelligence_metrics` (uma linha por dia×métrica×dimensão): taxa de aceitação
das recomendações por tipo de insight (de `recommendation_feedback`), taxa de
sucesso e fator de realização do Negociador, cobertura dos catálogos vivos
(tarifas, produtos) e volume de mensagens do agente. É a matéria-prima para
enxergar se a inteligência melhora ou degrada ao longo do tempo — a fundação
que faltava para "recalibrar sozinho".

## Padrões de resiliência (transversais)

- **Multi-layer fallback**: ML → regras → default (classificadores); API
  BACEN viva → taxa fixa (conectores); catálogo vivo → curado (OPP); Redis →
  memória (locks, contadores, rate limit).
- **Fail-closed onde importa**: webhooks sem segredo em produção recusam;
  CORS `*` em produção recusa o boot; SECRET_KEY mock em produção recusa.
- **Idempotência**: digest (log por dia), webhooks Stripe (event id),
  desafios (sync duplo não duplica), dedup de notificações por TTL.

## Dados e cache

- **PostgreSQL 16** + SQLAlchemy 2.0 + **Alembic** (cadeia de migrations
  validada do zero em PG real por teste e2e); **Polars** para DataFrames;
  **DuckDB** para histórico analítico/dev; **Redis** para cache, locks,
  sessões do agente, blacklist de tokens e contadores.
- `core/cache.py`: decorator `cache_response(prefix, ttl)` + invalidação por
  usuário.

## Ferramentas de produto embutidas

- **A/B testing determinístico** (`core/ab_testing.py`): variante por hash
  do user_id — sem randomização instável entre sessões.
- **Explicabilidade** (`core/explain.py` + explicações estruturadas no
  optimizer/OPP): todo número importante sai com o "porquê" em português.
- **Recorrência** (`core/recurrence.py`) e shadow invoices (`core/
  shadow_invoices.py`) compartilhados entre módulos.

## Testes e CI

- **2.285+ testes** (política: suíte 100% verde) — unitários por módulo,
  routers com TestClient, e2e seeded/fresh, e2e Postgres real (migrations do
  zero + ciclo de desafios), 31 testes de segurança, testes de conectores com
  `httpx.MockTransport` (zero rede na suíte).
- Isolações importantes do conftest: rate limiter desativado; catálogo vivo
  do OPP isolado (suíte determinística mesmo onde o job diário já rodou).
- **CI GitHub Actions**: testes + `pip-audit` (CVE novo quebra o build).
- Deploy: Docker (3 variantes) + Railway (`railway.toml`).

## O que NÃO faz / Gaps

- **Observabilidade**: sem Sentry/Prometheus/OpenTelemetry — logs existem,
  alertas não. Item recomendado antes de qualquer beta.
- **Sem fila de mensagens** — jobs e webhooks são síncronos; volume alto
  pedirá worker/fila.
- **Sem relatório de cobertura** no repositório (os 2.285 testes são
  coletáveis e verdes, mas o % de cobertura não é publicado).
- **Frontend**: `frontend-react/` é protótipo de validação (React 19 + Vite +
  Tailwind), assumidamente descartável; o app oficial será construído do zero
  portando o `src/pwa` (widget + push, que são permanentes).
