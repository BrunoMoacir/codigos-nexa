# DOCUMENTAÇÃO COMPLETA DE ENDPOINTS FASTAPI - NEXA

## SUMÁRIO EXECUTIVO
- **Total de Endpoints:** 56+
- **Routers Principais:** 20+
- **Funcionalidades Prontas:** 15 (Auth, Forecast, Shadow Invoice, Alerts, etc)
- **Funcionalidades Incompletas:** 8 (TODO: DB queries, Persistência, etc)
- **Status:** MVP Funcional - Alguns endpoints dependem de mock data (NexaRunner)

---

## 1. AUTH (Autenticação & Registro)
**Arquivo:** `backend/app/api/v1/routes/auth.py`
**Prefix:** `/auth`
**Status:** ✅ PRONTO

| Método | Endpoint | Descrição | Auth | Params | Frontend? |
|--------|----------|-----------|------|--------|-----------|
| POST | `/auth/register` | Registra novo usuário (email/senha) | ❌ Não | email, password, full_name | ✅ Sim |
| POST | `/auth/token` | Login via OAuth2 (retorna JWT) | ❌ Não | username, password (form) | ✅ Sim |

**Response Examples:**
```json
POST /auth/register → {
  "message": "Usuário criado com sucesso",
  "user_id": "uuid"
}

POST /auth/token → {
  "access_token": "eyJhbGc...",
  "token_type": "bearer",
  "user_id": "uuid"
}
```
**Rate Limit:** 10/minute

---

## 2. TRANSAÇÕES (ETL - Ingestão de Dados)
**Arquivo:** `backend/app/api/v1/routes/transactions.py`
**Prefix:** `/transactions`
**Status:** ✅ PRONTO (com fallback dev)

| Método | Endpoint | Descrição | Auth | Params | Frontend? |
|--------|----------|-----------|------|--------|-----------|
| POST | `/transactions/webhook` | Recebe webhook de transações da Pluggy | ❌ Não | payload (JSON), user_id (query) | ⚠️ Partial |
| GET | `/transactions/{user_id}` | Busca transações com filtros | ✅ Sim | start_date, end_date, category, type, limit | ⚠️ Partial |

**Status Endpoint 1:** 
- Valida batch com Pydantic
- Processa ETL: Ingestor → Classifier
- Salva no Postgres (se disponível)
- Fallback para mock em dev

**Response:**
```json
GET /transactions/user_123?limit=10 → {
  "user_id": "user_123",
  "total": 150,
  "debit_count": 95,
  "credit_count": 55,
  "transactions": [
    {
      "transaction_id": "tx_001",
      "description": "Mercado",
      "amount": -150.50,
      "date": "2025-03-11",
      "category": "Alimentação",
      "is_recurring": false,
      "is_installment": false
    }
  ]
}
```

---

## 3. FORECAST (F1 - Previsão Consolidada)
**Arquivo:** `backend/app/api/v1/routes/forecast.py`
**Prefix:** `/forecast`
**Status:** ✅ PRONTO

| Método | Endpoint | Descrição | Auth | Params | Frontend? |
|--------|----------|-----------|------|--------|-----------|
| GET | `/forecast/{user_id}` | Previsão 30 dias: cashflow + safe-to-spend | ✅ Sim | days_ahead | ✅ Sim |
| GET | `/forecast` | Health check | ❌ Não | - | ❌ Não |

**Retorna:**
- Saldo atual
- Projeção diária (30 dias)
- Safe-to-spend total/diário
- Renda estimada
- Health score financeiro

---

## 4. PLUGGY (Open Finance - Conexão de Bancos)
**Arquivo:** `backend/app/api/v1/routes/pluggy.py`
**Prefix:** `/pluggy`
**Status:** ✅ PRONTO

