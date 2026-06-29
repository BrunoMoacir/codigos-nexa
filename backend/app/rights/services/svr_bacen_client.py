"""
app/rights/services/svr_bacen_client.py — SVR BACEN (Valores a Receber)

Não existe API pública JSON para consulta por CPF — o portal usa autenticação
GOV.BR (OAuth2 gov.br) e não expõe endpoint documentado de terceiros.

Esta implementação:
  - lê bank_fee_history para estimar cobranças potencialmente contestáveis
    que podem aparecer no SVR após resolução com o banco;
  - sempre orienta o usuário ao canal oficial (valoresareceber.bcb.gov.br).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from app.rights.models import ForgottenRight

logger = logging.getLogger(__name__)


class SvrBacenClient:
    """
    Verificador de Valores a Receber — SVR BACEN.

    Faz consulta heurística em bank_fee_history para estimar relevância
    e retorna orientação de acesso ao portal oficial.
    """

    def check(self, user_id: str) -> ForgottenRight:
        estimated, reason = self._estimate_from_fee_history(user_id)

        return ForgottenRight(
            category="svr_bacen",
            title="SVR BACEN — Valores a Receber de Instituições Financeiras",
            description=(
                "O SVR BACEN lista saldos esquecidos em contas encerradas, cheques não sacados, "
                "quotas de consórcio não retiradas, tarifas cobradas indevidamente e parcelas "
                "restituíveis de seguros. A mediana entre os usuários que encontram valores "
                "é de aproximadamente R$ 150."
            ),
            estimated_amount=estimated,
            estimated_confidence="low" if estimated and estimated > 0 else "unknown",
            relevance_reason=reason,
            official_channel="Portal SVR BACEN (acesso com GOV.BR)",
            official_url="https://valoresareceber.bcb.gov.br",
            action_steps=[
                "Acesse valoresareceber.bcb.gov.br com sua conta GOV.BR (nível prata ou ouro).",
                "Selecione 'Consultar valores a receber' e confirme seus dados.",
                "Se houver valores, escolha como receber: Pix ou TED na conta indicada pelo banco.",
                "O prazo de pagamento pelo banco é de até 12 dias úteis após a solicitação.",
                "⚠️ Nunca forneça senha GOV.BR a terceiros ou apps não oficiais.",
            ],
            warning=(
                "O SVR não expõe API pública para consulta por CPF. "
                "Somente o portal oficial permite verificar se há valores disponíveis."
            ),
        )

    def _estimate_from_fee_history(self, user_id: str) -> tuple[Optional[float], str]:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            cutoff = (date.today() - timedelta(days=180)).strftime("%Y-%m")
            with SessionLocal() as db:
                row = db.execute(
                    text(
                        "SELECT COUNT(DISTINCT bank_name), COALESCE(SUM(amount), 0)"
                        " FROM bank_fee_history"
                        " WHERE user_id = :uid AND month >= :cutoff"
                    ),
                    {"uid": user_id, "cutoff": cutoff},
                ).fetchone()

            if not row:
                return None, "Histórico de tarifas não disponível; consulte o SVR para confirmar."

            bank_count, total_fees = int(row[0]), float(row[1])
            if bank_count >= 2:
                return None, (
                    f"Você tem tarifas registradas em {bank_count} bancos nos últimos 6 meses. "
                    "Contas que ficaram inativas podem ter saldo no SVR."
                )
            if total_fees > 0:
                return None, (
                    f"Foram identificadas tarifas bancárias (total R$ {total_fees:.2f}). "
                    "Tarifas cobradas indevidamente podem aparecer como crédito no SVR."
                )
            return None, "Consulte o SVR mesmo sem cobranças recentes — contas antigas também podem ter valores."

        except Exception as exc:
            logger.warning("[SvrBacenClient] user=%s: %s", user_id, exc)
            return None, "Consulte o portal oficial para verificar se há valores a receber."
