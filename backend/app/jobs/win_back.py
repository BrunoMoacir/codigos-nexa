"""
app/jobs/win_back.py — R5.c Win-back Automático após inatividade

Dispara eventos de win-back (e.g. e-mail ou push) para usuários
inativos há 14 dias ou mais. Usa NotificationEngine/DeliveryService.
"""

import logging
from datetime import date, timedelta
from typing import List
from ._base import job_guard

logger = logging.getLogger(__name__)

class WinBackService:
    def get_inactive_users(self, days_inactive: int) -> List[str]:
        # Simula a busca de usuarios inativos via BD
        # Retorna mock_users inativos há exatamente `days_inactive`
        return ["user_inativo_1", "user_inativo_2"]

    async def trigger_win_back_for_user(self, user_id: str):
        # Simula o envio de email "Sentimos sua falta" com highlights
        # (Ex: Você perdeu X oportunidades do Radar enquanto esteve fora!)
        logger.info(f"Win-back disparado para o usuario: {user_id}")
        return True

@job_guard("r5c_win_back")
async def run_win_back_job():
    """
    Roda diariamente para encontrar usuários inativos (ex: 14 dias).
    """
    service = WinBackService()
    
    # Busca usuarios inativos a exatamente 14 dias para evitar spam diario
    inactive_users = service.get_inactive_users(days_inactive=14)
    
    logger.info(f"Iniciando Win-back para {len(inactive_users)} usuarios inativos ha 14 dias.")
    
    for user_id in inactive_users:
        try:
            await service.trigger_win_back_for_user(user_id)
        except Exception as e:
            logger.error(f"Erro ao disparar win-back para {user_id}: {e}")
