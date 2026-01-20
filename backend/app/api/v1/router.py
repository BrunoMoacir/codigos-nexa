from fastapi import APIRouter
from app.api.v1.routes import pluggy_test
from app.api.v1.routes import bank_simulation

router = APIRouter()

# Registra rotas de teste da Pluggy
router.include_router(pluggy_test.router)
# Outras rotas podem ser registradas aqui futuramente
router.include_router(bank_simulation.router) 