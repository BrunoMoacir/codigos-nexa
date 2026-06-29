"""
app/jobs/fee_snapshot.py — Job diário 02h00 (D2/D4)

Responsabilidades:
  1. Para cada usuário ativo: analisar tarifas e persistir em bank_fee_history.
  2. Após processar todos os usuários: agregar bank_fee_history → bank_fee_trends
     (avg, p25, p75 anônimos por banco/fee_type/mês).

bank_fee_trends é o que permite que compare_to_market_baseline() use dados
reais de mercado em vez do benchmark estático de MarketFeesDB.

Anonimização: HAVING COUNT(DISTINCT user_id) >= 2 — linhas com apenas 1 usuário
não são publicadas no benchmark para não expor dados individuais.
"""

import logging
import uuid

from app.jobs._base import get_active_user_ids, job_guard

logger = logging.getLogger(__name__)


@job_guard("fee_snapshot")
async def run_fee_snapshot() -> None:
    user_ids = get_active_user_ids()
    logger.info("[fee_snapshot] %d usuários ativos", len(user_ids))

    if not user_ids:
        return

    ok, skipped, failed = 0, 0, 0

    from app.costs.bank_fee_analyzer import BankFeeAnalyzer
    from app.core.db.queries import get_transactions_for_user

    analyzer = BankFeeAnalyzer()

    for user_id in user_ids:
        try:
            df = get_transactions_for_user(user_id)
            if df.is_empty():
                skipped += 1
                continue

            report = analyzer.analyze(df, user_id=user_id)
            analyzer.persist_snapshot(report)
            ok += 1

        except Exception as exc:
            failed += 1
            logger.warning("[fee_snapshot] user=%s erro: %s", user_id, exc)

    logger.info(
        "[fee_snapshot] Snapshots: %d ok / %d sem dados / %d falha",
        ok, skipped, failed,
    )

    # Agrega bank_fee_history → bank_fee_trends após todos os usuários
    _aggregate_market_trends()


def _aggregate_market_trends() -> None:
    """
    Agrega bank_fee_history → bank_fee_trends.

    Calcula avg, p25, p75 e sample_size por (bank_name, fee_type, month) usando
    PERCENTILE_CONT do PostgreSQL. Faz UPSERT para que re-execuções atualizem
    os valores sem duplicar linhas.

    Apenas agrega grupos com >= 2 usuários distintos (anonimização).
    """
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            rows = db.execute(
                text("""
                    SELECT
                        bank_name,
                        fee_type,
                        month,
                        AVG(amount)::numeric(10,2)                                                AS market_avg,
                        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY amount)::numeric(10,2)       AS market_p25,
                        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY amount)::numeric(10,2)       AS market_p75,
                        COUNT(DISTINCT user_id)                                                    AS sample_size
                    FROM bank_fee_history
                    GROUP BY bank_name, fee_type, month
                    HAVING COUNT(DISTINCT user_id) >= 2
                """)
            ).fetchall()

            for row in rows:
                bank_name, fee_type, month, market_avg, market_p25, market_p75, sample_size = row
                db.execute(
                    text("""
                        INSERT INTO bank_fee_trends
                            (id, bank_name, fee_type, month,
                             market_avg, market_p25, market_p75, sample_size)
                        VALUES
                            (:id, :bank, :ftype, :month,
                             :avg, :p25, :p75, :n)
                        ON CONFLICT ON CONSTRAINT uq_bank_fee_trends DO UPDATE SET
                            market_avg   = EXCLUDED.market_avg,
                            market_p25   = EXCLUDED.market_p25,
                            market_p75   = EXCLUDED.market_p75,
                            sample_size  = EXCLUDED.sample_size,
                            captured_at  = now()
                    """),
                    {
                        "id":    str(uuid.uuid4()),
                        "bank":  bank_name,
                        "ftype": fee_type,
                        "month": month,
                        "avg":   float(market_avg)  if market_avg  is not None else None,
                        "p25":   float(market_p25)  if market_p25  is not None else None,
                        "p75":   float(market_p75)  if market_p75  is not None else None,
                        "n":     int(sample_size),
                    },
                )

            db.commit()

        logger.info("[fee_snapshot] bank_fee_trends atualizado: %d linhas", len(rows))

    except Exception as exc:
        logger.warning("[fee_snapshot] _aggregate_market_trends falhou: %s", exc)
