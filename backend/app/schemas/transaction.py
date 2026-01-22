"""
transaction.py - Schemas Pydantic para Transações Open Finance

Responsabilidades (CAMADA 1 - Firewall Semântico):
    ✅ Validação estrutural mínima
    ✅ Parsing robusto (múltiplos formatos BR/US)
    ✅ Validação tolerante (rejeita item, não batch)
    ✅ Segurança (limites, sanitização)
    ✅ Metadados para BankStrategy (institution_id, item_id)
    ❌ NÃO faz validação semântica pesada (Polars)
    ❌ NÃO aplica BankStrategy diretamente (Polars)

Fluxo completo:
    Open Finance JSON (Pluggy/Belvo)
        ↓
    FastAPI Webhook
        ↓
    TransactionWebhook (validação Pydantic) ← ESTAMOS AQUI
        ↓
    raw_events (S3) + metadata (Postgres)
        ↓
    Message Queue (Redis)
        ↓
    Polars Ingestor (normalização + BankStrategy)
        ↓
    transactions_clean (Postgres)
        ↓
    TransactionOut (API response)

Versão: 1.2.0
Última atualização: 2024-01-21
"""

import re
import html
import logging
from datetime import datetime, timezone, date
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
    ConfigDict,
    ValidationError
)

# Importar enums do módulo compartilhado
from .enums import (
    DataSource,
    DataStatus,
    TransactionStatus,
    Currency,
    get_field_importance,
    is_field_required,
    get_required_fields
)

# Configurar logger
logger = logging.getLogger(__name__)


# ==========================================
# CONSTANTES
# ==========================================

# Limites de segurança (prevenir DoS e valores absurdos)
MAX_AMOUNT = Decimal("1_000_000_000")  # 1 bilhão BRL
MAX_DESCRIPTION_LENGTH = 500           # Prevenir strings gigantes
MAX_TRANSACTION_ID_LENGTH = 255        # IDs padrão DB
MAX_INSTALLMENTS = 60                  # 5 anos de parcelamento (extremo)

# Thresholds de alerta (TransactionBatchResult)
REJECTION_WARNING_THRESHOLD = 0.20   # 20% de rejeição → WARNING
REJECTION_CRITICAL_THRESHOLD = 1.0   # 100% de rejeição → CRITICAL

# Regex patterns (compilados uma vez para performance)
AMOUNT_PATTERN = re.compile(
    r"""
    ^\s*                      # Whitespace inicial
    [-+]?                     # Sinal opcional
    (?:R\$\s*)?               # "R$" opcional (BR)
    \(?                       # Parênteses opcional (negativo contábil)
    (\d{1,3}(?:[.,]\d{3})*    # Parte inteira com separadores
    (?:[.,]\d{1,2})?)         # Parte decimal opcional
    \)?                       # Fecha parênteses
    \s*$                      # Whitespace final
    """,
    re.VERBOSE
)

# Controles ASCII perigosos (0x00-0x1F exceto \t, \n, \r)
CONTROL_CHARS = "".join(
    chr(i) for i in range(32) if i not in (9, 10, 13)
)
CONTROL_CHARS_PATTERN = re.compile(f"[{re.escape(CONTROL_CHARS)}]")


# ==========================================
# HELPERS DE PARSING
# ==========================================

def sanitize_text(text: str, max_length: int = MAX_DESCRIPTION_LENGTH) -> str:
    """
    Sanitiza texto removendo controles perigosos e limitando tamanho.
    
    Proteções:
        1. Limita tamanho ANTES de processar (previne ReDoS)
        2. Remove controles ASCII (0x00-0x1F exceto tab/newline/CR)
        3. Normaliza espaços consecutivos
        4. Escapa HTML (previne XSS se exibido em UI)
        5. Remove leading/trailing whitespace
    
    Args:
        text: Texto a sanitizar
        max_length: Tamanho máximo (default: 500)
    
    Returns:
        Texto sanitizado e seguro
    
    Example:
        >>> sanitize_text("PAG  UBER\x00\x01VIAGEM")
        "PAG UBER VIAGEM"
        
        >>> sanitize_text("<script>alert('xss')</script>")
        "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;"
        
        >>> sanitize_text("A" * 600, max_length=100)
        "AAAA...AAA"  # (100 chars)
    """
    if not isinstance(text, str):
        return ""
    
    # 1. Truncar ANTES de processar (segurança)
    if len(text) > max_length:
        text = text[:max_length]
    
    # 2. Remover controles ASCII perigosos
    text = CONTROL_CHARS_PATTERN.sub("", text)
    
    # 3. Normalizar espaços (múltiplos → único)
    text = re.sub(r"\s+", " ", text)
    
    # 4. Escapar HTML
    text = html.escape(text)
    
    # 5. Strip
    return text.strip()


