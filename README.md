# 🏦 Nexa AI — The Autonomous Financial Agent

> **Status:** MVP em Desenvolvimento 🚧  
> **Missão:** Democratizar a inteligência financeira de *Family Offices* para o brasileiro comum usando **IA Generativa + Matemática Determinística**.

A **Nexa AI** não é um organizador financeiro passivo.  
Ela é um **Agente Financeiro Autônomo** que:
- **Prevê o futuro** (Fluxo de Caixa, compromissos e riscos)
- **Otimiza o presente** (cartões, taxas, decisões de gasto)
## Visão geral do repositório

Este README foi expandido para descrever a estrutura atual do workspace, o propósito de cada pasta e uma descrição por arquivo (quando aplicável). As descrições abaixo foram compiladas a partir dos nomes e documentação existente do projeto. Onde a função do arquivo foi inferida (pela convenção do nome), isto está indicado.

Se quiser que eu abra e resuma o conteúdo linha-a-linha de arquivos específicos, eu posso fazer isso em seguida — basta indicar quais arquivos quer que eu detalhe.

### Top-level

- `API_IMPLEMENTATION_FINAL.md` — Documento final de implementação da API (especificações e decisões de implementação).
- `ARCHITECTURE_VISUAL_MAP.md` — Mapa visual da arquitetura do sistema (diagramas, fluxos e componentes).
- `PROJETO_CHECKOUT_FINAL.md` — Documento de escopo/checkout do projeto (requisitos finais, entregáveis).
- `QUICK_REFERENCE.md` — Referência rápida com comandos e atalhos para desenvolvedores.
- `README.md` — Este arquivo (descrição completa do repositório).
- `finance.duckdb` — Banco de dados DuckDB usado para dados financeiros de exemplo / desenvolvimento.
- `backend/` — Código principal da aplicação backend (detalhes abaixo).
- `data/` — Datasets (ex.: `transactions.duckdb`, CSVs e Parquet usados para treino/teste).

## Pasta `backend/` — visão geral

O diretório `backend/` contém a aplicação principal em Python, testes e scripts de suporte. Abaixo descrevo o propósito de cada item e o que cada arquivo/pasta faz, com base nos nomes e na documentação existente.

Arquivos na raiz de `backend/`:

- `.env` — Variáveis de ambiente para desenvolvimento/local (credenciais, URLs, flags).
- `.gitignore` — Regras do Git.
- `ARCHITETURE.md` — Documento de arquitetura (detalhes do backend).
- `debug_pluggy_validation.py` — Script de debug para validação usando pluggy (possivelmente executa hooks de validação).
- `debug_validation.py` — Script de debug para validar dados ou pipelines.
- `finance.duckdb` — DuckDB local com tabelas de desenvolvimento/teste.
- `HOW_TO_TEST.md` — Guia de como executar testes e validações locais.
- `imports.py` — Aggregador de imports/exports para facilitar testes ou execução (pode expor fixtures/utilitários).
- `pyproject.toml` — Configuração do projeto Python (build, dependências, ferramentas).
- `requirements.txt` — Dependências do Python (lista para pip).
- `schema_info.txt` — Informação sobre schemas das tabelas (colunas e tipos).
- `test_api.py` — Testes de integração/contrato da API.
- `test_new_mock.py` — Teste relacionado a mock de dados/serviços.
- `test_output.log` — Log de saída de testes (registro histórico).

Pasta `backend/app/` — aplicação principal

Estrutura e propósito dos arquivos principais em `backend/app/`:

- `__init__.py` — inicializador do pacote `app`.
- `main.py` — ponto de entrada da API (provavelmente inicia FastAPI/uvicorn). Inferência baseada em convenção.
- `runner.py` — runner/CLI usado para executar pipelines, ETL, ou tarefas agendadas.

Subpasta `app/adapters/`:

- `bank_adapter.py` — Adaptador para integração com bancos (Open Finance, leitura de extratos, normalização de payloads bancários).

Subpasta `app/agent/`:

- `__init__.py` — inicializador do pacote `agent`.
- `graph.py` — definição de grafo/fluxo do agente (orquestração de ações do agente).
- `state.py` — gerenciamento de estado do agente (contexto, memória curta/longa).
- `nodes/` — pasta com nós/ações que compõem o agente (plugins, passos do fluxo). (conteúdo omitido na listagem)

