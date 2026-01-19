# 🗺️ GUIA DE ARQUITETURA — NEXA AI BACKEND

## 📋 Visão Geral

Este documento explica a estrutura do backend da Nexa AI, o que cada pasta faz e como os componentes se conectam.

---

## 🏗️ ESTRUTURA DE PASTAS

```
backend/app/
├── api/          → Porta de entrada (HTTP endpoints)
├── schemas/      → Contratos de dados (validação)
├── etl/          → Limpeza e normalização (Polars)
├── engines/      → Cálculos financeiros (matemática)
├── agent/        → Orquestração inteligente (LangGraph)
├── ml/           → Modelos de Machine Learning
├── db/           → Banco de dados (Postgres)
├── storage/      → Armazenamento de arquivos (S3)
├── core/         → Configurações base (logs, security)
├── integrations/ → APIs externas (Pluggy, Belvo)
└── main.py       → Entrypoint da aplicação
```

---

## 📂 DETALHAMENTO DE CADA PASTA

### 🚪 `api/` — Porta de Entrada (FastAPI)

**O QUE FAZ:**
- Recebe requisições HTTP (webhooks, GET, POST)
- Valida entrada com Pydantic
- Chama serviços internos
- Retorna respostas formatadas

**ESTRUTURA:**
```
api/
├── v1/
│   ├── routes/
│   │   ├── transactions.py    # POST /webhook/transactions
│   │   ├── forecast.py        # GET /forecast/{user_id}
│   │   ├── safe_to_spend.py   # GET /safe-to-spend/{user_id}
│   │   └── chat.py            # POST /chat (agent)
│   └── router.py              # Registra todas as rotas
└── deps.py                    # Dependências (get_db, auth)
```

**CONECTA COM:**
- `schemas/` → Valida entrada/saída
- `etl/` → Processa dados
- `engines/` → Executa cálculos
- `agent/` → Orquestra decisões
- `db/` → Persiste dados

**EXEMPLO:**
```python
# api/v1/routes/transactions.py
from app.schemas.transaction import TransactionWebhook
from app.etl.ingestor import TransactionIngestor
from app.db.session import get_db

@router.post("/webhook/transactions")
async def receive_webhook(
    payload: list[TransactionWebhook],  # schemas valida
    db: Session = Depends(get_db)       # db injeta conexão
):
    # 1. Validar (schemas faz automaticamente)
    # 2. Processar (etl limpa os dados)
    # 3. Salvar (db persiste)
    ...
```

---

### 📝 `schemas/` — Contratos de Dados (Pydantic)

**O QUE FAZ:**
- Define estrutura esperada de entrada e saída
- Valida tipos e campos obrigatórios
- Converte tipos básicos (str → datetime)
- Gera documentação automática (OpenAPI)

**ESTRUTURA:**
```
schemas/
├── transaction.py       # TransactionWebhook, TransactionOut
├── forecast.py          # ForecastRequest, ForecastResponse
├── safe_to_spend.py     # SafeToSpendResponse
├── shadow_invoice.py    # ShadowInvoiceResponse
└── chat.py              # ChatRequest, ChatResponse
```

**CONECTA COM:**
- `api/` → FastAPI usa como validador
- `etl/` → Converte para DataFrame
- `engines/` → Recebe dados validados

**REGRA DE OURO:**
- **Pydantic valida FORMA, não SEMÂNTICA**
- ✅ `amount` é Decimal? → Pydantic
- ❌ `amount` é duplicata? → Polars (etl/)

**EXEMPLO:**
```python
# schemas/transaction.py
from pydantic import BaseModel, Field
from decimal import Decimal

class TransactionWebhook(BaseModel):
    """Contrato de entrada do webhook Open Finance"""
    transaction_id: str = Field(..., alias="id")
    amount: Decimal
    date: str
    description: str | None = None
    
    @field_validator("amount")
    @classmethod
    def amount_cannot_be_zero(cls, v):
        if v == 0:
            raise ValueError("Amount cannot be zero")
        return v
```