def parse_amount_safe(v: Any, field_name: str = "amount") -> Decimal:
    """
    Parser seguro de valores monetários (robusto para formatos BR/US).
    
    Aceita:
        - Decimal: Decimal("150.50")
        - Float: 150.50
        - Int: 150
        - String BR: "150,50", "1.500,50", "R$ 150,50"
        - String US: "150.50", "1,500.50", "$150.50"
        - Contábil: "(150.50)" → -150.50 (negativo)
    
    Args:
        v: Valor a parsear
        field_name: Nome do campo (para mensagens de erro)
    
    Returns:
        Decimal validado e normalizado
    
    Raises:
        ValueError: se valor for zero, negativo demais, ou formato inválido
    
    Example:
        >>> parse_amount_safe(150.50, "amount")
        Decimal('150.50')
        
        >>> parse_amount_safe("1.500,50", "amount")
        Decimal('1500.50')
        
        >>> parse_amount_safe("(150.50)", "amount")
        Decimal('-150.50')
        
        >>> parse_amount_safe(0, "amount")
        ValueError: amount não pode ser zero
    """
    # Já é Decimal válido
    if isinstance(v, Decimal):
        amount = v
    
    # Numérico simples
    elif isinstance(v, (int, float)):
        amount = Decimal(str(v))
    
    # String → parsing robusto
    elif isinstance(v, str):
        v = v.strip()
        
        # Vazio
        if not v:
            raise ValueError(f"{field_name} está vazio")
        
        # Detectar negativo contábil: (150.50)
        is_negative_accounting = v.startswith("(") and v.endswith(")")
        if is_negative_accounting:
            v = v[1:-1]  # Remove parênteses
        
        # Remove símbolos monetários
        v = v.replace("R$", "").replace("$", "").strip()
        
        # Detectar formato (BR usa vírgula decimal, US usa ponto)
        # Heurística: se tem vírgula seguida de 2 dígitos no final → BR
        is_br_format = bool(re.search(r",\d{2}$", v))
        
        if is_br_format:
            # BR: 1.500,50 → 1500.50
            v = v.replace(".", "")  # Remove separador de milhar
            v = v.replace(",", ".")  # Vírgula vira ponto decimal
        else:
            # US: 1,500.50 → 1500.50
            v = v.replace(",", "")  # Remove separador de milhar
        
        # Converte para Decimal
        try:
            amount = Decimal(v)
        except (InvalidOperation, ValueError) as e:
            raise ValueError(
                f"{field_name} tem formato inválido: {v!r} (erro: {e})"
            )
        
        # Aplica sinal negativo contábil
        if is_negative_accounting:
            amount = -amount
    
    else:
        raise ValueError(
            f"{field_name} deve ser número ou string, recebido: {type(v).__name__}"
        )
    
    # Validações de negócio
    if amount == 0:
        raise ValueError(f"{field_name} não pode ser zero")
    
    if abs(amount) > MAX_AMOUNT:
        raise ValueError(
            f"{field_name} excede limite ({MAX_AMOUNT}): {amount}"
        )
    
    return amount


