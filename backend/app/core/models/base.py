# app/models/base.py
from app.core.database import Base

# Import all models here so Alembic can discover them
from app.core.models.user import User
from app.core.models.transaction import Transaction
from app.divider.models import ContextOverride
from app.health_score.models import HealthScoreHistory
from app.goals.models import FinancialGoal
from app.architect.models_orm import ArchitectSimulation, ArchitectSimulationMetrics
from app.optimizer.models_orm import OptimizationReport, RecommendationFeedback
from app.agent.models import ChatMessage

