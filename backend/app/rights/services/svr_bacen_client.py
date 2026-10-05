"""
app/rights/services/svr_bacen_client.py — SVR BACEN (Valores a Receber)

Não existe API pública JSON para consulta por CPF — o portal usa autenticação
GOV.BR (OAuth2 gov.br) e não expõe endpoint documentado de terceiros.

Esta implementação:
  - lê bank_fee_history apenas para EXPLICAR por que vale consultar (contas
    inativas, tarifas contestáveis) — nunca para produzir um valor;
  - sempre orienta o usuário ao canal oficial (valoresareceber.bcb.gov.br).

A consulta REAL existe e está em `POST /rights/{user_id}/svr/check`: a API
pública do BACEN, com o captcha oficial respondido pelo próprio usuário,
responde se há valor. O montante exige login GOV.BR no portal.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from app.rights.models import ForgottenRight
from app.core.formatacao import brl

logger = logging.getLogger(__name__)


class SvrBacenClient:
    """
    Verificador de Valores a Receber — SVR BACEN.

    Explica por que vale consultar e aponta para a consulta assistida real.
    Não produz valor: o SVR público não devolve montante.
    """

    def check(self, user_id: str, ctx=None) -> ForgottenRight:
        # `ctx` entra por uniformidade com os outros verificadores; o SVR não
        # depende do extrato — o sinal dele vem do histórico de tarifas.
        _estimated, reason = self._estimate_from_fee_history(user_id)

        return ForgottenRight(
            category="svr_bacen",
            title="SVR BACEN — Valores a Receber de Instituições Financeiras",
            description=(
                "O SVR BACEN lista saldos esquecidos em contas encerradas, cheques não sacados, "
                "quotas de consórcio não retiradas, tarifas cobradas indevidamente e parcelas "
                "restituíveis de seguros."
                # Havia aqui "a mediana entre os usuários que encontram valores é de
                # aproximadamente R$ 150" — estatística sem fonte, apresentada ao
                # usuário como fato. Removida: número em texto de produto precisa de
                # origem verificável.
            ),
            estimated_amount=None,        # a consulta pública do SVR não devolve valor
            estimated_confidence="unknown",
            relevance_reason=reason,
            official_channel="Portal SVR BACEN (acesso com GOV.BR)",
            official_url="https://valoresareceber.bcb.gov.br",
            action_steps=[
                "Consulte agora dentro da Nexa: informamos na hora se existe valor em seu nome "
                "(você só responde o desafio de segurança oficial do BACEN).",
                "Se houver valores, acesse valoresareceber.bcb.gov.br com sua conta GOV.BR "
                "(nível prata ou ouro) para ver o montante e solicitar o resgate.",
                "Escolha como receber: Pix ou TED — o banco tem até 12 dias úteis para pagar.",
                "⚠️ Nunca forneça senha GOV.BR a terceiros ou apps não oficiais.",
            ],
            warning=(
                "A consulta pública do SVR informa apenas SE há valores; o montante e o "
                "resgate exigem login GOV.BR no portal oficial."
            ),
        )

    def _estimate_from_fee_history(self, user_id: str) -> tuple[None, str]:
        """
        Devolve apenas o MOTIVO de relevância. Nunca um valor: a consulta
        pública do SVR responde `temValorAReceber: bool` e mais nada — o
        montante exige login GOV.BR no portal oficial. Inventar um número aqui
        seria fabricar dinheiro para uma fonte que nem o BACEN quantifica sem
        autenticação.
        """
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
                    f"Foram identificadas tarifas bancárias (total {brl(total_fees)}). "
                    "Tarifas cobradas indevidamente podem aparecer como crédito no SVR."
                )
            return None, "Consulte o SVR mesmo sem cobranças recentes — contas antigas também podem ter valores."

        except Exception as exc:
            logger.warning("[SvrBacenClient] user=%s: %s", user_id, exc)
            return None, "Consulte o portal oficial para verificar se há valores a receber."
