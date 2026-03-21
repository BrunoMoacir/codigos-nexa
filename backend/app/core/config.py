#backend/app/core/config.py
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Resolve .env a partir do diretório backend/, independente do CWD
_backend_dir = Path(__file__).resolve().parents[2]
_env_file = _backend_dir / ".env"


class Settings(BaseSettings):
    """Centraliza todas as variáveis de ambiente do projeto."""

    model_config = SettingsConfigDict(
        env_file=str(_env_file) if _env_file.exists() else None,
        extra="ignore",
    )

    # Credenciais da Pluggy (opcionais em dev — rotas Pluggy falham se vazio)
    PLUGGY_CLIENT_ID: str = ""
    PLUGGY_CLIENT_SECRET: str = ""

    # URL base da Pluggy (sandbox ou produção)
    PLUGGY_BASE_URL: str = "https://api.pluggy.ai"

    # URL base do frontend (usada como fallback no redirect de reconexão)
    FRONTEND_BASE_URL: str = "http://localhost:8501"

    # Segurança JWT — OBRIGATÓRIO trocar em produção
    SECRET_KEY: str = "nexa_secret_key_mock_123_do_not_use_in_prod"

    # LLM Settings (opcional)
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    LLM_PROVIDER: str = "openai"   # "openai" | "anthropic"
    LLM_MODEL: str = "gpt-4o-mini" # ou "claude-sonnet-4-6"

    # DB (em dev, podemos cair para DuckDB se o Postgres não estiver acessível)
    DATABASE_URL: str = "postgresql+psycopg2://nexa_user:nexa_secret@localhost:5432/nexa_db"

    # Cache / Sessões do agente
    REDIS_URL: str = "redis://redis:6379/0"

    # Ambiente
    APP_ENV: str = "development"   # "development" | "production"
    LOG_LEVEL: str = "INFO"


settings = Settings()
