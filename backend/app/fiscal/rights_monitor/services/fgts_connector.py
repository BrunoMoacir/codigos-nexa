import logging
from datetime import datetime, timezone
from typing import Optional
from app.fiscal.rights_monitor.models import ForgottenRightCandidate

logger = logging.getLogger(__name__)

class FGTSConnector:
    """
    Conector para o FGTS (Caixa Econômica).
    
    Mock inicial para simular saldos inativos do FGTS.
    """

    def __init__(self):
        self._action_url = "https://www.caixa.gov.br/beneficios-trabalhador/fgts/Paginas/default.aspx"

    async def check_rights(self, user_id: str, cpf: str) -> ForgottenRightCandidate:
        logger.info(f"FGTSConnector: Consultando FGTS inativo para o CPF {cpf} (user: {user_id})")
        
        # Lógica simulada: 1 em cada 4 usuários tem FGTS inativo.
        has_values = (hash(cpf + "fgts") % 4) == 0
        
        if has_values:
            estimated_amount = 500.0 + (hash(cpf) % 2000) # Mock: R$ 500 a R$ 2499
            return ForgottenRightCandidate(
                source="FGTS",
                status="AVAILABLE",
                estimated_amount=estimated_amount,
                description="Saldo inativo de FGTS detectado.",
                action_url=self._action_url,
                last_checked_at=datetime.now(timezone.utc)
            )
        else:
            return ForgottenRightCandidate(
                source="FGTS",
                status="NOT_FOUND",
                estimated_amount=0.0,
                description="Não há saldo inativo do FGTS disponível.",
                action_url=self._action_url,
                last_checked_at=datetime.now(timezone.utc)
            )