| Método | Endpoint | Descrição | Auth | Params | Frontend? |
|--------|----------|-----------|------|--------|-----------|
| POST | `/pluggy/connect-token` | Gera token para Widget Pluggy | ✅ Sim | - | ✅ Sim |
| GET | `/pluggy/items` | Lista contas conectadas do usuário | ✅ Sim | - | ✅ Sim |
| POST | `/pluggy/sandbox` | Cria conexão Sandbox para testes | ✅ Sim | - | ✅ Sim |

---

## 5. SHADOW INVOICE (Obrigações Futuras Detectadas)
**Arquivo:** `backend/app/api/v1/routes/shadow_invoice.py`
**Prefix:** `/shadow_invoice`
**Status:** ✅ PRONTO (com fallback NexaRunner)

| Método | Endpoint | Descrição | Auth | Params | Frontend? |
|--------|----------|-----------|------|--------|-----------|
| GET | `/shadow_invoice/{user_id}` | Lista obrigações futuras (30 dias) | ✅ Sim | days_ahead | ❌ Não |
| GET | `/shadow_invoice/{user_id}/summary` | Resumo de obrigações (números chave) | ✅ Sim | - | ❌ Não |
| GET | `/shadow_invoice` | Health check | ❌ Não | - | ❌ Não |

**Detecta:** Parcelamentos, Assinaturas, Gastos Variáveis
**Response:**
```json
{
  "invoices": [
    {
      "id": "shadow_001",
      "date": "2025-02-15",
      "merchant": "MAGALU",
      "amount": -100.0,
      "type": "installment",
      "confidence": 0.95
    }
  ],
  "total_count": 42,
  "total_monthly_impact": -1068.10,
  "subscriptions_count": 9,
  "installments_count": 33
}
```

---

## 6. ALERTS (Alertas Financeiros Proativos)
**Arquivo:** `backend/app/api/v1/routes/alerts.py`
**Prefix:** `/alerts`
**Status:** ✅ PRONTO

| Método | Endpoint | Descrição | Auth | Params | Frontend? |
|--------|----------|-----------|------|--------|-----------|
| GET | `/alerts/{user_id}` | Retorna alertas ativos (token expiry, neg. balance, etc) | ✅ Sim | - | ❌ Não |
| DELETE | `/alerts/{user_id}/{alert_id}` | Marca alerta como lido | ✅ Sim | - | ❌ Não |
| GET | `/alerts` | Health check | ❌ Não | - | ❌ Não |

**Tipos de Alerta:**
- TOKEN_EXPIRY (Consentimento vencendo)
- NEGATIVE_BALANCE (Vai ficar negativo)
- HIGH_COMMITMENT (>80% caixa comprometido)
- SPENDING_ANOMALY (Gasto fora padrão — MI.1)

---

## 7. RECONNECT (Reconectar Consentimento Open Finance)
**Arquivo:** `backend/app/api/v1/routes/reconnect.py`
**Prefix:** `/reconnect`
**Status:** ⚠️ PARCIAL (URLs geradas, sem webhook real)

| Método | Endpoint | Descrição | Auth | Params | Frontend? |
|--------|----------|-----------|------|--------|-----------|
| POST | `/reconnect/{user_id}` | Gera URL para reconectar consentimento | ✅ Sim | redirect_uri (opcional) | ❌ Não |
| POST | `/reconnect/{user_id}/callback` | Webhook de retorno (placeholder) | ❌ Não | connection_id | ⚠️ Partial |
| GET | `/reconnect` | Health check | ❌ Não | - | ❌ Não |

**Response:**
```json
{
  "user_id": "user_123",
  "connect_url": "https://pluggy.io/open-finance/connections/abc123",
  "expires_at": "2025-02-12T15:30:00Z",
  "redirect_back_uri": "https://nexa.app/dashboard"
}
```

---

## 8. CONTEXT OVERRIDE (F4 - Nexa Divider)
**Arquivo:** `backend/app/api/v1/routes/context_override.py`
**Prefix:** `/context`
**Status:** ✅ PRONTO (com fallback)

