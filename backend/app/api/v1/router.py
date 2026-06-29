"""
app/api/v1/router.py - Router Principal da API V1

Registra TODAS as rotas disponíveis da API v1.
Cada feature tem seu próprio router.py auto-contido.
"""

from fastapi import APIRouter

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS: Rotas compartilhadas (teste/desenvolvimento)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from app.api.v1.routes import bank_simulation
from app.api.v1.routes import analyze
from app.api.v1.routes import auth
from app.api.v1.routes import pluggy
from app.api.v1.routes import reconnect

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS: Feature routers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# F1 - Forecast (ETL + cashflow engine)
from app.forecast.router import router as forecast_router
from app.forecast.router_transactions import router as transactions_router
from app.forecast.router_shadow_invoice import router as shadow_invoice_router
from app.forecast.router_alerts import router as alerts_router
from app.forecast.router_safe_to_spend import router as safe_to_spend_router

# F2 - Optimizer
from app.optimizer.router import router as optimizer_router

# F3 - Architect
from app.architect.router import router as architect_router

# F4 - Divider (PF/PJ classification + context override)
from app.divider.router import router as divider_router

# F5 - Costs (Raio-X de Custos Bancários)
from app.costs.router import router as costs_router

# F7 - Purchase (Modo Compra Inteligente)
from app.purchase.router import router as purchase_router

# F13 - Negotiator (Roteiro de Negociação)
from app.negotiator.router import router as negotiator_router

# M1.3 - Budget (Orçamento Inteligente)
from app.budget.router import router as budget_router

# M1.5 - Subscriptions
from app.subscriptions.router import router as subscriptions_router

# M4.1 - Fiscal Report (Relatório Fiscal PJ)
from app.fiscal.router import router as fiscal_router

# MX.1 - Health Score
from app.health_score.router import router as health_score_router

# MX.2 - Goals (Metas Financeiras)
from app.goals.router import router as goals_router

# MX.3 - Notifications (Notificações Proativas)
from app.notifications.router import router as notifications_router

# MX.4 - Peers (Comparação com Perfis Similares)
from app.peers.router import router as peers_router

# AI Chat Agent
from app.agent.router import router as agent_router

# User Settings (preferências de notificação)
from app.settings.router import router as settings_router

# OPP — Radar de Oportunidades
from app.opportunities.router import router as opportunities_router

# Defense — Defesa do Consumidor (D1–D5)
from app.defense.router import router as defense_router

# Rights — Monitor de Direitos Esquecidos (T3)
from app.rights.router import router as rights_router

# Tax — Otimização de IR em Investimentos (T1/T2)
from app.tax.router import router as tax_router

# Viral — Savings Card & Wrapped (V1/V2)
from app.viral.router import router as viral_router

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CRIAR ROUTER PRINCIPAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

router = APIRouter()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REGISTRAR ROTAS: Compartilhadas
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

router.include_router(bank_simulation.router)
router.include_router(analyze.router)
router.include_router(auth.router)
router.include_router(pluggy.router, prefix="/pluggy", tags=["Pluggy Analytics"])
router.include_router(reconnect.router)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REGISTRAR ROTAS: Features
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# F1 - Forecast
router.include_router(transactions_router)
router.include_router(forecast_router)
router.include_router(shadow_invoice_router)
router.include_router(alerts_router)
router.include_router(safe_to_spend_router)

# F2 - Optimizer
router.include_router(optimizer_router)

# F3 - Architect
router.include_router(architect_router)

# F4 - Divider
router.include_router(divider_router)

# F5 - Costs
router.include_router(costs_router)

# F7 - Purchase
router.include_router(purchase_router)

# F13 - Negotiator
router.include_router(negotiator_router)

# M1.3 - Budget
router.include_router(budget_router)

# M1.5 - Subscriptions
router.include_router(subscriptions_router)

# M4.1 - Fiscal
router.include_router(fiscal_router)

# MX.1 - Health Score
router.include_router(health_score_router)

# MX.2 - Goals
router.include_router(goals_router)

# MX.3 - Notifications
router.include_router(notifications_router)

# MX.4 - Peers
router.include_router(peers_router)

# AI Chat Agent
router.include_router(agent_router)

# User Settings
router.include_router(settings_router)

# OPP — Radar de Oportunidades
router.include_router(opportunities_router)

# Defense — Defesa do Consumidor
router.include_router(defense_router)

# Rights — Direitos Esquecidos (T3)
router.include_router(rights_router)

# Tax — Otimização de IR (T1/T2)
router.include_router(tax_router)

# Viral — Savings Card & Wrapped (V1/V2)
router.include_router(viral_router)
