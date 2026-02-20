"""
app/db/queries/architect_queries.py - Persistência das Simulações F3

Feature: F3 - Nexa Architect
Version: 1.0.0
Data:    2026-02-20

Responsabilidade:
    Todas as operações de banco de dados relacionadas às simulações do
    Nexa Architect (F3). Segue o mesmo padrão do restante do projeto:
      - Banco: DuckDB (finance.duckdb)
      - Sem ORM: SQL direto com placeholders posicionais (?)
      - try/finally para garantir fechamento de conexão
      - Fallback gracioso: funções retornam None/[] em vez de lançar exceção

Padrão de uso:
    Estas funções são chamadas pelo ArchitectService após cada simulação
    bem-sucedida. Elas NÃO fazem parte do caminho crítico da simulação —
    uma falha aqui não deve impedir que o usuário receba a resposta.

Usage:
    from app.db.queries.architect_queries import (
        save_simulation,
        get_simulation,
        get_user_simulations,
    )

    sim_id = save_simulation(user_id="user_123", request=req, response=resp)
    simulation = get_simulation(sim_id)
    history = get_user_simulations("user_123", limit=5)
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import duckdb

# ─── Configuração ─────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

# Caminho padrão do banco de dados compartilhado com o restante do projeto
DB_PATH = "finance.duckdb"


# ─── Helpers Internos ─────────────────────────────────────────────────────────

def _get_connection(db_path: str = DB_PATH) -> duckdb.DuckDBPyConnection:
    """
    Abre e retorna uma conexão com o DuckDB.

    Centralizado aqui para facilitar injeção em testes
    (os testes passam ':memory:' via parâmetro db_path).

    Args:
        db_path: Caminho do arquivo .duckdb ou ':memory:' para testes.

    Returns:
        Conexão DuckDB aberta.
    """
    return duckdb.connect(db_path)


def _ensure_tables_exist(con: duckdb.DuckDBPyConnection) -> bool:
    """
    Verifica se as tabelas do Architect existem no banco.

    Usado como guard antes de qualquer operação. Se as tabelas não existirem
    (migration não executada), a função loga um aviso e retorna False,
    permitindo que a chamada ignore o erro graciosamente.

    Args:
        con: Conexão DuckDB já aberta.

    Returns:
        True se ambas as tabelas existem, False caso contrário.
    """
    try:
        # SHOW TABLES retorna lista de tuplas: [(nome_tabela,), ...]
        existing = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        required = {"architect_simulations", "architect_simulation_metrics"}
        missing = required - existing

        if missing:
            logger.warning(
                "Tabelas do Architect não encontradas: %s. "
                "Execute a migration 003_create_architect_tables.sql.",
                missing,
            )
            return False

        return True

    except Exception as exc:
        # Banco pode estar corrompido ou em estado inconsistente
        logger.error("Erro ao verificar tabelas do Architect: %s", exc)
        return False


# ─── Funções Públicas ─────────────────────────────────────────────────────────

def save_simulation(
    user_id: str,
    request: Any,
    response: Any,
    db_path: str = DB_PATH,
) -> Optional[str]:
    """
    Persiste uma simulação completa no banco de dados.

    Salva tanto os campos indexáveis (para queries rápidas) quanto o
    JSON completo do request e response (para auditoria e replay).
    Após salvar, atualiza automaticamente as métricas do usuário.

    Args:
        user_id:  ID do usuário que solicitou a simulação.
        request:  SimulationRequest (objeto Pydantic) da simulação.
        response: SimulationResponse (objeto Pydantic) retornado pelo engine.
        db_path:  Caminho do banco (`:memory:` em testes).

    Returns:
        UUID da simulação salva (str), ou None em caso de erro.

    Example:
        >>> sim_id = save_simulation("user_123", req, resp)
        >>> print(sim_id)  # "550e8400-e29b-41d4-a716-446655440000"
    """
    # Gerar UUID único para esta simulação
    simulation_id = str(uuid.uuid4())

    con = _get_connection(db_path)
    try:
        if not _ensure_tables_exist(con):
            return None

        # Serializar request e response para JSON
        # .model_dump() é o método Pydantic v2 (substitui .dict())
        # Usamos mode="json" para garantir que tipos como date e Enum
        # sejam convertidos para string automaticamente
        request_json = json.dumps(
            request.model_dump(mode="json"),
            ensure_ascii=False,  # preservar acentos em pt-BR
        )
        response_json = json.dumps(
            response.model_dump(mode="json"),
            ensure_ascii=False,
        )

        # ── INSERT principal ─────────────────────────────────────────────────
        # Campos indexáveis extraídos diretamente dos objetos Pydantic
        con.execute(
            """
            INSERT INTO architect_simulations (
                id,
                user_id,
                created_at,
                target_amount,
                asset_type,
                amortization_type,
                financing_months,
                down_payment,
                max_monthly_budget,
                recommended_strategy,
                confidence_score,
                liquidity_impact,
                months_to_achieve,
                expected_cost,
                request_json,
                response_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                simulation_id,
                user_id,
                datetime.now(tz=timezone.utc),          # timestamp UTC
                request.target_amount,
                request.asset_type.value,               # Enum → string
                request.amortization_type.value,        # Enum → string
                request.financing_months,
                request.down_payment,
                request.max_monthly_budget,
                response.recommended_strategy.value,    # Enum → string
                response.confidence_score,
                response.liquidity_impact,
                response.months_to_achieve,
                response.costs.expected_cost,           # nested object
                request_json,
                response_json,
            ],
        )

        logger.info(
            "save_simulation | id=%s user=%s strategy=%s confidence=%.2f",
            simulation_id,
            user_id,
            response.recommended_strategy.value,
            response.confidence_score,
        )

        # ── Atualizar métricas do usuário ────────────────────────────────────
        # Feito na mesma conexão para garantir consistência
        _update_simulation_metrics_internal(con, user_id)

        return simulation_id

    except Exception as exc:
        # Falha de persistência NÃO deve interromper a resposta ao usuário
        logger.error(
            "save_simulation | ERRO user=%s: %s",
            user_id,
            exc,
            exc_info=True,
        )
        return None

    finally:
        # Garantia: conexão sempre fechada mesmo em caso de exceção
        con.close()


