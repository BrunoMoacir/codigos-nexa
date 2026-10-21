<div align="center">

# HIVE

### **Seu Dinheiro. Seu Lado.**

*O advogado financeiro que os bancos não querem que você tenha.*

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.139-009688?style=flat-square&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![Tests](https://img.shields.io/badge/Testes-3.636%20passando-success?style=flat-square)
![License](https://img.shields.io/badge/Licen%C3%A7a-Propriet%C3%A1ria-red?style=flat-square)

[Como Construímos Valor](#-como-a-hive-constrói-valor) •
[Funcionalidades](#-funcionalidades) •
[App Web](#️-app-web-frontend-react) •
[Início Rápido](#-início-rápido) •
[O Que Falta](#-o-que-está-pronto-vs-o-que-falta) •
[Arquitetura](#️-arquitetura-técnica)

---

</div>

## 📋 Índice

<details>
<summary><strong>Clique para expandir</strong></summary>

- [Visão Geral](#-visão-geral)
- [O Problema](#-o-problema)
- [Como a HIVE Constrói Valor](#-como-a-hive-constrói-valor)
- [As Superfícies do Produto](#-as-superfícies-do-produto)
- [Funcionalidades](#-funcionalidades)
  - [Motor Core de Análise](#motor-core-de-análise)
  - [Contas e Cartões](#contas-e-cartões)
  - [Radar de Oportunidades (OPP)](#radar-de-oportunidades-opp)
  - [Defesa do Consumidor (D)](#defesa-do-consumidor-d)
  - [Direitos Esquecidos e Impostos (T)](#direitos-esquecidos-e-impostos-t)
  - [Engajamento e Retenção (MX/R)](#engajamento-e-retenção-mxr)
  - [Viral (V)](#viral-v)
  - [Inteligência Comportamental](#inteligência-comportamental)
- [App Web (frontend-react)](#️-app-web-frontend-react)
- [Agente de IA](#-agente-de-ia)
- [Notificações e Alertas](#-notificações-e-alertas-mx3)
- [Jobs Automáticos](#-jobs-automáticos-scheduler)
- [Segurança e LGPD](#-segurança-e-lgpd)
- [Planos e Monetização](#-planos-e-monetização)
- [O Que Está Pronto vs O Que Falta](#-o-que-está-pronto-vs-o-que-falta)
- [Posição Competitiva](#-posição-competitiva)
- [Estratégias de Crescimento](#-estratégias-de-crescimento)
- [Arquitetura Técnica](#️-arquitetura-técnica)
- [Endpoints da API](#-endpoints-da-api)
- [Início Rápido](#-início-rápido)
- [Variáveis de Ambiente](#️-variáveis-de-ambiente)
- [Banco de Dados](#️-banco-de-dados)
- [Testes](#-testes)
- [Exemplos de Uso](#-exemplos-de-uso)
- [Como Contribuir](#-como-contribuir)
- [Problemas Conhecidos](#️-problemas-conhecidos)
- [Roadmap](#️-roadmap)
- [Documentação](#-documentação)

</details>

---

## 🎯 Visão Geral

A **HIVE** é uma plataforma de inteligência financeira pessoal que combina **Open Finance**, **Machine Learning** e **IA conversacional** para revelar quanto os bancos lucram com você — e transformar essa informação em ações concretas de economia, recuperação e otimização.

> **Não somos outro banco. Somos o advogado contra todos os bancos.**

A HIVE cobra do usuário, não do banco. Essa é a única estrutura de receita que garante neutralidade total: nenhuma recomendação é comissionada, nenhum produto é empurrado.

O repositório tem três peças:

| Peça | Onde | Estado |
|:---|:---|:---|
| **API** (FastAPI) | [`backend/`](backend/) | Produto completo: 141 operações, 31 ferramentas de IA, 9 jobs agendados |
| **App web oficial** (React 19) | [`frontend-react/`](frontend-react/) | Ligado à API real em todas as telas, com o redesenho visual HIVE da Beatriz Samaha |
| **Demo Streamlit** | [`backend/demo/`](backend/demo/) | O sistema inteiro sobre personas com um ano de extrato, para teste manual |

> **📄 Estado real do projeto:** notas por camada, posição competitiva contra a
> safra 2025–2026, economia unitária, cenários de crescimento, avaliação e plano
> de 90 dias em **[docs/RELATORIO-PROJETO.md](docs/RELATORIO-PROJETO.md)**.
> É o documento a ler antes de decidir qualquer coisa sobre este produto.

> **Sobre o nome.** A marca é **HIVE**, e é ela que o app web mostra. O código,
> os testes, as chaves de cache (`nexa:*`), o nome do banco de dados, o e-mail
> remetente padrão e a documentação de funcionalidades ainda usam a marca
> anterior, **Nexa**. Renomear identificadores é migração de dados e
> infraestrutura, não trabalho de produto.

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

## ✅ Como a HIVE Constrói Valor

O produto opera um **loop de valor contínuo** em cinco etapas. Cada funcionalidade existe para alimentar uma delas:

```
1. CONECTAR   →  Open Finance (Pluggy): todos os bancos do usuário em 30 segundos
2. REVELAR    →  ETL + módulos analíticos mostram onde o dinheiro está vazando
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

## 📱 As Superfícies do Produto

Todo módulo do backend entrega valor por **duas superfícies** — é o padrão arquitetural do produto:

### 1. Feed de Oportunidades
Lista priorizada de cards, ordenada por **impacto financeiro em R$/mês**. Cada card diz: o tipo de oportunidade, o valor em jogo, a urgência e — ao expandir — como foi calculado e os passos práticos para executar. São **17 tipos de card** (ver [Notificações](#-notificações-e-alertas-mx3)), gerados proativamente a cada 6 horas e filtrados por relevância conforme a renda do usuário.

### 2. Chat com Consultor IA
Agente LangGraph ReAct com **31 ferramentas** conectadas aos módulos do backend. O usuário pergunta em linguagem natural ("posso comprar um carro de R$ 60 mil?") e o agente consulta forecast, simulações e perfil comportamental antes de responder — com tom adaptado ao cluster do usuário. Cada conversa tem seu próprio `session_id`: o usuário abre conversas novas sem apagar as antigas e volta a qualquer uma pela lista de conversas.

> Regra de ouro do produto: **feature nova só está completa quando aparece no feed E no chat.**

No app web, essas duas superfícies são as abas **Chat IA** e **Oportunidades**, ao lado da aba **Organização** (cartões, gastos, metas e lançamentos). As demais telas ficam no card **Ferramentas** do Perfil — ver [App Web](#️-app-web-frontend-react).

---

## ⚡ Funcionalidades

### Motor Core de Análise

| ID | Funcionalidade | Valor para o usuário | Status |
|:---|:---|:---|:---:|
| F1 | **ETL Pipeline + Cashflow** — 8 estágios, projeção 30 dias, safe-to-spend | Sabe exatamente quanto pode gastar hoje sem comprometer contas futuras | ✅ |
| F2 | **Card Optimizer** — catálogo curado de 81 cartões (37 emissores, 11 programas de fidelidade valorados), multi-card, custo de oportunidade | Recupera R$ 50–200/mês em cashback/pontos que estava deixando na mesa | ✅ |
| F3 | **HIVE Architect** — financiamento vs consórcio vs investir, VPL + Monte Carlo, calibração por feedback real | Decisões de dezenas de milhares de reais com intervalo de confiança de 95% | ✅ |
| F4 | **PF/PJ Classifier** — Random Forest + regras, decidido pela **direção do dinheiro**; correções manuais do usuário (`/context/override`) | MEI separa gastos pessoais e da empresa automaticamente; base do relatório DAS | ✅ |
| F5 | **Raio-X de Custos** — tarifas detectadas, benchmark de mercado via Open Finance Dados Abertos | Vê cada tarifa cobrada e se está acima da média de mercado | ✅ |
| F7 | **Modo Compra Inteligente** — Pix, débito, crédito ou parcelado? | Veredito instantâneo da melhor forma de pagamento para cada compra | ✅ |
| F13 | **Negociador** — scripts personalizados gerados por IA, com registro do desfecho | Roteiro pronto para ligar no banco e negociar anuidade, juros e tarifas | ✅ |
| M4.1 | **Fiscal PJ** — relatório para MEI/PJ, uso misto PF/PJ | Faturamento, DAS e alertas de limite MEI sem contador | ✅ |

### Contas e Cartões

| Funcionalidade | Valor para o usuário | Status |
|:---|:---|:---:|
| **Conexão Open Finance** — Pluggy Connect (widget), sandbox, sync assíncrono com long-polling/SSE, webhook assinado, reconexão de consentimento | Conecta todos os bancos e acompanha a sincronização em tempo real | ✅ |
| **Origem dos dados** — cada conexão diz se é `demonstracao`, `sandbox` ou `open_finance` | O app nunca chama de "dados reais" o que é demonstração | ✅ |
| **Qualidade da ingestão** — `GET /data-quality/{user_id}` mostra o que foi descartado e por quê | Transparência sobre lançamentos rejeitados pelo ETL | ✅ |
| **Cartões de crédito** — snapshot de bandeira, limite, fatura e vencimento a cada sync das contas CREDIT (`credit_cards`) | Limite e fatura de cada cartão em um lugar | ✅ |
| **Cartão manual** — `POST /pluggy/cards/manual` para bancos que o Open Finance ainda não cobre | Ninguém fica de fora por causa do banco | ✅ |

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

Endpoints: `GET /defense/{user_id}`, `/defense/{user_id}/dossier`, `/defense/{user_id}/zip`, `/defense/{user_id}/portability`. No app web: tela `/defesa`.

### Direitos Esquecidos e Impostos (T)

| ID | Funcionalidade | Valor para o usuário | Status |
|:---|:---|:---|:---:|
| T1 | **Otimizador de IR** — tax loss harvesting, timing de resgate | Paga menos imposto legalmente sobre investimentos | ✅ |
| T2 | **Modo Imposto Zero** — migração CDB→LCI/LCA com breakeven | Sabe exatamente quando um LCI isento ganha do CDB tributado | ✅ |
| T3 | **Monitor de Direitos Esquecidos** — SVR BACEN, FGTS, PIS/PASEP, restituição IR | **Consulta REAL do SVR dentro do app** (API pública oficial do BACEN, usuário responde o captcha oficial) + **restituição IRPF em tempo real** (API SERPRO, autorizada pelo usuário no e-CAC); FGTS/PIS seguem orientativos (sem API para terceiros) — ver nota ↓ | ✅ |
| R2.c | **Sazonalidade Fiscal** — IR, DAS/DASN-SIMEI, IPVA/IPTU, 13º, lucro FGTS, personalizado por perfil MEI/CLT | Nunca mais multa por perder prazo fiscal | ✅ |

> **Nota T3:** consultas reais implementadas em dois níveis, ambas exclusivamente por canais oficiais:
> - **SVR (consulta assistida):** `GET /rights/{user_id}/svr/captcha` + `POST /rights/{user_id}/svr/check` usam a consulta pública oficial do BACEN (a mesma do site) — o usuário responde o desafio de segurança oficial no app e a HIVE informa na hora se existe valor em seu nome. O montante e o resgate seguem no portal com login GOV.BR. CPF/data de nascimento não são persistidos; logs só registram CPF mascarado. A tela `/direitos` do app web já exibe o captcha.
> - **Restituição IRPF (consulta autorizada):** `POST /rights/{user_id}/ir/check` consulta a API oficial Consulta Restituição do SERPRO com o token de Autorização de Compartilhamento que o próprio usuário gera no e-CAC (LGPD art. 7º/11º), decriptando valor, situação e banco (RSA PKCS#1). Requer contrato SERPRO em produção (`SERPRO_CONSUMER_KEY/SECRET`); sem credenciais, o endpoint degrada para o passo a passo de habilitação.
> - **FGTS e PIS/PASEP:** sem API pública para terceiros — permanecem orientativos.
> - O antigo mock de `app/fiscal/rights_monitor/` (valores fabricados por hash do CPF) **foi removido**; nenhum valor é inventado.

### Engajamento e Retenção (MX/R)

| ID | Funcionalidade | Valor para o usuário | Status |
|:---|:---|:---|:---:|
| MX.1 | **Health Score** — score 0–100 com tendência e histórico (fonte única em `health_score.py`) | Um número que resume a saúde financeira, com snapshot diário automático | ✅ |
| MX.2 | **Metas Financeiras** — CRUD, projeção de prazo, progresso | "Nesse ritmo, sua reserva fica pronta em 7 meses" | ✅ |
| MX.3 | **Notificações Proativas** — 17 tipos, filtro de relevância por renda | Só recebe alerta do que importa para o seu bolso (ver seção dedicada) | ✅ |
| MX.4 | **Peer Comparison** — benchmarks IBGE/POF por faixa de renda | "Você gasta 40% mais em delivery que pares da sua renda" | ✅ |
| MX.5 | **Budget Advisor** — plano 50/30/20 adaptado ao perfil comportamental | Orçamento realista, não genérico | ✅ |
| MX.6 | **Shadow Invoices** — parcelas e assinaturas futuras | Vê o caixa já comprometido antes de assumir nova dívida | ✅ |
| R1.a | **Compra no momento** — `GET /purchase/checkout-context/{user_id}` (veredito compacto) + revisão retroativa de compras grandes (card PURCHASE_FOLLOWUP + tool no chat) | Decisão certa na hora do checkout; aprende com compras passadas | ✅ |
| R1.b | **Entrega proativa** — NotificationEngine a cada 6h com entrega email/in-app/push e dedup por TTL | O valor chega ao usuário sem ele abrir o app | ✅ |
| R1.c | **Daily Digest** — email 07h00 com score, tarifas, oportunidades, prazos fiscais e desafios | Resumo diário idempotente; razão para voltar todo dia | ✅ |
| R1.d | **Widget Safe-to-Spend (PWA)** — página `/widget` instalável + Web Push VAPID; usa o mesmo diário do forecast e avisa quando o extrato está parado | Margem do dia na homescreen, payload de ~200 bytes | ✅ |
| R2.b | **Desafios mensais e badges** — SEM_TARIFAS, REDUZIR_CATEGORIA, GUARDAR_VALOR, SUBIR_SCORE + badges de streak | Gamificação com impacto real no bolso | ✅ |
| R3 | **Histórico acumulado** (DuckDB) + metas com projeção | Quanto mais tempo usa, mais insight — custo de troca cresce | ✅ |
| R4.b | **PromotionTracker** — promoções de transferência de pontos: staleness guard (curadoria >45d não alerta), matching por programa de fidelidade, card TRANSFER_PROMO no engine 6/6h e tool no chat | Bônus de 80–110% em milhas não passa despercebido — com estimativa do valor extra em R$ | ✅ |

### Viral (V)

| ID | Funcionalidade | Valor / mecânica | Status |
|:---|:---|:---|:---:|
| V1 | **Placar de Economia Compartilhável** — card SVG/PNG com o total economizado | "Economizei R$ 4.200 contra os bancos com a @hive" → CAC zero | ✅ |
| V2 | **HIVE Wrapped anual** — relatório "Seu Banco vs Você" com SVG compartilhável | Quanto cada banco lucrou com você no ano; viralização estilo Spotify Wrapped | ✅ |
| V3 | **Ranking público de bancos abusivos** — relatório trimestral anonimizado | Autoridade de marca + imprensa | 📅 |

Endpoints: `GET /viral/savings-card/{user_id}[/svg|/png]`, `GET /viral/wrapped/{user_id}/{year}[/svg]`, `POST /viral/shares` e `DELETE /viral/shares/{share_id}` (registro e revogação de compartilhamento, com recibo de consentimento).

### Inteligência Comportamental

*A camada que personaliza tudo: mesmos dados, recomendações diferentes por pessoa.*

| Módulo | O que faz | Onde atua |
|:---|:---|:---|
| **ConsumptionProfiler** | Classifica o usuário em 1 de 8 clusters de estilo de vida (90 dias de transações) — **modelo ML híbrido**: RandomForest destilado das regras (fidelidade 95,9% em holdout, artefato de 6 MB) decide o cluster primário com confiança calibrada; afinidades das regras dão os secundários; fallback integral nas regras; invariante determinístico para FSS crítico | Agente, optimizer, budget, notificações — 6+ módulos |
| **LifeEventsDetector** | Detecta bebê, mudança, casamento, faculdade, aumento/queda de renda via padrão de gastos | Cards LIFE_EVENT com ação sugerida |
| **NotificationRelevanceFilter** | Elimina ruído com thresholds escalados por renda | Mesmo evento é ruído para quem ganha R$ 15k e crítico para quem ganha R$ 2k |
| **IncomeProfiler** | Renda real após filtrar transferências e não-recorrentes | Base de todos os thresholds |

Os 8 clusters: `EXPLORADOR_GLOBAL` (milhas/lounge), `URBANO_FOODIE` (cashback alimentação), `INVESTIDOR_CAUTELOSO` (precisão numérica), `FAMILIA_ESTRUTURADA` (segurança/educação), `DIGITAL_NATIVO` (PIX/fintechs), `ESTRESSE_FINANCEIRO` (empatia, cortes, zero sugestão de gasto), `MICROEMPREENDEDOR` (PF vs PJ, DAS), `NAO_CLASSIFICADO` (neutro).

---

## 🖥️ App Web (frontend-react)

O **frontend oficial** da HIVE: React 19 + TypeScript + Vite, com o redesenho visual **HIVE** da Beatriz Samaha (preto quente, ouro, Satoshi, hexágonos). Todas as telas leem a API real — não há dados fabricados no caminho padrão. Detalhes de desenvolvimento em [frontend-react/README.md](frontend-react/README.md).

> **Status (out/2026):** o `frontend-react/` deixou de ser protótipo e passou a
> ser o app oficial, com o design como está. Ganhou lint zerado, testes de
> ponta a ponta (Playwright), job próprio no CI, carregamento de fonte que não
> trava a tela e correções de dados (Organização com 12 meses reais, login que
> volta para a tela de origem). O visual é a referência do produto: mudanças
> visuais são combinadas com a Beatriz.

### Navegação

- **Três abas:** **Chat IA** (`/chat`), **Oportunidades** (`/feed`) e **Organização** (`/organizar`).
- **Avatar → Perfil** (`/profile`), que tem o card **Ferramentas** com as demais telas.
- Depois do login o app abre no **Chat**. O antigo Dashboard foi descontinuado: `/dashboard` redireciona para `/organizar`.

### Telas e o que cada uma consome

| Rota | Tela | Acesso | Endpoints principais |
|:---|:---|:---:|:---|
| `/login` | Login | público | `POST /auth/token` |
| `/register` | Cadastro em 3 passos (CPF e telefone opcionais, aceite dos termos) | público | `GET /auth/check-email`, `POST /auth/register` |
| `/forgot-password` · `/reset-password` · `/verify-email` | Recuperação de senha e verificação de e-mail | público | `POST /auth/forgot-password`, `/reset-password`, `/verify-email`, `/resend-verification` |
| `/contact` | Contato (abre o WhatsApp com a mensagem pronta) | público | — |
| `/chat` | Chat IA com lista de conversas e "Nova conversa" | logado | `GET /chat/sessions`, `GET /chat/history`, `POST /chat/` |
| `/feed` | Oportunidades: alertas por gravidade e oportunidades | logado | `GET /alerts/{user_id}` |
| `/organizar` | Organização: cartões, gasto mês a mês (12 meses) e por semana, categorias do período, metas, movimentações | logado | `GET /transactions/{user_id}` (paginado), `/pluggy/cards`, `/goals/{user_id}` |
| `/organizar/cartao/novo` | Cadastro manual de cartão | logado | `POST /pluggy/cards/manual` |
| `/profile` | Perfil, preferências, privacidade (LGPD), modo demo, Ferramentas | logado | `/settings/{user_id}`, `/billing/subscription/{user_id}`, `/pluggy/connections`, `/privacy/*`, `/auth/logout-all` |
| `/strategies` | Estratégias: cartões, grandes compras, MEI, pares, negociador | logado | `/optimizer/*`, `/architect/*`, `/purchase/*`, `/fiscal-report/*`, `/peers/*`, `/negotiator/*`, `/costs/raio-x/*`, `/context/override` |
| `/goals` | Metas, desafios e badges | logado | `/goals/*`, `/health-score/challenges/*`, `/health-score/badges/*`, `/budget/*`, `/seasonality/*` |
| `/connections` | Conexões Open Finance e sincronização | logado | `/pluggy/connections`, `/pluggy/connect-token`, `/pluggy/items`, `/pluggy/sandbox`, `/pluggy/sync/jobs`, `/data-quality/*` |
| `/defesa` | Defesa do consumidor | logado | `/defense/{user_id}` (+ `/dossier`, `/zip`, `/portability`) |
| `/direitos` | Direitos esquecidos: consulta SVR assistida e restituição IR | logado | `/rights/{user_id}` (+ `/svr/captcha`, `/svr/check`, `/ir/check`) |
| `/impostos` | Impostos: IR dos investimentos e breakeven CDB × LCI/LCA | logado | `/tax/optimize/{user_id}`, `POST /tax/breakeven` |
| `/wrapped` | Seu ano na HIVE + placar de economia | logado | `/viral/wrapped/*`, `/viral/savings-card/*`, `POST /viral/shares` |
| `/planos` | Planos e uso dos limites | logado | `/billing/plans`, `/billing/subscription/*`, `/billing/checkout/*`, `/billing/portal/*` |
| `/widget` | Widget safe-to-spend (PWA) | logado | `/safe-to-spend/{user_id}/widget` |
| `/home` | Painel anterior (sem link na navegação atual) | logado | `/transactions/{user_id}/summary`, `/pluggy/connections`, `/health-score/history/*` |

### Como o app fala com a API

- **Base URL:** `VITE_API_URL` quando definida; senão `/api/v1` relativo. No `npm run dev`, o Vite faz proxy de `/api` para `VITE_DEV_BACKEND` (padrão `http://localhost:8000`); em produção o `nginx.conf.template` faz o mesmo papel.
- **Sessão:** access token de 30 min + refresh de 14 dias com rotação. O cliente HTTP ([`src/api/client.ts`](frontend-react/src/api/client.ts)) renova uma única vez quando várias requisições tomam 401 ao mesmo tempo; se o refresh falhar, volta para `/login?next=<tela>` e, depois do login, para a tela de origem (só caminhos internos).
- **Timeouts por tipo de chamada:** padrão 30 s, chamadas lentas (simulações, consulta SVR) 75 s e chat 95 s — o agente pode levar mais que o padrão.
- **Erros por tipo:** [`src/api/errors.ts`](frontend-react/src/api/errors.ts) traduz 401/402/403/404/429/5xx e timeout em mensagens em português.
- **Formatação:** valores em `pt-BR` (R$ com vírgula decimal).
- **Fonte:** a Satoshi vem do Fontshare e carrega sem bloquear a renderização; se o CDN cair, o app abre com a fonte do sistema.

### Modo demonstração (por conta)

Contas sem banco conectado mostram o estado real: vazio, com convite para conectar. O **modo demo** é um interruptor no Perfil, gravado por conta no navegador (`hive-demo-mode:<user_id>`), que preenche Oportunidades e Organização com **dados de exemplo do próprio frontend** só para mostrar como as telas ficam. Nunca vem ligado numa conta nova.

> Não confundir com as **personas de demonstração** do backend
> (`ana`, `bruno`, `carla`): essas têm extrato completo gravado no banco e
> passam pelo ETL real — ver [Início Rápido](#-início-rápido).

---

## 🤖 Agente de IA

Agente **ReAct (LangGraph)**: o LLM decide qual ferramenta chamar, observa o resultado e responde em linguagem natural. A primeira ferramenta de toda sessão é `get_user_profile_context`, que carrega o cluster comportamental e adapta o tom da conversa inteira. O `user_id` autenticado é injetado como contexto imutável — o agente ignora qualquer user_id vindo da mensagem (mitigação de prompt injection), e o thread de memória é vinculado ao dono.

### 31 Ferramentas Financeiras

| Domínio | Ferramentas |
|:---|:---|
| **Perfil e saúde** | `get_user_profile_context` · `get_financial_forecast` · `get_spending_alerts` · `get_goals_summary` |
| **Orçamento e pares** | `get_budget_advice` · `get_peer_comparison` |
| **Cartões e pontos** | `get_card_optimization` · `get_expert_card_analysis` · `get_transfer_promotions` |
| **Compras** | `get_purchase_recommendation` · `review_recent_purchases` |
| **Simulações (F3)** | `get_financing_simulation` · `get_timing_scenarios` · `get_leverage_simulation` |
| **Oportunidades (OPP)** | `get_opportunities` · `simulate_investment` · `get_best_bank` |
| **Defesa (D)** | `detect_abusive_fees` · `detect_wrongful_charges` · `detect_abusive_interest` · `get_defense_analysis` · `get_evidence_dossier` · `get_portability_analysis` |
| **Custos e negociação** | `get_bank_cost_analysis` · `get_negotiation_script` |
| **Fiscal e direitos** | `get_fiscal_report` · `get_fiscal_calendar` · `get_forgotten_rights` |
| **Engajamento** | `get_monthly_challenges` · `get_annual_wrapped` |
| **Conta** | `get_plan_info` |

### Como o chat funciona

| Aspecto | Comportamento |
|:---|:---|
| **LLM** | `LLM_PROVIDER=anthropic` usa Claude via `langchain-anthropic` (se `LLM_MODEL` ainda estiver num modelo `gpt-*`, cai no `claude-haiku-4-5`); `LLM_PROVIDER=openai` usa `gpt-4o-mini` por padrão. **O padrão do código é `openai`** — defina o provedor no `.env`. Sem chave, o chat responde 503 com mensagem clara, nunca uma resposta fabricada |
| **Conversas** | `POST /chat/` recebe `user_id`, `message` e `session_id`; `GET /chat/sessions` lista as conversas (título = primeira pergunta, mais recente primeiro); `GET /chat/history?session_id=` traz uma conversa |
| **Histórico** | Mensagens gravadas em `chat_messages` (Postgres), ordenadas por id; a resposta traz `tools_used` com as ferramentas chamadas |
| **Memória do agente** | Checkpointer em cadeia: Redis Stack (RediSearch ≥ 2.6) → Postgres → memória do processo (último recurso, logado como erro em produção) |
| **Limites** | Free: 5 mensagens/dia, consumidas **só depois** de uma resposta bem-sucedida; 20 requisições/min por IP no endpoint |

---

## 🔔 Notificações e Alertas (MX.3)

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
        CRITICAL nunca é descartado por relevância
```

Cards WARNING/CRITICAL sobem automaticamente para **Web Push** quando o usuário tem inscrição PWA ativa. Dedup por TTL específico por tipo (ex.: SAVINGS_BELOW_CDI no máximo 1×/mês).

**Contrato com o app:** `GET /notifications/{user_id}` é idempotente — ler não marca nada como visto. Interações (visto, clicado, dispensado) vão por `POST /notifications/{user_id}/events`.

### Alertas do fluxo de caixa

`GET /alerts/{user_id}` (alimenta a aba Oportunidades) devolve alertas do forecast — saldo negativo projetado, consentimento Open Finance perto de vencer — com a gravidade em **`level`** (`CRITICAL` · `WARNING` · `INFO`). O campo `type` é o tipo do alerta (ex.: `NEGATIVE_BALANCE`), não a gravidade. `DELETE /alerts/{user_id}/{alert_id}` dispensa um alerta.

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

APScheduler com lock distribuído Redis (`SET NX EX`) — seguro em multi-instância. **Desligado por padrão**; ative com `SCHEDULER_ENABLED=true`. Registro em [`app/core/scheduler.py`](backend/app/core/scheduler.py).

| Horário | Job | O que entrega |
|:---:|:---|:---|
| 02h00 | `fee_snapshot` | Histórico de tarifas por usuário + agregado anônimo `bank_fee_trends` (alimenta D2/D4) |
| 02h15 | `market_fees_refresh` | Baseline VIVO de tarifas de mercado via Open Finance Dados Abertos (preço típico ponderado por faixa de clientes) — F5/D4 desde o dia 1 |
| 02h30 | `product_catalog_refresh` | Atualiza catálogo de produtos via Open Finance Dados Abertos (OPP) |
| 03h00 | `opportunity_scan` | Varredura de dinheiro parado e poupança sub-CDI por usuário |
| seg 03h30 | `cards_curation_audit` | Auditoria semanal da curadoria do catálogo de cartões |
| 04h00 | `health_score_snapshot` | Série temporal do score (tendência 30/90 dias) |
| a cada 6h | `notification_scheduler` | Gera e entrega notificações proativas (email/in-app/push) |
| 05h30 | `intelligence_metrics` | Monitoramento de acurácia (aceitação de recomendações, sucesso do negociador, cobertura) + calibração do Negociador por desfechos reais |
| 07h00 | `daily_digest` | Email diário com score, tarifas, oportunidades, prazos fiscais e desafios |

> ⚠️ **Escritos e nunca agendados:** `app/jobs/quarterly_report.py` (R4.a),
> `app/jobs/win_back.py` (R5) e `app/jobs/promotion_alerts.py` existem e têm
> testes, mas não estão registrados no scheduler. As promoções de pontos chegam
> ao usuário pelo card `TRANSFER_PROMO` do `notification_scheduler`.

---

## 🔐 Segurança e LGPD

*Confiança é o produto: quem entrega extrato bancário completo precisa de mais que promessa.* Modelo completo em [docs/SEGURANCA.md](docs/SEGURANCA.md).

| Camada | Implementação |
|:---|:---|
| **Autenticação** | JWT HS256 de 30 min + refresh token de 14 dias com **rotação de uso único** (reuso → 401); blacklist Redis por `jti`; `POST /auth/logout` revoga a sessão inteira (access + refresh) e `POST /auth/logout-all` derruba todos os aparelhos; anti-enumeração no login |
| **Cadastro** | E-mail sem diferença de maiúsculas, senha ≥ 8 caracteres, telefone validado; **aceite dos termos obrigatório**, com o instante gravado (`users.terms_accepted_at`) |
| **Conta** | Reset de senha e verificação de e-mail com tokens de uso único (só o SHA-256 vai ao banco); respostas 202 uniformes (anti-enumeração); emitir link novo invalida o anterior; auditoria de cada evento |
| **Autorização** | `require_owner` em todos os endpoints de dados (IDOR bloqueado); recursos aninhados verificam o dono do objeto; um teste varre **todas** as rotas e falha se alguma rota privada não exigir autenticação |
| **Webhooks** | Pluggy: segredo compartilhado comparado em tempo constante, produção sem segredo → 503 fail-closed, identidade resolvida server-side. Stripe: assinatura + anti-replay |
| **Headers** | CSP estrito, HSTS (produção), X-Frame-Options DENY, COOP, Permissions-Policy |
| **Configuração** | Em `APP_ENV=production` o boot é recusado com `SECRET_KEY` de desenvolvimento ou `ALLOWED_ORIGINS='*'` (sem `FRONTEND_BASE_URL` válido) |
| **Rate limiting** | 60/min global por IP (Redis). Login 10/min · cadastro 5/min · refresh 20/min · check-email 20/min · esqueci/redefinir senha 5/min · verificar e-mail 10/min · reenviar verificação 3/min · chat 20/min · forecast 10/min · consultas SVR/IR 10/min |
| **LGPD** | `GET /privacy/export/{user_id}` (portabilidade, art. 18 V) e `DELETE /privacy/erase/{user_id}` (eliminação irreversível, art. 18 VI, exige frase de confirmação e limpa também os threads do agente); auditoria com e-mail mascarado |
| **Supply chain** | `pip-audit` no CI — qualquer CVE novo quebra o build (ver [Problemas Conhecidos](#️-problemas-conhecidos)) |
| **Prompt injection** | `user_id` imutável injetado pelo sistema; agente instruído a ignorar user_id na mensagem |

> **Rota pública que revela cadastro:** `GET /auth/check-email` (passo 1 do
> cadastro) responde se um e-mail já tem conta. É uma troca consciente de UX —
> o `POST /auth/register` já revelava isso ao recusar e-mail repetido — e fica
> limitada a 20 consultas/min por IP.

---

## 💼 Planos e Monetização

> **A HIVE cobra do usuário, não do banco.** Isso garante neutralidade total — e é o que justifica pagar: um consultor comissionado nunca mandaria você sair do banco que o comissiona.

| Plano | Preço | O que entrega | Valor que justifica o preço |
|:---|:---:|:---|:---|
| **Free** | R$ 0/mês | 1 banco conectado, dashboard básico, safe-to-spend, 3 consultas Compra Inteligente/mês, 5 msgs de IA/dia, consulta SVR assistida | Porta de entrada: o usuário **vê** quanto está perdendo (indignação → conversão) |
| **Pro** | R$ 19,90/mês | Bancos ilimitados, Raio-X completo, Radar de Oportunidades, chat ilimitado, Negociador (1/mês), digest diário, desafios e badges | Se o usuário recupera **R$ 50+/mês** (média esperada: tarifas + cashback + dinheiro parado), o plano se paga 2,5× |
| **Total** | R$ 39,90/mês | Tudo do Pro + Defesa do Consumidor completa (dossiê PROCON/JEC), portabilidade simulada, otimizador de IR, Wrapped trimestral, Negociador ilimitado | Uma única contestação de tarifa recuperada (R$ 200–800) paga o ano inteiro |

**Status de implementação:** billing e gating **implementados** em `app/billing/` — Stripe Checkout/Portal/webhook assinado (fail-closed em produção), tabela `user_subscriptions` (Alembic), hierarquia Free/Pro/Total e limites de uso com contadores Redis + fallback em memória. Gates aplicados: Defesa e Otimizador de IR exigem **Total**; Radar de Oportunidades e Raio-X exigem **Pro**. **Dark launch:** `BILLING_ENFORCEMENT_ENABLED=false` por padrão — violações são apenas logadas (`would_block`); ligar a flag em produção ativa os 402 com contexto de upgrade. Falta: criar Products/Prices no dashboard Stripe e preencher `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_PRO_MONTHLY` e `STRIPE_PRICE_TOTAL_MONTHLY`.

### Unit Economics — alvo vs. chão real

| Métrica | Target |
|:---|:---:|
| ARPU | R$ 25/mês |
| CAC | R$ 40–80 |
| LTV (12 meses) | R$ 300 |
| LTV:CAC | > 4:1 |
| Margem bruta | 75%+ |
| Payback | < 3 meses |

**O que os targets acima não mostram:** acessar o Open Finance sem ser
instituição autorizada exige um agregador, e o plano de dados da Pluggy parte de
**R$ 2.500/mês**. Com infra e e-mail, o custo mensal **antes do primeiro
usuário** é de ~R$ 3.000.

| Plano | Preço | Contribuição líquida | Ponto de equilíbrio |
|:---|---:|---:|---:|
| Pro | R$ 19,90 | R$ 17,22 | 174 assinantes |
| Total | R$ 39,90 | R$ 35,92 | 84 assinantes |
| Mistura 80/20 | — | R$ 20,96 | **143 assinantes** |

> **143 assinantes pagam a empresa inteira.** É meta de beta fechado, não de
> campanha de marketing.

> ⚠️ **A armadilha do Free.** O plano gratuito permite 1 banco conectado, e cada
> conexão viva é um item cobrado pela Pluggy acima do mínimo — **usuário
> gratuito tem custo marginal recorrente e receita zero**. Com 10 mil gratuitos
> conectados, o agregador vira a maior linha da empresa. Resolve-se no desenho
> do plano, não no orçamento.

> 💰 **Preço está defasado.** O Pierre cobra R$ 39/mês no plano intermediário e
> R$ 199/mês no superior, por um produto que faz menos. Recomendação (com plano
> anual, que hoje não existe): **Pro R$ 29,90 · Total R$ 59,90 · anual R$ 249 /
> R$ 499**. Racional completo em
> [RELATORIO-PROJETO.md § 5](docs/RELATORIO-PROJETO.md#5-modelo-de-negócio-e-economia-unitária).

---

## 📊 O Que Está Pronto vs O Que Falta

### ✅ Pronto

| Área | Entregas |
|:---|:---|
| **Motor core** | F1 ETL + cashflow, F2 optimizer (81 cartões curados de 37 emissores), F3 Architect (Monte Carlo), F4 PF/PJ, F5 custos, F7 compra inteligente, F13 negociador, fiscal MEI/PJ |
| **Contas e cartões** | Pluggy Connect + sync assíncrono (long-polling/SSE) + webhook, origem dos dados por conexão, qualidade da ingestão, cartões de crédito sincronizados e cadastro manual |
| **Oportunidades** | OPP.1–OPP.5 completos + Bank Match + catálogo público + refresh diário |
| **Defesa** | D1–D6 codificados: venda casada, cobranças indevidas, juros abusivos, mudança unilateral, dossiê + ZIP, portabilidade |
| **Direitos e impostos** | T1 otimizador IR, T2 imposto zero, T3 direitos esquecidos (consulta REAL do SVR assistida + restituição IRPF via SERPRO autorizada; FGTS/PIS orientativos), calendário fiscal sazonal |
| **Engajamento** | Health score + desafios + badges, metas, 17 tipos de notificação com filtro de relevância, peer comparison, budget 50/30/20, shadow invoices |
| **Retenção** | Scheduler com 9 jobs, daily digest, entrega email/in-app/push, PWA com widget instalável e Web Push VAPID, checkout-context, revisão de compras |
| **Viral** | Placar de economia (SVG/PNG) e Wrapped anual (SVG), com registro e revogação de compartilhamento |
| **IA** | Agente ReAct com 31 ferramentas, conversas por sessão, memória com fallback Redis → Postgres, perfil comportamental (8 clusters), life events |
| **App web oficial** | `frontend-react` com o redesenho HIVE, lint zerado, 29 testes unitários, 13 testes e2e e job no CI; todas as telas ligadas à API real (cadastro com aceite dos termos, chat por conversas, feed, organização, cartões, perfil com LGPD, conexões, estratégias, metas, defesa, direitos, impostos, wrapped, planos, widget), recuperação de senha e verificação de e-mail, renovação de sessão automática |
| **Plataforma** | Auth JWT + refresh rotativo, IDOR hardening, LGPD export/erase, rate limiting, audit log, 3.636 testes de backend passando (79% de cobertura), testes de contrato front↔back |

### 🚧 Falta (em ordem de prioridade de negócio)

| Item | O que é | Por que importa | Dependência |
|:---|:---|:---|:---|
| **CI verde de novo** | O `requirements.txt` não resolve num ambiente limpo e o CI falha na instalação desde agosto (ver [Problemas Conhecidos](#️-problemas-conhecidos)) | Sem CI, nenhum push é verificado e o `pip-audit` não roda | Rodada de dependências (langchain 0.2 × numpy 2) |
| **Chaves Stripe + flip do enforcement** | Billing/gating implementados em dark launch; falta criar os Prices no Stripe, preencher o `.env` e ligar `BILLING_ENFORCEMENT_ENABLED` | Último passo entre o código e a receita | Conta Stripe |
| **Decisões de produto no app** | Botão "Continuar com Google" sem backend, CPF pedido e não enviado, passo 2 do cadastro dizendo que o Open Banking está "em construção", Feed sem os cards do motor de notificações — ver [frontend-react/README.md](frontend-react/README.md#pendências-conhecidas) | Promessa visível que o produto não cumpre | Design (Beatriz) |
| **Validação jurídica (D5)** | Revisão por advogado dos templates de petição JEC e cartas | Código pronto; lançar sem revisão gera risco de responsabilidade por orientação incorreta | Advogado parceiro |
| **Contrato SERPRO (produção)** | A consulta real de restituição IRPF funciona em trial; produção exige contratar a API Consulta Restituição na Loja SERPRO (consumer key/secret + chave do e-CNPJ) | Sem o contrato, o `POST /rights/{user_id}/ir/check` degrada para o passo a passo de habilitação | Contratação SERPRO (custo por consulta) |
| **App mobile nativo** | Widget de homescreen nativo, push FCM | PWA cobre o essencial, mas retenção diária de massa exige mobile nativo | Time mobile |
| **R4.a Relatório trimestral** | ⚠️ **O job existe e nunca roda** — `app/jobs/quarterly_report.py` está escrito e testado, mas não está registrado em `app/core/scheduler.py` | Reforço de valor percebido a cada 3 meses | Duas linhas de `add_job` — mas só faz sentido com usuários e cobrança |
| **R5 Anti-churn** | ⚠️ **Mesma situação** — `app/jobs/win_back.py` escrito, testado e nunca agendado. Falta ainda a tela de cancelamento com impacto calculado e o modo pausa | Reduz churn no momento crítico | Billing primeiro |
| **V3 Ranking de bancos abusivos** | Relatório trimestral público anonimizado | Autoridade de marca + imprensa | Massa de dados D1–D3 |
| **F6 Sweep automático** | Mover sobra para investimento automaticamente | "Piloto automático" — valor passivo | Open Finance fase 4 (iniciação de pagamento) |
| **F8 Radar — cauda longa** | ✅ varredura completa do diretório Open Finance implementada (2026-07). Restante: fontes fora do Open Finance (corretoras não participantes, catálogo ANBIMA) | Cobertura além dos participantes do Open Finance | Fontes adicionais |
| **F9/F10** | Portabilidade de crédito assistida (execução), pagamento otimizado | D6 simula; falta executar | Validação jurídica + APIs |
| **F12 Modo Família** | Até 4 membros | Aumenta ARPU e lock-in | Modelo multi-usuário |
| **HIVE Score exportável** | Score como bureau de crédito alternativo | Vetor de escala fase 3 | Massa crítica de usuários |
| **B2B2C** | Venda como benefício corporativo | CAC próximo de zero em escala | Produto estável + billing |
| **Expansão México** | Adaptar ETL e conectores (Ley Fintech) | Valuation "LatAm" 2–3× | Modelo provado no Brasil |

---

## 🏆 Posição Competitiva

> Revisado em **agosto/2026** contra a safra recente de produtos. Análise
> completa em **[RELATORIO-PROJETO.md](docs/RELATORIO-PROJETO.md)**.

### A safra 2025–2026

Entre 2025 e 2026 surgiu no Brasil uma geração de produtos de finanças pessoais
nativos de IA sobre Open Finance. O mais relevante é o **Pierre**, da CloudWalk
(InfinitePay) — lançado em julho/2025, adquirido um mês depois, hoje com **165
mil usuários**, 1,2 milhão de mensagens e 70+ milhões de transações
processadas. Planos: Free · **R$ 39/mês** · **R$ 199/mês**.

Ao lado dele: **Muuney** (dashboard + alertas no WhatsApp), **Jota**
(assistente no WhatsApp com Pix e suporte a PJ) e **Magie** (banking
conversacional). Fora do Brasil, a mesma safra: Copilot Money (US$ 95/ano),
Monarch (US$ 99,99/ano), Cleo, Rocket Money.

> ### ⚠️ A correção que isso impõe
>
> Versões anteriores deste README tratavam o **consultor conversacional** como
> diferencial. **Não é mais.** O Pierre faz exatamente isso, é brasileiro, roda
> sobre Open Finance e está financiado por uma das fintechs mais capitalizadas
> do país. Uma disputa por distribuição contra a CloudWalk não é uma disputa
> que a HIVE ganha.
>
> A camada de conversa virou **requisito de entrada**. O diferencial é a
> **defesa do consumidor bancário**, que nenhum deles faz.

### A comparação real

| Capacidade | HIVE | Pierre | Muuney · Jota | Mobills · Organizze | App do banco | Advogado |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| Categoriza gastos | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| Open Finance multi-banco | ✅ | ✅ | ✅ | ✅ | ⚠️ só o próprio | — |
| Consultor conversacional | ✅ 31 tools | ✅ multiagente | ✅ WhatsApp | ❌ | ⚠️ chatbot | humano |
| Projeta fluxo de caixa | ✅ | ✅ | ⚠️ | ⚠️ básico | ❌ | ❌ |
| Sinaliza gasto fora do padrão | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| **Detecta tarifa indevida** | ✅ | ❌ | ❌ | ❌ | ❌ | manual |
| **Confere juros contra o BACEN** | ✅ | ❌ | ❌ | ❌ | ❌ | manual |
| **Base legal (CDC, BACEN, STJ)** | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Dossiê para PROCON / JEC** | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Roteiro de negociação** | ✅ | ❌ | ❌ | ❌ | ❌ | substitui |
| **Dinheiro esquecido (SVR)** | ✅ | ❌ | ❌ | ❌ | ❌ | cobra por isso |
| Simulação sem viés (Monte Carlo) | ✅ | ❌ | ❌ | ❌ | ⚠️ viesado | ❌ |
| Otimiza IR e calendário fiscal | ✅ | ❌ | ❌ | ❌ | ❌ | contador |
| Separa PF/PJ para MEI | ✅ | ❌ | ⚠️ Jota | ❌ | ❌ | contador |
| **Usuários reais** | **0** | 165 mil | — | milhões | dezenas de milhões | o mercado |
| **Marca e capital** | **0** | CloudWalk | independente | alta | alta | OAB |

As linhas **em negrito** são as únicas onde a HIVE está sozinha. Elas são a
empresa. O resto é paridade competitiva contra quem tem marca, capital e
usuários.

### O que sustenta a diferença

> **1. Neutralidade estrutural** — Bancos nunca vão recomendar o concorrente. Apps que ganham comissão não podem ser neutros. A HIVE cobra do usuário — a única estrutura que garante trabalhar exclusivamente para quem paga.

> **2. Flywheel de dados** — Cada novo usuário melhora o benchmark de tarifas (`bank_fee_trends`) e os detectores de abuso. Meses de dados históricos que nenhum concorrente replica retroativamente.

> **3. Profundidade, não wrapper** — ETL de 8 estágios, catálogo curado de 81 cartões de 37 emissores, Monte Carlo calibrado, agente ReAct com 31 ferramentas, 8 clusters comportamentais, 6 detectores de defesa e scheduler proativo. Reconstruir isso custa de R$ 700 mil a R$ 1,3 milhão.

> **4. Confiança do usuário** — Uma vez que o usuário confia na HIVE como seu advogado, o custo de troca é altíssimo.

> **5. HIVE Score como bureau alternativo** — Com massa crítica, o score baseado em fluxo de caixa real vira selo de qualidade que força bancos a baixarem juros.

### O que a comparação **não** resolve

Nada acima muda o fato de que a HIVE tem **zero usuários**. A tabela mede
capacidade instalada, não posição de mercado — e capacidade instalada sem
distribuição vale uma fração do que custou construir.

---

## 🚀 Estratégias de Crescimento

### 1. B2B2C — Bem-Estar Financeiro Corporativo

O CAC no B2C financeiro é R$ 80–150/usuário. O canal B2B2C muda a economia do negócio: vender a HIVE como benefício corporativo (estilo Gympass para finanças). O RH distribui o app — uma venda = 10.000–50.000 usuários com CAC ~zero.

| Aspecto | Detalhe |
|:---|:---|
| **Proposta para o RH** | Estresse financeiro custa ~R$ 15.000/ano por funcionário em produtividade (PwC) |
| **Pricing** | R$ 5–15/funcionário/mês → empresa de 10.000 = R$ 100k–150k MRR por contrato |
| **Efeito colateral** | Funcionário conecta contas pessoais; ao sair da empresa, migra para plano individual |

### 2. HIVE Score — Bureau de Crédito Alternativo

O Serasa olha o passado (inadimplência); a HIVE olha o presente (fluxo de caixa real). Fase 1: gamificação interna (✅ base pronta — health score + badges). Fase 2: score exportável que o usuário mostra ao pedir crédito. Fase 3: instituições consultam mediante pagamento — receita sem quebrar neutralidade (o usuário decide compartilhar).

### 3. HIVE Wrapped — Viralização Orgânica

✅ **Gerador já implementado** (`/viral/wrapped/{user_id}/{year}/svg`) e com tela no app (`/wrapped`). Todo dezembro (e trimestralmente para Pro/Total): quanto cada banco ganhou com você, top tarifas evitáveis, total economizado pela HIVE, evolução do score. Benchmark Spotify: ~20% de share rate; conversão esperada de 3–5% dos alcançados.

### 4. Expansão LatAm — Playbook Mexicano

México: Open Banking regulado (Ley Fintech 2018), 60M sub-bancarizados, concentração bancária similar (7 bancos = 80%), tarifa média ~MXN 3.000/ano. Provar no Brasil (2026–2027) → adaptar conectores (2028) → tese "LatAm" com multiplicador de valuation 2–3×.

---

## 🏗️ Arquitetura Técnica

```
┌───────────────────────────────────────────────────────────────────┐
│   APP WEB oficial (frontend-react, React 19) · PWA Widget/Push    │
│   Demo Streamlit (backend/demo) sobre os mesmos serviços          │
└────────────────────────────┬──────────────────────────────────────┘
                             │ HTTPS /api/v1 · JWT (+ refresh rotativo)
┌────────────────────────────▼──────────────────────────────────────┐
│                   FastAPI — app/main.py                           │
│   Rate Limiting (Redis) · CORS estrito · Security Headers · CSP   │
│        Audit Log · Correlation IDs · Health/Readiness             │
└──────┬──────────┬──────────┬───────────┬──────────────────────────┘
       │          │          │           │
┌──────▼───┐ ┌───▼──────┐ ┌─▼─────────┐ ┌▼──────────────────────┐
│   ETL    │ │ Cashflow │ │ Architect │ │  Agent (LangGraph)    │
│ Pipeline │ │  Engine  │ │ MonteCarlo│ │  ReAct + Claude/GPT   │
│ 8 stages │ │Safe2Spend│ │  VPL/TIR  │ │  31 Financial Tools   │
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
│     PostgreSQL + SQLAlchemy 2.0 + Alembic · Polars · DuckDB      │
│        Redis (cache, locks, rate limit, memória do agente)       │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    INTEGRAÇÕES EXTERNAS                          │
│  Pluggy (Open Finance) · BACEN SGS/SVR · Open Finance Dados      │
│  Abertos · SERPRO · Claude / OpenAI · Stripe · SendGrid/SMTP     │
└──────────────────────────────────────────────────────────────────┘
```

### Padrões Arquiteturais

| Padrão | Aplicação |
|:---|:---|
| **Feature-driven** | Cada funcionalidade em `backend/app/{feature}/` isolado com router próprio |
| **Feed + Chat** | Toda feature entrega por card no feed E tool no agente |
| **Pipeline Pattern** | ETL 8 estágios: Ingest → Classify → Detect → Validate → Persist |
| **Strategy Pattern** | Parsing por banco: Nubank, Itaú, Inter, default |
| **ReAct Agent** | LangGraph: pensa → chama ferramenta → observa → repete |
| **Multi-layer Fallback** | ML → Regras → Defaults em classificadores; SELIC dinâmica → fallback fixo; checkpointer Redis → Postgres → memória |
| **Job Guard** | Lock distribuído Redis (`SET NX EX`) com fallback em memória |
| **Behavioral Clustering** | 8 clusters adaptam todas as recomendações |
| **Procedência explícita** | Cada ferramenta emite `confianca`, `cobertura`, `fontes` e `degradado`; o agente usa, o usuário não vê |

### Stack

| Camada | Backend | | Camada | Frontend/DevOps |
|:---|:---|---|:---|:---|
| API | FastAPI 0.139 + Uvicorn + Pydantic 2 | | Framework | React 19 + TypeScript 5.9 |
| Database | PostgreSQL + SQLAlchemy 2.0 + Alembic 1.13 | | Build | Vite 8 |
| Cache/Locks | Redis + SlowAPI | | Styling | TailwindCSS 4 + CSS por tela |
| DataFrames | Polars 1.0 · DuckDB 1.4 | | Dados | React Query 5 + Axios · Zustand 5 |
| ML | Scikit-learn 1.8 · SALib (sensibilidade) | | Rotas · Gráficos | React Router 7 · Recharts 3 |
| Open Finance | Pluggy + Dados Abertos | | PWA | Manifest + Service Worker + VAPID |
| Taxas | BACEN SGS + ANBIMA | | Container | Docker · nginx (frontend) |
| IA | LangGraph 0.2 + Claude (ou OpenAI) | | CI | GitHub Actions (testes + pip-audit + build) |
| Scheduler | APScheduler 3.10 | | Deploy | Railway (`Dockerfile.railway`) |
| Pagamentos | Stripe | | Testes | pytest · Vitest · Playwright |

### Estrutura do repositório

```
codigos-nexa/
├── backend/
│   ├── app/                 # API: um pacote por domínio (agent, architect, billing, costs,
│   │                        #   defense, fiscal, forecast, goals, notifications, opportunities,
│   │                        #   optimizer, pluggy_sync, privacy, rights, tax, viral, ...)
│   │   ├── main.py          # app FastAPI, middlewares, rate limit, startup
│   │   ├── api/v1/          # router agregador + rotas de auth, pluggy, reconnect, dashboard
│   │   ├── core/            # config, banco, segurança, scheduler, modelos ORM
│   │   └── jobs/            # jobs do scheduler
│   ├── alembic/             # migrações
│   ├── demo/                # personas, seed pelo ETL real, apps Streamlit
│   ├── data/                # catálogo de cartões, produtos, tarifas, datasets de treino
│   ├── models/              # artefatos de ML
│   ├── tests/               # suíte pytest (um diretório por domínio + ligacao/ + agent/)
│   ├── requirements.txt     # pins de desenvolvimento/CI
│   └── requirements.railway.txt  # faixas usadas no deploy
├── frontend-react/
│   ├── src/api/             # módulos tipados por tela + cliente HTTP com refresh
│   ├── src/pages/           # telas (21)
│   ├── src/components/      # AppShell, guardas de rota, UI
│   ├── src/pwa/             # registro do service worker e push
│   ├── e2e/                 # testes de ponta a ponta (Playwright)
│   └── nginx.conf.template  # proxy /api em produção
├── docs/                    # relatório, segurança, funcionalidades, roadmap
├── docker-compose.yml       # api + postgres + redis + frontend
├── Dockerfile               # imagem da API usada pelo compose
├── Dockerfile.railway       # imagem de produção (Railway)
└── railway.toml
```

---

## 🔌 Endpoints da API

**141 operações em 134 caminhos.** Todas as rotas de dados ficam sob `/api/v1` e exigem `Authorization: Bearer <token>`, exceto as marcadas como públicas. Rotas com `{user_id}` só respondem ao dono do token (403 para outra pessoa). Swagger em `http://localhost:8000/docs`.

### Sistema e Autenticação

| Método | Rota | Descrição |
|:---:|:---|:---|
| `GET` | `/health` · `/readiness` · `/version` | Saúde, prontidão e versão (públicas) |
| `GET` | `/api/v1/auth/check-email?email=` | E-mail disponível para cadastro? (pública, 20/min) |
| `POST` | `/api/v1/auth/register` | Cadastro (`accepted_terms` obrigatório; dispara verificação de e-mail) |
| `POST` | `/api/v1/auth/token` | Login (formulário OAuth2: `username` = e-mail, `password`) → access + refresh |
| `POST` | `/api/v1/auth/refresh` | Troca o refresh por um par novo (uso único) |
| `POST` | `/api/v1/auth/logout` · `/auth/logout-all` | Encerra a sessão atual · todas as sessões |
| `POST` | `/api/v1/auth/forgot-password` · `/auth/reset-password` | Reset de senha: token de uso único (60 min), sempre 202 |
| `POST` | `/api/v1/auth/verify-email` · `/auth/resend-verification` | Verificação de e-mail: token de uso único (48 h) |

<details>
<summary><strong>Ver todos os endpoints por domínio</strong></summary>

### Open Finance, Contas e Cartões

| Método | Rota | Descrição |
|:---:|:---|:---|
| `POST` | `/api/v1/pluggy/connect-token` | Connect Token para o widget Pluggy |
| `GET` | `/api/v1/pluggy/connections` | Conexões persistidas do usuário, com `data_source` (sem chamar a Pluggy) |
| `GET/POST` | `/api/v1/pluggy/items` | Lista · salva um item conectado pelo widget |
| `POST` | `/api/v1/pluggy/sandbox` | Cria um item de sandbox para testes |
| `POST` | `/api/v1/pluggy/sync` | Sync bloqueante (legado) |
| `POST/GET` | `/api/v1/pluggy/sync/jobs` | Inicia um sync assíncrono · lista os últimos jobs |
| `GET` | `/api/v1/pluggy/sync/jobs/{job_id}` | Long-polling do progresso |
| `GET` | `/api/v1/pluggy/sync/jobs/{job_id}/stream` | Progresso via SSE (`text/event-stream`) |
| `GET` | `/api/v1/pluggy/cards` | Cartões de crédito do usuário |
| `POST` | `/api/v1/pluggy/cards/manual` | Cadastra um cartão manualmente |
| `POST` | `/api/v1/pluggy/webhook` | Webhook `item/*` da Pluggy (assinado; pública) |
| `POST` | `/api/v1/reconnect/{user_id}` · `/reconnect/{user_id}/callback` | Renovação de consentimento Open Finance |
| `GET` | `/api/v1/transactions/{user_id}` | Lançamentos paginados (`offset`, `total`, `has_more`) |
| `GET` | `/api/v1/transactions/{user_id}/summary` | Resumo de receitas, gastos e saldo |
| `POST` | `/api/v1/transactions/webhook` | Webhook de transações (assinado; pública) |
| `GET` | `/api/v1/data-quality/{user_id}` | O que a ingestão descartou e por quê |
| `POST` | `/api/v1/context/override` | Corrige PF/PJ de um lançamento |
| `GET` | `/api/v1/context/overrides` · `/context/overrides/stats` | Correções do usuário e estatísticas |
| `GET` | `/api/v1/banks/simulate/{bank}` | Extrato simulado por banco (desenvolvimento) |

### Saúde Financeira (F1)

| Método | Rota | Descrição |
|:---:|:---|:---|
| `GET` | `/api/v1/forecast/{user_id}` | Projeção de caixa, safe-to-spend e perfil (`negative_day`, `first_negative_date`, `savings_rate` em %) |
| `GET` | `/api/v1/safe-to-spend/{user_id}` | Orçamento do mês e gasto até hoje |
| `GET` | `/api/v1/safe-to-spend/{user_id}/widget` | Payload compacto do widget PWA (~200 bytes, com `data_as_of`/`stale`) |
| `GET` | `/api/v1/shadow_invoice/{user_id}` · `/{user_id}/summary` | Parcelas e assinaturas futuras |
| `GET` | `/api/v1/subscriptions/{user_id}` · `/{user_id}/simple` | Assinaturas recorrentes detectadas |
| `GET` | `/api/v1/alerts/{user_id}` | Alertas do fluxo de caixa (gravidade em `level`) |
| `DELETE` | `/api/v1/alerts/{user_id}/{alert_id}` | Dispensa um alerta |
| `GET` | `/dashboard/summary` · `/dashboard/safe-to-spend` | Painel consolidado (fora do prefixo `/api/v1`) |

### Otimização (F2, F3, F7)

| Método | Rota | Descrição |
|:---:|:---|:---|
| `POST` | `/api/v1/optimizer/analyze` | Análise da carteira de cartões |
| `GET` | `/api/v1/optimizer/cards` | Catálogo público de cartões |
| `GET` | `/api/v1/optimizer/portfolio/{user_id}` | Carteira atual do usuário |
| `GET` | `/api/v1/optimizer/reports/{user_id}` · `/reports/{report_id}/detail` | Relatórios salvos |
| `GET` | `/api/v1/optimizer/opportunity-cost` · `/roi/{card_id}` | Custo de oportunidade · ROI de um cartão |
| `GET` | `/api/v1/optimizer/promotions` · `/promotions/opportunities` | Promoções de transferência de pontos (públicas) |
| `POST` | `/api/v1/optimizer/recommendations/{recommendation_id}/feedback` | Feedback de recomendação |
| `GET` | `/api/v1/optimizer/feedback/stats` · `/feedback/weights` | Aprendizado por feedback |
| `POST` | `/api/v1/architect/simulate` | Financiar × consórcio × investir (VPL + Monte Carlo) |
| `POST` | `/api/v1/architect/timing-scenarios` | "E se eu esperar X meses?" |
| `GET` | `/api/v1/architect/simulations` · `/simulations/{id}` · `/simulations/{id}/sensitivity` | Histórico, detalhe e sensibilidade |
| `GET` | `/api/v1/architect/simulations/pending-feedback` · `/metrics` | Simulações aguardando desfecho · métricas |
| `POST` | `/api/v1/architect/simulations/{id}/feedback` · `/calibration/rollback` | Registra desfecho real · reverte a última calibração |
| `POST` | `/api/v1/purchase/analyze` | Melhor forma de pagamento para uma compra |
| `GET` | `/api/v1/purchase/checkout-context/{user_id}` · `/recent-review/{user_id}` | Veredito no checkout · revisão retroativa |

### Oportunidades (OPP)

| Método | Rota | Descrição |
|:---:|:---|:---|
| `GET` | `/api/v1/opportunities/{user_id}` | Dinheiro parado + recomendações |
| `GET` | `/api/v1/opportunities/{user_id}/banks` | Scorecard por banco (ajuste a risco) |
| `GET` | `/api/v1/opportunities/{user_id}/bank-match` | Melhor banco pelo perfil completo |
| `GET` | `/api/v1/opportunities/products` | Catálogo público transparente |
| `GET` | `/api/v1/opportunities/savings-vs-cdi` · `/treasury-vs-cdb-vs-savings` | Comparadores |
| `POST` | `/api/v1/opportunities/compare` | Simulação de investimento |

### Defesa, Direitos, Impostos e Custos (D, T, F5, F13)

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
| `GET` | `/api/v1/fiscal-report/{user_id}` · `/{user_id}/mixed-use` | Relatório fiscal MEI/PJ · uso misto PF/PJ |
| `GET` | `/api/v1/fiscal-report/ir-pf/compare` · `/ir-pf/breakeven` · `/forgotten-rights` | Comparadores de IR PF · direitos esquecidos (visão fiscal) |
| `GET` | `/api/v1/seasonality/{user_id}` | Calendário fiscal personalizado |
| `GET` | `/api/v1/costs/raio-x/{user_id}` | Raio-X de tarifas vs benchmark |
| `POST` | `/api/v1/negotiator/generate-script` | Roteiro de negociação |
| `GET/PATCH` | `/api/v1/negotiator/history/{user_id}` · `/history/{record_id}` | Histórico · registra o desfecho |

### Engajamento (MX, R, V)

| Método | Rota | Descrição |
|:---:|:---|:---|
| `GET` | `/api/v1/health-score/history/{user_id}` | Score e série histórica |
| `GET` | `/api/v1/health-score/challenges/{user_id}` · `/badges/{user_id}` | Desafios mensais · badges |
| `POST/GET` | `/api/v1/goals/{user_id}` · `/{user_id}/simple` | Cria · lista metas com projeção |
| `GET/DELETE` | `/api/v1/goals/{user_id}/{goal_id}` | Detalhe · abandona uma meta |
| `PATCH` | `/api/v1/goals/{user_id}/{goal_id}/progress` | Atualiza o progresso |
| `GET` | `/api/v1/budget/{user_id}` | Orçamento 50/30/20 por categoria |
| `GET` | `/api/v1/peers/compare/{user_id}` | Comparação com pares (IBGE/POF) |
| `GET` | `/api/v1/notifications/{user_id}` | Feed de cards filtrados por relevância (não marca como visto) |
| `POST` | `/api/v1/notifications/{user_id}/events` | Registra visto/clicado/dispensado |
| `GET` | `/api/v1/push/vapid-public-key` | Chave pública VAPID (pública) |
| `POST/DELETE` | `/api/v1/push/subscribe/{user_id}` | Inscreve · cancela Web Push |
| `GET` | `/api/v1/push/status/{user_id}` | Situação da inscrição |
| `GET` | `/api/v1/viral/savings-card/{user_id}[/svg\|/png]` | Placar de economia compartilhável |
| `GET` | `/api/v1/viral/wrapped/{user_id}/{year}[/svg]` | HIVE Wrapped anual |
| `POST/DELETE` | `/api/v1/viral/shares` · `/viral/shares/{share_id}` | Registra · revoga um compartilhamento |

### IA, Conta, Planos e Privacidade

| Método | Rota | Descrição |
|:---:|:---|:---|
| `POST` | `/api/v1/chat/` | Mensagem para o agente (`user_id`, `message`, `session_id`) → `response`, `tools_used` |
| `GET` | `/api/v1/chat/sessions` | Conversas do usuário (uma por `session_id`) |
| `GET/DELETE` | `/api/v1/chat/history` | Histórico (opcionalmente de uma conversa) · apaga histórico |
| `GET/PUT` | `/api/v1/settings/{user_id}` | Preferências do usuário |
| `GET` | `/api/v1/billing/plans` | Planos (pública) |
| `GET` | `/api/v1/billing/subscription/{user_id}` | Assinatura + uso dos limites |
| `POST` | `/api/v1/billing/checkout/{user_id}` · `/billing/portal/{user_id}` | Stripe Checkout e portal do cliente |
| `POST` | `/api/v1/billing/webhook` | Webhook Stripe (assinado, fail-closed; pública) |
| `GET` | `/api/v1/privacy/export/{user_id}` | Export LGPD (portabilidade) |
| `DELETE` | `/api/v1/privacy/erase/{user_id}` | Eliminação irreversível (LGPD) |

### Saúde dos módulos

`GET /api/v1/alerts` · `/forecast` · `/shadow_invoice` · `/reconnect` · `/architect/health` · `/optimizer/health` — health checks por módulo.

</details>

> 📄 Referência complementar em [docs/ENDPOINTS_SUMMARY.md](docs/ENDPOINTS_SUMMARY.md). A fonte da verdade é o OpenAPI em `/docs`.

---

## 🚀 Início Rápido

### Pré-requisitos

| Requisito | Versão |
|:---|:---|
| Python | 3.12 |
| PostgreSQL | 15+ (o compose usa 15) |
| Redis | 5+ (opcional em dev; sem ele o rate limit e a memória do agente caem para fallbacks) |
| Node.js | 20+ (desenvolvido com 22) |

> ⚠️ **Instalação do backend num ambiente limpo.** O `backend/requirements.txt`
> não resolve por inteiro: `langchain==0.2.16` exige `numpy<2` e `SALib==1.5.2`
> exige `numpy>=2` (está anotado no próprio arquivo). Um `pip install -r` direto
> termina em `ResolutionImpossible` — é por isso que o CI e o `docker compose`
> falham na instalação. Até a rodada de dependências, instale em dois passos:
>
> ```bash
> cd backend
> grep -viE '^SALib==' requirements.txt > /tmp/req-sem-salib.txt
> pip install -r /tmp/req-sem-salib.txt          # tudo menos o SALib
> pip install SALib==1.5.2 numpy==2.4.6           # o pip avisa do langchain e segue
> ```
>
> Testado numa venv limpa com Python 3.12: instala, a API sobe e os testes de
> contrato passam. É o mesmo estado dos ambientes de desenvolvimento atuais
> (numpy 2.4.6 com langchain 0.2), sobre o qual a suíte inteira passa.

### Opção A — Manual (recomendada para desenvolvimento)

**1. Backend**

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
# instalar as dependências conforme o aviso acima

# O config lê backend/.env. Se o seu .env fica na raiz do repositório,
# exporte-o antes de cada comando:
set -a; . ../.env; set +a

python3 -m alembic upgrade head
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app
```

Para desenvolvimento local, aponte `REDIS_URL=redis://localhost:6379/0` (o padrão do código é o host `redis` do compose) e `FRONTEND_BASE_URL=http://localhost:3000`.

**2. Dados de demonstração (opcional, recomendado)**

```bash
cd backend
python3 -m demo.seed            # 3 personas com um ano de extrato, pelo ETL real
python3 -m demo.seed --reset    # apaga e repopula
```

| Persona | Login | Plano | Perfil |
|:---|:---|:---:|:---|
| Ana Souza | `ana.demo@nexa.test` | Total | Assalariada |
| Bruno Lima | `bruno.demo@nexa.test` | Pro | MEI (receita PJ + gastos PF) |
| Carla Mendes | `carla.demo@nexa.test` | Free | Plano gratuito, com limites |

Senha das três: `demo1234` — **só para o banco de desenvolvimento**. Depois de um reseed, reinicie o uvicorn: o `cache_response` é em memória do processo e guarda respostas antigas.

**3. Frontend**

```bash
cd frontend-react
npm install
npm run dev                     # http://localhost:3000, proxy /api → http://localhost:8000
```

Para apontar o proxy para outro backend: `VITE_DEV_BACKEND=http://host:porta npm run dev`.

**4. Demo Streamlit (opcional)**

```bash
cd backend
streamlit run demo/hive_app.py  # http://localhost:8501 — o produto inteiro sobre as personas
```

Detalhes em [backend/demo/README.md](backend/demo/README.md).

### Opção B — Docker Compose

```bash
git clone https://github.com/BrunoMoacir/codigos-nexa.git && cd codigos-nexa
cp backend/.env.example backend/.env   # edite com suas credenciais
docker compose up --build
```

| Serviço | URL |
|:---|:---|
| API | http://localhost:8000 (roda `alembic upgrade head` ao subir) |
| Swagger UI | http://localhost:8000/docs |
| Frontend (Vite dev) | http://localhost:3000 |
| Postgres · Redis | `localhost:5432` · `localhost:6379` |

> O build da imagem da API usa `backend/requirements.txt` e hoje falha pelo
> conflito descrito acima. Até a correção, prefira a Opção A.

### Deploy (Railway)

`railway.toml` constrói com `Dockerfile.railway`, que instala `backend/requirements.railway.txt` (faixas de versão, não pins) e usa `/health` como healthcheck. Variáveis de produção de referência em [`.env.railway.example`](.env.railway.example). Em produção: `APP_ENV=production`, `SECRET_KEY` forte, `ALLOWED_ORIGINS` explícito, `PLUGGY_WEBHOOK_SECRET` e `DUCKDB_PATH` em volume persistente.

---

## ⚙️ Variáveis de Ambiente

Definidas em [`backend/app/core/config.py`](backend/app/core/config.py). Modelos: [`.env.example`](.env.example), [`backend/.env.example`](backend/.env.example) e [`.env.railway.example`](.env.railway.example). Nunca versione o `.env`.

| Grupo | Variável | Padrão | Para quê |
|:---|:---|:---|:---|
| **Núcleo** | `APP_ENV` | `development` | `production` liga as validações fail-closed |
| | `APP_MODE` | `dev` | `prod` desliga atalhos de desenvolvimento (override manual de dono, modo das respostas) |
| | `SECRET_KEY` | chave de dev | Assinatura dos JWT — obrigatória em produção |
| | `DATABASE_URL` | Postgres local | `postgresql+psycopg2://usuario:senha@host:5432/banco` |
| | `DB_POOL_SIZE` · `DB_MAX_OVERFLOW` | `5` · `10` | Pool do SQLAlchemy |
| | `REDIS_URL` | `redis://redis:6379/0` | Cache, locks, rate limit, blacklist de tokens, memória do agente |
| | `ALLOWED_ORIGINS` | `*` | Origens do CORS — `*` é recusado em produção |
| | `FRONTEND_BASE_URL` | `http://localhost:3000` | Links dos e-mails (reset, verificação) e fallback de CORS |
| | `LOG_LEVEL` | `INFO` | Nível de log |
| | `PORT` | — | Porta no Railway |
| | `DUCKDB_PATH` · `NEXA_CACHE_DIR` | `backend/finance.duckdb` · — | Histórico analítico (DuckDB) e cache em disco |
| **IA** | `LLM_PROVIDER` | `openai` | `anthropic` ou `openai` |
| | `LLM_MODEL` | `gpt-4o-mini` | Modelo; com `anthropic` e um `gpt-*`, usa `claude-haiku-4-5` |
| | `ANTHROPIC_API_KEY` · `OPENAI_API_KEY` | — | Chave do provedor escolhido |
| **Open Finance** | `PLUGGY_CLIENT_ID` · `PLUGGY_CLIENT_SECRET` | — | Credenciais da Pluggy |
| | `PLUGGY_BASE_URL` · `PLUGGY_CONNECT_URL` | API e Connect da Pluggy | Endpoints da Pluggy |
| | `PLUGGY_WEBHOOK_SECRET` | — | Obrigatório em produção (sem ele o webhook responde 503) |
| | `PLUGGY_AUTOSYNC_ON_WEBHOOK` | `true` | Sincroniza ao receber o webhook |
| | `PLUGGY_SYNC_LOOKBACK_DAYS` | `7` | Janela de releitura de cada sync |
| **Billing** | `STRIPE_SECRET_KEY` · `STRIPE_WEBHOOK_SECRET` | — | Stripe |
| | `STRIPE_PRICE_PRO_MONTHLY` · `STRIPE_PRICE_TOTAL_MONTHLY` | — | IDs dos Prices |
| | `BILLING_ENFORCEMENT_ENABLED` | `false` | `true` aplica os limites (402); `false` só registra |
| **Direitos** | `SERPRO_CONSUMER_KEY` · `SERPRO_CONSUMER_SECRET` | — | API Consulta Restituição |
| | `SERPRO_RESTITUICAO_PRIVATE_KEY_B64` · `SERPRO_RESTITUICAO_TRIAL` | — · `false` | Chave do e-CNPJ · ambiente trial |
| **E-mail** | `SENDGRID_API_KEY` ou `SMTP_HOST` · `SMTP_PORT` · `SMTP_USER` · `SMTP_PASSWORD` | — · `587` | Envio de e-mails |
| | `EMAIL_FROM` · `EMAIL_FROM_NAME` | `noreply@nexa.app` · `Nexa` | Remetente |
| **Push** | `VAPID_PUBLIC_KEY` · `VAPID_PRIVATE_KEY` · `VAPID_CLAIMS_EMAIL` | — | Web Push do PWA |
| **Jobs** | `SCHEDULER_ENABLED` | `false` | Liga o APScheduler |
| **Observabilidade** | `SENTRY_DSN` · `SENTRY_TRACES_SAMPLE_RATE` | — · `0.0` | Sentry (sem dados de extrato) |
| **Frontend** | `VITE_API_URL` | `/api/v1` | Base da API no navegador |
| | `VITE_DEV_BACKEND` | `http://localhost:8000` | Alvo do proxy do `npm run dev` |

---

## 🗄️ Banco de Dados

PostgreSQL com migrações Alembic em [`backend/alembic/versions/`](backend/alembic/versions/). O head atual é `84dbb59343ed`, uma revisão de merge que une o ramo do cadastro (`b2c4e6f8a0d1`) ao de cartões e conversas do chat (`b3e8a1c7f0d4`).

```bash
cd backend
python3 -m alembic upgrade head     # aplica tudo
python3 -m alembic heads            # deve listar UM head
```

> **Dois heads depois de um merge?** Crie uma revisão de merge
> (`alembic merge -m "junta ..." <head1> <head2>`) em vez de editar a cadeia, e
> nunca crie a mesma coluna em dois ramos. Na inicialização a API compara a
> revisão do banco com o head do código e loga um erro claro se estiverem
> diferentes.

Tabelas por domínio:

| Domínio | Tabelas |
|:---|:---|
| **Usuários e sessão** | `users` (com `phone` e `terms_accepted_at`), `auth_tokens`, `user_settings` |
| **Extrato e Open Finance** | `transactions_clean`, `rejected_transactions`, `account_balances`, `pluggy_items`, `pluggy_sync_jobs`, `credit_cards`, `context_overrides` |
| **Planejamento** | `financial_goals`, `shadow_invoices`, `health_score_history`, `user_badges`, `user_challenges` |
| **Simulações e otimização** | `architect_simulations`, `architect_simulation_metrics`, `architect_simulation_feedback`, `architect_calibration_state`, `optimization_reports`, `recommendation_feedback` |
| **Custos, oportunidades e negociação** | `bank_fee_history`, `bank_fee_trends`, `opportunity_snapshots`, `negotiation_history`, `intelligence_metrics` |
| **Agente** | `chat_messages` (com `session_id`), `checkpoints`, `checkpoint_writes`, `checkpoint_blobs`, `checkpoint_migrations` (checkpointer Postgres do LangGraph) |
| **Notificações** | `notification_delivery_log`, `daily_digest_log`, `push_subscriptions` |
| **Billing** | `user_subscriptions` |
| **Viral e comunidade** | `viral_share_log`, `viral_consent_receipts`, `viral_calculation_snapshots`, `viral_ranking_snapshots`, `community_*` (posts, reações, desafios, membros, denúncias, moderação — criadas pela migração `f1a2c3d4e5b6`, ainda sem rotas na API) |

O DuckDB (`backend/finance.duckdb`, ou `DUCKDB_PATH`) guarda o histórico analítico. Ele muda a cada execução da suíte — **não versione as alterações dele**.

---

## 🧪 Testes

### Backend

**3.636 passando · 0 falhas · 147 pulados · 79% de cobertura** (rodada completa de 21/10/2026). A suíte é mantida 100% verde como política do projeto.

| Lote | Testes | O que cobre |
|:---|---:|:---|
| `tests/optimizer/` | 926 | Catálogo de cartões, ranking, custo de oportunidade, promoções |
| `tests/architect/` | 630 | VPL, Monte Carlo, calibração pelas séries do BACEN, sensibilidade |
| `tests/test_*.py` (raiz) | 554 | ETL, pipeline ponta a ponta, segurança e LGPD, PF/PJ, Pluggy, endpoints |
| `tests/agent/` | 314 | As 31 ferramentas, histórico por conversa, agente de produção |
| `tests/opportunities/` | 200 | Radar, Bank Match, catálogo vivo |
| `tests/defense/` | 164 | D1–D6 e séries do BACEN |
| `tests/notifications/` | 143 | 17 geradores, filtro de relevância, entrega |
| `tests/fiscal/` · `tests/rights/` · `tests/seasonality/` | 87 · 80 · 79 | IR, MEI/DAS, direitos esquecidos, calendário fiscal |
| `tests/costs/` · `tests/viral/` · `tests/peers/` · `tests/purchase/` | 68 · 62 · 59 · 56 | Raio-X, Wrapped/placar, pares, compra inteligente |
| `tests/billing/` · `tests/ligacao/` · `tests/health_score/` · `tests/cashflow/` | 42 · 39 · 30 · 28 | Planos e gating, contratos front↔back, score, fluxo de caixa |
| `tests/negotiator/` · `tests/demo/` · `tests/auth/` · `tests/jobs/` · `tests/e2e/` | 27 · 21 · 14 · 8 · 5 | Negociador, personas, conta, jobs, ponta a ponta |

Os pulados são opcionais por custo ou ambiente: 126 avaliações da prosa do agente, que gastam tokens (ligue com `NEXA_EVAL_LLM=1`; o juiz LLM com `NEXA_EVAL_JUDGE=1`), 13 da suíte do usuário-referência, que pede o seed de dados reais, e os demais dependem de um LLM no ar ou do Redis Stack (`NEXA_TEST_REDIS_STACK_URL`).

Como rodar:

```bash
cd backend
set -a; . ../.env; set +a                       # se o .env estiver na raiz
python3 -m pytest tests/ligacao -q              # um domínio
python3 -m pytest tests/agent/test_chat_historico_por_sessao.py -q
python3 -m pytest tests/ --cov=app --cov-report=html
```

A suíte inteira leva ~25 min (o lote `architect` sozinho passa de 9 min, por causa do Monte Carlo). Rodar por lote — um diretório por vez, depois `tests/agent/` e os `tests/test_*.py` da raiz — dá o mesmo resultado e mostra onde cada falha está. Os testes usam o Postgres do `DATABASE_URL` e criam usuários descartáveis (`*@nexa.test`); o rate limiter é desligado no `conftest.py`.

**Testes de contrato front↔back** ([`tests/ligacao/`](backend/tests/ligacao/) e nos diretórios de cada domínio) fixam o formato que o app web consome:

| Contrato | Regra |
|:---|:---|
| Lançamentos | `/transactions/{user_id}` paginado com `offset`, `total` e `has_more`; `/summary` com receitas, gastos e saldo |
| Forecast | `negative_day` inteiro + `first_negative_date`; `savings_rate` em % |
| Notificações | `GET` idempotente; interações por `POST /events` |
| Alertas | Gravidade em `level` |
| Chat | Histórico por `session_id`, resposta com `tools_used`, conversas listadas por dono (403 para outra pessoa) |
| Cadastro e sessão | `accepted_terms` obrigatório, e-mail sem diferença de caixa, logout revoga o refresh |
| Widget | Mesmo diário do forecast + `data_as_of`/`stale` |
| Conexões | `data_source` por conexão (`demonstracao` · `sandbox` · `open_finance`) |
| Cartões | `/pluggy/cards` e `/cards/manual` só do dono do token |
| E-mail disponível | `/auth/check-email` com a mesma regra de caixa do cadastro |

**Cobertura não é atestado.** 79% mede o que foi *executado*, não o que foi *verificado*. As auditorias de 2026 encontraram dezenas de testes que passavam sobre código quebrado — por isso cada correção é validada por **mutação**: quebra-se o código de propósito e exige-se que um teste específico falhe. A distribuição também importa: `app/jobs` está a **28%**, o pior módulo do projeto — e é a camada que roda de madrugada sem ninguém olhando. Os mais cobertos são `app/seasonality` (97%), `app/peers` (94%) e `app/budget` (92%).

### Frontend

```bash
cd frontend-react
npx vitest run      # testes unitários (Vitest + Testing Library)
npx tsc -b          # checagem de tipos
npm run build       # tsc + build de produção
npm run lint        # ESLint
```

**29 testes unitários em 6 arquivos e 13 testes e2e, todos passando; lint, tipos e build sem erros.**

- **Unitários** (Vitest + Testing Library): Chat (histórico da conversa salva, envio na conversa atual, "Nova conversa" sem apagar a anterior, lista de conversas), Estratégias, componentes, destino seguro do login e a busca paginada da Organização.
- **Ponta a ponta** (Playwright, `npm run test:e2e`), contra o backend local com as personas: as 14 telas logadas abrem sem nenhum erro de API nos três planos, as abas navegam no celular, a sessão vencida renova sozinha, a sessão morta volta para a tela de origem depois do login, `next` externo é recusado e o cadastro envia `accepted_terms`. O envio real ao agente só roda com `HIVE_E2E_CHAT=1`.

### CI

GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) em push para `main`/`develop` e PR para `main`: migrações + pytest, `pip-audit` nos pins diretos + catraca de CVE na árvore transitiva (o número só pode descer) build da imagem Docker e, para o `frontend-react`, lint + tipos + testes unitários + build. **Hoje os jobs do backend falham na instalação de dependências** — ver [Problemas Conhecidos](#️-problemas-conhecidos).

---

## 📖 Exemplos de Uso

### Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -d "username=ana.demo@nexa.test&password=demo1234"
# → {"access_token": "...", "refresh_token": "...", "user_id": "demo-ana", ...}
```

### Chat com o Agente

```bash
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"user_id": "demo-ana", "session_id": "minha-conversa-1",
       "message": "Como estão minhas finanças? Posso comprar um carro de R$ 60.000?"}'
```

O agente encadeia `get_user_profile_context` → `get_financial_forecast` → `get_financing_simulation` e responde com análise adaptada ao cluster comportamental; `tools_used` lista as ferramentas chamadas.

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
  -d '{"user_id": "demo-ana", "asset_type": "VEICULO", "target_amount": 60000,
       "down_payment": 12000, "financing_months": 48, "max_monthly_budget": 2500,
       "risk_profile": "moderado", "monthly_income": 8000}'
```

**Retorna:** as estratégias ranqueadas por VPL com sensibilidade a juros e intervalo Monte Carlo (95%). Leva de 12 a 20 s.

---

## 🤝 Como Contribuir

- **Idioma:** código de domínio, mensagens de commit, docs e textos de interface em português.
- **Commits:** convencionais (`feat(escopo):`, `fix(escopo):`, `docs:`, `test:`), um assunto por commit.
- **Suíte verde é política:** nada entra com teste falhando. Mudou um contrato que o app consome? Atualize o teste em `tests/ligacao/` e o módulo em `frontend-react/src/api/` no mesmo commit.
- **Feature nova:** card no feed **e** ferramenta no agente (ver [Superfícies](#-as-superfícies-do-produto)); nada de valores fabricados — sem dado, a resposta diz o que falta.
- **Rota nova com dados do usuário:** `require_owner` (ou o usuário do token) é obrigatório; o teste de segurança falha se uma rota privada não exigir autenticação. Rota pública precisa entrar na allowlist de `tests/test_seguranca_lgpd.py` com justificativa.
- **Migrações:** uma por mudança de schema; nunca a mesma coluna em dois ramos; um único head depois de cada merge.
- **Visual do app:** o `frontend-react` segue o redesenho da Beatriz Samaha; mudança visual se combina com ela antes. O app precisa passar em `npm run lint`, `npx tsc -b`, `npx vitest run` e `npm run test:e2e`.
- **Não versionar:** `.env`, `backend/finance.duckdb`, `test.db`, artefatos de cobertura.
- **Personas:** mudou o classificador PF/PJ? Rode `python3 -m demo.seed --reset` — o banco guarda o rótulo antigo.

---

## ⚠️ Problemas Conhecidos

Verificados em outubro/2026:

| Problema | Impacto | Contorno |
|:---|:---|:---|
| `backend/requirements.txt` não resolve (`langchain 0.2.16` × `SALib 1.5.2` por causa do numpy) | CI falha na instalação desde agosto; `docker compose up --build` não sobe a API | Instalação em dois passos ([Início Rápido](#-início-rápido)); correção real = atualizar o langchain ou trocar o SALib |
| Job "Docker Build" do CI roda `docker build ./backend`, mas não existe `backend/Dockerfile` | O job falharia mesmo com as dependências resolvidas | Apontar para o `Dockerfile` da raiz (`docker build -f Dockerfile .`) |
| `POST /pluggy/cards/manual` aceita limite negativo e qualquer texto em `last4` | Dado ruim pode entrar pela tela de cartão manual | Validar no backend (Pydantic) |
| Tabelas `community_*` existem no banco sem rotas na API | Schema sem uso | Remover ou implementar |
| `docs/SETUP_LOCAL.md` descreve o fluxo antigo (Streamlit como frontend, fallback DuckDB) | Pode confundir quem chega | Usar o [Início Rápido](#-início-rápido) deste README |

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

### Fase 2 — Monetização e Casa Própria (em andamento)

- [x] **Billing + gating Free/Pro/Total** (Stripe, dark launch — falta só chaves + flip da flag)
- [x] **App web ligado ao backend real** em todas as telas (out/2026)
- [x] Redesenho visual HIVE: login, cadastro, chat por conversas, feed, organização, cartões
- [x] Telas de conta: recuperação de senha e verificação de e-mail
- [x] Personas de demonstração com um ano de extrato pelo ETL real
- [ ] **CI verde** (resolver o conflito de dependências)
- [x] **Frontend oficial:** `frontend-react` promovido a app oficial, com o design como está (out/2026)
- [ ] Validação jurídica e lançamento do D5
- [ ] R4.a relatório trimestral · R5 anti-churn (⚠️ jobs escritos e nunca agendados)
- [ ] Lançamento público do Wrapped (dezembro)

### Fase 3 — Escala (2027)

- [ ] App mobile nativo (widget homescreen, FCM)
- [ ] F6 sweep automático · F8 radar 200+ instituições · F12 modo família
- [ ] HIVE Score exportável → bureau alternativo
- [ ] B2B2C — primeiros contratos corporativos
- [ ] V3 ranking público de bancos

### Fase 4 — LatAm (2028)

- [ ] Expansão México (Ley Fintech)
- [ ] API de inteligência financeira para terceiros

---

## 📚 Documentação

| Arquivo | Conteúdo |
|:---|:---|
| **[RELATORIO-PROJETO.md](docs/RELATORIO-PROJETO.md)** | **Relatório de projeto** — notas por camada, posição competitiva (Pierre, Muuney, Jota, Mobills, Organizze), economia unitária, crescimento, avaliação, riscos e plano de 90 dias |
| [funcionalidades/](docs/funcionalidades/README.md) | **Documentação de todas as funcionalidades** — o que cada uma faz, o que NÃO faz e gaps, técnica e em palavras simples (18 domínios) |
| [backend/demo/README.md](backend/demo/README.md) | Demo Streamlit: personas, seed pelo ETL real, o que cada superfície mostra |
| [ROADMAP.md](docs/ROADMAP.md) | Roadmap de produto auditado contra o código |
| [MUDANÇAS.md](docs/MUDANÇAS.md) | Mapa técnico de cada mudança por camada |
| [SEGURANCA.md](docs/SEGURANCA.md) | Modelo de segurança completo |
| [ENDPOINTS_SUMMARY.md](docs/ENDPOINTS_SUMMARY.md) | Referência de endpoints (o OpenAPI em `/docs` é a fonte da verdade) |
| [QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md) | Cheatsheet do dev |
| [BACKEND_REFERENCE.md](docs/BACKEND_REFERENCE.md) | Referência de arquivos do backend |
| [OPP.md](docs/OPP.md) | Spec do Radar de Oportunidades |
| [SETUP_LOCAL.md](docs/SETUP_LOCAL.md) | Setup antigo sem Docker (ver [Problemas Conhecidos](#️-problemas-conhecidos)) |

---

<div align="center">

### HIVE

**141 operações de API · 31 ferramentas de IA · 17 tipos de alerta proativo · 3.636 testes passando**

*Trabalhar para você, não para o banco.*

---

**Outubro 2026 · Confidencial**

</div>
