"""
app/jobs/fee_snapshot.py — Job diário 02h00 (D2/D4)

Persiste snapshot de tarifas bancárias para cada usuário ativo em bank_fee_history.
Necessário para: detectar cobranças indevidas (D2) e mudanças unilaterais (D4).

Status: STUB — lógica de persistência será implementada junto com o módulo defense/.
"""

import logging
from app.jobs._base import get_active_user_ids, job_guard

logger = logging.getLogger(__name__)


@job_guard("fee_snapshot")
async def run_fee_snapshot() -> None:
    user_ids = get_active_user_ids()
    logger.info("[fee_snapshot] %d usuários ativos — snapshot de tarifas pendente de implementação", len(user_ids))
    # TODO: para cada user_id, chamar BankFeeAnalyzer.analyze() e persistir em bank_fee_history