Subpasta `app/analysis/`:

- `__init__.py` — inicializador.
- `recurring_detector.py` — algoritmo para detectar despesas recorrentes (assinaturas, parcelas).
- `shadow_invoice_detector.py` — detector de faturas "ocultas" (parcelamentos e cobranças recorrentes disfarçadas).

Subpasta `app/api/`:

- `v1/` — versão 1 das rotas e controladores da API (endpoints REST/HTTP). Conteúdo não listado (suponho controllers, schemas e routers).

Subpasta `app/cashflow/`:

- `__init__.py` — inicializador.
- `engine.py` — núcleo de cálculo/projeção do fluxo de caixa.
- `projector.py` — lógica de projeção diária/por período (transforma transações em projeção).
- `safe_to_spend.py` — cálculo de "safe-to-spend" (quanto pode gastar sem risco), com regras de segurança.

Subpasta `app/core/`:

- `__init__.py` — inicializador.
- `config.py` — carregamento de configurações (padrão/env/validação de schemas).
- `explain.py` — helpers para gerar explicações (textuais) das decisões do sistema.
- `logging.py` — configuração de logging e helper para logs estruturados.
- `recurrence.py` — regras e utilitários para recorrência de transações.
- `security.py` — utilitários de segurança (tokens, verificação, roles).
- `shadow_invoices.py` — lógica relacionada a "shadow invoices" (agregação e tratamento).

Subpasta `app/db/`:

- `__init__.py` — inicializador.
- `models.py` — modelos ORM / definições de tabelas (p.ex., SQLAlchemy/Dataclasses para persistência).
- `queries.py` — queries reutilizáveis (consultas SQL pré-definidas para o app).
- `session.py` — gerenciamento de sessão/connection pool com o banco.
- `migrations/` — scripts de migração de esquema (pasta vazia/listada).

Subpasta `app/domain/`:

- `__init__.py` — inicializador.
- `finance_engine.py` — orquestrador de regras de negócio específicas do domínio financeiro (regras compostas, coordenação entre módulos).

Subpasta `app/engines/`:

- `__init__.py` — inicializador.
- `calculator.py` — funções de cálculo financeiro (VPL, juros, amortizações).
- `reconciler.py` — regras de reconciliação entre transações e registros contábeis.
- `shadow_invoice.py` — motor específico para detecção/tratamento de shadow invoices.

Subpasta `app/etl/`:

- `__init__.py` — inicializador.
- `classifier.py` — pipeline ou wrapper que aplica modelos de classificação a transações (PF/PJ, categorias).
- `data_quality.py` — verificações e métricas de qualidade dos dados.
- `ingestor.py` — ingestor de fontes externas (importação e normalização de dados brutos).
- `loader.py` — carregador para o banco local/duckdb ou ODS.
- `organização.md` — documento de organização do ETL.
- `pf_pj_classifier.py` — implementação do classificador PF vs PJ (pode conter o código do modelo e pré/processamento).
- `profiles.py` — criação/manutenção de perfis de usuário (agregações, heurísticas).
- `recurring_detector.py` — wrapper/integração para detectar recorrências no processo ETL.
- `runner.py` — runner de pipelines ETL (execução agendada/manual).
- `shadow_invoices.py` — integração ETL para detectar e persistir shadow invoices.
- `test_ultimate_etl_and_schemas.py` — testes que exercitam ETL e validação de schemas.
- `bank_strategy/`, `dedup/`, `shadow_invoices/` — submódulos com estratégias por banco, deduplicação e lógica relacionada (detalhes omitidos).

Subpasta `app/insights/`:

- `engine.py` — motor de insights (agregações, geração de insights acionáveis para o usuário).

Subpasta `app/integrations/`:

- `__init__.py` — inicializador.
- `a/`, `open_finance/` — integrações com provedores de serviços e Open Finance.

Subpasta `app/ml/`:

- `__init__.py` — inicializador.
- `models/` — artefatos de modelos, treinamentos e utilitários de ML (pasta com modelos salvos e helpers).

