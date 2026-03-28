import logging
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import func

from app.divider.models import ContextOverride
from app.core.models.transaction import Transaction
from app.health_score.models import HealthScoreHistory

logger = logging.getLogger(__name__)

def get_connection():
    """Conexão DuckDB (fallback para dev).

    Prioriza DUCKDB_PATH; caso não exista, usa backend/finance.duckdb.
    """
    import duckdb
    import os
    from pathlib import Path

    env_path = os.getenv("DUCKDB_PATH")
    if env_path and Path(env_path).exists():
        return duckdb.connect(env_path)

    # Tenta múltiplos caminhos (relativo ao CWD ou absoluto)
    candidates = [
        Path("backend/finance.duckdb"),  # relativo
        Path("finance.duckdb"),  # raiz
        Path("backend/data/finance.duckdb"),  # alternativo
    ]

    for cand in candidates:
        if cand.exists():
            return duckdb.connect(str(cand.absolute()))

    # Fallback: tenta a partir do arquivo deste módulo
    module_dir = Path(__file__).resolve().parent
    repo_root = module_dir.parents[3]
    for subpath in ["backend/finance.duckdb", "finance.duckdb", "backend/data/finance.duckdb"]:
        full_path = repo_root / subpath
        if full_path.exists():
            return duckdb.connect(str(full_path))

    raise FileNotFoundError("finance.duckdb not found in expected locations")


def _get_transactions_for_user_duckdb(user_id: str):
    import polars as pl

    try:
        con = get_connection()
        try:
            df = con.execute(
                """
                SELECT
                  transaction_id,
                  date,
                  amount,
                  description,
                  category,
                  is_recurring,
                  is_installment,
                  context_type,
                  context_confidence,
                  context_override_by_user,
                  pj_subcategory,
                  transaction_type
                FROM transactions_clean
                WHERE user_id = ?
                ORDER BY date
                """,
                [user_id],
            ).pl()
        finally:
            con.close()

        if df is None or df.is_empty():
            return pl.DataFrame()

        if "date" in df.columns:
            df = df.with_columns(pl.col("date").cast(pl.Date))
        return df
    except Exception as exc:
        logger.info("DuckDB fallback sem dados/erro user=%s: %s", user_id, exc)
        return pl.DataFrame()


def get_transactions_for_user(user_id: str, db: Optional[Session] = None):
    """Busca transações do usuário.

    Ordem:
      1) Postgres (SQLAlchemy) — usa `db` se fornecido, senão abre sessão própria
      2) DuckDB (backend/finance.duckdb)

    Retorna polars.DataFrame.
    """
    import polars as pl
    from app.core.models.transaction import Transaction

    _own_session = db is None
    if _own_session:
        from app.core.database import SessionLocal
        db = SessionLocal()

    try:
        transactions = (
            db.query(Transaction)
            .filter(Transaction.user_id == user_id)
            .order_by(Transaction.date)
            .all()
        )
        if not transactions:
            return _get_transactions_for_user_duckdb(user_id)

        data = [
            {
                "transaction_id": t.transaction_id,
                "date": t.date,
                "amount": float(t.amount) if t.amount else 0.0,
                "description": t.description if t.description else "Sem descrição",
                "category": t.category if t.category else "outros",
                "transaction_type": getattr(t, "transaction_type", None),
                "is_recurring": t.is_recurring,
                "is_installment": t.is_installment,
                "context_type": t.context_type,
                "context_confidence": t.context_confidence,
                "context_override_by_user": t.context_override_by_user,
                "pj_subcategory": t.pj_subcategory,
            }
            for t in transactions
        ]
        return pl.DataFrame(data)
    except Exception as exc:
        logger.warning("Postgres indisponível, caindo para DuckDB | user=%s erro=%s", user_id, exc)
        return _get_transactions_for_user_duckdb(user_id)
    finally:
        if _own_session:
            db.close()

def get_context_overrides(db: Session, user_id: str) -> List[Dict[str, Any]]:
    try:
        overrides = db.query(ContextOverride).filter(ContextOverride.user_id == user_id).order_by(ContextOverride.created_at.desc()).all()
        return [
            {
                "transaction_id": o.transaction_id,
                "original_context": o.original_context,
                "corrected_context": o.corrected_context,
                "reason": o.reason,
                "created_at": o.created_at
            }
            for o in overrides
        ]
    except Exception as e:
        logger.error("Erro ao buscar overrides para user=%s: %s", user_id, e, exc_info=True)
        raise

def save_context_override(
    db: Session,
    user_id: str,
    transaction_id: str,
    corrected_context: str,
    original_context: Optional[str] = None,
    reason: Optional[str] = None
) -> bool:
    try:
        # DELETA o antigo e INSERE o novo, igual o DuckDB fazia internamente
        db.query(ContextOverride).filter(
            ContextOverride.transaction_id == transaction_id, 
            ContextOverride.user_id == user_id
        ).delete()
        
        new_override = ContextOverride(
            id=str(uuid.uuid4()),
            transaction_id=transaction_id,
            user_id=user_id,
            original_context=original_context,
            corrected_context=corrected_context,
            reason=reason
        )
        db.add(new_override)

        # Refletir o override na tabela transactions_clean
        db.query(Transaction).filter(Transaction.transaction_id == transaction_id).update({
            "context_type": corrected_context,
            "context_override_by_user": True,
            "context_confidence": 1.0
        })
        
        db.commit()
        logger.info("Override salvo para txn %s: %s", transaction_id, corrected_context)
        return True
    except Exception as e:
        logger.error("Erro ao salvar override: %s", e)
        db.rollback()
        return False

