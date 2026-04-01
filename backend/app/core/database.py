from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

# ── Sessão síncrona (psycopg2) — usada por rotas legadas com Session ──
_connect_args = {}

# Corrigir DATABASE_URL se Railway fornecer postgresql:// sem o driver
_database_url = settings.DATABASE_URL
if _database_url.startswith("postgresql://") and "+psycopg2://" not in _database_url:
    _database_url = _database_url.replace("postgresql://", "postgresql+psycopg2://", 1)

# Evita travar em dev quando Postgres não está disponível
if _database_url.startswith("postgresql"):
    _connect_args = {"connect_timeout": 2}

engine = create_engine(
    _database_url,
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    connect_args=_connect_args,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ── Sessão async (asyncpg) — usada por novas rotas async ─────────────
# Requer DATABASE_URL com prefixo postgresql+asyncpg://
_async_url = _database_url.replace(
    "postgresql://", "postgresql+asyncpg://"
).replace(
    "postgresql+psycopg2://", "postgresql+asyncpg://"
)
_async_connect_args = {}
if _async_url.startswith("postgresql"):
    _async_connect_args = {"timeout": 2}

async_engine = create_async_engine(
    _async_url,
    echo=False,
    pool_pre_ping=True,
    connect_args=_async_connect_args,
)
AsyncSessionLocal = sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False
)

# Base Declarativa para os modelos do ORM
Base = declarative_base()


def get_db():
    """Dependency síncrona — para rotas legadas."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> AsyncSession:
    """Dependency async — para novas rotas."""
    async with AsyncSessionLocal() as session:
        yield session
