# app/main.py
import logging
import time
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.api.v1.router import router as api_router
from app.api.v1.routes.dashboard import router as dashboard_router
from app.core.config import settings
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

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Log de informações importantes para debug no Railway
logger.info(f"🚀 Starting Nexa API")
logger.info(f"📦 Python version: {os.sys.version}")
logger.info(f"🌍 APP_ENV: {os.getenv('APP_ENV', 'not set')}")
logger.info(f"🔗 DATABASE_URL configured: {bool(os.getenv('DATABASE_URL'))}")
logger.info(f"🔑 SECRET_KEY configured: {bool(os.getenv('SECRET_KEY'))}")
logger.info(f"🤖 LLM_PROVIDER: {os.getenv('LLM_PROVIDER', 'not set')}")
logger.info(f"🚪 PORT: {os.getenv('PORT', '8000')}")

# Rate limiter global (por IP)
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Nexa API",
    version="0.1.0"
)

# Registra o limiter e o handler de erro 429
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — origens controladas por ALLOWED_ORIGINS no .env
# Em produção defina: ALLOWED_ORIGINS=["https://app.nexa.com"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
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
    # Railway pode levar até 60 segundos para conectar o banco
    for attempt in range(60):
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("DB schema ready")
            return
        except Exception as e:
            last_err = e
            logger.warning(f"DB connection attempt {attempt + 1}/60 failed: {e}")
            time.sleep(1)
    logger.error(f"Failed to connect to database after 60 attempts: {last_err}")
    # Não falhar completamente - deixar a API subir mesmo sem DB
    # Isso permite que o health check do Railway passe


@app.get("/health")
def health():
    """Health check endpoint - não depende do banco de dados"""
    return {"status": "ok", "service": "nexa-api"}


@app.get("/readiness")
def readiness():
    """Verifica se a API está pronta (incluindo banco de dados)"""
    try:
        # Tenta fazer uma query simples no banco
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "disconnected", "error": str(e)}
        )


@app.get("/version")
def version():
    return {"version": "0.1.0"}