def save_transactions_clean(
    db: Session,
    df,
    user_id: str,
    account_id: Optional[str] = None,
) -> int:
    import polars as pl
    try:
        if "user_id" not in df.columns:
            df = df.with_columns(pl.lit(user_id).alias("user_id"))
        if "account_id" not in df.columns:
            df = df.with_columns(pl.lit(account_id).alias("account_id"))
            
        rename_map = {
            "predicted_category": "category",
            "pf_pj_label": "context_type",
            "pf_pj_confidence": "context_confidence",
            "transaction_date": "date",
        }
        for old_name, new_name in rename_map.items():
            if old_name in df.columns and new_name not in df.columns:
                df = df.rename({old_name: new_name})
                
        schema_cols = [
            "transaction_id", "user_id", "account_id", "description",
            "amount", "date", "transaction_type", "category",
            "is_recurring", "is_installment", "context_type",
            "context_confidence", "context_override_by_user", "pj_subcategory",
        ]
        cols_to_save = [c for c in schema_cols if c in df.columns]
        df_to_save = df.select(cols_to_save)
        
        records = df_to_save.to_dicts()
        if not records:
            return 0
            
        # Preparar statement de UPSERT do Postgres via sqlalchemy.dialects.postgresql
        stmt = insert(Transaction).values(records)
        # stmt.excluded[col] é a referência correta à coluna na cláusula EXCLUDED.
        # Usamos cols_to_save (já calculado acima) para garantir que só
        # referenciamos colunas que existem no INSERT.
        update_dict = {
            col: stmt.excluded[col]
            for col in cols_to_save
            if col != "transaction_id"
        }
        
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["transaction_id"],
            set_=update_dict
        )
        
        db.execute(upsert_stmt)
        db.commit()
        
        rows = len(records)
        logger.info("transactions_clean: %s linhas salvas para user %s", rows, user_id)
        return rows
    except Exception as e:
        logger.error("Erro ao salvar transactions_clean: %s", e)
        db.rollback()
        return 0

def save_health_score_snapshot(
    db: Session,
    user_id: str,
    health_score: int,
    savings_rate: float,
    profile_type: str,
    safe_to_spend: Optional[float] = None,
    date: Optional[str] = None,
) -> bool:
    if date is None:
        date = datetime.now().strftime("%Y-%m")
    try:
        from datetime import datetime as _dt
        date = _dt.strptime(date, "%Y-%m").strftime("%Y-%m")
    except ValueError:
        raise ValueError(f"Parâmetro 'date' deve estar no formato 'YYYY-MM', recebido: {date!r}")

    try:
        stmt = insert(HealthScoreHistory).values(
            user_id=user_id,
            date=date,
            health_score=health_score,
            savings_rate=savings_rate,
            profile_type=profile_type,
            safe_to_spend=safe_to_spend
        )
        
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "date"],
            set_={
                "health_score": stmt.excluded.health_score,
                "savings_rate": stmt.excluded.savings_rate,
                "profile_type": stmt.excluded.profile_type,
                "safe_to_spend": stmt.excluded.safe_to_spend,
                "created_at": func.now()
            }
        )
        
        db.execute(upsert_stmt)
        db.commit()
        logger.info("health_score_history: snapshot salvo para user=%s date=%s score=%s", user_id, date, health_score)
        return True
    except Exception as e:
        logger.error("Erro ao salvar health_score_history: %s", e)
        db.rollback()
        return False
        
def get_health_score_history(
    db: Session,
    user_id: str,
    months: int = 6,
) -> List[Dict[str, Any]]:
    try:
        history_records = db.query(HealthScoreHistory).filter(HealthScoreHistory.user_id == user_id).order_by(HealthScoreHistory.date.desc()).limit(months).all()
        history = [
            {
                "date": row.date,
                "health_score": row.health_score,
                "savings_rate": row.savings_rate,
                "profile_type": row.profile_type,
                "safe_to_spend": row.safe_to_spend,
            }
            for row in reversed(history_records)
        ]
        return history
    except Exception as e:
        logger.error("Erro ao buscar health_score_history: %s", e)
        return []

def get_override_stats(db: Session, user_id: str) -> Dict[str, int]:
    try:
        rows = db.query(ContextOverride.corrected_context, func.count()).filter(ContextOverride.user_id == user_id).group_by(ContextOverride.corrected_context).all()
        stats = {row[0]: row[1] for row in rows}
        return stats
    except Exception as e:
        logger.error("Erro ao buscar stats: %s", e)
        return {}