def get_simulation(
    simulation_id: str,
    db_path: str = DB_PATH,
) -> Optional[Dict[str, Any]]:
    """
    Recupera uma simulação pelo seu ID único.

    Retorna o dict completo com os campos indexáveis mais os JSONs
    de request e response desserializados.

    Args:
        simulation_id: UUID da simulação (retornado por save_simulation).
        db_path:       Caminho do banco.

    Returns:
        Dict com os dados da simulação, ou None se não encontrada.

    Example:
        >>> sim = get_simulation("550e8400-...")
        >>> print(sim["recommended_strategy"])  # "FINANCING"
        >>> print(sim["response"]["confidence_score"])  # 0.85
    """
    con = _get_connection(db_path)
    try:
        if not _ensure_tables_exist(con):
            return None

        row = con.execute(
            """
            SELECT
                id,
                user_id,
                created_at,
                target_amount,
                asset_type,
                amortization_type,
                financing_months,
                down_payment,
                max_monthly_budget,
                recommended_strategy,
                confidence_score,
                liquidity_impact,
                months_to_achieve,
                expected_cost,
                request_json,
                response_json
            FROM architect_simulations
            WHERE id = ?
            """,
            [simulation_id],
        ).fetchone()

        if row is None:
            return None

        # Montar dict com nomes legíveis e JSONs desserializados
        return {
            "id":                   row[0],
            "user_id":              row[1],
            "created_at":           row[2],
            "target_amount":        row[3],
            "asset_type":           row[4],
            "amortization_type":    row[5],
            "financing_months":     row[6],
            "down_payment":         row[7],
            "max_monthly_budget":   row[8],
            "recommended_strategy": row[9],
            "confidence_score":     row[10],
            "liquidity_impact":     row[11],
            "months_to_achieve":    row[12],
            "expected_cost":        row[13],
            # JSON desserializado para facilitar o uso pelo caller
            "request":              json.loads(row[14]) if row[14] else {},
            "response":             json.loads(row[15]) if row[15] else {},
        }

    except Exception as exc:
        logger.error("get_simulation | id=%s | ERRO: %s", simulation_id, exc)
        return None

    finally:
        con.close()


