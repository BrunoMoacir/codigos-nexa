"""
app/api/v1/routes/notifications.py — Notificações Proativas (MX.3)

Endpoint: GET /notifications/{user_id}

Orquestra todas as fontes de dados e retorna notificações proativas
ordenadas por prioridade (CRITICAL → WARNING → INFO).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import polars as pl
from fastapi import APIRouter, HTTPException, Query, status, Depends
from app.core.security import get_current_user

from app.notifications.notifier import (
    ProactiveNotifier,
    NotificationContext,
    BurnRateCategoryInput,
    AnomalyInput,
    SubscriptionChangeInput,
    SafeToSpendInput,
    ScoreChangeInput,
    GoalProgressInput,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications (MX.3)"])

_notifier = ProactiveNotifier()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: GET /notifications/{user_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="MX.3 — Notificações Proativas Inteligentes",
    description=(
        "Gera notificações proativas baseadas em eventos financeiros detectados: "
        "burn rate alto, anomalias de gasto, assinaturas com preço aumentado, "
        "oportunidade de cartão, isenção de anuidade próxima, promoção de pontos, "
        "variação do score financeiro, marco de meta atingido, e margem segura baixa. "
        "Retorna lista ordenada por prioridade (CRITICAL → WARNING → INFO)."
    ),
)
async def get_notifications(
    user_id: str,
    monthly_income: float = Query(
        default=0.0,
        ge=0,
        description="Renda mensal líquida para contextualizar alertas de orçamento (opcional).",
    ),
    include_info: bool = Query(
        default=True,
        description="Se False, retorna apenas CRITICAL e WARNING.",
    ),
    _: str = Depends(get_current_user),
) -> dict:
    """
    Retorna notificações proativas baseadas no histórico real do usuário.

    **Fontes de dados consultadas:**
    - Transações dos últimos 90 dias (DuckDB/NexaRunner)
    - BurnRateAnalyzer (velocidade de gasto por categoria)
    - SpendingAnomalyDetector (gastos incomuns)
    - SubscriptionDetector (mudanças de assinatura)
    - CashflowEngine (safe-to-spend)
    - GoalTracker (progresso de metas ativas)

    **Exemplo de resposta:**
    ```json
    {
        "user_id": "user_123",
        "total": 3,
        "by_priority": {"CRITICAL": 1, "WARNING": 1, "INFO": 1},
        "notifications": [
            {
                "type": "BURN_RATE_HIGH",
                "priority": "CRITICAL",
                "title": "⛔ Orçamento de Alimentação estourado",
                "message": "Você gastou R$1.200 em Alimentação — R$200 acima do orçamento.",
                "action_hint": "Evite gastos em Alimentação pelo resto do mês.",
                ...
            }
        ]
    }
    ```
    """
    logger.info("GET /notifications/%s | income=R$%.0f", user_id, monthly_income)

    ctx = NotificationContext()

    # ── 1. NexaRunner: busca transações e cashflow ─────────────────
    try:
        from app.runner import NexaRunner
        from app.etl.income_profiler import IncomeProfiler
        from app.etl.spending_anomaly_detector import SpendingAnomalyDetector
        from app.cashflow.burn_rate import BurnRateAnalyzer
        from app.goals.tracker import GoalTracker

        import os
        from app.core.config import settings

        mode = "prod" if os.getenv("APP_MODE", "dev") == "prod" else "dev"
        if mode == "prod" and (not settings.PLUGGY_CLIENT_ID or not settings.PLUGGY_CLIENT_SECRET):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Pluggy não configurada. Defina PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET no backend/.env.",
            )

        runner = NexaRunner(mode=mode)
        runner_result = runner.run(horizon_days=30)

        transactions_data = runner_result.get("transactions", {})
        transactions_df: pl.DataFrame | None = transactions_data.get("pf_pj_classified_df")

        # ── 2. IncomeProfile ───────────────────────────────────────
        income_profile = None
        if transactions_df is not None and not transactions_df.is_empty():
            income_profile = IncomeProfiler().build(transactions_df)
            if monthly_income == 0.0 and income_profile.confidence >= 0.5:
                monthly_income = income_profile.monthly_net_income

        # ── 3. Burn rate por categoria ─────────────────────────────
        if transactions_df is not None and not transactions_df.is_empty():
            burn_report = BurnRateAnalyzer().analyze(
                transactions_df=transactions_df,
                monthly_income=monthly_income if monthly_income > 0 else None,
            )
            today = date.today()
            for cat in burn_report.categories_over_pace:
                ctx.burn_rate_categories.append(BurnRateCategoryInput(
                    category=cat.category,
                    spent_so_far=cat.spent_so_far,
                    monthly_budget=cat.monthly_budget,
                    pct_consumed=cat.pct_consumed,
                    current_day=today.day,
                ))

        # ── 4. Anomalias de gasto ──────────────────────────────────
        if transactions_df is not None and not transactions_df.is_empty():
            cutoff = date.today() - timedelta(days=30)
            recent_df = transactions_df.filter(
                pl.col("transaction_date").cast(pl.Date) >= cutoff
            )
            if not recent_df.is_empty():
                anomalies = SpendingAnomalyDetector().detect(
                    transactions_df=recent_df,
                    history_df=transactions_df,
                    income_profile=income_profile,
                )
                for a in anomalies[:5]:
                    ctx.anomalies.append(AnomalyInput(
                        merchant=getattr(a, "merchant", a.anomaly_type),
                        amount=getattr(a, "amount", 0.0),
                        factor=getattr(a, "sigma_distance", getattr(a, "factor", 2.0)),
                        anomaly_type=a.anomaly_type,
                        description=a.description,
                    ))

        # ── 5. Assinaturas com preço aumentado ─────────────────────
        try:
            from app.etl.subscription_detector import SubscriptionDetector
            if transactions_df is not None and not transactions_df.is_empty():
                sub_report = SubscriptionDetector().detect(transactions_df)
                for sub in getattr(sub_report, "subscriptions", []):
                    if getattr(sub, "price_increased", False):
                        old = getattr(sub, "previous_amount", 0.0)
                        new = getattr(sub, "amount", 0.0)
                        if old > 0 and new > old:
                            ctx.subscription_changes.append(SubscriptionChangeInput(
                                merchant=sub.merchant,
                                old_amount=old,
                                new_amount=new,
                                pct_change=(new - old) / old,
                            ))
        except Exception as sub_exc:
            logger.debug("SubscriptionDetector indisponível: %s", sub_exc)

        # ── 6. Safe-to-spend ───────────────────────────────────────
        projections = runner_result.get("projections", {})
        sts_obj = projections.get("safe_to_spend")
        if sts_obj is not None:
            daily = getattr(sts_obj, "safe_to_spend_daily", 0.0)
            monthly = getattr(sts_obj, "safe_to_spend_total", daily * 30)
            ctx.safe_to_spend = SafeToSpendInput(
                daily_safe_amount=daily,
                monthly_safe_amount=monthly,
            )

        # ── 7. Metas ativas ────────────────────────────────────────
        try:
            tracker = GoalTracker()
            active_goals = tracker.list_goals(user_id=user_id, status="ACTIVE")
            for goal in active_goals:
                proj = tracker.get_projection(goal)
                pct = (goal.current_amount / goal.target_amount * 100) if goal.target_amount > 0 else 0
                remaining = max(0.0, goal.target_amount - goal.current_amount)
                ctx.goal_progress.append(GoalProgressInput(
                    goal_name=goal.name,
                    goal_id=goal.id,
                    pct_complete=pct,
                    remaining_amount=remaining,
                    target_date=goal.target_date,
                ))
        except Exception as goal_exc:
            logger.debug("GoalTracker indisponível: %s", goal_exc)

    except Exception as exc:
        logger.warning("NexaRunner indisponível para /notifications/%s: %s", user_id, exc)
        # Retorna notificações vazias em caso de falha — não lança 500

    # ── 8. Gerar notificações ──────────────────────────────────────
    all_notes = _notifier.generate(ctx)

    if not include_info:
        all_notes = [n for n in all_notes if n.priority != "INFO"]

    by_priority = {
        "CRITICAL": sum(1 for n in all_notes if n.priority == "CRITICAL"),
        "WARNING":  sum(1 for n in all_notes if n.priority == "WARNING"),
        "INFO":     sum(1 for n in all_notes if n.priority == "INFO"),
    }

    logger.info(
        "GET /notifications/%s | total=%d CRITICAL=%d WARNING=%d INFO=%d",
        user_id, len(all_notes), by_priority["CRITICAL"], by_priority["WARNING"], by_priority["INFO"],
    )

    return {
        "user_id":      user_id,
        "total":        len(all_notes),
        "by_priority":  by_priority,
        "notifications": [n.to_dict() for n in all_notes],
    }
