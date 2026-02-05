"""
app/api/v1/router.py - Router principal da API v1

Registra todas as rotas disponíveis.
"""

from fastapi import APIRouter
from app.api.v1.routes import analyze

# Importar rotas existentes
from app.api.v1.routes import pluggy_test, bank_simulation

# ✅ NOVA: Importar rota de transactions
from app.api.v1.routes import transactions

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CRIAR ROUTER PRINCIPAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

router = APIRouter()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REGISTRAR ROTAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Rotas de teste (desenvolvimento)
router.include_router(pluggy_test.router)
router.include_router(bank_simulation.router)

router.include_router(analyze.router)


# ✅ NOVA: Rota de transações (produção - webhook Pluggy)
router.include_router(transactions.router)