def get_user_simulations(
    user_id: str,
    limit: int = 10,
    asset_type: Optional[str] = None,
    db_path: str = DB_PATH,
) -> List[Dict[str, Any]]:
    """
    Lista as últimas simulações de um usuário, ordenadas da mais recente.

    Suporta filtro opcional por tipo de bem.
    Útil para o endpoint GET /api/v1/architect/simulations.

    Args:
        user_id:    ID do usuário.
        limit:      Máximo de registros a retornar (default: 10).
        asset_type: Filtro opcional: "IMOVEL", "VEICULO", etc.
        db_path:    Caminho do banco.

    Returns:
        Lista de dicts com campos resumidos (sem os JSONs completos).
        Lista vazia se não houver simulações ou em caso de erro.

    Example:
        >>> sims = get_user_simulations("user_123", limit=5)
        >>> for s in sims:
        ...     print(s["recommended_strategy"], s["created_at"])
    """
    con = _get_connection(db_path)
    try:
        if not _ensure_tables_exist(con):
            return []

        # Query base — colunas resumidas sem os JSONs pesados
        query = """
            SELECT
                id,
                created_at,
                target_amount,
                asset_type,
                recommended_strategy,
                confidence_score,
                liquidity_impact,
                months_to_achieve,
                expected_cost
            FROM architect_simulations
            WHERE user_id = ?
        """
        params: List[Any] = [user_id]

        # Filtro opcional por tipo de bem (ex: listar só simulações de imóvel)
        if asset_type:
            query += " AND asset_type = ?"
            params.append(asset_type.upper())

        # Ordenação e limite
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = con.execute(query, params).fetchall()

        # Converter tuplas em dicts com nomes legíveis
        return [
            {
                "id":                   row[0],
                "created_at":           row[1],
                "target_amount":        row[2],
                "asset_type":           row[3],
                "recommended_strategy": row[4],
                "confidence_score":     row[5],
                "liquidity_impact":     row[6],
                "months_to_achieve":    row[7],
                "expected_cost":        row[8],
            }
            for row in rows
        ]

    except Exception as exc:
        logger.error(
            "get_user_simulations | user=%s | ERRO: %s", user_id, exc
        )
        return []

    finally:
        con.close()


