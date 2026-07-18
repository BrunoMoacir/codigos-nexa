# app/main.py
import logging
import time
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.api.v1.router import router as api_router
from app.api.v1.routes.dashboard import router as dashboard_router
from app.core.config import settings
from app.core.database import Base, engine
from app.core import audit
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
from app.billing.models_orm import UserSubscription  # noqa: F401

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

logger.info("Starting Nexa API")
logger.info("APP_ENV: %s", os.getenv("APP_ENV", "not set"))
logger.info("DATABASE_URL configured: %s", bool(os.getenv("DATABASE_URL")))
logger.info("SECRET_KEY configured: %s", bool(os.getenv("SECRET_KEY")))
logger.info("LLM_PROVIDER: %s", os.getenv("LLM_PROVIDER", "not set"))


def _create_db_tables() -> None:
    """
    Garante que o schema mínimo existe no Postgres. Backoff exponencial.

    ATENÇÃO: `create_all` é adequado apenas para desenvolvimento e ambientes
    de teste. Em produção, use migrações Alembic (`alembic upgrade head`) para
    controlar mudanças de schema de forma incremental e rastreável.
    """
    last_err: Exception | None = None
    for attempt in range(20):
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("DB schema ready (attempt %d)", attempt + 1)
            return
        except Exception as e:
            last_err = e
            wait = min(2 ** attempt, 30)
            logger.warning("DB connection attempt %d/20 failed: %s — retry in %ds", attempt + 1, e, wait)
            time.sleep(wait)
    logger.error("Failed to connect to database after 20 attempts: %s", last_err)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────
    _create_db_tables()

    from app.core.scheduler import scheduler, register_jobs
    if settings.SCHEDULER_ENABLED:
        register_jobs()
        scheduler.start()
        logger.info("[Scheduler] Iniciado com %d jobs", len(scheduler.get_jobs()))
    else:
        logger.info("[Scheduler] Desativado (SCHEDULER_ENABLED=false)")

    yield
    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("Shutting down Nexa API — closing DB and cache connections")

    from app.core.scheduler import scheduler as _scheduler
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Encerrado")
    try:
        engine.dispose()
        logger.info("DB connection pool closed")
    except Exception as e:
        logger.warning("Error closing DB pool: %s", e)
    try:
        from app.core.cache import get_redis
        redis_client = get_redis()
        if redis_client:
            redis_client.close()
            logger.info("Redis connection closed")
    except Exception as e:
        logger.warning("Error closing Redis: %s", e)


# Rate limiter global (por IP) com storage Redis para ser eficaz em múltiplas instâncias.
# Fallback para storage em memória se Redis não estiver configurado.
# default_limits aplica-se a TODAS as rotas que não têm @limiter.limit() próprio.
# Rotas pesadas (forecast, agent) definem seus próprios limites mais restritivos.
try:
    limiter = Limiter(
        key_func=get_remote_address,
        storage_uri=settings.REDIS_URL,
        default_limits=["60/minute"],
    )
    logger.info("Rate limiter: Redis storage (%s), default=60/min", settings.REDIS_URL)
except Exception:
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["60/minute"],
    )
    logger.warning("Rate limiter: in-memory storage (Redis indisponível), default=60/min")

app = FastAPI(
    title="Nexa API",
    version="0.1.0",
    lifespan=lifespan,
)

# Registra o limiter e o handler de erro 429
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — qualquer origem permitida para suportar frontend local e no Railway
# Para restringir em produção, defina ALLOWED_ORIGINS no Railway:
#   ALLOWED_ORIGINS=https://seu-frontend.up.railway.app
_cors_origins = settings.ALLOWED_ORIGINS
if _cors_origins == ["*"] or not _cors_origins:
    _cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Registra as rotas da API v1
app.include_router(api_router, prefix="/api/v1")
app.include_router(dashboard_router)


# Caminhos da documentação interativa — o Swagger UI carrega JS/CSS do
# jsdelivr, então recebem um CSP relaxado (o resto da API recebe o estrito)
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")

_CSP_STRICT = "default-src 'none'; frame-ancestors 'none'"
_CSP_DOCS = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "frame-ancestors 'none'"
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """
    Security headers em toda resposta (auditoria 2026-07).

    - HSTS apenas em produção (em dev não há TLS e o header envenenaria
      o localhost do navegador por max-age).
    - CSP estrito para a API (default-src 'none' — respostas JSON não
      executam nada); relaxado só em /docs e /redoc (Swagger UI usa CDN).
    """
    response = await call_next(request)
    headers = response.headers

    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("X-Frame-Options", "DENY")
    headers.setdefault("Referrer-Policy", "no-referrer")
    headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")

    is_docs = any(request.url.path.startswith(p) for p in _DOCS_PATHS)
    headers.setdefault("Content-Security-Policy", _CSP_DOCS if is_docs else _CSP_STRICT)

    if settings.APP_ENV == "production":
        headers.setdefault(
            "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
        )

    return response


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """
    Middleware de logging estruturado com correlation ID.

    Adiciona X-Request-ID a cada request (gerado ou propagado do cliente)
    e loga método, path, status e tempo de resposta para cada chamada.
    Requests autenticados (Bearer token presente) também geram entrada de auditoria.
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.monotonic()

    response = await call_next(request)

    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info(
        "%s %s → %d  (%.0fms) [req=%s]",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        request_id,
    )
    response.headers["X-Request-ID"] = request_id

    # Gera entrada de auditoria para qualquer request autenticado com Bearer token.
    # O user_id aqui é opaco (não decodificamos o JWT no middleware para evitar
    # duplicação de lógica) — os eventos de auth detalhados ficam em audit.py.
    # Caminhos públicos (/health, /readiness, /version, /auth/*) são excluídos.
    path = request.url.path
    _PUBLIC_PREFIXES = ("/health", "/readiness", "/version", "/api/v1/auth/")
    is_public = any(path.startswith(p) for p in _PUBLIC_PREFIXES)
    has_token = request.headers.get("Authorization", "").startswith("Bearer ")
    if has_token and not is_public:
        ip = request.client.host if request.client else "unknown"
        audit.log_data_access(
            user_id="<token>",
            endpoint=path,
            method=request.method,
            ip=ip,
            status_code=response.status_code,
            request_id=request_id,
        )

    return response


@app.get("/health")
def health():
    """Liveness probe — verifica se o processo está de pé (não depende do banco)."""
    return {"status": "ok", "service": "nexa-api"}


@app.get("/readiness")
def readiness():
    """Readiness probe — retorna 503 se o banco não estiver acessível."""
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        logger.error("Readiness check failed: %s", e)
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "disconnected"},
        )


@app.get("/version")
def version():
    return {"version": "0.1.0"}