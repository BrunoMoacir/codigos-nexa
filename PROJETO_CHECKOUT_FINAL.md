# NEXA AI — PROJECT CHECKOUT

> Documento de estado real do projeto. Nada aqui é especulação:
> cada item foi verificado lendo o código e rodando os testes.
>
> Última atualização: 2026-02-23
> Testes confirmados: **414 passando, 0 falhando**

---

## VISÃO GERAL

| Funcionalidade | Código existe | Testes passam | Integrado na API | Status |
|---|---|---|---|---|
| **F1 — Cashflow & Safe-to-Spend** | ✅ | ✅ | ✅ | **Pronto** |
| **F3 — Nexa Architect (Simulador)** | ✅ | ✅ | ✅ | **Pronto** |
| **F4 — PF/PJ Classifier** | ✅ | ✅ | ✅ parcial | **Pronto (isolado)** |
| **F2 — Card Optimizer** | ❌ | ❌ | ❌ stub | **Não iniciado** |

---

## F1 — CASHFLOW & SAFE-TO-SPEND

### O que está feito

**Pipeline ETL** (`app/etl/`)

- `ingestor.py` — Normaliza JSON do Pluggy para Polars DataFrame. Deduplica via hash de ID. Salva no DuckDB (`transactions_clean`). Estratégias por banco: Nubank, Itaú, Inter, Default.
- `classifier.py` — Classifica transações em 10 categorias por regras determinísticas: Alimentação, Transporte, Saúde, Educação, Lazer, Moradia, Vestuário, Transferências, Investimentos, Outros.
- `recurring_detector.py` — Detecta assinaturas e parcelamentos. Usa `SubscriptionDetector` e `InstallmentDetector`.
- `shadow_invoices/runner.py` — Gera obrigações futuras (shadow invoices) projetando assinaturas e parcelas para os próximos meses.
- `profiles.py` — Classifica perfil do usuário: CONSERVATIVE / BALANCED / SPENDER + health score 0-100.
- `data_quality.py` — Validação de qualidade dos dados processados.
- `pf_pj_classifier.py` — Ver F4.

**Cálculos financeiros** (`app/cashflow/`)

- `projector.py` — Projeta saldo diário para os próximos N dias (padrão 30). Usa transações históricas + shadow invoices. Retorna Polars DataFrame com: `date`, `projected_balance`, `events`, `expenses`, `risk_flag`.
- `safe_to_spend.py` — Calcula quanto o usuário pode gastar hoje com segurança. Fórmula: `min_projected_balance - (buffer × 15%)`. Risk levels: LOW / MEDIUM / HIGH / CRITICAL.
- `engine.py` — Orquestra projector + safe_to_spend em uma chamada só.

**Orquestrador principal** (`app/runner.py` — `NexaRunner`)

Executa o pipeline completo na ordem:
1. Conecta ao Pluggy (real ou mock)
2. Valida batch com Pydantic (`TransactionBatchResult`)
3. Normaliza com `TransactionIngestor`
4. Classifica categorias com `TransactionClassifier`
5. Classifica PF/PJ com `PFPJClassifier`
6. Detecta recorrências com `RecurringDetector`
7. Gera shadow invoices com `run_shadow_invoice_detection`
8. Projeta cashflow com `CashflowProjector`
9. Calcula safe-to-spend com `SafeToSpendCalculator`

**API — Endpoints funcionando com lógica real**

| Método | Rota | O que faz |
|---|---|---|
| `GET` | `/api/v1/forecast/{user_id}` | Executa NexaRunner completo, retorna previsão consolidada |
| `GET` | `/api/v1/shadow_invoice/{user_id}` | Detecta obrigações futuras |
| `GET` | `/api/v1/shadow_invoice/{user_id}/summary` | Resumo de obrigações |
| `GET` | `/api/v1/alerts/{user_id}` | Gera alertas (token expiry, saldo negativo, caixa comprometido) |
| `POST` | `/api/v1/transactions/webhook` | Recebe transações do Pluggy, valida e roda ETL |
| `POST` | `/api/v1/reconnect/{user_id}` | Gera URL de reconexão Pluggy |
| `GET` | `/dashboard` | Painel básico via `FinanceEngine` |