def get_user_latest_simulation(
    user_id: str,
    db_path: str = DB_PATH,
) -> Optional[Dict[str, Any]]:
    """
    Retorna a simulação mais recente de um usuário (com JSON completo).

    Útil para pre-preencher o formulário com os últimos parâmetros
    ou exibir o último resultado sem o usuário precisar refazer.

    Args:
        user_id: ID do usuário.
        db_path: Caminho do banco.

    Returns:
        Dict completo da última simulação, ou None se não houver nenhuma.
    """
    con = _get_connection(db_path)
    try:
        if not _ensure_tables_exist(con):
            return None

        row = con.execute(
            """
            SELECT id
            FROM architect_simulations
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            [user_id],
        ).fetchone()

        if row is None:
            return None

        # Reusar get_simulation para não duplicar lógica de montagem do dict
        # Fechamos esta conexão antes para evitar lock simultâneo no arquivo
        simulation_id = row[0]
        return get_simulation(simulation_id, db_path=db_path)

    except Exception as exc:
        logger.error(
            "get_user_latest_simulation | user=%s | ERRO: %s", user_id, exc
        )
        return None

    finally:
        con.close()


def update_simulation_metrics(
    user_id: str,
    db_path: str = DB_PATH,
) -> bool:
    """
    Recalcula e persiste as métricas agregadas do usuário.

    Versão pública — abre sua própria conexão.
    Pode ser chamada manualmente para forçar recálculo.
    Normalmente é chamada automaticamente por save_simulation.

    Args:
        user_id: ID do usuário.
        db_path: Caminho do banco.

    Returns:
        True se bem-sucedido, False em caso de erro.
    """
    con = _get_connection(db_path)
    try:
        if not _ensure_tables_exist(con):
            return False

        result = _update_simulation_metrics_internal(con, user_id)
        return result

    except Exception as exc:
        logger.error(
            "update_simulation_metrics | user=%s | ERRO: %s", user_id, exc
        )
        return False

    finally:
        con.close()


def get_user_metrics(
    user_id: str,
    db_path: str = DB_PATH,
) -> Optional[Dict[str, Any]]:
    """
    Retorna as métricas agregadas de um usuário.

    Estas métricas são mantidas atualizadas automaticamente pelo
    save_simulation. Consulta O(1) — não precisa de GROUP BY.

    Args:
        user_id: ID do usuário.
        db_path: Caminho do banco.

    Returns:
        Dict com total_simulations, last_simulated_at, favorite_strategy
        e avg_confidence_score. None se o usuário não tiver simulações.

    Example:
        >>> m = get_user_metrics("user_123")
        >>> print(f"Total: {m['total_simulations']}")
        >>> print(f"Favorita: {m['favorite_strategy']}")
    """
    con = _get_connection(db_path)
    try:
        if not _ensure_tables_exist(con):
            return None

        row = con.execute(
            """
            SELECT
                user_id,
                total_simulations,
                last_simulated_at,
                favorite_strategy,
                avg_confidence_score,
                first_simulated_at
            FROM architect_simulation_metrics
            WHERE user_id = ?
            """,
            [user_id],
        ).fetchone()

        if row is None:
            return None

        return {
            "user_id":              row[0],
            "total_simulations":    row[1],
            "last_simulated_at":    row[2],
            "favorite_strategy":    row[3],
            "avg_confidence_score": row[4],
            "first_simulated_at":   row[5],
        }

    except Exception as exc:
        logger.error(
            "get_user_metrics | user=%s | ERRO: %s", user_id, exc
        )
        return None

    finally:
        con.close()


# ─── Helper de Métricas (Interno) ────────────────────────────────────────────

def _update_simulation_metrics_internal(
    con: duckdb.DuckDBPyConnection,
    user_id: str,
) -> bool:
    """
    Recalcula e faz UPSERT nas métricas do usuário.

    Versão interna — recebe uma conexão já aberta para ser chamada
    dentro da mesma transação que o INSERT da simulação (save_simulation).

    Calcula via SQL diretamente para eficiência:
      - total_simulations: COUNT(*)
      - last_simulated_at: MAX(created_at)
      - first_simulated_at: MIN(created_at)
      - favorite_strategy: moda (valor mais frequente)
      - avg_confidence_score: AVG(confidence_score)

    Args:
        con:     Conexão DuckDB aberta.
        user_id: ID do usuário.

    Returns:
        True se bem-sucedido.
    """
    # ── Calcular métricas via SQL ────────────────────────────────────────────
    # Subconsulta para obter o mode (valor mais frequente) de recommended_strategy,
    # pois DuckDB não tem função MODE() direta — usamos ORDER BY + LIMIT 1
    metrics_row = con.execute(
        """
        SELECT
            COUNT(*)                        AS total_simulations,
            MAX(created_at)                 AS last_simulated_at,
            MIN(created_at)                 AS first_simulated_at,
            AVG(confidence_score)           AS avg_confidence_score
        FROM architect_simulations
        WHERE user_id = ?
        """,
        [user_id],
    ).fetchone()

    if metrics_row is None or metrics_row[0] == 0:
        # Usuário não tem simulações (não deveria acontecer pois esta função
        # é chamada após um INSERT, mas defensivo)
        return False

    total_sim         = metrics_row[0]
    last_sim_at       = metrics_row[1]
    first_sim_at      = metrics_row[2]
    avg_confidence    = metrics_row[3]

    # Estratégia favorita: a mais frequente nas simulações do usuário
    fav_row = con.execute(
        """
        SELECT recommended_strategy
        FROM architect_simulations
        WHERE user_id = ?
        GROUP BY recommended_strategy
        ORDER BY COUNT(*) DESC
        LIMIT 1
        """,
        [user_id],
    ).fetchone()
    favorite_strategy = fav_row[0] if fav_row else None

    # ── UPSERT nas métricas ──────────────────────────────────────────────────
    # DuckDB suporta INSERT OR REPLACE (similar ao SQLite).
    # Se o user_id já existe na tabela, substitui o registro inteiro.
    con.execute(
        """
        INSERT OR REPLACE INTO architect_simulation_metrics (
            user_id,
            total_simulations,
            last_simulated_at,
            first_simulated_at,
            favorite_strategy,
            avg_confidence_score
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            user_id,
            total_sim,
            last_sim_at,
            first_sim_at,
            favorite_strategy,
            round(avg_confidence, 4) if avg_confidence else None,
        ],
    )

    logger.debug(
        "_update_metrics | user=%s total=%d favorite=%s",
        user_id,
        total_sim,
        favorite_strategy,
    )
    return True


# ─── Exports ──────────────────────────────────────────────────────────────────

__all__ = [
    "save_simulation",
    "get_simulation",
    "get_user_simulations",
    "get_user_latest_simulation",
    "update_simulation_metrics",
    "get_user_metrics",
]
