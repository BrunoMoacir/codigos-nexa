
# 🏗️ Nexa AI — Core Engine (Funcionalidade 1)
## Fluxo de Caixa, Previsão & Inteligência Ativa

> **Status:** MVP (Fase 1)  
> **Stack:** Python 3.11+, Polars, PyTorch, NeuralProphet, CatBoost, LangGraph  
> **Princípio Central:** *O dado oficial vem primeiro. Se falhar, o sistema se adapta.*  
> **Mantra:** **Matemática determinística calcula. IA generativa explica.**

---

## 🎯 Visão Geral

O Core Engine da Nexa é responsável por transformar transações bancárias em **decisões financeiras acionáveis**.  
Não somos um chatbot financeiro. Somos um **Agente Financeiro Autônomo**, capaz de prever cenários futuros mesmo quando dados bancários são incompletos ou instáveis.

O sistema foi desenhado desde o início para conviver com a realidade do Open Finance brasileiro.

---

## 🧠 Estratégia Central — *Shadow Invoice* (Fatura Sombra)

A Nexa sempre segue esta ordem de decisão:

### 🥇 1️⃣ Fonte Primária — Dados Oficiais do Banco
Sempre que disponíveis, utilizamos:
- Extrato bancário
- Transações confirmadas
- Fatura aberta / future invoice

Esses dados **têm prioridade absoluta**, desde que passem por validações internas de consistência.

---

### ⚠️ 2️⃣ Validação de Consistência
Antes de confiar no dado oficial, o Core Engine executa verificações como:
- Completude do período
- Coerência de datas e valores
- Histórico mínimo disponível
- Estabilidade conhecida da API da instituição

Se qualquer regra crítica falhar, o dado é marcado como **UNTRUSTED**.

---

### 🥈 3️⃣ Fallback Inteligente — *Shadow Invoice*
Quando o dado oficial:
- Não existe  
- Está incompleto  
- Está inconsistente  
- Ou a API do banco é instável  

A Nexa ativa automaticamente a **Shadow Invoice**.

> **Shadow Invoice é uma projeção matemática da fatura futura, calculada localmente a partir do histórico real do usuário.**

O usuário nunca fica sem resposta.

---

## 🔍 Como a Shadow Invoice é Calculada

A projeção se baseia em três padrões matematicamente detectáveis:

### 1️⃣ Parcelamentos (A Chave de Ouro)
Detectamos padrões explícitos como:
- `01/10`
- `1/10`
- `01 de 10`

Exemplo:
```

MAGALU *COMPRA 01/10 → MAGALU *COMPRA 02/10

````

O sistema projeta automaticamente a próxima parcela, mantendo:
- Merchant
- Valor
- Dia aproximado do mês

📌 Sem PDF. Sem OCR. 100% determinístico.

---

### 2️⃣ Assinaturas Recorrentes
Identificamos recorrências quando:
- Mesmo merchant
- Frequência mensal
- Baixa variação de data (desvio < 4 dias)
- Presença em ≥ 3 meses

O Nexa cria uma **linha virtual futura** na data correta.

---

### 3️⃣ Gastos Variáveis (Colchão de Liquidez)
Para categorias variáveis (Uber, Mercado, Lazer):
- Média móvel dos últimos 60–90 dias
- Ajuste por sazonalidade
- Percentil de segurança (p50 / p70)

Isso evita subestimar a fatura futura.

---

## 🧩 Estratégia por Banco (Design Pattern: Strategy)

Cada instituição financeira possui um **adaptador próprio**, que define o nível de confiança nos dados oficiais.

```python
class BankStrategy:
    def predict_invoice(self, history, api_data):
        raise NotImplementedError


class NubankStrategy(BankStrategy):
    def predict_invoice(self, history, api_data):
        if api_data and api_data.is_consistent():
            return api_data
        return project_from_history(history)


class BradescoStrategy(BankStrategy):
    def predict_invoice(self, history, api_data):
        return project_from_history(history)
````

Essa abordagem evita `if/else` espalhados pelo código e permite tuning fino por banco.

---

## 🧠 Funcionalidades Ativas Geradas pelo Core Engine

Essas funcionalidades **não são módulos separados**.
Elas são **saídas diretas do mesmo motor de previsão**.

---

### 💰 Quanto Posso Gastar Hoje? (*Safe-to-Spend*)

**Pergunta respondida:**

> *“Quanto posso gastar hoje sem comprometer meu mês?”*

Cálculo diário baseado em:

* Saldo atual
* Despesas futuras previstas (recorrências + Shadow Invoice)
* Margem de segurança

```
Safe-to-Spend = Saldo Atual − (Despesas Previstas + Margem)
```

---

### 🧾 Resumo Semanal dos Gastos

**Pergunta respondida:**

> *“O que mudou no meu financeiro essa semana?”*

