# Re-export from canonical location so alembic env.py resolves correctly.
# Importing app.core.models.base registers all ORM models as a side effect.
from app.core.models.base import Base  # noqa: F401