| Método | Endpoint | Descrição | Auth | Params | Frontend? |
|--------|----------|-----------|------|--------|-----------|
| POST | `/context/override` | Sobrescreve contexto PF/PJ de transação | ✅ Sim | transaction_id, context_type | ❌ Não |
| GET | `/context/overrides` | Lista overrides do usuário | ✅ Sim | - | ❌ Não |
| GET | `/context/overrides/stats` | Stats de overrides | ✅ Sim | - | ❌ Não |

---

## 9. ARCHITECT (F3 - Simulador de Conquistas)
**Arquivo:** `backend/app/api/v1/routes/architect.py`
**Prefix:** `/architect`
**Status:** ✅ PRONTO

| Método | Endpoint | Descrição | Auth | Params | Frontend? |
|--------|----------|-----------|------|--------|-----------|
| POST | `/architect/simulate` | Simula Financiamento vs Consórcio vs Poupar | ✅ Sim | SimulationRequest (JSON) | ❌ Não |
| GET | `/architect/simulations` | Histórico de simulações do usuário | ✅ Sim | - | ❌ Não |
| GET | `/architect/simulations/{simulation_id}` | Detalhe de simulação específica | ✅ Sim | - | ❌ Não |
| GET | `/architect/metrics` | Métricas agregadas do usuário | ✅ Sim | - | ❌ Não |
| GET | `/architect/health` | Health check | ❌ Não | - | ❌ Não |

**Estratégias:** Financiamento, Consórcio, Poupança

---

## 10. OPTIMIZER (F2 - Otimização de Cartões)
**Arquivo:** `backend/app/api/v1/routes/optimizer.py`
**Prefix:** `/optimizer`
**Status:** ✅ PRONTO

| Método | Endpoint | Descrição | Auth | Params | Frontend? |
|--------|----------|-----------|------|--------|-----------|
| POST | `/optimizer/analyze` | Recomenda melhor cartão baseado em gastos | ✅ Sim | OptimizationRequest (JSON) | ❌ Não |
| GET | `/optimizer/reports/{user_id}` | Histórico resumido de otimizações | ✅ Sim | - | ❌ Não |
| GET | `/optimizer/reports/{report_id}/detail` | Detalhe completo de relatório | ✅ Sim | - | ❌ Não |
| GET | `/optimizer/cards` | Lista cartões na base de conhecimento | ✅ Sim | - | ❌ Não |
| GET | `/optimizer/opportunity-cost` | Calcula opportunity cost de trocar cartão | ✅ Sim | user_id, current_card_id, months | ❌ Não |
| GET | `/optimizer/portfolio/{user_id}` | Portfolio de cartões do usuário | ✅ Sim | - | ❌ Não |
| GET | `/optimizer/roi/{card_id}` | ROI atual do cartão | ✅ Sim | - | ❌ Não |
| GET | `/optimizer/promotions` | Promoções disponíveis | ✅ Sim | - | ❌ Não |

---

## 11. CHAT (Agent IA - F2/F3)
**Arquivo:** `backend/app/api/v1/routes/chat.py`
**Prefix:** `/chat`
**Status:** ✅ PRONTO

| Método | Endpoint | Descrição | Auth | Params | Frontend? |
|--------|----------|-----------|------|--------|-----------|
| POST | `/chat/` | Conversa com agente LangGraph | ✅ Sim | ChatRequest (user_id, message) | ✅ Sim |

**Rate Limit:** 20/minute

---

## 12. HEALTH SCORE (MX.1)
**Arquivo:** `backend/app/api/v1/routes/health_score.py`
**Prefix:** `/health-score`
**Status:** ✅ PRONTO

| Método | Endpoint | Descrição | Auth | Params | Frontend? |
|--------|----------|-----------|------|--------|-----------|
| GET | `/health-score/history/{user_id}` | Histórico de saúde financeira (30 dias) | ✅ Sim | - | ❌ Não |

---

## 13. SUBSCRIPTIONS (M1.5)
**Arquivo:** `backend/app/api/v1/routes/subscriptions.py`
**Prefix:** `/subscriptions`
**Status:** ✅ PRONTO

