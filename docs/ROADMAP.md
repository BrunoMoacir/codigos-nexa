# Nexa — Roadmap de Produto e Arquitetura

**Visão:** Um app que otimiza cada centavo do usuário, sem parcialidade entre bancos.
O consultor financeiro que os bancos não querem que você tenha.

> **Auditoria de 2026-06-24:** este documento foi conferido linha a linha contra o código real
> (`backend/app/`, `backend/alembic/versions/`, `backend/tests/`). Onde a afirmação original estava
> errada ou desatualizada, foi corrigida no lugar e marcada com "↳ verificado". Nenhum conteúdo
> original foi removido — apenas corrigido ou complementado.

> **Re-auditoria de 2026-07-18:** o repositório avançou muito desde 24/06 e várias correções daquela
> auditoria ficaram, por sua vez, desatualizadas. Nesta passada: OPP, D1–D6, T1–T3, seasonality,
> viral (V1/V2), scheduler completo (6 jobs), daily digest, PWA/Web Push e hardening de segurança
> **estão implementados** (ver [README](../README.md) para o inventário completo). Notas corrigidas
> abaixo estão marcadas com "↳ verificado 2026-07-18".

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
- 29 tools especializadas com acesso a todos os módulos do backend (↳ verificado 2026-07-18: contagem em `backend/app/agent/tools/`)
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
| MX.3 | Notificações Contextuais | ↳ verificado 2026-07-18: **completo** — 17 tipos de card, filtro de relevância por renda, scheduler a cada 6h e entrega email/in-app/Web Push |
| MX.4 | Peers | Benchmark anônimo com perfis financeiros similares |
| AI Chat | Agente LangGraph ReAct | Consultor financeiro conversacional com 29 tools (↳ verificado 2026-07-18) |

↳ **verificado 2026-07-18:** a tabela acima é o inventário da Fase 1. Desde então também estão
implementados e registrados em `api/v1/router.py`: **OPP** (Radar de Oportunidades + Bank Match),
**D1–D6** (Defesa do Consumidor), **T1–T3** (impostos e direitos — T3 orientativo, ver Gap 4),
**R2.c** (sazonalidade fiscal), **V1/V2** (placar + Wrapped SVG), goals, purchase (checkout-context),
health_score com desafios/badges, privacy LGPD (export/erase) e push (VAPID). Inventário completo no
[README](../README.md).

**Infra:** Python 3.11+ (`pyproject.toml`, roda em 3.13 localmente) + FastAPI + PostgreSQL + DuckDB + Redis + LangGraph + LangChain.
↳ **verificado 2026-06-24:** Anthropic/OpenAI são usados via import dinâmico (`architect/services/llm_reasoner.py`,
`negotiator/script_generator.py`) e via `langchain-anthropic`/`langchain-openai`; os SDKs puros `anthropic`/`openai`
não estão pinados em `requirements.txt`.
**Testes:** ↳ **verificado 2026-07-18:** 2.189 testes coletados via `pytest --collect-only`, **sem erros
de coleção** (os 3 erros apontados na auditoria de 2026-06-24 foram resolvidos). Política do projeto:
suíte 100% verde. Ainda não há relatório de cobertura no repo.

---

## Roadmap por Vertical

### D — Defesa do Consumidor
*Diferencial competitivo: o único app que fica do lado do usuário contra o banco*

↳ **verificado 2026-07-18: D1–D6 estão implementados** em `backend/app/defense/` (6 serviços,
endpoints `/defense/{user_id}`, `/dossier`, `/zip`, `/portability` + 6 tools no agente).
**D5/D6 permanecem bloqueados para lançamento pela validação jurídica (Gap 5).** A tabela abaixo é
mantida como registro do planejamento original:

