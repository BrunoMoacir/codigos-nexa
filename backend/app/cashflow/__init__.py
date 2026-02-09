# app/cashflow/__init__.py
"""
Módulo Cashflow - Análise de Fluxo de Caixa

COMPONENTES:
    - CashflowProjector: Projeção diária (30 dias)
    - SafeToSpendCalculator: Cálculo de gastos seguros  
    - CashflowEngine: Orquestrador completo

USAGE BÁSICO (RECOMENDADO):
    from app.cashflow import CashflowEngine
    
    engine = CashflowEngine()
    result = engine.analyze(transactions_df, shadow_invoices_df)

USAGE AVANÇADO (Componentes individuais):
    from app.cashflow import CashflowProjector, SafeToSpendCalculator
    
    projector = CashflowProjector(horizon_days=30)
    projection_df = projector.project(df, shadow_df)
    
    calculator = SafeToSpendCalculator()
    sts = calculator.calculate(projection_df, 30)
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from .projector import CashflowProjector, ProjectionSummary
from .safe_to_spend import SafeToSpendCalculator, SafeToSpendResult
from .engine import CashflowEngine

__all__ = [
    "CashflowProjector",
    "ProjectionSummary",
    "SafeToSpendCalculator",
    "SafeToSpendResult",
    "CashflowEngine",
]

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

from .engine import CashflowEngine

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API PÚBLICA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

__all__ = [
    # Projector (lógica de projeção)
    "CashflowProjector",
    "ProjectionSummary",
    "project_cashflow",
    
    # Safe-to-Spend (lógica de cálculo)
    "SafeToSpendCalculator",
    "SafeToSpendResult",
    "calculate_safe_to_spend",
    
    # Engine (orquestrador)
    "CashflowEngine",
]

__version__ = "2.0.0"
__author__ = "Nexa AI Team"