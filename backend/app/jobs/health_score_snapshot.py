"""
app/jobs/health_score_snapshot.py — Job diário 04h00 (MX.1)

Recalcula e persiste o health score de cada usuário ativo em health_score_history.
Garante que o histórico mensal existe mesmo sem o usuário abrir o app.
Após o cálculo, avalia badges de gamificação via BadgeService e sincroniza
os desafios mensais (R2.b) via ChallengeService — geração no início do mês,
progresso diário e fechamento do mês anterior.
"""

import logging
from app.jobs._base import get_active_user_ids, job_guard

logger = logging.getLogger(__name__)


@job_guard("health_score_snapshot")
async def run_health_score_snapshot() -> None:
    from app.core.database import SessionLocal
    from app.core.db.queries import (
        get_health_score_history,
        get_transactions_for_user,
        save_health_score_snapshot,
    )
    from app.forecast.etl.profiles import UserProfileAnalyzer
    from app.health_score.badge_service import BadgeService

    user_ids = get_active_user_ids()
    logger.info("[health_score_snapshot] Calculando score para %d usuários", len(user_ids))

    badge_service = BadgeService()
    success_count = 0

    for user_id in user_ids:
        try:
            with SessionLocal() as db:
                df = get_transactions_for_user(user_id, db=db)
                if df.is_empty():
                    continue

                analyzer = UserProfileAnalyzer()
                profile = analyzer.analyze(df)
                resilience_score = profile.resilience_score

                fss_value = 0.0
                try:
                    from app.optimizer.profiler import ConsumptionProfiler

                    prof_df = df
                    if "transaction_date" in df.columns and "date" not in df.columns:
                        prof_df = df.rename({"transaction_date": "date"})
                    beh = ConsumptionProfiler().build(prof_df)
                    fss_value = beh.fss
                except Exception:
                    pass

                current_score = round(resilience_score * 0.60 + (100 - fss_value) * 0.40)

                save_health_score_snapshot(
                    db=db,
                    user_id=user_id,
                    health_score=current_score,
                    savings_rate=profile.savings_rate,
                    profile_type=profile.profile_type,
                )

                history = get_health_score_history(db=db, user_id=user_id, months=6)
                badge_service.evaluate_badges(user_id, current_score, history)

            # R2.b — desafios mensais: gera (mês novo), atualiza progresso e
            # fecha o mês anterior. Fora do SessionLocal do snapshot — o
            # service abre as próprias sessões e falha aberto.
            try:
                from app.health_score.challenge_service import get_challenge_service

                get_challenge_service().sync(user_id)
            except Exception as ch_exc:
                logger.warning("[health_score_snapshot] challenges user=%s: %s", user_id, ch_exc)

            success_count += 1

        except Exception as exc:
            logger.warning("[health_score_snapshot] user=%s erro: %s", user_id, exc)

    logger.info(
        "[health_score_snapshot] Concluído: %d/%d usuários processados",
        success_count,
        len(user_ids),
    )