Geração automática com:

* Total gasto vs semana anterior
* Principais categorias
* Gastos fora do padrão
* Impacto no fluxo de caixa futuro

Exemplo:

> “Você gastou 12% mais esta semana.
> Isso reduz seu Safe-to-Spend da próxima semana em R$ 180.”

---

### 🕳️ Identificação de Gastos Invisíveis

**Pergunta respondida:**

> *“Para onde meu dinheiro está vazando sem eu perceber?”*

O sistema detecta:

* Pequenos valores recorrentes
* Assinaturas esquecidas
* Parcelamentos antigos ainda ativos
* Vazamentos financeiros de baixo valor unitário, mas alto impacto acumulado

---

## 🚨 Expiração de Token & Resiliência

Se a conexão Open Finance expirar:

* **T-30:** aviso preventivo
* **T-7:** alerta crítico
* **T-0:** sistema entra em modo Shadow Invoice com aviso explícito

O sistema nunca para. Apenas reduz o nível de certeza e comunica isso claramente.

---

## 🧠 Regras de Ouro do Core Engine

1. O dado oficial sempre vem primeiro
2. Se o dado falhar, a matemática assume
3. Nenhum número é inventado
4. Toda previsão possui impacto mensurável
5. IA explica — nunca calcula

---

## 🧾 Resumo Executivo

> **A Nexa não mostra apenas gráficos.
> Ela responde perguntas reais:
> quanto posso gastar, o que mudou e onde estou perdendo dinheiro.
> Sempre — mesmo quando o banco falha.**

```
```
## 🔌 APIs & Webhooks — Funcionalidade 1 (Nexa Core Engine)

> **Objetivo:** centralizar ingestão, normalização e projeção de dados financeiros (transações, saldos, faturas projetadas) para alimentar os módulos superiores (**Optimizer, Architect, Agent**).  
> **Princípio:** salvar `raw_events` imediatamente; processamento secundário com **Polars**; preservar **audit trail** (`data_source`, `version`, `fetched_at`).

---

## 1️⃣ APIs Externas (Connectors)

### 1.1 Pluggy / Belvo / SaltEdge (Open Finance Connectors)

**Uso:** ingestão de contas, transações, saldos, cartões e metadados de consentimento.

#### Campos relevantes (normalizados para `raw_events`)
- `item_id` / `user_id` / `institution_id`
- `accounts[]` → `{ account_id, account_type, currency, number_masked }`
- `transactions[]` → `{ transaction_id, date, amount, description, status }`  
  **status:** `POSTED` | `PENDING`
- `balances` → `{ available, current, blocked }`
- `cards` → `{ card_id, last_four, credit_limit, closing_date, due_date }` *(quando disponível)*
- `future_invoice` → `{ closing_date, due_date, invoice_amount }`  
  *(usar apenas se `validated_consistent = true`)*
- `consent` → `{ consent_id, consent_expires_at, status }`

#### Observações práticas
- Tratar **Webhook (push)** + **Polling (fallback)**.
- Salvar **JSON cru** em `raw_events` com metadata:  
  `{ source, fetched_at, item_version }`.
- Mapear `institution_id` → `bank_trust_score` (heurística).

---

## 2️⃣ Endpoints Internos (expostos pelo Core)

> **Autenticação:** todas as APIs internas requerem **API Key / JWT**.  
> **Segurança de Webhooks:** validar assinatura **HMAC** (se disponível) ou token no header.

---

### 2.1 `POST /webhook/transaction`

Recebe webhooks dos conectores (Pluggy/Belvo). **Idempotente.**

**Headers**
X-Signature: <hmac>
X-Source: pluggy | belvo

