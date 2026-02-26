# app/db/queries/optimizer_queries.py
# Queries DuckDB para o módulo Nexa Optimizer (Funcionalidade 2)
# Salva e busca relatórios de otimização de cartões.

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import duckdb

logger = logging.getLogger(__name__)

# Usa o mesmo banco que o resto do projeto
_DB_PATH = str(Path(__file__).parent.parent.parent.parent / "data" / "transactions.duckdb")

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS optimization_reports (
    report_id               VARCHAR PRIMARY KEY,
    user_id                 VARCHAR NOT NULL,
    generated_at            VARCHAR NOT NULL,
    recommendation_type     VARCHAR NOT NULL,
    best_card_id            VARCHAR,
    best_card_name          VARCHAR,
    net_gain_expected       DOUBLE,
    net_gain_min            DOUBLE,
    net_gain_max            DOUBLE,
    confidence_score        DOUBLE,
    liquidity_impact        DOUBLE,
    liquidity_risk          VARCHAR,
    data_sources            VARCHAR,
    strategy_text           VARCHAR,
    warnings                VARCHAR,
    full_report_json        VARCHAR
)
"""


def _get_connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(_DB_PATH)


def ensure_table() -> None:
    """Cria tabela optimization_reports se não existir."""
    con = _get_connection()
    try:
        con.execute(_CREATE_TABLE_SQL)
        con.commit()
    finally:
        con.close()


def save_optimization_report(report: dict) -> None:
    """
    Persiste um OptimizationReport (dict) na tabela optimization_reports.
    Faz upsert por report_id.
    """
    con = _get_connection()
    try:
        ensure_table()

        best_card = report.get("best_card") or {}
        con.execute(
            """
            INSERT OR REPLACE INTO optimization_reports (
                report_id, user_id, generated_at, recommendation_type,
                best_card_id, best_card_name,
                net_gain_expected, net_gain_min, net_gain_max,
                confidence_score, liquidity_impact, liquidity_risk,
                data_sources, strategy_text, warnings, full_report_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                report["report_id"],
                report["user_id"],
                str(report["generated_at"]),
                report["recommendation_type"],
                best_card.get("card_id"),
                best_card.get("card_name"),
                best_card.get("net_gain_expected"),
                best_card.get("net_gain_min"),
                best_card.get("net_gain_max"),
                best_card.get("confidence_score"),
                best_card.get("liquidity_impact"),
                best_card.get("liquidity_risk"),
                json.dumps(report.get("data_sources", [])),
                report.get("strategy_text", ""),
                json.dumps(report.get("warnings", [])),
                json.dumps(report, default=str),
            ],
        )
        con.commit()
        logger.info(f"Relatório {report['report_id']} salvo para user {report['user_id']}")
    except Exception as e:
        logger.error(f"Erro ao salvar relatório: {e}")
        raise
    finally:
        con.close()


def get_optimization_reports(user_id: str) -> list[dict]:
    """
    Retorna lista de relatórios resumidos de um usuário.
    Ordenados do mais recente para o mais antigo.
    """
    con = _get_connection()
    try:
        ensure_table()
        rows = con.execute(
            """
            SELECT report_id, user_id, generated_at, recommendation_type,
                   best_card_id, best_card_name,
                   net_gain_expected, net_gain_min, net_gain_max,
                   confidence_score, liquidity_impact, liquidity_risk,
                   data_sources, strategy_text, warnings
            FROM optimization_reports
            WHERE user_id = ?
            ORDER BY generated_at DESC
            """,
            [user_id],
        ).fetchall()

        cols = [
            "report_id", "user_id", "generated_at", "recommendation_type",
            "best_card_id", "best_card_name",
            "net_gain_expected", "net_gain_min", "net_gain_max",
            "confidence_score", "liquidity_impact", "liquidity_risk",
            "data_sources", "strategy_text", "warnings",
        ]
        return [dict(zip(cols, row)) for row in rows]
    except Exception as e:
        logger.error(f"Erro ao buscar relatórios de {user_id}: {e}")
        return []
    finally:
        con.close()


def get_optimization_report_by_id(report_id: str) -> Optional[dict]:
    """
    Retorna o relatório completo (full_report_json) pelo report_id.
    Retorna None se não encontrado.
    """
    con = _get_connection()
    try:
        ensure_table()
        row = con.execute(
            "SELECT full_report_json FROM optimization_reports WHERE report_id = ?",
            [report_id],
        ).fetchone()

        if not row:
            return None

        return json.loads(row[0])
    except Exception as e:
        logger.error(f"Erro ao buscar relatório {report_id}: {e}")
        return None
    finally:
        con.close()
