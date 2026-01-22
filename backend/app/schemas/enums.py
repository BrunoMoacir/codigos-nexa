"""
Enums compartilhados entre validação Pydantic, BankStrategy e Polars.

Centralizar aqui evita imports circulares e garante consistência.
"""

from enum import Enum

#Adicionar um currency
# ==========================================
# STATUS DE DADOS
# ==========================================

class DataStatus(str, Enum):
    """
    Status de confiança dos dados após validação.
    
    Usado por:
        - BankStrategy (validação por banco)
        - Polars validators (consistência temporal)
        - Core Engine (decisão de fallback)
    
    Fluxo:
        TRUSTED → usar dados oficiais
        DEGRADED → misturar oficial + Shadow Invoice
        UNTRUSTED → Shadow Invoice completo
    """
    TRUSTED = "TRUSTED"        # Dados completos, <5% lacunas
    DEGRADED = "DEGRADED"      # Lacunas 5-20%, usar híbrido
    UNTRUSTED = "UNTRUSTED"    # Lacunas >20%, só Shadow Invoice


class DataSource(str, Enum):
    """
    Origem dos dados.
    
    Usado para:
        - Rastreabilidade (audit trail)
        - Aplicar BankStrategy correto
        - Logging estruturado
    """
    PLUGGY = "PLUGGY"           # API Pluggy
    BELVO = "BELVO"             # API Belvo
    SALTEDGE = "SALTEDGE"       # API Salt Edge
    MANUAL_CSV = "MANUAL_CSV"   # Upload de CSV pelo usuário
    SHADOW = "SHADOW"           # Gerado pelo Shadow Invoice
    UNKNOWN = "UNKNOWN"         # Origem não identificada


class TransactionStatus(str, Enum):
    """
    Status da transação no banco.
    
    Importante para:
        - Evitar duplicatas (PENDING → POSTED)
        - Precisão de curto prazo
        - Validação de consistência
    """
    POSTED = "POSTED"           # Efetivada
    PENDING = "PENDING"         # Pendente (pode mudar valor/data)
    PROCESSED = "PROCESSED"     # Processada (Belvo usa isso)
    CANCELLED = "CANCELLED"     # Cancelada


class BankTier(str, Enum):
    """
    Tier de confiabilidade do banco.
    
    Baseado em observações reais de produção.
    """
    TIER_1 = "TIER_1"  # Nubank, C6, BTG → Excelentes
    TIER_2 = "TIER_2"  # Inter, XP, Original → Bons
    TIER_3 = "TIER_3"  # Itaú, Bradesco, Santander → Problemáticos
    TIER_4 = "TIER_4"  # PicPay, Mercado Pago → Muito instáveis


class FieldImportance(str, Enum):
    """
    Nível de importância de um campo para o Core Engine.
    
    Baseado na sua categorização:
        1️⃣ FUNDAMENTAL → Sem isso não funciona
        2️⃣ CRITICAL_SUBSTITUTABLE → Fallback possível
        3️⃣ QUALITY_ENHANCER → Melhora, não bloqueia
        4️⃣ DISPOSABLE → Não entra no Core Engine
    """
    FUNDAMENTAL = "FUNDAMENTAL"                 # transaction_id, amount, date
    CRITICAL_SUBSTITUTABLE = "CRITICAL_SUBSTITUTABLE"  # description, balance
    QUALITY_ENHANCER = "QUALITY_ENHANCER"       # category, status
    DISPOSABLE = "DISPOSABLE"                   # MCC, geo, UI metadata


# ==========================================
# MAPEAMENTO DE IMPORTÂNCIA
# ==========================================

FIELD_IMPORTANCE_MAP = {
    # 1️⃣ FUNDAMENTAL (não-negociáveis)
    "transaction_id": FieldImportance.FUNDAMENTAL,
    "account_id": FieldImportance.FUNDAMENTAL,
    "institution_id": FieldImportance.FUNDAMENTAL,
    "date": FieldImportance.FUNDAMENTAL,
    "amount": FieldImportance.FUNDAMENTAL,
    
    # 2️⃣ CRÍTICO MAS SUBSTITUÍVEL
    "description": FieldImportance.CRITICAL_SUBSTITUTABLE,
    "balance": FieldImportance.CRITICAL_SUBSTITUTABLE,
    
    # 3️⃣ MELHORADORES DE QUALIDADE
    "category": FieldImportance.QUALITY_ENHANCER,
    "status": FieldImportance.QUALITY_ENHANCER,
    "merchant": FieldImportance.QUALITY_ENHANCER,
    
    # 4️⃣ DESCARTÁVEIS (não usamos no Core)
    "mcc": FieldImportance.DISPOSABLE,
    "geolocation": FieldImportance.DISPOSABLE,
    "merchant_logo": FieldImportance.DISPOSABLE,
}


class Currency(str, Enum):
    """
    Códigos de moeda (ISO 4217).
    
    Usado para:
        - Normalização de inputs
        - Conversão cambial (futuro)
        - Validação de consistência
    """
    BRL = "BRL"  # Real Brasileiro (Default MVP)
    USD = "USD"  # Dólar Americano
    EUR = "EUR"  # Euro
    GBP = "GBP"  # Libra Esterlina