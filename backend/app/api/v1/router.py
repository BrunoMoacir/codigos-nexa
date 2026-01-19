from fastapi import APIRouter
from app.api.v1.routes import pluggy_test

router = APIRouter()

router.include_router(pluggy_test.router)
# Inclui outras rotas aqui conforme necessário
# registrar a rota no router principal