"""
app/privacy/service.py — Export e eliminação de dados do titular (LGPD).

Inventário de dados pessoais/financeiros por tabela, chaveado por user_id.
Ao adicionar uma tabela nova com user_id, INCLUA-A AQUI — este inventário
é o contrato de portabilidade e de eliminação do produto.

Design:
  - Export: SELECT * das tabelas do inventário → dict {tabela: [linhas]}.
  - Eliminação: DELETE por user_id em cada tabela, na ordem do inventário,
    e por fim o próprio registro em users. Cada tabela falha isolada
    (tabela pode não existir em um ambiente) sem abortar o processo — o
    resultado reporta o que foi apagado.
  - Sem soft-delete: eliminação LGPD é eliminação. O que precisa
    sobreviver por obrigação legal (trilha de auditoria) não contém PII
    em claro (emails são mascarados desde a auditoria 2026-07).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Inventário: (tabela, coluna de chave do titular)
# users por último — apagar a conta só depois dos dados dependentes.
_DATA_INVENTORY: list[tuple[str, str]] = [
    ("transactions_clean",        "user_id"),
    ("context_overrides",         "user_id"),
    ("account_balances",          "user_id"),
    ("pluggy_items",              "user_id"),
    ("financial_goals",           "user_id"),
    ("health_score_history",      "user_id"),
    ("user_badges",               "user_id"),
    ("user_challenges",           "user_id"),
    ("user_settings",             "user_id"),
    ("negotiation_history",       "user_id"),
    ("opportunity_snapshots",     "user_id"),
    ("bank_fee_history",          "user_id"),
    ("bank_fee_trends",           "user_id"),
    ("notification_delivery_log", "user_id"),
    ("daily_digest_log",          "user_id"),
    ("push_subscriptions",        "user_id"),
    ("chat_messages",             "user_id"),
    ("architect_simulations",     "user_id"),
    ("architect_simulation_metrics", "user_id"),
    ("optimization_reports",      "user_id"),
    ("recommendation_feedback",   "user_id"),
    ("users",                     "user_id"),
]


@dataclass
class ErasureResult:
    user_id: str
    erased_at: str = ""
    tables_purged: int = 0
    rows_deleted: int = 0
    details: dict[str, int] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)


def export_user_data(user_id: str) -> dict:
    """
    Portabilidade (art. 18 V): todos os dados do titular, por tabela,
    em formato estruturado de uso comum (JSON).
    """
    from app.core.database import SessionLocal
    from sqlalchemy import text

    export: dict = {
        "user_id": user_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "format": "LGPD art.18 V — portabilidade em JSON",
        "data": {},
    }

    with SessionLocal() as db:
        for table, key_col in _DATA_INVENTORY:
            try:
                rows = db.execute(
                    text(f"SELECT * FROM {table} WHERE {key_col} = :uid"),  # noqa: S608 — tabela/coluna vêm do inventário estático
                    {"uid": user_id},
                )
                columns = list(rows.keys())
                records = [
                    {col: _jsonable(val) for col, val in zip(columns, row)}
                    for row in rows.fetchall()
                ]
                if records:
                    if table == "users":
                        # nunca exportar hash de senha
                        for r in records:
                            r.pop("hashed_password", None)
                    export["data"][table] = records
            except Exception as exc:
                logger.debug("[Privacy] export %s indisponível: %s", table, exc)

    return export


def erase_user_data(user_id: str) -> ErasureResult:
    """
    Eliminação (art. 18 VI): apaga os dados do titular tabela a tabela.

    Cada tabela é uma transação isolada — ambiente sem alguma tabela
    (ex: SQLite de teste) não aborta a eliminação das demais.
    """
    from app.core.database import SessionLocal
    from sqlalchemy import text

    result = ErasureResult(user_id=user_id)

    for table, key_col in _DATA_INVENTORY:
        try:
            with SessionLocal() as db:
                res = db.execute(
                    text(f"DELETE FROM {table} WHERE {key_col} = :uid"),  # noqa: S608 — inventário estático
                    {"uid": user_id},
                )
                db.commit()
            deleted = res.rowcount if res.rowcount and res.rowcount > 0 else 0
            result.details[table] = deleted
            result.rows_deleted += deleted
            if deleted:
                result.tables_purged += 1
        except Exception as exc:
            logger.debug("[Privacy] erase %s indisponível: %s", table, exc)
            result.skipped.append(table)

    # Estado derivado fora do banco relacional: dedup de notificações (DuckDB)
    try:
        from app.notifications.state_store import NotificationStateStore

        store = NotificationStateStore()
        con = store._conn()
        con.execute("DELETE FROM notification_state WHERE user_id = ?", [user_id])
        con.execute("DELETE FROM notification_events WHERE user_id = ?", [user_id])
        con.close()
    except Exception as exc:
        logger.debug("[Privacy] erase notification_state indisponível: %s", exc)

    result.erased_at = datetime.now(timezone.utc).isoformat()
    logger.info(
        "[Privacy] Eliminação concluída user=%s: %d linhas em %d tabelas (skipped=%d)",
        user_id, result.rows_deleted, result.tables_purged, len(result.skipped),
    )
    return result


def _jsonable(value):
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (bytes, memoryview)):
        return "<binário omitido>"
    try:
        float(value)  # Decimal → float
        if not isinstance(value, (int, float, str, bool)) and value is not None:
            return float(value)
    except (TypeError, ValueError):
        pass
    return value


__all__ = ["ErasureResult", "erase_user_data", "export_user_data"]
