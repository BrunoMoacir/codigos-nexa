from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

# Corrigir DATABASE_URL se Railway fornecer postgresql:// sem o driver
_database_url = settings.DATABASE_URL
if _database_url.startswith("postgresql://") and "+psycopg2://" not in _database_url:
    _database_url = _database_url.replace("postgresql://", "postgresql+psycopg2://", 1)

_is_sqlite = _database_url.startswith("sqlite")

# SQLite não suporta pool_size/max_overflow nem connect_timeout
if _is_sqlite:
    engine = create_engine(
        _database_url,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_engine(
        _database_url,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        connect_args={"connect_timeout": 2},
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ── Sessão async ──────────────────────────────────────────────────────
if _is_sqlite:
    _async_url = _database_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    async_engine = create_async_engine(_async_url, echo=False)
else:
    _async_url = _database_url.replace(
        "postgresql://", "postgresql+asyncpg://"
    ).replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )
    async_engine = create_async_engine(
        _async_url,
        echo=False,
        pool_pre_ping=True,
        connect_args={"timeout": 2},
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