---

### ⚙️ `etl/` — Limpeza e Normalização (Polars)

**O QUE FAZ:**
- Transforma JSON → DataFrame limpo
- Remove duplicatas
- Normaliza datas e textos
- Detecta padrões (recorrências, parcelamentos)
- Valida qualidade por banco (BankStrategy)

**ESTRUTURA:**
```
etl/
├── ingestor.py              # JSON → DataFrame limpo
├── classifier.py            # CatBoost: categorização
├── recurring_detector.py    # Detecta assinaturas
├── installment_detector.py  # Detecta parcelamentos
└── bank_strategy.py         # Valida confiança por banco
```

**CONECTA COM:**
- `schemas/` → Recebe dados validados (list[dict])
- `ml/` → Usa CatBoost para classificar
- `engines/` → Fornece DataFrame limpo
- `db/` → Salva dados processados

**REGRA DE OURO:**
- **Tudo que entra é DataFrame, tudo que sai é DataFrame**
- **Polars faz matemática pesada, não validação simples**

**EXEMPLO:**
```python
# etl/ingestor.py
import polars as pl

class TransactionIngestor:
    """Transforma JSON → DataFrame limpo"""
    
    def process(self, raw_transactions: list[dict]) -> pl.DataFrame:
        # 1. Criar DataFrame
        df = pl.DataFrame(raw_transactions)
        
        # 2. Normalizar tipos
        df = df.with_columns([
            pl.col("amount").cast(pl.Float64),
            pl.col("date").str.to_datetime("%Y-%m-%d"),
            pl.col("description").str.strip().str.to_lowercase()
        ])
        
        # 3. Remover duplicatas
        df = df.unique(subset=["transaction_id"], keep="first")
        
        return df
```

---

### 🧮 `engines/` — Cálculos Financeiros (Matemática Determinística)

**O QUE FAZ:**
- Executa cálculos financeiros críticos
- Safe-to-Spend (quanto posso gastar hoje?)
- Shadow Invoice (projeção quando dados falham)
- Detecção de parcelamentos/recorrências
- Simulações (Optimizer, Architect)

**ESTRUTURA:**
```
engines/
├── calculator.py         # Safe-to-Spend, fluxo de caixa
├── shadow_invoice.py     # Projeção fallback
├── reconciler.py         # Parcelamentos
├── optimizer.py          # Custo de oportunidade (cartões)
└── architect.py          # Simulações (carro, imóvel)
```

**CONECTA COM:**
- `etl/` → Recebe DataFrame limpo
- `ml/` → Pode usar previsões como input
- `agent/` → Fornece números para explicação
- `db/` → Salva resultados (daily_forecast)

**REGRA DE OURO:**
- **Matemática decide, IA explica**
- **Engines NUNCA usam LLM para calcular**

**EXEMPLO:**
```python
# engines/calculator.py
import polars as pl

class SafeToSpendCalculator:
    """Calcula quanto o usuário pode gastar hoje"""
    
    def calculate(
        self,
        current_balance: float,
        transactions_df: pl.DataFrame,
        forecast_days: int = 30
    ) -> dict:
        # 1. Detectar despesas recorrentes
        recurring = self._detect_recurring(transactions_df)
        
        # 2. Projetar despesas futuras
        future_outflows = self._project_outflows(recurring, forecast_days)
        
        # 3. Aplicar margem de segurança (15%)
        margin = future_outflows * 0.15
        
        # 4. Calcular Safe-to-Spend
        safe_amount = current_balance - future_outflows - margin
        
        return {
            "safe_to_spend": max(0, safe_amount),
            "current_balance": current_balance,
            "predicted_outflows": future_outflows,
            "safety_margin": margin,
            "confidence": 0.85
        }
```

---

### 🤖 `agent/` — Orquestração Inteligente (LangGraph)

