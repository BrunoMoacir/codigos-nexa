"""
app/rights/router.py — T3: Monitor de Direitos Esquecidos

GET /api/v1/rights/{user_id}  — executa os 4 checkers e retorna orientação estruturada

Nenhum dado é obtido de APIs privadas ou áreas autenticadas de terceiros.
Toda a verificação real é feita pelo usuário nos canais oficiais indicados.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.core.security import require_owner
from app.rights.models import ForgottenRight, RightsResponse
from app.rights.services.svr_bacen_client import SvrBacenClient
from app.rights.services.fgts_checker import FgtsChecker
from app.rights.services.pis_pasep_checker import PisPasepChecker
from app.rights.services.ir_restituicao_checker import IrRestituicaoChecker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rights", tags=["Rights (T3 — Direitos Esquecidos)"])

_svr = SvrBacenClient()
_fgts = FgtsChecker()
_pis = PisPasepChecker()
_ir = IrRestituicaoChecker()

_DISCLAIMER = (
    "Todas as estimativas são baseadas em transações Pluggy e heurísticas; "
    "os valores reais só podem ser verificados nos canais oficiais indicados. "
    "A Nexa não acessa, armazena nem consulta sistemas GOV.BR, CEF, BB ou Receita Federal. "
    "Confirme sempre diretamente nas plataformas oficiais antes de tomar qualquer ação."
)


@router.get("/{user_id}", response_model=RightsResponse)
def get_forgotten_rights(
    user_id: str = Depends(require_owner),
) -> RightsResponse:
    """
    **Monitor de Direitos Esquecidos (T3)**

    Verifica 4 fontes de direitos financeiros que podem estar esquecidos:

    | Fonte | O que verifica |
    |-------|---------------|
    | **SVR BACEN** | Saldos em contas encerradas, cheques não sacados, tarifas restituíveis |
    | **FGTS** | Saldo de contas de empregos anteriores (inclusive empresas extintas) |
    | **PIS/PASEP** | Cotas pré-1988 e abono salarial do ano-base |
    | **IR Restituição** | IRRF retido acima do devido, deduções esquecidas |

    **Importante:** nenhuma API privada ou área autenticada é consultada.
    Toda verificação real é feita pelo usuário nos canais oficiais indicados.
    """
    rights: list[ForgottenRight] = []
    context_note: str | None = None

    checkers = [
        ("svr_bacen", _svr),
        ("fgts", _fgts),
        ("pis_pasep", _pis),
        ("ir_restituicao", _ir),
    ]
    for name, checker in checkers:
        try:
            right = checker.check(user_id)
            rights.append(right)
        except Exception as exc:
            logger.error("[rights] checker=%s user=%s: %s", name, user_id, exc)

    # Soma apenas estimativas com confiança medium ou high
    recoverable = sum(
        r.estimated_amount
        for r in rights
        if r.estimated_amount and r.estimated_confidence in ("high", "medium")
    )

    # Contexto adicional de ganhos já identificados pelo Negociador
    negotiation_gain = _get_negotiation_gain(user_id)
    if negotiation_gain > 0:
        context_note = (
            f"O Negociador Nexa já identificou R$ {negotiation_gain:,.2f} em ganhos potenciais "
            "com seus bancos atuais. Combine com os direitos esquecidos acima para maximizar sua recuperação."
        )

    logger.info(
        "[rights] user=%s rights=%d estimated_recoverable=%.2f",
        user_id, len(rights), recoverable,
    )

    return RightsResponse(
        user_id=user_id,
        generated_at=datetime.now(timezone.utc),
        rights=rights,
        total_estimated_recoverable=round(recoverable, 2),
        disclaimer=_DISCLAIMER,
        context_note=context_note,
    )


def _get_negotiation_gain(user_id: str) -> float:
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            row = db.execute(
                text(
                    "SELECT COALESCE(SUM(potential_gain), 0)"
                    " FROM negotiation_history WHERE user_id = :uid"
                ),
                {"uid": user_id},
            ).fetchone()
        return float(row[0]) if row else 0.0
    except Exception:
        return 0.0