**Testes passando**

| Arquivo de teste | O que cobre |
|---|---|
| `test_cashflow_projection.py` | CashflowProjector |
| `test_classifier.py` | TransactionClassifier |
| `test_etl_ingestor.py` | TransactionIngestor |
| `test_pipeline_integration.py` | NexaRunner ponta-a-ponta |
| `test_pluggy_integration.py` | MockPluggyClient |
| `test_recurring_detector.py` | RecurringDetector |
| `test_runner.py` | NexaRunner |
| `test_runner_import.py` | imports do runner |
| `test_safe_to_spend.py` | SafeToSpendCalculator |
| `test_shadow_invoice.py` | shadow invoice detection |
| `test_shadow_pipeline.py` | pipeline completo de shadow |
| `test_schemas_complete.py` | schemas Pydantic |
| `test_ultimate_etl_and_schemas.py` | ETL + schemas integrado |

---

## F3 — NEXA ARCHITECT (SIMULADOR FINANCEIRO)

### O que está feito

**Calculadoras** (`app/architect/calculators/`)

- `npv.py` — VPL, TIR (Newton-Raphson), VP de anuidade, FV de anuidade. Guards contra divisão por zero.
- `financing.py` — PMT (tabela PRICE e SAC), CET, cronograma de amortização.
- `investment.py` — Retorno composto, PMT necessário, meses necessários, FV com aportes.
- `consortium.py` — Parcela de consórcio, taxa de administração, probabilidade de contemplação (2000 iterações Monte Carlo com 200 participantes simulados).

**Simuladores** (`app/architect/simulators/`)

- `strategy_engine.py` — Executa e compara 3 estratégias: Financiamento vs Consórcio vs Investimento. Ranqueia por VPL (menor custo total vence). Gera plano de ação.
- `monte_carlo.py` — Simulação estocástica de risco para contemplação de consórcio.
- `sensitivity_analyzer.py` — Analisa 4 variáveis: taxa de juros, prazo, entrada, CDI. Gera curvas de elasticidade, detecta inversão de estratégia, classifica risco: baixo/moderado/alto.

**Conectores de taxas de mercado** (`app/architect/connectors/`)

- `bacen.py` — Busca SELIC (Série 432) na API do BACEN. Fallback hardcoded se API falhar.
- `anbima.py` — Busca CDI (Série 4391) na ANBIMA. Fallback hardcoded.
- `market_rates.py` — CET por tipo de bem (veículo, imóvel). Fallback hardcoded.
- `abac.py` — Estatísticas de consórcio (ABAC). Fallback hardcoded.
- Cache 2 níveis: L1 memória (TTL 1h) + L2 disco (TTL 24h).

**Validadores** (`app/architect/validators/`)

- `input_validator.py` — 7 regras de negócio validadas (target > 0, entrada < target, prazo > 0, etc.)
- `liquidity_validator.py` — 4 níveis de risco de liquidez: SAFE / WARNING / HIGH / CRITICAL.

**Orquestrador** (`app/architect/services/architect_service.py`)

Fluxo: Input validation → busca taxas de mercado → executa StrategyEngine → LiquidityValidator → ajuste de confidence → persiste no DuckDB.

