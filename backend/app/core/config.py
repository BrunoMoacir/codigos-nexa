from pydantic_settings import BaseSettings
# – Centraliza configs
# – Facilita Docker, CI, produção

class Settings(BaseSettings):
    # Credenciais da Pluggy, guardadas no .env
    PLUGGY_CLIENT_ID: str
    PLUGGY_CLIENT_SECRET: str

    class Config:
        env_file = ".env"  # Diz ao Pydantic para ler o .env


# Instância global de configuração
settings = Settings()
