# FUNCIONALIDADE 3: Nexa Architect - Documentação Técnica

**Status:** Fase 1 - MVP Completo
**Responsável:** Nexa AI Team
**Última Atualização:** 19/02/2026

## 1. Visão Geral
O módulo **Nexa Architect** é um motor de decisão financeira que compara três estratégias principais para aquisição de bens de alto valor:
1.  **Financiamento (Debt-based):** Compra imediata com juros (PRICE/SAC).
2.  **Consórcio (Probability-based):** Compra a médio prazo com taxa administrativa e sorteio/lance.
3.  **Investimento (Equity-based):** Acumulação de capital com juros compostos a favor.

---

## 2. Status de Implementação

| Componente | Arquivo | Status | Observações |
|---|---|---|---|
| Schemas Pydantic | `app/architect/models.py` | ✅ Completo | SimulationRequest, SimulationResponse, enums |
| NPV/IRR | `app/architect/calculators/npv.py` | ✅ Completo | Newton-Raphson, guards de taxa |
| PRICE/SAC/CET | `app/architect/calculators/financing.py` | ✅ Completo | CET via Newton-Raphson unificado |
| Acumulação FV | `app/architect/calculators/investment.py` | ✅ Completo | PMT needed, months needed |
| Monte Carlo Consórcio | `app/architect/calculators/consortium.py` | ✅ Completo | 2000 iterações, sorteio + lance |
| Motor de decisão | `app/architect/simulators/strategy_engine.py` | ✅ Completo | 16 testes passando |
| Formatters | `app/architect/utils/formatters.py` | ✅ Completo | R$ 1.234,56, 12,50%, compacto |
| Date Helpers | `app/architect/utils/date_helpers.py` | ✅ Completo | months_between, business_days |
| Connector Base | `app/architect/connectors/base.py` | ✅ Completo | Cache 2 níveis, fallback automático |
| BACEN (SELIC) | `app/architect/connectors/bacen.py` | ✅ Completo | SGS série 432 |
| ANBIMA (CDI) | `app/architect/connectors/anbima.py` | ✅ Completo | SGS série 4391 |
| CETs de mercado | `app/architect/connectors/market_rates.py` | ✅ Completo | JSON local, path corrigido |
| Validator de input | `app/architect/validators/input_validator.py` | ✅ Completo | 7 regras de negócio |
| Validator de liquidez | `app/architect/validators/liquidity_validator.py` | ✅ Completo | 4 níveis de risco |
| Service orquestrador | `app/architect/services/architect_service.py` | ✅ Completo | Injeta safe_to_spend da F1 |
| API Routes | `app/api/v1/routes/architect.py` | ✅ Completo | POST /architect/simulate |
| ABAC (Consórcio stats) | `app/architect/connectors/abac.py` | 🔶 Stub | Fase 2 |
| Monte Carlo engine | `app/architect/simulators/monte_carlo.py` | 🔶 Stub | Fase 2 |
| Sensitivity Analyzer | `app/architect/simulators/sensitivity_analyzer.py` | 🔶 Stub | Fase 3 |
| Cache avançado | `app/architect/utils/cache.py` | 🔶 Stub | Fase 3 |
| DB Migrations | `app/db/migrations/003_create_architect_tables.sql` | 🔶 Pendente | Fase 1 (próximo) |
| DB Queries | `app/db/queries/architect_queries.py` | 🔶 Pendente | Fase 1 (próximo) |
| Testes de integração | `tests/architect/` | 🔶 Pendente | Fase 1 (próximo) |

**Progresso da Fase 1:** ~85% completo

---

## 3. Análise dos Componentes

### 3.1. Core Models (`models.py`)
Define as estruturas de dados fundamentais usando Pydantic.
-   **`SimulationRequest`**: Inputs do usuário. Campos obrigatórios: `user_id`, `target_amount`. Validações Pydantic: `down_payment < target_amount`, `target_date` no futuro.
-   **`SimulationResponse`**: Saída unificada com estratégia recomendada, NPVs, plano de ação, `liquidity_impact`, `confidence_score` e `warnings`.
-   **Enums**: `StrategyType`, `RiskProfile`, `AmortizationMethod`, `AssetType`.

### 3.2. Calculadoras Financeiras (`calculators/`)

#### `npv.py` — Net Present Value & IRR
-   **`calculate_npv`**: Traz fluxos futuros a valor presente — comparação justa entre estratégias de prazos diferentes.
-   **`calculate_irr`**: Newton-Raphson para TIR. Guard `<= -1` em todas as funções para evitar `ZeroDivisionError`.