**Body (exemplo abstrato)**
```json
{
  "item_id": "item_abc",
  "institution_id": "itau",
  "raw_payload": {},
  "received_at": "2025-01-20T10:00:00Z",
  "webhook_type": "transactions.updated"
}
Comportamento
Persistir em raw_events (audit trail).
Enfileirar job assíncrono para o ingestor.
Resposta: 204 No Content.
2.2 GET /transactions/{user_id}?start=YYYY-MM-DD&end=YYYY-MM-DD
Retorna transações normalizadas (UI / debug).
Response (exemplo)

{
  "user_id": "u_123",
  "transactions": [
    {
      "transaction_id": "t_abc",
      "date": "2025-01-10",
      "amount": -100.0,
      "description_raw": "MAGALU *COMPRA 01/10",
      "merchant_clean": "Magalu",
      "category": "Compras",
      "status": "POSTED",
      "is_recurring": true,
      "is_parcel": true
    }
  ]
}
2.3 GET /forecast/{user_id}?horizon_days=30
Retorna daily_forecast (D+1..D+n).
Response (exemplo)

{
  "user_id": "u_123",
  "generated_at": "2025-01-25T12:00:00Z",
  "horizon_days": 30,
  "daily": [
    {
      "date": "2025-01-26",
      "balance": 1200.0,
      "events": [
        {
          "type": "recurrence",
          "merchant": "NETFLIX",
          "amount": -21.9,
          "source": "shadow_invoice"
        },
        {
          "type": "transaction",
          "merchant": "SALARIO",
          "amount": 3000,
          "source": "transactions_clean"
        }
      ]
    }
  ],
  "sources": ["shadow_invoice", "prophet", "transactions_clean"]
}
Notas
Cada evento possui source (audit trail).
Forecast inclui min / max / expected se confidence for baixa.
2.4 GET /shadow_invoice/{user_id}
Retorna eventos projetados da Fatura Sombra.
Response (exemplo)

{
  "user_id": "u_123",
  "shadow_invoice_events": [
    {
      "date": "2025-02-05",
      "merchant": "MAGALU",
      "amount": -100.0,
      "type": "parcel",
      "origin": "detected_parcel_01/10"
    }
  ],
  "generated_at": "2025-01-25T12:00:00Z"
}
2.5 GET /safe_to_spend/{user_id}
Retorna cálculo de Safe-to-Spend.
Response

{
  "user_id": "u_123",
  "safe_to_spend": 720.0,
  "components": {
    "current_balance": 1500.0,
    "predicted_outflows_next_30_days": 600.0,
    "margin": 180.0
  },
  "generated_at": "2025-01-25T12:00:00Z"
}
2.6 GET /alerts/{user_id}
Retorna alertas ativos (inclui T-30 / T-7 / T-0 de consentimento).
Exemplo

[
  {
    "id": "a_1",
    "type": "token_expiry",
    "level": "warning",
    "message": "Conexão vence em 30 dias",
    "due_date": "2025-02-24"
  }
]
2.7 POST /reconnect/{user_id}
Dispara fluxo de reconexão (gera connect_url Pluggy/Belvo).
3️⃣ Artefatos Internos (Persistidos)
raw_events — JSON cru (audit trail)
transactions_clean — tabela Polars normalizada
shadow_invoice_events — parcelas e assinaturas futuras
daily_forecast — série diária D+1..D+N
alerts — consentimento + previsão negativa
items — { item_id, institution_id, consent_expires_at, status, last_sync_at, bank_trust_score }
4️⃣ Fluxo Recomendado / Boas Práticas
Salvar raw_events imediatamente → responder 204.
Processamento assíncrono:
ingestor
classifier
detector de recorrência
forecaster
Idempotência: item_id + event_id ou idempotency_key.
Observability: logs estruturados (trace_id, user_id, item_id).
Retries & Backoff: polling com fallback (Shadow Invoice).
Segurança: PII criptografado at-rest; mascarar antes de LLMs.
Token expiry: jobs T-30 / T-7 / T-0.
5️⃣ Integração Pluggy / Belvo — Campos Úteis
Campos típicos:
item.id
institution.id
accounts
transactions
cards
balances
consent.expires_at
Normalização obrigatória
date → YYYY-MM-DD
amount → Float
description_raw → texto original
Recomendação
Criar adaptadores:
connectors/pluggy.py
connectors/belvo.py
Retornando:
{ "source", "fetched_at", "item_version", "trust_score" }
6️⃣ Idempotência & Versionamento
Cada processamento grava item_version (hash do payload).
Jobs detectam diffs entre versões para evitar reprocessamento total.
7️⃣ Observability & Health
Dashboards
Sync success rate por instituição
Latência média do ingestor
Erros por regra de classificação
% de itens UNTRUSTED
Alertas Operacionais
Falha de ingestão > X minutos
Aumento de error rate em conectores externos
8️⃣ Requisitos de Implantação
Queue: Redis / Rabbit / Kafka
Workers: pipelines Polars
DB: Postgres (metadata) + Object Storage (raw_events)
Secrets: Vault (rotação periódica)
Retention
raw_events: 1 ano (configurável)
transactions_clean: 5 anos
9️⃣ Fluxo End-to-End (Resumo)
Webhook transactions.updated → /webhook/transaction
Worker processa → transactions_clean
Detector encontra parcela 01/10 → shadow_invoice_event
Forecaster gera daily_forecast
Sentinel cria alerta (se aplicável)
/forecast/{user_id} retorna forecast auditável
✅ Resumo Rápido
Fonte primária: Open Finance (Pluggy / Belvo)
Sempre: salvar raw, versionar e auditar
Endpoints-chave:
/webhook/transaction
/forecast/{user_id}
/shadow_invoice/{user_id}
/safe_to_spend/{user_id}
/alerts/{user_id}
/reconnect/{user_id}
Princípios: idempotência, audit trail, fallback (Shadow Invoice) e alertas T-30/T-7/T-0
