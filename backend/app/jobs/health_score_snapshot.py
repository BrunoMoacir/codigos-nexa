"""
app/jobs/health_score_snapshot.py — Job diário 04h00 (MX.1)

Recalcula e persiste o health score de cada usuário ativo em health_score_history.
Garante que o histórico mensal existe mesmo sem o usuário abrir o app.

Status: STUB — cálculo real já existe em health_score/, falta apenas o loop de usuários.
"""

import logging
from app.jobs._base import get_active_user_ids, job_guard

logger = logging.getLogger(__name__)


@job_guard("health_score_snapshot")
async def run_health_score_snapshot() -> None:
    user_ids = get_active_user_ids()
    logger.info("[health_score_snapshot] %d usuários ativos — snapshot de health score pendente", len(user_ids))
    # TODO: para cada user_id, chamar HealthScoreService.calculate_and_persist()
