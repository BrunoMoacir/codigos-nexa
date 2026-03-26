# app/db/session.py
# Re-exporta as sessions do database.py como ponto central de acesso
from app.core.database import (
    get_db,
    get_async_db,
    SessionLocal,
    AsyncSessionLocal,
    engine,
    async_engine,
    Base,
)