| Método | Endpoint | Descrição | Auth | Params | Frontend? |
|--------|----------|-----------|------|--------|-----------|
| GET | `/subscriptions/{user_id}` | Lista assinaturas detectadas | ✅ Sim | months (padrão: 6) | ❌ Não |

---

## 14. GOALS (MX.2 - Metas Financeiras)
**Arquivo:** `backend/app/api/v1/routes/goals.py`
**Prefix:** `/goals`
**Status:** ✅ PRONTO

| Método | Endpoint | Descrição | Auth | Params | Frontend? |
|--------|----------|-----------|------|--------|-----------|
| POST | `/goals/{user_id}` | Cria nova meta financeira | ✅ Sim | CreateGoalRequest (JSON) | ✅ Sim |
| GET | `/goals/{user_id}` | Lista metas do usuário | ✅ Sim | - | ✅ Sim |
| GET | `/goals/{user_id}/{goal_id}` | Detalhe + projeção de meta | ✅ Sim | - | ❌ Não |
| PATCH | `/goals/{user_id}/{goal_id}/progress` | Atualiza progresso da meta | ✅ Sim | UpdateProgressRequest (JSON) | ❌ Não |
| DELETE | `/goals/{user_id}/{goal_id}` | Abandona meta | ✅ Sim | - | ❌ Não |

**Tipos:** imovel, viagem, carro, educacao, emergencia, outros

---

## 15. BUDGET (M1.3 - Orçamento Inteligente)
**Arquivo:** `backend/app/api/v1/routes/budget.py`
**Prefix:** `/budget`
**Status:** ✅ PRONTO

| Método | Endpoint | Descrição | Auth | Params | Frontend? |
|--------|----------|-----------|------|--------|-----------|
| GET | `/budget/{user_id}` | Sugestões de orçamento por categoria | ✅ Sim | monthly_income | ✅ Sim |

---

## 16. NOTIFICATIONS (MX.3 - Notificações Proativas)
**Arquivo:** `backend/app/api/v1/routes/notifications.py`
**Prefix:** `/notifications`
**Status:** ✅ PRONTO

| Método | Endpoint | Descrição | Auth | Params | Frontend? |
|--------|----------|-----------|------|--------|-----------|
| GET | `/notifications/{user_id}` | Notificações baseadas em eventos | ✅ Sim | - | ❌ Não |

---

## 17. FISCAL REPORT (M4.1 - Relatório Fiscal PJ)
**Arquivo:** `backend/app/api/v1/routes/fiscal_report.py`
**Prefix:** `/fiscal-report`
**Status:** ✅ PRONTO

| Método | Endpoint | Descrição | Auth | Params | Frontend? |
|--------|----------|-----------|------|--------|-----------|
| GET | `/fiscal-report/{user_id}` | Relatório fiscal para PJ | ✅ Sim | - | ❌ Não |
| GET | `/fiscal-report/{user_id}/mixed-use` | Relatório de uso misto (PF+PJ) | ✅ Sim | - | ❌ Não |

---

## 18. PEERS (MX.4 - Comparação com Perfis Similares)
**Arquivo:** `backend/app/api/v1/routes/peers.py`
**Prefix:** `/peers`
**Status:** ✅ PRONTO

| Método | Endpoint | Descrição | Auth | Params | Frontend? |
|--------|----------|-----------|------|--------|-----------|
| GET | `/peers/compare/{user_id}` | Compara gastos com benchmarks IBGE/POF | ✅ Sim | - | ❌ Não |

---

## 19. SAFE-TO-SPEND (F1 - Gauge + Ritmo de Gastos)
**Arquivo:** `backend/app/api/v1/routes/safe_to_spend.py`
**Prefix:** `/safe-to-spend`
**Status:** ✅ PRONTO

| Método | Endpoint | Descrição | Auth | Params | Frontend? |
|--------|----------|-----------|------|--------|-----------|
| GET | `/safe-to-spend/{user_id}` | Orçamento mensal + gasto até hoje + risk | ✅ Sim | - | ✅ Sim |

