# app/domain/__init__.py
"""
Domain - Engines de Negócio

COMPONENTE:
    - FinanceEngine: Score de saúde financeira (0-100)

USAGE:
    from app.domain import FinanceEngine
    
    engine = FinanceEngine()
    summary = engine.calculate_summary(income=10000, expenses=7000)
    print(summary["health_score"])  # 100
"""

from .finance_engine import FinanceEngine

__all__ = ["FinanceEngine"]