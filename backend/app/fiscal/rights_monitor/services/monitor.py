import asyncio
import logging
from datetime import datetime, timezone
from app.fiscal.rights_monitor.models import ForgottenRightsReport, ForgottenRightCandidate
from app.fiscal.rights_monitor.services.svr_connector import SVRConnector
from app.fiscal.rights_monitor.services.fgts_connector import FGTSConnector
from app.fiscal.rights_monitor.services.receita_connector import ReceitaConnector

logger = logging.getLogger(__name__)

class RightsMonitorAggregator:
    """
    Agregador principal do Monitor de Direitos Esquecidos.
    Executa consultas em paralelo nos diferentes conectores.
    """

    def __init__(self):
        self.svr = SVRConnector()
        self.fgts = FGTSConnector()
        self.receita = ReceitaConnector()

    async def run_scan(self, user_id: str) -> ForgottenRightsReport:
        """
        Varredura de status por fonte. NÃO recebe CPF: nenhum dos conectores
        usa — as três consultas reais dependem de ação do titular (captcha do
        BACEN, token do e-CAC) e não de um CPF passado por parâmetro.
        """
        logger.info(f"RightsMonitorAggregator: Iniciando varredura para user {user_id}")
        
        # Executa as consultas em paralelo para minimizar tempo de resposta
        results = await asyncio.gather(
            self.svr.check_rights(user_id),
            self.fgts.check_rights(user_id),
            self.receita.check_rights(user_id),
            return_exceptions=True
        )

        candidates: list[ForgottenRightCandidate] = []
        total_amount = 0.0

        for res in results:
            if isinstance(res, Exception):
                logger.error(f"Erro em um dos conectores do Monitor de Direitos Esquecidos: {res}")
                continue
            
            # Se for um candidato válido
            if isinstance(res, ForgottenRightCandidate):
                candidates.append(res)
                if res.status == "AVAILABLE":
                    total_amount += res.estimated_amount

        return ForgottenRightsReport(
            user_id=user_id,
            total_estimated_amount=total_amount,
            candidates=candidates,
            generated_at=datetime.now(timezone.utc)
        )
