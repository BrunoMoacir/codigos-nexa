#backend/app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centraliza todas as variáveis de ambiente do projeto
    """

    # Credenciais da Pluggy
    PLUGGY_CLIENT_ID: str
    PLUGGY_CLIENT_SECRET: str

    # URL base da Pluggy (sandbox ou produção)
    PLUGGY_BASE_URL: str = "https://api.pluggy.ai"

    # URL base do frontend (usada como fallback no redirect de reconexão)
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    # Segurança JWT — OBRIGATÓRIO trocar em produção
    SECRET_KEY: str = "nexa_secret_key_mock_123_do_not_use_in_prod"

    # LLM Settings
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    LLM_PROVIDER: str = "openai"   # "openai" | "anthropic"
    LLM_MODEL: str = "gpt-4o-mini" # ou "claude-sonnet-4-6"

    # DB
    DATABASE_URL: str

    # Cache / Sessões do agente
    REDIS_URL: str = "redis://redis:6379/0"

    # Ambiente
    APP_ENV: str = "development"   # "development" | "production"
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
