"""
app/core/webhook_security.py — Autenticação de webhooks de entrada.

Problema que resolve (auditoria 2026-07): POST /transactions/webhook era
uma porta de escrita sem autenticação — qualquer origem podia injetar
transações falsas na conta de QUALQUER usuário (o user_id vinha da query
string). Num produto cuja tese é confiança, integridade do dado de
entrada é o produto.

Modelo de segurança:
  1. Segredo compartilhado (PLUGGY_WEBHOOK_SECRET) conferido em tempo
     constante contra o header X-Webhook-Token (ou ?token= na URL, pois
     o painel da Pluggy permite configurar a URL do webhook com query).
  2. Identidade NUNCA vem do chamador: item_id do payload é resolvido
     para user_id via tabela pluggy_items (gravada quando o usuário
     conectou o banco). Item desconhecido → 404, nada é escrito.

Postura por ambiente:
  - Produção SEM segredo configurado → 503 (fail-closed: preferimos o
    webhook fora do ar a aceitar escrita anônima).
  - Desenvolvimento sem segredo → permitido (fluxo local com mocks),
    com warning no log.
"""

from __future__ import annotations

import hmac
import logging
import os

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)

_TOKEN_HEADER = "x-webhook-token"
_TOKEN_QUERY = "token"


def _is_prod() -> bool:
    return os.getenv("APP_MODE", "dev") == "prod"


def verify_webhook_token(request: Request) -> None:
    """
    Valida o segredo do webhook. Levanta HTTPException quando inválido.

    Ordem de busca do token do chamador: header X-Webhook-Token, depois
    query ?token= (a comparação é sempre em tempo constante).
    """
    from app.core.config import settings

    secret = (settings.PLUGGY_WEBHOOK_SECRET or "").strip()

    if not secret:
        if _is_prod():
            logger.error(
                "[WebhookSecurity] PLUGGY_WEBHOOK_SECRET ausente em produção — "
                "webhook recusado (fail-closed)."
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Webhook não configurado no servidor.",
            )
        logger.warning(
            "[WebhookSecurity] Sem PLUGGY_WEBHOOK_SECRET — aceitando webhook "
            "SEM autenticação (permitido apenas em desenvolvimento)."
        )
        return

    provided = request.headers.get(_TOKEN_HEADER) or request.query_params.get(_TOKEN_QUERY) or ""
    if not hmac.compare_digest(provided.encode(), secret.encode()):
        logger.warning(
            "[WebhookSecurity] Token de webhook inválido (ip=%s)",
            request.client.host if request.client else "?",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de webhook inválido.",
        )


def resolve_user_from_item(item_id: str) -> str | None:
    """
    Mapeia item_id (Pluggy) → user_id via pluggy_items.

    A identidade do dono dos dados vem EXCLUSIVAMENTE deste mapeamento,
    gravado quando o usuário autenticado conectou a conta — nunca do
    payload ou da query do webhook.
    """
    if not item_id or item_id == "unknown":
        return None
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            row = db.execute(
                text("SELECT user_id FROM pluggy_items WHERE item_id = :iid LIMIT 1"),
                {"iid": item_id},
            ).fetchone()
        return row[0] if row else None
    except Exception as exc:
        logger.warning("[WebhookSecurity] resolve_user_from_item(%s): %s", item_id, exc)
        return None


__all__ = ["resolve_user_from_item", "verify_webhook_token"]