**API — Endpoints funcionando**

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/api/v1/architect/simulate` | Simulação completa: valida → taxas → estratégias → sensibilidade |
| `GET` | `/api/v1/architect/simulations` | Lista simulações do usuário (DuckDB) |
| `GET` | `/api/v1/architect/simulations/{id}` | Simulação específica por ID |
| `GET` | `/api/v1/architect/simulations/{id}/sensitivity` | Re-análise de sensibilidade com taxas atuais |
| `GET` | `/api/v1/architect/metrics` | Métricas do usuário |
| `GET` | `/api/v1/architect/health` | Health check do módulo |

**Persistência** — `app/db/queries/architect_queries.py`
Salva e busca simulações no DuckDB. Tabelas: `simulations`, `simulation_results`.

**Testes passando** — 355 testes só no módulo architect

| Arquivo | Testes |
|---|---|
| `tests/architect/test_api.py` | 29 testes dos endpoints |
| `tests/architect/test_connectors.py` | 16 testes dos conectores |
| `tests/architect/test_consortium.py` | 12 testes da calculadora consórcio |
| `tests/architect/test_db.py` | 4 testes de persistência |
| `tests/architect/test_financing.py` | testes do financiamento |
| `tests/architect/test_investment.py` | testes do investimento |
| `tests/architect/test_npv.py` | testes VPL/TIR |
| `tests/architect/test_strategy.py` | 16 testes do strategy engine |
| `tests/architect/test_sensitivity.py` | 53 testes do analisador |
| `tests/architect/test_monte_carlo.py` | testes Monte Carlo |
| `tests/architect/test_liquidity.py` | testes do validador |
| `tests/architect/test_input_validator.py` | testes de validação |

---

## F4 — PF/PJ CLASSIFIER

### O que está feito

**Modelo treinado** (`backend/models/`)

- `pf_pj_classifier.pkl` — Random Forest treinado
- `feature_encoders.pkl` — LabelEncoders para features categóricas
- `feature_scaler.pkl` — StandardScaler para features numéricas
- Dataset: `data/training_dataset_pf_pj.csv` + `.parquet`
- Relatório de validação: `docs/pf_pj_validation_report.md`

**Classificador** (`app/etl/pf_pj_classifier.py`)

Features: texto do merchant (TF-IDF-like), nome do merchant, valor, dia da semana, hora, categoria.

Pipeline de decisão (em ordem de prioridade):
1. Modelo ML — se confiança ≥ threshold usa previsão
2. Palavras-chave PJ: EMPRESA, LTDA, MEI, CNPJ, S.A., etc.
3. Thresholds de valor
4. Padrões de merchant
5. Default: UNCERTAIN

Saída: coluna `pf_pj_label` (PF / PJ / UNCERTAIN) + `pf_pj_confidence`.

**API — Endpoint funcionando**

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/api/v1/context/override` | Salva correção manual PF/PJ no DuckDB |
| `GET` | `/api/v1/context/overrides/{user_id}` | Lista overrides do usuário |

**Scripts de suporte** (`backend/scripts/`)

- `create_labeled_dataset.py` — gera dataset rotulado
- `train_pf_pj_classifier.py` — treina o modelo
- `validate_pf_pj_classifier.py` — valida acurácia
- `pf_pj_fallback_rules.py` — regras heurísticas fallback
- `test_manual_override.py` — testa override manual

**Testes passando** — `tests/test_f4_complete.py` — 8 testes

**Limitação:** F4 está integrado no `NexaRunner` mas não está integrado no `run_etl_pipeline()` (`app/etl/runner.py`). As duas funções existem em paralelo.

---

## F2 — CARD OPTIMIZER

### Status: NÃO INICIADO

O que existe:
- `app/api/v1/routes/analyze.py` — arquivo vazio, não registrado no router
- `app/api/v1/routes/chat.py` — arquivo vazio, não registrado no router

O que não existe: nenhuma lógica implementada.

---

## INFRAESTRUTURA E SUPORTE

### Banco de dados

- **DuckDB** — em uso localmente. Tabelas: `transactions_clean`, `context_overrides`, `simulations`.
- **PostgreSQL** — `app/db/session.py` e `app/db/models.py` existem mas não estão ativos no fluxo principal.
- **Migrações** — `scripts/apply_migrations.py` existe, não aplicado automaticamente.

### Configuração

- `app/core/config.py` — Pydantic Settings, carrega variáveis de ambiente do `.env`.
- Dependência marcada como deprecated no Pydantic v2 (aviso nos testes — não é erro).

### Integração Pluggy

- `pluggy_mock.py` — funcional, usado em todos os testes.
- `pluggy.py` — cliente real implementado, não testado end-to-end com credenciais reais.

### Autenticação

- `app/core/security.py` — JWT skeleton existe, **não está aplicado em nenhum endpoint**.

