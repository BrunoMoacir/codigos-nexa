"""
app/jobs/opportunity_scan.py — Job diário 03h00 (OPP)

Para cada usuário ativo, executa OpportunityEngine.analyze() e persiste
snapshot em opportunity_snapshots.

Lido por: agent/tools/get_opportunities.py, agent/tools/get_annual_wrapped.py
"""

import logging

from app.jobs._base import get_active_user_ids, job_guard

logger = logging.getLogger(__name__)


@job_guard("opportunity_scan")
async def run_opportunity_scan() -> None:
    user_ids = get_active_user_ids()
    logger.info("[opportunity_scan] %d usuários ativos", len(user_ids))

    from app.opportunities.services.opportunity_engine import OpportunityEngine
    engine = OpportunityEngine()

    success = skipped = errors = 0

    for user_id in user_ids:
        try:
            result = engine.analyze(
                user_id=user_id,
                holding_months=12,
                persist_snapshot=True,
            )
            if result.idle_amount > 0:
                success += 1
            else:
                skipped += 1
        except Exception as exc:
            logger.warning("[opportunity_scan] user=%s erro: %s", user_id, exc)
            errors += 1

    logger.info(
        "[opportunity_scan] done: %d snapshots, %d sem ociosidade, %d erros",
        success, skipped, errors,
    )
