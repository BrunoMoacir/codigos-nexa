"""
app/etl/bank_strategy/__init__.py - Entry Point do Módulo BankStrategy

╔══════════════════════════════════════════════════════════════════════╗
║ O QUE ESTE ARQUIVO FAZ                                               ║
╚══════════════════════════════════════════════════════════════════════╝

Exporta a função pública get_bank_strategy() que retorna a strategy
apropriada para cada banco (Nubank, Itaú, Inter, etc).

╔══════════════════════════════════════════════════════════════════════╗
║ API PÚBLICA                                                          ║
╚══════════════════════════════════════════════════════════════════════╝

get_bank_strategy(bank_id: str) → BankStrategy
    - Retorna strategy específica do banco
    - Fallback: DefaultStrategy para bancos desconhecidos
    - Thread-safe (strategies são stateless)

╔══════════════════════════════════════════════════════════════════════╗
║ COMO USAR                                                            ║
╚══════════════════════════════════════════════════════════════════════╝

# ✅ Import correto:
from app.forecast.etl.bank_strategy import get_bank_strategy

# Obter strategy
strategy = get_bank_strategy("nubank")

# Normalizar DataFrame
df_normalized = strategy.normalize(df)

# Avaliar qualidade
data_status = strategy.evaluate_quality(df_normalized)

╔══════════════════════════════════════════════════════════════════════╗
║ STRATEGIES DISPONÍVEIS                                               ║
╚══════════════════════════════════════════════════════════════════════╝

• nubank    → NubankStrategy (TIER_1 - Excelente)
• inter     → InterStrategy (TIER_2 - Bom)
• itau      → ItauStrategy (TIER_3 - Problemático)
• *outros*  → DefaultStrategy (Fallback universal)
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from .registry import get_bank_strategy
from .base import BankStrategy

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API PÚBLICA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

__all__ = [
    "get_bank_strategy",  # Factory function (principal)
    "BankStrategy",       # Interface base (para type hints)
]

__version__ = "1.0.0"