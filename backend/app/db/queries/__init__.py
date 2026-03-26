# app/db/queries/__init__.py
# LEGACY COMPATIBILITY LAYER
# All queries have moved to app.core.db.queries and feature-specific modules

from app.core.db.queries import (
    get_connection,
    get_context_overrides,
    save_context_override,
    get_override_stats,
    save_transactions_clean,
    save_health_score_snapshot,
    get_health_score_history,
    get_transactions_for_user,
)

__all__ = [
    "get_connection",
    "get_context_overrides",
    "save_context_override",
    "get_override_stats",
    "save_transactions_clean",
    "save_health_score_snapshot",
    "get_health_score_history",
    "get_transactions_for_user",
]