Subpasta `app/schemas/`:

- `__init__.py` — inicializador.
- `...` — schemas Pydantic / validações para receptores e saídas da API.

Subpasta `app/services/` e `app/storage/`:

- `...` — serviços auxiliares (pagamentos, notificações) e abstrações de storage (S3, GCS, etc.). Conteúdo omitido.

Pasta `backend/data/`:

- `training_dataset_pf_pj.csv` — CSV de treinamento para classificador PF vs PJ.
- `training_dataset_pf_pj.parquet` — mesma base em formato Parquet (mais eficiente).
- `transactions.duckdb` — base de transações para testes/infra.

Pasta `backend/docs/`:

- `f4_complete_test_results.json` — resultados de testes automatizados/exportados.
- `pf_pj_validation_report.md` — relatório de validação para o classificador PF/PJ.
- `pf_pj_validation_results.json` — resultados numericos da validação.

Pasta `backend/models/`:

- `feature_encoders.pkl` — encoders de features salvos (usados em produção/teste).
- `feature_scaler.pkl` — scaler salvo (normalização de features).
- `pf_pj_classifier.pkl` — modelo serializado do classificador PF/PJ.

Pasta `backend/scripts/`:

- `apply_migrations.py` — script para aplicar migrações de banco.
- `create_labeled_dataset.py` — script para gerar dataset rotulado (uso em ML).
- `exploration_script.py` — script de exploração/EDA.
- `pf_pj_fallback_rules.py` — regras fallback para classificador PF/PJ (heurísticas).
- `test_manual_override.py` — script de teste para sobreposição manual de decisões.
- `train_pf_pj_classifier.py` — script de treinamento do classificador PF/PJ.
- `validate_pf_pj_classifier.py` — script de validação do classificador.

Pasta `backend/tests/`:

- `conftest.py` — fixtures e configuração de testes pytest.
- `test_cashflow_projection.py` — testes do módulo de projeção de caixa.
- `test_classifier.py` — testes do classificador PF/PJ.
- `test_etl_ingestor.py` — testes do ingestor ETL.
- `test_f4_complete.py` — teste fim-a-fim / integração completa.
- `test_pipeline_integration.py` — integração de pipelines.
- `test_pluggy_integration.py` — testes de integração com pluggy/hook system.
- `test_recurring_detector.py` — testes do detector de recorrências.
- `test_runner_import.py` — teste de importação do runner.
- `test_runner.py` — testes do runner principal.
- `test_safe_to_spend.py` — testes do cálculo safe-to-spend.
- `test_shadow_invoice.py` — testes do módulo de shadow invoices.
- `test_shadow_pipeline.py` — testes específicos do pipeline de shadow invoices.
- `api/`, `data/`, `fixtures/` — diretórios com testes de API, dados de teste e fixtures.

---

## Observações gerais e suposições

- Muitas descrições acima foram inferidas a partir dos nomes e da documentação já existente no repositório (por exemplo `HOW_TO_TEST.md`, `ARCHITETURE.md` e o README original). Quando a função do arquivo é óbvia (p.ex. `train_pf_pj_classifier.py`), descrevi seu propósito com base em convenções comuns.
- Onde houver `...` ou pastas listadas sem arquivos concretos no anexo, indiquei o propósito esperado. Se precisar, eu posso abrir cada arquivo e gerar um resumo preciso do conteúdo (funções, classes, entradas/saídas, docstrings) — isso pode ser feito arquivo a arquivo ou em lotes.

## Próximos passos (opções)

1. Gerar um sumário detalhado por arquivo com base no conteúdo real (abrir e ler cada arquivo): isso criará um documento com a assinatura de cada função/classe, docstrings e pontos-chave. (recomendado se precisar de documentação técnica precisa).
2. Criar um arquivo `CONTRIBUTING.md` com instruções de desenvolvimento e fluxo de PRs.
3. Gerar diagramas (Mermaid) automáticos para dependências entre módulos (posso escanear imports e construir o grafo).

Diga qual opção prefere e eu sigo: posso começar abrindo todos os arquivos em `backend/` e produzir descrições linha-a-linha automaticamente.

---

Fim do README gerado automaticamente — atualização concluída.
