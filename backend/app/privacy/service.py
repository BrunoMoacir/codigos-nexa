"""
app/privacy/service.py — Export e eliminação de dados do titular (LGPD).

O inventário é DESCOBERTO do banco, não mantido à mão.

Era uma lista escrita por pessoas, com a instrução "ao adicionar uma tabela
nova com user_id, INCLUA-A AQUI". Medido em 2026-08-25, a lista errava nos dois
sentidos ao mesmo tempo:

    fora do inventário, com dado do titular    no inventário, inexistentes
    ────────────────────────────────────────   ─────────────────────────────
    auth_tokens               2851 linhas      daily_digest_log
    rejected_transactions      200 linhas      notification_delivery_log
    shadow_invoices              4 linhas      push_subscriptions
    user_subscriptions           3 linhas      user_settings
    architect_simulation_feedback              bank_fee_trends (sem user_id)
    pluggy_sync_jobs

`rejected_transactions` guarda descrição e valor de transações recusadas pelo
ETL — dado financeiro pessoal sobrevivendo ao art. 18 VI. Um contrato de
eliminação não pode depender de alguém lembrar.

Design:
  - **Descoberta**: toda tabela com coluna `user_id` entra, via
    `sqlalchemy.inspect` (funciona em Postgres e SQLite). O que NÃO deve ser
    apagado fica numa allowlist explícita e curta, com o motivo escrito.
  - **Ordem**: `_ORDEM_PREFERIDA` resolve dependências conhecidas e `users`
    vai por último; o resto vem depois, em ordem alfabética. Violação de FK
    não é falha silenciosa — a tabela volta para uma segunda passada.
  - Export: SELECT * das tabelas descobertas → dict {tabela: [linhas]}.
  - Cada tabela falha isolada (ambiente sem alguma tabela) sem abortar o
    processo — o resultado reporta o que foi apagado e o que ficou.
  - Sem soft-delete: eliminação LGPD é eliminação. O que precisa sobreviver
    por obrigação legal (trilha de auditoria) não contém PII em claro
    (emails são mascarados desde a auditoria 2026-07).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Tabelas que têm `user_id` e NÃO devem ser apagadas. Curta de propósito: cada
# entrada é uma exceção ao contrato de eliminação e precisa de motivo escrito.
_NAO_APAGAR: dict[str, str] = {
    # (vazia hoje — nenhuma tabela com user_id precisa sobreviver à eliminação;
    #  a trilha de auditoria não guarda user_id em claro)
}

# Ordem para as tabelas conhecidas: dependentes antes das referenciadas.
# O que não estiver aqui entra depois, em ordem alfabética, e uma segunda
# passada resolve o que tiver falhado por chave estrangeira.
_ORDEM_PREFERIDA: tuple[str, ...] = (
    "transactions_clean",
    "rejected_transactions",
    "context_overrides",
    "account_balances",
    "shadow_invoices",
    "pluggy_sync_jobs",
    "pluggy_items",
    "financial_goals",
    "health_score_history",
    "user_badges",
    "user_challenges",
    "negotiation_history",
    "opportunity_snapshots",
    "bank_fee_history",
    "chat_messages",
    "architect_simulation_feedback",
    "architect_simulation_metrics",
    "architect_simulations",
    "optimization_reports",
    "recommendation_feedback",
    "auth_tokens",
    "user_subscriptions",
)

_COLUNA_DO_TITULAR = "user_id"


def inventario_de_dados() -> list[tuple[str, str]]:
    """
    `[(tabela, coluna)]` de tudo que guarda dado do titular, descoberto do banco.

    É o contrato de portabilidade E de eliminação. Descobrir em vez de manter à
    mão é o ponto: a lista escrita à mão errava nos dois sentidos (ver o
    docstring do módulo).

    `users` sai por último — apagar a conta só depois dos dados dependentes.
    """
    from sqlalchemy import inspect

    from app.core.database import engine

    try:
        inspetor = inspect(engine)
        tabelas = set(inspetor.get_table_names())
    except Exception as exc:
        logger.error("[Privacy] não foi possível inspecionar o banco: %s", exc)
        return []

    com_titular = set()
    for tabela in tabelas:
        if tabela in _NAO_APAGAR:
            continue
        try:
            colunas = {c["name"] for c in inspetor.get_columns(tabela)}
        except Exception:
            continue
        if _COLUNA_DO_TITULAR in colunas:
            com_titular.add(tabela)

    conhecidas = [t for t in _ORDEM_PREFERIDA if t in com_titular]
    resto = sorted(com_titular - set(conhecidas) - {"users"})
    ordenadas = conhecidas + resto
    if "users" in com_titular:
        ordenadas.append("users")

    return [(t, _COLUNA_DO_TITULAR) for t in ordenadas]


@dataclass
class ErasureResult:
    user_id: str
    erased_at: str = ""
    tables_purged: int = 0
    rows_deleted: int = 0
    details: dict[str, int] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    # Threads do checkpointer do agente esquecidos. `chat_messages` guarda o
    # texto que a UI mostra; o checkpointer guarda a conversa que o LLM relê —
    # perguntas do titular MAIS todo resultado de ferramenta (renda, saldo,
    # tarifas, dívidas). Apagar as 22 tabelas e deixar isso de pé não é
    # eliminação. Ver app/agent/memoria.py.
    agent_threads_cleared: int = 0
    agent_memory_error: str | None = None


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
        for table, key_col in inventario_de_dados():
            try:
                rows = db.execute(
                    text(f"SELECT * FROM {table} WHERE {key_col} = :uid"),  # noqa: S608 — nome vem do inspetor do banco
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

    from app.agent.memoria import esquecer_conversas

    result = ErasureResult(user_id=user_id)

    def _apagar(table: str, key_col: str) -> tuple[bool, Exception | None]:
        try:
            with SessionLocal() as db:
                res = db.execute(
                    text(f"DELETE FROM {table} WHERE {key_col} = :uid"),  # noqa: S608 — nome vem do inspetor do banco
                    {"uid": user_id},
                )
                db.commit()
            deleted = res.rowcount if res.rowcount and res.rowcount > 0 else 0
            result.details[table] = deleted
            result.rows_deleted += deleted
            if deleted:
                result.tables_purged += 1
            return True, None
        except Exception as exc:
            return False, exc

    # Primeira passada, na ordem preferida.
    pendentes: list[tuple[str, str, Exception]] = []
    for table, key_col in inventario_de_dados():
        ok, exc = _apagar(table, key_col)
        if not ok:
            pendentes.append((table, key_col, exc))

    # Segunda passada: o que falhou pode ter falhado por chave estrangeira de
    # uma tabela que só foi apagada depois. Repetir enquanto houver progresso é
    # a diferença entre resolver a ordem e desistir em silêncio.
    while pendentes:
        restantes: list[tuple[str, str, Exception]] = []
        for table, key_col, exc in pendentes:
            ok, novo_exc = _apagar(table, key_col)
            if not ok:
                restantes.append((table, key_col, novo_exc))
        if len(restantes) == len(pendentes):
            break
        pendentes = restantes

    for table, _key, exc in pendentes:
        # Nível ERROR, não debug: aqui sobrou dado do titular. A tabela pode
        # simplesmente não existir neste ambiente — e é por isso que o motivo
        # vai junto, em vez de um "indisponível" genérico.
        logger.error("[Privacy] erase NÃO concluído em %s: %s", table, exc)
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

    # Estado do agente conversacional (checkpointer do LangGraph). Fica fora do
    # Postgres e guarda a cópia mais rica dos dados do titular: as perguntas
    # dele e o retorno de cada ferramenta chamada na conversa.
    memoria = esquecer_conversas(user_id)
    result.agent_threads_cleared = memoria["apagados"]
    result.agent_memory_error = memoria["erro"]
    if memoria["erro"]:
        # Diferente das tabelas ausentes (debug): aqui sobrou dado pessoal.
        logger.error(
            "[Privacy] Memória do agente NÃO eliminada para user=%s: %s",
            user_id, memoria["erro"],
        )

    result.erased_at = datetime.now(timezone.utc).isoformat()
    logger.info(
        "[Privacy] Eliminação concluída user=%s: %d linhas em %d tabelas "
        "(skipped=%d, threads do agente=%d)",
        user_id, result.rows_deleted, result.tables_purged,
        len(result.skipped), result.agent_threads_cleared,
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
