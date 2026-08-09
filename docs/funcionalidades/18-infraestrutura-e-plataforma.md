# 18 — Infraestrutura e Plataforma

> O que sustenta tudo: os robôs que rodam de madrugada, o cache, os padrões
> de resiliência e a máquina de testes que mantém a suíte verde.

## Em palavras simples

Grande parte do valor da Nexa chega SEM o usuário abrir o app: às 2h da manhã
um robô fotografa as tarifas, às 2h30 outro atualiza o catálogo de
investimentos do mercado inteiro, às 3h outro procura dinheiro parado, às 7h
sai o e-mail com o resumo do dia. Esta camada é o relógio que faz tudo isso
acontecer com segurança — inclusive quando há vários servidores rodando ao
mesmo tempo.

---

## Scheduler e jobs (`core/scheduler.py` + `app/jobs/`)

APScheduler com `CronTrigger`, ativado por `SCHEDULER_ENABLED=true`:

| Horário | Trigger | Job | Entrega |
|---|---|---|---|
| 02h00 | `hour=2, minute=0` | `fee_snapshot` | `bank_fee_history` (por usuário) + `bank_fee_trends` (baseline anônimo por banco) → alimenta D2/D4/V3 |
| 02h15 | `hour=2, minute=15` | `market_fees_refresh` | Tarifas publicadas no Open Finance → `market_fees_live.json` |
| 02h30 | `hour=2, minute=30` | `product_catalog_refresh` | Catálogo vivo de renda fixa (varredura completa do diretório) |
| 03h00 | `hour=3, minute=0` | `opportunity_scan` | Dinheiro parado + poupança sub-CDI por usuário → cards |
| 04h00 | `hour=4, minute=0` | `health_score_snapshot` | Série temporal do score (tendências 30/90d) |
| 05h30 | `hour=5, minute=30` | `intelligence_metrics` | Monitoramento de acurácia + calibração do Negociador |
| a cada 6h | `hour="*/6"` | `notification_scheduler` | Gera + entrega notificações (e-mail/in-app/push) |
| 07h00 | `hour=7, minute=0` | `daily_digest` | E-mail diário idempotente |

### Job Guard — lock distribuído (`jobs/_base.py`)

```python
_LOCK_PREFIX  = "nexa:job_lock:"
_JOB_LOCK_TTL = 7200          # 2 horas
```

O decorator `@job_guard("job_id")` faz `SET NX EX` no Redis — **operação
atômica**, segura em ambiente multi-worker (Railway roda múltiplas instâncias).
Se o lock já existe, o job simplesmente não roda naquele worker.

O TTL de 2 horas é o mecanismo anti-deadlock: se o processo morrer antes do
`_release_lock`, o lock expira sozinho e o job volta a rodar no próximo ciclo,
em vez de ficar travado para sempre.

**Fallback em memória** quando o Redis falha, com log de warning explícito —
protege contra re-entrada dentro do mesmo processo, mas não entre instâncias.

---

## Loops de aprendizado e monitoramento (`intelligence_metrics`, 05h30)

O gap histórico era "os dados de feedback existem mas nada os consome". O job
das 05h30 fecha isso em duas frentes.

### 1. Loop fechado do Negociador (F13)

O detector estima `potential_gain` por heurística; usuários reportam o desfecho
real. `compute_calibration()` calcula, por tipo de gatilho, o **fator de
realização** = mediana de `(ganho real ÷ estimado)` — com **"recusado" contando
como 0**, para que o fator reflita a taxa real de sucesso e não a média dos
vencedores. Mínimo de 5 desfechos; fator limitado a `[0,2 · 1,2]`.

O router aplica o fator **e declara a origem** ao usuário. Fórmulas completas
no [doc 08](08-negociador.md).

### 2. Monitoramento de acurácia em produção

Grava série temporal em `intelligence_metrics` — **uma linha por
dia × métrica × dimensão**:

| Métrica | Dimensão | Fonte |
|---|---|---|
| `reco_acceptance_rate` | `{insight_type}` | `recommendation_feedback` (janela de 30 dias) |
| taxa de sucesso do Negociador | por gatilho | `negotiation_history` |
| fator de realização | por gatilho | `compute_calibration()` |
| `fee_baseline_coverage` | `open_finance` | instituições no baseline vivo de tarifas |
| `fee_trends_coverage` | `users_agg` | bancos no agregado anônimo |
| `catalog_coverage` | `open_finance` | instituições no catálogo OPP |
| volume de mensagens | — | agente |

Cada linha carrega `samples` além do valor — uma taxa de aceitação de 100% com
2 amostras não é confundida com 100% em 200.

É a matéria-prima para enxergar se a inteligência melhora ou degrada ao longo
do tempo — a fundação que faltava para "recalibrar sozinho".

---

## Padrões de resiliência (transversais)

**Multi-layer fallback** — presente em todo o código:

