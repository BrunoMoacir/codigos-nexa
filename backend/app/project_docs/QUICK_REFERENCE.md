# ⚡ QUICK REFERENCE - NEXA AI

**Salva este arquivo! Você vai usar 100 vezes por dia**

---

## 🚀 COMANDOS ESSENCIAIS

```bash
# ✅ Iniciar servidor
cd backend && python -m uvicorn app.main:app --reload --host localhost --port 8000

# ✅ Testar API
cd backend && python test_api.py

# ✅ Ver Swagger
http://localhost:8000/docs

# ✅ Rodar testes
cd backend && python -m pytest tests/ -v

# ✅ Novo arquivo de rota
touch backend/app/api/v1/routes/new_route.py

# ✅ Novo schema
touch backend/app/schemas/new_schema.py

# ✅ Debug do runner
python backend/app/runner.py
```

---

## 📂 ESTRUTURA RÁPIDA

```
backend/app/
├── api/v1/routes/           ← Crie endpoints aqui 🔨
├── schemas/                  ← Valide com Pydantic 📝
├── etl/                      ← Processa dados 🔄
├── cashflow/                 ← Projeção financeira 📊
├── integrations/open_finance/ ← Pluggy (externa)
├── agent/                    ← LangGraph (conversa)
├── ml/models/                ← Modelos treinados 🤖
├── db/                       ← Postgres/DuckDB 💾
└── main.py                   ← Entry point
```

---

## 🔗 COMO TUDO CONECTA

```
Request HTTP
  ↓
Route (api/v1/routes/*.py)
  ↓
Schema validation (schemas/*.py)
  ↓
Business logic (etl/, cashflow/, agent/)
  ↓
Database op (db/ ou DuckDB)
  ↓
Response
```

---

## 📍 LOCALIZAÇÃO: ONDE ACHAR AS COISAS?

| Vou precisar editar... | Vai estar aqui... |
|---|---|
| Novo endpoint (GET /xyz) | `backend/app/api/v1/routes/xyz.py` |
| Validar entrada | `backend/app/schemas/xyz.py` |
| Classificar transação | `backend/app/etl/classifier.py` |
| Projetar cashflow | `backend/app/cashflow/projector.py` |
| Detectar recorrência | `backend/app/etl/recurring_detector.py` |
| Detectar futuros (shadow) | `backend/app/etl/shadow_invoices.py` |
| Integrar LLM | `backend/app/agent/graph.py` |
| Dados de teste | `backend/app/integrations/open_finance/pluggy_mock.py` |
| Configuração | `backend/.env` |
| Variáveis globais | `backend/app/core/config.py` |

---

## 🎯 STATUS CHECKLIST

### ✅ Completo (F1: Core Engine)
- [x] Ingestão via Pluggy
- [x] ETL pipeline (5 etapas)
- [x] Classificação CatBoost
- [x] Recurring detector
- [x] Shadow invoice detector
- [x] Cashflow projector
- [x] Safe-to-spend calculator
- [x] 5 endpoints API live
- [x] 10/10 testes passing
- [x] Swagger docs

### ⏳ TODO (F2: Optimizer)
- [ ] Análise de cartões
- [ ] Score por cartão
- [ ] Recomendação de fusão
- [ ] Endpoint: GET /analyze_cards/{user_id}
- [ ] Testes

### ⏳ TODO (F3: Architect)
- [ ] Integração Claude
- [ ] Tools para agent
- [ ] Endpoint: POST /get_recommendation/{user_id}
- [ ] Chat conversacional
- [ ] Testes

### ⏳ TODO (F4: Divider PF/PJ)
- [ ] Feature engineering
- [ ] Random Forest training
- [ ] Decision rules
- [ ] User override
- [ ] Continuous learning

---

## 🛠️ ADICIONAR NOVA ROTA (PASSO A PASSO)

