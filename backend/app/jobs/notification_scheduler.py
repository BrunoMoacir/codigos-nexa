"""
app/jobs/notification_scheduler.py — Job a cada 6h (MX.3)

Gera notificações proativas para todos os usuários ativos sem precisar que
o usuário abra o app. Quando NotificationEngine estiver pronto, substitui
o modelo reativo atual.

Status: STUB — NotificationEngine será desacoplado no item 3.3.
"""

import logging
from app.jobs._base import get_active_user_ids, job_guard

logger = logging.getLogger(__name__)


@job_guard("notification_scheduler")
async def run_notification_scheduler() -> None:
    user_ids = get_active_user_ids()
    logger.info("[notification_scheduler] %d usuários ativos — geração proativa pendente de implementação", len(user_ids))
    # TODO: para cada user_id, chamar NotificationEngine.run_for_user()
    #       e delivery_service.deliver() para enviar pelo canal configurado
