# Nexa AI — Backend

Agente financeiro que usa dados do Open Finance (via Pluggy) para responder perguntas sobre saúde financeira, quanto o usuário pode gastar e como comprar um bem da forma mais barata possível.

**Status atual:** Ferramentas de cálculo prontas. Camada de IA (LLM + agente conversacional) em desenvolvimento.

---

## O que o sistema faz hoje

| Funcionalidade | Status |
|---|---|
| Ingestão de transações via Pluggy (Open Finance) | Pronto |
| ETL: normalização, categorização, deduplicação | Pronto |
| Detecção de assinaturas e parcelas (shadow invoices) | Pronto |
| Projeção de saldo diário (30 dias) | Pronto |
| Cálculo de safe-to-spend (quanto pode gastar com segurança) | Pronto |
| Perfil financeiro do usuário (score 0-100) | Pronto |
| Classificador PF/PJ de transações (Random Forest) | Pronto |
| Simulador de compra de bem (financiamento vs consórcio vs investimento) | Pronto |
| Agente conversacional com LLM | Em desenvolvimento |
| Card Optimizer | Não iniciado |

---

## Pré-requisitos

- Python 3.11+
- Conta na [Pluggy](https://pluggy.ai) com `CLIENT_ID` e `CLIENT_SECRET`

---

## Instalação

```bash
cd backend
pip install -r requirements.txt
```

---

## Variáveis de ambiente

Crie o arquivo `backend/.env` com base no exemplo abaixo:

```env
# Pluggy (Open Finance)
PLUGGY_CLIENT_ID=seu_client_id
PLUGGY_CLIENT_SECRET=seu_client_secret
PLUGGY_BASE_URL=https://api.pluggy.ai

# URL do frontend (usada no redirect de reconexão)
FRONTEND_BASE_URL=http://localhost:3000
```

---

## Como rodar

```bash
cd backend
uvicorn app.main:app --port 8000 --reload
```

Swagger UI disponível em: `http://localhost:8000/docs`

---

## Como rodar os testes

```bash
cd backend
pytest tests/
```

414 testes, 0 falhando.

---

## Endpoints da API

### Saúde financeira e previsão

| Método | Rota | O que faz |
|---|---|---|
| `GET` | `/api/v1/forecast/{user_id}` | Previsão completa: cashflow 30 dias, safe-to-spend, shadow invoices, perfil financeiro |
| `GET` | `/api/v1/shadow_invoice/{user_id}` | Lista obrigações futuras detectadas (assinaturas + parcelas) |
| `GET` | `/api/v1/shadow_invoice/{user_id}/summary` | Resumo de obrigações futuras |
| `GET` | `/api/v1/alerts/{user_id}` | Alertas ativos: token expirado, saldo negativo, caixa comprometido |

### Transações

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/api/v1/transactions/webhook` | Recebe transações do Pluggy, valida e roda ETL |
| `GET` | `/api/v1/transactions/{user_id}` | Busca transações do usuário — **501 (não implementado)** |

### Simulador de compra de bem (F3 — Nexa Architect)

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/api/v1/architect/simulate` | Simula compra: compara financiamento, consórcio e investimento. Ranqueia pelo menor custo (VPL). Busca taxas reais BACEN/ANBIMA. |
| `GET` | `/api/v1/architect/simulations` | Lista simulações anteriores do usuário |
| `GET` | `/api/v1/architect/simulations/{id}` | Detalhe de uma simulação |
| `GET` | `/api/v1/architect/simulations/{id}/sensitivity` | Re-análise de sensibilidade com taxas atuais |
| `GET` | `/api/v1/architect/metrics` | Métricas do usuário |

### Classificação PF/PJ (F4)

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/api/v1/context/override` | Salva correção manual de classificação PF/PJ |
| `GET` | `/api/v1/context/overrides/{user_id}` | Lista correções manuais do usuário |

### Reconexão e utilitários

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/api/v1/reconnect/{user_id}` | Gera URL de reconexão do consentimento Pluggy |
| `GET` | `/health` | Health check |
| `GET` | `/version` | Versão da API |

---

## Exemplo de uso — Simulação de compra

```bash
curl -X POST http://localhost:8000/api/v1/architect/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "asset_type": "vehicle",
    "target_value": 60000,
    "down_payment": 12000,
    "months": 48,
    "monthly_income": 8000,
    "current_savings": 15000
  }'
```

Retorna as 3 estratégias ranqueadas por custo total (VPL), com análise de sensibilidade a variações de taxa de juros, CDI e prazo.

---

## Estrutura do backend

```
backend/
├── app/
│   ├── main.py                        # FastAPI app
│   ├── runner.py                      # NexaRunner: orquestra pipeline completo
│   ├── api/v1/routes/                 # Endpoints
│   ├── etl/                           # Pipeline ETL (ingestão, classificação, shadow invoices)
│   ├── cashflow/                      # Projeção de saldo e safe-to-spend
│   ├── architect/                     # Simulador de compra de bem (F3)
│   ├── agent/                         # Agente LangGraph (desabilitado)
│   ├── integrations/open_finance/     # Cliente Pluggy (real + mock)
│   ├── schemas/                       # Modelos Pydantic
│   ├── db/                            # DuckDB queries
│   └── core/                          # Config, logging
├── models/                            # Modelos ML serializados (.pkl)
├── data/                              # Datasets de treino
├── scripts/                           # Scripts de treino e validação ML
└── tests/                             # 414 testes pytest
```

Para o mapa completo de dependências entre arquivos, consulte [backend/caminho.md](backend/caminho.md).

---

## Documentação adicional

| Arquivo | Conteúdo |
|---|---|
| [PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md) | Tudo que falta para ir a produção |
| [PROJETO_CHECKOUT_FINAL.md](PROJETO_CHECKOUT_FINAL.md) | Estado atual detalhado: o que está pronto e o que não está |
| [backend/caminho.md](backend/caminho.md) | Mapa completo de dependências entre arquivos |
| [backend/ARCHITECTURE.md](backend/ARCHITECTURE.md) | Arquitetura do sistema |
| [backend/HOW_TO_TEST.md](backend/HOW_TO_TEST.md) | Guia de testes |