| ID | Funcionalidade | Prioridade | Esforço Est. | Base técnica existente |
|----|----------------|------------|--------------|------------------------|
| D1 | Detector de Venda Casada (CDC art. 39) | Alta | 2–3 sem | F5 costs + Pluggy |
| D2 | Recuperador de Cobranças Indevidas | Alta | 2–3 sem | F5 + baseline histórico |
| D3 | Detector de Juros Abusivos (BACEN SGS 20714/20715 + STJ REsp 1.061.530) | Alta | 1–2 sem | F13 + BacenConnector (parcial — ver nota ↓) |
| D4 | Alerta de Mudança Unilateral de Tarifa | Média | 1–2 sem | MX.3 + baseline banco |
| D5 | Central de Evidências (dossiê PROCON / JEC) | Média | 4+ sem | D1+D2+D3 + validação jurídica |
| D6 | Simulador de Portabilidade Total (conta + cartão + crédito + salário + investimentos) | Baixa | 4+ sem | F3 + Res. BACEN 4.292/2013 |

**Fluxo D5 (maior impacto):** Detecta → Calcula valor a recuperar → Gera dossiê → Modelo de petição JEC

↳ **Nota sobre D3 (verificado 2026-07-18):** a lacuna apontada em 2026-06-24 foi fechada — o conector
das séries SGS específicas existe (`backend/app/architect/connectors/bacen_credit.py`, séries 20714
rotativo PF / 20706 cheque especial) e é usado pelo detector D3
(`backend/app/defense/services/abusive_interest_detector.py`), com base legal Tema 27/STJ
(REsp 1.061.530/RS) e linguagem de "indício" (nunca promessa de direito).

---

### T — Fiscal e Tributária

| ID | Funcionalidade | Prioridade | Esforço Est. | Base técnica existente |
|----|----------------|------------|--------------|------------------------|
| T1 | Otimizador de IR (tax loss harvesting, timing de resgate, migração de fundos) | Média | 3–4 sem | Pluggy investimentos |
| T2 | Modo Imposto Zero (CDB→LCI/LCA, poupança→Tesouro SELIC, come-cotas) | Média | 2–3 sem | OPP (Radar) |
| T3 | Monitor de Direitos Esquecidos (SVR BACEN, FGTS, PIS/PASEP, restituição IR, dividendos B3) | Alta | 2–3 sem | APIs públicas BCB/Caixa |

↳ **atualizado 2026-07-18:** T1 e T2 implementados (`app/tax/`). T3 agora tem **consulta real**
nas duas fontes que importam: SVR via consulta assistida (API pública oficial do BACEN, captcha
respondido pelo usuário no app) e restituição IRPF via API SERPRO com autorização do titular no
e-CAC — ambas validadas ao vivo (ver Gap 4). FGTS/PIS seguem orientativos. O hook "existe dinheiro
em seu nome? — resposta na hora" é agora **verdadeiro para o SVR**; para marketing, a formulação
correta é "verificamos na hora se há valores em seu nome no BACEN" (o montante aparece no portal
GOV.BR do usuário).

**T3 — maior ROI de conversão:** SVR BACEN tem ~R$ 6,2 bilhões não reclamados no Brasil
(BACEN, mai/2026; era ~R$ 8,5 bi antes da transferência de R$ 5,7 bi ao FGO pela Lei 14.973/2024).

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

| ID | Funcionalidade | Prioridade | Status (2026-07-18) |
|----|----------------|------------|---------------------|
| V1 | Placar de Economia Compartilhável (card SVG para redes) | Média | ✅ Implementado — `GET /viral/savings-card/{user_id}[/svg]` |
| V2 | Relatório Anual "Seu Banco vs Você" (Wrapped) | Média | ✅ Implementado — `GET /viral/wrapped/{user_id}/{year}[/svg]`; lançamento público planejado para dezembro |
| V3 | Ranking de Bancos Mais Abusivos (relatório trimestral público) | Baixa | 📅 A desenvolver — depende de massa de dados D1–D3 (`bank_fee_trends`) |

**V1 hook:** "O Bradesco ganhou R$3.200 de mim em 2025. E você?" — Janeiro viraliza.
**V2 hook:** "Você perdeu R$840 em tarifas que não deveria ter pago."

---

### R — Retenção

