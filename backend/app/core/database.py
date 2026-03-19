from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

# ── Sessão síncrona (psycopg2) — usada por rotas legadas com Session ──
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ── Sessão async (asyncpg) — usada por novas rotas async ─────────────
# Requer DATABASE_URL com prefixo postgresql+asyncpg://
_async_url = settings.DATABASE_URL.replace(
    "postgresql://", "postgresql+asyncpg://"
).replace(
    "postgresql+psycopg2://", "postgresql+asyncpg://"
)
async_engine = create_async_engine(_async_url, echo=False, pool_pre_ping=True)
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