### Agent (LangGraph)

- `app/agent/graph.py`, `state.py`, `nodes/` — implementados mas **desabilitados**.
- `routes/analyze.py` — import comentado no `router.py` com TODO.

---

## ARQUIVOS QUE EXISTEM MAS NÃO FAZEM PARTE DO FLUXO ATIVO

| Arquivo | Razão |
|---|---|
| `app/services/finance_engine_service.py` | Importa `app.core_engine.*` que não existe — código quebrado |
| `app/engines/calculator.py` | Não importado por ninguém — substituído por `app/cashflow/` |
| `app/engines/reconciler.py` | Não importado por ninguém |
| `app/engines/shadow_invoice.py` | Não importado por ninguém |
| `app/ml/models/catboost_classifier.py` | Não usado — pipeline usa sklearn via joblib |
| `app/ml/models/neuralprophet_forecaster.py` | Não usado |
| `app/insights/engine.py` | Não importado por ninguém |
| `app/db/session.py` | Não usado no fluxo principal |
| `app/db/models.py` | Não usado no fluxo principal |

---

## CONTAGEM FINAL

- **Arquivos Python:** 167
- **Testes:** 414 passando, 0 falhando
- **Endpoints ativos:** 14
- **Endpoints stub/não implementados:** 2 (`analyze`, `chat`)
- **Funcionalidades prontas:** F1, F3, F4
- **Funcionalidades não iniciadas:** F2

---
---

# O QUE FALTA PARA O PROJETO FICAR PRONTO

## Análise baseada no README e no código real

O README atual tem problemas sérios que precisam ser tratados antes de qualquer outra coisa.

---

### PROBLEMA 1 — O README foi gerado automaticamente e está errado

O próprio README diz: *"Muitas descrições acima foram inferidas a partir dos nomes"*
e *"Onde a função do arquivo foi inferida pela convenção do nome, isto está indicado"*.

Isso significa que o README não documenta o projeto real — ele infere o projeto pelo nome dos arquivos.
Exemplos de informações erradas ou incompletas no README:

- Descreve `app/engines/` como se fosse ativo ("funções de cálculo financeiro, reconciliação") — esses arquivos não são importados por ninguém.
- Descreve `app/services/` como "serviços auxiliares" — o arquivo está quebrado.
- Não menciona F1, F3, F4 como funcionalidades com status definido.
- Não tem instruções de como rodar o projeto.
- Não lista os endpoints da API.
- Não tem exemplo de uso.

---

### O QUE FALTA — POR CATEGORIA

#### 1. README — precisa ser reescrito do zero

- [ ] Remover todo o conteúdo gerado automaticamente
- [ ] Descrever o que o projeto realmente faz (não o que "pode fazer")
- [ ] Adicionar instruções de instalação: `pip install -r requirements.txt` ou `poetry install`
- [ ] Adicionar como rodar: `uvicorn app.main:app --port 8000 --reload`
- [ ] Adicionar como rodar os testes: `pytest tests/`
- [ ] Listar os endpoints reais com exemplo de request/response
- [ ] Adicionar status real de cada funcionalidade (F1 pronto, F2 não iniciado, etc.)
- [ ] Documentar variáveis de ambiente necessárias (`.env`)

#### 2. F2 — Card Optimizer (0% feito)

- [ ] Definir escopo e regras de negócio (o que exatamente o otimizador decide?)
- [ ] Implementar lógica de análise de cartões
- [ ] Calcular custo-benefício por cartão (anuidade vs cashback vs milhas)
- [ ] Criar endpoint `GET /api/v1/analyze_cards/{user_id}`
- [ ] Registrar rota no `router.py`
- [ ] Escrever testes

#### 3. Autenticação — não existe em nenhum endpoint

- [ ] Aplicar JWT nos endpoints (o skeleton em `app/core/security.py` não está conectado a nada)
- [ ] Proteger pelo menos: `/forecast`, `/shadow_invoice`, `/alerts`, `/context/override`
- [ ] Definir como o `user_id` chega na API (hoje é parâmetro de URL sem verificação)