| ID | Funcionalidade | Prioridade | Status |
|----|----------------|------------|--------|
| R1.a | F7 Modo Compra no momento da compra | — | ✅ Implementado — `GET /purchase/checkout-context` (veredito compacto para o momento da compra), `GET /purchase/recent-review` + card PURCHASE_FOLLOWUP no feed (análise retroativa de compras grandes) e tool `review_recent_purchases` no chat |
| R1.b | MX.3 Notificações proativas | — | ✅ Implementado — NotificationEngine roda a cada 6h via APScheduler e entrega por email/in_app/push (delivery_service), com dedup por TTL; cards WARNING/CRITICAL sobem automaticamente para Web Push quando o usuário tem inscrição PWA ativa |
| R1.c | Daily digest (email ou push) | Média | ✅ Implementado — job 07h00 com score, tarifas, oportunidades, prazos fiscais (R2.c) e desafios concluídos (R2.b); idempotente via daily_digest_log |
| R1.d | Widget safe-to-spend (homescreen mobile) | Baixa | ✅ Implementado via PWA — `GET /safe-to-spend/{user_id}/widget` (payload ~200 bytes) + página `/widget` instalável (manifest + service worker + atalho de homescreen) e Web Push com VAPID (`/push/*`, tabela push_subscriptions). Widget nativo de homescreen segue dependendo de app mobile (Gap 1) |
| R2.a | OPP Radar de Produtos | — | ✅ Implementado (ver seção OPP acima) |
| R2.b | Health Score com badges e desafios mensais | Média | ✅ Implementado — ChallengeService (SEM_TARIFAS, REDUZIR_CATEGORIA, GUARDAR_VALOR, SUBIR_SCORE), badges PRIMEIRO_DESAFIO/DESAFIO_TRIPLO/DESAFIO_STREAK_3, `GET /health-score/challenges`, cards no feed e tool `get_monthly_challenges` |
| R2.c | Sazonalidade fiscal (alertas IR, FGTS, 13º) | Média | ✅ Implementado — módulo `app/seasonality/` (IR, restituição, IPVA/IPTU, DAS/DASN-SIMEI, 13º, lucro FGTS) personalizado por perfil MEI/CLT, `GET /seasonality/{user_id}`, card FISCAL_SEASON no feed, tool `get_fiscal_calendar` e prazos urgentes no daily digest |
| R3.a | Histórico financeiro acumulado | — | Implementado (DuckDB) |
| R3.b | Metas financeiras com projeção | — | Implementado (MX.2) |
| R4.a | Relatório trimestral automático | Média | A desenvolver — ↳ verificado 2026-07-18: o scheduler já existe (Gap 2 resolvido); falta apenas escrever o job |
| R4.b | Alerta de promoções de milhas/pontos | Parcial | PromotionTracker existe |
| R5.a | Tela de cancelamento com impacto calculado | Média | 1 sem (frontend) |
| R5.b | Modo pausa / downgrade gracioso | Baixa | Requer billing |
| R5.c | Win-back automático após inatividade | Baixa | Requer scheduler + analytics |

---

## Priorização de Sprints

↳ **verificado 2026-07-18:** Sprints 1 e 2 estão entregues (T3 na forma orientativa — ver seção T).
Do Sprint 3, entregues os itens 9 (código pronto; aguarda validação jurídica), 10, 11 e 12.
Mantido como registro histórico da priorização.

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

### Gap 1 — Produto Mobile (impacto: Alto) — ⚠️ parcialmente resolvido
↳ **verificado 2026-07-18:** o PWA cobre widget de safe-to-spend (página `/widget` instalável,
payload ~200 bytes) e push notifications (Web Push VAPID, tabela `push_subscriptions`).
- O que ainda falta: app nativo (widget de homescreen nativo, push FCM) para retenção diária de massa
- Nota: cards virais (V1/V2) funcionam de web.

### Gap 2 — Scheduler / Cron (impacto: Médio) — ✅ resolvido
↳ **verificado 2026-07-18:** APScheduler com lock distribuído Redis (`SET NX EX`) e 6 jobs em
`backend/app/jobs/` (fee_snapshot 02h, catálogo 02h30, opportunity_scan 03h, health_score 04h,
notificações 6/6h, daily digest 07h). Falta apenas o job do relatório trimestral (R4.a).

