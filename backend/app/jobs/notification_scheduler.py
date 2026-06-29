"""
app/jobs/notification_scheduler.py — Job a cada 6h (MX.3)

Delega para NotificationEngine.run_for_all_users(), que:
  1. Para cada usuário ativo, detecta tarifas aumentadas em bank_fee_history.
  2. Gera notificações TARIFA_AUMENTO_UNILATERAL quando delta >= 10%.
  3. Entrega via delivery_service (email ou in_app conforme user_settings).
"""

import logging
from app.jobs._base import job_guard

logger = logging.getLogger(__name__)


@job_guard("notification_scheduler")
async def run_notification_scheduler() -> None:
    from app.notifications.engine import NotificationEngine

    results = await NotificationEngine().run_for_all_users()

    total = sum(len(v) for v in results.values())
    logger.info(
        "[notification_scheduler] %d notificações entregues para %d usuários",
        total, len(results),
    )
