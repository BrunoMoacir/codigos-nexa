# app/core/db/__init__.py
# Shared database utilities

from .session import get_db, get_async_db, SessionLocal, AsyncSessionLocal, engine, async_engine, Base
from .queries import (
    get_transactions_for_user,
    save_transactions_clean,
    get_context_overrides,
    save_context_override,
    save_health_score_snapshot,
    get_health_score_history,
    get_override_stats,
)
from .users import get_user_by_email, create_user

__all__ = [
    "get_db",
    "get_async_db",
    "SessionLocal",
    "AsyncSessionLocal",
    "engine",
    "async_engine",
    "Base",
    "get_transactions_for_user",
    "save_transactions_clean",
    "get_context_overrides",
    "save_context_override",
    "save_health_score_snapshot",
    "get_health_score_history",
    "get_override_stats",
    "get_user_by_email",
    "create_user",
]