| Camada primária | Fallback | Onde |
|---|---|---|
| ML | regras → default | classificadores (docs 05, 13) |
| API BACEN viva | taxa fixa versionada | conectores (docs 04, 08, 10) |
| Catálogo vivo | catálogo curado | OPP (doc 09) |
| Baseline vivo de tarifas | tabela estática | Raio-X (doc 06) |
| Redis | memória | locks, contadores, rate limit, cache |

**Fail-closed onde importa**: webhooks sem segredo em produção recusam (503);
CORS `*` em produção recusa o boot; `SECRET_KEY` mock em produção recusa o
boot.

**Idempotência**: digest (log por dia), webhooks Stripe (por `event_id`),
desafios (sync duplo não duplica), dedup de notificações por TTL de tipo +
fingerprint (doc 14).

---

## Dados e cache

**Stack**: PostgreSQL 16 + SQLAlchemy 2.0 + **Alembic** (15 migrations, cadeia
validada do zero em PG real por teste e2e); **Polars** para DataFrames;
**DuckDB** para histórico analítico/dev; **Redis** para cache, locks, sessões
do agente, blacklist de tokens e contadores.

### `core/cache.py`

```python
@cache_response(prefix="forecast", ttl=900)     # 15 min padrão
```

A chave carrega uma **versão de cache**:

```
nexa:cache:{_CACHE_VERSION}:{prefix}:{kwargs serializados}
```

Bumpar `_CACHE_VERSION` invalida tudo de uma vez — o caminho de escape quando o
formato da resposta muda. `invalidate_user_cache(user_id)` limpa por usuário
(chamado após o ETL). Funciona com handlers sync e async (dois wrappers).
Erros de Redis são tratados por `_on_redis_error` e degradam para "sem cache",
nunca para erro 500.

---

## Ferramentas de produto embutidas

### A/B testing determinístico (`core/ab_testing.py`)

```python
hash_input = f"{user_id}:{experiment_name}"
hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
normalized = (hash_value % 10_000) / 10_000.0
```

O bucketing é **determinístico**: mesmo `user_id` + mesmo experimento → sempre
a mesma variante, sem estado persistido e sem randomização que mudaria entre
sessões. Incluir o nome do experimento no hash garante que um usuário no grupo
de tratamento de um experimento não fique correlacionado no próximo.

MD5 é usado **apenas como função de bucketing uniforme** (não criptográfica) —
está anotado no código para não parecer um descuido de segurança.

`log_exposure` emite `AB_EXPOSURE user_id=… experiment=… variant=…` em formato
grepável (pivot por experimento + variante direto do log). Experimentos
graduados viram 100% TREATMENT.

### Explicabilidade

`core/explain.py` + explicações estruturadas no optimizer
(`RecommendationExplanation`), OPP e cashflow: todo número importante sai com o
"porquê" em português.

### Utilitários compartilhados

`core/recurrence.py` e `core/shadow_invoices.py` são compartilhados entre
módulos — a definição de "recorrente" é a mesma no ETL, no cashflow e nas
assinaturas.

---

## Testes e CI

- **2.489 testes coletados** (política: suíte 100% verde) — unitários por
  módulo, routers com `TestClient`, e2e seeded/fresh, **e2e Postgres real**
  (migrations do zero + ciclo completo de desafios), 31 testes de segurança,
  testes de conectores com `httpx.MockTransport` (**zero rede na suíte**).
- **Isolações do conftest**: rate limiter desativado; catálogo vivo do OPP
  isolado (suíte determinística mesmo onde o job diário já rodou).
- **CI GitHub Actions**: testes + `pip-audit` (CVE novo quebra o build).
- **Deploy**: Docker (3 variantes: `Dockerfile`, `.minimal`, `.railway`) +
  Railway (`railway.toml`) + pipeline AWS (S3 para frontend).

---

## O que NÃO faz / Gaps

- **Observabilidade**: sem Sentry/Prometheus/OpenTelemetry — logs existem,
  alertas não. Item recomendado antes de qualquer beta. O
  `intelligence_metrics` grava séries, mas nada as monitora ativamente.
- **Sem fila de mensagens** — jobs e webhooks são síncronos; volume alto
  pedirá worker/fila.
- **Os jobs iteram sobre todos os usuários ativos** (`get_active_user_ids`) de
  forma sequencial. Com base grande, uma janela de 2h (o TTL do lock) pode não
  bastar — não há particionamento nem paralelismo.
- **O fallback em memória do job lock não protege entre instâncias**: com Redis
  fora do ar e 3 workers, o mesmo job roda 3 vezes.
- **Sem relatório de cobertura** no repositório (os testes são coletáveis e
  verdes, mas o % de cobertura não é publicado).
- **Horários dos jobs são fixos em UTC do servidor** — não há ajuste para fuso
  do usuário no digest das 07h.
- **Frontend**: `frontend-react/` é protótipo de validação (React 19 + Vite +
  Tailwind), assumidamente descartável; o app oficial será construído do zero
  portando o `src/pwa` (widget + push, que são permanentes).
