"""
app/api/v1/router.py - Router Principal da API V1

╔══════════════════════════════════════════════════════════════════════╗
║ O QUE ESTE ARQUIVO FAZ                                               ║
╚══════════════════════════════════════════════════════════════════════╝

Registra TODAS as rotas disponíveis da API v1.

Funciona como o ponto central: qualquer endpoint novo deve ser
importado e registrado aqui.

╔══════════════════════════════════════════════════════════════════════╗
║ ROTAS DISPONÍVEIS                                                    ║
╚══════════════════════════════════════════════════════════════════════╝

CORE ENGINE:
  GET  /forecast/{user_id}              Previsão consolidada (cashflow + safe-to-spend)
  GET  /shadow_invoice/{user_id}        Obrigações futuras detectadas
  GET  /shadow_invoice/{user_id}/summary Resumo de obrigações
  GET  /alerts/{user_id}                Alertas ativos (token, saldo, etc)
  POST /reconnect/{user_id}             Gerar URL de reconexão

TRANSAÇÕES (ETL):
  POST /transactions/webhook            Webhook de transações (Pluggy)
  GET  /transactions/{user_id}          Buscar transações do usuário

TESTES/desenvolvimento:
  (Other routers for testing)

DOCUMENTAÇÃO:
  GET  /docs                            Swagger UI (auto-generated)
  GET  /redoc                           ReDoc (auto-generated)
"""

from fastapi import APIRouter

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS: Rotas Existentes (teste/desenvolvimento)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from app.api.v1.routes import bank_simulation

# TODO: Ativar quando dependências forem resolvidas
# from app.api.v1.routes import pluggy_test
# from app.api.v1.routes import analyze
# from app.api.v1.routes import cashflow

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS: CORE ENGINE (NOVO!)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Transações: webhook + get
from app.api.v1.routes import transactions

# ✨ NOVO: Auth (Login e Register)
from app.api.v1.routes import auth

# ✨ NOVO: Forecast (previsão consolidada)
from app.api.v1.routes import forecast

# ✨ NOVO: Shadow Invoices (obrigações futuras)
from app.api.v1.routes import shadow_invoice

# ✨ NOVO: Alerts (avisos ao usuário)
from app.api.v1.routes import alerts

# ✨ NOVO: Reconnect (reconectar consentimento)
from app.api.v1.routes import reconnect

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CRIAR ROUTER PRINCIPAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

router = APIRouter()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REGISTRAR ROTAS: Testes/Desenvolvimento
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

router.include_router(bank_simulation.router)

# TODO: Ativar quando dependências forem resolvidas
# router.include_router(pluggy_test.router)
# router.include_router(analyze.router)
# router.include_router(cashflow.router)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REGISTRAR ROTAS: CORE ENGINE (PRODUÇÃO)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 0️⃣ Auth: POST /auth/register, POST /auth/token
router.include_router(auth.router)

# 1️⃣ Transações: POST /transactions/webhook (ingestão de dados)
#    GET  /transactions/{user_id} (buscar dados)
router.include_router(transactions.router)

# 2️⃣ Forecast: GET /forecast/{user_id} (previsão consolidada)
router.include_router(forecast.router)

# 3️⃣ Shadow Invoice: GET /shadow_invoice/{user_id} (obrigações futuras)
router.include_router(shadow_invoice.router)

# 4️⃣ Alerts: GET /alerts/{user_id} (avisos)
router.include_router(alerts.router)

# 5️⃣ Reconnect: POST /reconnect/{user_id} (reconectar consentimento)
router.include_router(reconnect.router)

# 6️⃣ Context Override: POST /context/override (F4 - Nexa Divider)
from app.api.v1.routes import context_override
router.include_router(context_override.router)

# 7️⃣ Architect: POST /architect/simulate (F3 - Nexa Architect)
from app.api.v1.routes import architect
router.include_router(architect.router)

# 8️⃣ Optimizer: POST /optimizer/analyze (F2 - Nexa Optimizer)
from app.api.v1.routes import optimizer
router.include_router(optimizer.router)

# 9️⃣ Agent Chat: POST /chat (F2/F3 - Nexa IA Chat)
from app.api.v1.routes import chat
router.include_router(chat.router)

# 🔟 Health Score History: GET /health-score/history/{user_id} (MX.1)
from app.api.v1.routes import health_score
router.include_router(health_score.router)
# 1️⃣1️⃣ Subscriptions: GET /subscriptions/{user_id} (M1.5)
from app.api.v1.routes import subscriptions
router.include_router(subscriptions.router)

# 1️⃣2️⃣ Goals: /goals/{user_id} (MX.2)
from app.api.v1.routes import goals
router.include_router(goals.router)

# 1️⃣3️⃣ Budget: /budget/{user_id} (M1.3 — Orçamento Inteligente)
from app.api.v1.routes import budget
router.include_router(budget.router)

# 1️⃣4️⃣ Notifications: /notifications/{user_id} (MX.3 — Notificações Proativas)
from app.api.v1.routes import notifications
router.include_router(notifications.router)

# 1️⃣5️⃣ Fiscal Report: /fiscal-report/{user_id} (M4.1 — Relatório Fiscal PJ)
from app.api.v1.routes import fiscal_report
router.include_router(fiscal_report.router)

# 1️⃣6️⃣ Peers: /peers/compare/{user_id} (MX.4 — Comparação com Perfis Similares)
from app.api.v1.routes import peers
router.include_router(peers.router)

# 1️⃣7️⃣ Safe-to-Spend: /safe-to-spend/{user_id} (F1 — Gauge + Ritmo de Gastos)
from app.api.v1.routes import safe_to_spend
router.include_router(safe_to_spend.router)

