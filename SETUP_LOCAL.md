# 🚀 Setup Local da Nexa (Sem Docker)

Este guia descreve como rodar a Nexa **localmente** sem precisar de Postgres/Docker, usando o **fallback automático para DuckDB**.

## ✅ Requisitos

- Python 3.12+
- `venv` (virtual environment)
- Dependências listadas em `backend/requirements.txt` e `frontend/requirements.txt`

## 🏃 Início Rápido (3 passos)

### 1️⃣ Ativar o Virtual Environment

```bash
cd /home/bruno/Área\ de\ trabalho/nexa/codigos-nexa.worktrees/copilot-worktree-2026-03-20T20-00-43

source venv/bin/activate
```

### 2️⃣ Rodar Backend (Uvicorn)

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Você verá:
```
[Agent] OPENAI_API_KEY não configurada! (expected)
INFO:     Started server process [...]
INFO:     Uvicorn running on http://0.0.0.0:8000
```

✅ Backend OK! Teste:
```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

### 3️⃣ Rodar Frontend (Streamlit)

Em **outro terminal**:

```bash
cd /home/bruno/Área\ de\ trabalho/nexa/codigos-nexa.worktrees/copilot-worktree-2026-03-20T20-00-43

source venv/bin/activate

cd frontend

streamlit run app.py
```

Frontend abre em `http://localhost:8501`

---

## 🔐 Login

Na tela inicial, use:

### Criar conta nova:
- **E-mail**: qualquer e-mail (ex: `seu-email@example.com`)
- **Senha**: mínimo 6 caracteres
- **Nome**: seu nome

### Ou use conta de teste:
- **E-mail**: `test@nexa.local`
- **Senha**: `test123`

---

## 🎯 Testar Endpoints

Após fazer login, acesse **✨ Funcionalidades** (primeira página no sidebar).

Lá você encontra:

| Aba | Endpoint | O que testa |
|-----|----------|-----------|
| 📊 **Transações** | `GET /api/v1/transactions/{user_id}` | Lista transações com fallback DuckDB |
| 💰 **Forecast** | `GET /api/v1/forecast/{user_id}` | Previsão financeira (cashflow, shadow invoices) |
| 🎯 **Metas** | `GET /api/v1/goals/{user_id}` | Metas financeiras do usuário |
| 💳 **Orçamento** | `GET /api/v1/budget/{user_id}` | Regra 50/30/20 com recomendações |
| 🏦 **Conexões** | Pluggy Items | Contas bancárias conectadas / Sandbox |
| 🔗 **Context Override** | `POST/GET /api/v1/context/*` | Classificação PF/PJ manual |
| ❤️ **Health Score** | `GET /api/v1/health-score/history/{user_id}` | Evolução da saúde financeira |

---

## 🧪 Rodar Testes Automatizados (Smoke Tests)

```bash
cd backend
pytest tests/test_endpoints_smoke.py -v
```

Resultado esperado:
```
tests/test_endpoints_smoke.py::TestAuth::test_login_success PASSED       [ 12%]
tests/test_endpoints_smoke.py::TestAuth::test_login_invalid_password PASSED [ 25%]
tests/test_endpoints_smoke.py::TestTransactions::test_get_transactions PASSED [ 37%]
tests/test_endpoints_smoke.py::TestTransactions::test_get_transactions_with_filters PASSED [ 50%]
tests/test_endpoints_smoke.py::TestHealthScore::test_get_health_score_history PASSED [ 62%]
tests/test_endpoints_smoke.py::TestContextOverride::test_list_overrides PASSED [ 75%]
tests/test_endpoints_smoke.py::TestForecast::test_get_forecast PASSED    [ 87%]
tests/test_endpoints_smoke.py::TestHealth::test_health_check PASSED      [100%]

======================== 8 passed in 5.50s =========================
```

---

## 📊 Arquitetura: Como funciona o Fallback

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (Streamlit @ 8501)                                │
└─────────────────────────────────────────────────────────────┘
                            ↓
                    API calls (HTTP)
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Backend (FastAPI @ 8000)                                   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Rotas (auth, transactions, forecast, etc)           │   │
│  └──────────────────────────────────────────────────────┘   │
│           ↓                           ↓                      │
│    Try Postgres                  Try SQLAlchemy             │
│           │                           │                      │
│           ├─→ ❌ Falha? │             │                      │
│                         └─→ Cair para DuckDB ←─┘             │
│                                      │                       │
│                    ┌─────────────────┴────────────────┐      │
│                    ↓                                  ↓       │
│        DuckDB Fallback         NexaRunner (Mock)     │       │
│        finance.duckdb          (se vazio)            │       │
│    (users, transactions)       (desenvolvimento)     │       │
│                                                      │       │
│  ✅ Resultado: Sempre retorna dados, mesmo offline! │       │
└─────────────────────────────────────────────────────┘       │
```

### 🔄 Fluxo de Dados para GET /transactions/{user_id}

1. **SQLAlchemy → Postgres**
   - Se Postgres está ON e tem dados → retorna do Postgres
   - Se Postgres está ON mas sem dados → fallback DuckDB

2. **Fallback → DuckDB**
   - Lê `backend/finance.duckdb`
   - Tabelas: `users`, `transactions_clean`, `context_overrides`, `health_score_history`
   - Retorna dados normalizados para o frontend

3. **Sempre retorna resposta válida** (200 OK com transações, ou 404 se realmente vazio)

---

## 📝 Variáveis de Ambiente

Todos os defaults estão em `backend/.env.example`. Para dev local, você pode:

```bash
# Usar o .env padrão (já criado) ou criar um novo:
cp backend/.env.example backend/.env