def parse_date_safe(v: Any, field_name: str = "date") -> datetime:
    """
    Parser seguro de datas/timestamps (SEMPRE retorna UTC).
    
    Aceita:
        - datetime: datetime.now()
        - date: date.today() → converte para datetime UTC
        - ISO 8601: "2024-01-15T10:30:00Z", "2024-01-15T10:30:00.000Z"
        - BR: "15/01/2024", "15/01/2024 10:30:00"
        - US: "2024-01-15", "2024-01-15 10:30:00"
    
    Args:
        v: Valor a parsear
        field_name: Nome do campo (para mensagens de erro)
    
    Returns:
        datetime timezone-aware (UTC)
    
    Raises:
        ValueError: se formato for inválido
    
    Example:
        >>> parse_date_safe("2024-01-15T10:30:00Z", "date")
        datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        
        >>> parse_date_safe("15/01/2024", "date")
        datetime(2024, 1, 15, 0, 0, tzinfo=timezone.utc)
        
        >>> parse_date_safe(date(2024, 1, 15), "date")
        datetime(2024, 1, 15, 0, 0, tzinfo=timezone.utc)
    """
    # Já é datetime
    if isinstance(v, datetime):
        dt = v
        # Garante timezone-aware (UTC)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    
    # date → datetime UTC (00:00)
    if isinstance(v, date):
        return datetime.combine(v, datetime.min.time(), tzinfo=timezone.utc)
    
    # String → parsing robusto
    if isinstance(v, str):
        v = v.strip()
        
        if not v:
            raise ValueError(f"{field_name} está vazio")
        
        # Trata ISO 8601 com milissegundos (Pluggy usa isso)
        # "2024-01-15T10:30:00.000Z" → remove .000 antes de parsear
        v_clean = re.sub(r"\.\d{3}Z$", "Z", v)
        
        # Tenta formatos em ordem de probabilidade (Pluggy primeiro)
        formats = [
            "%Y-%m-%dT%H:%M:%SZ",       # ISO 8601 UTC (Pluggy)
            "%Y-%m-%dT%H:%M:%S%z",      # ISO 8601 com timezone
            "%Y-%m-%d",                 # ISO date (Pluggy usa para "date")
            "%Y-%m-%d %H:%M:%S",        # US datetime
            "%d/%m/%Y %H:%M:%S",        # BR datetime
            "%d/%m/%Y",                 # BR date
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(v_clean, fmt)
                # Adiciona UTC se naive
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except ValueError:
                continue
        
        # Nenhum formato funcionou
        raise ValueError(
            f"{field_name} tem formato inválido: {v!r}. "
            f"Formatos aceitos: ISO 8601, YYYY-MM-DD, DD/MM/YYYY"
        )
    
    raise ValueError(
        f"{field_name} deve ser datetime, date ou string, "
        f"recebido: {type(v).__name__}"
    )


def parse_status_safe(v: Any) -> TransactionStatus:
    """
    Parser seguro de status de transação.
    
    Aceita:
        - Enum: TransactionStatus.POSTED
        - String: "POSTED", "posted", "Posted"
        - None/vazio: retorna POSTED (fallback seguro)
        - Aliases: "PROCESSED" → POSTED, "COMPLETED" → POSTED
    
    Args:
        v: Valor a parsear
    
    Returns:
        TransactionStatus validado
    
    Raises:
        ValueError: se tipo for inválido (não string/enum/None)
    
    Rationale:
        - Pluggy: envia "POSTED"
        - Belvo: envia "PROCESSED" (diferente!)
        - CSV: pode vir vazio ou lowercase
        - Fallback tolerante: POSTED (mais comum)
    
    Example:
        >>> parse_status_safe("posted")
        TransactionStatus.POSTED
        
        >>> parse_status_safe("PROCESSED")
        TransactionStatus.POSTED  # Belvo alias
        
        >>> parse_status_safe(None)
        TransactionStatus.POSTED  # Fallback
        
        >>> parse_status_safe("canceled")
        TransactionStatus.CANCELLED  # Normaliza US → UK
    """
    # Já é enum válido
    if isinstance(v, TransactionStatus):
        return v
    
    # None ou vazio → fallback POSTED (tolerante)
    if v is None or v == "":
        return TransactionStatus.POSTED
    
    # String → normalizar e mapear
    if isinstance(v, str):
        v_upper = v.strip().upper()
        
        # Mapeamento direto (tenta primeiro)
        try:
            return TransactionStatus(v_upper)
        except ValueError:
            pass
        
        # Aliases de outros conectores (Belvo, etc)
        aliases = {
            "PROCESSED": TransactionStatus.POSTED,
            "COMPLETED": TransactionStatus.POSTED,
            "SETTLED": TransactionStatus.POSTED,
            "CANCELED": TransactionStatus.CANCELLED,  # US → UK
        }
        
        if v_upper in aliases:
            return aliases[v_upper]
        
        # Status desconhecido → logar e usar POSTED (tolerante, não quebra)
        logger.warning(
            "unknown_transaction_status",
            extra={
                "status": v,
                "fallback": "POSTED"
            }
        )
        return TransactionStatus.POSTED
    
    # Tipo completamente inesperado
    raise ValueError(
        f"Status deve ser string, TransactionStatus ou None. "
        f"Recebido: {type(v).__name__}"
    )


# ==========================================
# SCHEMAS
# ==========================================

class TransactionWebhook(BaseModel):
    """
    Schema de ENTRADA para webhooks Open Finance.
    
    Responsabilidade (CAMADA 1 - Pydantic):
        ✅ Firewall semântico (validação estrutural)
        ✅ Parsing robusto de múltiplos formatos
        ✅ Fallbacks explícitos
        ❌ NÃO faz validação semântica pesada (Polars faz)
    
    Próxima camada:
        → raw_events (S3) → Polars Ingestor → transactions_clean
    
    Metadados (set pelo webhook receiver):
        - institution_id: inferido de connector.id
        - item_id: de item.id
        - fetched_at: timestamp do webhook
    """
    
    # ==========================================
    # 1️⃣ FUNDAMENTAL (não-negociáveis)
    # ==========================================
    
    transaction_id: str = Field(
        ...,
        max_length=MAX_TRANSACTION_ID_LENGTH,
        description="ID único da transação (Pluggy: 'id')"
    )
    
    amount: Decimal = Field(
        ...,
        description="Valor da transação (negativo = débito, positivo = crédito)"
    )
    
    transaction_date: datetime = Field(
        ...,
        description="Data da transação (SEMPRE UTC timezone-aware)"
    )
    
    account_id: str = Field(
        ...,
        max_length=MAX_TRANSACTION_ID_LENGTH,
        description="ID da conta (Pluggy: 'accountId')"
    )
    
    # ==========================================
    # 2️⃣ CRÍTICO MAS SUBSTITUÍVEL (fallback possível)
    # ==========================================
    
    description: str = Field(
        default="",
        max_length=MAX_DESCRIPTION_LENGTH,
        description=(
            "Descrição da transação. "
            "Fallback: description → description_raw → observations"
        )
    )
    
    balance: Decimal | None = Field(
        default=None,
        description=(
            "Saldo após transação (opcional). "
            "Se None, Polars estima via cumsum."
        )
    )
    
    # ==========================================
    # 3️⃣ MELHORADORES (aumentam confiança)
    # ==========================================
    
    category: str | None = Field(
        default=None,
        description="Categoria (Pluggy/Belvo pode enviar)"
    )
    
    merchant: str | None = Field(
        default=None,
        max_length=MAX_DESCRIPTION_LENGTH,
        description="Nome do estabelecimento"
    )
    
    status: TransactionStatus = Field(
        default=TransactionStatus.POSTED,
        description="Status da transação (POSTED, PENDING, CANCELLED)"
    )
    
    # ==========================================
    # 4️⃣ METADADOS ADICIONAIS
    # ==========================================
    
    currency: Currency = Field(
        default=Currency.BRL,
        description="Moeda (MVP: apenas BRL)"
    )
    
    description_raw: str | None = Field(
        default=None,
        max_length=MAX_DESCRIPTION_LENGTH,
        description="Descrição original sem processamento"
    )
    
    observations: str | None = Field(
        default=None,
        max_length=MAX_DESCRIPTION_LENGTH,
        description="Observações adicionais"
    )
    
    merchant_details: dict[str, Any] | None = Field(
        default=None,
        description="Detalhes extras do merchant (JSON)"
    )
    
    installment_number: int | None = Field(
        default=None,
        ge=1,
        le=MAX_INSTALLMENTS,
        description="Número da parcela atual (1-60)"
    )
    
    installment_total: int | None = Field(
        default=None,
        ge=1,
        le=MAX_INSTALLMENTS,
        description="Total de parcelas (1-60)"
    )
    
    # ==========================================
    # 5️⃣ RASTREABILIDADE (para BankStrategy)
    # ==========================================
    
    institution_id: str = Field(
        ...,
        description="ID do banco (inferido de connector.id pelo webhook receiver)"
    )
    
    item_id: str = Field(
        ...,
        max_length=MAX_TRANSACTION_ID_LENGTH,
        description="ID da conexão Pluggy/Belvo (item.id)"
    )
    
    source: DataSource = Field(
        default=DataSource.PLUGGY,
        description="Fonte de dados (PLUGGY, BELVO, MANUAL_CSV)"
    )
    
    fetched_at: datetime = Field(
        ...,
        description="Quando dados foram buscados (UTC, set pelo webhook receiver)"
    )
    
    # ==========================================
    # 6️⃣ AUDITORIA (não serializa)
    # ==========================================
    
    raw_payload: dict[str, Any] | None = Field(
        default=None,
        exclude=True,  # Não serializa em JSON (só auditoria interna)
        description="Payload completo do webhook (audit trail)"
    )
    
    # Configuração
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "transaction_id": "txn_abc123",
                "amount": -150.50,
                "transaction_date": "2024-01-15T10:30:00Z",
                "account_id": "acc_xyz789",
                "description": "PAG UBER VIAGEM",
                "balance": 1849.50,
                "status": "POSTED",
                "institution_id": "nubank",
                "item_id": "item_123",
                "source": "PLUGGY",
                "fetched_at": "2024-01-21T14:00:00Z"
            }
        }
    )
    
    # ==========================================
    # VALIDATORS
    # ==========================================
    
    @field_validator("amount", mode="before")
    @classmethod
    def parse_amount(cls, v: Any) -> Decimal:
        """Parseia valor monetário com múltiplos formatos."""
        return parse_amount_safe(v, "amount")
    
    @field_validator("balance", mode="before")
    @classmethod
    def parse_balance(cls, v: Any) -> Decimal | None:
        """Parseia saldo (opcional)."""
        if v is None or v == "":
            return None
        return parse_amount_safe(v, "balance")
    
    @field_validator("transaction_date", "fetched_at", mode="before")
    @classmethod
    def parse_dates(cls, v: Any) -> datetime:
        """Parseia datas garantindo UTC."""
        return parse_date_safe(v)
    
    @field_validator("status", mode="before")
    @classmethod
    def parse_status(cls, v: Any) -> TransactionStatus:
        """Parseia status com fallback tolerante."""
        return parse_status_safe(v)
    
    @field_validator("description", "description_raw", "observations", "merchant")
    @classmethod
    def sanitize_texts(cls, v: str | None) -> str | None:
        """Sanitiza textos removendo controles e limitando tamanho."""
        if v is None:
            return None
        return sanitize_text(v) or None
    
    @model_validator(mode="after")
    def validate_fundamental_fields(self) -> "TransactionWebhook":
        """
        Valida campos fundamentais (última linha de defesa).
        
        Garante que campos críticos estão presentes mesmo que
        tenham passado por validators individuais.
        """
        required = ["transaction_id", "amount", "transaction_date", 
                   "account_id", "institution_id", "item_id", "fetched_at"]
        
        for field in required:
            value = getattr(self, field, None)
            if value is None or value == "":
                raise ValueError(f"Campo fundamental '{field}' está vazio ou None")
        
        return self
    
    @model_validator(mode="after")
    def merge_descriptions(self) -> "TransactionWebhook":
        """
        Fallback de descriptions: description → description_raw → observations.
        
        Se description estiver vazio, tenta preencher com outras fontes.
        """
        if not self.description or not self.description.strip():
            # Tenta description_raw
            if self.description_raw and self.description_raw.strip():
                self.description = self.description_raw
            # Senão, tenta observations
            elif self.observations and self.observations.strip():
                self.description = self.observations
            # Se tudo vazio, deixa como ""
            else:
                self.description = ""
        
        return self
    
    @model_validator(mode="after")
    def validate_installments(self) -> "TransactionWebhook":
        """
        Valida coerência de parcelamentos.
        
        Se installment_number existe, installment_total deve existir.
        installment_number deve ser <= installment_total.
        """
        if self.installment_number is not None:
            if self.installment_total is None:
                raise ValueError(
                    "Se installment_number está presente, "
                    "installment_total também deve estar"
                )
            
            if self.installment_number > self.installment_total:
                raise ValueError(
                    f"installment_number ({self.installment_number}) não pode "
                    f"ser maior que installment_total ({self.installment_total})"
                )
        
        return self


