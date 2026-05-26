# Nexa Architect — F3: Motor de Simulação Financeira

## Visão Geral

O **Nexa Architect** é o módulo de inteligência financeira da plataforma Nexa. Ele compara estratégias de aquisição de bens (imóvel, veículo, reforma, viagem etc.) e recomenda a melhor opção para o perfil do usuário, baseando-se em matemática financeira rigorosa, simulações probabilísticas e raciocínio assistido por LLM.

**Critério principal de decisão:** VPL (Valor Presente Líquido) — a estratégia com maior VPL (menos negativo) vence, representando o menor custo em valor presente.

---

## Sumário

1. [Estratégias Simuladas](#1-estratégias-simuladas)
2. [Pipeline de Execução](#2-pipeline-de-execução)
3. [Camada de Calculadores](#3-camada-de-calculadores)
4. [Motor de Estratégia (StrategyEngine)](#4-motor-de-estratégia-strategyengine)
5. [Score de Risco (RiskScorer)](#5-score-de-risco-riskscorer)
6. [Raciocínio LLM (LLMReasoner)](#6-raciocínio-llm-llmreasoner)
7. [Calibração Contínua (CalibrationPipeline)](#7-calibração-contínua-calibrationpipeline)
8. [Conectores de Mercado](#8-conectores-de-mercado)
9. [Simuladores Probabilísticos](#9-simuladores-probabilísticos)
10. [Validadores](#10-validadores)
11. [Open Finance Pipeline](#11-open-finance-pipeline)
12. [Utilitários](#12-utilitários)
13. [Persistência (ORM e Queries)](#13-persistência-orm-e-queries)
14. [API REST (Router)](#14-api-rest-router)
15. [Modelos e Schemas](#15-modelos-e-schemas)
16. [Configuração e Ambiente](#16-configuração-e-ambiente)
17. [Fluxo Completo — Exemplo](#17-fluxo-completo--exemplo)
18. [Arquitetura de Arquivos](#18-arquitetura-de-arquivos)

---

## 1. Estratégias Simuladas

O módulo compara **5 estratégias de aquisição**:

| Código | Nome | Descrição |
|--------|------|-----------|
| `FINANCING` | Financiamento | PRICE ou SAC, com IOF e CET real via Newton-Raphson |
| `CONSORTIUM` | Consórcio | Monte Carlo de contemplação por sorteio e lance |
| `SAVE_INVEST` | Poupar e Investir | Acumular o valor em renda fixa/variável |
| `FINANCING_RENTAL` | Financiamento + Aluguel | Financia e aluguéis cobrem as parcelas |
| `CONSORTIUM_SELIC_RENTAL` | Consórcio + SELIC + Aluguel | Consórcio alavancado com renda de aluguel |

---

## 2. Pipeline de Execução

O `ArchitectService` orquestra **8 etapas** sequenciais para cada requisição:

```
1. InputValidator          → valida regras de negócio cruzadas
2. Calibração (TTL 5min)   → carrega thresholds calibrados do DuckDB
3. RiskScore               → infere score contínuo [0,1] das transações
4. Taxas de Mercado        → BACEN, ANBIMA, BCB/MarketRates, IPCA, ABAC
5. Open Finance            → sobrepõe CET real, rendimento real, adimplência
6. StrategyEngine.simulate → calcula VPL + SSD de todas as estratégias
7. LLMReasoner.reason      → verificação de consistência + possível re-run + narrativa
8. Pós-processamento       → liquidez, confiança, bônus cartão, advisor de orçamento
```

### Cálculo de Confiança

```
base = 0.50
+ 0.10 se dados Open Finance disponíveis
+ 0.10 se dados F1 (Core Engine) disponíveis
- 0.05 se taxas são fallback (API externa falhou)
- 0.02 × n_warnings (máx -0.10)
Resultado: clamp([0.30, 1.00])
```

---

## 3. Camada de Calculadores

### 3.1 Financiamento (`calculators/financing.py`)

Suporta dois métodos de amortização:

**PRICE (prestação constante):**
```
PMT = PV × i / (1 - (1+i)^-n)
```

**SAC (amortização constante):**
```
Amortização = PV / n
Juros_k = Saldo_k × i
Correção monetária (TR/IPCA): saldo ajustado mensalmente
```

**IOF** (Res. BACEN 3.516/2007):
- Fixo: 0,38% sobre o principal
- Diário: 0,0082%/dia sobre cada amortização (cap 3%)

**Seguro por tipo de bem:**
- Imóvel: 0,035%/mês sobre saldo devedor
- Veículo: 0,20%/mês sobre saldo devedor

**CET** (Custo Efetivo Total): Newton-Raphson sobre `principal_líquido vs pagamentos + seguro`.

### 3.2 Investimento (`calculators/investment.py`)

Modela a estratégia de acumulação progressiva:

- **IR por depósito**: cada aporte tem seu próprio prazo de carência e alíquota
  - ≤180d → 22,5% | ≤360d → 20% | ≤720d → 17,5% | >720d → 15%
- **Come-cotas**: dedução de IR a cada 6 meses para fundos (alíquota 15%)
- **Tax-exempt**: LCI/LCA sem IR
- **PMT**: fórmula fechada O(1) quando saldo inicial = 0, iterativo caso contrário
- **Retorno real**: `fv_real = fv_nominal / (1 + IPCA)^(meses/12)`

### 3.3 VPL / TIR (`calculators/npv.py`)

- **VPL (Fisher)**: `r_real = (1+r_nominal)/(1+inflação) - 1` quando inflação > 0
- **TIR**: Newton-Raphson com tentativas múltiplas [0.01, 0.10, 0.50, 1.0]
  - Regra de Descartes: detecta múltiplas raízes
- **Helpers**: `discount_cashflow`, `present_value_annuity`, `future_value_annuity`

### 3.4 Consórcio — Monte Carlo (`calculators/consortium.py`)

Simula 2.000 cenários de contemplação:

- **Distribuição dos lances**: log-normal com decaimento exponencial da média
  - `bid_mean` decai ao longo do prazo (half-life = 30% do prazo)
- **Reajuste anual**: INCC ≈ IPCA × 1,5 para imóveis; IPCA para demais
- **Saída**: percentis P10/P25/P50/P75/P90 do mês de contemplação
- **Parâmetros calibráveis**: `bid_mean_initial` e `bid_std` via CalibrationPipeline

### 3.5 Otimizador de Alavancagem (`calculators/leverage_optimizer.py`)

Testa multiplicadores de alavancagem de **1,2x a 3,0x** (passo 0,1x):

- Por cenário: simula mês a mês (renda SELIC + aluguel − parcela consórcio)
- **Auto-sustentável**: saldo nunca negativo durante o prazo
- **Ótimo**: maior `patrimônio_final` dentre os cenários auto-sustentáveis
- `quick_viability_check()`: check rápido em 2,0x sem simulação completa

---

## 4. Motor de Estratégia (StrategyEngine)

Arquivo: `simulators/strategy_engine.py` (~1.920 linhas). Pure math, sem I/O.

### Fluxo de Decisão

```
1. Simular todas as estratégias → calcular VPLs
2. SSD override: se uma estratégia domina estocasticamente todas as outras
3. Ajuste por perfil de risco (conservador nunca financia veículo; requer vantagem mínima de VPL)
4. Verificação de constraint de orçamento
5. Seleção de estratégia eficiente (scoring secundário)
```

### Taxa de Investimento por Perfil

```python
_get_investment_rate(cdi, risk_profile, risk_score):
    # Interpola continuamente entre CDI_net e min(CDI×1.60, 18%)
    # Usa risk_score [0,1] quando disponível, profile enum como fallback
```

| Perfil | Taxa |
|--------|------|
| Conservador | CDI × 0,85 (net IR 15%) |
| Moderado | CDI × 1,0 a 1,2 (proporcional ao score) |
| Agressivo | min(CDI × 1,6, 18%) |

### Ajuste Conservador

```python
_apply_risk_profile_adjustment():
    # conservador + veículo → nunca financia (usa consórcio ou save_invest)
    # conservador + outro   → FINANCING só vence se VPL_FIN > VPL_SI × (1 + margem)
    # margem: 25% em score=0, interpolada a 15% em score=0.35
```

### Simulação Macro — VAR(1)

```python
_run_macro_simulation():
    # 2.000 trajetórias de (Selic, IPCA, apreciação_ativo)
    # Modelo VAR(1): X_t = A × X_(t-1) + ε
    # Correlações históricas via Cholesky
    # Saída: P10/P50/P90 por mês + CVaR95 + matriz SSD
```

### SSD (Dominância Estocástica de Segunda Ordem)

Uma estratégia A domina B por SSD se:
- Integral acumulada da CDF de A ≤ integral acumulada da CDF de B **para todo** x
- Garante preferência de qualquer agente avesso a risco

### Break-even CET

```python
_find_break_even_cet():
    # Busca binária (60 iterações) para CET onde VPL_FIN == VPL_SAVE_INVEST
    # Acurácia: ±0.01 p.p.

_compute_breakeven_surface():
    # 5.000 amostras Monte Carlo com (Selic, IPCA) correlacionados
    # Bisseção vetorizada → distribuição do CET break-even
```

### Análise de Timing — M3.4

```python
simulate_timing_scenarios():
    # Simula esperar [0, 3, 6, 12] meses antes de comprar
    # Calcula: entrada acumulada, novo principal, VPL com custo de oportunidade
    # Responde: "comprar agora ou esperar?"
```

### Scoring de Eficiência Secundária

```python
_pick_efficient_strategy():
    # score = 40% × capital_loss + 35% × speed + 25% × budget
    # Readiness: PRONTO / ATENÇÃO / AGUARDAR
```

---

## 5. Score de Risco (RiskScorer)

Arquivo: `validators/risk_scorer.py`

Produz um score contínuo **[0,1]** via média geométrica ponderada:

```
score = exp(Σ wᵢ × log(max(cᵢ, LOG_FLOOR)))
LOG_FLOOR = 1e-4  (evita log(0))
```

### Componentes

| Componente | Peso IMÓVEL | Peso VEÍCULO | Descrição |
|------------|-------------|--------------|-----------|
| C1 — Volatilidade de renda | 30% | 25% | Inverso do desvio padrão da receita mensal |
| C3 — Comprometimento | 25% | 30% | `exp(-3 × committed_pct)` — penalidade exponencial |
| C4 — Profundidade de reserva | 20% | 20% | Meses de reserva de emergência |
| C5 — Regularidade de poupança | 15% | 15% | Meses com saldo positivo / total |
| C6 — Horizonte temporal | 10% | 10% | Adequação do prazo ao objetivo |

### Confiança do Score

```
base = 0.40
+ 0.20 se income_profile.confidence ≥ 0.70
+ 0.15 se ≥ 6 meses de transações
- 0.07 por componente ausente
```

### Mapeamento Score → Perfil

Thresholds calibráveis pelo CalibrationPipeline:
- `score ≤ threshold_conservative` → CONSERVADOR
- `score ≤ threshold_moderate` → MODERADO
- `score > threshold_moderate` → AGRESSIVO

---

## 6. Raciocínio LLM (LLMReasoner)

Arquivo: `services/llm_reasoner.py`

Modelo: **Claude Haiku** (`claude-haiku-4-5-20251001`) via Anthropic API.

### O que o LLM adiciona — e o que o engine já resolve antes

O `StrategyEngine` já trata as inconsistências mais óbvias antes do LLM rodar:
- Perfil conservador + FINANCING recomendado → engine já rejeita via `_apply_risk_profile_adjustment`
- Perfil conservador + veículo → engine já descarta FINANCING
- VPL da melhor estratégia muito próximo da segunda → engine já aplica margem mínima

Para esses casos, o LLM raramente vai divergir da decisão do motor. A divergência real acontece em **casos de borda** que o engine não tem como detectar:

**1. Ajuste de prazo (`financing_months`) — override exclusivo do LLM**

O engine nunca sugere alterar o prazo do financiamento. O LLM pode detectar que um prazo de 360 meses é inadequado para um perfil conservador com 45 anos e sugerir 240 meses — reduzindo o custo total em detrimento de uma parcela maior. Esse override recalcula o VPL com o novo prazo e pode mudar a estratégia vencedora.

**2. Visão holística de combinações não modeladas**

O LLM recebe como contexto o conjunto completo: `risk_score`, todos os NPVs, warnings do motor, taxas, dados Open Finance. O engine avalia componentes em isolamento; o LLM pode detectar a combinação:

> "comprometimento de renda 80% + imóvel R$800k + prazo 30 anos + risco_score 0.28"

...e sinalizar que, mesmo que FINANCING tenha o melhor NPV matemático, a sobreposição desses fatores torna a aprovação bancária improvável e o risco de default alto — o que nenhum componente isolado detectaria.

**Em síntese:** o LLM é uma camada de detecção de borda, não de decisão primária. Para o caso central (perfil razoável, taxas normais, dados completos), a decisão já está correta quando o LLM começa a rodar.

---

### 3 Etapas de Raciocínio

**Etapa 1 — Verificação de Consistência (JSON)**
- Envia resumo da simulação ao LLM (perfil, risk_score, todos os VPLs, taxas, warnings do motor, dados Open Finance)
- LLM verifica se a recomendação é coerente com o perfil e detecta combinações problemáticas não modeladas
- Retorna JSON com `is_consistent`, `reasoning`, `override_params` (opcional)
- Chaves de override permitidas: `{"risk_profile", "financing_months"}` (proteção contra prompt injection)
- Técnica de prefill: força resposta iniciando com `{` para JSON válido garantido

**Etapa 2 — Re-execução condicional**
- Se LLM retorna `override_params`, o StrategyEngine é re-executado com parâmetros ajustados
- `financing_months` é o único override que o engine nunca conseguiria sugerir por conta própria
- Limita a 1 re-execução por request

**Etapa 3 — Narrativa (3 parágrafos)**
- Estilo adaptado por perfil:
  - Conservador: formal, prudente, foco em segurança
  - Moderado: direto, informativo, foco em equilíbrio
  - Agressivo: técnico, objetivo, foco em resultado
- Parágrafo 1: contexto e cenário macro
- Parágrafo 2: justificativa da recomendação
- Parágrafo 3: próximos passos concretos

### Configuração LLM

```env
# backend/.env
ANTHROPIC_API_KEY=sk-ant-api03-...
LLM_PROVIDER=anthropic
LLM_MODEL=claude-haiku-4-5-20251001
```

A configuração é lida via `pydantic-settings` a partir de `backend/.env` (resolvido de `Path(__file__).resolve().parents[2]`).

---

## 7. Calibração Contínua (CalibrationPipeline)

Arquivo: `services/calibration_pipeline.py`

Aprendizado contínuo com feedback dos usuários. Disparada quando:
- ≥ 20 feedbacks registrados **E**
- ≥ 7 dias desde a última calibração

### 3 Processos de Calibração

**1. Thresholds do RiskScorer** (Regressão Isotônica)
```python
_calibrate_score_thresholds():
    # Modelo: IsotonicRegression(risk_score → P(usuario_seguiu_recomendacao))
    # Threshold conservador: onde P(follow) = 0.50
    # Threshold moderado:    onde P(follow) = 0.75
    # Clamp: [0.20, 0.45] e [0.55, 0.80]
    # Requer: ≥ 15 feedbacks por tipo de bem
```

**2. Parâmetros do Consórcio** (Comparação com dados reais)
```python
_calibrate_bid_params():
    # Compara P50 real de contemplação vs P50 simulado
    # Ajusta bid_mean_initial: máx ±5% por rodada
    # Requer: ≥ 10 feedbacks de consórcio
```

**3. Threshold de Confiança** (Precisão por decil)
```python
_calibrate_confidence_threshold():
    # Encontra o maior decil com precisão ≥ 75%
    # Define o threshold mínimo de confiança para exibição da recomendação
    # Requer: ≥ 50 feedbacks total
```

---

## 8. Conectores de Mercado

Todos herdam de `BaseConnector` com **cache em memória + fallback automático**.

### BaseConnector (`connectors/base.py`)

```
get_rates() → cache válido? → retorna imediatamente
           → fetch_rates() bem-sucedido? → cacheia por cache_ttl e retorna
           → falhou? → loga aviso, cacheia fallback por fallback_cache_ttl, retorna fallback
```

### Conectores Implementados

| Connector | Fonte | Dado | Cache | Fallback |
|-----------|-------|------|-------|---------|
| `BacenConnector` | BCB SGS série 432 | SELIC meta anual | 1h | 14,75% a.a. |
| `AnbimaConnector` | BCB SGS série 12 | CDI anual | 1h | 14,65% a.a. |
| `IPCAConnector` | BCB SGS série 433 | IPCA 12m acumulado | 6h | 4,5% a.a. |
| `MarketRatesConnector` | BCB SGS (3 séries) | CET min/avg/max por tipo | 24h | Hardcoded fev/2026 |
| `AbacConnector` | ABAC (fallback) | Estatísticas de grupos de consórcio | 24h | Boletim ABAC fev/2026 |
| `RealEstateDataConnector` | FipeZAP (fallback) | Preço e aluguel R$/m² por cidade | 24h | ~60 bairros hardcoded |
| `ConsortiumRateProvider` | AbacConnector + IPCAConnector | Parâmetros completos para Monte Carlo | — | Agregação dos fallbacks |

### CET de Mercado por Tipo de Bem (Fallback fev/2026)

| Tipo | Min | Avg | Max |
|------|-----|-----|-----|
| Imóvel | 14,75% | 15,25% | 16,25% |
| Veículo | 16,20% | 19,50% | 24,50% |
| Reforma | 22,00% | 31,00% | 45,00% |
| Viagem | 28,00% | 36,00% | 52,00% |
| Outro | 24,00% | 32,00% | 48,00% |

### Dados Imobiliários — Cobertura

13 cidades (~60 bairros): São Paulo, Rio de Janeiro, Belo Horizonte, Brasília, Curitiba, Porto Alegre, Florianópolis, Campinas, Fortaleza, Salvador, Recife, Goiânia, Manaus.

Aliases suportados: `BH → belo_horizonte`, `SP → sao_paulo`, `RJ → rio_de_janeiro`, `DF → brasilia`, etc.

---

## 9. Simuladores Probabilísticos

### Motor Monte Carlo Genérico (`simulators/monte_carlo.py`)

```python
run_monte_carlo(scenario_fn, n_iterations=2000, seed=None) → MonteCarloResult
```

- Stdlib apenas (sem numpy) — `random`, `statistics`, `math`
- Seed opcional para reprodutibilidade em testes
- Distribuições: `sample_normal`, `sample_uniform`, `sample_lognormal`
- Funções: `probability_below`, `probability_above`, `clamp`
- Percentis: interpolação linear (compatível com numpy/pandas)

### Analisador de Sensibilidade (`simulators/sensitivity_analyzer.py`)

Responde: *"qual variável impacta mais a recomendação?"*

**4 variáveis analisadas:**

| Variável | Faixa | Pontos |
|----------|-------|--------|
| CET do financiamento | ±2 p.p. | 9 |
| Prazo do financiamento | ±6 meses | 7 |
| Valor da entrada | ±10% do original | 9 |
| Taxa CDI | ±2 p.p. | 9 |

**Métricas por variável:**
- `npv_range`: amplitude do VPL vencedor (quanto maior, mais sensível)
- `elasticity`: variação do VPL por unidade de delta
- `strategy_flips`: quantas vezes a estratégia vencedora muda

**Índices de Sobol (opcional — requer SALib):**
- S1 (primeira ordem): efeito direto de cada variável
- ST (total): efeito incluindo todas as interações
- 6 variáveis: CET, prazo, entrada, CDI, IPCA, apreciação do ativo

**Perfil de risco da simulação:**
- `baixo`: sem flips, elasticidade < 20% do target
- `moderado`: ≤ 2 flips, elasticidade < 100% do target
- `alto`: flips frequentes ou alta volatilidade de VPL

---

## 10. Validadores

### InputValidator (`validators/input_validator.py`)

Valida regras cruzadas que o Pydantic não captura:

| Regra | Tipo | Detalhe |
|-------|------|---------|
| Principal mínimo | Erro | `target - entrada ≥ R$ 1.000` |
| Entrada proporcional | Erro | Entrada ≤ 90% do target |
| Budget mínimo | Erro | `max_monthly_budget ≥ R$ 100` |
| Prazo por tipo de bem | Erro | Imóvel ≤ 420m, Veículo ≤ 84m, Reforma ≤ 120m, Viagem ≤ 60m |
| Valor mínimo por tipo | Erro | Imóvel ≥ R$50k, Veículo ≥ R$5k, Reforma ≥ R$2k |
| Flags contraditórias | Aviso | `prefers_consortium=True` mas `include_consortium=False` |
| Prazo vs target_date | Aviso | `financing_months > 2× meses_até_target_date` |

### LiquidityValidator (`validators/liquidity_validator.py`)

Calcula impacto de liquidez do compromisso mensal:

```
impact = -(parcela / safe_to_spend)  # negativo por convenção
```

| Faixa | Nível |
|-------|-------|
| ≤ 25% | SAFE (verde) |
| 26–40% | WARNING (amarelo) |
| 41–70% | HIGH (laranja) |
| > 70% | CRITICAL (vermelho) |

Hierarquia de referência: `safe_to_spend` (F1) → `max_monthly_budget` → sem referência (aviso).

---

## 11. Open Finance Pipeline

Arquivo: `pipelines/open_finance_pipeline.py`

Transforma dados bancários normalizados do Open Finance em `OpenFinanceFeatures`.

**Filosofia:** fail-silent por campo — dado ausente → campo `None` → simulação usa fallback de mercado.

### Dados Extraídos por Endpoint

**`/investments` → rendimento e composição da carteira:**
- `rendimento_real_atual`: retorno ponderado pelo valor investido (sobrepõe CDI de mercado)
- `composicao_rf_pct` / `composicao_rv_pct`: alocação renda fixa vs variável
- Suporta `rate_annual` direto ou `indexer_pct × CDI` (com IR 15% proxy)

**`/loans` → crédito e comportamento de pagamento:**
- `cet_medio_historico`: CET médio ponderado pela parcela
- `adimplencia_pct`: parcelas pagas / total (mede confiabilidade)
- `comprometimento_renda_pct`: total de parcelas / renda mensal

**`/accounts` → comportamento de poupança:**
- `sazonalidade_receita`: 12 multiplicadores mensais relativos à média anual
- `meses_consecutivos_poupanca`: streak de meses com saldo positivo

**`/financings` → histórico de financiamentos:**
- `cet_historico_real`: CET médio dos financiamentos anteriores
- `experiencia_financiamento`: flag booleana

### Impacto na Simulação

Quando dados Open Finance estão presentes:
- CET personalizado com desconto de adimplência: `-0,5 p.p. se adimplência ≥ 95%`
- Taxa de desconto do investidor: `rendimento_real_atual` substitui CDI de mercado
- Score de risco recalculado com dados reais de comprometimento, reserva e regularidade

---

## 12. Utilitários

### Cache Multi-nível (`utils/cache.py`)

**L1 — Memória** (sub-milissegundo, ephemeral):
- Dict em processo com TTL de 1h por padrão
- Eviction: remove expiradas → remove a mais antiga (LRU-like)
- Máx 256 entradas

**L2 — Disco** (~1ms, persiste entre restarts):
- Arquivo JSON por chave em `/tmp/nexa_cache/` (sobrescrevível via `NEXA_CACHE_DIR`)
- TTL de 24h por padrão
- Lazy deletion: expiradas removidas na leitura

**Chaves de cache:**
```python
make_simulation_key(req_dict, market_rates)
    # SHA-256 dos parâmetros matemáticos relevantes (exclui user_id)
    # Formato: "sim_{48 hex chars}"

make_sensitivity_key(simulation_id, market_rates)
    # simulation_id + hash das taxas atuais
    # Formato: "sens_{id}_{24 hex chars}"
```

### Formatadores (`utils/formatters.py`)

```python
format_currency(1234.56)       → "R$ 1.234,56"
format_percentage(0.125)       → "12,50%"
format_months(27)              → "2 anos e 3 meses"
format_compact_number(1500000) → "R$ 1,5M"
```

### Helpers de Data (`utils/date_helpers.py`)

```python
months_between(date(2026,1,15), date(2028,3,15))  → 26
add_months(date(2026,1,31), 1)                     → date(2026,2,28)
business_days_between(d1, d2)                      → int (sem feriados)
is_business_day(date(2026,2,15))                   → False (domingo)
next_business_day(date(2026,2,13))                 → date(2026,2,16)
```

---

## 13. Persistência (ORM e Queries)

**Banco de dados:** DuckDB  
**ORM:** Pydantic v2 + queries SQL manuais

### Tabelas Principais

| Tabela | Conteúdo |
|--------|----------|
| `architect_simulations` | Histórico completo de simulações por usuário |
| `architect_feedback` | Feedback dos usuários sobre recomendações |
| `architect_calibration` | Estado atual dos thresholds calibrados |
| `architect_calibration_history` | Log histórico de calibrações |

### Queries Notáveis

- `get_simulations_by_user()`: histórico com paginação
- `get_pending_feedback()`: simulações ≥ 6 meses sem feedback
- `get_calibration_state()`: thresholds vigentes (com TTL 5min em memória)
- `get_feedbacks_for_calibration()`: dados para CalibrationPipeline

---

## 14. API REST (Router)

Arquivo: `router.py`

Prefixo: `/architect`  
Autenticação: JWT obrigatório em todos os endpoints.

### Endpoints

| Método | Path | Descrição |
|--------|------|-----------|
| `POST` | `/simulate` | Simulação principal — executa pipeline completo |
| `GET` | `/simulations` | Histórico de simulações do usuário (paginado) |
| `GET` | `/simulations/pending-feedback` | Simulações sem feedback (≥ 6 meses) |
| `GET` | `/simulations/{id}` | Detalhe de uma simulação |
| `GET` | `/simulations/{id}/sensitivity` | Análise de sensibilidade (cacheada) |
| `GET` | `/metrics` | Métricas agregadas do usuário |
| `POST` | `/timing-scenarios` | M3.4 — "e se eu esperar X meses?" |
| `POST` | `/simulations/{id}/feedback` | Registra feedback → dispara calibração se elegível |
| `POST` | `/calibration/rollback` | Reverte última calibração |

### Exemplo de Request

```json
POST /architect/simulate
{
  "user_id": "uuid",
  "target_amount": 350000,
  "down_payment": 70000,
  "asset_type": "IMOVEL",
  "financing_months": 240,
  "amortization_method": "PRICE",
  "max_monthly_budget": 3500,
  "risk_profile": "MODERADO",
  "include_consortium": true,
  "open_finance_features": {
    "rendimento_real_atual": 0.1280,
    "adimplencia_pct": 0.98,
    "comprometimento_renda_pct": 0.22,
    "meses_consecutivos_poupanca": 8
  }
}
```

---

## 15. Modelos e Schemas

Arquivo: `models.py` (~1.681 linhas). Todos baseados em Pydantic v2.

### Enums Principais

```python
StrategyType:       FINANCING | CONSORTIUM | SAVE_INVEST | FINANCING_RENTAL | CONSORTIUM_SELIC_RENTAL
AmortizationMethod: PRICE | SAC
RiskProfile:        CONSERVADOR | MODERADO | AGRESSIVO
AssetType:          IMOVEL | VEICULO | REFORMA | VIAGEM | OUTRO
```

### SimulationRequest (campos principais)

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `user_id` | UUID | Sim | Identificador do usuário |
| `target_amount` | float | Sim | Valor total do bem (R$) |
| `down_payment` | float | Não | Entrada (default 0) |
| `asset_type` | AssetType | Não | Tipo do bem (default OUTRO) |
| `financing_months` | int | Não | Prazo [6–420] — default por tipo |
| `amortization_method` | AmortizationMethod | Não | PRICE ou SAC |
| `max_monthly_budget` | float | Não | Orçamento mensal máximo |
| `risk_profile` | RiskProfile | Não | Perfil declarado (sobrescrito pelo score) |
| `risk_score` | float | Não | Score contínuo [0,1] da F1 |
| `include_consortium` | bool | Não | Incluir consórcio na comparação |
| `expected_rental_income` | float | Não | Renda de aluguel esperada |
| `open_finance_features` | OpenFinanceFeatures | Não | Dados bancários reais |

### SimulationResponse (campos principais)

```python
recommended_strategy: StrategyType
costs: dict[StrategyType, float]          # custo total por estratégia
npv: dict[StrategyType, float]            # VPL por estratégia
confidence_score: float                   # [0.30, 1.00]
llm_reasoning: LLMReasoningResult         # {is_consistent, narrative, override_applied}
macro_simulation: MacroSimulationResult   # {P10, P50, P90, CVaR95, ssd_guarantee}
ssd_guarantee: bool                       # True se SSD confirmou dominância
liquidity_impact: float                   # fração do disponível comprometida (negativo)
months_to_achieve: int                    # meses até a meta
action_plan: list[str]                    # próximas ações recomendadas
warnings: list[str]                       # alertas não-bloqueantes
```

---

## 16. Configuração e Ambiente

### Variáveis de Ambiente (`backend/.env`)

```env
# LLM — obrigatório para llm_reasoning não ser null
ANTHROPIC_API_KEY=sk-ant-api03-...
LLM_PROVIDER=anthropic
LLM_MODEL=claude-haiku-4-5-20251001

# Cache de disco — opcional
NEXA_CACHE_DIR=/tmp/nexa_cache
```

> **Atenção:** o backend lê `.env` de `backend/.env`, **não** do `.env` raiz do projeto. A resolução é feita via `Path(__file__).resolve().parents[2]` relativo ao arquivo de settings.

### Dependências Principais

```
fastapi, uvicorn          — API server
pydantic, pydantic-settings — schemas e config
anthropic                 — LLM provider
httpx, requests           — HTTP clients para conectores
duckdb                    — banco de dados
numpy                     — simulação Sobol (sensitivity_analyzer)
SALib                     — índices de Sobol (opcional)
dateutil                  — date_helpers
sklearn                   — IsotonicRegression (CalibrationPipeline)
```

---

## 17. Fluxo Completo — Exemplo

**Cenário:** usuário quer um imóvel de R$ 350.000, tem R$ 70.000 de entrada e R$ 3.500/mês de orçamento. Perfil moderado.

```
1. POST /architect/simulate
   ↓
2. InputValidator
   ✓ principal R$280k ≥ R$1k
   ✓ entrada 20% < 90%
   ✓ 240 meses ≤ 420 (IMOVEL)

3. Taxas de Mercado
   SELIC: 14,75% (BCB SGS 432)
   CDI:   14,65% (BCB SGS 12)
   IPCA:   4,87% (BCB SGS 433)
   CET_IMOVEL_min: 14,75% (BCB SGS 25497)
   Consórcio: admin=19%, prazo=180m, grupo=150 (ABAC fallback)

4. RiskScore
   C1 (renda): 0.72, C3 (compromisso): 0.68, C4 (reserva): 0.55
   C5 (poupança): 0.80, C6 (horizonte): 0.75
   score = exp(0.30×log(0.72) + 0.25×log(0.68) + ...) = 0.68
   → Perfil: MODERADO

5. StrategyEngine.simulate()
   FINANCING (PRICE, 240m, CET 14,75%):
     PMT = R$ 3.448/mês
     IOF = R$ 1.064
     VPL = -R$ 451.320

   SAVE_INVEST (CDI×1.1=16,1%, 38 meses):
     Depósito = R$ 3.500/mês
     VPL = -R$ 389.540

   CONSORTIUM (180m, admin 19%):
     P50 contemplação: 67 meses
     Parcela: R$ 2.230/mês
     VPL = -R$ 412.780

   → SAVE_INVEST vence (maior VPL)
   → SSD: não há dominância estocástica (macro incerto)
   → Ajuste conservador: não aplicável (moderado)

6. LLMReasoner
   Etapa 1: "is_consistent: true" — SAVE_INVEST coerente com perfil moderado
   Etapa 2: sem override (consistente)
   Etapa 3: narrativa 3 parágrafos em estilo direto/informativo

7. Pós-processamento
   Liquidez: R$3.500 / R$8.000 safe_to_spend = -0.4375 → WARNING
   Confiança: 0.50 + 0.10 (OF) = 0.60

8. Resposta
   recommended_strategy: SAVE_INVEST
   confidence_score: 0.60
   liquidity_impact: -0.4375
   months_to_achieve: 38
   llm_reasoning: {is_consistent: true, narrative: "..."}
```

---

## 18. Arquitetura de Arquivos

```
backend/app/architect/
├── README.md                          ← Este arquivo
├── __init__.py
├── models.py                          ← Todos os schemas Pydantic v2 (~1.681 linhas)
├── models_orm.py                      ← Modelos de banco DuckDB
├── router.py                          ← Endpoints FastAPI
├── queries.py                         ← Queries SQL (simulações)
├── feedback_queries.py                ← Queries SQL (feedback e calibração)
│
├── services/
│   ├── architect_service.py           ← Orquestrador principal (8 etapas)
│   ├── llm_reasoner.py                ← Raciocínio LLM 3 etapas (Anthropic Haiku)
│   └── calibration_pipeline.py        ← Aprendizado contínuo com feedback
│
├── simulators/
│   ├── strategy_engine.py             ← Motor de decisão puro (~1.920 linhas)
│   ├── monte_carlo.py                 ← Motor Monte Carlo genérico (stdlib)
│   ├── macro_scenario.py              ← Cenários macro VAR(1) + Cholesky
│   └── sensitivity_analyzer.py        ← Análise de sensibilidade + Sobol
│
├── calculators/
│   ├── financing.py                   ← PRICE/SAC, IOF, CET (Newton-Raphson)
│   ├── investment.py                  ← PMT, IR por depósito, come-cotas
│   ├── npv.py                         ← VPL (Fisher), TIR (Newton-Raphson)
│   ├── consortium.py                  ← Monte Carlo de contemplação
│   └── leverage_optimizer.py          ← Otimizador de alavancagem 1.2x–3.0x
│
├── connectors/
│   ├── base.py                        ← BaseConnector com cache + fallback
│   ├── bacen.py                       ← SELIC (BCB SGS 432)
│   ├── anbima.py                      ← CDI (BCB SGS 12)
│   ├── ipca.py                        ← IPCA (BCB SGS 433)
│   ├── market_rates.py                ← CET por tipo de bem (BCB SGS)
│   ├── abac.py                        ← Estatísticas de consórcio (fallback)
│   ├── real_estate.py                 ← Preços imobiliários FipeZAP (~60 bairros)
│   └── consortium_rate_provider.py    ← Provider agregador (ABAC + IPCA)
│
├── validators/
│   ├── input_validator.py             ← Regras de negócio cruzadas
│   ├── liquidity_validator.py         ← Impacto de liquidez [SAFE/WARNING/HIGH/CRITICAL]
│   └── risk_scorer.py                 ← Score contínuo [0,1] via média geométrica
│
├── pipelines/
│   └── open_finance_pipeline.py       ← Extrai OpenFinanceFeatures de dados bancários
│
└── utils/
    ├── cache.py                       ← Cache L1 (memória) + L2 (disco) com TTL
    ├── formatters.py                  ← Formatação R$, %, meses, compacto
    └── date_helpers.py                ← months_between, add_months, dias úteis
```

---

*Última atualização: 2026-05-25 — branch `feat/architect-improvements`*