# Editar se quiser Postgres real:
# DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/nexa_db

# Ou usar DuckDB (padrão):
# DATABASE_URL=postgresql+psycopg2://...  # tenta Postgres, cai para DuckDB se falhar
```

---

## 🐛 Troubleshooting

### ❌ "Postgres not available"
→ **Esperado!** O backend automáticamente cai para DuckDB. Você pode ver este warning:
```
⚠ Postgres not available (expected): ArgumentError
```
Isso significa que vai usar DuckDB em vez de Postgres (OK para dev).

### ❌ "Cannot find finance.duckdb"
→ Verifique a localização:
```bash
find . -name finance.duckdb -type f
# Deve estar em: backend/finance.duckdb ou finance.duckdb (raiz)
```

### ❌ "Auth failed: 401 Unauthorized"
→ Usuário não existe no DuckDB. Crie uma conta nova no frontend ou use:
```
Email: test@nexa.local
Password: test123
```

### ❌ "Backend offline / Connection refused"
→ Backend não está rodando. Verifique:
```bash
# Terminal 1
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## ✨ Próximos Passos

1. **Postgres Local (Opcional)**
   - Se quiser dados reais: configure Postgres e altere `DATABASE_URL` no `.env`
   - Backend automaticamente usará Postgres em vez de DuckDB

2. **LLM/OpenAI (Opcional)**
   - Para Chat Inteligente: configure `OPENAI_API_KEY` no `.env`
   - Sem isso, o Chat retorna erro (mas outros endpoints funcionam)

3. **Pluggy (Opcional)**
   - Para conectar contas bancárias reais: configure `PLUGGY_CLIENT_ID` e `PLUGGY_CLIENT_SECRET`
   - Sem isso, apenas modo Sandbox disponível

---

## 📚 Estrutura de Arquivos

```
├── backend/
│   ├── app/
│   │   ├── api/v1/router.py              # Registro de todas as rotas
│   │   ├── db/
│   │   │   ├── queries.py               # Queries (Postgres + DuckDB fallback)
│   │   │   └── users.py                 # Auth (Postgres + DuckDB fallback)
│   │   ├── api/v1/routes/
│   │   │   ├── auth.py                  # Login/Register
│   │   │   ├── transactions.py          # Transações (com fallback)
│   │   │   ├── health_score.py          # Health Score
│   │   │   ├── forecast.py              # Forecast
│   │   │   ├── goals.py                 # Metas
│   │   │   └── ... (outros endpoints)
│   ├── core/
│   │   ├── config.py                    # Configuração (Settings)
│   │   ├── database.py                  # SQLAlchemy setup
│   │   └── security.py                  # JWT, password hashing
│   ├── finance.duckdb                   # Banco de dados DuckDB (fallback)
│   ├── requirements.txt
│   └── tests/
│       └── test_endpoints_smoke.py      # Smoke tests
│
├── frontend/
│   ├── app.py                           # Login/Home page
│   ├── pages/
│   │   ├── 0_✨_Funcionalidades.py      # Teste de endpoints (NEW!)
│   │   ├── 1_💬_Chat_Inteligente.py
│   │   ├── 2_📊_Meu_Dinheiro.py
│   │   └── 3_🔗_Conexoes.py
│   ├── utils/
│   │   ├── api.py                       # Cliente HTTP (NexaAPIClient)
│   │   └── ui.py                        # Componentes Streamlit
│   └── requirements.txt
│
├── .env                                 # Variáveis de ambiente (local)
├── .env.example                         # Template
├── .gitignore                           # Ignora .env
├── pytest.ini                           # Config de testes
├── SETUP_LOCAL.md                       # Este arquivo
└── docker-compose.yml                   # (Opcional) Para Postgres + Redis
```

---

## 🎓 Exemplos de Uso

### Fazer login e acessar Dashboard

```
1. Abra http://localhost:8501
2. Crie conta ou use: test@nexa.local / test123
3. Clique em "📊 Meu Dinheiro" para ver KPIs
4. Clique em "✨ Funcionalidades" para testar endpoints
```

### Testar um endpoint via curl (com token)

```bash
# 1. Login
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -d "username=test@nexa.local&password=test123" | jq -r .access_token)

# 2. Buscar transações
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/transactions/f9aac378-8cb1-4a60-ac31-e95ce9563b7c | jq

# 3. Buscar health score
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/health-score/history/f9aac378-8cb1-4a60-ac31-e95ce9563b7c | jq
```

---

## 🤝 Contribuindo

Mudanças no backend? Rodar tests:

```bash
cd backend
pytest tests/test_endpoints_smoke.py -v
```

Mudanças no frontend? Recarregar Streamlit (Ctrl+R na página).

---

## 📞 Suporte

- **Backend offline?** → Restart Uvicorn
- **Streamlit bugado?** → `streamlit run app.py --logger.level=debug`
- **Testes falhando?** → Verifique se `finance.duckdb` existe

Qualquer dúvida, me avisa!

---

**Status**: ✅ Pronto para dev local!  
**Última atualização**: 2026-03-20  
**Fallback ativo**: ✅ DuckDB + NexaRunner
