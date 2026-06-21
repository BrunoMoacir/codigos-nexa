# Nexa — Roadmap de Produto e Arquitetura

**Visão:** Um app que otimiza cada centavo do usuário, sem parcialidade entre bancos.
O consultor financeiro que os bancos não querem que você tenha.

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
| MX.3 | Notificações Proativas | Alertas contextuais em tempo real |
| MX.4 | Peers | Benchmark anônimo com perfis financeiros similares |
| AI Chat | Agente LangGraph ReAct | Consultor financeiro conversacional com 15 tools |

**Infra:** Python 3.12 + FastAPI + PostgreSQL + DuckDB + Redis + LangGraph + Anthropic/OpenAI
**Testes:** 414 passando, cobertura 89%

---

## Roadmap por Vertical

### D — Defesa do Consumidor
*Diferencial competitivo: o único app que fica do lado do usuário contra o banco*

| ID | Funcionalidade | Prioridade | Esforço Est. | Base técnica existente |
|----|----------------|------------|--------------|------------------------|
| D1 | Detector de Venda Casada (CDC art. 39) | Alta | 2–3 sem | F5 costs + Pluggy |
| D2 | Recuperador de Cobranças Indevidas | Alta | 2–3 sem | F5 + baseline histórico |
| D3 | Detector de Juros Abusivos (BACEN SGS 20714/20715 + STJ REsp 1.061.530) | Alta | 1–2 sem | F13 + BacenConnector |
| D4 | Alerta de Mudança Unilateral de Tarifa | Média | 1–2 sem | MX.3 + baseline banco |
| D5 | Central de Evidências (dossiê PROCON / JEC) | Média | 4+ sem | D1+D2+D3 + validação jurídica |
| D6 | Simulador de Portabilidade Total (conta + cartão + crédito + salário + investimentos) | Baixa | 4+ sem | F3 + Res. BACEN 4.292/2013 |

**Fluxo D5 (maior impacto):** Detecta → Calcula valor a recuperar → Gera dossiê → Modelo de petição JEC

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
| OPP.1 | Detecção de dinheiro parado em conta corrente | A desenvolver |
| OPP.2 | Comparação de CDB/LCI/LCA por retorno líquido após IR | A desenvolver |
| OPP.3 | Comparação Tesouro SELIC vs. CDB vs. poupança | A desenvolver |
| OPP.4 | Identificação de poupança abaixo do CDI | A desenvolver |
| OPP.5 | Recomendação de troca com passos práticos | A desenvolver |

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
| R1.a | F7 Modo Compra no momento da compra | — | Implementado |
| R1.b | MX.3 Notificações proativas | — | Implementado |
| R1.c | Daily digest (email ou push) | Média | A desenvolver — requer scheduler |
| R1.d | Widget safe-to-spend (homescreen mobile) | Baixa | Requer app mobile |
| R2.a | OPP Radar de Produtos | — | A desenvolver (ver acima) |
| R2.b | Health Score com badges e desafios mensais | Média | A desenvolver — MX.1 já existe |
| R2.c | Sazonalidade fiscal (alertas IR, FGTS, 13º) | Média | A desenvolver |
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

Os arquivos abaixo foram criados como rascunho estrutural do módulo OPP,
mas o desenvolvimento completo não foi iniciado ainda:

- `backend/data/bank_products.json` — catálogo curado de 19 produtos de 12 bancos
- `backend/app/opportunities/__init__.py` — módulo vazio
- `backend/app/opportunities/models.py` — modelos Pydantic (request/response)
- `backend/app/opportunities/services/__init__.py` — pasta de serviços vazia
- `backend/app/opportunities/services/bank_comparator.py` — rascunho do comparador

Nenhum router foi registrado — não quebra nada no estado atual.

---

## Métricas de Sucesso (Referência)

| Métrica | Estado Atual | Meta 6 meses |
|---------|--------------|--------------|
| Módulos implementados | 15 | 22+ |
| Cobertura de testes | 89% | ≥ 85% |
| Valor identificado por usuário/mês | — | R$50–500/mês |
| Features de defesa do consumidor | 0 | 4 (D1–D4) |
| Tempo até primeiro insight após conexão | — | < 30s |
| Taxa de viralização (V1 share rate) | — | ≥ 15% dos usuários ativos |