**Response:**
```json
{
  "user_id": "user_123",
  "month": "2026-03",
  "safe_to_spend_total": 3000.00,
  "spent_to_date": 2401.25,
  "pct_consumed": 80.04,
  "safe_to_spend_daily": 36.00,
  "current_balance": 5000.00,
  "risk_level": "MEDIUM"
}
```

---

## 20. PURCHASE (F7 - Modo Compra Inteligente)
**Arquivo:** `backend/app/api/v1/routes/purchase.py`
**Prefix:** `/purchase`
**Status:** ✅ PRONTO

| Método | Endpoint | Descrição | Auth | Params | Frontend? |
|--------|----------|-----------|------|--------|-----------|
| POST | `/purchase/analyze` | Recomenda melhor forma de pagamento | ✅ Sim | PurchaseRequest (JSON) | ❌ Não |

**Compara:** PIX à vista, Cartão à vista, Parcelado, CDC

---

## 21. COSTS (F5 - Raio-X de Custos Bancários)
**Arquivo:** `backend/app/api/v1/routes/costs.py`
**Prefix:** `/costs`
**Status:** ✅ PRONTO

| Método | Endpoint | Descrição | Auth | Params | Frontend? |
|--------|----------|-----------|------|--------|-----------|
| GET | `/costs/raio-x/{user_id}` | Análise de custos bancários | ✅ Sim | - | ❌ Não |

---

## 22. NEGOTIATOR (F13 - Roteiro de Negociação)
**Arquivo:** `backend/app/api/v1/routes/negotiator.py`
**Prefix:** `/negotiator`
**Status:** ✅ PRONTO

| Método | Endpoint | Descrição | Auth | Params | Frontend? |
|--------|----------|-----------|------|--------|-----------|
| POST | `/negotiator/generate-script` | Gera roteiro de negociação | ✅ Sim | NegotiationRequest (JSON) | ❌ Não |

---

## 23. DASHBOARD (Endpoints Legados)
**Arquivo:** `backend/app/api/v1/routes/dashboard.py`
**Prefix:** `/dashboard`
**Status:** ⚠️ DEPRECIADO

| Método | Endpoint | Descrição | Auth | Params | Frontend? |
|--------|----------|-----------|------|--------|-----------|
| GET | `/dashboard/summary` | (Usar `/forecast/{user_id}` no lugar) | ✅ Sim | - | ❌ Não |
| GET | `/dashboard/safe-to-spend` | (Usar `/safe-to-spend/{user_id}` no lugar) | ✅ Sim | - | ❌ Não |

---

## 24. BANK SIMULATION & ANALYZE (Teste/Desenvolvimento)
**Arquivo:** `backend/app/api/v1/routes/bank_simulation.py`, `analyze.py`
**Status:** ⚠️ TESTE

---

## SUMÁRIO DE STATUS POR FUNCIONALIDADE

