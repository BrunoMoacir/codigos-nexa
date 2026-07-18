<div align="center">

# NEXA AI

### **Seu Dinheiro. Seu Lado.**

*O advogado financeiro que os bancos não querem que você tenha.*

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Tests](https://img.shields.io/badge/Tests-2.189%20coletados-success?style=flat-square)](backend/tests/)
[![License](https://img.shields.io/badge/License-Proprietary-red?style=flat-square)](LICENSE)

[Como Construímos Valor](#-como-a-nexa-constrói-valor) •
[Funcionalidades](#-funcionalidades) •
[O Que Está Pronto vs O Que Falta](#-o-que-está-pronto-vs-o-que-falta) •
[Planos](#-planos-e-monetização) •
[Arquitetura](#-arquitetura-técnica)

---

</div>

## 📋 Índice

<details>
<summary><strong>Clique para expandir</strong></summary>

- [Visão Geral](#-visão-geral)
- [O Problema](#-o-problema)
- [Como a Nexa Constrói Valor](#-como-a-nexa-constrói-valor)
- [As Duas Superfícies do Produto](#-as-duas-superfícies-do-produto)
- [Funcionalidades](#-funcionalidades)
  - [Motor Core de Análise](#motor-core-de-análise)
  - [Radar de Oportunidades (OPP)](#radar-de-oportunidades-opp)
  - [Defesa do Consumidor (D)](#defesa-do-consumidor-d)
  - [Direitos Esquecidos e Impostos (T)](#direitos-esquecidos-e-impostos-t)
  - [Engajamento e Retenção (MX/R)](#engajamento-e-retenção-mxr)
  - [Viral (V)](#viral-v)
  - [Inteligência Comportamental](#inteligência-comportamental)
- [Agente de IA](#-agente-de-ia)
- [Sistema de Notificações](#-sistema-de-notificações-mx3)
- [Jobs Automáticos](#-jobs-automáticos-scheduler)
- [Segurança e LGPD](#-segurança-e-lgpd)
- [Planos e Monetização](#-planos-e-monetização)
- [O Que Está Pronto vs O Que Falta](#-o-que-está-pronto-vs-o-que-falta)
- [Diferencial Competitivo](#-diferencial-competitivo)
- [Estratégias de Crescimento](#-estratégias-de-crescimento)
- [Arquitetura Técnica](#-arquitetura-técnica)
- [Endpoints da API](#-endpoints-da-api)
- [Início Rápido](#-início-rápido)
- [Testes](#-testes)
- [Documentação](#-documentação)

</details>

---

## 🎯 Visão Geral

A **Nexa AI** é uma plataforma de inteligência financeira pessoal que combina **Open Finance**, **Machine Learning** e **IA conversacional** para revelar quanto os bancos lucram com você — e transformar essa informação em ações concretas de economia, recuperação e otimização.

> **Não somos outro banco. Somos o advogado contra todos os bancos.**

A Nexa cobra do usuário, não do banco. Essa é a única estrutura de receita que garante neutralidade total: nenhuma recomendação é comissionada, nenhum produto é empurrado.

---

## 💸 O Problema

O brasileiro médio perde por ano, sem perceber:

| Perda Anual | Causa |
|:---:|:---|
| **R$ 800** | Tarifas bancárias evitáveis |
| **R$ 2.000** | Uso do cartão errado (cashback/pontos perdidos) |
| **R$ 3.500** | Lucro oculto do banco (spread, juros, poupança rendendo abaixo do CDI) |

**Total: ~R$ 6.300/ano drenados silenciosamente.** Além disso, há ~R$ 8,5 bilhões esquecidos no SVR do BACEN, FGTS não sacado e restituições de IR não resgatadas.

---

## ✅ Como a Nexa Constrói Valor

O produto opera um **loop de valor contínuo** em cinco etapas. Cada funcionalidade existe para alimentar uma delas:

```
1. CONECTAR   →  Open Finance (Pluggy): todos os bancos do usuário em 30 segundos
2. REVELAR    →  ETL + 20 módulos analíticos mostram onde o dinheiro está vazando
3. AGIR       →  Cartas de contestação, scripts de negociação, dossiês, passos práticos
4. PROTEGER   →  Safe-to-spend, alertas proativos, calendário fiscal, metas
5. RETER      →  Push, digest diário, desafios mensais, score gamificado, Wrapped
```

Cada etapa entrega valor mensurável em **R$/mês**:

| Etapa | Mecanismo de valor | Exemplo concreto |
|:---|:---|:---|
| **Revelar** | Transparência que nenhum banco oferece | "O Bradesco lucrou R$ 3.200 com você em 2025" |
| **Agir** | Recuperação com base legal (CDC, BACEN, STJ) | Carta de contestação de tarifa com correção monetária |
| **Otimizar** | Decisão certa em cada transação | "Use o cartão X nessa compra: +R$ 34 de cashback" |
| **Realocar** | Dinheiro parado vira rendimento | "R$ 5.000 ociosos → CDB 110% CDI = +R$ 480/ano líquidos" |
| **Proteger** | Prevenção de derrapagem | "Sua margem segura hoje é R$ 87/dia" |

---

## 📱 As Duas Superfícies do Produto

Todo módulo do backend entrega valor por **duas superfícies** — é o padrão arquitetural do produto:

### 1. Feed de Oportunidades
Lista priorizada de cards, ordenada por **impacto financeiro em R$/mês**. Cada card diz: o tipo de oportunidade, o valor em jogo, a urgência e — ao expandir — como foi calculado e os passos práticos para executar. São **17 tipos de card** (ver [Notificações](#-sistema-de-notificações-mx3)), gerados proativamente a cada 6 horas e filtrados por relevância conforme a renda do usuário.

### 2. Chat com Consultor IA
Agente LangGraph ReAct com **29 ferramentas** conectadas a todos os módulos do backend. O usuário pergunta em linguagem natural ("posso comprar um carro de R$ 60 mil?") e o agente consulta forecast, simulações e perfil comportamental antes de responder — com tom adaptado ao cluster do usuário. Histórico persistido por sessão (Redis).

> Regra de ouro do produto: **feature nova só está completa quando aparece no feed E no chat.**

---

## ⚡ Funcionalidades

### Motor Core de Análise

| ID | Funcionalidade | Valor para o usuário | Status |
|:---|:---|:---|:---:|
| F1 | **ETL Pipeline + Cashflow** — 8 estágios, projeção 30 dias, safe-to-spend | Sabe exatamente quanto pode gastar hoje sem comprometer contas futuras | ✅ |
| F2 | **Card Optimizer** — catálogo curado de 81 cartões (37 emissores, 11 programas de fidelidade valorados), multi-card, custo de oportunidade | Recupera R$ 50–200/mês em cashback/pontos que estava deixando na mesa | ✅ |
| F3 | **Nexa Architect** — financiamento vs consórcio vs investir, VPL + Monte Carlo | Decisões de dezenas de milhares de reais com intervalo de confiança de 95% | ✅ |
| F4 | **PF/PJ Classifier** — Random Forest + regras, relatório fiscal MEI | MEI separa gastos pessoais e da empresa automaticamente; base do relatório DAS | ✅ |
| F5 | **Raio-X de Custos** — tarifas detectadas, benchmark de 16 bancos | Vê cada tarifa cobrada e se está acima da média de mercado | ✅ |
| F7 | **Modo Compra Inteligente** — Pix, débito, crédito ou parcelado? | Veredito instantâneo da melhor forma de pagamento para cada compra | ✅ |
| F13 | **Negociador** — scripts personalizados gerados por IA | Roteiro pronto para ligar no banco e negociar anuidade, juros e tarifas | ✅ |
| M4.1 | **Fiscal PJ** — relatório para MEI/PJ | Faturamento, DAS e alertas de limite MEI sem contador | ✅ |

### Radar de Oportunidades (OPP)

*Detecta dinheiro mal alocado e compara o mercado sem viés — **varredura diária de todos os participantes do Open Finance Dados Abertos** (~23 instituições com renda fixa CDI publicada em 2026-07, cresce conforme adesão) com fallback curado. Ranking por retorno **líquido após IR**, não por taxa bruta; taxas-teaser (>130% CDI) são marcadas como promocionais e rebaixadas no ranking.*

| Sub-feature | Valor para o usuário | Status |
|:---|:---|:---:|
| OPP.1 | **Dinheiro parado** — saldo ocioso além da reserva de emergência (threshold R$ 500/30d) | Descobre que tem R$ X rendendo zero na conta corrente | ✅ |
| OPP.2 | **Comparador CDB/LCI/LCA** — retorno líquido após IR, catálogo vivo via Open Finance (varredura completa do diretório + paginação + dedup) com fallback curado | Compara as ofertas publicadas por todos os participantes do Open Finance sem comissão embutida | ✅ |
| OPP.3 | **Tesouro SELIC vs CDB vs poupança** — simulador com IR e taxas | Vê em R$ quanto cada opção rende de verdade no seu prazo | ✅ |
| OPP.4 | **Poupança abaixo do CDI** — SELIC + TR vs CDI | Card mostra quanto está perdendo por manter poupança | ✅ |
| OPP.5 | **Passos práticos de troca** — instruções por produto | Não só "invista melhor": diz exatamente onde clicar | ✅ |
| Bank Match | **Melhor banco pelo perfil completo** — rendimento ajustado a risco + tarifas típicas + força dos cartões + fit comportamental | Resposta definitiva para "qual banco é melhor para mim?" | ✅ |

Extras: scorecard por banco (`GET /opportunities/{user_id}/banks`), catálogo público transparente (`GET /opportunities/products`), refresh diário via Open Finance Dados Abertos, disclaimer regulatório em todas as respostas.

### Defesa do Consumidor (D)

*O diferencial que nenhum banco ou app comissionado pode copiar: ficar do lado do usuário contra o banco.*

| ID | Funcionalidade | Valor para o usuário | Status |
|:---|:---|:---|:---:|
| D1 | **Detector de Venda Casada** (CDC art. 39) | Identifica seguros e pacotes embutidos ilegalmente e o valor a recuperar | ✅ código |
| D2 | **Recuperador de Cobranças Indevidas** — baseline histórico + duplicidades | Detecta cobrança em dobro e tarifa nova não contratada | ✅ código |
| D3 | **Detector de Juros Abusivos** — comparação com séries BACEN + jurisprudência STJ | Prova documentada de que os juros do rotativo/cheque especial estão acima do mercado | ✅ código |
| D4 | **Alerta de Mudança Unilateral de Tarifa** — baseline por banco | Notificação quando o banco aumenta tarifa sem avisar | ✅ código |
| D5 | **Central de Evidências** — dossiê consolidado + export ZIP para PROCON/JEC | Sai do app com o processo pronto para protocolar | ✅ código ⚠️ requer validação jurídica antes de lançar |
| D6 | **Simulador de Portabilidade Total** — conta + cartão + crédito | Quanto economiza migrando tudo para outro banco | ✅ código |

Endpoints: `GET /defense/{user_id}`, `/defense/{user_id}/dossier`, `/defense/{user_id}/zip`, `/defense/{user_id}/portability`.

### Direitos Esquecidos e Impostos (T)

| ID | Funcionalidade | Valor para o usuário | Status |
|:---|:---|:---|:---:|
| T1 | **Otimizador de IR** — tax loss harvesting, timing de resgate | Paga menos imposto legalmente sobre investimentos | ✅ |
| T2 | **Modo Imposto Zero** — migração CDB→LCI/LCA com breakeven | Sabe exatamente quando um LCI isento ganha do CDB tributado | ✅ |
| T3 | **Monitor de Direitos Esquecidos** — SVR BACEN, FGTS, PIS/PASEP, restituição IR | **Consulta REAL do SVR dentro do app** (API pública oficial do BACEN, usuário responde o captcha oficial) + **restituição IRPF em tempo real** (API SERPRO, autorizada pelo usuário no e-CAC); FGTS/PIS seguem orientativos (sem API para terceiros) — ver nota ↓ | ✅ |
| R2.c | **Sazonalidade Fiscal** — IR, DAS/DASN-SIMEI, IPVA/IPTU, 13º, lucro FGTS, personalizado por perfil MEI/CLT | Nunca mais multa por perder prazo fiscal | ✅ |

> **Nota T3 (atualizada 2026-07-18):** consultas reais implementadas em dois níveis, ambas exclusivamente por canais oficiais e validadas ao vivo:
> - **SVR (consulta assistida):** `GET /rights/{user_id}/svr/captcha` + `POST /rights/{user_id}/svr/check` usam a consulta pública oficial do BACEN (a mesma do site) — o usuário responde o desafio de segurança oficial no app e a Nexa informa na hora se existe valor em seu nome. O montante e o resgate seguem no portal com login GOV.BR. CPF/data de nascimento não são persistidos; logs só registram CPF mascarado.
> - **Restituição IRPF (consulta autorizada):** `POST /rights/{user_id}/ir/check` consulta a API oficial Consulta Restituição do SERPRO com o token de Autorização de Compartilhamento que o próprio usuário gera no e-CAC (LGPD art. 7º/11º), decriptando valor, situação e banco (RSA PKCS#1). Requer contrato SERPRO em produção (`SERPRO_CONSUMER_KEY/SECRET`); sem credenciais, o endpoint degrada para o passo a passo de habilitação.
> - **FGTS e PIS/PASEP:** sem API pública para terceiros — permanecem orientativos.
> - O antigo mock de `app/fiscal/rights_monitor/` (valores fabricados por hash do CPF) **foi removido**; a visão fiscal agora aponta para os fluxos reais acima, sem inventar valores.

### Engajamento e Retenção (MX/R)

| ID | Funcionalidade | Valor para o usuário | Status |
|:---|:---|:---|:---:|
| MX.1 | **Health Score** — score 0–100 com tendência e histórico | Um número que resume a saúde financeira, com snapshot diário automático | ✅ |
| MX.2 | **Metas Financeiras** — CRUD, projeção de prazo, progresso | "Nesse ritmo, sua reserva fica pronta em 7 meses" | ✅ |
| MX.3 | **Notificações Proativas** — 17 tipos, filtro de relevância por renda | Só recebe alerta do que importa para o seu bolso (ver seção dedicada) | ✅ |
| MX.4 | **Peer Comparison** — benchmarks IBGE/POF por faixa de renda | "Você gasta 40% mais em delivery que pares da sua renda" | ✅ |
| MX.5 | **Budget Advisor** — plano 50/30/20 adaptado ao perfil comportamental | Orçamento realista, não genérico | ✅ |
| MX.6 | **Shadow Invoices** — parcelas e assinaturas futuras | Vê o caixa já comprometido antes de assumir nova dívida | ✅ |
| R1.a | **Compra no momento** — `GET /purchase/checkout-context` (veredito compacto) + revisão retroativa de compras grandes (card PURCHASE_FOLLOWUP + tool no chat) | Decisão certa na hora do checkout; aprende com compras passadas | ✅ |
| R1.b | **Entrega proativa** — NotificationEngine a cada 6h com entrega email/in-app/push e dedup por TTL | O valor chega ao usuário sem ele abrir o app | ✅ |
| R1.c | **Daily Digest** — email 07h00 com score, tarifas, oportunidades, prazos fiscais e desafios | Resumo diário idempotente; razão para voltar todo dia | ✅ |
| R1.d | **Widget Safe-to-Spend (PWA)** — página `/widget` instalável + Web Push VAPID | Margem do dia na homescreen, payload de ~200 bytes | ✅ |
| R2.b | **Desafios mensais e badges** — SEM_TARIFAS, REDUZIR_CATEGORIA, GUARDAR_VALOR, SUBIR_SCORE + badges de streak | Gamificação com impacto real no bolso | ✅ |
| R3 | **Histórico acumulado** (DuckDB) + metas com projeção | Quanto mais tempo usa, mais insight — custo de troca cresce | ✅ |
| R4.b | **PromotionTracker** — promoções de transferência de pontos | Bônus de 20%+ em milhas não passa despercebido | ⚠️ parcial |

### Viral (V)

| ID | Funcionalidade | Valor / mecânica | Status |
|:---|:---|:---|:---:|
| V1 | **Placar de Economia Compartilhável** — card SVG com o total economizado | "Economizei R$ 4.200 contra os bancos com a @NexaAI" → CAC zero | ✅ |
| V2 | **Nexa Wrapped anual** — relatório "Seu Banco vs Você" com SVG compartilhável | Quanto cada banco lucrou com você no ano; viralização estilo Spotify Wrapped | ✅ |
| V3 | **Ranking público de bancos abusivos** — relatório trimestral anonimizado | Autoridade de marca + imprensa | 📅 |

Endpoints: `GET /viral/savings-card/{user_id}[/svg]`, `GET /viral/wrapped/{user_id}/{year}[/svg]`.

### Inteligência Comportamental

*A camada que personaliza tudo: mesmos dados, recomendações diferentes por pessoa.*

| Módulo | O que faz | Onde atua |
|:---|:---|:---|
| **ConsumptionProfiler** | Classifica o usuário em 1 de 8 clusters de estilo de vida (90 dias de transações; regras determinísticas calibradas — substituição por modelo ML prevista na Fase 3) | Agente, optimizer, budget, notificações — 6+ módulos |
| **LifeEventsDetector** | Detecta bebê, mudança, casamento, faculdade, aumento/queda de renda via padrão de gastos | Cards LIFE_EVENT com ação sugerida |
| **NotificationRelevanceFilter** | Elimina ruído com thresholds escalados por renda | Mesmo evento é ruído para quem ganha R$ 15k e crítico para quem ganha R$ 2k |
| **IncomeProfiler** | Renda real após filtrar transferências e não-recorrentes | Base de todos os thresholds |

Os 8 clusters: `EXPLORADOR_GLOBAL` (milhas/lounge), `URBANO_FOODIE` (cashback alimentação), `INVESTIDOR_CAUTELOSO` (precisão numérica), `FAMILIA_ESTRUTURADA` (segurança/educação), `DIGITAL_NATIVO` (PIX/fintechs), `ESTRESSE_FINANCEIRO` (empatia, cortes, zero sugestão de gasto), `MICROEMPREENDEDOR` (PF vs PJ, DAS), `NAO_CLASSIFICADO` (neutro).

---

## 🤖 Agente de IA

Agente **ReAct (LangGraph)**: o LLM decide qual ferramenta chamar, observa o resultado e responde em linguagem natural. A primeira ferramenta de toda sessão é `get_user_profile_context`, que carrega o cluster comportamental e adapta o tom da conversa inteira. O `user_id` autenticado é injetado como contexto imutável — o agente ignora qualquer user_id vindo da mensagem (mitigação de prompt injection).

### 29 Ferramentas Financeiras

| Domínio | Ferramentas |
|:---|:---|
| **Perfil e saúde** | `get_user_profile_context` · `get_financial_forecast` · `get_spending_alerts` · `get_goals_summary` |
| **Orçamento e pares** | `get_budget_advice` · `get_peer_comparison` |
| **Cartões** | `get_card_optimization` · `get_expert_card_analysis` |
| **Compras** | `get_purchase_recommendation` · `review_recent_purchases` |
| **Simulações (F3)** | `get_financing_simulation` · `get_timing_scenarios` · `get_leverage_simulation` |
| **Oportunidades (OPP)** | `get_opportunities` · `simulate_investment` · `get_best_bank` |
| **Defesa (D)** | `detect_abusive_fees` · `detect_wrongful_charges` · `detect_abusive_interest` · `get_defense_analysis` · `get_evidence_dossier` · `get_portability_analysis` |
| **Custos e negociação** | `get_bank_cost_analysis` · `get_negotiation_script` |
| **Fiscal e direitos** | `get_fiscal_report` · `get_fiscal_calendar` · `get_forgotten_rights` |
| **Engajamento** | `get_monthly_challenges` · `get_annual_wrapped` |

LLM: Claude (preferencial, via `langchain-anthropic`) com fallback OpenAI. Memória de sessão via checkpointer Redis.

---

## 🔔 Sistema de Notificações (MX.3)

O `ProactiveNotifier` gera cards de **17 tipos**, combinando burn rate, anomalias, score, metas, assinaturas, eventos de vida, oportunidades, calendário fiscal e desafios. O `NotificationRelevanceFilter` aplica um pipeline de 3 etapas para eliminar ruído.

| Tipo | Gatilho | Prioridade |
|:---|:---|:---:|
| `BURN_RATE_HIGH` | Categoria consumiu >70% do orçamento | WARNING / CRITICAL |
| `ANOMALY_DETECTED` | Gasto ≥2.5× acima do padrão histórico | WARNING / CRITICAL |
| `SUBSCRIPTION_INCREASE` | Assinatura ficou ≥15% mais cara | WARNING |
| `CARD_OPPORTUNITY` | Cashback perdido por usar cartão errado | INFO |
| `WAIVER_ALERT` | Faltam R$ X para isentar anuidade | INFO |
| `TRANSFER_PROMO` | Transferência de pontos com bônus ≥20% | INFO |
| `SCORE_IMPROVED` | Health Score variou ≥5 pontos | INFO / WARNING |
| `GOAL_PROGRESS` | Meta atingiu 50%, 75% ou 100% | INFO |
| `SAFE_TO_SPEND_LOW` | Margem diária abaixo de R$ 100/dia | WARNING / CRITICAL |
| `LIFE_EVENT` | Evento de vida detectado via gastos | INFO → CRITICAL |
| `TARIFA_AUMENTO_UNILATERAL` | Banco subiu tarifa sem contrapartida (D4) | WARNING |
| `SAVINGS_BELOW_CDI` | Poupança rendendo abaixo do CDI (OPP.4) | INFO |
| `IDLE_MONEY_DETECTED` | Dinheiro parado confirmado (OPP.1) | INFO |
| `FISCAL_SEASON` | Janela fiscal ativa: IR, DAS, 13º… (R2.c) | INFO / WARNING |
| `CHALLENGE_COMPLETED` | Desafio mensal concluído (R2.b) | INFO |
| `CHALLENGE_PROGRESS` | Desafio ≥70% concluído (R2.b) | INFO |
| `PURCHASE_FOLLOWUP` | Compra grande paga de forma subótima (R1.a) | INFO |

### Filtro de Relevância (3 etapas)

```
Bruto → [1: Threshold por tipo] → [2: Cap ≤2/tipo] → [3: Cap global ≤4 não-críticos]
                     ↑
        Thresholds escalam com a renda mensal do usuário
        CRITICAL nunca é descartado em nenhuma etapa
```

Cards WARNING/CRITICAL sobem automaticamente para **Web Push** quando o usuário tem inscrição PWA ativa. Dedup por TTL específico por tipo (ex.: SAVINGS_BELOW_CDI no máximo 1×/mês).

### Life Events

| Evento | Sinal | Ação sugerida |
|:---|:---|:---|
| `new_baby` | Fraldas, maternidade, enxoval | Revisar metas, reserva e seguro de vida |
| `home_change` | Mudança, reforma, móveis | Revisar custos fixos e seguro residencial |
| `wedding` | Buffet, cerimonial | Planejar finanças a dois |
| `new_education` | Mensalidades de ensino | Meta para cobrir 12 meses |
| `income_increase` | Renda >20% acima do histórico | Investir o incremento antes de virar gasto fixo |
| `income_drop` | Renda >20% abaixo do histórico | Cortar gastos, garantir reserva |

---

## ⏰ Jobs Automáticos (Scheduler)

APScheduler com lock distribuído Redis (`SET NX EX`) — seguro em multi-instância. Ativado por `SCHEDULER_ENABLED=true`.

| Horário | Job | O que entrega |
|:---:|:---|:---|
| 02h00 | `fee_snapshot` | Histórico de tarifas por usuário + baseline de mercado (alimenta D2/D4) |
| 02h30 | `product_catalog_refresh` | Atualiza catálogo de produtos via Open Finance Dados Abertos (OPP) |
| 03h00 | `opportunity_scan` | Varredura de dinheiro parado e poupança sub-CDI por usuário |
| 04h00 | `health_score_snapshot` | Série temporal do score (tendência 30/90 dias) |
| a cada 6h | `notification_scheduler` | Gera e entrega notificações proativas (email/in-app/push) |
| 07h00 | `daily_digest` | Email diário com score, tarifas, oportunidades, prazos fiscais e desafios |

---

## 🔐 Segurança e LGPD

*Confiança é o produto: quem entrega extrato bancário completo precisa de mais que promessa.* Hardening auditado em 2026-07 — detalhes em [docs/SEGURANCA.md](docs/SEGURANCA.md).

| Camada | Implementação |
|:---|:---|
| **Autenticação** | JWT HS256 30 min + refresh token de 14 dias com **rotação de uso único** (reuso → 401); blacklist Redis por `jti`; anti-enumeração no login |
| **Autorização** | `require_owner` em todos os endpoints de dados (IDOR bloqueado); recursos aninhados verificam dono do objeto |
| **Webhook Pluggy** | Segredo compartilhado comparado em tempo constante; produção sem segredo → 503 fail-closed; identidade resolvida server-side, nunca do payload |
| **Headers** | CSP estrito, HSTS (produção), X-Frame-Options DENY, COOP, Permissions-Policy; CORS `*` proibido em produção (validador recusa boot) |
| **Rate limiting** | 60/min global por IP (Redis), login 10/min, registro 5/min, refresh 20/min |
| **LGPD** | `GET /privacy/export/{user_id}` (portabilidade, art. 18 V) e `DELETE /privacy/erase/{user_id}` (eliminação irreversível, art. 18 VI, exige frase de confirmação); auditoria com email mascarado |
| **Supply chain** | `pip-audit` no CI — qualquer CVE novo quebra o build |
| **Prompt injection** | `user_id` imutável injetado pelo sistema; agente instruído a ignorar user_id na mensagem |

---

## 💼 Planos e Monetização

> **A Nexa cobra do usuário, não do banco.** Isso garante neutralidade total — e é o que justifica pagar: um consultor comissionado nunca mandaria você sair do banco que o comissiona.

| Plano | Preço | O que entrega | Valor que justifica o preço |
|:---|:---:|:---|:---|
| **Free** | R$ 0/mês | 1 banco conectado, dashboard básico, safe-to-spend, 3 consultas Compra Inteligente/mês, 5 msgs de IA/dia | Porta de entrada: o usuário **vê** quanto está perdendo (indignação → conversão). T3 (direitos esquecidos) no Free orienta onde verificar dinheiro esquecido nos canais oficiais |
| **Pro** | R$ 19,90/mês | Bancos ilimitados, Raio-X completo, Radar de Oportunidades, chat ilimitado, Negociador (1/mês), digest diário, desafios e badges | Se o usuário recupera **R$ 50+/mês** (média esperada: tarifas + cashback + dinheiro parado), o plano se paga 2,5× |
| **Total** | R$ 39,90/mês | Tudo do Pro + Defesa do Consumidor completa (dossiê PROCON/JEC), portabilidade simulada, otimizador de IR, Wrapped trimestral, Modo Família (futuro) | Uma única contestação de tarifa recuperada (R$ 200–800) paga o ano inteiro |

**⚠️ Status de implementação:** os planos estão definidos como modelo de negócio, mas **billing e gating por plano ainda não existem no código** — hoje todos os endpoints são liberados para qualquer usuário autenticado. É um dos itens pendentes (ver seção seguinte).

### Unit Economics Target

| Métrica | Target |
|:---|:---:|
| ARPU | R$ 25/mês |
| CAC | R$ 40–80 |
| LTV (12 meses) | R$ 300 |
| LTV:CAC | > 4:1 |
| Margem bruta | 75%+ |
| Payback | < 3 meses |

---

## 📊 O Que Está Pronto vs O Que Falta

### ✅ Pronto (implementado e testado no backend)

| Área | Entregas |
|:---|:---|
| **Motor core** | F1 ETL + cashflow, F2 optimizer (81 cartões curados de 37 emissores), F3 Architect (Monte Carlo), F4 PF/PJ, F5 custos, F7 compra inteligente, F13 negociador, fiscal MEI/PJ |
| **Oportunidades** | OPP.1–OPP.5 completos + Bank Match + catálogo público + refresh diário |
| **Defesa** | D1–D6 codificados: venda casada, cobranças indevidas, juros abusivos, mudança unilateral, dossiê + ZIP, portabilidade |
| **Direitos e impostos** | T1 otimizador IR, T2 imposto zero, T3 direitos esquecidos (consulta REAL do SVR assistida + restituição IRPF via SERPRO autorizada; FGTS/PIS orientativos), calendário fiscal sazonal |
| **Engajamento** | Health score + desafios + badges, metas, 17 tipos de notificação com filtro de relevância, peer comparison, budget 50/30/20, shadow invoices |
| **Retenção** | Scheduler com 6 jobs, daily digest, entrega email/in-app/push, PWA com widget instalável e Web Push VAPID, checkout-context, revisão de compras |
| **Viral** | Placar de economia (SVG) e Wrapped anual (SVG) |
| **IA** | Agente ReAct com 29 ferramentas, memória Redis, perfil comportamental (8 clusters), life events |
| **Plataforma** | Auth JWT + refresh rotativo, IDOR hardening, LGPD export/erase, rate limiting, audit log, pip-audit no CI, 2.189 testes coletados |

### 🚧 Falta (em ordem de prioridade de negócio)

| Item | O que é | Por que importa | Dependência |
|:---|:---|:---|:---|
| **Billing + gating de planos** | Cobrança (Stripe/Pagar.me) e enforcement Free/Pro/Total nos endpoints | Sem isso não há receita — o modelo de negócio existe só no papel | Decisão de gateway |
| **Frontend oficial** | O `frontend-react/` atual é protótipo de validação (descartável); app oficial será construído do zero | Toda a inteligência do backend precisa de uma casa definitiva | Design system |
| **Validação jurídica (D5)** | Revisão por advogado dos templates de petição JEC e cartas | Código pronto; lançar sem revisão gera risco de responsabilidade por orientação incorreta | Advogado parceiro |
| **Contrato SERPRO (produção)** | A consulta real de restituição IRPF funciona em trial; produção exige contratar a API Consulta Restituição na Loja SERPRO (consumer key/secret + chave do e-CNPJ) | Sem o contrato, o `POST /rights/{user_id}/ir/check` degrada para o passo a passo de habilitação | Contratação SERPRO (custo por consulta) |
| **UI da consulta SVR assistida** | Tela no app exibindo o captcha oficial do BACEN (endpoints prontos no backend) | O "existe dinheiro em seu nome?" em tempo real é o maior hook de conversão do produto | Frontend oficial |
| **Conta de usuário completa** | Reset de senha e verificação de e-mail | Não existem no código; suporte e abuso no dia 1 sem isso | — |
| **App mobile nativo** | Widget de homescreen nativo, push FCM | PWA cobre o essencial, mas retenção diária de massa exige mobile nativo | Time mobile |
| **R4.a Relatório trimestral** | Consolidado automático por email | Reforço de valor percebido a cada 3 meses | Scheduler (pronto) — só falta o job |
| **R5 Anti-churn** | Tela de cancelamento com impacto calculado, modo pausa, win-back | Reduz churn no momento crítico | Billing primeiro |
| **V3 Ranking de bancos abusivos** | Relatório trimestral público anonimizado | Autoridade de marca + imprensa | Massa de dados D1–D3 |
| **F6 Sweep automático** | Mover sobra para investimento automaticamente | "Piloto automático" — valor passivo | Open Finance fase 4 (iniciação de pagamento) |
| **F8 Radar — cauda longa** | ✅ varredura completa do diretório Open Finance implementada (2026-07): todos os participantes com renda fixa publicada entram no catálogo diário. Restante: fontes fora do Open Finance (corretoras não participantes, catálogo ANBIMA) | Cobertura além dos participantes do Open Finance | Fontes adicionais |
| **F9/F10** | Portabilidade de crédito assistida (execução), pagamento otimizado | D6 simula; falta executar | Validação jurídica + APIs |
| **F12 Modo Família** | Até 4 membros | Aumenta ARPU e lock-in | Modelo multi-usuário |
| **Nexa Score exportável** | Score como bureau de crédito alternativo | Vetor de escala fase 3 | Massa crítica de usuários |
| **B2B2C** | Venda como benefício corporativo | CAC próximo de zero em escala | Produto estável + billing |
| **Expansão México** | Adaptar ETL e conectores (Ley Fintech) | Valuation "LatAm" 2–3× | Modelo provado no Brasil |

---

## 🏆 Diferencial Competitivo

| Dimensão | Nexa | Bancos | Apps de Controle | Comparadores |
|:---|:---:|:---:|:---:|:---:|
| **Modelo de receita** | Assinatura do usuário | Tarifas + spread | Freemium / comissão | Comissão de banco |
| **Neutralidade** | ✅ Total | ❌ Conflito | ⚠️ Parcial | ❌ Conflito |
| **Ação automática** | ✅ Contesta, negocia, gera dossiê | ❌ | ❌ Só visualiza | ❌ Só compara |
| **Open Finance nativo** | ✅ Multi-banco | ⚠️ Só o próprio | ⚠️ Manual | ⚠️ Parcial |
| **Base legal integrada** | ✅ CDC, BACEN, STJ | ❌ | ❌ | ❌ |
| **IA conversacional** | ✅ 29 ferramentas | ❌ | ❌ | ❌ |
| **Defesa do consumidor** | ✅ D1–D6 | ❌ | ❌ | ❌ |
| **Perfil comportamental** | ✅ 8 clusters adaptativos | ❌ | ❌ | ❌ |

### Por que não é copiável

> **1. Neutralidade estrutural** — Bancos nunca vão recomendar o concorrente. Apps que ganham comissão não podem ser neutros. A Nexa cobra do usuário — a única estrutura que garante trabalhar exclusivamente para quem paga.

> **2. Flywheel de dados** — Cada novo usuário melhora o benchmark de tarifas (`bank_fee_trends`) e os detectores de abuso. Meses de dados históricos que nenhum concorrente replica retroativamente.

> **3. Complexidade técnica** — 20+ módulos de análise, ETL de 8 estágios, catálogo curado de 81 cartões com 11 programas de fidelidade valorados, Monte Carlo, agente ReAct com 29 ferramentas, 8 clusters comportamentais, 6 detectores de defesa do consumidor e scheduler de inteligência proativa. Não é um wrapper de API.

> **4. Confiança do usuário** — Uma vez que o usuário confia na Nexa como seu advogado, o custo de troca é altíssimo.

> **5. Nexa Score como bureau alternativo** — Com massa crítica, o score baseado em fluxo de caixa real vira selo de qualidade que força bancos a baixarem juros.

---

## 🚀 Estratégias de Crescimento

### 1. B2B2C — Bem-Estar Financeiro Corporativo

O CAC no B2C financeiro é R$ 80–150/usuário. O canal B2B2C muda a economia do negócio: vender a Nexa como benefício corporativo (estilo Gympass para finanças). O RH distribui o app — uma venda = 10.000–50.000 usuários com CAC ~zero.

| Aspecto | Detalhe |
|:---|:---|
| **Proposta para o RH** | Estresse financeiro custa ~R$ 15.000/ano por funcionário em produtividade (PwC) |
| **Pricing** | R$ 5–15/funcionário/mês → empresa de 10.000 = R$ 100k–150k MRR por contrato |
| **Efeito colateral** | Funcionário conecta contas pessoais; ao sair da empresa, migra para plano individual |

### 2. Nexa Score — Bureau de Crédito Alternativo

O Serasa olha o passado (inadimplência); a Nexa olha o presente (fluxo de caixa real). Fase 1: gamificação interna (✅ base pronta — health score + badges). Fase 2: score exportável que o usuário mostra ao pedir crédito. Fase 3: instituições consultam mediante pagamento — receita sem quebrar neutralidade (o usuário decide compartilhar).

### 3. Nexa Wrapped — Viralização Orgânica

✅ **Gerador já implementado** (`/viral/wrapped/{user_id}/{year}/svg`). Todo dezembro (e trimestralmente para Pro/Total): quanto cada banco ganhou com você, top tarifas evitáveis, total economizado pela Nexa, evolução do score. Benchmark Spotify: ~20% de share rate; conversão esperada de 3–5% dos alcançados.

### 4. Expansão LatAm — Playbook Mexicano

México: Open Banking regulado (Ley Fintech 2018), 60M sub-bancarizados, concentração bancária similar (7 bancos = 80%), tarifa média ~MXN 3.000/ano. Provar no Brasil (2026–2027) → adaptar conectores (2028) → tese "LatAm" com multiplicador de valuation 2–3×.

---

## 🏗️ Arquitetura Técnica

```
┌───────────────────────────────────────────────────────────────────┐
│           FRONTEND (protótipo React 19) + PWA Widget/Push         │
└────────────────────────────┬──────────────────────────────────────┘
                             │ HTTPS / JWT (+ refresh rotativo)
┌────────────────────────────▼──────────────────────────────────────┐
│                   FastAPI — app/main.py                           │
│   Rate Limiting (Redis) · CORS estrito · Security Headers · CSP   │
│        Audit Log · Correlation IDs · Health/Readiness             │
└──────┬──────────┬──────────┬───────────┬──────────────────────────┘
       │          │          │           │
┌──────▼───┐ ┌───▼──────┐ ┌─▼─────────┐ ┌▼──────────────────────┐
│   ETL    │ │ Cashflow │ │ Architect │ │  Agent (LangGraph)    │
│ Pipeline │ │  Engine  │ │ MonteCarlo│ │  ReAct + Claude       │
│ 8 stages │ │Safe2Spend│ │  VPL/TIR  │ │  29 Financial Tools   │
└──────┬───┘ └───┬──────┘ └───────────┘ └───────────────────────┘
       │         │
┌──────▼─────────▼───────────────────────────────────────────────┐
│                     MÓDULOS ANALÍTICOS                          │
│ F2 Optimizer · F5 Costs · F7 Purchase · F13 Negotiator · Fiscal │
│ OPP Radar · D1–D6 Defense · T1–T3 Tax/Rights · Seasonality      │
│ MX.1–6 · Goals · Budget · Peers · Viral (Wrapped/Placar)        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                INTELIGÊNCIA COMPORTAMENTAL                       │
│  ConsumptionProfiler (8 clusters) · LifeEventsDetector           │
│  NotificationRelevanceFilter · IncomeProfiler                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│              SCHEDULER (APScheduler + lock Redis)                │
│  02h fees · 02h30 catálogo · 03h opps · 04h score · 6/6h notifs  │
│  07h daily digest → email (SendGrid/SMTP) / in-app / Web Push    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                        DATA LAYER                                │
│     PostgreSQL 16 + SQLAlchemy 2.0 + Alembic · Polars · DuckDB   │
│                    Redis (cache/locks/sessões)                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    INTEGRAÇÕES EXTERNAS                          │
│  Pluggy (Open Finance) · BACEN SGS/SVR · Open Finance Dados      │
│  Abertos · Claude (IA) · OpenAI (fallback) · SendGrid/SMTP       │
└──────────────────────────────────────────────────────────────────┘
```

### Padrões Arquiteturais

| Padrão | Aplicação |
|:---|:---|
| **Feature-driven** | Cada funcionalidade em `/app/{feature}/` isolado com router próprio |
| **Feed + Chat** | Toda feature entrega por card no feed E tool no agente |
| **Pipeline Pattern** | ETL 8 estágios: Ingest → Classify → Detect → Validate → Persist |
| **Strategy Pattern** | Parsing por banco: Nubank, Itaú, Inter, default |
| **ReAct Agent** | LangGraph: pensa → chama ferramenta → observa → repete |
| **Multi-layer Fallback** | ML → Regras → Defaults em classificadores; SELIC dinâmica → fallback fixo |
| **Job Guard** | Lock distribuído Redis (`SET NX EX`) com fallback em memória |
| **Behavioral Clustering** | 8 clusters adaptam todas as recomendações |

### Stack

| Camada | Backend | | Camada | Frontend/DevOps |
|:---|:---|---|:---|:---|
| API | FastAPI + Uvicorn | | Framework | React 19 + TypeScript 5 (protótipo) |
| Database | PostgreSQL 16 + SQLAlchemy 2.0 + Alembic | | Build | Vite |
| Cache/Locks | Redis + SlowAPI | | Styling | TailwindCSS 4 |
| DataFrames | Polars · DuckDB | | State | Zustand + React Query |
| ML | Scikit-learn | | PWA | Manifest + Service Worker + VAPID |
| Open Finance | Pluggy + Dados Abertos | | Container | Docker |
| Taxas | BACEN SGS + ANBIMA | | CI/CD | GitHub Actions (+ pip-audit) |
| IA | LangGraph + Claude (fallback OpenAI) | | Deploy | Railway |
| Scheduler | APScheduler | | Tests | pytest · Vitest · Playwright |

---

## 🔌 Endpoints da API

### Sistema e Autenticação

| Método | Rota | Descrição |
|:---:|:---|:---|
| `GET` | `/health` · `/readiness` · `/version` | Saúde e versão |
| `POST` | `/api/v1/auth/register` · `/auth/token` · `/auth/refresh` · `/auth/logout` | Cadastro, login JWT, refresh rotativo, logout |

<details>
<summary><strong>Ver todos os endpoints por domínio</strong></summary>

### Open Finance

| Método | Rota | Descrição |
|:---:|:---|:---|
| `GET` | `/api/v1/pluggy/institutions` | Lista instituições |
| `POST` | `/api/v1/pluggy/connect` | Conecta conta bancária |
| `GET` | `/api/v1/pluggy/accounts/{user_id}` · `/transactions/{user_id}` | Contas e transações |
| `POST` | `/api/v1/transactions/webhook` | Webhook Pluggy (assinado) |

### Saúde Financeira (F1)

| Método | Rota | Descrição |
|:---:|:---|:---|
| `GET` | `/api/v1/forecast/{user_id}` | Cashflow + safe-to-spend + perfil |
| `GET` | `/api/v1/safe_to_spend/{user_id}` | Margem segura do dia |
| `GET` | `/api/v1/safe-to-spend/{user_id}/widget` | Payload compacto p/ widget PWA (~200 bytes) |
| `GET` | `/api/v1/shadow_invoice/{user_id}` · `/alerts/{user_id}` | Obrigações futuras, alertas |
| `GET` | `/api/v1/dashboard/summary` · `/dashboard/safe-to-spend` | Dashboard consolidado |

### Otimização (F2, F3, F7)

| Método | Rota | Descrição |
|:---:|:---|:---|
| `POST` | `/api/v1/optimizer/recommend` · `/simulate` · `/multi_card` · `/opportunity_cost` | Cartões |
| `POST` | `/api/v1/architect/simulate` | VPL + Monte Carlo |
| `GET` | `/api/v1/architect/simulations[/{id}/sensitivity]` | Histórico e sensibilidade |
| `POST` | `/api/v1/purchase/recommend` | Melhor forma de pagamento |
| `GET` | `/api/v1/purchase/checkout-context` · `/purchase/recent-review` | Veredito no checkout, revisão retroativa |

### Oportunidades (OPP)

| Método | Rota | Descrição |
|:---:|:---|:---|
| `GET` | `/api/v1/opportunities/{user_id}` | Dinheiro parado + recomendações |
| `GET` | `/api/v1/opportunities/{user_id}/banks` | Scorecard por banco (ajuste a risco) |
| `GET` | `/api/v1/opportunities/{user_id}/bank-match` | Melhor banco pelo perfil completo |
| `GET` | `/api/v1/opportunities/products` | Catálogo público transparente |
| `GET` | `/api/v1/opportunities/savings-vs-cdi` · `/treasury-vs-cdb-vs-savings` | Comparadores |
| `POST` | `/api/v1/opportunities/compare` | Simulação de investimento |

### Defesa, Direitos e Impostos (D, T)

| Método | Rota | Descrição |
|:---:|:---|:---|
| `GET` | `/api/v1/defense/{user_id}` | Venda casada + cobranças indevidas + juros abusivos |
| `GET` | `/api/v1/defense/{user_id}/dossier` · `/zip` | Dossiê de evidências (PROCON/JEC) + export |
| `GET` | `/api/v1/defense/{user_id}/portability` | Simulador de portabilidade total |
| `GET` | `/api/v1/rights/{user_id}` | Visão geral: 4 fontes + capacidade de consulta de cada uma |
| `GET` | `/api/v1/rights/{user_id}/svr/captcha` | Desafio oficial do BACEN (consulta assistida SVR) |
| `POST` | `/api/v1/rights/{user_id}/svr/check` | Consulta REAL na consulta pública do SVR/BACEN |
| `POST` | `/api/v1/rights/{user_id}/ir/check` | Consulta REAL da restituição IRPF (e-CAC + SERPRO) |
| `GET` | `/api/v1/tax/optimize/{user_id}` | Otimizador de IR + tax loss harvesting |
| `POST` | `/api/v1/tax/breakeven` | Breakeven CDB vs LCI/LCA |
| `GET` | `/api/v1/seasonality/{user_id}` | Calendário fiscal personalizado |
| `GET` | `/api/v1/costs/{user_id}` | Raio-X de tarifas vs benchmark |

### Engajamento (MX, R, V)

| Método | Rota | Descrição |
|:---:|:---|:---|
| `GET` | `/api/v1/health-score/history/{user_id}` · `/health-score/challenges` | Score, desafios e badges |
| `POST/GET` | `/api/v1/goals/{user_id}` | Metas com projeção |
| `GET` | `/api/v1/notifications/{user_id}` | Feed de cards filtrados por relevância |
| `POST` | `/api/v1/push/*` | Inscrição Web Push (VAPID) |
| `GET` | `/api/v1/peers/compare/{user_id}` · `/budget/{user_id}` | Benchmark e orçamento 50/30/20 |
| `GET` | `/api/v1/viral/savings-card/{user_id}[/svg]` | Placar de economia compartilhável |
| `GET` | `/api/v1/viral/wrapped/{user_id}/{year}[/svg]` | Nexa Wrapped anual |

### IA, Privacidade e Fiscal

| Método | Rota | Descrição |
|:---:|:---|:---|
| `POST` | `/api/v1/chat/` | Chat com agente (29 ferramentas) |
| `GET` | `/api/v1/privacy/export/{user_id}` | Export LGPD (portabilidade) |
| `DELETE` | `/api/v1/privacy/erase/{user_id}` | Eliminação irreversível (LGPD) |
| `GET` | `/api/v1/fiscal/*` | Relatório fiscal MEI/PJ |
| `GET` | `/api/v1/negotiator/*` | Scripts de negociação |

</details>

> 📄 Referência completa em [docs/ENDPOINTS_SUMMARY.md](docs/ENDPOINTS_SUMMARY.md)

---

## 🚀 Início Rápido

### Pré-requisitos

| Requisito | Versão |
|:---|:---|
| Python | 3.12+ |
| PostgreSQL | 16 |
| Redis | 5.0+ (opcional em dev) |
| Node.js | 20+ (frontend) |

### Docker Compose

```bash
git clone https://github.com/nexa-ai/nexa.git && cd nexa
cp backend/.env.example backend/.env   # edite com suas credenciais
docker-compose up --build
```

| Serviço | URL |
|:---|:---|
| API | http://localhost:8000 |
| Frontend | http://localhost:3000 |
| Swagger UI | http://localhost:8000/docs |

### Instalação Manual

<details>
<summary><strong>Backend</strong></summary>

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --port 8000 --reload
```

</details>

<details>
<summary><strong>Frontend (protótipo)</strong></summary>

```bash
cd frontend-react
npm install && npm run dev
```

</details>

### Variáveis de Ambiente Principais

```env
# Obrigatórios
DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/nexa
SECRET_KEY=sua-chave-secreta-forte-aqui

# LLM
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Open Finance
PLUGGY_CLIENT_ID=...
PLUGGY_CLIENT_SECRET=...
PLUGGY_WEBHOOK_SECRET=...        # produção: obrigatório (fail-closed)

# Proatividade (opcional)
SCHEDULER_ENABLED=true
REDIS_URL=redis://localhost:6379/0
SENDGRID_API_KEY=...             # ou SMTP_HOST/SMTP_USER/SMTP_PASSWORD

# Produção
ALLOWED_ORIGINS=https://app.nexa.com.br   # '*' recusado em produção
```

> 📄 Setup completo em [docs/SETUP_LOCAL.md](docs/SETUP_LOCAL.md)

---

## 🗄️ Banco de Dados

PostgreSQL 16 com migrations Alembic. Principais tabelas:

```sql
users                    -- Usuários
transactions_clean       -- Transações processadas (índice: user_id, date)
financial_goals          -- Metas financeiras
architect_simulations    -- Histórico de simulações F3
chat_messages            -- Histórico do agente
pluggy_items             -- Contas Open Finance
health_score_history     -- Série temporal do score
bank_fee_history         -- Histórico de tarifas por usuário (D2/D4)
bank_fee_trends          -- Baseline de mercado anonimizado por banco
opportunity_snapshots    -- Varreduras diárias do Radar OPP
user_badges              -- Badges de desafios (R2.b)
daily_digest_log         -- Idempotência do digest diário
push_subscriptions       -- Inscrições Web Push (PWA)
negotiation_history      -- Histórico do negociador
context_overrides        -- Correções manuais PF/PJ
```

---

## 🧪 Testes

```bash
cd backend
pytest tests/ -v                          # suíte completa
pytest tests/ --cov=app --cov-report=html # com coverage
pytest tests/opportunities/ -v            # por feature
```

**2.189 testes coletados** — suíte mantida 100% verde como política do projeto. Cobertura por área: optimizer, architect, cashflow/ETL, opportunities, notifications (filtro + life events), seasonality, purchase, health_score, peers, fiscal, agent, e2e (seeded e fresh) e **31 testes dedicados de segurança** (`test_security_hardening.py`).

CI via GitHub Actions: testes + `pip-audit` (CVE novo quebra o build).

---

## 📖 Exemplos de Uso

### Chat com o Agente

```bash
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"message": "Como estão minhas finanças? Posso comprar um carro de R$ 60.000?"}'
```

O agente encadeia `get_user_profile_context` → `get_financial_forecast` → `get_financing_simulation` e responde com análise adaptada ao cluster comportamental.

### Radar de Oportunidades

```bash
curl http://localhost:8000/api/v1/opportunities/<user_id> \
  -H "Authorization: Bearer <token>"
```

**Retorna:** dinheiro parado detectado, valor além da reserva de emergência, ranking de produtos por retorno líquido pós-IR e passos práticos de realocação.

### Dossiê de Defesa

```bash
curl http://localhost:8000/api/v1/defense/<user_id>/zip \
  -H "Authorization: Bearer <token>" -o dossie.zip
```

**Retorna:** ZIP com evidências de venda casada, cobranças indevidas e juros abusivos, pronto para PROCON/JEC.

### Simulação de Compra (F3)

```bash
curl -X POST http://localhost:8000/api/v1/architect/simulate \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"asset_type": "vehicle", "target_value": 60000, "down_payment": 12000,
       "months": 48, "monthly_income": 8000, "current_savings": 15000}'
```

**Retorna:** 3 estratégias ranqueadas por VPL com sensibilidade a juros e intervalo Monte Carlo (95%).

---

## 🗺️ Roadmap

### Fase 1 — Fundação ✅ (concluída)

- [x] ETL 8 estágios, Card Optimizer, Architect, PF/PJ, Raio-X, Compra Inteligente
- [x] Score, Metas, Notificações (17 tipos), Budget, Shadow Invoices, Peers
- [x] Agente conversacional + perfil comportamental + life events
- [x] Auth JWT, rate limiting, audit log

### Fase 1.5 — Conversão, Defesa e Retenção ✅ (concluída)

- [x] OPP Radar de Oportunidades completo (OPP.1–5 + Bank Match)
- [x] D1–D6 Defesa do Consumidor (código; D5 aguarda validação jurídica)
- [x] T1–T3 Impostos e Direitos Esquecidos
- [x] Scheduler + daily digest + entrega email/in-app/push
- [x] PWA: widget instalável + Web Push VAPID
- [x] Desafios mensais + badges, calendário fiscal sazonal
- [x] V1 Placar + V2 Wrapped (geradores SVG)
- [x] Hardening de segurança + LGPD (export/erase)

### Fase 2 — Monetização e Casa Própria (próxima)

- [ ] **Billing + gating Free/Pro/Total** (pré-requisito de receita)
- [ ] **Frontend oficial** (substituir protótipo)
- [ ] Validação jurídica e lançamento do D5
- [ ] R4.a relatório trimestral · R5 anti-churn
- [ ] Lançamento público do Wrapped (dezembro)

### Fase 3 — Escala (2027)

- [ ] App mobile nativo (widget homescreen, FCM)
- [ ] F6 sweep automático · F8 radar 200+ instituições · F12 modo família
- [ ] Nexa Score exportável → bureau alternativo
- [ ] B2B2C — primeiros contratos corporativos
- [ ] V3 ranking público de bancos

### Fase 4 — LatAm (2028)

- [ ] Expansão México (Ley Fintech)
- [ ] API de inteligência financeira para terceiros

---

## 📚 Documentação

| Arquivo | Conteúdo |
|:---|:---|
| [ROADMAP.md](docs/ROADMAP.md) | Roadmap de produto auditado contra o código |
| [MUDANÇAS.md](docs/MUDANÇAS.md) | Mapa técnico de cada mudança por camada |
| [SEGURANCA.md](docs/SEGURANCA.md) | Modelo de segurança completo |
| [SETUP_LOCAL.md](docs/SETUP_LOCAL.md) | Setup local detalhado |
| [ENDPOINTS_SUMMARY.md](docs/ENDPOINTS_SUMMARY.md) | Referência completa de endpoints |
| [QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md) | Cheatsheet do dev |
| [BACKEND_REFERENCE.md](docs/BACKEND_REFERENCE.md) | Referência de arquivos do backend |
| [OPP.md](docs/OPP.md) | Spec do Radar de Oportunidades |

---

<div align="center">

### Nexa AI

**20+ módulos implementados · 29 ferramentas de IA · 17 tipos de alerta proativo · 2.189 testes**

*Trabalhar para você, não para o banco.*

---

**Julho 2026 · Confidencial**

</div>
