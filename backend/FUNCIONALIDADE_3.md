# FUNCIONALIDADE 3: Nexa Architect - Documentação Técnica

**Status:** Em Desenvolvimento (Fase 1 - MVP)
**Responsável:** Nexa AI Team
**Última Atualização:** 18/02/2026

## 1. Visão Geral
O módulo **Nexa Architect** é um motor de decisão financeira que compara três estratégias principais para aquisição de bens de alto valor:
1.  **Financiamento (Debt-based):** Compra imediata com juros (PRICE/SAC).
2.  **Consórcio (Probability-based):** Compra a médio prazo com taxa administrativa e sorteio/lance.
3.  **Investimento (Equity-based):** Acumulação de capital com juros compostos a favor.

---

## 2. Análise dos Componentes Implementados

### 2.1. Core Models (`models.py`)
Define as estruturas de dados fundamentais usando Pydantic.
-   **`SimulationRequest`**: Contém todos os inputs do usuário (valor alvo, entrada, perfil de risco).
-   **`SimulationResponse`**: Estrutura unificada de saída, contendo a estratégia recomendada, comparação de NPVs e planos de ação.
-   **Enums**: `StrategyType`, `RiskProfile`, `AmortizationMethod` garantem consistência nos tipos de dados.
-   **Integração**: Serve como contrato entre o Frontend, API e os Calculators.

### 2.2. Calculadoras Financeiras (`calculators/`)

#### a) `npv.py` (Net Present Value & IRR)
Motor matemático central para comparação justa entre estratégias com fluxos de caixa diferentes no tempo.
-   **`calculate_npv`**: Traz todos os fluxos futuros para valor presente. Essencial para comparar uma dívida de 5 anos (Financiamento) com uma espera de 2 anos (Consórcio).
-   **`calculate_irr`**: Calcula a Taxa Interna de Retorno. Implementa o método de Newton-Raphson para encontrar a raiz da equação $NPV(rate) = 0$.
    -   *Destaque Técnico:* Tratamento robusto para não-convergência e taxas negativas.

#### b) `financing.py` (Sistemas de Amortização)
Simulador de empréstimos bancários.
-   **`calculate_price`**: Implementa o Sistema Francês (parcelas fixas). Usa a fórmula clássica $PMT = PV \times \frac{i(1+i)^n}{(1+i)^n - 1}$.
-   **`calculate_sac`**: Implementa o Sistema de Amortização Constante. Amortização é fixa ($P/n$), e juros decrescem com o saldo devedor.
-   **`compare_methods`**: Executa ambas as simulações para dar ao usuário o comparativo lado a lado.
-   **CET (Custo Efetivo Total)**: Calcula a taxa real anual incluindo IOF e tarifas, resolvendo a equação de fluxo de caixa via métodos numéricos.

#### c) `investment.py` (Acumulação de Capital)
Simulador de investimentos para a estratégia de "Poupar".
-   **`calculate_future_value`**: Projeta quanto o usuário terá no futuro dado um aporte mensal e taxa.
-   **`calculate_pmt_needed`**: Processo inverso — calcula quanto é preciso poupar por mês para atingir uma meta.
-   **`generate_accumulation_schedule`**: Gera a tabela mês a mês da evolução patrimonial, crucial para mostrar ao usuário o poder dos juros compostos.

### 2.3. Utilitários (`utils/`)

#### a) `formatters.py`
Padronização de exibição.
-   Garante que valores monetários (`R$ 1.234,56`) e percentuais (`12,50%`) sejam exibidos consistentemente em toda a aplicação. Resolve problemas de ponto flutuante na exibição.

#### b) `date_helpers.py`
Manipulação temporal precisa.
-   **`business_days_between`**: Cálculo exato de dias úteis (Seg-Sex), fundamental para cálculos de pro-rata dia em taxas bancárias.
-   **`add_months`**: Tratamento correto de viradas de ano e meses com dias diferentes (ex: 31 Jan + 1 mês = 28/29 Fev).

---

