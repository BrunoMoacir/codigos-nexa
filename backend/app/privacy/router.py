"""
app/privacy/router.py — Endpoints de direitos do titular (LGPD arts. 18/19).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.core import audit
from app.core.security import require_owner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/privacy", tags=["Privacidade (LGPD)"])


class ErasureRequest(BaseModel):
    """Confirmação explícita — eliminação é irreversível."""
    confirm: str   # deve ser exatamente "EXCLUIR MEUS DADOS"


_CONFIRM_PHRASE = "EXCLUIR MEUS DADOS"


@router.get(
    "/export/{user_id}",
    summary="LGPD art. 18 V — Portabilidade: exportar todos os dados do titular",
    description=(
        "Retorna todos os dados pessoais e financeiros do titular em JSON "
        "estruturado, tabela a tabela (transações, metas, scores, desafios, "
        "conexões Open Finance, notificações...). Requer o token do próprio "
        "titular. O hash de senha nunca é incluído."
    ),
)
def export_data(request: Request, user_id: str = Depends(require_owner)) -> dict:
    from app.privacy.service import export_user_data

    ip = request.client.host if request.client else "unknown"
    req_id = getattr(request.state, "request_id", None)

    try:
        data = export_user_data(user_id)
    except Exception as exc:
        logger.error("[Privacy] export user=%s: %s", user_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao exportar dados.")

    audit.log_privacy_export(user_id=user_id, ip=ip, request_id=req_id)
    return data


@router.delete(
    "/erase/{user_id}",
    summary="LGPD art. 18 VI — Eliminação: apagar os dados do titular",
    description=(
        "Elimina definitivamente os dados pessoais e financeiros do titular "
        "em todas as tabelas do inventário (incluindo a conta). Irreversível. "
        "Requer o token do próprio titular e a frase de confirmação "
        f"'{_CONFIRM_PHRASE}' no corpo. Após a eliminação, o token deixa de "
        "funcionar (o usuário não existe mais)."
    ),
)
def erase_data(
    body: ErasureRequest,
    request: Request,
    user_id: str = Depends(require_owner),
) -> dict:
    from app.privacy.service import erase_user_data

    if body.confirm != _CONFIRM_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Confirmação inválida. Envie confirm='{_CONFIRM_PHRASE}'.",
        )

    ip = request.client.host if request.client else "unknown"
    req_id = getattr(request.state, "request_id", None)

    try:
        result = erase_user_data(user_id)
    except Exception as exc:
        logger.error("[Privacy] erase user=%s: %s", user_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao eliminar dados.")

    audit.log_privacy_deletion(
        user_id=user_id, ip=ip, tables_purged=result.tables_purged, request_id=req_id
    )
    return {
        "user_id": result.user_id,
        "erased_at": result.erased_at,
        "tables_purged": result.tables_purged,
        "rows_deleted": result.rows_deleted,
        "message": (
            "Dados eliminados. Sua conta deixou de existir e este token "
            "não será mais aceito."
        ),
    }
