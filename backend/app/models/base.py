# app/models/base.py
from app.core.database import Base

# Import all models here so Alembic can discover them
from app.models.user import User
from app.models.transaction import Transaction
from app.models.context_override import ContextOverride
from app.models.health_score import HealthScoreHistory
from app.models.financial_goal import FinancialGoal
from app.models.architect import ArchitectSimulation, ArchitectSimulationMetrics
from app.models.optimization_report import OptimizationReport