#### 4. Integração com Pluggy real

- [ ] Testar `pluggy.py` com credenciais reais end-to-end
- [ ] Validar que o webhook do Pluggy (`POST /transactions/webhook`) funciona com payload real
- [ ] Testar `POST /reconnect/{user_id}` com Pluggy real

#### 5. Banco de dados — migração PostgreSQL

- [ ] Aplicar migrations do PostgreSQL (`scripts/apply_migrations.py`)
- [ ] Conectar `app/db/session.py` e `app/db/models.py` ao fluxo real
- [ ] Substituir DuckDB por PostgreSQL em produção (ou definir qual DB usar onde)
- [ ] Tabela `transactions_clean` precisa existir no PostgreSQL

#### 6. ETL — passos não integrados no `run_etl_pipeline()`

O `app/etl/runner.py` tem comentários `# TODO` nos passos 1, 2, 3, 6, 7. Os módulos existem mas não estão chamados dentro dessa função:

- [ ] Integrar `DataIngestor` no `run_etl_pipeline()`
- [ ] Integrar `TransactionClassifier` no `run_etl_pipeline()`
- [ ] Integrar `RecurringDetector` no `run_etl_pipeline()`
- [ ] Integrar `DataQualityValidator` no `run_etl_pipeline()`
- [ ] Integrar `UserProfileAnalyzer` no `run_etl_pipeline()`

#### 7. `GET /transactions/{user_id}` — não implementado

- [ ] Endpoint retorna 501 hoje. Implementar busca de transações por usuário no banco.

#### 8. Agent/LangGraph — desabilitado

Decisão necessária: implementar ou remover?

- [ ] Se implementar: resolver dependências LangGraph e reativar `routes/analyze.py` no router
- [ ] Se não implementar: deletar `app/agent/` para não gerar confusão

#### 9. Arquivos mortos — limpar ou integrar

Decisão necessária para cada um:

- [ ] `app/services/finance_engine_service.py` — corrigir os imports quebrados ou deletar
- [ ] `app/engines/` (calculator, reconciler, shadow_invoice) — integrar ou deletar
- [ ] `app/ml/models/` (catboost, neuralprophet) — integrar ou deletar
- [ ] `app/insights/engine.py` — integrar ou deletar

#### 10. Aviso de compatibilidade Pydantic v2

Aparece em todos os testes:
```
PydanticDeprecatedSince20: Support for class-based `config` is deprecated
```
- [ ] Migrar `app/core/config.py` de `class Config` para `model_config = ConfigDict(...)`

#### 11. Aviso de compatibilidade sklearn

Aparece nos testes de F4:
```
InconsistentVersionWarning: Trying to unpickle estimator from version 1.7.2 when using version 1.8.0
```
- [ ] Retreinar e salvar o modelo com a versão atual do sklearn (`train_pf_pj_classifier.py`)

#### 12. Documentação técnica — atualizar

- [ ] `ARCHITECTURE.md` menciona `app/analysis/` que não existe no código atual
- [ ] `ARCHITECTURE.md` menciona stages ETL que estão como TODO no código
- [ ] `DOCUMENTACAO_COMPLETA.md` precisa refletir o estado atual (F3 completo, F2 não iniciado)

---

### RESUMO: PRIORIDADES PARA FICAR PRONTO

**Crítico (sem isso não vai para produção):**
1. Autenticação nos endpoints
2. PostgreSQL funcionando (ou decisão definitiva de ficar com DuckDB)
3. Pluggy real testado end-to-end
4. README reescrito

**Importante (produto incompleto sem isso):**
5. F2 — Card Optimizer implementado
6. `GET /transactions/{user_id}` implementado
7. ETL `run_etl_pipeline()` com todos os passos integrados

**Qualidade (faz diferença mas não bloqueia):**
8. Corrigir aviso do Pydantic v2
9. Retreinar modelo sklearn para versão atual
10. Limpar arquivos mortos
11. Decidir sobre Agent/LangGraph (implementar ou remover)
12. Atualizar documentação técnica
