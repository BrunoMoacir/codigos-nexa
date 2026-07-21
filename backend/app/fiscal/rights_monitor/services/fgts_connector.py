"""
Conector FGTS do Monitor de Direitos Esquecidos (T3).

Não existe API pública da Caixa para consulta de saldo FGTS por terceiros —
a verificação é feita pelo titular no app FGTS ou presencialmente. Este
conector retorna orientação estruturada, sem fabricar valores.

(Nota histórica: a versão anterior simulava saldos por hash do CPF —
removido por completo: nunca fabricar dinheiro para o usuário.)
"""

import logging
from datetime import datetime, timezone

from app.fiscal.rights_monitor.models import ForgottenRightCandidate

logger = logging.getLogger(__name__)


class FGTSConnector:
    """Orientação de verificação do FGTS (sem API pública para terceiros)."""

    def __init__(self):
        self._action_url = (
            "https://www.caixa.gov.br/beneficios-trabalhador/fgts/Paginas/default.aspx"
        )

    async def check_rights(self, user_id: str, cpf: str) -> ForgottenRightCandidate:
        logger.info("FGTSConnector: orientação de verificação (user: %s)", user_id)
        return ForgottenRightCandidate(
            source="FGTS",
            status="PENDING_VERIFICATION",
            estimated_amount=0.0,
            description=(
                "Verifique saldos de contas FGTS de empregos anteriores (inclusive "
                "empresas extintas) no app FGTS da Caixa. Contas de empresas extintas "
                "podem exigir atendimento presencial na CEF com a carteira de trabalho."
            ),
            action_url=self._action_url,
            last_checked_at=datetime.now(timezone.utc),
        )
