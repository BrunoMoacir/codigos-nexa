# 📊 DOCUMENTAÇÃO COMPLETA: ENDPOINTS FASTAPI NEXA

> **Status:** ✅ COMPLETO | **Data:** 2025-03-20 | **Cobertura:** 35+ endpoints, 20+ routers, 15+ funcionalidades prontas

---

## 📋 ARQUIVOS DE DOCUMENTAÇÃO GERADOS

### 1. **ENDPOINTS_TABLE.txt** (38 KB) ⭐ COMECE AQUI
Tabela completa com todos 35+ endpoints em formato visual:
- **Colunas:** ID | ENDPOINT | DESCRIÇÃO | REQUISITOS | STATUS | FRONTEND?
- **Inclui:** Legenda, sumário de status, mapeamento de funcionalidades
- **Use para:** Referência rápida, busca visual
- **Tempo de leitura:** 10-15 min
```
📁 /home/bruno/Área de trabalho/nexa/codigos-nexa.worktrees/.../ENDPOINTS_TABLE.txt
```

### 2. **ENDPOINTS_SUMMARY.md** (23 KB) 📖 LEITURA PROFUNDA
Documentação detalhada em Markdown:
- **Seções:** 22+ (uma por router/funcionalidade)
- **Por endpoint:** Descrição, auth, parâmetros, response examples, frontend status
- **Inclui:** Fluxos de dependência, comandos curl, modo dev/prod
- **Use para:** Entender funcionamento completo, integração
- **Tempo de leitura:** 30-40 min
```
📁 /home/bruno/Área de trabalho/nexa/codigos-nexa.worktrees/.../ENDPOINTS_SUMMARY.md
```

### 3. **ARQUIVOS_CHAVE.txt** (17 KB) 🗂️ NAVEGAÇÃO CODEBASE
Mapeamento de arquivos-chave do backend:
- **Blocos:** 8 categorias principais (Entrypoint, Auth, DB, ETL, Agent IA, etc)
- **Por arquivo:** Path, linhas de código, responsabilidades, classes principais
- **Inclui:** Fluxo de chamadas, dependências
- **Use para:** Navegar código, entender arquitetura, encontrar onde editar
- **Tempo de leitura:** 20-25 min
```
📁 /home/bruno/Área de trabalho/nexa/codigos-nexa.worktrees/.../ARQUIVOS_CHAVE.txt
```

---

## 🎯 SUMÁRIO EXECUTIVO

### Endpoints Levantados
- **Total:** 35+ endpoints funcionais
- **Routers:** 20+ (auth, transactions, forecast, pluggy, alerts, architect, optimizer, chat, goals, etc)
- **Métodos:** GET, POST, PUT, DELETE, PATCH

### Funcionalidades Prontas ✅
```
F1 Core     : Forecast, Safe-to-Spend, Shadow Invoice, Alerts, Transactions
F2 Otimiz.  : Optimizer (recomendação cartão)
F3 Simulador: Architect (Financiamento vs Consórcio vs Poupar)
F4 Divider  : Context Override (PF/PJ)
F5-13       : Costs, Purchase, Negotiator
MX.1-4      : Health Score, Goals, Notifications, Peers
M1.3-M4.1   : Budget, Subscriptions, Fiscal Report
🤖 Agent    : Chat com LangGraph (15+ ferramentas)
```

### Funcionalidades Incompletas ⚠️
- Reconnect Callback (webhook real não integrado)
- Goals Persistence (não salva em Postgres)
- Context Override Persistence
- Bank Connection Manager

### Usado no Frontend ✅
```
Integrado (app.py Streamlit):
- POST /auth/token, /auth/register
- POST /pluggy/connect-token, GET /pluggy/items, POST /pluggy/sandbox
- GET /forecast/{user_id}, /safe-to-spend/{user_id}
- GET /goals/{user_id}, /budget/{user_id}
- POST /chat/
```

---

## 🔍 COMO USAR ESTA DOCUMENTAÇÃO

### Caso 1: "Quero saber todos os endpoints rápido" (5 min)
```
1. Abra: ENDPOINTS_TABLE.txt
2. Procure por: Ctrl+F seu endpoint
3. Veja: Status, requisitos, se está no frontend
```

### Caso 2: "Preciso integrar um endpoint novo no frontend" (20 min)
```
1. Leia: ENDPOINTS_SUMMARY.md (seção do seu endpoint)
2. Veja: Exemplo JSON, autenticação, parâmetros
3. Use: Padrão NexaAPIClient (frontend/utils/api.py)
4. Teste: Comando curl fornecido
```

### Caso 3: "Vou editar o código backend" (30 min)
```
1. Consulte: ARQUIVOS_CHAVE.txt (mapa de arquivos)
2. Encontre: Arquivo que precisa editar
3. Leia: Estrutura, classes, responsabilidades
4. Siga: Fluxo de chamadas para entender contexto
```

### Caso 4: "Quero testar um endpoint" (10 min)
```
1. Encontre em: ENDPOINTS_SUMMARY.md
2. Procure por: "Comandos úteis" ou exemplos curl
3. Rode: curl conforme exemplo
4. Veja: Response JSON esperado
```

---

## 📊 TABELA RESUMIDA: 35+ ENDPOINTS

