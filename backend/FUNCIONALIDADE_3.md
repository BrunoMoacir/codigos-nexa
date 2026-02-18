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

## 3. Próximos Passos de Implementação
O foco agora é implementar o **Simulador de Consórcio (`consortium.py`)**, que introduz uma complexidade estocástica (probabilística) ao sistema, diferentemente das calculadoras determinísticas acima.

### Plano para `consortium.py`:
1.  **Modelo Matemático**: Utilizar Simulação de Monte Carlo.
2.  **Variáveis**: Número de participantes, taxa de administração, fundo de reserva, lance livre/fixo.
3.  **Output**: Probabilidade de contemplação em X meses e Custo Financeiro esperado.

#### d) `consortium.py` (Simulador Estocástico) - **NOVO**
Simulador probabilístico para consórcios.
-   **`calculate_consortium_metrics`**: Orquestra a simulação de Monte Carlo (padrão 2000 iterações) para determinar o perfil de risco do consórcio.
-   **`_simulate_single_run`**: Simula a trajetória de *um* participante em um grupo de 200 pessoas.
    -   *Modelagem de Sorteio*: Probabilidade de $1/N$, onde $N$ decresce a cada mês.
    -   *Modelagem de Lance*: Lances vencedores modelados como uma distribuição normal que decai ao longo do tempo (lances são mais altos no início).
-   **Propósito**: Entrega ao usuário não apenas o custo, mas a *probabilidade* de ter o bem em mãos em 6, 12 ou 24 meses, algo que calculadoras tradicionais ignoram.

### 2.4. Strategy Engine (`simulators/strategy_engine.py`) - **NOVO**
O cérebro da operação.
-   **Responsabilidade**: Orquestrar as 3 simulações (Financiamento, Consórcio, Investimento) e recomendar a melhor.
-   **Lógica de Decisão**:
    1.  Calcula os cenários paralelamente.
    2.  Calcula NPV (Valor Presente Líquido) de cada fluxo de caixa para tornar comparáveis valores no tempo.
    3.  Aplica restrições de liquidez (Parcela < Budget).
    4.  Classifica estratégias por NPV (maior é melhor, ou seja, menor custo presente).
    5.  Gera `ActionStep` (plano prático) customizado para a estratégia vencedora.
-   **Status**: Implementado. Integra as calculadoras e conecta as pontas.