| # | Funcionalidade | Arquivo | Status | Db Queries | Persistência | Frontend |
|---|---|---|---|---|---|---|
| 1 | Auth/Login | auth.py | ✅ Pronto | ❌ TODO | ✅ Sim | ✅ Sim |
| 2 | Transações (ETL) | transactions.py | ✅ Pronto | ⚠️ Fallback | ✅ Sim | ⚠️ Partial |
| 3 | Forecast (F1) | forecast.py | ✅ Pronto | ⚠️ NexaRunner | ❌ Não | ✅ Sim |
| 4 | Pluggy (Open Finance) | pluggy.py | ✅ Pronto | ❌ SDK | ⚠️ Webhook | ✅ Sim |
| 5 | Shadow Invoice | shadow_invoice.py | ✅ Pronto | ⚠️ NexaRunner | ❌ Não | ❌ Não |
| 6 | Alerts | alerts.py | ✅ Pronto | ⚠️ NexaRunner | ❌ Não | ❌ Não |
| 7 | Reconnect | reconnect.py | ⚠️ Partial | ❌ TODO | ❌ TODO | ❌ Não |
| 8 | Context Override (F4) | context_override.py | ✅ Pronto | ⚠️ Fallback | ⚠️ Partial | ❌ Não |
| 9 | Architect (F3) | architect.py | ✅ Pronto | ⚠️ DuckDB | ✅ Sim | ❌ Não |
| 10 | Optimizer (F2) | optimizer.py | ✅ Pronto | ✅ Sim | ❌ Não | ❌ Não |
| 11 | Chat (Agent IA) | chat.py | ✅ Pronto | ❌ N/A | ❌ Não | ✅ Sim |
| 12 | Health Score (MX.1) | health_score.py | ✅ Pronto | ❌ N/A | ❌ Não | ❌ Não |
| 13 | Subscriptions (M1.5) | subscriptions.py | ✅ Pronto | ⚠️ NexaRunner | ❌ Não | ❌ Não |
| 14 | Goals (MX.2) | goals.py | ✅ Pronto | ⚠️ Fallback | ❌ Não | ✅ Sim |
| 15 | Budget (M1.3) | budget.py | ✅ Pronto | ⚠️ NexaRunner | ❌ Não | ✅ Sim |
| 16 | Notifications (MX.3) | notifications.py | ✅ Pronto | ⚠️ NexaRunner | ❌ Não | ❌ Não |
| 17 | Fiscal Report (M4.1) | fiscal_report.py | ✅ Pronto | ⚠️ NexaRunner | ❌ Não | ❌ Não |
| 18 | Peers (MX.4) | peers.py | ✅ Pronto | ⚠️ NexaRunner | ❌ Não | ❌ Não |
| 19 | Safe-to-Spend (F1) | safe_to_spend.py | ✅ Pronto | ⚠️ NexaRunner | ❌ Não | ✅ Sim |
| 20 | Purchase (F7) | purchase.py | ✅ Pronto | ❌ Sim | ❌ Não | ❌ Não |
| 21 | Costs (F5) | costs.py | ✅ Pronto | ⚠️ NexaRunner | ❌ Não | ❌ Não |
| 22 | Negotiator (F13) | negotiator.py | ✅ Pronto | ❌ N/A | ❌ Não | ❌ Não |

**Legenda:**
- ✅ Implementado/Pronto
- ⚠️ Parcial/Fallback
- ❌ Não implementado/TODO

---

## ARQUIVOS-CHAVE DO BACKEND

```
backend/
├── app/
│   ├── main.py                              ← App FastAPI principal
│   ├── api/v1/
│   │   ├── router.py                        ← Router consolidado (importa todos)
│   │   └── routes/                          ← Todos os 22 routers
│   ├── core/
│   │   ├── security.py                      ← JWT, OAuth2, autenticação
│   │   ├── config.py                        ← Configurações (env vars)
│   │   └── database.py                      ← SessionLocal, get_db()
│   ├── db/
│   │   ├── models.py                        ← ORM SQLAlchemy
│   │   ├── session.py                       ← Engine + Session
│   │   ├── users.py                         ← Queries de usuários
│   │   ├── queries.py                       ← Queries gerais
│   │   └── queries/
│   │       ├── architect_queries.py
│   │       └── optimizer_queries.py
│   ├── schemas/                             ← Pydantic models
│   │   ├── transaction.py
│   │   ├── shadow_invoice.py
│   │   └── ...
│   ├── etl/                                 ← Processamento de dados
│   │   ├── transaction_ingestor.py
│   │   ├── transaction_classifier.py
│   │   ├── income_profiler.py               ← MI.6
│   │   └── spending_anomaly_detector.py     ← MI.1
│   ├── agent/                               ← LangGraph Agent
│   │   ├── graph.py                         ← Build do agente
│   │   ├── state.py                         ← State da máquina
│   │   ├── nodes/                           ← Nós do grafo
│   │   └── tools/                           ← Ferramentas disponíveis
│   ├── architect/                           ← F3: Simulador
│   │   └── services/
│   ├── optimizer/                           ← F2: Otimização
│   │   └── services/
│   ├── purchase/                            ← F7: Compra Inteligente
│   │   └── purchase_advisor.py
│   ├── negotiator/                          ← F13: Negociação
│   ├── goals/                               ← MX.2: Metas
│   │   └── tracker.py
│   ├── integrations/
│   │   └── open_finance/
│   │       └── pluggy.py                    ← SDK Pluggy
│   └── runner.py                            ← NexaRunner (mock pipeline)
└── tests/
```

