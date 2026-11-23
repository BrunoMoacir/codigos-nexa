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

    # URL base do frontend React (links de e-mail, retorno do Stripe e da
    # reconexão Open Finance). O padrão era a porta 8501 do Streamlit de
    # demonstração, e o link "redefinir senha" do e-mail abria uma tela que
    # não tem essa rota.
    FRONTEND_BASE_URL: str = "http://localhost:3000"

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

    # Billing — Stripe (assinaturas Pro/Total)
    # BILLING_ENFORCEMENT_ENABLED=false → dark launch: gating só loga
    # ("would_block"), nada é bloqueado. Ligar em produção após o lançamento.
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    # IDs dos Prices. Opcionais: vazios, o cliente resolve pelos lookup_keys
    # que o scripts/stripe_setup.py cria (hive_pro_mensal / hive_total_mensal).
    STRIPE_PRICE_PRO_MONTHLY: str = ""
    STRIPE_PRICE_TOTAL_MONTHLY: str = ""
    # Versão da API fixada em toda chamada. A 2025-03-31.basil tirou
    # current_period_end da assinatura e `subscription` da fatura; fixar a
    # versão (e ler os dois formatos) impede que um upgrade da conta mude os
    # campos que o webhook lê.
    STRIPE_API_VERSION: str = "2024-06-20"
    # Configuração do portal do cliente (bpc_…) criada pelo stripe_setup.py:
    # troca Pro↔Total, cancelamento no fim do período, troca de cartão.
    # Vazia, o Stripe usa a configuração padrão da conta.
    STRIPE_PORTAL_CONFIGURATION: str = ""
    # Só vale com o Stripe configurado (chave + segredo do webhook): ligar sem
    # isso bloquearia usuários sem nenhum caminho para pagar — ver gating.py.
    BILLING_ENFORCEMENT_ENABLED: bool = False

    # SERPRO — API Consulta Restituição IRPF (T3)
    # Trial usa o bearer público de demonstração do SERPRO; produção exige
    # consumer key/secret contratados na Loja SERPRO. A chave privada (DER
    # PKCS#8 em base64, arquivo `chave-privada` do e-CNPJ) decripta os campos.
    SERPRO_RESTITUICAO_TRIAL: bool = False
    SERPRO_CONSUMER_KEY: str = ""
    SERPRO_CONSUMER_SECRET: str = ""
    SERPRO_RESTITUICAO_PRIVATE_KEY_B64: str = ""

    # Email — remetente padrão
    EMAIL_FROM: str = "noreply@nexa.app"
    EMAIL_FROM_NAME: str = "Nexa"

    # Backend SMTP (dev / self-hosted)
    # Deixar SMTP_HOST vazio desativa o backend SMTP.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""

    # Backend SendGrid (produção recomendado)
    # Tem precedência sobre SMTP quando definido.
    SENDGRID_API_KEY: str | None = None

    # Segredo do webhook de transações (Pluggy → /transactions/webhook).
    # Configure a URL do webhook no painel Pluggy com ?token=<este valor>
    # ou envie o header X-Webhook-Token. Em produção, webhook SEM segredo
    # configurado é recusado (fail-closed).
    PLUGGY_WEBHOOK_SECRET: str = ""

    # Webhook item/* da Pluggy dispara um job de sync quando não há nenhum
    # em andamento (o usuário conectou o banco e fechou o app). Desligue
    # para sincronizar apenas sob demanda.
    PLUGGY_AUTOSYNC_ON_WEBHOOK: bool = True

    # Sync incremental: quantos dias ANTES da última transação salva o sync
    # pede de novo à Pluggy. A janela existe porque lançamento não é imutável
    # — PENDING vira POSTED, valor de cartão muda, e o banco publica compra
    # retroativa. Tudo é upsert por transaction_id, então reler é barato e
    # seguro; o que a janela não cobrir só entra num sync completo.
    # 0 = sempre completo (mais caro, cobre retroatividade ilimitada).
    PLUGGY_SYNC_LOOKBACK_DAYS: int = 7

    # Web Push (PWA — R1.d). Gerar par VAPID com:
    #   python3 -c "from py_vapid import Vapid; v=Vapid(); v.generate_keys(); \
    #               print(v.private_pem()); print(v.public_pem())"
    # ou `npx web-push generate-vapid-keys`. Vazio desativa o canal push.
    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""
    VAPID_CLAIMS_EMAIL: str = "mailto:noreply@nexa.app"
    # Push nativo (app Android/iOS) via Firebase Cloud Messaging HTTP v1:
    # JSON da conta de serviço do Firebase em base64. SEGREDO — só no
    # gerenciador de segredos do deploy. Vazio = push nativo desligado.
    FCM_SERVICE_ACCOUNT_B64: str = ""

    # ── Observabilidade ───────────────────────────────────────────────────
    # Vazio = desligado. O SDK já estava instalado e nunca era inicializado:
    # o audit registrava eventos de negócio, mas erro de produção não alertava
    # ninguém. `send_default_pii=False` é o padrão e fica explícito: os dados
    # deste produto são extrato bancário, não podem ir para telemetria.
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

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
