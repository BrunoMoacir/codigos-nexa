from fastapi import APIRouter
from app.api.v1.routes import pluggy_test

router = APIRouter()

# Registra rotas de teste da Pluggy
router.include_router(pluggy_test.router)
# Outras rotas podem ser registradas aqui futuramente