**O QUE FAZ:**
- Orquestra fluxos de decisão complexos
- Decide quando usar dados oficiais vs Shadow Invoice
- Chama ferramentas (tools) apropriadas
- Gera explicações via LLM
- Gerencia fallbacks

**ESTRUTURA:**
```
agent/
├── graph.py       # LangGraph state machine
├── tools.py       # Ferramentas disponíveis (get_forecast, etc)
├── prompts.py     # Templates para LLM
└── state.py       # Estado da conversa
```

**CONECTA COM:**
- `engines/` → Consulta cálculos prontos
- `etl/` → Verifica qualidade dos dados
- `db/` → Busca informações persistidas
- `api/` → Recebe requisições do chat

**REGRA DE OURO:**
- **LLM explica, não calcula**
- **Decisões baseadas em matemática, não em prompts**

**EXEMPLO:**
```python
# agent/graph.py
from langgraph.graph import StateGraph
from app.engines.calculator import SafeToSpendCalculator

def create_agent():
    """Cria grafo de decisão do agente"""
    
    graph = StateGraph()
    
    # Nó: Verificar qualidade dos dados
    def check_data_quality(state):
        # Se confiança < 0.5 → usar Shadow Invoice
        # Se confiança >= 0.5 → usar dados oficiais
        ...
    
    # Nó: Calcular Safe-to-Spend
    def calculate_safe_to_spend(state):
        calculator = SafeToSpendCalculator()
        result = calculator.calculate(...)  # ← Matemática
        state["safe_to_spend"] = result
        return state
    
    # Nó: Explicar resultado (LLM)
    def explain_result(state):
        # LLM APENAS explica números já calculados
        prompt = f"""
        O Safe-to-Spend é {state['safe_to_spend']}.
        Explique de forma clara por que este é o valor.
        """
        ...
    
    graph.add_edge("check_quality", "calculate")
    graph.add_edge("calculate", "explain")
    
    return graph
```

---

### 🧠 `ml/` — Machine Learning

**O QUE FAZ:**
- Classificação de categorias (CatBoost)
- Previsão de séries temporais (NeuralProphet)
- Treino e inferência de modelos
- **NUNCA usado para validação crítica**

**ESTRUTURA:**
```
ml/
├── models/                      # Modelos treinados (.cbm, .pkl)
├── catboost_classifier.py       # Merchant → Categoria
├── neuralprophet_forecaster.py  # Previsão temporal
└── training/                    # Scripts de retreino
```

**CONECTA COM:**
- `etl/` → Fornece classificações
- `engines/` → Complementa cálculos (nunca substitui)

**REGRA DE OURO:**
- **IA sugere, matemática decide**
- **ML não toca em Safe-to-Spend ou Shadow Invoice**

**EXEMPLO:**
```python
# ml/catboost_classifier.py
from catboost import CatBoostClassifier
import polars as pl

class TransactionClassifier:
    """Classifica transações em categorias"""
    
    def __init__(self):
        self.model = CatBoostClassifier()
        self.model.load_model("ml/models/category_classifier.cbm")
    
    def predict(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Adiciona coluna 'predicted_category' ao DataFrame.
        
        Confiança sempre retornada junto (confidence_score).
        """
        features = df.select(["merchant", "amount", "description"])
        predictions = self.model.predict(features)
        probabilities = self.model.predict_proba(features)
        
        return df.with_columns([
            pl.Series("predicted_category", predictions),
            pl.Series("ml_confidence", probabilities.max(axis=1))
        ])
```

---

### 💾 `db/` — Banco de Dados (Postgres)

**O QUE FAZ:**
- Define modelos (SQLAlchemy)
- Gerencia sessões de conexão
- Migrations (Alembic)
- Persiste dados processados

**ESTRUTURA:**
```
db/
├── models.py       # User, Account, Transaction, DailyForecast
├── session.py      # Conexão e dependency injection
└── migrations/     # Alembic migrations
```

**CONECTA COM:**
- `api/` → Fornece `get_db()` dependency
- `etl/` → Salva dados limpos
- `engines/` → Persiste resultados