class RejectedTransaction(BaseModel):
    """
    Registro de transação rejeitada durante validação Pydantic.
    
    Responsabilidades:
        - Auditoria completa (nada é perdido)
        - Debugging (por que foi rejeitada?)
        - Inbox de revisão manual (UI para analista)
        - Métricas de qualidade por banco
    
    Persistência (futuro):
        → Tabela `rejected_transactions` (Postgres)
        → Campos: raw_data (JSONB), field_errors (JSONB)
    
    Uso:
        - Analista revisa rejected_transactions
        - Detecta padrões de rejeição por banco
        - Melhora schemas baseado em rejeições comuns
    """
    
    # Dados rejeitados (sem PII em logs)
    raw_data: dict[str, Any] = Field(
        description="JSON original que falhou validação (NUNCA logar completo)"
    )
    
    # Motivo da rejeição
    error_type: str = Field(
        description="Tipo de erro (ValidationError, ValueError, DuplicateInBatch)"
    )
    
    error_message: str = Field(
        description="Mensagem completa do erro"
    )
    
    field_errors: dict[str, list[str]] = Field(
        default_factory=dict,
        description=(
            "Erros por campo estruturados. "
            "Exemplo: {'amount': ['cannot be zero'], 'date': ['invalid format']}"
        )
    )
    
    # Timestamp
    rejected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Quando a transação foi rejeitada (UTC)"
    )
    
    # Contexto (extraído do raw_data quando possível)
    transaction_id: str | None = Field(
        default=None,
        description="ID da transação (se conseguiu extrair do raw_data)"
    )
    
    account_id: str | None = Field(
        default=None,
        description="ID da conta (se presente no raw_data)"
    )
    
    institution_id: str | None = Field(
        default=None,
        description="ID do banco (para métricas por instituição)"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "raw_data": {"id": "txn_123", "amount": 0, "date": "2024-01-15"},
                "error_type": "ValidationError",
                "error_message": "amount não pode ser zero",
                "field_errors": {"amount": ["não pode ser zero"]},
                "rejected_at": "2024-01-21T10:30:00Z",
                "transaction_id": "txn_123",
                "account_id": "acc_456",
                "institution_id": "nubank"
            }
        }
    )


