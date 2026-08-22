"""
Conector SVR do Monitor de Direitos Esquecidos (T3 — visão fiscal).

O SVR não permite consulta autônoma por terceiros: a consulta pública oficial
exige um captcha respondido pelo titular, e o montante exige login GOV.BR.
Por isso este conector NÃO retorna valores — ele aponta para o fluxo de
consulta assistida real da Nexa (`/api/v1/rights/{user_id}/svr/check`),
onde o usuário responde o desafio oficial do BACEN e recebe a resposta
verdadeira na hora.

(Nota histórica: a versão anterior deste arquivo simulava valores por hash
do CPF — removido por completo: nunca fabricar dinheiro para o usuário.)
"""

import logging
from datetime import datetime, timezone

from app.fiscal.rights_monitor.models import ForgottenRightCandidate

logger = logging.getLogger(__name__)


class SVRConnector:
    """Aponta para a consulta assistida real do SVR (sem fabricar valores)."""

    def __init__(self):
        self._action_url = "https://valoresareceber.bcb.gov.br/"

    async def check_rights(self, user_id: str) -> ForgottenRightCandidate:
        logger.info("SVRConnector: fluxo assistido indicado (user: %s)", user_id)
        return ForgottenRightCandidate(
            source="SVR_BACEN",
            status="PENDING_VERIFICATION",
            estimated_amount=0.0,
            description=(
                "Consulta real disponível na Nexa: responda o desafio de segurança "
                "oficial do BACEN e saiba na hora se existe valor em seu nome "
                "(POST /api/v1/rights/{user_id}/svr/check). O montante e o resgate "
                "são feitos no portal oficial com login GOV.BR."
            ),
            action_url=self._action_url,
            last_checked_at=datetime.now(timezone.utc),
        )