### Passo 1: Criar arquivo
```python
# backend/app/api/v1/routes/my_feature.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/my_feature", tags=["MyFeature"])

class MyRequest(BaseModel):
    user_id: str

class MyResponse(BaseModel):
    result: str

@router.get("/{user_id}")
async def get_my_feature(user_id: str) -> MyResponse:
    """Descrição da rota"""
    return MyResponse(result="OK")

@router.get("", tags=["Health"])
async def health():
    return {"status": "ok"}
```

### Passo 2: Registrar em router.py
```python
# backend/app/api/v1/router.py

from app.api.v1.routes import my_feature  # ← Add import

# Depois, no código:
api_router.include_router(my_feature.router)  # ← Register
```

### Passo 3: Testar
```bash
curl http://localhost:8000/api/v1/my_feature/user_123
```

---

## 📝 ADICIONAR NOVO SCHEMA (PASSO A PASSO)

### Passo 1: Criar arquivo
```python
# backend/app/schemas/my_data.py

from pydantic import BaseModel, Field
from typing import Literal

class MySchema(BaseModel):
    """Contrato de dados"""
    user_id: str = Field(..., description="ID do usuário")
    amount: float = Field(..., ge=0)
    status: Literal["PENDING", "DONE"] = "PENDING"
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_123",
                "amount": 100.0,
                "status": "PENDING"
            }
        }
```

### Passo 2: Usar na rota
```python
# backend/app/api/v1/routes/my_feature.py

from app.schemas.my_data import MySchema

@router.post("/process")
async def process_data(data: MySchema):
    print(data.user_id)  # Type-safe!
    return {"received": data}
```

---

## 🧪 TESTAR RÁPIDO

### Via Python
```bash
cd backend
python test_api.py
```

### Via cURL
```bash
curl http://localhost:8000/api/v1/forecast/user_123

curl -X POST http://localhost:8000/api/v1/reconnect/user_123 \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Via Swagger
```
http://localhost:8000/docs
```

### Via Pytest
```bash
cd backend
python -m pytest tests/test_my_feature.py -v
```

---

## 🐛 DEBUG RÁPIDO

### Problema: Pydantic validation error
```python
# ❌ Esqueci campo obrigatório
{"name": "xyz"}  # falta "amount"

# ✅ Adicione
{"name": "xyz", "amount": 100.0}
```

### Problema: Endpoint retorna 404
```
❌ GET http://localhost:8000/api/v1/xyz
✅ Verifique em router.py se router está registrado
   include_router(xyz.router)
```

### Problema: Teste falha
```bash
# ❌ Rodou no caminho errado
python test_api.py

# ✅ Rode do backend/
cd backend && python test_api.py
```

### Problema: DuckDB não encontrado
```bash
# ❌ Não criou o banco
❌ FileNotFoundError: data/transactions.duckdb

# ✅ Roda NexaRunner uma vez
python -c "from app.runner import NexaRunner; NexaRunner().run()"
```

---

## 📊 DADOS MOCK PARA TESTE

```python
# backend/app/integrations/open_finance/pluggy_mock.py
# Edite aqui para mudar dados de teste

MOCK_TRANSACTIONS = [
    {
        "id": "txn_001",
        "date": "2025-02-10",
        "amount": -150.00,
        "description": "Restaurante X",
        "merchant": "RESTAURANTE X"
    },
    # ... mais transações
]
```

---

## 📈 COMO VER O QUE CADA LAYER FAZ

### 1. Integração (dados brutos)
```bash
curl http://localhost:8000/api/v1/transactions  # ← raw JSON
```

### 2. Validação (Pydantic)
```python
# Automático! Se der erro, Pydantic reclama
POST /api/v1/forecast
  ├─ ✅ user_id present? → OK
  └─ ❌ user_id missing? → "Field required"
```

### 3. ETL (processamento)
```python
# backend/app/runner.py
runner = NexaRunner()
result = runner.run()
print(result["transactions"])  # ← normalizado
print(result["cashflow"])      # ← processado
```

### 4. Forecast (resposta final)
```bash
GET http://localhost:8000/api/v1/forecast/user_123
# Retorna tudo consolidado
```

---

## 🔄 DEPENDÊNCIAS IMPORTANTES

```python
# Sempre que mexer em:

# ← Transações
from app.etl import TransactionIngestor

# ← Cashflow
from app.cashflow import CashflowProjector, SafeToSpendCalculator

# ← Classificação
from app.etl import TransactionClassifier

# ← Recorrência
from app.etl import RecurringDetector

# ← Dados consolidados
from app.runner import NexaRunner

# ← Schemas (validação)
from app.schemas import * 

# ← Agent (conv)
from app.agent import build_graph
```

---

## ⚙️ VARIÁVEIS IMPORTANTES

```python
# benchmark/app/core/config.py
LOG_LEVEL = "INFO"       # Mudar para "DEBUG" para mais logs
APP_MODE = "dev"         # ou "prod"
DATABASE_URL = "sqlite:///./test.db"

# Muitos endpoints
HORIZON_DAYS = 30        # Quantos dias projetar
SAFETY_BUFFER = 0.15     # 15% de margem de segurança
```

---

## 📊 APIS EXTERNAS CHAVE

| API | Como Usar |
|-----|-----------|
| **Pluggy** | `from app.integrations.open_finance.pluggy_mock import MockPluggyClient` |
| **Claude** | `from langchain.chat_models import ChatAnthropic` (F3) |
| **Postgres** | `from app.db.session import get_db` |
| **DuckDB** | `import duckdb; duckdb.sql("SELECT * FROM transactions")` |

---

## 🧩 FLUXO: DO ENTENDER MELHOR

```
[User Question]
    "Quanto posso gastar?"
         ↓
[API Route receives]
    GET /forecast/user_123
         ↓
[Pydantic validates]
    ✓ user_id is strings
    ✓ All fields OK
         ↓
[Runner executes]
    1. Pluggy → gets transactions
    2. Ingestor → cleans
    3. Classifier → categorizes
    4. Recurring → finds patterns
    5. Shadow → predicts obligations
    6. Cashflow → projects balance
    7. Safe-to-spend → calculates margin
         ↓
[API returns]
    {
      "safe_to_spend_daily": 107.67,
      "risk_level": "LOW"
    }
         ↓
[Frontend shows]
    "Gaste até R$ 107.67"
```

---

## 🎯 TROUBLESHOOTING CHECKLIST

- [ ] Servidor rodando? `python -m uvicorn ...`
- [ ] Porta 8000 livre? `lsof -i :8000`
- [ ] Dependências instaladas? `pip install -r requirements.txt`
- [ ] .env configurado? `ls backend/.env`
- [ ] Python 3.11+? `python --version`
- [ ] No venv? `source .venv/Scripts/activate` (Windows) ou `source .venv/bin/activate` (Mac/Linux)
- [ ] Rota registrada em router.py? `grep include_router router.py`
- [ ] Schema importadoem rota? `from app.schemas import ...`
- [ ] Swagger acessível? `http://localhost:8000/docs`

---

## 🚀 PRÓXIMOS PASSOS HOJE

1. **Ler** `PROJECT_CHECKOUT.md` (completo)
2. **Rodar** servidor + testes
3. **Explorar** Swagger em http://localhost:8000/docs
4. **Decidir:** F2 ou F3 ou F4 primeiro?
5. **Começar** novo endpoint

---

## 📞 CHEAT SHEET DE PATH

```bash
Root: c:\Users\bruno\OneDrive\Área de Trabalho\nexa\codigos-nexa\

backend/          ← Código Python
├── app/          ← Aplicação
├── tests/        ← Testes pytest
├── .env          ← Vars de env
└── pyproject.toml ← Dependencies

# 99% do tempo você faz algo em:
backend/app/api/v1/routes/
backend/app/schemas/
backend/app/etl/
```

---

**Salva este arquivo e volta aqui sempre que precisar!**

*Última atualização: 11/02/2026*