**EXEMPLO:**
```python
# db/models.py
from sqlalchemy import Column, String, Numeric, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Transaction(Base):
    """Transação financeira normalizada"""
    __tablename__ = "transactions"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    amount = Column(Numeric(15, 2), nullable=False)
    date = Column(DateTime, nullable=False, index=True)
    description = Column(String)
    category = Column(String)
    is_recurring = Column(Boolean, default=False)
    confidence = Column(Numeric(3, 2))
```

---

### 📦 `storage/` — Armazenamento de Arquivos (S3)

**O QUE FAZ:**
- Salva JSON cru (raw_events) no S3/MinIO
- Auditoria completa
- Permite replay de ingestão

**ESTRUTURA:**
```
storage/
├── raw_events.py    # Salva/recupera JSON do S3
└── audit.py         # Metadados de auditoria
```

**CONECTA COM:**
- `api/` → Salva webhooks antes de processar
- `db/` → Metadados no Postgres

**EXEMPLO:**
```python
# storage/raw_events.py
import boto3
import json

class RawEventStorage:
    """Armazena eventos crus no S3"""
    
    def store(self, user_id: str, event_type: str, data: dict) -> str:
        """Salva JSON cru no S3 e retorna chave"""
        s3_key = f"{user_id}/{event_type}_{timestamp}.json"
        
        self.s3_client.put_object(
            Bucket="nexa-raw-events",
            Key=s3_key,
            Body=json.dumps(data)
        )
        
        return s3_key
```

---

### ⚙️ `core/` — Configurações Base

**O QUE FAZ:**
- Configurações centralizadas (Pydantic Settings)
- Logs estruturados (structlog)
- Segurança (JWT, hashing, HMAC)

**ESTRUTURA:**
```
core/
├── config.py      # Variáveis de ambiente (12-factor app)
├── logging.py     # Logs estruturados (JSON)
└── security.py    # JWT, bcrypt, HMAC
```

**CONECTA COM:**
- **TODOS OS MÓDULOS** → Fornece config, logs, auth

**EXEMPLO:**
```python
# core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Configurações da aplicação"""
    SECRET_KEY: str
    DATABASE_URL: str
    REDIS_HOST: str
    S3_BUCKET: str
    
    class Config:
        env_file = ".env"

settings = Settings()
```

---

### 🔌 `integrations/` — APIs Externas

**O QUE FAZ:**
- Conecta com Pluggy, Belvo (Open Finance)
- Busca dados ativamente (polling)
- Webhooks vêm via `api/`, isso é para fetch ativo

**ESTRUTURA:**
```
integrations/
└── open_finance/
    ├── pluggy.py     # Cliente Pluggy SDK
    └── belvo.py      # Cliente Belvo SDK
```

**CONECTA COM:**
- `api/` → Pode ser chamado por rotas (sync manual)
- `storage/` → Salva dados buscados

**EXEMPLO:**
```python
# integrations/open_finance/pluggy.py
from pluggy import PluggyClient

class PluggyConnector:
    """Cliente para buscar dados do Pluggy"""
    
    def fetch_transactions(self, item_id: str):
        """Busca transações direto da API"""
        return self.client.fetch_transactions(item_id)
```

---

## 🔄 FLUXO DE DADOS COMPLETO

### **Cenário: Webhook de transações chega**

```
1. ENTRADA (api/)
   └─> POST /webhook/transactions recebe JSON

2. VALIDAÇÃO (schemas/)
   └─> Pydantic valida estrutura

3. PERSISTÊNCIA (storage/)
   └─> JSON cru salvo no S3

4. LIMPEZA (etl/)
   └─> Polars normaliza → DataFrame limpo

5. CLASSIFICAÇÃO (ml/)
   └─> CatBoost adiciona categoria

6. CÁLCULO (engines/)
   └─> Calculator gera Safe-to-Spend

7. PERSISTÊNCIA (db/)
   └─> DataFrame → Postgres

8. RESPOSTA (api/)
   └─> 204 No Content (webhook aceito)
```

