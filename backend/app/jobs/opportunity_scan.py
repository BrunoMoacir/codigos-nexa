"""
app/jobs/opportunity_scan.py — Job diário 03h00 (OPP)

Para cada usuário ativo, detecta dinheiro parado e persiste em opportunity_snapshots.
Necessário para: Feed de Oportunidades e histórico do Wrapped (V2).

Status: STUB — implementação completa no módulo opportunities/.
"""

import logging
from app.jobs._base import get_active_user_ids, job_guard

logger = logging.getLogger(__name__)


@job_guard("opportunity_scan")
async def run_opportunity_scan() -> None:
    user_ids = get_active_user_ids()
    logger.info("[opportunity_scan] %d usuários ativos — scan de oportunidades pendente de implementação", len(user_ids))
    # TODO: para cada user_id, chamar OpportunityEngine.analyze() e persistir em opportunity_snapshots
