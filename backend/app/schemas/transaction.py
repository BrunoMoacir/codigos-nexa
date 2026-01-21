"""
Pydantic Schemas para Transações Open Finance.

Estratégia Multi-Banco:
    ✅ Aceitar variações de formato (permissivo)
    ✅ Validar FORMA, não semântica (isso é Polars)
    ✅ Parsear múltiplos formatos (datas, valores)
    ✅ Fallbacks explícitos (campos opcionais com default)
    ✅ Metadados de qualidade inline

Princípio:
    "Funcionalidade 1 não precisa do extrato perfeito.
     Precisa de informação suficiente para projetar fluxo de caixa
     com confiança mensurável."

Baseado em:
    - 4 níveis de importância (FUNDAMENTAL → DISPOSABLE)
    - Observações reais de 10+ bancos brasileiros
    - Compatibilidade Pluggy/Belvo/CSV
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Literal, Any
from datetime import datetime, date
from decimal import Decimal
import re

from app.schemas.enums import (
    DataStatus,
    DataSource,
    TransactionStatus,
    FieldImportance,
    FIELD_IMPORTANCE_MAP
)


# ==========================================
# TRANSACTION WEBHOOK (Entrada)
# ==========================================

class TransactionWebhook(BaseModel):
    """
    Schema de ENTRADA para webhooks Open Finance.
    
    Design:
        - Campos FUNDAMENTAIS → obrigatórios
        - Campos SUBSTITUÍVEIS → opcionais com fallback
        - Campos MELHORADORES → opcionais sem default
        - Campos DESCARTÁVEIS → ignorados (não declarados)
    
    Compatibilidade:
        ✅ Pluggy
        ✅ Belvo
        ✅ CSV upload
    
    Versionamento:
        - Schema versão: 1.0.0
        - Compatível com Pluggy API v2, Belvo v1
    """
    
    # ============================================
    # 1️⃣ FUNDAMENTAL (não-negociáveis)
    # ============================================
    
    transaction_id: str = Field(
        ...,
        alias="id",
        min_length=1,
        max_length=255,
        description="ID único da transação (idempotência, deduplicação)"
    )
    
    amount: Decimal = Field(
        ...,
        description=(
            "Valor da transação (matemática base). "
            "Positivo=entrada, negativo=saída. "
            "Aceita múltiplos formatos: 1500.00, -150,50, 'R$ 150,50'"
        )
    )
    
    transaction_date: str | datetime | date = Field(
        ...,
        alias="date",
        description=(
            "Data da transação (série temporal). "
            "Aceita: ISO 8601, DD/MM/YYYY, YYYY-MM-DD"
        )
    )
    
    account_id: str = Field(
        ...,
        alias="accountId",
        description="ID da conta (vincular saldo, conta, banco)"
    )
    
    # institution_id virá do contexto (item_id → institution_id)
    # Não vem no JSON individual da transação
    
    # ============================================
    # 2️⃣ CRÍTICO MAS SUBSTITUÍVEL (fallback possível)
    # ============================================
    
    description: str = Field(
        default="",  # ← Fallback: string vazia
        description=(
            "Descrição da transação. "
            "CRÍTICO para: detectar parcelamentos, recorrências. "
            "Fallback se ausente: usar padrão de datas + valor"
        )
    )
    
    balance: Decimal | None = Field(
        default=None,  # ← Fallback: None
        description=(
            "Saldo após transação. "
            "CRÍTICO para: Safe-to-Spend, validação de forecast. "
            "Fallback se ausente: estimar via cumsum"
        )
    )
    
    # ============================================
    # 3️⃣ MELHORADORES DE QUALIDADE (aumentam confiança)
    # ============================================
    
    category: str | None = Field(
        default=None,
        description=(
            "Categoria sugerida pelo banco. "
            "MELHORA: resumo semanal, gastos invisíveis. "
            "Fallback: classificador interno (CatBoost)"
        )
    )
    
    status: TransactionStatus = Field(
        default=TransactionStatus.POSTED,  # ← Assume POSTED se não vier
        description=(
            "Status da transação. "
            "MELHORA: evitar duplicatas, precisão curto prazo. "
            "Fallback: tratar como POSTED"
        )
    )
    
    merchant: str | None = Field(
        default=None,
        description=(
            "Nome do estabelecimento. "
            "MELHORA: limpeza de descriptions. "
            "Opcional: extraído de description se ausente"
        )
    )
    
    # ============================================
    # 4️⃣ METADADOS ADICIONAIS (compatibilidade)
    # ============================================
    
    currency: str = Field(
        default="BRL",
        alias="currencyCode",
        description="Moeda (99% BRL no Brasil)"
    )
    
    description_raw: str | None = Field(
        default=None,
        alias="descriptionRaw",
        description="Descrição crua (alguns bancos enviam 2 versões)"
    )
    
    observations: str | None = Field(
        default=None,
        description="Observações extras (Belvo usa isso)"
    )
    
    # Merchant detalhado (alguns bancos enviam objeto)
    merchant_details: dict[str, Any] | None = Field(
        default=None,
        alias="merchant",
        description="Objeto merchant com name, category, logo"
    )
    
    # Parcelamentos (importante para detectar!)
    installment_number: int | None = Field(
        default=None,
        description="Parcela atual (ex: 3 de 12)"
    )
    
    installment_total: int | None = Field(
        default=None,
        description="Total de parcelas"
    )
    
    # ============================================
    # METADADOS INTERNOS (set pelo webhook receiver)
    # ============================================
    
    source: DataSource = Field(
        default=DataSource.UNKNOWN,
        description="Origem dos dados (set pelo API handler)"
    )
    
    institution_id: str | None = Field(
        default=None,
        description="ID do banco (set pelo webhook receiver via item_id)"
    )
    
    # JSON completo para auditoria (salvo no S3)
    raw_payload: dict[str, Any] | None = Field(
        default=None,
        exclude=True,  # Não serializar em responses
        description="JSON completo para debug (S3 raw_events)"
    )
    
    class Config:
        populate_by_name = True  # Aceita aliases (id ou transaction_id)
        str_strip_whitespace = True  # Remove espaços automaticamente
        
    
    # ==========================================
    # VALIDATORS (Parsing Robusto)
    # ==========================================
    
    @field_validator("amount", mode="before")
    @classmethod
    def parse_amount(cls, v: Any) -> Decimal:
        """
        Parseia valores em múltiplos formatos.
        
        Aceita:
            - 1500.00 (US)
            - 1500,50 (BR)
            - -150.50 (negativo explícito)
            - (150.50) (negativo em parênteses - contabilidade)
            - "R$ 150,50" (com símbolo)
        
        Retorna:
            Decimal normalizado
        
        Raises:
            ValueError: formato não reconhecido
        """
        if isinstance(v, (int, float, Decimal)):
            return Decimal(str(v))
        
        if not isinstance(v, str):
            raise ValueError(
                f"Amount deve ser número ou string, recebido: {type(v).__name__}"
            )
        
        # Remove espaços, símbolos de moeda
        v = v.strip().replace("R$", "").replace("BRL", "").strip()
        
        # Detecta negativo em parênteses: (150.50) → -150.50
        if v.startswith("(") and v.endswith(")"):
            v = "-" + v[1:-1]
        
        # Remove separadores de milhar (pontos em BR, vírgulas em US)
        # Heurística: se tem vírgula E ponto → vírgula é milhar
        if "," in v and "." in v:
            # Ex: 1.500,50 (BR) ou 1,500.50 (US)
            if v.rindex(",") > v.rindex("."):
                # BR: 1.500,50
                v = v.replace(".", "").replace(",", ".")
            else:
                # US: 1,500.50
                v = v.replace(",", "")
        elif "," in v:
            # Só vírgula: assume BR (1500,50)
            v = v.replace(",", ".")
        
        # Remove espaços restantes
        v = v.replace(" ", "")
        
        try:
            return Decimal(v)
        except Exception as e:
            raise ValueError(
                f"Não foi possível parsear amount: '{v}'. "
                f"Formatos aceitos: 1500.00, -150,50, 'R$ 150,50'. "
                f"Erro: {e}"
            )
    
    
    @field_validator("amount")
    @classmethod
    def amount_cannot_be_zero(cls, v: Decimal) -> Decimal:
        """
        Transações com valor zero são inválidas.
        
        Rationale:
            - Não impacta fluxo de caixa
            - Pode ser erro de sincronização
            - Polui análises de recorrência
        """
        if v == 0:
            raise ValueError("Amount não pode ser zero")
        return v
    
    
    @field_validator("transaction_date", mode="before")
    @classmethod
    def parse_date(cls, v: Any) -> datetime:
        """
        Parseia datas em múltiplos formatos.
        
        Aceita:
            - ISO 8601: 2024-01-15T10:30:00.000Z
            - ISO 8601 com timezone: 2024-01-15T10:30:00-03:00
            - Apenas data: 2024-01-15
            - Formato BR: 15/01/2024
            - Formato US: 01/15/2024 (ambíguo, última opção)
        
        Retorna:
            datetime normalizado (UTC se sem timezone)
        
        Raises:
            ValueError: formato não reconhecido
        """
        if isinstance(v, datetime):
            return v
        
        if isinstance(v, date):
            return datetime.combine(v, datetime.min.time())
        
        if not isinstance(v, str):
            raise ValueError(
                f"Date deve ser string ou datetime, recebido: {type(v).__name__}"
            )
        
        v = v.strip()
        
        # 1. Tentar ISO 8601 (mais comum em APIs)
        try:
            # Remove 'Z' e trata como UTC
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except:
            pass
        
        # 2. Tentar apenas data ISO: 2024-01-15
        try:
            return datetime.strptime(v, "%Y-%m-%d")
        except:
            pass
        
        # 3. Tentar formato BR: 15/01/2024 (mais provável em CSV)
        try:
            return datetime.strptime(v, "%d/%m/%Y")
        except:
            pass
        
        # 4. Tentar formato US: 01/15/2024 (ambíguo, última opção)
        try:
            return datetime.strptime(v, "%m/%d/%Y")
        except:
            pass
        
        # Nenhum formato funcionou
        raise ValueError(
            f"Não foi possível parsear date: '{v}'. "
            f"Formatos aceitos: ISO 8601, YYYY-MM-DD, DD/MM/YYYY"
        )
    
    
    @field_validator("balance", mode="before")
    @classmethod
    def parse_balance(cls, v: Any) -> Decimal | None:
        """
        Parseia balance (pode ser null).
        
        40% dos bancos não enviam balance.
        Usa mesmo parser de amount.
        """
        if v is None or v == "":
            return None
        
        # Reusar parser de amount
        return cls.parse_amount(v)
    
    
    @field_validator("description")
    @classmethod
    def sanitize_description(cls, v: str) -> str:
        """
        Sanitização básica de description.
        
        - Remove múltiplos espaços
        - Remove caracteres de controle
        - Limita tamanho (evitar abuso)
        
        Nota: Normalização pesada (lowercase, etc) é feita no Polars.
        """
        if not v:
            return ""
        
        # Remove múltiplos espaços
        v = re.sub(r'\s+', ' ', v.strip())
        
        # Remove caracteres de controle (quebras de linha, tabs)
        v = re.sub(r'[\x00-\x1F\x7F]', '', v)
        
        # Limita tamanho (500 chars é MUITO generoso)
        if len(v) > 500:
            v = v[:500]
        
        return v
    
    
    @model_validator(mode="after")
    def extract_merchant_from_details(self):
        """
        Se merchant é None mas merchant_details existe,
        extrai merchant.name do objeto.
        
        Alguns bancos (C6, Inter):
            merchant: null
            merchant_details: {"name": "NETFLIX", "category": "..."}
        """
        if self.merchant is None and self.merchant_details:
            self.merchant = self.merchant_details.get("name")
        
        return self
    
    
    @model_validator(mode="after")
    def merge_descriptions(self):
        """
        Fallback de description.
        
        Prioridade:
            1. description (se não vazio)
            2. description_raw
            3. observations (Belvo/Bradesco)
        
        Bradesco exemplo:
            description: "COMPRA CARTAO" ← genérico
            observations: "FARMACIA SAO JOAO" ← útil!
        """
        if not self.description:
            if self.description_raw:
                self.description = self.description_raw
            elif self.observations:
                self.description = self.observations
        
        return self
    
    
    @model_validator(mode="after")
    def validate_fundamental_fields(self):
        """
        Validação final: campos FUNDAMENTAIS presentes?
        
        Se faltar qualquer FUNDAMENTAL → transação inutilizável.
        Rejeita evento individual, não lote inteiro.
        """
        fundamental_fields = [
            "transaction_id",
            "amount",
            "transaction_date",
            "account_id"
        ]
        
        missing = []
        for field in fundamental_fields:
            if getattr(self, field, None) is None:
                missing.append(field)
        
        if missing:
            raise ValueError(
                f"Campos FUNDAMENTAIS faltando: {', '.join(missing)}. "
                f"Transação inutilizável para Core Engine."
            )
        
        return self


# ==========================================
# TRANSACTION OUT (Saída para Frontend/API)
# ==========================================

class TransactionOut(BaseModel):
    """
    Schema de SAÍDA para frontend/API.
    
    Diferenças do TransactionWebhook:
        - Dados já processados (limpos, classificados)
        - Tipos normalizados (datetime, float)
        - Campos de confiança (confidence, data_status)
        - Sem raw_payload
    """
    
    id: str
    amount: float
    date: datetime
    description: str
    
    category: str | None = None
    merchant: str | None = None
    
    is_recurring: bool = False
    is_installment: bool = False
    installment_info: str | None = None  # "3/12"
    
    balance: float | None = None
    
    # Metadados de qualidade
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confiança nos dados processados (0.0 - 1.0)"
    )
    
    source: Literal["OFFICIAL", "SHADOW", "HYBRID"] = Field(
        description=(
            "OFFICIAL: dados do banco. "
            "SHADOW: gerado por Shadow Invoice. "
            "HYBRID: mistura (DEGRADED data_status)"
        )
    )
    
    data_status: DataStatus = Field(
        description="Status após BankStrategy + Polars validation"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "txn_nubank_123",
                "amount": -150.50,
                "date": "2024-01-15T10:30:00Z",
                "description": "Netflix Assinatura",
                "category": "Assinaturas",
                "merchant": "Netflix",
                "is_recurring": True,
                "is_installment": False,
                "balance": 3250.50,
                "confidence": 0.95,
                "source": "OFFICIAL",
                "data_status": "TRUSTED"
            }
        }


# ==========================================
# BATCH WEBHOOK (múltiplas transações)
# ==========================================

class TransactionBatchWebhook(BaseModel):
    """
    Webhook com múltiplas transações.
    
    Pluggy/Belvo enviam listas de 10-100 transações por webhook.
    
    Importante:
        - Se 1 transação falhar validação → rejeita ela, não o lote
        - item_id usado para buscar institution_id
        - fetched_at para rastreabilidade
    """
    
    transactions: list[TransactionWebhook] = Field(
        ...,
        min_length=1,
        description="Lista de transações (min: 1)"
    )
    
    # Metadados do batch
    account_id: str
    item_id: str  # Pluggy/Belvo connection ID
    institution_id: str  # "nubank", "inter", etc (set pelo webhook receiver)
    fetched_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Quando os dados foram buscados (rastreabilidade)"
    )

# ==========================================
# BATCH WEBHOOK COM VALIDAÇÃO TOLERANTE
# ==========================================

from typing import TypedDict
from pydantic import ValidationError
import structlog

logger = structlog.get_logger(__name__)


class RejectedTransaction(TypedDict):
    """
    Registro de transação rejeitada.
    
    Usado para:
        - Auditoria (salvar em DB)
        - Debugging (logs estruturados)
        - Alertas (se taxa de rejeição > threshold)
    """
    raw_data: dict[str, Any]
    error_type: str
    error_message: str
    field_errors: dict[str, list[str]]
    rejected_at: datetime


class TransactionBatchResult(BaseModel):
    """
    Resultado do processamento de batch com validação tolerante.
    
    Contém:
        - Transações válidas (processadas)
        - Transações rejeitadas (auditoria)
        - Métricas de qualidade
    """
    
    valid_transactions: list[TransactionWebhook] = Field(
        description="Transações que passaram na validação"
    )
    
    rejected_transactions: list[RejectedTransaction] = Field(
        description="Transações rejeitadas com motivo"
    )
    
    # Métricas
    total_received: int = Field(
        description="Total de transações no batch original"
    )
    
    total_valid: int = Field(
        description="Transações válidas"
    )
    
    total_rejected: int = Field(
        description="Transações rejeitadas"
    )
    
    rejection_rate: float = Field(
        ge=0.0,
        le=1.0,
        description="Taxa de rejeição (0.0 - 1.0)"
    )
    
    # Contexto
    account_id: str
    item_id: str
    institution_id: str
    processed_at: datetime = Field(default_factory=datetime.utcnow)
    
    
    @classmethod
    def from_raw_batch(
        cls,
        raw_transactions: list[dict[str, Any]],
        account_id: str,
        item_id: str,
        institution_id: str
    ) -> "TransactionBatchResult":
        """
        Processa batch com validação tolerante.
        
        Estratégia:
            1. Para cada transação:
                - Tenta validar com Pydantic
                - Se OK → adiciona em valid_transactions
                - Se FALHA → loga + adiciona em rejected_transactions
            2. Calcula métricas
            3. Alerta se rejection_rate > threshold
        
        Args:
            raw_transactions: Lista de dicts crus (JSON do webhook)
            account_id: ID da conta
            item_id: ID do item Pluggy/Belvo
            institution_id: ID do banco (ex: "nubank")
        
        Returns:
            TransactionBatchResult com válidas + rejeitadas
        
        Exemplo:
            >>> result = TransactionBatchResult.from_raw_batch(
            ...     raw_transactions=[{...}, {...}],
            ...     account_id="acc_123",
            ...     item_id="item_456",
            ...     institution_id="nubank"
            ... )
            >>> print(f"Válidas: {result.total_valid}, Rejeitadas: {result.total_rejected}")
        """
        
        valid_transactions: list[TransactionWebhook] = []
        rejected_transactions: list[RejectedTransaction] = []
        
        # Processar cada transação individualmente
        for idx, raw_txn in enumerate(raw_transactions):
            try:
                # Tentar validar com Pydantic
                txn = TransactionWebhook(
                    **raw_txn,
                    source=DataSource.PLUGGY,  # TODO: detectar dinamicamente
                    institution_id=institution_id
                )
                
                valid_transactions.append(txn)
                
            except ValidationError as e:
                # Transação inválida → registrar rejeição
                
                # Extrair erros por campo
                field_errors: dict[str, list[str]] = {}
                for error in e.errors():
                    field = ".".join(str(loc) for loc in error["loc"])
                    msg = error["msg"]
                    
                    if field not in field_errors:
                        field_errors[field] = []
                    field_errors[field].append(msg)
                
                rejected = RejectedTransaction(
                    raw_data=raw_txn,
                    error_type="ValidationError",
                    error_message=str(e),
                    field_errors=field_errors,
                    rejected_at=datetime.utcnow()
                )
                
                rejected_transactions.append(rejected)
                
                # Log estruturado para debugging
                logger.warning(
                    "transaction_rejected",
                    batch_index=idx,
                    account_id=account_id,
                    institution_id=institution_id,
                    transaction_id=raw_txn.get("id", "unknown"),
                    errors=field_errors,
                    # Não logar raw_data completo (pode ter PII)
                )
            
            except Exception as e:
                # Erro inesperado (não deveria acontecer)
                rejected = RejectedTransaction(
                    raw_data=raw_txn,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    field_errors={},
                    rejected_at=datetime.utcnow()
                )
                
                rejected_transactions.append(rejected)
                
                logger.error(
                    "transaction_unexpected_error",
                    batch_index=idx,
                    account_id=account_id,
                    error=str(e),
                    error_type=type(e).__name__
                )
        
        # Calcular métricas
        total_received = len(raw_transactions)
        total_valid = len(valid_transactions)
        total_rejected = len(rejected_transactions)
        rejection_rate = total_rejected / total_received if total_received > 0 else 0.0
        
        # Alerta se taxa de rejeição alta
        REJECTION_THRESHOLD = 0.20  # 20%
        
        if rejection_rate > REJECTION_THRESHOLD:
            logger.error(
                "high_rejection_rate",
                account_id=account_id,
                institution_id=institution_id,
                rejection_rate=rejection_rate,
                total_rejected=total_rejected,
                total_received=total_received,
                message=f"Taxa de rejeição {rejection_rate:.1%} acima do threshold {REJECTION_THRESHOLD:.1%}"
            )
        
        # Log final
        logger.info(
            "batch_processed",
            account_id=account_id,
            institution_id=institution_id,
            total_received=total_received,
            total_valid=total_valid,
            total_rejected=total_rejected,
            rejection_rate=rejection_rate
        )
        
        return cls(
            valid_transactions=valid_transactions,
            rejected_transactions=rejected_transactions,
            total_received=total_received,
            total_valid=total_valid,
            total_rejected=total_rejected,
            rejection_rate=rejection_rate,
            account_id=account_id,
            item_id=item_id,
            institution_id=institution_id
        )


# ==========================================
# HELPER: SALVAR REJEIÇÕES NO DB
# ==========================================

# TODO: Criar tabela rejected_transactions no Postgres
# Campos:
#   - id (UUID)
#   - account_id
#   - institution_id
#   - raw_data (JSONB)
#   - error_type
#   - error_message
#   - field_errors (JSONB)
#   - rejected_at (timestamp)
#   - reviewed (boolean) - para inbox de revisão manual