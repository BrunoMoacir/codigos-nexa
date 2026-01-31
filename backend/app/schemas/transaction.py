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
"""

from datetime import timedelta
import hashlib
import re
import html
import logging
from datetime import datetime, timezone, date
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Optional

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
    ConfigDict,
    ValidationError
)

# Importar enums do módulo compartilhado
from app.schemas.enums import (
    DataSource,
    DataStatus,
    TransactionStatus,
    Currency,
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

# Remove scripts e styles (COM conteúdo)
SCRIPT_PATTERN = re.compile(
    r'<script[^>]*>.*?</script>',
    re.IGNORECASE | re.DOTALL
)
STYLE_PATTERN = re.compile(
    r'<style[^>]*>.*?</style>',
    re.IGNORECASE | re.DOTALL
)

# Remove todas as outras tags HTML (sem conteúdo)
HTML_TAG_PATTERN = re.compile(r'<[^>]+>')
# ==========================================
# HELPERS DE PARSING
# ==========================================

def sanitize_text(text: str, max_length: int = MAX_DESCRIPTION_LENGTH, escape_html: bool = False, strip_html_tags: bool = True) -> str:
    """
    Versão Definitiva v2.0:
    1. Trunca entrada excessiva (anti-ReDoS).
    2. Remove tags HTML perigosas COM conteúdo.  # ✅ NOVO
    3. Limpa caracteres.
    4. Normaliza espaços.
    5. Escapa (Opcional).
    6. Garante limite FINAL (segurança de DB).
    """
    if not isinstance(text, str):
        return ""

    # 1. Proteção inicial contra ReDoS
    if len(text) > max_length * 2:
        text = text[:max_length * 2]

    # 2. ✅ NOVO: Remove tags HTML perigosas COM conteúdo
    if strip_html_tags:
        text = SCRIPT_PATTERN.sub('', text)
        text = STYLE_PATTERN.sub('', text)
        text = HTML_TAG_PATTERN.sub('', text)

    # 3. Remover controles
    text = CONTROL_CHARS_PATTERN.sub("", text)

    # 4. Normalizar espaços
    text = re.sub(r"\s+", " ", text).strip()

    # 5. Escapar HTML (Opcional)
    if escape_html:
        text = html.escape(text)

    # 6. Corte Final Rígido
    if len(text) > max_length:
        text = text[:max_length]

    return text

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


def parse_status_safe(v: Any) -> TransactionStatus:
    """Parser tolerante de status."""
    if isinstance(v, TransactionStatus):
        return v
    
    # ✅ MUDANÇA CRÍTICA: Permite None (fallback para POSTED)
    if v is None or v == "":
        return TransactionStatus.POSTED  # Default seguro
    
    if isinstance(v, str):
        v_clean = v.strip().upper()
        
        try:
            return TransactionStatus(v_clean)
        except ValueError:
            pass
        
        aliases = {
            "PROCESSED": TransactionStatus.POSTED,
            "COMPLETED": TransactionStatus.POSTED,
            "SETTLED": TransactionStatus.POSTED,
            "CONFIRMED": TransactionStatus.POSTED,
            "SCHEDULED": TransactionStatus.PENDING,
            "IN_PROCESS": TransactionStatus.PENDING,
            "PROCESSING": TransactionStatus.PENDING,
            "FAILED": TransactionStatus.CANCELLED,
            "REJECTED": TransactionStatus.CANCELLED,
            "CANCELED": TransactionStatus.CANCELLED,
            "VOIDED": TransactionStatus.CANCELLED,
        }
        
        if v_clean in aliases:
            return aliases[v_clean]
        
        # Status desconhecido (mas não None): usar POSTED com warning
        logger.warning(f"Status desconhecido '{v_clean}', usando POSTED como fallback")
        return TransactionStatus.POSTED
    
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

    # Muitos bancos mandam isso (ex: "CREDIT", "DEBIT")
    type: Optional[str] = Field(
        default=None, 
        description="Indicador de Crédito/Débito (ex: CREDIT, DEBIT)"
    )

    # --- CAMPO COMPUTADO (Deve ficar junto dos campos, não métodos) ---
    dedup_hash: str = Field(
        default="",
        description="Hash compósito para deduplicação (gerado automaticamente)"
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
    
    # ==========================================
# VALIDATORS (Ordem de Execução)
# ==========================================

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FASE 1: FIELD VALIDATORS (Parsers Individuais)
# Rodam ANTES dos model validators
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
    def parse_dates(cls, v: Any, info) -> datetime:
        """Parseia datas garantindo UTC."""
        return parse_date_safe(v, field_name=info.field_name)

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


    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # FASE 2: MODEL VALIDATORS (Validações Cross-Field)
    # Rodam DEPOIS dos field validators, na ordem definida  
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @model_validator(mode="after")
    def step1_validate_fundamental_fields(self) -> "TransactionWebhook":
        """
        STEP 1: Valida campos fundamentais (última linha de defesa).
    
        Garante que campos críticos estão presentes mesmo que
        tenham passado por validators individuais.
    
        ORDEM: Primeiro validator (valida existência básica).
        """
        required = ["transaction_id", "amount", "transaction_date", 
               "account_id", "institution_id", "item_id", "fetched_at"]
    
        for field in required:
            value = getattr(self, field, None)
            if value is None or value == "":
                raise ValueError(f"Campo fundamental '{field}' está vazio ou None")
    
        return self


    @model_validator(mode="after")
    def step2_validate_temporal_consistency(self) -> "TransactionWebhook":
        """
        STEP 2: Valida sanidade temporal.
    
        Verifica que datas fazem sentido (não muito antigas/futuras).
    
        ORDEM: Segundo (depende de step1 garantir que datas existem).
        """
        now = datetime.now(TZ_UTC)

        # 1. Transaction date: permite até 1 ano no futuro (agendamentos)
        if self.transaction_date > now + timedelta(days=365):
            raise ValueError(
                f"transaction_date muito distante no futuro: {self.transaction_date}"
            )

        # 2. Transaction date: permite até 10 anos no passado (histórico)
        if self.transaction_date < now - timedelta(days=3650):
            logger.warning(
                f"transaction_date muito antiga: {self.transaction_date} "
                f"(ID: {self.transaction_id})"
            )

        # 3. Fetched_at: NUNCA pode estar no futuro
        if self.fetched_at > now + timedelta(minutes=5):  # 5min de clock skew
            raise ValueError(
                f"fetched_at no futuro: {self.fetched_at}"
            )

        return self


    @model_validator(mode="after")
    def step3_merge_descriptions(self) -> "TransactionWebhook":
        """
        STEP 3: Fallback de descriptions.
    
        Prioridade: description → description_raw → observations.
        Se todos vazios, deixa description = "".
    
        ORDEM: Terceiro (manipula dados, não valida).
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
    def step4_validate_installments(self) -> "TransactionWebhook":
        """
        STEP 4: Valida coerência de parcelamentos.
    
        Se installment_number existe, installment_total deve existir.
        installment_number deve ser <= installment_total.
    
        ORDEM: Quarto (validação lógica independente).
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


    @model_validator(mode="after")
    def step5_normalize_amount_sign(self) -> "TransactionWebhook":
        """
        STEP 5: Normaliza sinal do amount.
    
        Usa campo 'type' (DEBIT/CREDIT) para corrigir sinal se necessário.
        Evita adivinhar por texto (muito perigoso).
    
        ORDEM: Quinto (depende de amount existir - step1 validou).
    
        IMPORTANTE: Não usa keywords na description porque:
            - "ESTORNO DE COMPRA" tem "COMPRA" mas é crédito
            - "DEVOLUÇÃO PAGAMENTO" tem "PAGAMENTO" mas é crédito
            - Polars faz análise semântica mais robusta
        """
        if self.type:
            type_upper = self.type.upper()
        
            # Regra: DEBIT deve ser negativo
            if type_upper in ["DEBIT", "DEBITO", "D"]:
                if self.amount > 0:
                    self.amount = -self.amount
        
            # Regra: CREDIT deve ser positivo
            elif type_upper in ["CREDIT", "CREDITO", "C"]:
                if self.amount < 0:
                    self.amount = abs(self.amount)
    
        return self


    @model_validator(mode="after")
    def step6_generate_composite_key(self) -> "TransactionWebhook":
        """
        STEP 6: Gera chave única composta (deduplicação).
    
        Hash baseado em: Account + Date + Amount + Desc (primeiros 20 chars).
    
        ORDEM: ÚLTIMO (depende de todos os campos estarem normalizados).
    
        Rationale:
        - Usa apenas os primeiros 20 chars da descrição
        - Evita que variações no final mudem o hash
        - Ex: "PAG UBER SAO PAULO" vs "PAG UBER RIO DE JANEIRO"
              Ambos viram "PAG UBER" no hash
        """
        # Formatação segura para evitar erros de tipo
        date_str = self.transaction_date.isoformat()
        amt_str = str(self.amount)
    
        # Pega apenas os primeiros 20 chars da descrição
        # (evita que pequenas variações no final mudem o hash)
        desc_short = (self.description or "").strip().upper()[:20]

        raw_string = f"{self.account_id}|{date_str}|{amt_str}|{desc_short}"
    
        self.dedup_hash = hashlib.sha256(raw_string.encode()).hexdigest()
    
        # Validação extra: hash nunca pode ficar vazio
        if not self.dedup_hash:
            raise ValueError("Falha ao gerar dedup_hash")
    
        return self

# ## 📊 **ORDEM DE EXECUÇÃO (Resumo)**
# ```
# ┌─────────────────────────────────────────────┐
# │ FASE 1: FIELD VALIDATORS (Parsers)         │
# ├─────────────────────────────────────────────┤
# │ 1. parse_amount()           → Decimal      │
# │ 2. parse_balance()          → Decimal|None │
# │ 3. parse_dates()            → datetime UTC │
# │ 4. parse_status()           → Enum         │
# │ 5. sanitize_texts()         → str clean    │
# └─────────────────────────────────────────────┘
#               ↓
# ┌─────────────────────────────────────────────┐
# │ FASE 2: MODEL VALIDATORS (Validações)      │
# ├─────────────────────────────────────────────┤
# │ STEP 1: validate_fundamental_fields()      │
# │         ✅ Garante campos obrigatórios      │
# │              ↓                              │
# │ STEP 2: validate_temporal_consistency()    │
# │         ✅ Sanidade temporal                │
# │              ↓                              │
# │ STEP 3: merge_descriptions()               │
# │         ✅ Fallback description_raw         │
# │              ↓                              │
# │ STEP 4: validate_installments()            │
# │         ✅ Coerência parcelamento           │
# │              ↓                              │
# │ STEP 5: normalize_amount_sign()            │
# │         ✅ Corrige sinal (type: DEBIT)      │
# │              ↓                              │
# │ STEP 6: generate_composite_key()           │
# │         ✅ Hash de deduplicação             │
# └─────────────────────────────────────────────┘
#               ↓
#         TransactionWebhook
#         (Pronto para S3)

class RejectedTransaction(BaseModel):
    """
    Registro de transação rejeitada durante validação Pydantic (DLQ - Dead Letter Queue).
    
    Responsabilidades:
        - Auditoria completa (nada é perdido)
        - Debugging (por que foi rejeitada?)
        - Métricas de qualidade por banco
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TODO (FUTURO - NÃO IMPLEMENTAR AGORA):
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 
    # 1. PERSISTÊNCIA (Postgres):
    #    CREATE TABLE rejected_transactions (
    #        id UUID PRIMARY KEY,
    #        raw_data JSONB NOT NULL,
    #        raw_data_truncated BOOLEAN DEFAULT FALSE,
    #        error_type VARCHAR(100),
    #        error_message TEXT,
    #        field_errors JSONB,
    #        transaction_id VARCHAR(255),
    #        account_id VARCHAR(255),
    #        institution_id VARCHAR(100),
    #        rejected_at TIMESTAMPTZ NOT NULL,
    #        reviewed BOOLEAN DEFAULT FALSE,
    #        INDEX idx_rejected_institution_date (institution_id, rejected_at DESC)
    #    );
    # 
    # 2. SERVICE LAYER (rejection_tracker.py):
    #    async def persist_rejections(rejections: list[RejectedTransaction]):
    #        INSERT INTO rejected_transactions (...) VALUES (...)
    # 
    # 3. MÉTRICAS (quality_metrics.py):
    #    async def calculate_rejection_rate(institution_id, last_hours=24):
    #        SELECT COUNT(*) / total_processed as rate
    # 
    # 4. ALERTAS (quality_alerts.py):
    #    if rejection_rate > 0.5:
    #        send_slack_alert("🚨 CRITICAL: 50%+ rejection")
    # 
    # 5. DASHBOARD (Frontend):
    #    /admin/data-quality/rejections
    #    - Gráfico de rejeições ao longo do tempo
    #    - Top erros por banco
    #    - Inbox de revisão manual
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """
    
    # ==========================================
    # CAMPOS
    # ==========================================
    
    # Dados rejeitados
    raw_data: dict[str, Any] = Field(
        description=(
            "JSON original que falhou validação. "
            "ATENÇÃO: Pode conter PII. NUNCA logar completo."
        )
    )
    
    raw_data_truncated: bool = Field(
        default=False,
        description="Se True, raw_data foi truncado por exceder 10KB"
    )
    
    # Classificação do erro
    error_type: str = Field(
        max_length=100,
        description=(
            "Tipo de erro. "
            "Comum: ValidationError, ValueError, DuplicateInBatch"
        )
    )
    
    error_message: str = Field(
        description="Mensagem completa do erro"
    )
    
    field_errors: dict[str, list[str]] = Field(
        default_factory=dict,
        description=(
            "Erros estruturados por campo. "
            "Ex: {'amount': ['Field required'], 'date': ['Invalid format']}"
        )
    )
    
    # Timestamp
    rejected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Quando foi rejeitada (UTC)"
    )
    
    # Contexto (extraído do raw_data quando possível)
    transaction_id: Optional[str] = Field(
        default=None,
        description="ID da transação (se conseguiu extrair)"
    )
    
    account_id: Optional[str] = Field(
        default=None,
        description="ID da conta (se presente)"
    )
    
    institution_id: Optional[str] = Field(
        default=None,
        description="ID do banco (para métricas)"
    )
    
    # Configuração
    model_config = ConfigDict(
        extra='ignore',  # ✅ Ignora campos extras (flexibilidade)
        json_schema_extra={
            "example": {
                "raw_data": {"id": "txn_123", "amount": None},
                "raw_data_truncated": False,
                "error_type": "ValidationError",
                "error_message": "2 validation errors for TransactionWebhook",
                "field_errors": {
                    "amount": ["Field required"],
                    "transaction_date": ["Input should be a valid datetime"]
                },
                "rejected_at": "2024-01-21T10:30:00+00:00",
                "transaction_id": "txn_123",
                "account_id": "acc_456",
                "institution_id": "nubank"
            }
        }
    )
    
    # ==========================================
    # VALIDATORS
    # ==========================================
    
    @field_validator("raw_data", mode="after")
    @classmethod
    def truncate_large_raw_data(cls, v: dict[str, Any]) -> dict[str, Any]:
        """
        Trunca raw_data se > 10KB (prevenir DB bloat).
        
        Se muito grande, mantém apenas campos essenciais.
        """
        import json
        
        try:
            raw_json = json.dumps(v, default=str, ensure_ascii=False)
            size_kb = len(raw_json.encode('utf-8')) / 1024
        except Exception:
            return v  # Se falhar, deixa passar
        
        # Se menor que 10KB, ok
        if size_kb <= 10:
            return v
        
        # Truncar para campos essenciais
        logger.warning(
            f"raw_data truncado ({size_kb:.1f}KB → 10KB)",
            extra={"original_size_kb": size_kb}
        )
        
        essential_fields = [
            "id", "transaction_id", "amount", "date", "transaction_date",
            "accountId", "account_id", "description", "balance"
        ]
        
        truncated = {k: v.get(k) for k in essential_fields if k in v}
        truncated["_truncated"] = True
        truncated["_original_size_kb"] = round(size_kb, 2)
        
        return truncated
    
    # ==========================================
    # FACTORY METHOD (Generic & Flexible)
    # ==========================================
    
    @classmethod
    def create_from_exception(
        cls, 
        data: dict[str, Any], 
        exc: Exception, 
        **kwargs  # Permite passar institution_id, etc
    ) -> "RejectedTransaction":
        """
        Factory method genérico: Converte Exception → RejectedTransaction.
        
        Extrai automaticamente:
            - field_errors (se ValidationError)
            - transaction_id, account_id (do data)
            - institution_id (de kwargs)
        
        Args:
            data: JSON original que causou erro
            exc: Exception capturada (qualquer tipo)
            **kwargs: Contexto adicional (ex: institution_id="nubank")
        
        Returns:
            RejectedTransaction estruturado
        
        Example:
            # Caso 1: ValidationError (Pydantic)
            try:
                txn = TransactionWebhook(**raw)
            except ValidationError as e:
                rejected = RejectedTransaction.create_from_exception(
                    data=raw,
                    exc=e,
                    institution_id="nubank"
                )
            
            # Caso 2: KeyError (campo faltando)
            try:
                txn_id = raw["id"]  # KeyError
            except Exception as e:
                rejected = RejectedTransaction.create_from_exception(
                    data=raw,
                    exc=e,
                    institution_id="nubank"
                )
            
            # Caso 3: Duplicata (nosso código)
            if txn_id in seen_ids:
                rejected = RejectedTransaction.create_from_exception(
                    data=raw,
                    exc=ValueError(f"Duplicata: {txn_id}"),
                    institution_id="nubank"
                )
        """
        field_errors = {}
        error_msg = str(exc)
        error_type = type(exc).__name__
        
        # Se ValidationError do Pydantic, extrair field_errors
        if isinstance(exc, ValidationError):
            for err in exc.errors():
                # Pega nome do campo (ex: 'amount') ou 'root' se não tiver
                loc = str(err["loc"][-1]) if err["loc"] else "root"
                field_errors.setdefault(loc, []).append(err["msg"])
            
            error_msg = f"{len(exc.errors())} validation errors"
        
        # Extrair IDs do payload (best effort)
        tx_id = str(data.get("transaction_id") or data.get("id") or "")
        acc_id = str(data.get("account_id") or data.get("accountId") or "")
        
        # Institution ID pode vir de kwargs (preferencial) ou payload
        inst_id = str(
            kwargs.get("institution_id") or 
            data.get("institution_id") or 
            ""
        )
        
        return cls(
            raw_data=data,
            error_type=error_type,
            error_message=error_msg,
            field_errors=field_errors,
            transaction_id=tx_id if tx_id else None,
            account_id=acc_id if acc_id else None,
            institution_id=inst_id if inst_id else None
        )

# ==========================================
# TRANSACTION OUT (Schema de SAÍDA)
# ==========================================

class TransactionOut(BaseModel):
    """
    Schema de SAÍDA para API (dados pós-ETL).
    
    ⚠️ IMPORTANTE - FLUXO COMPLETO:
        Este schema representa dados JÁ PROCESSADOS por:
        
        1. Pydantic (TransactionWebhook)
           ↓ Validação estrutural
        
        2. raw_events (S3)
           ↓ Auditoria completa
        
        3. Message Queue (Redis)
           ↓ Desacoplamento
        
        4. Polars Ingestor (app/etl/ingestor.py)
           ↓ Normalização, limpeza, dedupe
        
        5. BankStrategy (app/etl/bank_strategy.py)
           ↓ Validação de confiança por banco
        
        6. ETL Workers
           ↓ Classificação (CatBoost), detecção de padrões
        
        7. Engines (app/engines/)
           ↓ Cálculos financeiros (Safe-to-Spend, etc)
        
        8. transactions_clean (Postgres)
           ↓ Persistência
        
        9. TransactionOut ← ESTAMOS AQUI
           ↓ API Response
        
        10. Frontend / LangGraph
            ✅ Consumo final
    
    Diferenças do TransactionWebhook (entrada):
        ✅ Tipos simplificados (float vs Decimal - JSON friendly)
        ✅ Flags calculadas (is_recurring, is_installment)
        ✅ Metadados de QUALIDADE (confidence, data_status, source)
        ❌ SEM raw_payload (muito grande)
        ❌ SEM campos internos (item_id, fetched_at)
    
    Consumidores:
        - Frontend: exibe extrato com badges de confiança
        - LangGraph: toma decisões baseadas em confidence
        - Engines: usa para cálculos (Safe-to-Spend, Shadow Invoice)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TODO (FUTURO - PERSISTÊNCIA E API):
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 
    # 1. POSTGRES QUERY (transactions_clean):
    #    Arquivo: backend/app/db/queries/transactions.py
    # 
    #    SELECT 
    #        id,
    #        amount,
    #        transaction_date as date,
    #        description,
    #        category,
    #        merchant,
    #        is_recurring,
    #        is_installment,
    #        CASE 
    #            WHEN is_installment THEN 
    #                installment_number::text || '/' || installment_total::text
    #            ELSE NULL
    #        END as installment_info,
    #        balance,
    #        confidence,
    #        source,
    #        data_status
    #    FROM transactions_clean
    #    WHERE account_id = $1
    #    AND transaction_date BETWEEN $2 AND $3
    #    ORDER BY transaction_date DESC
    #    LIMIT $4
    # 
    # 2. FASTAPI ENDPOINT (routes/transactions.py):
    #    Arquivo: backend/app/api/routes/transactions.py
    # 
    #    @router.get("/transactions", response_model=list[TransactionOut])
    #    async def get_transactions(
    #        account_id: str,
    #        date_from: datetime | None = None,
    #        date_to: datetime | None = None,
    #        limit: int = 100,
    #        db: AsyncSession = Depends(get_db)
    #    ):
    #        '''Retorna transações processadas de uma conta.'''
    #        
    #        # Default: últimos 30 dias
    #        if not date_from:
    #            date_from = datetime.utcnow() - timedelta(days=30)
    #        if not date_to:
    #            date_to = datetime.utcnow()
    #        
    #        rows = await db.execute(
    #            query,
    #            account_id, date_from, date_to, limit
    #        )
    #        
    #        return [TransactionOut(**row._asdict()) for row in rows.fetchall()]
    # 
    # 3. FRONTEND (components/TransactionList.tsx):
    #    Arquivo: frontend/src/components/TransactionList.tsx
    # 
    #    function TransactionBadge({ transaction }) {
    #        const getColor = (confidence) => {
    #            if (confidence >= 0.8) return "green"
    #            if (confidence >= 0.5) return "yellow"
    #            return "red"
    #        }
    #        
    #        return (
    #            <Badge color={getColor(transaction.confidence)}>
    #                {transaction.data_status}
    #            </Badge>
    #        )
    #    }
    # 
    # 4. LANGGRAPH TOOL (agent/tools/transactions.py):
    #    Arquivo: backend/app/agent/tools/transactions.py
    # 
    #    @tool
    #    def get_recent_transactions(account_id: str) -> list[dict]:
    #        '''Busca transações recentes de alta confiança.'''
    #        
    #        # Consulta API
    #        response = requests.get(
    #            f"/api/transactions?account_id={account_id}"
    #        )
    #        
    #        # Filtra apenas TRUSTED (confidence > 0.8)
    #        transactions = [
    #            tx for tx in response.json()
    #            if tx["confidence"] > 0.8
    #        ]
    #        
    #        return transactions
    # 
    # 5. ENGINES (Safe-to-Spend):
    #    Arquivo: backend/app/engines/safe_to_spend.py
    # 
    #    def calculate_safe_to_spend(
    #        transactions: list[TransactionOut],
    #        balance: float
    #    ) -> float:
    #        '''Calcula quanto o usuário pode gastar hoje.'''
    #        
    #        # Filtra apenas transações confiáveis
    #        trusted = [
    #            tx for tx in transactions
    #            if tx.data_status == "TRUSTED"
    #        ]
    #        
    #        # Calcula gastos futuros (PENDING)
    #        future_expenses = sum(
    #            abs(tx.amount) for tx in trusted
    #            if tx.amount < 0 and tx.date > datetime.utcnow()
    #        )
    #        
    #        return balance - future_expenses - SAFETY_MARGIN
    # 
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """
    
    # ==========================================
    # DADOS BÁSICOS (normalizados)
    # ==========================================
    
    id: str = Field(
        description="ID único da transação (mesmo do TransactionWebhook.transaction_id)"
    )
    
    amount: float = Field(
        description=(
            "Valor da transação em float (JSON-friendly). "
            "Negativo = débito, positivo = crédito. "
            "Conversão: Decimal → float feita pelo Polars."
        )
    )
    
    date: datetime = Field(
        description=(
            "Data da transação (SEMPRE UTC timezone-aware). "
            "Mesmo valor de TransactionWebhook.transaction_date."
        )
    )
    
    description: str = Field(
        default="Transação sem descrição",
        description=(
            "Descrição normalizada pelo Polars. "
            "Lowercase, sem acentos, trimmed. "
            "Ex: 'PAG UBER VIAGEM' → 'pag uber viagem'. "
            "Se vazio após normalização: 'Transação sem descrição'"
        )
    )
    
    # ==========================================
    # ENRIQUECIMENTO (calculado por ETL)
    # ==========================================
    
    category: str | None = Field(
        default=None,
        description=(
            "Categoria final após classificação. "
            "Prioridade: CatBoost → regras → banco original. "
            "Ex: 'Transporte', 'Alimentação', 'Assinaturas'"
        )
    )
    
    merchant: str | None = Field(
        default=None,
        description=(
            "Merchant normalizado. "
            "Ex: 'UBER *TRIP' → 'Uber', 'NETFLIX.COM' → 'Netflix'"
        )
    )
    
    # ==========================================
    # FLAGS CALCULADAS (Polars + Engines)
    # ==========================================
    
    is_recurring: bool = Field(
        default=False,
        description=(
            "True se detectada como recorrência (assinatura). "
            "Critérios: mesmo merchant, valor similar, frequência mensal. "
            "Calculado por: app/etl/recurring_detector.py"
        )
    )
    
    is_installment: bool = Field(
        default=False,
        description=(
            "True se detectada como parcelamento. "
            "Critérios: regex na description, installment_number presente. "
            "Calculado por: app/engines/reconciler.py"
        )
    )
    
    installment_info: str | None = Field(
        default=None,
        description=(
            "Informação de parcelamento formatada para UI. "
            "Formato: 'N/M' onde N = parcela atual, M = total. "
            "Ex: '3/12' (parcela 3 de 12). "
            "None se não for parcelamento."
        )
    )
    
    balance: float | None = Field(
        default=None,
        description=(
            "Saldo após transação. "
            "Se None no input, Polars estimou via cumsum. "
            "Conversão: Decimal → float."
        )
    )
    
    # ==========================================
    # METADADOS DE QUALIDADE (Transparência!)
    # ==========================================
    
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Confiança nos dados processados (0.0 - 1.0). "
            "\n\n"
            "Calculado por:\n"
            "  1. BankStrategy (perfil do banco)\n"
            "  2. Polars validation (cobertura temporal, lacunas)\n"
            "  3. ETL quality checks\n"
            "\n"
            "Interpretação:\n"
            "  ≥ 0.90: Excelente (TRUSTED)\n"
            "  0.70-0.89: Boa (DEGRADED)\n"
            "  < 0.70: Baixa (UNTRUSTED)\n"
            "\n"
            "UI: Exibir badge colorido:\n"
            "  - Verde: confidence ≥ 0.8\n"
            "  - Amarelo: 0.5 ≤ confidence < 0.8\n"
            "  - Vermelho: confidence < 0.5"
        )
    )
    
    source: Literal["OFFICIAL", "SHADOW", "HYBRID"] = Field(
        description=(
            "Fonte dos dados após processamento. "
            "\n\n"
            "OFFICIAL (dados oficiais do banco):\n"
            "  - Transação veio do Open Finance\n"
            "  - BankStrategy validou como TRUSTED\n"
            "  - Usa dados do banco sem alteração\n"
            "\n"
            "SHADOW (gerado por Shadow Invoice):\n"
            "  - Transação não veio do banco (lacuna)\n"
            "  - Gerada por heurística/previsão\n"
            "  - Baseada em padrões históricos\n"
            "\n"
            "HYBRID (mistura oficial + shadow):\n"
            "  - Transação do banco (DEGRADED)\n"
            "  - Complementada com estimativas\n"
            "  - Ex: balance estimado, category inferida\n"
            "\n"
            "Uso em UI:\n"
            "  - OFFICIAL: ícone de check verde\n"
            "  - SHADOW: ícone de estrela (estimado)\n"
            "  - HYBRID: ícone de warning (parcial)"
        )
    )
    
    data_status: str = Field(  # DataStatus enum
        description=(
            "Status de confiança após validação completa. "
            "\n\n"
            "TRUSTED:\n"
            "  - Dados completos do banco\n"
            "  - Cobertura temporal boa (< 5% lacunas)\n"
            "  - BankStrategy aprovou\n"
            "  → Usar dados oficiais\n"
            "\n"
            "DEGRADED:\n"
            "  - Dados do banco com lacunas (5-20%)\n"
            "  - Campos faltando (balance, category)\n"
            "  - BankStrategy com ressalvas\n"
            "  → Misturar oficial + Shadow Invoice\n"
            "\n"
            "UNTRUSTED:\n"
            "  - Muitas lacunas (> 20%)\n"
            "  - Histórico insuficiente\n"
            "  - BankStrategy rejeitou\n"
            "  → Usar Shadow Invoice completo\n"
            "\n"
            "Decisão de fallback (Engines):\n"
            "  if data_status == 'TRUSTED':\n"
            "      use_official_data()\n"
            "  elif data_status == 'DEGRADED':\n"
            "      blend_official_and_shadow()\n"
            "  else:  # UNTRUSTED\n"
            "      use_shadow_invoice_only()"
        )
    )
    
    # ==========================================
    # CONFIGURAÇÃO
    # ==========================================
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "txn_nubank_abc123",
                "amount": -150.50,
                "date": "2024-01-15T10:30:00+00:00",
                "description": "pag uber viagem",
                "category": "Transporte",
                "merchant": "Uber",
                "is_recurring": False,
                "is_installment": False,
                "installment_info": None,
                "balance": 1849.50,
                "confidence": 0.95,
                "source": "OFFICIAL",
                "data_status": "TRUSTED"
            }
        }
    )
    
    # ==========================================
    # VALIDATORS (Sanidade de saída)
    # ==========================================
    
    @field_validator("amount")
    @classmethod
    def validate_amount_range(cls, v: float) -> float:
        """
        Valida que amount está em range razoável.
        
        Nota: Não rejeitamos (já passou por todas as camadas),
        apenas logamos warning se suspeito.
        """
        MAX_AMOUNT_FLOAT = 1_000_000_000.0  # 1 bilhão
        
        if abs(v) > MAX_AMOUNT_FLOAT:
            logger.warning(
                "suspicious_amount_in_output",
                extra={
                    "amount": v,
                    "max_expected": MAX_AMOUNT_FLOAT,
                    "message": "Amount muito alto em TransactionOut (passou por ETL?)"
                }
            )
        
        return v
    
    
    @field_validator("date")
    @classmethod
    def validate_date_sanity(cls, v: datetime) -> datetime:
        """
        Valida sanidade temporal em TransactionOut.
        
        Mesmo sendo pós-ETL, pode haver bugs de pipeline.
        Logamos warnings se suspeito.
        """
        now = datetime.now(timezone.utc)
        
        # Não pode estar muito no futuro (>1 ano)
        if v > now + timedelta(days=365):
            logger.error(
                "future_date_in_output",
                extra={
                    "date": v.isoformat(),
                    "message": "Data muito no futuro em TransactionOut (bug de ETL?)"
                }
            )
        
        # Alertar se muito antiga (>10 anos)
        if v < now - timedelta(days=3650):
            logger.warning(
                "very_old_date_in_output",
                extra={
                    "date": v.isoformat(),
                    "message": "Data muito antiga em TransactionOut"
                }
            )
        
        return v
    
    
    @field_validator("confidence")
    @classmethod
    def validate_confidence_range(cls, v: float) -> float:
        """
        Valida que confidence está entre 0 e 1.
        
        Nota: Pydantic já valida ge=0.0, le=1.0, mas reforçamos aqui.
        """
        if not 0.0 <= v <= 1.0:
            raise ValueError(
                f"confidence deve estar entre 0.0 e 1.0, recebido: {v}"
            )
        
        return v
    
    
    @field_validator("installment_info")
    @classmethod
    def validate_installment_format(cls, v: str | None) -> str | None:
        """
        Valida formato de installment_info (deve ser 'N/M').
        
        Formato esperado: "3/12" (parcela 3 de 12).
        Sanitiza se inválido (retorna None).
        """
        if v is None:
            return None
        
        # Formato válido: "N/M" onde N <= M, ambos <= 60
        if not re.match(r"^\d{1,2}/\d{1,2}$", v):
            logger.warning(
                "invalid_installment_format",
                extra={
                    "installment_info": v,
                    "expected_format": "N/M",
                    "message": "installment_info com formato inválido, sanitizando para None"
                }
            )
            return None
        
        # Extrair N e M para validar lógica
        try:
            n, m = map(int, v.split("/"))
            
            if n > m or n <= 0 or m <= 0 or m > 60:
                logger.warning(
                    "invalid_installment_logic",
                    extra={
                        "installment_info": v,
                        "message": f"Lógica inválida: parcela {n} de {m}"
                    }
                )
                return None
            
        except ValueError:
            return None
        
        return v
    
    
    @model_validator(mode="after")
    def validate_installment_consistency(self) -> "TransactionOut":
        """
        Valida consistência entre is_installment e installment_info.
        
        Se is_installment=True, installment_info deve existir.
        Não rejeita, apenas loga inconsistência.
        """
        if self.is_installment and not self.installment_info:
            logger.warning(
                "inconsistent_installment",
                extra={
                    "transaction_id": self.id,
                    "is_installment": True,
                    "installment_info": None,
                    "message": "is_installment=True mas installment_info=None"
                }
            )
        
        return self
    
    
    @model_validator(mode="after")
    def validate_source_vs_status(self) -> "TransactionOut":
        """
        Valida consistência entre source e data_status.
        
        Regras esperadas:
            - TRUSTED → source deve ser OFFICIAL
            - UNTRUSTED → source deve ser SHADOW
            - DEGRADED → source pode ser HYBRID ou OFFICIAL
        
        Nota: Não rejeita, apenas loga inconsistências para debugging.
        """
        # TRUSTED deveria ter source=OFFICIAL
        if self.data_status == "TRUSTED" and self.source != "OFFICIAL":
            logger.warning(
                "inconsistent_source_status",
                extra={
                    "transaction_id": self.id,
                    "data_status": "TRUSTED",
                    "source": self.source,
                    "expected_source": "OFFICIAL",
                    "message": "TRUSTED deveria ter source=OFFICIAL"
                }
            )
        
        # UNTRUSTED não deveria ter source=OFFICIAL
        if self.data_status == "UNTRUSTED" and self.source == "OFFICIAL":
            logger.warning(
                "inconsistent_source_status",
                extra={
                    "transaction_id": self.id,
                    "data_status": "UNTRUSTED",
                    "source": "OFFICIAL",
                    "expected_source": "SHADOW",
                    "message": "UNTRUSTED não deveria ter source=OFFICIAL"
                }
            )
        
        return self

# ==========================================
# TRANSACTION BATCH RESULT (Validação Tolerante)
# ==========================================

# ==========================================
# TRANSACTION BATCH RESULT (Validação Tolerante)
# ==========================================

"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TRANSACTION BATCH RESULT - VERSÃO CORRIGIDA COM MAPEAMENTO DE CAMPOS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SUBSTITUIR ESTA CLASSE COMPLETA em: app/schemas/transaction.py

CORREÇÕES:
    ✅ from_raw_batch() agora mapeia campos Pluggy/Belvo
    ✅ Método _normalize_webhook_fields() adicionado
    ✅ Suporta Nubank, Itaú, Inter automaticamente
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

class TransactionBatchResult(BaseModel):
    """
    Resultado de validação tolerante de batch de transações.
    
    Filosofia Nexa:
        ✅ "99 transações válidas > 0 transações (batch inteiro rejeitado)"
        ✅ "Open Finance é instável → esperar falhas individuais"
        ✅ "Shadow Invoice preenche lacunas → 1 faltando não quebra forecast"
    """
    
    # ==========================================
    # CAMPOS
    # ==========================================
    
    batch_id: str = Field(description="ID único do batch")
    institution_id: str = Field(description="Banco de origem")
    processed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Quando foi processado"
    )
    
    valid_transactions: list[TransactionWebhook] = Field(
        default_factory=list,
        description="Transações válidas (prontas para S3)"
    )
    
    rejected_transactions: list[RejectedTransaction] = Field(
        default_factory=list,
        description="Transações rejeitadas (DLQ)"
    )
    
    total_received: int = Field(ge=0, description="Total recebido")
    total_valid: int = Field(ge=0, description="Total válidas")
    total_rejected: int = Field(ge=0, description="Total rejeitadas")
    rejection_rate: float = Field(ge=0.0, le=1.0, description="Taxa rejeição")
    
    error_summary: dict[str, int] = Field(
        default_factory=dict,
        description="Top erros por tipo"
    )
    
    field_error_summary: dict[str, int] = Field(
        default_factory=dict,
        description="Top campos com erro"
    )
    
    alert_level: Literal["INFO", "WARNING", "CRITICAL"] = Field(
        default="INFO",
        description="Nível de alerta"
    )
    
    should_alert: bool = Field(default=False, description="Deve alertar?")
    alert_message: str | None = Field(default=None, description="Mensagem alerta")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "batch_id": "batch_abc123",
                "institution_id": "nubank",
                "total_received": 100,
                "total_valid": 95,
                "total_rejected": 5,
                "rejection_rate": 0.05,
                "alert_level": "INFO"
            }
        }
    )
    
    # ==========================================
    # VALIDATORS
    # ==========================================
    
    @model_validator(mode="after")
    def calculate_metrics(self) -> "TransactionBatchResult":
        """Calcula métricas derivadas."""
        self.total_valid = len(self.valid_transactions)
        self.total_rejected = len(self.rejected_transactions)
        
        if self.total_received > 0:
            self.rejection_rate = self.total_rejected / self.total_received
        else:
            self.rejection_rate = 0.0
        
        return self
    
    @model_validator(mode="after")
    def analyze_errors(self) -> "TransactionBatchResult":
        """Analisa padrões de erro."""
        error_types: dict[str, int] = {}
        field_errors: dict[str, int] = {}
        
        for rejected in self.rejected_transactions:
            error_type = rejected.error_type
            error_types[error_type] = error_types.get(error_type, 0) + 1
            
            for field_name in rejected.field_errors.keys():
                field_errors[field_name] = field_errors.get(field_name, 0) + 1
        
        self.error_summary = dict(
            sorted(error_types.items(), key=lambda x: x[1], reverse=True)
        )
        
        self.field_error_summary = dict(
            sorted(field_errors.items(), key=lambda x: x[1], reverse=True)
        )
        
        return self
    
    @model_validator(mode="after")
    def determine_alert_level(self) -> "TransactionBatchResult":
        """Define nível de alerta."""
        if self.rejection_rate >= REJECTION_CRITICAL_THRESHOLD:
            self.alert_level = "CRITICAL"
            self.should_alert = True
        elif self.rejection_rate >= REJECTION_WARNING_THRESHOLD:
            self.alert_level = "WARNING"
            self.should_alert = True
        else:
            self.alert_level = "INFO"
            self.should_alert = False
        
        if self.should_alert:
            top_errors = list(self.error_summary.items())[:3]
            top_errors_str = ", ".join(
                f"{err}: {count}" for err, count in top_errors
            )
            
            self.alert_message = (
                f"[{self.alert_level}] Batch {self.batch_id} - "
                f"Banco: {self.institution_id} - "
                f"Rejection Rate: {self.rejection_rate:.1%} "
                f"({self.total_rejected}/{self.total_received}) | "
                f"Top Erros: {top_errors_str}"
            )
        
        return self
    
    # ==========================================
    # FACTORY METHOD (CORRIGIDO!)
    # ==========================================
    
    @classmethod
    def from_raw_batch(
        cls,
        raw_data: list[dict[str, Any]],
        institution_id: str,
        item_id: str,
        fetched_at: datetime,
        batch_id: str | None = None
    ) -> "TransactionBatchResult":
        """
        Factory method: Processa batch completo de forma tolerante.
        
        ✅ NOVO: Agora mapeia campos Pluggy/Belvo → padrão Nexa!
        
        Args:
            raw_data: Lista de dicts do webhook
            institution_id: ID do banco (inferido de connector)
            item_id: ID da conexão Pluggy/Belvo
            fetched_at: Timestamp UTC de recebimento
            batch_id: ID do batch (opcional)
        
        Returns:
            TransactionBatchResult com transações validadas
        """
        import uuid
        
        # 1. Gerar batch_id
        if batch_id is None:
            batch_id = f"batch_{uuid.uuid4().hex[:12]}"
        
        # 2. Listas de resultado
        valid: list[TransactionWebhook] = []
        rejected: list[RejectedTransaction] = []
        
        # 3. Processar cada transação
        for raw_txn in raw_data:
            try:
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # ✅ STEP A: MAPEAR CAMPOS (NOVO!)
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # Converte campos Pluggy/Belvo → padrão Nexa
                # Ex: id → transaction_id, accountId → account_id
                
                normalized_txn = cls._normalize_webhook_fields(
                    raw_txn, 
                    institution_id
                )
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # STEP B: ENRIQUECER COM METADADOS
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                
                enriched_txn = {
                    **normalized_txn,
                    "institution_id": institution_id,
                    "item_id": item_id,
                    "fetched_at": fetched_at
                }
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # STEP C: VALIDAR COM PYDANTIC
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                
                transaction = TransactionWebhook(**enriched_txn)
                valid.append(transaction)
                
            except ValidationError as e:
                rejected_txn = RejectedTransaction.create_from_exception(
                    data=raw_txn,
                    exc=e,
                    institution_id=institution_id
                )
                rejected.append(rejected_txn)
                
            except Exception as e:
                logger.error(
                    "unexpected_error_in_batch_processing",
                    extra={
                        "batch_id": batch_id,
                        "institution_id": institution_id,
                        "error_type": type(e).__name__,
                        "error_message": str(e)
                    },
                    exc_info=True
                )
                
                rejected_txn = RejectedTransaction.create_from_exception(
                    data=raw_txn,
                    exc=e,
                    institution_id=institution_id
                )
                rejected.append(rejected_txn)
        
        # 4. Criar resultado
        result = cls(
            batch_id=batch_id,
            institution_id=institution_id,
            valid_transactions=valid,
            rejected_transactions=rejected,
            total_received=len(raw_data),
            total_valid=0,
            total_rejected=0,
            rejection_rate=0.0
        )
        
        return result
    
    # ==========================================
    # ✅ NOVO MÉTODO: MAPEAMENTO DE CAMPOS
    # ==========================================
    
    @staticmethod
    def _normalize_webhook_fields(
        raw_txn: dict[str, Any], 
        institution_id: str
    ) -> dict[str, Any]:
        """
        Normaliza campos específicos de cada banco → padrão Nexa.
        
        MAPEAMENTOS:
        
        Nubank/Pluggy (padrão):
            id → transaction_id
            accountId → account_id
            date → transaction_date
        
        Itaú (não-padrão):
            conta → account_id
            data → transaction_date
            valor → amount
            descricao → description
            tipo → type
            saldo → balance
        
        Inter (quase padrão):
            value → amount
        
        Args:
            raw_txn: Transação crua do webhook
            institution_id: ID do banco
        
        Returns:
            Dict com campos normalizados
        """
        normalized = raw_txn.copy()
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # PLUGGY/BELVO PADRÃO (Nubank, Bradesco, etc)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # id → transaction_id
        if "id" in normalized and "transaction_id" not in normalized:
            normalized["transaction_id"] = normalized.pop("id")
        
        # accountId → account_id
        if "accountId" in normalized and "account_id" not in normalized:
            normalized["account_id"] = normalized.pop("accountId")
        
        # date → transaction_date
        if "date" in normalized and "transaction_date" not in normalized:
            normalized["transaction_date"] = normalized.pop("date")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ITAÚ (Campos não-padrão)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        if institution_id == "itau":
            # conta → account_id
            if "conta" in normalized:
                normalized["account_id"] = normalized.pop("conta")
            
            # data → transaction_date
            if "data" in normalized:
                normalized["transaction_date"] = normalized.pop("data")
            
            # valor → amount
            if "valor" in normalized:
                normalized["amount"] = normalized.pop("valor")
            
            # descricao → description
            if "descricao" in normalized:
                normalized["description"] = normalized.pop("descricao")
            
            # tipo → type
            if "tipo" in normalized:
                normalized["type"] = normalized.pop("tipo")
            
            # saldo → balance
            if "saldo" in normalized:
                normalized["balance"] = normalized.pop("saldo")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # INTER (Quase padrão, mas usa "value")
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        elif institution_id == "inter":
            # value → amount
            if "value" in normalized:
                normalized["amount"] = normalized.pop("value")
        
        return normalized
    
    # ==========================================
    # HELPER METHODS
    # ==========================================
    
    def log_summary(self, logger: logging.Logger) -> None:
        """Loga resumo do batch processado."""
        log_level = self.alert_level.lower()
        
        top_errors = list(self.error_summary.items())[:3]
        top_errors_str = ", ".join(
            f"{err}: {count}" for err, count in top_errors
        ) if top_errors else "nenhum"
        
        logger.log(
            getattr(logging, log_level.upper()),
            f"Batch {self.batch_id} processado - "
            f"Banco: {self.institution_id} - "
            f"{self.total_valid}/{self.total_received} válidas "
            f"({self.rejection_rate:.1%} rejeição) - "
            f"Top erros: {top_errors_str}"
        )
    
    def to_metrics_dict(self) -> dict[str, Any]:
        """Converte para dict de métricas."""
        return {
            "batch_id": self.batch_id,
            "institution_id": self.institution_id,
            "processed_at": self.processed_at.isoformat(),
            "transactions_received": self.total_received,
            "transactions_valid": self.total_valid,
            "transactions_rejected": self.total_rejected,
            "rejection_rate": self.rejection_rate,
            "alert_level": self.alert_level,
            "should_alert": self.should_alert,
            "error_summary": self.error_summary,
            "field_error_summary": self.field_error_summary,
        }

# ==========================================
# FIM DO ARQUIVO transaction.py
# ==========================================

# 📊 RESUMO DO ARQUIVO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 
# SCHEMAS IMPLEMENTADOS:
#     1. TransactionWebhook      - Schema de ENTRADA (webhook)
#     2. RejectedTransaction     - DLQ (Dead Letter Queue)
#     3. TransactionOut          - Schema de SAÍDA (API response)
#     4. TransactionBatchResult  - Validação tolerante de batch
# 
# HELPERS DE PARSING:
#     - sanitize_text()          - Limpeza de texto (anti-XSS, anti-DoS)
#     - parse_amount_safe()      - Parser financeiro BR/US
#     - parse_date_safe()        - Parser de datas (timezone-aware)
#     - parse_status_safe()      - Parser de status (tolerante)
# 
# VALIDATORS (TransactionWebhook):
#     FASE 1: Field Validators
#         - parse_amount()       - Decimal (BR/US)
#         - parse_balance()      - Decimal|None
#         - parse_dates()        - datetime UTC
#         - parse_status()       - Enum
#         - sanitize_texts()     - str clean
#     
#     FASE 2: Model Validators (ordem crítica!)
#         STEP 1: validate_fundamental_fields()      # Existência
#         STEP 2: validate_temporal_consistency()    # Sanidade temporal
#         STEP 3: merge_descriptions()               # Fallback
#         STEP 4: validate_installments()            # Coerência
#         STEP 5: normalize_amount_sign()            # Sinal (type: DEBIT)
#         STEP 6: generate_composite_key()           # Hash (deduplicação)
# 
# FILOSOFIA:
#     ✅ Pydantic = Firewall semântico (estrutural)
#     ✅ Parsing robusto (múltiplos formatos)
#     ✅ Validação tolerante (rejeita item, não batch)
#     ✅ Segurança (limites, sanitização, anti-DoS)
#     ❌ NÃO faz validação semântica pesada (Polars faz)
# 
# PRÓXIMOS PASSOS:
#     1. Criar bank_strategy.py (BankStrategy para Pydantic)
#     2. Criar bank_profiles.yaml (perfis por banco)
#     3. Integrar BankStrategy no TransactionWebhook
#     4. Criar testes unitários (pytest)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━