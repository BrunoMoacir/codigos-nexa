"""
app/jobs/daily_digest.py — Job diário 07h00 (R1.c)

Compila os eventos do dia anterior para cada usuário ativo e envia via
email (ou push quando o app mobile existir). Roda depois dos outros jobs
para ter os snapshots mais recentes disponíveis.

Status: STUB — depende de delivery_service (item 1.2) e das tabelas
        daily_digest_log e notification_delivery_log (item 2.x).
"""

import logging
from app.jobs._base import get_active_user_ids, job_guard

logger = logging.getLogger(__name__)


@job_guard("daily_digest")
async def run_daily_digest() -> None:
    user_ids = get_active_user_ids()
    logger.info("[daily_digest] %d usuários ativos — envio de digest pendente de delivery_service", len(user_ids))
    # TODO:
    #   1. Para cada user_id, verificar user_settings.notification_frequency != "off"
    #   2. Coletar oportunidades (opportunity_snapshots), alertas (notification_events) do dia
    #   3. Formatar digest em HTML
    #   4. Chamar delivery_service.send_email()
    #   5. Registrar em daily_digest_log
