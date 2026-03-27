#backend/app/core/config.py
import logging
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_logger = logging.getLogger(__name__)

# Resolve .env a partir do diretório backend/, independente do CWD
_backend_dir = Path(__file__).resolve().parents[2]
_env_file = _backend_dir / ".env"

_MOCK_SECRET = "nexa_secret_key_mock_123_do_not_use_in_prod"


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

    # Origens permitidas no CORS.
    # Em produção defina via env: ALLOWED_ORIGINS=["https://app.nexa.com","https://nexa.com"]
    # Padrão "*" só é aceito silenciosamente em development.
    ALLOWED_ORIGINS: list[str] = ["*"]

    # Segurança JWT — OBRIGATÓRIO trocar em produção
    SECRET_KEY: str = _MOCK_SECRET

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

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> "Settings":
        if self.APP_ENV == "production":
            if self.SECRET_KEY == _MOCK_SECRET:
                raise ValueError(
                    "SECRET_KEY não pode ser o valor mock em produção. "
                    "Defina SECRET_KEY como uma string aleatória segura via variável de ambiente."
                )
            if self.ALLOWED_ORIGINS == ["*"]:
                _logger.warning(
                    "[Config] ALLOWED_ORIGINS='*' em produção é inseguro. "
                    "Defina ALLOWED_ORIGINS com as origens permitidas."
                )
        elif self.SECRET_KEY == _MOCK_SECRET:
            _logger.warning(
                "[Config] Usando SECRET_KEY mock. Nunca use este valor em produção."
            )
        return self


settings = Settings()
