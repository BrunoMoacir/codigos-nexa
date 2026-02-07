"""
app/cashflow/__init__.py - Entry Point do Módulo Cashflow

╔══════════════════════════════════════════════════════════════════════╗
║ O QUE ESTE ARQUIVO FAZ                                               ║
╚══════════════════════════════════════════════════════════════════════╝

Exporta classes e funções públicas do módulo Cashflow:
    - CashflowProjector: Projeta saldo futuro com Shadow Invoices
    - SafeToSpendCalculator: Calcula quanto pode gastar com segurança

╔══════════════════════════════════════════════════════════════════════╗
║ COMO USAR                                                            ║
╚══════════════════════════════════════════════════════════════════════╝

# ✅ Import correto:
from app.cashflow import CashflowProjector, SafeToSpendCalculator

# Projetar cashflow
projector = CashflowProjector(horizon_days=30)
projection_df = projector.project(transactions_df, shadow_df)

# Calcular safe-to-spend
calculator = SafeToSpendCalculator(safety_buffer_pct=0.15)
result = calculator.calculate(projection_df, 30)

print(f"Você pode gastar: R$ {result.safe_to_spend_daily:.2f}/dia")

╔══════════════════════════════════════════════════════════════════════╗
║ INTEGRAÇÃO COM ETL                                                   ║
╚══════════════════════════════════════════════════════════════════════╝

Pipeline completo:
    1. ETL: Ingestor → Classifier → RecurringDetector → DataQuality
    2. Shadow Invoices: Detecta obrigações futuras
    3. Cashflow: Projeta saldo futuro ✅ NOVO
    4. Safe-to-Spend: Calcula quanto pode gastar ✅ NOVO
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from .projector import (
    CashflowProjector,
    ProjectionSummary,
    project_cashflow
)

from .safe_to_spend import (
    SafeToSpendCalculator,
    SafeToSpendResult,
    calculate_safe_to_spend
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API PÚBLICA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

__all__ = [
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CASHFLOW PROJECTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    "CashflowProjector",      # Classe principal
    "ProjectionSummary",      # Dataclass de resumo
    "project_cashflow",       # Helper function
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SAFE TO SPEND
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    "SafeToSpendCalculator",  # Classe principal
    "SafeToSpendResult",      # Dataclass de resultado
    "calculate_safe_to_spend", # Helper function
]

__version__ = "1.0.0"  # ✅ Cashflow COMPLETO


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# METADATA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

__author__ = "Nexa AI Team"
__status__ = "Production"
__description__ = "Módulo de projeção de cashflow e cálculo de safe-to-spend"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FIM DO ARQUIVO __init__.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
📊 RESUMO DO MÓDULO CASHFLOW (v1.0.0)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

COMPONENTES:
    1. CashflowProjector     → Projeta saldo futuro (integra Shadow Invoices)
    2. SafeToSpendCalculator → Calcula safe-to-spend (buffer 15%)

HELPERS:
    • project_cashflow()        → Wrapper do CashflowProjector
    • calculate_safe_to_spend() → Wrapper do SafeToSpendCalculator

DATACLASSES:
    • ProjectionSummary  → Resumo da projeção
    • SafeToSpendResult  → Resultado do cálculo

FEATURES:
    ✅ Integração com Shadow Invoices
    ✅ Projeção dia a dia (até 90 dias)
    ✅ Risk classification (LOW/MEDIUM/HIGH/CRITICAL)
    ✅ Buffer de segurança inteligente (15% + mínimo R$ 200)
    ✅ Cálculo de safe-to-spend diário e total

EXEMPLO DE USO:
    >>> from app.cashflow import CashflowProjector, SafeToSpendCalculator
    >>> 
    >>> # Projetar
    >>> projector = CashflowProjector(horizon_days=30)
    >>> projection_df = projector.project(df, shadow_df)
    >>> 
    >>> # Calcular safe-to-spend
    >>> calculator = SafeToSpendCalculator()
    >>> result = calculator.calculate(projection_df, 30)
    >>> 
    >>> print(f"Safe-to-spend: R$ {result.safe_to_spend_daily:.2f}/dia")
    >>> print(f"Risk level: {result.risk_level}")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""