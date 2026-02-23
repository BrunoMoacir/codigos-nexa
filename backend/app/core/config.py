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

    model_config = SettingsConfigDict(env_file=".env", extra="forbid")

settings = Settings()