class TransactionBatchResult(BaseModel):
    """
    Resultado de validação tolerante de batch.
    
    Filosofia (da arquitetura):
        "99 transações válidas > 0 transações (batch inteiro rejeitado)"
        "Open Finance é instável → esperar falhas individuais"
        "Shadow Invoice preenche lacunas → 1 faltando não quebra forecast"
    
    Alertas automáticos:
        - rejection_rate > 20% → WARNING (log + métrica)
        - rejection_rate = 100% → CRITICAL (log + alerta)
    
    Uso:
        result = TransactionBatchResult.from_raw_batch(raw_list, ...)
        if result.should_alert:
            logger.warning("high_rejection_rate", level=result.alert_level)
    """
    
    # Transações processadas
    valid_transactions: list[TransactionWebhook] = Field(
        default_factory=list,
        description="Transações que passaram na validação"
    )
    
    rejected_transactions: list[RejectedTransaction] = Field(
        default_factory=list,
        description="Transações rejeitadas com motivo"
    )
    
    # Métricas
    total_received: int = Field(ge=0)
    total_valid: int = Field(ge=0)
    total_rejected: int = Field(ge=0)
    rejection_rate: float = Field(ge=0.0, le=1.0)
    
    # Contexto
    account_id: str
    item_id: str
    institution_id: str
    processed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    
    # ==========================================
    # PROPRIEDADES CALCULADAS (Alertas)
    # ==========================================
    
    @property
    def alert_level(self) -> Literal["OK", "WARNING", "CRITICAL"]:
        """
        Nível de alerta baseado na taxa de rejeição.
        
        Returns:
            "OK": rejection_rate <= 20%
            "WARNING": rejection_rate > 20% e < 100%
            "CRITICAL": rejection_rate = 100%
        
        Uso:
            if result.alert_level
            """