| # | Categoria | Endpoint | Status | Frontend |
|---|-----------|----------|--------|----------|
| 1-2 | Auth | `/auth/{register,token}` | ✅ | ✅ |
| 3-4 | Transações | `/transactions/{webhook,{user_id}}` | ✅ | ⚠️ |
| 5 | Forecast | `/forecast/{user_id}` | ✅ | ✅ |
| 6-8 | Pluggy | `/pluggy/{connect-token,items,sandbox}` | ✅ | ✅ |
| 9-11 | Shadow Invoice | `/shadow_invoice/{user_id,summary,health}` | ✅ | ❌ |
| 12-14 | Alerts | `/alerts/{user_id,dismiss,health}` | ✅ | ❌ |
| 15-17 | Reconnect | `/reconnect/{user_id,callback,health}` | ⚠️ | ❌ |
| 18-20 | Context Override | `/context/{override,overrides,stats}` | ✅ | ❌ |
| 21-25 | Architect F3 | `/architect/{simulate,simulations,metrics,health}` | ✅ | ❌ |
| 26-32 | Optimizer F2 | `/optimizer/{analyze,cards,reports,roi,portfolio}` | ✅ | ❌ |
| 33 | Chat IA | `/chat/` | ✅ | ✅ |
| 34-38 | Goals MX.2 | `/goals/{create,list,detail,progress,delete}` | ✅ | ✅ |
| 39 | Budget M1.3 | `/budget/{user_id}` | ✅ | ✅ |
| 40 | Health MX.1 | `/health-score/history/{user_id}` | ✅ | ❌ |
| 41 | Subscriptions M1.5 | `/subscriptions/{user_id}` | ✅ | ❌ |
| 42 | Notifications MX.3 | `/notifications/{user_id}` | ✅ | ❌ |
| 43-44 | Fiscal M4.1 | `/fiscal-report/{user_id,mixed-use}` | ✅ | ❌ |
| 45 | Peers MX.4 | `/peers/compare/{user_id}` | ✅ | ❌ |
| 46 | Safe-to-Spend | `/safe-to-spend/{user_id}` | ✅ | ✅ |
| 47 | Purchase F7 | `/purchase/analyze` | ✅ | ❌ |
| 48 | Costs F5 | `/costs/raio-x/{user_id}` | ✅ | ❌ |
| 49 | Negotiator F13 | `/negotiator/generate-script` | ✅ | ❌ |

**Legenda:** ✅ = Pronto | ⚠️ = Parcial/Mock | ❌ = Não integrado

---

## 🔧 ARQUIVOS-CHAVE

### Entrypoint Central
```
backend/app/api/v1/router.py ⭐
└─ Consolida TODOS os 20+ routers em um ponto
└─ Arquivo para procurar ao adicionar novo endpoint
```

### Pipeline Core (ETL)
```
backend/app/runner.py                          ← Mock pipeline (NexaRunner)
backend/app/etl/
├─ transaction_ingestor.py                     ← Limpeza de dados
├─ transaction_classifier.py                   ← Categorização (ML)
├─ income_profiler.py                          ← Detecção de renda (MI.6)
├─ spending_anomaly_detector.py                ← Anomalias (MI.1)
└─ shadow_invoice_detector.py                  ← Obrigações futuras
```

### Funcionalidades Principais
```
backend/app/architect/                         ← F3: Simulador
backend/app/optimizer/                         ← F2: Otimização cartões
backend/app/purchase/purchase_advisor.py       ← F7: Compra Inteligente
backend/app/negotiator/                        ← F13: Negociação
backend/app/goals/tracker.py                   ← MX.2: Metas
backend/app/agent/graph.py                     ← LangGraph Agent IA
backend/app/integrations/open_finance/pluggy.py ← Open Finance
```

### Banco de Dados
```
backend/app/db/
├─ models.py                                   ← ORM SQLAlchemy
├─ queries.py                                  ← Queries principais
├─ users.py                                    ← User management
└─ queries/*.py                                ← Queries específicas (Architect, Optimizer)
```

---

## 🚀 PRÓXIMAS AÇÕES

### Esta Semana (Urgente)
- [ ] Implementar persistência de Goals
- [ ] Testar todos endpoints com curl script
- [ ] Integrar endpoints faltantes no frontend

### Próximas 2 Semanas (Importante)
- [ ] Webhook real Pluggy para reconexão
- [ ] Banco connection manager
- [ ] Context override persistence

### Próximas 4 Semanas (Nice-to-Have)
- [ ] Migrar queries de NexaRunner para SQL puro
- [ ] Adicionar 2FA
- [ ] Testes E2E completos

---

## 💻 EXEMPLOS RÁPIDOS

### Login
```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test@email.com&password=senha123"
```

### Forecast
```bash
curl http://localhost:8000/api/v1/forecast/golden_user_777 \
  -H "Authorization: Bearer {token}"
```

### Chat com Agent IA
```bash
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "golden_user_777", "message": "Como está meu orçamento?"}'
```

---

## 📞 PRECISA DE AJUDA?

1. **Endpoint específico:** Busque em ENDPOINTS_TABLE.txt
2. **Entender fluxo:** Leia ENDPOINTS_SUMMARY.md
3. **Editar código:** Use ARQUIVOS_CHAVE.txt como mapa
4. **Testar:** Use exemplos curl em ENDPOINTS_SUMMARY.md

---

## ✨ INFORMAÇÕES

- **Versão:** 1.0
- **Data:** 2025-03-20T17:34:00Z
- **Cobertura:** 35+ endpoints, 20+ routers
- **Status:** COMPLETO ✅
- **Próxima revisão:** Quando novos endpoints forem adicionados

---

**Bom desenvolvimento! 🚀**
