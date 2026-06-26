#backend/app/core/config.py
import logging
import re
from pathlib import Path
from typing import Annotated

from pydantic import BeforeValidator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Apenas origens localhost reais são permitidas como fallback em produção.
# Rejeita padrões como http://localhost-prod.com ou http://localhost.evil.com.
_LOCALHOST_RE = re.compile(r'^https?://localhost(:\d+)?$')


def parse_cors_origins(value):
    """Parse ALLOWED_ORIGINS - aceita tanto string quanto lista."""
    if isinstance(value, str):
        # Se for string única, converte pra lista
        if value.strip() in ("*", '["*"]'):
            return ["*"]
        # Se começar com [, tenta parsear como JSON
        if value.startswith("["):
            import json
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else [value]
            except Exception:
                # Se falhar, trata como string única
                return [v.strip() for v in value.split(",") if v.strip()]
        # String separada por vírgula
        return [v.strip() for v in value.split(",") if v.strip()]
    return value

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

    # URL do Widget Pluggy Connect (onde o usuário conecta sua conta)
    PLUGGY_CONNECT_URL: str = "https://connect.pluggy.ai"

    # URL base do frontend (usada como fallback no redirect de reconexão)
    FRONTEND_BASE_URL: str = "http://localhost:8501"

    # Origens permitidas no CORS.
    # Aceita formatos: "*", "https://a.com,https://b.com", ou ["https://a.com","https://b.com"]
    # Padrão "*" só é aceito silenciosamente em development.
    ALLOWED_ORIGINS: Annotated[list[str], BeforeValidator(parse_cors_origins)] = ["*"]

    # Segurança JWT — OBRIGATÓRIO trocar em produção
    SECRET_KEY: str = _MOCK_SECRET

    # LLM Settings (opcional)
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    LLM_PROVIDER: str = "openai"   # "openai" | "anthropic"
    LLM_MODEL: str = "gpt-4o-mini" # ou "claude-haiku-4-5-20251001"

    # DB (em dev, podemos cair para DuckDB se o Postgres não estiver acessível)
    DATABASE_URL: str = "postgresql+psycopg2://nexa_user:nexa_secret@localhost:5432/nexa_db"

    # Cache / Sessões do agente
    REDIS_URL: str = "redis://redis:6379/0"

    # Pool de conexões do banco — ajuste conforme número de workers uvicorn
    # Regra geral: pool_size >= número de workers; max_overflow é burst extra
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # Ambiente
    APP_ENV: str = "development"   # "development" | "production"
    LOG_LEVEL: str = "INFO"

    # Scheduler de jobs periódicos
    # False em development — jobs não sobem automaticamente.
    # True em produção para ativar fee_snapshot, opportunity_scan, etc.
    SCHEDULER_ENABLED: bool = False

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> "Settings":
        if self.APP_ENV == "production":
            if self.SECRET_KEY == _MOCK_SECRET:
                raise ValueError(
                    "SECRET_KEY não pode ser o valor mock em produção. "
                    "Defina SECRET_KEY como uma string aleatória segura via variável de ambiente."
                )
            if self.ALLOWED_ORIGINS == ["*"]:
                fallback_origin = (self.FRONTEND_BASE_URL or "").strip().rstrip("/")
                if fallback_origin and not _LOCALHOST_RE.match(fallback_origin):
                    self.ALLOWED_ORIGINS = [fallback_origin]
                    _logger.warning(
                        "[Config] APP_ENV=production e ALLOWED_ORIGINS='*'. "
                        "Aplicando fallback seguro com FRONTEND_BASE_URL=%s",
                        fallback_origin,
                    )
                else:
                    raise ValueError(
                        "ALLOWED_ORIGINS='*' não é permitido em produção. "
                        "Defina ALLOWED_ORIGINS com as origens explícitas do frontend, "
                        "ex: ALLOWED_ORIGINS=[\"https://app.nexa.com\"]"
                    )
        else:
            if self.SECRET_KEY == _MOCK_SECRET:
                _logger.warning(
                    "[Config] Usando SECRET_KEY mock. Nunca use este valor em produção."
                )
            if self.ALLOWED_ORIGINS == ["*"]:
                _logger.warning(
                    "[Config] ALLOWED_ORIGINS='*' — aceitável em desenvolvimento, "
                    "mas defina origens explícitas antes de ir para produção."
                )
        return self


settings = Settings()
