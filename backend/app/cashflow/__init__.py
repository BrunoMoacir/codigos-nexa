# app/cashflow/__init__.py
# LEGACY COMPATIBILITY LAYER
# All cashflow modules have moved to app.forecast.cashflow (engine) and app.budget (budget_advisor)

from app.forecast.cashflow.projector import CashflowProjector, ProjectionSummary
from app.forecast.cashflow.safe_to_spend import SafeToSpendCalculator, SafeToSpendResult
from app.forecast.cashflow.burn_rate import BurnRateAnalyzer, BurnRateReport, CategoryBurnRate
from app.forecast.cashflow.engine import CashflowEngine
from app.budget.budget_advisor import (
    BudgetAdvisor,
    BudgetSuggestion,
    CategoryAllocation,
    BudgetCut,
    GroupSummary,
    suggest_budget,
)

__all__ = [
    "CashflowProjector",
    "ProjectionSummary",
    "SafeToSpendCalculator",
    "SafeToSpendResult",
    "BurnRateAnalyzer",
    "BurnRateReport",
    "CategoryBurnRate",
    "CashflowEngine",
    "BudgetAdvisor",
    "BudgetSuggestion",
    "CategoryAllocation",
    "BudgetCut",
    "GroupSummary",
    "suggest_budget",
]
