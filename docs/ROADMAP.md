# Nexa — Roadmap de Produto e Arquitetura

**Visão:** Um app que otimiza cada centavo do usuário, sem parcialidade entre bancos.
O consultor financeiro que os bancos não querem que você tenha.

> **Auditoria de 2026-06-24:** este documento foi conferido linha a linha contra o código real
> (`backend/app/`, `backend/alembic/versions/`, `backend/tests/`). Onde a afirmação original estava
> errada ou desatualizada, foi corrigida no lugar e marcada com "↳ verificado". Nenhum conteúdo
> original foi removido — apenas corrigido ou complementado.

---

## App — Estrutura Final (2 páginas)

### 1. Feed de Oportunidades
Lista priorizada das análises com maior impacto financeiro para o usuário.
- Cada card: tipo de oportunidade, valor gerado em R$/mês, urgência
- Ao expandir: como foi calculado, passos práticos para executar
- Ordenação: maior impacto em R$/mês primeiro
- Fontes: todos os módulos do backend que retornam valor mensurável

### 2. Chat com Consultor IA
Interface de conversa direta com o agente LangGraph ReAct.
- 15 tools especializadas com acesso a todos os módulos do backend
- Histórico persistido por sessão (Redis)
- Consultor disponível 24/7, sem viés de banco

---

## Estado Atual — Módulos Implementados

| Código | Nome | Valor para o Usuário |
|--------|------|----------------------|
| F1 | Forecast & ETL | Cashflow projetado, alertas, safe-to-spend |
| F2 | Optimizer de Cartões | Qual cartão usar por categoria, cashback, pontos |
| F3 | Architect (Simulações) | Financiamento vs. consórcio vs. investir, NPV, Monte Carlo |
| F4 | Divider PF/PJ | Separação automática de gastos pessoais e da empresa |
| F5 | Raio-X de Custos | Detecção de tarifas bancárias cobradas |
| F7 | Modo Compra Inteligente | Melhor forma de pagamento (PIX / cartão / parcelado / crédito) |
| F13 | Negociador | Roteiro personalizado de negociação com o banco |
| M1.3 | Budget Inteligente | Orçamento adaptativo 50/30/20 por categoria |
| M1.5 | Monitor de Assinaturas | Detecção de cobranças recorrentes e alertas de aumento |
| M4.1 | Fiscal PJ | Relatório fiscal para MEI e PJ |
| MX.1 | Health Score | Score financeiro 0–100 com histórico mensal |
| MX.2 | Metas Financeiras | Rastreamento de objetivos com projeção de prazo |
| MX.3 | Notificações Contextuais | Parcial: geração sob demanda via API; scheduler e entrega ainda não existem |
| MX.4 | Peers | Benchmark anônimo com perfis financeiros similares |
| AI Chat | Agente LangGraph ReAct | Consultor financeiro conversacional com 15 tools |