### **Cenário: Usuário pergunta "Posso gastar R$ 500?"**

```
1. ENTRADA (api/)
   └─> POST /chat com pergunta

2. ORQUESTRAÇÃO (agent/)
   └─> LangGraph decide fluxo

3. CONSULTA (engines/)
   └─> Busca Safe-to-Spend calculado

4. EXPLICAÇÃO (agent/)
   └─> LLM gera resposta natural

5. RESPOSTA (api/)
   └─> JSON com resposta + confiança
```

---

## 🎯 REGRAS DE OURO

### **1. Divisão de Responsabilidades**
- `api/` → Recebe e responde HTTP
- `schemas/` → Valida forma
- `etl/` → Limpa e normaliza
- `engines/` → Calcula
- `agent/` → Decide e explica
- `ml/` → Classifica e prevê
- `db/` → Persiste
- `storage/` → Armazena arquivos
- `core/` → Fundação
- `integrations/` → Mundo externo

### **2. Nunca misture responsabilidades**
❌ **ERRADO**: API fazendo cálculo financeiro
❌ **ERRADO**: Pydantic detectando duplicatas
❌ **ERRADO**: LLM calculando Safe-to-Spend
❌ **ERRADO**: Engine salvando no banco

✅ **CORRETO**: Cada camada tem um propósito único

### **3. Fluxo de dados sempre linear**
```
api → schemas → etl → engines → db → api
```

### **4. Imports sempre de cima para baixo**
```python
# ✅ CORRETO
from app.schemas.transaction import TransactionWebhook  # camada inferior
from app.etl.ingestor import TransactionIngestor       # camada inferior

# ❌ ERRADO
from app.api.v1.routes import transactions  # camada superior!
```

---

## 📚 GLOSSÁRIO RÁPIDO

| Termo | O que é | Onde vive |
|-------|---------|-----------|
| **Pydantic** | Validação de tipos | `schemas/` |
| **Polars** | DataFrame (tipo pandas) | `etl/`, `engines/` |
| **FastAPI** | Framework web | `api/` |
| **LangGraph** | Orquestração de agentes | `agent/` |
| **CatBoost** | ML para classificação | `ml/` |
| **SQLAlchemy** | ORM (Postgres) | `db/` |
| **S3/MinIO** | Storage de arquivos | `storage/` |
| **Raw Events** | JSON cru (auditoria) | `storage/` |
| **Shadow Invoice** | Projeção fallback | `engines/` |
| **Safe-to-Spend** | Quanto posso gastar | `engines/` |

---

## 🆘 PERGUNTAS FREQUENTES

**Q: Onde crio uma nova rota HTTP?**  
A: `api/v1/routes/`, depois registra em `router.py`

**Q: Onde adiciono validação de campo?**  
A: Se é simples (tipo, null) → `schemas/`. Se é complexo (duplicata) → `etl/`

**Q: Onde faço cálculo financeiro?**  
A: `engines/`. NUNCA em `api/` ou `schemas/`

**Q: Onde o LLM entra?**  
A: `agent/`, apenas para explicar números já calculados

**Q: Onde salvo dados processados?**  
A: `db/models.py` → SQLAlchemy → Postgres

**Q: Onde salvo JSON cru?**  
A: `storage/raw_events.py` → S3/MinIO

**Q: Como conectar com Pluggy?**  
A: `integrations/open_finance/pluggy.py`

---

## 🚀 PRÓXIMOS PASSOS

1. Ler este guia completo
2. Entender separação de responsabilidades
3. Começar implementação por:
   - `core/` (fundação)
   - `schemas/` (contratos)
   - `db/` (persistência)
   - `api/` (endpoints)
   - `etl/` (processamento)
   - `engines/` (cálculos)
   - `agent/` (orquestração)

**Dúvidas? Pergunte antes de criar código!** 🤝