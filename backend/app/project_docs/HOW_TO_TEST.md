# 📚 GUIA DE TESTE: NOVOS ENDPOINTS CORE ENGINE

## ✅ Status

Todos os **5 novos endpoints** estão criados, documentados e testados:

```
✅ GET  /api/v1/forecast/{user_id}              Previsão consolidada
✅ GET  /api/v1/shadow_invoice/{user_id}        Obrigações futuras  
✅ GET  /api/v1/shadow_invoice/{user_id}/summary Resumo de obrigações
✅ GET  /api/v1/alerts/{user_id}                Alertas ativos
✅ POST /api/v1/reconnect/{user_id}             Gerar URL de reconexão
```

---

## 🚀 Como Testar

### Pré-requisito: Servidor rodando

```bash
cd backend
uvicorn app.main:app --port 8000 --reload
```

Deve aparecer:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

### Opção 1: Usar Swagger UI (Recomendado)

Abra no navegador:

```
http://localhost:8000/docs
```

**O que você verá:**
- Lista de todos os endpoints
- Descrição detalhada de cada um
- Parâmetros aceitos
- Exemplos de response
- **Botão "Try it out"** para testar interativamente

**Passo a passo:**
1. Clique em um endpoint (ex: `GET /api/v1/forecast/{user_id}`)
2. Clique em "Try it out"
3. Preencha `user_id` = `test_user_123`
4. Clique "Execute"
5. Veja a resposta em JSON

---

### Opção 2: Linha de Comando (Python)

Script de teste automático:

```bash
cd backend
python test_api.py
```

**Saída esperada:**
```
======================================================================
[TESTE] Novos Endpoints - Core Engine
======================================================================

[1] HEALTH CHECKS
----------------------------------------------------------------------
OK  forecast             -> 200
OK  shadow_invoice       -> 200
OK  alerts               -> 200
OK  reconnect            -> 200

[2] GET /forecast/{user_id}
----------------------------------------------------------------------
...
```

---

### Opção 3: cURL (Linha de Comando)

#### 1. **Forecast (Previsão)**
```bash
curl -X GET "http://localhost:8000/api/v1/forecast/test_user_123" \
  -H "accept: application/json"
```

**Resposta:**
```json
{
  "user_id": "test_user_123",
  "generated_at": "2025-02-11T15:30:00Z",
  "financial_health": {
    "profile_type": "EQUILIBRADO",
    "health_score": 75
  },
  "safe_to_spend": {
    "current_balance": 5000.0,
    "safe_to_spend_daily": 120.32
  },
  "shadow_invoices": {
    "total_count": 12,
    "total_monthly_impact": -1068.10
  }
}
```

---

#### 2. **Shadow Invoices (Obrigações Futuras)**
```bash
curl -X GET "http://localhost:8000/api/v1/shadow_invoice/test_user_123" \
  -H "accept: application/json"
```

**Resposta:**
```json
{
  "invoices": [
    {
      "date": "2025-02-15",
      "merchant": "NETFLIX",
      "amount": -21.90,
      "type": "subscription",
      "confidence": 0.99
    }
  ],
  "total_count": 12,
  "total_monthly_impact": -1068.10,
  "subscriptions_count": 9,
  "installments_count": 3
}
```

---

#### 3. **Shadow Invoice Summary**
```bash
curl -X GET "http://localhost:8000/api/v1/shadow_invoice/test_user_123/summary" \
  -H "accept: application/json"
```

**Resposta:**
```json
{
  "total_monthly_committed": -1068.10,
  "total_count": 12,
  "subscriptions": 9,
  "installments": 3,
  "date_generated": "2025-02-11T15:30:00Z"
}
```

---

#### 4. **Alerts (Avisos)**
```bash
curl -X GET "http://localhost:8000/api/v1/alerts/test_user_123" \
  -H "accept: application/json"
```

**Resposta:**
```json
{
  "user_id": "test_user_123",
  "alerts": [
    {
      "id": "token_expiry_30d",
      "type": "TOKEN_EXPIRY",
      "level": "WARNING",
      "title": "Conexão vence em 30 dias",
      "message": "Sua conexão vencerá em 30 dias...",
      "due_date": "2025-03-13T15:30:00Z",
      "action_url": "/api/v1/reconnect"
    }
  ],
  "total_count": 1,
  "critical_count": 0,
  "warning_count": 1,
  "generated_at": "2025-02-11T15:30:00Z"
}
```

---

#### 5. **Reconnect (Gerar URL de Reconexão)**
```bash
curl -X POST "http://localhost:8000/api/v1/reconnect/test_user_123" \
  -H "Content-Type: application/json" \
  -d '{"redirect_uri": "http://localhost:3000/dashboard"}'
```

**Resposta:**
```json
{
  "user_id": "test_user_123",
  "connect_url": "https://pluggy.io/open-finance/connections/abc123xyz",
  "expires_at": "2025-02-12T15:30:00Z",
  "redirect_back_uri": "http://localhost:3000/dashboard"
}
```

---

### Opção 4: Postman

1. **Abra Postman**
2. **Importe collection:**
   - Vá em `File → Import`
   - Cole a URL: `http://localhost:8000/openapi.json`
   
3. **Ou crie manualmente:**
   - Novo request
   - Método: `GET`
   - URL: `http://localhost:8000/api/v1/forecast/test_user_123`
   - Click "Send"

---

## 📋 Detalhes de Cada Endpoint

### 1️⃣ GET /forecast/{user_id}

**Propósito:** Retorna previsão consolidada (cashflow, safe-to-spend, shadow invoices)

