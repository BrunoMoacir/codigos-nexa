"""
app/core/db/shadow_invoices.py — Persistência das obrigações futuras.

O Step 5 do ETL detecta assinatura/parcelamento a cada sync e, até aqui,
descartava o resultado. Aqui ele vira linha em `shadow_invoices`, com
upsert por (user_id, merchant_key, type): o detector reprocessa a mesma
série todo sync, então empilhar duplicata seria o comportamento errado.

Segue a convenção de balances/rejections: sessão própria e falha
silenciosa — persistir previsão nunca pode derrubar a ingestão do extrato.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


def save_shadow_invoices(
    user_id: str,
    shadow_df: Any,
    account_id: Optional[str] = None,
) -> int:
    """
    Persiste as shadow invoices de um usuário. Retorna quantas gravou.

    `shadow_df` é o Polars DataFrame do run_shadow_invoice_detection:
    colunas type, amount, next_due_date, metadata (struct com description e
    occurrences), confidence.
    """
    if shadow_df is None or getattr(shadow_df, "is_empty", lambda: True)():
        return 0

    from app.forecast.etl.text_normalizer import canonical_key

    gravadas = 0
    try:
        from app.core.database import SessionLocal
        from app.core.models.shadow_invoice import ShadowInvoice

        agora = datetime.now(timezone.utc)
        vistos: set[tuple[str, str]] = set()

        with SessionLocal() as db:
            for linha in shadow_df.iter_rows(named=True):
                metadata = linha.get("metadata") or {}
                if not isinstance(metadata, dict):
                    metadata = {}

                descricao = metadata.get("description") or ""
                tipo = str(linha.get("type") or "UNKNOWN")
                # A chave canônica é o identificador estável da série; a
                # descrição do detector já vem normalizada, mas de bancos que
                # carimbam competência ela ainda varia.
                chave = canonical_key(descricao) or descricao
                if not chave:
                    continue

                # Dentro do mesmo lote, o detector pode repetir a série.
                if (chave, tipo) in vistos:
                    continue
                vistos.add((chave, tipo))

                existente = (
                    db.query(ShadowInvoice)
                    .filter(
                        ShadowInvoice.user_id == str(user_id),
                        ShadowInvoice.merchant_key == chave,
                        ShadowInvoice.type == tipo,
                    )
                    .first()
                )

                valores = dict(
                    amount=float(linha.get("amount") or 0.0),
                    next_due_date=linha.get("next_due_date"),
                    occurrences=float(metadata.get("occurrences") or 0) or None,
                    confidence=float(linha.get("confidence") or 0.0),
                    description=descricao[:255] or None,
                    detector_metadata=json.dumps(metadata, default=str, ensure_ascii=False),
                    account_id=account_id,
                    active=True,
                    updated_at=agora,
                )

                if existente is not None:
                    for campo, valor in valores.items():
                        setattr(existente, campo, valor)
                else:
                    db.add(
                        ShadowInvoice(
                            id=str(uuid.uuid4()),
                            user_id=str(user_id),
                            merchant_key=chave,
                            type=tipo,
                            detected_at=agora,
                            **valores,
                        )
                    )
                gravadas += 1

            db.commit()
    except Exception as exc:
        logger.warning("[ShadowInvoice] Falha ao gravar user=%s: %s", user_id, exc)
        return 0

    logger.info("[ShadowInvoice] %s obrigações futuras salvas para user %s", gravadas, user_id)
    return gravadas


def get_shadow_invoices(user_id: str, only_active: bool = True) -> list[dict]:
    """Obrigações futuras do usuário, mais confiáveis primeiro."""
    try:
        from app.core.database import SessionLocal
        from app.core.models.shadow_invoice import ShadowInvoice

        with SessionLocal() as db:
            consulta = db.query(ShadowInvoice).filter(ShadowInvoice.user_id == str(user_id))
            if only_active:
                consulta = consulta.filter(ShadowInvoice.active.is_(True))

            return [
                {
                    "id": linha.id,
                    "type": linha.type,
                    "merchant_key": linha.merchant_key,
                    "description": linha.description,
                    "amount": linha.amount,
                    "next_due_date": linha.next_due_date.isoformat() if linha.next_due_date else None,
                    "occurrences": linha.occurrences,
                    "confidence": linha.confidence,
                }
                for linha in consulta.order_by(ShadowInvoice.confidence.desc()).all()
            ]
    except Exception as exc:
        logger.warning("[ShadowInvoice] Falha ao consultar user=%s: %s", user_id, exc)
        return []
