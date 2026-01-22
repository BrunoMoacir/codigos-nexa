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
from enums import (
    DataSource,
    DataStatus,
    TransactionStatus,
    Currency
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

# Constantes (exemplo)
CONTROL_CHARS_PATTERN = re.compile(r"[\x00-\x1f\x7f-\x9f]")

def sanitize_text(text: str, max_length: int = MAX_DESCRIPTION_LENGTH, escape_html: bool = False) -> str: #TESTADO E OK!!
    """
    Versão Definitiva:
    1. Trunca entrada excessiva (anti-ReDoS).
    2. Limpa caracteres.
    3. Normaliza espaços.
    4. Escapa (Opcional).
    5. Garante limite FINAL (segurança de DB).
    """
    if not isinstance(text, str):
        return ""

    # 1. Proteção inicial contra ReDoS (corta excessos absurdos antes de processar)
    # Cortamos um pouco a mais que o max_length para dar margem a normalizações,
    # mas impedimos processar strings de 10MB.
    if len(text) > max_length * 2:
        text = text[:max_length * 2]

    # 2. Remover controles
    text = CONTROL_CHARS_PATTERN.sub("", text)

    # 3. Normalizar espaços
    text = re.sub(r"\s+", " ", text).strip()

    # 4. Escapar HTML (Opcional - Geralmente deve ser False para salvar no DB)
    if escape_html:
        text = html.escape(text)

    # 5. Corte Final Rígido (Garante que cabe na coluna do banco)
    if len(text) > max_length:
        text = text[:max_length]

    return text


import re
from decimal import Decimal, InvalidOperation
from typing import Any

def parse_amount_safe(v: Any, field_name: str = "amount", default_locale: str = 'BR') -> Decimal:
    """
    Parser financeiro híbrido e resiliente.
    
    Estratégia:
    1. Se tem ',' e '.', a última ocorrência define a casa decimal.
    2. Se tem apenas um separador, usa o locale + regex para inferir.
       - BR com ponto: "1.000" (Milhar) vs "1.50" (Decimal híbrido).
    """
    # 1. Short-circuit para tipos já numéricos
    if isinstance(v, Decimal):
        return v
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    if not isinstance(v, str):
        raise ValueError(f"{field_name} formato inválido: deve ser string ou número.")

    # 2. Limpeza inicial
    v = v.strip()
    if not v:
        raise ValueError(f"{field_name} está vazio.")

    # 3. Tratamento de Sinais (Contábil e Padrão)
    is_negative = False
    if v.startswith("(") and v.endswith(")"):
        is_negative = True
        v = v[1:-1]
    elif v.startswith("-"):
        is_negative = True
        v = v[1:]

    # 4. Remove moeda e ESPAÇOS INTERNOS (ex: "1 500,00")
    v = v.replace("R$", "").replace("$", "").replace(" ", "")

    # 5. Análise de Separadores
    has_comma = "," in v
    has_dot = "." in v

    if has_comma and has_dot:
        # Lógica Posicional: Quem aparece por último é o decimal
        if v.rfind(",") > v.rfind("."):
            # Formato BR: 1.500.000,50
            v = v.replace(".", "").replace(",", ".")
        else:
            # Formato US: 1,500,000.50
            v = v.replace(",", "")
    
    elif has_comma:
        # Apenas vírgula (ex: "1000,50" ou "1,000")
        if default_locale == 'BR':
            # No BR, vírgula isolada é quase sempre decimal
            v = v.replace(",", ".")
        else:
            # No US, vírgula é milhar. "1,000" -> 1000.
            # Risco: "10,5" no US vira 105. Aceitável pois vírgula não é decimal lá.
            v = v.replace(",", "")
            
    elif has_dot:
        # Apenas ponto (ex: "10.50" ou "1.000")
        if default_locale == 'BR':
            # A GRANDE SACADA: Diferenciar milhar de decimal por estrutura
            # Se parece estritamente milhar (1-3 digitos, ponto, 3 digitos...)
            # Ex: 1.000 (match) | 1.000.000 (match) | 1.50 (no match)
            if re.match(r"^\d{1,3}(\.\d{3})+$", v):
                v = v.replace(".", "") # É milhar, remove
            else:
                # Não parece milhar (ex: 1.50, 10.5).
                # Assume que o usuário digitou com ponto decimal (hábito comum).
                pass 
        else:
            # US: Ponto é decimal, não faz nada.
            pass

    # 6. Conversão Final
    try:
        amount = Decimal(v)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field_name} contém valor inválido para conversão: '{v}'")

    if is_negative:
        amount = -amount

    if abs(amount) > MAX_AMOUNT:
        raise ValueError(f"{field_name} excede o limite permitido.")

    return amount

try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Fallback para Python < 3.9 (Requer: pip install backports.zoneinfo)
    from backports.zoneinfo import ZoneInfo

