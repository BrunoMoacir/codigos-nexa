# app/main.py
import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.api.v1.router import router as api_router
from app.api.v1.routes.dashboard import router as dashboard_router
from app.core.database import Base, engine
from fastapi.middleware.cors import CORSMiddleware

# Importa modelos para registrar no metadata (necessário para create_all)
from app.core.models.user import User  # noqa: F401
from app.core.models.transaction import Transaction  # noqa: F401
from app.goals.models import FinancialGoal  # noqa: F401
from app.health_score.models import HealthScoreHistory  # noqa: F401
from app.divider.models import ContextOverride  # noqa: F401
from app.optimizer.models_orm import OptimizationReport  # noqa: F401
from app.architect.models_orm import ArchitectSimulation, ArchitectSimulationMetrics  # noqa: F401
from app.core.models.pluggy_item import PluggyItem  # noqa: F401

logger = logging.getLogger(__name__)

# Rate limiter global (por IP)
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Nexa API",
    version="0.1.0"
)

# Registra o limiter e o handler de erro 429
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registra as rotas da API v1
app.include_router(api_router, prefix="/api/v1")

app.include_router(dashboard_router)


@app.on_event("startup")
def _startup_create_tables() -> None:
    """Garante que o schema mínimo existe no Postgres (dev/local, idempotente)."""
    last_err: Exception | None = None
    for _ in range(15):
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("DB schema ready")
            return
        except Exception as e:
            last_err = e
            time.sleep(1)
    raise last_err  # fail fast se o DB não sobe


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"version": "0.1.0"}