---

## DEPENDÊNCIAS NOS ENDPOINTS

```
Entrypoint: POST /auth/token → JWT Token
    ↓
GET /forecast/{user_id}
    ├→ GET /safe-to-spend/{user_id}
    ├→ GET /shadow_invoice/{user_id}
    ├→ GET /alerts/{user_id}
    └→ GET /transactions/{user_id}

POST /chat/ (Agent IA)
    ├→ Usa todas as ferramentas de dados acima
    └→ Retorna resposta em linguagem natural

POST /optimizer/analyze (F2)
    ├→ GET /transactions (classificadas)
    └→ Retorna recomendação de cartão

POST /architect/simulate (F3)
    ├→ GET /safe-to-spend (opcional para contexto)
    └→ Retorna simulação de estratégia

POST /purchase/analyze (F7)
    ├→ Recomendação de cartão (F2)
    └→ Retorna ranking de formas de pagamento

POST /transactions/webhook (ETL entry point)
    ├→ TransactionIngestor (limpeza)
    ├→ TransactionClassifier (categorização)
    └→ save_transactions_clean (Postgres)
```

---

## REQUISITOS POR ENDPOINT

### Autenticação (Auth)
- ❌ Sem autenticação (login não precisa de token)

### Endpoints Protegidos (maioria)
- ✅ Requer header: `Authorization: Bearer {access_token}`
- ✅ Extrai `user_id` do JWT

### Query Parameters Comuns
- `user_id`: ID único do usuário (geralmente no path)
- `days_ahead`: Quantos dias para frente projetar (padrão: 30)
- `months`: Quantos meses histórico (padrão: 6)
- `limit`: Quantidade máxima de registros

### Request Body (POST/PATCH)
- JSON com estrutura específica para cada endpoint (validado por Pydantic)

---

## INCOMPLETO / TODO

1. **Reconnect Callback**: Webhook real da Pluggy não implementado
2. **Persistência de Goals**: Salvar progressão de metas no Postgres (existe schema em TODO)
3. **Persistência de Contexto Override**: Salvar overrides no banco
4. **Persistência de Alerts**: Marcar alertas como lidos (DELETE não persiste)
5. **Bank Connections Manager**: Gerenciar tokens de expiry das conexões
6. **Historical Simulations**: Alguns endpoints dependem de DuckDB (não SQL)
7. **Real Pluggy Webhooks**: Webhook ingestão em produção precisa autenticação
8. **Frontend Integration**: Alguns endpoints ainda não têm integrações (marcados ⚠️)

---

## COMANDOS ÚTEIS PARA TESTAR

```bash
# Health checks
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/forecast

# Login
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test@email.com&password=senha123"

# Forecast (com token)
curl http://localhost:8000/api/v1/forecast/golden_user_777 \
  -H "Authorization: Bearer {token}"

# Transações
curl "http://localhost:8000/api/v1/transactions/golden_user_777?limit=50" \
  -H "Authorization: Bearer {token}"

# Safe-to-Spend
curl http://localhost:8000/api/v1/safe-to-spend/golden_user_777 \
  -H "Authorization: Bearer {token}"
```

---

## MODO DEVELOPMENT vs PRODUCTION

**Em DEV:**
- NexaRunner com mock data (duckdb finance.duckdb)
- Fallback automático quando banco não disponível
- Transações fake com padrões realistas

**Em PROD (TODO):**
- Queries reais ao Postgres
- Webhooks reais da Pluggy
- Rate limiting ativo
- Logs estruturados
- Autenticação 2FA
- Criptografia de dados sensíveis