### Gap 3 — Base de Tarifas Bancárias (impacto: Médio) — ⚠️ parcialmente resolvido
↳ **verificado 2026-07-18:** o job `fee_snapshot` já constrói baseline de mercado anonimizado a
partir dos próprios usuários (`bank_fee_history` / `bank_fee_trends`) — mas ele só ganha
representatividade com massa de usuários.
- O que ainda falta: crawler/coleta das tabelas públicas de tarifas dos bancos para dar baseline
  desde o dia 1 (BACEN publica consulta de tarifas)

### Gap 4 — APIs de Direitos Públicos (impacto: Alto para T3) — ✅ resolvido para SVR e IRPF
↳ **atualizado 2026-07-18 (validado ao vivo):** duas consultas REAIS implementadas em
`app/rights/connectors/`, ambas por canais oficiais:
- **SVR — consulta assistida** (`svr_public.py`): usa a consulta pública oficial do BACEN
  (`/publico/rest/captcha` + `/publico/rest/valoresAReceber/...`), com o usuário respondendo o
  captcha oficial no app (humano no loop; sem contorno). Responde na hora se existe valor a
  receber; montante/resgate seguem no portal com GOV.BR. CPF nunca é persistido.
- **Restituição IRPF — consulta autorizada** (`serpro_restituicao.py`): API oficial Consulta
  Restituição do SERPRO (`gateway.apiserpro.serpro.gov.br/consulta-restituicao/v1`), mediante
  token de Autorização de Compartilhamento gerado pelo titular no e-CAC; decriptação
  RSA PKCS#1 dos campos (valor, situação, banco). Trial validado ponta a ponta; produção
  requer contratação na Loja SERPRO.
- **FGTS / PIS-PASEP:** seguem sem API para terceiros → orientativos.
- O mock que fabricava valores por hash do CPF em `app/fiscal/rights_monitor/` **foi removido**;
  a visão fiscal agora aponta para os fluxos reais, sem inventar valores.

### Gap 5 — Validação Jurídica (impacto: Alto para D5/D6)
Templates de petição para JEC e cartas de portabilidade precisam de revisão por advogado.
Sem isso, não lançar D5/D6 para evitar responsabilidade por orientação jurídica incorreta.

---

## Arquivos Criados como Base Técnica

> ✅ **Atualização (verificado 2026-07-18):** a correção de 2026-06-24 (que dizia que o módulo OPP
> não existia) ficou obsoleta — o módulo foi implementado integralmente depois daquela data.
> `backend/app/opportunities/` existe com 18 arquivos (~3.100 linhas), `backend/data/bank_products.json`
> existe, e o router está registrado em `api/v1/router.py`. Entregas: OPP.1–OPP.5, Bank Match,
> scorecard por banco, catálogo público e conector Open Finance Dados Abertos com refresh diário
> (job 02h30). Ver a seção OPP acima e o [README](../README.md).

---

## Métricas de Sucesso (Referência)

| Métrica | Estado Atual (verificado 2026-07-18) | Meta 6 meses |
|---------|--------------------------------------|--------------|
| Módulos implementados | 20+ registrados em `api/v1/router.py` (core F1–F13, OPP, D1–D6, T1–T3, MX.1–6, R, V1/V2, fiscal, privacy) | 22+ ✅ atingida |
| Cobertura de testes | 2.189 testes coletados, sem erros de coleção; sem relatório de cobertura no repo | ≥ 85% com relatório |
| Valor identificado por usuário/mês | — (sem usuários em produção) | R$50–500/mês |
| Features de defesa do consumidor | 6 (D1–D6 em código; D5/D6 aguardam validação jurídica) | 4 (D1–D4) ✅ atingida |
| Tempo até primeiro insight após conexão | — (medir na beta) | < 30s |
| Taxa de viralização (V1 share rate) | — (medir na beta) | ≥ 15% dos usuários ativos |
