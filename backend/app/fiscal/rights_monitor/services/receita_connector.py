import logging
from datetime import datetime, timezone
from typing import Optional
from app.fiscal.rights_monitor.models import ForgottenRightCandidate

logger = logging.getLogger(__name__)

class ReceitaConnector:
    """
    Conector para a Receita Federal (Restituição IRPF).
    
    Mock inicial para simular restituição de imposto de renda não sacada.
    """

    def __init__(self):
        self._action_url = "https://www.gov.br/receitafederal/pt-br/assuntos/meu-imposto-de-renda"

    async def check_rights(self, user_id: str, cpf: str) -> ForgottenRightCandidate:
        logger.info(f"ReceitaConnector: Consultando Restituição IRPF para o CPF {cpf} (user: {user_id})")
        
        # Lógica simulada: 1 em cada 5 usuários tem restituição parada.
        has_values = (hash(cpf + "irpf") % 5) == 0
        
        if has_values:
            estimated_amount = 200.0 + (hash(cpf) % 1500) # Mock: R$ 200 a R$ 1699
            return ForgottenRightCandidate(
                source="IR_RESTITUTION",
                status="AVAILABLE",
                estimated_amount=estimated_amount,
                description="Lote de Restituição do IRPF liberado e não sacado.",
                action_url=self._action_url,
                last_checked_at=datetime.now(timezone.utc)
            )
        else:
            return ForgottenRightCandidate(
                source="IR_RESTITUTION",
                status="NOT_FOUND",
                estimated_amount=0.0,
                description="Nenhuma restituição do IRPF pendente encontrada.",
                action_url=self._action_url,
                last_checked_at=datetime.now(timezone.utc)
            )