**Parâmetros:**
| Nome | Tipo | Obrigatório | Descrição |
|------|------|-----------|-----------|
| `user_id` | string | Sim | ID único do usuário |
| `horizon_days` | integer | Não | Dias para projetar (padrão: 30) |

**O que retorna:**
- Previsão financeira completa
- Análise de saúde (score + perfil)
- Safe-to-spend (quanto pode gastar hoje)
- Shadow invoices (12 próximos meses)
- Risk assessment

**Tempo de resposta:** 10-20 segundos (processa ETL)

---

### 2️⃣ GET /shadow_invoice/{user_id}

**Propósito:** Apenas as obrigações futuras detectadas

**Parâmetros:**
| Nome | Tipo | Obrigatório |
|------|------|-----------|
| `user_id` | string | Sim |
| `days_ahead` | integer | Não (padrão: 60) |

**O que retorna:**
- Lista de shadow invoices (parcelamentos, assinaturas)
- Total mensal impactado
- Contagem de cada tipo

**Tempo de resposta:** 5-10 segundos

---

### 3️⃣ GET /shadow_invoice/{user_id}/summary

**Propósito:** Resumo rápido (sem detalhes)

**Retorna:**
- Apenas números (sem lista de items)
- Ideal para dashboards que querem só o resumo

**Tempo de resposta:** Instant (dados em cache)

---

### 4️⃣ GET /alerts/{user_id}

**Propósito:** Avisos financeiros ativos

**O que detecta:**
- ⏰ Token expiry (T-30, T-7, T-0)
- ⛔ Saldo vai ficar negativo
- ⚠️ Caixa muito comprometido (> 80%)

**Retorna:**
- Lista de alertas com severidade
- URL para ação (ex: /reconnect)

**Tempo de resposta:** Instant

---

### 5️⃣ POST /reconnect/{user_id}

**Propósito:** Gerar URL para reconectar consentimento

**Body (JSON):**
```json
{
  "redirect_uri": "http://localhost:3000/dashboard"
}
```

**O que retorna:**
- `connect_url` → URL para usuário clicar
- `expires_at` → Quando URL expira (24h)
- `redirect_back_uri` → Onde Pluggy redireciona

**Fluxo:**
1. Frontend recebe `connect_url`
2. Redireciona usuário: `window.location.href = connect_url`
3. Usuário conecta no Pluggy
4. Pluggy redireciona para `redirect_back_uri`
5. Dados começam a fluir novamente

**Tempo de resposta:** < 1 segundo

---

## 🔧 Troubleshooting

### ❌ "Connection refused" (Porta 8000)

**Solução:**
```bash
# Verificar se server está rodando
lsof -i :8000  # Mac/Linux
netstat -ano | findstr :8000  # Windows

# Matar processo na porta (se necessário)
kill -9 <PID>  # Mac/Linux
taskkill /PID <PID> /F  # Windows

# Recomeçar
uvicorn app.main:app --port 8000
```

---

### ❌ "404 Not Found"

**Causas possíveis:**
- URL mal escrita (verificar `/api/v1/` no início)
- Servidor não iniciou
- Rota não foi registrada

**Solução:**
```bash
# Verificar que app carregou
curl http://localhost:8000/docs

# Se retornar HTML com Swagger, está ok
```

---

### ❌ "500 Internal Server Error"

**Causas possíveis:**
- Database offline
- Dados inválidos
- Dependências faltando

**Solução:**
```bash
# Verificar logs do servidor
# (error estará no terminal onde uvicorn rodando)

# Reinstalar dependências
pip install -r requirements.txt

# Rodar testes
pytest tests/
```

---

### ⚠️ Endpoints retornam {}

**Causa:** user_id não existe no banco

**Solução:**
- Use user_id real (vai ser criado quando usuário se conectar via Open Finance)
- Ou use dados mock (NexaRunner com mode="dev")

---

## 📊 Arquitetura Visual

```
┌──────────────────────────────────────────────────┐
│         Frontend/Cliente                          │
└─────────────────────┬──────────────────────────────┘
                      │ HTTP/REST
              ┌───────▼────────┐
              │   FastAPI      │
              │ app.main:app   │
              └───────┬────────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
   ┌────▼────┐  ┌──────▼──┐  ┌─────▼──────┐
   │ forecast │  │  shadow │  │  alerts    │
   │  .py     │  │ invoice │  │   .py      │
   │          │  │  .py    │  │            │
   └────┬─────┘  └───┬─────┘  └─────┬──────┘
        │             │              │
        └─────────────┼──────────────┘
                      │
        ┌─────────────▼─────────────┐
        │    NexaRunner (ETL)       │
        │ (run_shadow, forecast,    │
        │  safe_to_spend, etc)      │
        └───────────────────────────┘
```

---

## 🎯 Próximos Passos

### ✅ Feito
- [x] 5 novos endpoints criados
- [x] Bem documentados (docstrings)
- [x] Testes iniciais
- [x] Swagger documentação automática
- [x] Tratamento de erros

### 🔄 Em Progresso
- [ ] Corrigir schemas de validação
- [ ] Integração com Postgres (persistência)
- [ ] Testes mais robustos
- [ ] Rate limiting

### ⏳ Futuro
- [ ] Funcionalidade 2 (Optimizer - Cartões)
- [ ] Funcionalidade 3 (Architect - Simulador)
- [ ] Agent (LangGraph)
- [ ] WebSocket (real-time)

---

## 📞 Suporte

**Dúvidas?**
- Verificar docstring no código (bem comentado)
- Ver exemplo no test_api.py
- Abrir Swagger em http://localhost:8000/docs
- Checar logs do servidor (stderr/stdout)