#### d) `consortium.py` (Simulador Estocástico) - **IMPLEMENTADO**
Simulador probabilístico para consórcios.
-   **`calculate_consortium_metrics`**: Orquestra a simulação de Monte Carlo (2000 iterações) para determinar o perfil de risco do consórcio.
-   **`_simulate_single_run`**: Simula a trajetória de *um* participante em um grupo de 200 pessoas.
    -   *Modelagem de Sorteio*: Probabilidade de $1/N$, onde $N$ decresce a cada mês.
    -   *Modelagem de Lance*: Lances vencedores modelados como distribuição normal que decai ao longo do tempo.
-   **Propósito**: Entrega ao usuário não apenas o custo, mas a *probabilidade* de ter o bem em mãos em 12, 24 ou 36 meses.

### 2.4. Strategy Engine (`simulators/strategy_engine.py`) - **IMPLEMENTADO**
O cérebro da operação. Classe `StrategyEngine` com método principal `simulate()`.
-   **Responsabilidade**: Orquestrar as 3 simulações e recomendar a melhor estratégia.
-   **Fluxo de Decisão**:
    1.  `_simulate_financing()` → Calcula PRICE ou SAC via `fin_calc`, gera cashflows e calcula NPV.
    2.  `_simulate_investment()` → Calcula PMT ou meses necessários via `inv_calc`, gera cashflows e calcula NPV.
    3.  `_simulate_consortium()` → Executa Monte Carlo via `cons_calc`, gera cashflows e calcula NPV.
    4.  **Ranking por NPV**: Ordena estratégias do maior NPV (menor custo presente) para o menor.
    5.  **Validação de Liquidez**: Se a parcela da melhor estratégia excede `max_monthly_budget`, faz fallback automático para a próxima.
    6.  `_generate_action_plan()` → Gera `ActionStep` customizados para a estratégia vencedora.
-   **Decisão Técnica**: Removido `numpy` como dependência — substituído por `math.isnan`/`math.isinf` via helper `_safe_float()`.
-   **Retorno**: `SimulationResponse` (Pydantic) com custos, NPVs, probabilidades, impacto de liquidez e plano de ação.

### 2.5. Conectores (`connectors/`) - **IMPLEMENTADOS**
Camada de acesso a dados externos com resiliência.

#### a) `base.py` (Classe Abstrata)
-   Cache em memória com TTL configurável.
-   Fallback automático se API externa falhar.
-   Subclasses implementam `fetch_rates()` e `get_fallback_rates()`.

#### b) `bacen.py` (Banco Central)
-   Busca **Taxa SELIC** meta anual via API SGS do BCB (série 432).
-   Fallback: taxa hardcoded (10,75% a.a.).

#### c) `anbima.py` (CDI)
-   Busca **Taxa CDI** anual via API SGS do BCB (série 4391, MVP).
-   Plano futuro: migrar para ANBIMA Developer API.

#### d) `market_rates.py` (CETs de Mercado)
-   Lê CETs por tipo de bem (Imóvel, Veículo, Reforma, etc.) de `data/architect/market_rates.json`.
-   Oferece `get_best_cet()` e `get_avg_cet()` por `AssetType`.

### 2.6. Testes (`tests/architect/`) - **IMPLEMENTADO**

#### `test_strategy_engine.py` — 16 testes, 5 classes
| Classe | Testes | Cobertura |
|--------|--------|-----------|
| `TestStrategyEngineBasic` | 5 | Retorno válido, custos, NPV, meses, fontes |
| `TestConsortiumSimulation` | 3 | Toggle consórcio on/off, probabilidades |
| `TestBudgetConstraints` | 3 | Budget apertado → fallback, liquidez negativa |
| `TestActionPlan` | 2 | Steps sequenciais, steps críticos |
| `TestHelpers` | 3 | Métodos internos de cada simulação |

**Resultado:** ✅ 16 passed in 0.84s

---

## 3. Próximos Passos de Implementação
1.  **Validators** (`validators/input_validator.py`, `liquidity_validator.py`) — Validação de entrada e checagem de liquidez com `safe_to_spend` da F1.
2.  **Architect Service** (`services/architect_service.py`) — Orquestrador que conecta API → Connectors → StrategyEngine → Response.
3.  **API Routes** (`api/v1/routes/architect.py`) — Endpoint `POST /architect/simulate`.
4.  **Testes de Integração** — Testar o fluxo completo API → Service → Engine → Calculators.
