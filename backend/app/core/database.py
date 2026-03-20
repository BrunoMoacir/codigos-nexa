from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

# ── Sessão síncrona (psycopg2) — usada por rotas legadas com Session ──
_connect_args = {}
# Evita travar em dev quando Postgres não está disponível
if settings.DATABASE_URL.startswith("postgresql"):
    _connect_args = {"connect_timeout": 2}

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    connect_args=_connect_args,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ── Sessão async (asyncpg) — usada por novas rotas async ─────────────
# Requer DATABASE_URL com prefixo postgresql+asyncpg://
_async_url = settings.DATABASE_URL.replace(
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
