"""
app/core/db/rejections.py — Persistência e leitura da DLQ de ingestão.

Gravação: `save_rejected_transactions()` é chamada no sync de item logo
após a validação do lote. Abre sessão própria e falha silenciosamente,
pelo mesmo motivo de balances.py — registrar rejeição nunca pode derrubar
a ingestão das transações que passaram.

Leitura: `rejection_stats()` responde "este banco está degradando?" na
janela recente. É a consulta que faltava para descobrir um conector
quebrado antes do usuário reclamar de extrato faltando.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Um lote inteiro podre não deve escrever milhares de linhas por sync.
# Acima disso, a amostra + o total já contam a história.
_MAX_POR_LOTE = 200

# Acima deste percentual de rejeição o lote vira alerta operacional.
_LIMIAR_ALERTA = 0.20


@dataclass
class RejectionStats:
    """Resumo de rejeições numa janela de tempo."""

    institution_id: Optional[str]
    total: int
    por_erro: dict[str, int] = field(default_factory=dict)
    por_campo: dict[str, int] = field(default_factory=dict)
    janela_horas: int = 24


def save_rejected_transactions(
    user_id: str,
    item_id: Optional[str],
    institution_id: str,
    batch_result: Any,
) -> int:
    """
    Persiste as rejeições de um TransactionBatchResult. Retorna quantas gravou.

    Recebe o batch inteiro (e não a lista) para poder guardar o batch_id —
    é ele que amarra as rejeições ao lote que as produziu quando for
    investigar.
    """
    rejeitadas = getattr(batch_result, "rejected_transactions", None) or []
    if not rejeitadas:
        return 0

    gravadas = 0
    try:
        from app.core.database import SessionLocal
        from app.core.models.rejected_transaction import RejectedTransactionRecord

        batch_id = getattr(batch_result, "batch_id", None)
        agora = datetime.now(timezone.utc)

        with SessionLocal() as db:
            for rejeitada in rejeitadas[:_MAX_POR_LOTE]:
                db.add(
                    RejectedTransactionRecord(
                        id=str(uuid.uuid4()),
                        user_id=str(user_id) if user_id else None,
                        item_id=item_id,
                        institution_id=institution_id,
                        transaction_id=getattr(rejeitada, "transaction_id", None),
                        account_id=getattr(rejeitada, "account_id", None),
                        error_type=getattr(rejeitada, "error_type", "Unknown")[:100],
                        error_message=str(getattr(rejeitada, "error_message", ""))[:2000],
                        field_errors=_to_json(getattr(rejeitada, "field_errors", None)),
                        raw_data=_to_json(getattr(rejeitada, "raw_data", None)) or "{}",
                        raw_data_truncated=bool(
                            getattr(rejeitada, "raw_data_truncated", False)
                        ),
                        batch_id=batch_id,
                        rejected_at=getattr(rejeitada, "rejected_at", None) or agora,
                    )
                )
                gravadas += 1
            db.commit()
    except Exception as exc:
        logger.warning(
            "[DLQ] Falha ao gravar rejeições user=%s item=%s banco=%s: %s",
            user_id, item_id, institution_id, exc,
        )
        return 0

    descartadas = len(rejeitadas) - gravadas
    if descartadas > 0:
        logger.warning(
            "[DLQ] %s rejeições gravadas (%s descartadas pelo limite de %s por lote)",
            gravadas, descartadas, _MAX_POR_LOTE,
        )

    return gravadas


def alert_on_batch(batch_result: Any, institution_id: str, user_id: str) -> Optional[str]:
    """
    Emite o alerta operacional do lote (o `alert_message` que só existia em
    memória e nunca era logado por ninguém).

    Retorna a mensagem quando alertou, None quando o lote está saudável.
    """
    total = getattr(batch_result, "total_received", 0) or 0
    if total == 0:
        return None

    taxa = getattr(batch_result, "rejection_rate", 0.0) or 0.0
    if taxa < _LIMIAR_ALERTA:
        return None

    mensagem = getattr(batch_result, "alert_message", None) or (
        f"Rejeição de {taxa:.1%} em {institution_id}"
    )
    nivel = logging.CRITICAL if taxa >= 1.0 else logging.WARNING

    logger.log(
        nivel,
        "[DLQ] %s | user=%s banco=%s erros=%s",
        mensagem,
        user_id,
        institution_id,
        getattr(batch_result, "field_error_summary", {}),
    )
    return mensagem


def rejection_stats(
    institution_id: Optional[str] = None,
    user_id: Optional[str] = None,
    hours: int = 24,
) -> RejectionStats:
    """
    Rejeições na janela recente, agrupadas por tipo de erro e por campo.

    É a resposta para "o conector do banco X quebrou?": campo sempre igual
    no topo (ex.: transaction_date) significa mudança de contrato do banco,
    não usuário com dado estranho.
    """
    stats = RejectionStats(institution_id=institution_id, total=0, janela_horas=hours)

    try:
        from app.core.database import SessionLocal
        from app.core.models.rejected_transaction import RejectedTransactionRecord

        desde = datetime.now(timezone.utc) - timedelta(hours=hours)

        with SessionLocal() as db:
            consulta = db.query(RejectedTransactionRecord).filter(
                RejectedTransactionRecord.rejected_at >= desde
            )
            if institution_id:
                consulta = consulta.filter(
                    RejectedTransactionRecord.institution_id == institution_id
                )
            if user_id:
                consulta = consulta.filter(RejectedTransactionRecord.user_id == str(user_id))

            for linha in consulta.all():
                stats.total += 1
                erro = linha.error_type or "Unknown"
                stats.por_erro[erro] = stats.por_erro.get(erro, 0) + 1

                for campo in (json.loads(linha.field_errors or "{}") or {}):
                    stats.por_campo[campo] = stats.por_campo.get(campo, 0) + 1
    except Exception as exc:
        logger.warning("[DLQ] Falha ao consultar rejeições: %s", exc)

    stats.por_erro = dict(sorted(stats.por_erro.items(), key=lambda x: x[1], reverse=True))
    stats.por_campo = dict(sorted(stats.por_campo.items(), key=lambda x: x[1], reverse=True))
    return stats


def _to_json(valor: Any) -> Optional[str]:
    if valor is None:
        return None
    try:
        return json.dumps(valor, default=str, ensure_ascii=False)
    except Exception:
        return json.dumps({"_serialization_error": repr(valor)[:200]})
