"""
Conector de Restituição IRPF do Monitor de Direitos Esquecidos (T3).

A consulta real usa a API Consulta Restituição do SERPRO, mediante token de
Autorização de Compartilhamento gerado pelo titular no e-CAC — portanto não
pode rodar numa varredura automática sem ação do usuário. Este conector
informa se o ambiente está habilitado (credenciais SERPRO) e aponta para o
endpoint de consulta autorizada (`/api/v1/rights/{user_id}/ir/check`).

(Nota histórica: a versão anterior simulava restituições por hash do CPF —
removido por completo: nunca fabricar dinheiro para o usuário.)
"""

import logging
from datetime import datetime, timezone

from app.fiscal.rights_monitor.models import ForgottenRightCandidate
from app.rights.connectors.serpro_restituicao import SerproRestituicaoConnector

logger = logging.getLogger(__name__)


class ReceitaConnector:
    """Aponta para a consulta autorizada real (e-CAC + SERPRO)."""

    def __init__(self, serpro: SerproRestituicaoConnector | None = None):
        self._action_url = (
            "https://www.gov.br/receitafederal/pt-br/assuntos/meu-imposto-de-renda"
        )
        self._serpro = serpro or SerproRestituicaoConnector()

    async def check_rights(self, user_id: str) -> ForgottenRightCandidate:
        if self._serpro.is_configured:
            description = (
                "Consulta em tempo real habilitada: gere uma Autorização de "
                "Compartilhamento no e-CAC (Compartilha Receita Federal) e envie o "
                "token em POST /api/v1/rights/{user_id}/ir/check para ver valor e "
                "situação da sua restituição."
            )
        else:
            description = (
                "Verifique sua restituição no app Meu Imposto de Renda ou no e-CAC. "
                "A consulta em tempo real pela Nexa (API SERPRO) ainda não está "
                "habilitada neste ambiente."
            )
        logger.info(
            "ReceitaConnector: serpro_configurado=%s (user: %s)",
            self._serpro.is_configured, user_id,
        )
        return ForgottenRightCandidate(
            source="IR_RESTITUTION",
            status="PENDING_VERIFICATION",
            estimated_amount=0.0,
            description=description,
            action_url=self._action_url,
            last_checked_at=datetime.now(timezone.utc),
        )
