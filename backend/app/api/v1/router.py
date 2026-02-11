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