"""
app/widget/router.py — o widget nativo de tela inicial.

POST   /widget/token/{user_id}   — (sessão do app) emite o token do aparelho
DELETE /widget/token/{user_id}   — (sessão do app) revoga o token do aparelho
GET    /widget/margem            — (token do widget, header X-Widget-Token)
                                   o mesmo payload de /safe-to-spend/{id}/widget

O token do widget NÃO é aceito em nenhuma outra rota: o `require_owner` só
conhece JWT. E o JWT não é aceito aqui — a rota existe para o widget.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.security import require_owner
from app.widget import service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/widget", tags=["Widget nativo"])
limiter = Limiter(key_func=get_remote_address)

# id do aparelho gerado pelo app (UUID). Restrito para não virar campo livre.
_PADRAO_APARELHO = r"^[A-Za-z0-9_-]{8,100}$"


class EmitirIn(BaseModel):
    device_id: str = Field(..., pattern=_PADRAO_APARELHO)


class RevogarIn(BaseModel):
    device_id: str | None = Field(default=None, pattern=_PADRAO_APARELHO)


def dono_do_token_de_widget(x_widget_token: str | None = Header(default=None)) -> str:
    """Autenticação da rota do widget: só o token de escopo restrito."""
    dono = service.validar(x_widget_token)
    if not dono:
        raise HTTPException(status_code=401, detail="Token do widget inválido ou vencido.")
    return dono


@router.post("/token/{user_id}")
@limiter.limit("10/minute")
def emitir_token(request: Request, body: EmitirIn, user_id: str = Depends(require_owner)) -> dict:
    token, expira = service.emitir(user_id, body.device_id)
    logger.info("[Widget] token emitido user=%s", user_id)
    return {"token": token, "expires_at": expira.isoformat()}


@router.delete("/token/{user_id}")
def revogar_token(body: RevogarIn, user_id: str = Depends(require_owner)) -> dict:
    return {"revoked": service.revogar(user_id, body.device_id)}


@router.get("/margem")
@limiter.limit("30/minute")
async def margem_do_dia(request: Request, user_id: str = Depends(dono_do_token_de_widget)) -> dict:
    from app.forecast.router_safe_to_spend import get_safe_to_spend_widget

    return await get_safe_to_spend_widget(user_id=user_id)