print(sanitize_text(""))

# Configuração de Timezones
TZ_UTC = timezone.utc
TZ_BR = ZoneInfo("America/Sao_Paulo")

def parse_date_safe(v: Any, field_name: str = "date", default_tz: Any = TZ_BR) -> datetime: #TESTADO E OK!!
    """
    Parser de datas corrigido.
    
    Diferença chave da v1:
    - Se a data for 'naive' (sem info de fuso), assume 'default_tz' 
      (ex: Brasil) e ENTÃO converte para UTC.
    """
    if v is None:
        raise ValueError(f"{field_name} é None")

    # 1. Já é datetime
    if isinstance(v, datetime):
        # Se não tem fuso, assume o default (ex: Brasil)
        if v.tzinfo is None:
            v = v.replace(tzinfo=default_tz)
        return v.astimezone(TZ_UTC)
    
    # 2. Date -> Datetime (Inicio do dia no fuso default)
    if isinstance(v, date):
        # Cria datetime 00:00:00 no fuso especificado (ex: Brasil)
        dt = datetime.combine(v, datetime.min.time(), tzinfo=default_tz)
        return dt.astimezone(TZ_UTC)
    
    # 3. String Parsing
    if isinstance(v, str):
        v = v.strip()
        if not v:
            raise ValueError(f"{field_name} vazio")

        # Estratégia Otimizada:
        # A) Tenta ISO 8601 nativo (muito mais rápido e robusto que strptime)
        try:
            # fromisoformat (Py 3.11+) lida bem com 'Z' e offsets
            # Para versões antigas, substitua 'Z' por '+00:00'
            if v.endswith("Z"):
                v_iso = v[:-1] + "+00:00"
            else:
                v_iso = v
            
            dt = datetime.fromisoformat(v_iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=default_tz)
            return dt.astimezone(TZ_UTC)
        except ValueError:
            pass # Falhou ISO, tenta formatos manuais

        # B) Formatos BR e Legados
        formats = [
            "%d/%m/%Y %H:%M:%S", # BR Completo
            "%d/%m/%Y",          # BR Data
            "%Y-%m-%d %H:%M:%S", # SQL Simples
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(v, fmt)
                # Se formato não tem timezone (ex: BR), aplica o default
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=default_tz)
                return dt.astimezone(TZ_UTC)
            except ValueError:
                continue

    raise ValueError(f"{field_name} formato desconhecido: {v}")


def parse_status_safe(v: Any) -> TransactionStatus: #TESTADO E OK!!
    """
    Parser estrito de status.
    
    Mudança chave da v1:
    - REMOVIDO o fallback para POSTED. Se não conhece o status, 
      ESTOURA ERRO. Segurança financeira em primeiro lugar.
    """
    if isinstance(v, TransactionStatus):
        return v
        
    # Tratamento de Nulos: 
    # Dependendo da regra de negócio, None pode ser PENDING ou erro.
    # Aqui assumimos que transação sem status é inválida.
    if v is None or v == "":
        raise ValueError("Status da transação não pode ser vazio.")

    if isinstance(v, str):
        v_clean = v.strip().upper()
        
        # 1. Tentativa Direta
        try:
            return TransactionStatus(v_clean)
        except ValueError:
            pass

        # 2. Tabela de Aliases (Expandida)
        aliases = {
            # Sucesso
            "PROCESSED": TransactionStatus.POSTED,
            "COMPLETED": TransactionStatus.POSTED,
            "SETTLED":   TransactionStatus.POSTED,
            "CONFIRMED": TransactionStatus.POSTED,
            
            # Pendente
            "SCHEDULED":  TransactionStatus.PENDING,
            "IN_PROCESS": TransactionStatus.PENDING,
            "PROCESSING": TransactionStatus.PENDING,
            
            # Falha (Crítico mapear estes!)
            "FAILED":    TransactionStatus.CANCELLED,
            "REJECTED":  TransactionStatus.CANCELLED,
            "CANCELED":  TransactionStatus.CANCELLED, # US spelling
            "VOIDED":    TransactionStatus.CANCELLED,
        }

        if v_clean in aliases:
            return aliases[v_clean]
            
        # 3. Fail Fast
        # Loga o erro crítico para o dev adicionar o novo status na lista acima
        msg = f"Status desconhecido encontrado: '{v_clean}'. Impossível mapear com segurança."
        logger.error(msg)
        raise ValueError(msg)

    raise ValueError(f"Tipo inválido para status: {type(v)}")


# ==========================================
# SCHEMAS
# ==========================================

class TransactionWebhook(BaseModel): #TESTADO E OK!!
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


class RejectedTransaction(BaseModel): #Testar
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


class TransactionBatchResult(BaseModel): #TESTAR E COMPLETAR O CODIGO
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