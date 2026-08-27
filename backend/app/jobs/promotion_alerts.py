"""
app/jobs/promotion_alerts.py — R4.b Alertas de Promoções (Milhas)

Verifica o PromotionTracker e aciona o NotificationEngine
para enviar avisos de promoções bonificadas ativas (ex: Livelo > TudoAzul).
Deve rodar periodicamente (ex: diariamente ou a cada hora).
"""

import logging
from ._base import job_guard, get_active_user_ids
from app.optimizer.promotion_tracker import PromotionTracker

logger = logging.getLogger(__name__)

class PromotionAlertsService:
    def __init__(self):
        self.tracker = PromotionTracker()
        
    async def process_alerts_for_user(self, user_id: str):
        # Em producao, cruzaríamos as carteiras do usuario com as promocoes ativas.
        # Por hora, pega as promocoes e simula envio.
        promos = self.tracker.get_active_promotions()
        
        if not promos:
            logger.info(f"[PromotionAlerts] Nenhuma promocao ativa para o usuario {user_id}")
            return False
            
        # Simula o envio de notificacao contextual via NotificationEngine
        # (ex: notificando o usuario que tem Smiles)
        count = len(promos)
        best_promo = promos[0]
        
        logger.info(f"Enviando alerta p/ {user_id}: Aproveite {best_promo.bonus_pct}% de bonus de {best_promo.loyalty_program} para {best_promo.partner}!")
        return True

@job_guard("r4b_promotion_alerts")
async def run_promotion_alerts_job():
    """
    Roda para encontrar promocoes ativas e disparar os alertas aos usuarios.
    """
    service = PromotionAlertsService()
    active_users = get_active_user_ids()
    
    if not active_users:
        logger.info("[PromotionAlerts] Nenhum usuario ativo.")
        return
        
    logger.info(f"Iniciando checagem de promocoes p/ {len(active_users)} usuarios.")
    
    for user_id in active_users:
        try:
            await service.process_alerts_for_user(user_id)
        except Exception as e:
            logger.error(f"Erro ao gerar alerta de promocao para {user_id}: {e}")