#### `financing.py` — PRICE / SAC / CET
-   **`calculate_price`**: Sistema Francês — parcelas fixas. $PMT = PV \times \frac{i(1+i)^n}{(1+i)^n - 1}$.
-   **`calculate_sac`**: Amortização constante — parcelas decrescentes. SAC sempre mais barato que PRICE.
-   **`_calculate_cet`**: CET unificado via Newton-Raphson para PRICE e SAC. Inclui IOF e tarifas.

#### `investment.py` — Acumulação de Capital
-   **`calculate_pmt_needed`**: Depósito mensal para atingir meta em N meses.
-   **`calculate_months_needed`**: Meses até a meta dado um depósito fixo. Retorna `Optional[int]` (None se não converge).
-   **`generate_accumulation_schedule`**: Tabela mês a mês da evolução patrimonial.

#### `consortium.py` — Monte Carlo Consórcio
-   **`calculate_consortium_metrics`**: 2000 iterações simulando grupo de 200 participantes.
-   **Modelagem de sorteio**: Probabilidade $1/N$, onde $N$ decresce a cada mês.
-   **Modelagem de lance**: Distribuição normal que decai ao longo do tempo.
-   Entrega probabilidades de contemplação em 12m, 24m e 36m.

### 3.3. Strategy Engine (`simulators/strategy_engine.py`)
Classe `StrategyEngine` — cérebro da F3.

**Fluxo de decisão:**
1. `_simulate_financing()` → PRICE/SAC → NPV
2. `_simulate_investment()` → PMT/meses → NPV
3. `_simulate_consortium()` → Monte Carlo → NPV
4. Ranking por NPV (maior = menor custo presente)
5. Fallback de liquidez: se parcela > `max_monthly_budget`, passa para próxima estratégia
6. `_generate_action_plan()` → steps customizados por estratégia

**Decisão técnica:** sem dependência de `numpy` — usa `math.isnan`/`math.isinf` via `_safe_float()`.

**Testes:** 16 testes, 5 classes — ✅ 16 passed in 0.84s

### 3.4. Conectores (`connectors/`)

#### `base.py` — Classe Abstrata
-   Cache em 2 níveis: sucesso (TTL 1h padrão) + fallback (TTL 60s padrão).
-   Nunca bloqueia o usuário: API falha → retorna hardcoded automaticamente.
-   Subclasses implementam `fetch_rates()` e `get_fallback_rates()`.

#### `bacen.py` — SELIC
-   API: SGS série 432 do BCB (`api.bcb.gov.br`)
-   Fallback hardcoded: 13,25% a.a. (referência fev/2026)

#### `anbima.py` — CDI
-   API: SGS série 4391 do BCB (MVP — migrar para ANBIMA Developer API na Fase 2)
-   Fallback hardcoded: 13,15% a.a. (referência fev/2026)

#### `market_rates.py` — CETs de Mercado
-   Fonte: `data/architect/market_rates.json`
-   **Bug corrigido (19/02/2026):** `parents[4]` → `parents[3]` no path (arquivo estava sendo buscado na raiz do projeto em vez de `backend/`)
-   **Bug corrigido (19/02/2026):** CETs do IMOVEL estavam abaixo da SELIC (spread negativo). Corrigidos para SELIC 13,25% + spread 150-300bps.

| Bem | min | avg | max |
|---|---|---|---|
| IMOVEL | 14,75% | 15,25% | 16,25% |
| VEICULO | 16,20% | 19,50% | 24,50% |
| REFORMA | 22,00% | 31,00% | 45,00% |
| VIAGEM | 28,00% | 36,00% | 52,00% |
| OUTRO | 24,00% | 32,00% | 48,00% |

### 3.5. Validators (`validators/`) — NOVO

#### `input_validator.py` — Regras de Negócio
Valida o `SimulationRequest` com regras que vão além do Pydantic (campos em conjunto).

| Regra | Tipo | Exemplo de falha |
|---|---|---|
| `principal >= R$ 1.000` | Erro | down_payment muito alto |
| `down_payment <= 90% do target` | Erro | 95% de entrada |
| `max_monthly_budget >= R$ 100` | Erro | budget de R$ 50 |
| `financing_months` compatível com `asset_type` | Erro | 10 anos para VIAGEM |
| `target_amount` mínimo por tipo de bem | Erro | Imóvel de R$ 500 |
| `prefers_consortium` vs `include_consortium` | Warning | flags contraditórios |
| `target_date` vs `financing_months` | Warning | quer em 12m, financiamento de 84m |

Limites por tipo de bem:

| Tipo | Prazo máx. | Valor mínimo |
|---|---|---|
| IMOVEL | 420 meses (35 anos) | R$ 50.000 |
| VEICULO | 84 meses (7 anos) | R$ 5.000 |
| REFORMA | 120 meses (10 anos) | R$ 2.000 |
| VIAGEM | 60 meses (5 anos) | R$ 1.000 |
| OUTRO | 120 meses (10 anos) | R$ 1.000 |