**Infra:** Python 3.11+ (`pyproject.toml`, roda em 3.13 localmente) + FastAPI + PostgreSQL + DuckDB + Redis + LangGraph + LangChain.
↳ **verificado 2026-06-24:** Anthropic/OpenAI são usados via import dinâmico (`architect/services/llm_reasoner.py`,
`negotiator/script_generator.py`) e via `langchain-anthropic`/`langchain-openai`; os SDKs puros `anthropic`/`openai`
não estão pinados em `requirements.txt`.
**Testes:** ↳ **verificado 2026-06-24:** 1.757 testes coletados via `pytest --collect-only` (o número "414 passando,
cobertura 89%" está desatualizado e não há relatório de cobertura no repo). 3 erros de coleção conhecidos:
`test_goals_2.py` (conflito de tabela SQLite `financial_goals` ao rodar em paralelo), `tests/architect/test_api.py`,
`tests/test_e2e_production_ready.py`.

---

## Roadmap por Vertical

### D — Defesa do Consumidor
*Diferencial competitivo: o único app que fica do lado do usuário contra o banco*

| ID | Funcionalidade | Prioridade | Esforço Est. | Base técnica existente |
|----|----------------|------------|--------------|------------------------|
| D1 | Detector de Venda Casada (CDC art. 39) | Alta | 2–3 sem | F5 costs + Pluggy |
| D2 | Recuperador de Cobranças Indevidas | Alta | 2–3 sem | F5 + baseline histórico |
| D3 | Detector de Juros Abusivos (BACEN SGS 20714/20715 + STJ REsp 1.061.530) | Alta | 1–2 sem | F13 + BacenConnector (parcial — ver nota ↓) |
| D4 | Alerta de Mudança Unilateral de Tarifa | Média | 1–2 sem | MX.3 + baseline banco |
| D5 | Central de Evidências (dossiê PROCON / JEC) | Média | 4+ sem | D1+D2+D3 + validação jurídica |
| D6 | Simulador de Portabilidade Total (conta + cartão + crédito + salário + investimentos) | Baixa | 4+ sem | F3 + Res. BACEN 4.292/2013 |

**Fluxo D5 (maior impacto):** Detecta → Calcula valor a recuperar → Gera dossiê → Modelo de petição JEC

↳ **Nota sobre D3 (verificado 2026-06-24):** `backend/app/negotiator/opportunity_detector.py` já tem um detector
de juros rotativo (`_detect_juros_rotativo`) que busca a SELIC via `BacenConnector` dinamicamente (com fallback de
3,99% a.m. se a API cair) — **não é hardcoded**. O que falta é trocar essa aproximação genérica (SELIC + spread)
pelas séries SGS específicas de crédito rotativo PF (20714/20715) e cheque especial (20706), que ainda não têm
conector (ver [MUDANÇAS.md §3.2 e §5.1](MUDANÇAS.md)). Já existe, sim, um valor hardcoded no mesmo arquivo —
`_ANUIDADE_MARKET_MONTHLY_AVG = 30.0` — mas ele é usado pelo detector de **anuidade alta** (`_detect_anuidade_alta`),
não pelo de juros rotativo.

---

### T — Fiscal e Tributária

| ID | Funcionalidade | Prioridade | Esforço Est. | Base técnica existente |
|----|----------------|------------|--------------|------------------------|
| T1 | Otimizador de IR (tax loss harvesting, timing de resgate, migração de fundos) | Média | 3–4 sem | Pluggy investimentos |
| T2 | Modo Imposto Zero (CDB→LCI/LCA, poupança→Tesouro SELIC, come-cotas) | Média | 2–3 sem | OPP (Radar) |
| T3 | Monitor de Direitos Esquecidos (SVR BACEN, FGTS, PIS/PASEP, restituição IR, dividendos B3) | Alta | 2–3 sem | APIs públicas BCB/Caixa |

**T3 — maior ROI de conversão:** encontra R$ esquecido → converte usuário na hora.
SVR BACEN tem ~R$8,5 bilhões não reclamados no Brasil.

---

### OPP — Radar de Oportunidades
*Funcionalidade nova: detecta dinheiro parado e compara 12+ bancos sem viés*

| Sub-feature | Descrição | Status |
|-------------|-----------|--------|
| OPP.1 | Detecção de dinheiro parado em conta corrente | ✅ Implementado (detector + reserva de emergência + threshold R$500/30d) |
| OPP.2 | Comparação de CDB/LCI/LCA por retorno líquido após IR | ✅ Implementado (BankComparator + IRPFCalculator; catálogo curado + Open Finance) |
| OPP.3 | Comparação Tesouro SELIC vs. CDB vs. poupança | ✅ Implementado (calc_ir_on_tesouro_selic + TreasuryComparatorService + tool simulate_investment) |
| OPP.4 | Identificação de poupança abaixo do CDI | ✅ Implementado (savings_rate SELIC+TR, SavingsVsCdiService, card SAVINGS_BELOW_CDI) |
| OPP.5 | Recomendação de troca com passos práticos | ✅ Implementado (steps por produto na API, chat e card do dashboard) |

**Extensões V2 já entregues:** scorecard por banco com ajuste a risco
(`GET /opportunities/{user_id}/banks`), catálogo público transparente
(`GET /opportunities/products`), conector Open Finance Dados Abertos com job
diário de refresh (02h30), disclaimer regulatório em todas as respostas,
cards de feed (SAVINGS_BELOW_CDI, IDLE_MONEY_DETECTED) e card no dashboard.

**Bank Match (camada geral):** `GET /opportunities/{user_id}/bank-match` e tool
`get_best_bank` — recomenda o melhor banco pelo perfil completo do usuário,
ponderando rendimento líquido ajustado a risco, tarifas típicas (market_fees_db
do F5), força dos cartões do emissor (catálogo do optimizer F2) e fit com o
perfil (FSS, tipo de investidor), com pesos adaptativos e explicação por
componente. Catálogo com reload automático (mtime/TTL) ao ser atualizado pelo
job do Open Finance.

**Bancos/produtos comparados na V1:** Nubank, Inter, C6, PicPay, BTG, XP, Itaú,
Bradesco, Santander, BB, Caixa, Sicoob, Tesouro Direto.

**Lógica de detecção:**
- Compara saldo médio dos últimos 3 meses com média de gastos mensais
- Ocioso = saldo − (N meses de gastos) − reserva de emergência
- Threshold mínimo: R$500 por 30+ dias
- Ranking por retorno líquido real após IR (não por taxa bruta)

---

### V — Viral / Comunidade
*CAC gratuito via indignação + dado pessoal*

| ID | Funcionalidade | Prioridade | Esforço Est. | Dependência |
|----|----------------|------------|--------------|-------------|
| V1 | Placar de Economia Compartilhável (card PNG para redes) | Média | 1–2 sem | Consolidação de todos os insights |
| V2 | Relatório Anual "Seu Banco vs Você" (Wrapped) | Média | 3–4 sem | F1+F2+F5+F13 com 12m de dados |
| V3 | Ranking de Bancos Mais Abusivos (relatório trimestral público) | Baixa | 4+ sem | D1+D2+D3 + anonimização |

**V1 hook:** "O Bradesco ganhou R$3.200 de mim em 2025. E você?" — Janeiro viraliza.
**V2 hook:** "Você perdeu R$840 em tarifas que não deveria ter pago."

---

### R — Retenção

| ID | Funcionalidade | Prioridade | Status |
|----|----------------|------------|--------|
| R1.a | F7 Modo Compra no momento da compra | — | ✅ Implementado — `GET /purchase/checkout-context` (veredito compacto para o momento da compra), `GET /purchase/recent-review` + card PURCHASE_FOLLOWUP no feed (análise retroativa de compras grandes) e tool `review_recent_purchases` no chat |
| R1.b | MX.3 Notificações proativas | — | ✅ Implementado — NotificationEngine roda a cada 6h via APScheduler e entrega por email/in_app (delivery_service), com dedup por TTL |
| R1.c | Daily digest (email ou push) | Média | ✅ Implementado — job 07h00 com score, tarifas, oportunidades, prazos fiscais (R2.c) e desafios concluídos (R2.b); idempotente via daily_digest_log |
| R1.d | Widget safe-to-spend (homescreen mobile) | Baixa | ✅ API pronta — `GET /safe-to-spend/{user_id}/widget` (payload ~200 bytes com status semafórico, cor e headline); render nativo aguarda app mobile/PWA |
| R2.a | OPP Radar de Produtos | — | ✅ Implementado (ver seção OPP acima) |
| R2.b | Health Score com badges e desafios mensais | Média | ✅ Implementado — ChallengeService (SEM_TARIFAS, REDUZIR_CATEGORIA, GUARDAR_VALOR, SUBIR_SCORE), badges PRIMEIRO_DESAFIO/DESAFIO_TRIPLO/DESAFIO_STREAK_3, `GET /health-score/challenges`, cards no feed e tool `get_monthly_challenges` |
| R2.c | Sazonalidade fiscal (alertas IR, FGTS, 13º) | Média | ✅ Implementado — módulo `app/seasonality/` (IR, restituição, IPVA/IPTU, DAS/DASN-SIMEI, 13º, lucro FGTS) personalizado por perfil MEI/CLT, `GET /seasonality/{user_id}`, card FISCAL_SEASON no feed, tool `get_fiscal_calendar` e prazos urgentes no daily digest |
| R3.a | Histórico financeiro acumulado | — | Implementado (DuckDB) |
| R3.b | Metas financeiras com projeção | — | Implementado (MX.2) |
| R3.c | Modo Família (multi-usuário compartilhado) | Baixa | Nova infra — 4+ sem |
| R4.a | Relatório trimestral automático | Média | A desenvolver — requer scheduler |
| R4.b | Alerta de promoções de milhas/pontos | Parcial | PromotionTracker existe |
| R5.a | Tela de cancelamento com impacto calculado | Média | 1 sem (frontend) |
| R5.b | Modo pausa / downgrade gracioso | Baixa | Requer billing |
| R5.c | Win-back automático após inatividade | Baixa | Requer scheduler + analytics |

---

## Priorização de Sprints

### Sprint 1 — Conversão & Ativação (objetivo: primeiro R$ recuperado para o usuário)
1. **OPP** Radar de Oportunidades — dinheiro parado + comparação de bancos
2. **D3** Detector de Juros Abusivos — aproveita F13 + BacenConnector já prontos
3. **T3** Monitor de Direitos Esquecidos — maior hook de conversão (acha R$ esquecido)
4. **D1** Venda Casada — diferencial competitivo e legal imediato

### Sprint 2 — Retenção & Profundidade (objetivo: razão para voltar todo dia)
5. **D2** Cobranças Indevidas — amplia F5 com baseline histórico e detecção de duplicidade
6. **D4** Mudança Unilateral — amplia MX.3 com baseline de tarifas por banco
7. **V1** Placar compartilhável — CAC gratuito via redes sociais
8. **R2.b** Health Score gamificado — badges, desafios, níveis

### Sprint 3 — Diferencial Profundo (objetivo: impossível de replicar rapidamente)
9. **D5** Central de Evidências + **D6** Portabilidade — requer validação jurídica
10. **T1** + **T2** Otimizador IR — requer integração com corretoras via Pluggy
11. **V2** Wrapped anual — depende de história acumulada de 12 meses
12. **R1.c** Daily digest — scheduler + SMTP/push notifications

---

## Gaps Técnicos a Resolver

### Gap 1 — Produto Mobile (impacto: Alto)
A maioria das funcionalidades de retenção diária depende de mobile.
- Sem mobile: sem widget de safe-to-spend, sem push notifications, sem "modo compra no momento"
- O que falta: React Native ou PWA com push notifications e widget homescreen
- Nota: cards virais (V1/V2) funcionam de web. Mas uso diário exige mobile.

### Gap 2 — Scheduler / Cron (impacto: Médio)
Daily digest, relatório trimestral, alertas D4 e R2.c precisam de execução periódica.
- O que falta: Celery + Redis (Redis já existe na infra) ou APScheduler
- Estimativa: 1 semana para infraestrutura básica

### Gap 3 — Base de Tarifas Bancárias (impacto: Médio)
D4 (mudança unilateral) e V3 (ranking de bancos) precisam de baseline histórico de tarifas.
- O que falta: coleta periódica manual ou crawler das páginas de tarifas dos bancos
- Fontes: Páginas de tarifas dos bancos + BACEN (consulta de tarifas é pública)

### Gap 4 — APIs de Direitos Públicos (impacto: Alto para T3)
T3 Monitor de Direitos Esquecidos requer:
- SVR BACEN: `https://www.bcb.gov.br/moenational/svr` (pública)
- FGTS: App FGTS da Caixa tem API de consulta por CPF
- PIS/PASEP: Dataprev
- Restituição IR: Receita Federal (scraping ou consulta pública)

### Gap 5 — Validação Jurídica (impacto: Alto para D5/D6)
Templates de petição para JEC e cartas de portabilidade precisam de revisão por advogado.
Sem isso, não lançar D5/D6 para evitar responsabilidade por orientação jurídica incorreta.

---

## Arquivos Criados como Base Técnica

> ⚠️ **Correção (verificado 2026-06-24):** nenhum dos arquivos abaixo existe no repositório atual.
> `backend/app/opportunities/` **não existe** (nenhum arquivo, nenhuma pasta) e `backend/data/bank_products.json`
> **não existe**. O módulo OPP é 100% greenfield — não há rascunho estrutural iniciado, contrário ao que esta
> seção afirmava antes. A lista abaixo é mantida como **proposta de estrutura inicial** (não como inventário do
> que já existe):

- `backend/data/bank_products.json` — catálogo curado de produtos por banco (a criar)
- `backend/app/opportunities/__init__.py` — módulo (a criar)
- `backend/app/opportunities/models.py` — modelos Pydantic (request/response) (a criar)
- `backend/app/opportunities/services/__init__.py` — pasta de serviços (a criar)
- `backend/app/opportunities/services/bank_comparator.py` — comparador (a criar)

Nenhum router está registrado em `backend/app/api/v1/router.py` — começar este módulo não quebra nada no estado atual.

---

## Métricas de Sucesso (Referência)

| Métrica | Estado Atual | Meta 6 meses |
|---------|--------------|--------------|
| Módulos implementados | 15 (todos confirmados registrados em `api/v1/router.py`, verificado 2026-06-24) | 22+ |
| Cobertura de testes | desconhecida — sem relatório no repo (1.757 testes coletados via pytest em 2026-06-24; "89%" não pôde ser confirmado) | ≥ 85% |
| Valor identificado por usuário/mês | — | R$50–500/mês |
| Features de defesa do consumidor | 0 | 4 (D1–D4) |
| Tempo até primeiro insight após conexão | — | < 30s |
| Taxa de viralização (V1 share rate) | — | ≥ 15% dos usuários ativos |
