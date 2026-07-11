"""
app/seasonality/router.py — R2.c: Sazonalidade Fiscal

Endpoint: GET /seasonality/{user_id}
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import require_owner
from app.seasonality.models import SeasonalityResponse
from app.seasonality.service import get_seasonality_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/seasonality", tags=["Sazonalidade Fiscal (R2.c)"])


@router.get(
    "/{user_id}",
    response_model=SeasonalityResponse,
    summary="R2.c — Eventos fiscais sazonais ativos para o usuário",
    description=(
        "Retorna os eventos do calendário fiscal brasileiro (IR, restituição, "
        "IPVA/IPTU, DAS/DASN-SIMEI, 13º, lucro do FGTS) cuja janela de alerta "
        "está ativa, personalizados com o perfil do usuário: eventos de MEI só "
        "aparecem para quem tem sinal de MEI/PJ, eventos de 13º só para quem "
        "tem salário recorrente, e valores são estimados a partir de dados "
        "reais (nunca inventados)."
    ),
)
def get_seasonality(user_id: str = Depends(require_owner)) -> SeasonalityResponse:
    logger.info("GET /seasonality/%s", user_id)
    try:
        return get_seasonality_service().get_events(user_id)
    except Exception as exc:
        logger.error("GET /seasonality/%s erro: %s", user_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao montar o calendário fiscal.")