#### `liquidity_validator.py` — Impacto de Liquidez
Calcula `liquidity_impact = -(monthly_payment / safe_to_spend)` e classifica o risco.

**Hierarquia de referência:**
1. `safe_to_spend` da F1 (preferido — reflete receita real)
2. `max_monthly_budget` do request (fallback com aviso)
3. Sem referência → retorna `impact=0.0` com aviso

**Thresholds:**

| Nível | Comprometimento | `is_sustainable` |
|---|---|---|
| `SAFE` | ≤ 25% | True |
| `WARNING` | 26–40% | True |
| `HIGH` | 41–70% | True |
| `CRITICAL` | > 70% | False |

### 3.6. Architect Service (`services/architect_service.py`) — NOVO
Orquestrador central. Ponto único de entrada da lógica de negócio.

**Fluxo do `simulate(request, safe_to_spend)`:**
1. `InputValidator.validate()` → erros bloqueantes lançam `ValueError`
2. `_fetch_market_rates()` → SELIC + CDI + CET com fallback silencioso + warning
3. `StrategyEngine.simulate()` → base response com NPV, estratégia, action plan
4. `LiquidityValidator.calculate()` → recalcula `liquidity_impact` com `safe_to_spend` real
5. `_compute_confidence()` → ajusta score por qualidade dos dados
6. `model_copy(update=...)` → response final consolidado

**`confidence_score` dinâmico:**

| Condição | Ajuste |
|---|---|
| Base (engine) | 0,85 |
| Dados reais da F1 disponíveis | +0,10 |
| Taxas de fallback (API offline) | −0,05 |
| Por aviso gerado (máx −0,10) | −0,02 |

**Injeção de dependência:** todos os conectores e engine são injetáveis via `__init__` (mock fácil em testes).

**Integração com F1:** o service recebe `safe_to_spend: Optional[float]` como parâmetro. A rota é responsável por buscá-lo do `NexaRunner` antes de chamar o service. Se F1 indisponível, degradação graciosa com `safe_to_spend=None`.

### 3.7. API Routes (`api/v1/routes/architect.py`) — NOVO
Registrada no `router.py` como rota 7.

#### `POST /architect/simulate`
Endpoint principal. Recebe `SimulationRequest`, retorna `SimulationResponse`.

**Fluxo:**
1. `_fetch_safe_to_spend(user_id)` → tenta buscar F1 via `NexaRunner(mode="dev")`, falha graciosa
2. `ArchitectService.simulate(request, safe_to_spend)` → resultado completo
3. `ValueError` → HTTP 422 Unprocessable Entity
4. `Exception` → HTTP 500 Internal Server Error

#### `GET /architect/health`
Health check do módulo. Retorna `{"status": "ok", "module": "architect", "timestamp": "..."}`.

---

## 4. Padrões e Decisões Técnicas

1. **Guards de taxa:** `<= -1` (não `< -1`) em todos os cálculos para evitar `ZeroDivisionError`.
2. **Capitalização composta:** conversão anual → mensal via `(1 + annual_rate) ** (1/12) - 1`.
3. **Totais derivados do schedule:** soma dos valores arredondados (consistência de arredondamento).
4. **Newton-Raphson:** sem clamp durante iterações; validação apenas no resultado final.
5. **Dataclasses:** cada calculator tem seu `Result` dataclass com `to_dict()` e `__all__` exports.
6. **Padrão Connector:** cache 2 níveis (sucesso + fallback), nunca bloqueia, TTL configurável.
7. **Degradação graciosa:** F1 indisponível → `safe_to_spend=None` → LiquidityValidator usa fallback → warning no response.
8. **Sem numpy no engine:** `math.isnan`/`math.isinf` via `_safe_float()` — elimina dependência pesada.

---

## 5. Próximos Passos

### Fase 1 — Pendentes
1. **DB Migrations** (`db/migrations/003_create_architect_tables.sql`) — tabela `architect_simulations`
2. **DB Queries** (`db/queries/architect_queries.py`) — CRUD de simulações (persistência do histórico)
3. **Testes de integração** (`tests/architect/`) — fluxo completo API → Service → Engine → Calculators

### Fase 2 (Dia 31–60)
4. **Monte Carlo avançado** (`simulators/monte_carlo.py`) — simulador genérico reutilizável
5. **ABAC Connector** (`connectors/abac.py`) — estatísticas reais de consórcio
6. **Testes do consórcio** (`tests/architect/test_consortium.py`)

### Fase 3 (Dia 61–90)
7. **Sensitivity Analyzer** (`simulators/sensitivity_analyzer.py`) — análise de sensibilidade
8. **Cache avançado** (`utils/cache.py`) — Redis para cache distribuído
9. **Benchmark de performance** — meta < 1s de resposta
