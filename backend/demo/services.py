"""
demo/services.py — Ponte entre o Streamlit e os serviços REAIS da Nexa.

Nada aqui recalcula inteligência: apenas orquestra os componentes de
produção sobre os dados semeados no banco.

  dashboard_data(user_id)  → forecast/safe-to-spend, health score, perfil
                             comportamental, gastos por categoria, PF/PJ
  build_feed(user_id)      → cards proativos REAIS (mesmo ProactiveNotifier
                             e NotificationRelevanceFilter do produto), mas
                             a partir de run_from_db (dados da persona) em
                             vez do Pluggy mock que o router HTTP usa.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import polars as pl

logger = logging.getLogger("demo.services")


# ══════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════

def dashboard_data(user_id: str) -> dict:
    """Diagnóstico completo da persona pelos serviços reais."""
    from app.runner import get_runner
    from app.core.db.queries import get_transactions_for_user

    out: dict = {"user_id": user_id, "ok": False}

    df = get_transactions_for_user(user_id)
    if df.is_empty():
        out["error"] = "Sem transações — rode `python3 -m demo.seed` primeiro."
        return out

    result = get_runner("dev").run_from_db(user_id)
    if not result or result.get("status") != "success":
        out["error"] = "Pipeline não retornou sucesso."
        return out

    proj = result.get("projections", {})
    analysis = result.get("analysis", {})
    sts = proj.get("safe_to_spend")
    income = analysis.get("income_profile")

    out.update({
        "ok": True,
        "n_transactions": len(df),
        "current_balance": proj.get("current_balance"),
        "min_projected_balance": proj.get("min_projected_balance"),
        "safe_to_spend_daily": getattr(sts, "safe_to_spend_daily", None),
        "safe_to_spend_total": getattr(sts, "safe_to_spend_total", None),
        "monthly_income": getattr(income, "monthly_net_income", None),
        "income_pattern": getattr(getattr(income, "income_pattern", None), "value",
                                  getattr(income, "income_pattern", None)),
        "cashflow_forecast": proj.get("cashflow_forecast"),
    })

    # O health score precisa vir ANTES do perfil: o `resilience_score` que ele
    # calcula é entrada do FSS, e passá-lo como zero (o que este demo fazia)
    # dava a TODA persona o sinal `low_resilience=0` — a penalidade máxima.
    # Era o que mantinha a Ana em ALERTA com health score 85.
    out["health_score"] = _health_score(user_id, df)
    out["profile"] = _behavioral_profile(df, out["health_score"].get("resilience"))
    out["by_category"] = _spend_by_category(df)
    out["pf_pj"] = _pf_pj_split(df)
    out["recent"] = _recent_transactions(df)
    return out


def _behavioral_profile(df: pl.DataFrame, resilience: float | None = None) -> dict:
    """
    Cluster comportamental (ML híbrido) + FSS via o profiler real.

    `resilience` é o `resilience_score` do `UserProfileAnalyzer`. Ele entra no
    FSS como o fator de resiliência; sem ele o cálculo recebia zero fixo e todo
    perfil ganhava `low_resilience=0`, que sozinho põe o FSS em ALERTA.
    """
    try:
        from app.optimizer.profiler import ConsumptionProfiler
        from app.optimizer.detectors.lifestyle_classifier import LifestyleClassifier
        from app.optimizer.detectors.fss_calculator import FSSCalculator

        profile = ConsumptionProfiler().build(df)
        try:
            fss = FSSCalculator().calc_fss(
                profile, df, resilience_score=float(resilience or 0.0))
            profile.fss = fss["fss"]
            profile.fss_level = fss["fss_level"]
        except Exception:
            pass
        classified = LifestyleClassifier().classify(profile)
        return {
            "cluster": classified.get("lifestyle_cluster"),
            "secondary": classified.get("secondary_clusters", []),
            "source": classified.get("classification_source"),
            "ml_confidence": classified.get("ml_confidence"),
            "fss": getattr(profile, "fss", None),
            "fss_level": getattr(profile, "fss_level", None),
            "is_mei": getattr(profile, "is_likely_mei", False),
            "savings_rate": getattr(profile, "savings_rate", None),
        }
    except Exception as exc:
        logger.warning("perfil comportamental: %s", exc)
        return {"cluster": "NAO_CLASSIFICADO", "error": str(exc)}


def _health_score(user_id: str, df: pl.DataFrame) -> dict:
    """Score 0–100 via UserProfileAnalyzer real (o mesmo usado no forecast)."""
    try:
        from app.forecast.etl.profiles import UserProfileAnalyzer
        from app.forecast.etl.income_profiler import IncomeProfiler

        work = df
        if "transaction_date" not in work.columns and "date" in work.columns:
            work = work.with_columns(pl.col("date").cast(pl.Datetime).alias("transaction_date"))
        income = None
        try:
            income = IncomeProfiler().build(work)
        except Exception:
            pass
        analyzer = UserProfileAnalyzer().analyze(work, income_profile=income)
        score = getattr(analyzer, "financial_health_score", None)
        resilience = getattr(analyzer, "resilience_score", None)
        level = (
            "SAUDÁVEL" if (score or 0) >= 70
            else "ATENÇÃO" if (score or 0) >= 40
            else "CRÍTICO"
        )
        return {"score": score, "resilience": resilience, "level": level,
                "savings_rate": getattr(analyzer, "savings_rate", None)}
    except Exception as exc:
        logger.warning("health_score: %s", exc)
        return {"score": None, "level": None}


def _spend_by_category(df: pl.DataFrame) -> list[dict]:
    if "amount" not in df.columns or "category" not in df.columns:
        return []
    spend = (
        df.filter(pl.col("amount") < 0)
        .with_columns(pl.col("amount").abs().alias("gasto"))
        .group_by("category")
        .agg(pl.col("gasto").sum().alias("total"), pl.len().alias("n"))
        .sort("total", descending=True)
    )
    return spend.to_dicts()


def _pf_pj_split(df: pl.DataFrame) -> dict:
    col = "context_type" if "context_type" in df.columns else None
    if col is None:
        return {}
    gastos = df.filter(pl.col("amount") < 0).with_columns(pl.col("amount").abs().alias("g"))
    if gastos.is_empty():
        return {}
    agg = gastos.group_by(col).agg(pl.col("g").sum().alias("total")).to_dicts()
    return {str(r[col]): round(r["total"], 2) for r in agg}


def _recent_transactions(df: pl.DataFrame, n: int = 15) -> list[dict]:
    date_col = "date" if "date" in df.columns else "transaction_date"
    cols = [c for c in (date_col, "description", "amount", "category", "context_type") if c in df.columns]
    recent = df.select(cols).sort(date_col, descending=True).head(n)
    return recent.to_dicts()


# ══════════════════════════════════════════════════════════════════════
# FEED — cards proativos reais (a partir dos dados da persona)
# ══════════════════════════════════════════════════════════════════════

def build_feed(user_id: str, monthly_income: float = 0.0) -> list[dict]:
    """
    Constrói o feed com o MESMO notifier + filtro de relevância do produto,
    porém a partir de run_from_db (persona) em vez do Pluggy mock que o
    router HTTP usa. Espelha o pipeline do router de notificações.
    """
    from app.notifications.notifier import (
        AnomalyInput, BurnRateCategoryInput, GoalProgressInput,
        LifeEventInput, NotificationContext, ProactiveNotifier,
        SafeToSpendInput, SubscriptionChangeInput,
    )
    from app.notifications.relevance_filter import NotificationRelevanceFilter
    from app.runner import get_runner

    ctx = NotificationContext()
    result = get_runner("dev").run_from_db(user_id)
    tx = result.get("transactions", {}) if result else {}
    df = tx.get("pf_pj_classified_df")

    if df is not None and not df.is_empty():
        try:
            from app.optimizer.feature_store import TransactionFeatureEnricher
            df = TransactionFeatureEnricher().enrich(df)
        except Exception:
            pass

    income_profile = None
    if df is not None and not df.is_empty():
        from app.forecast.etl.income_profiler import IncomeProfiler
        income_profile = IncomeProfiler().build(df)
        if monthly_income == 0.0 and income_profile and income_profile.confidence >= 0.5:
            monthly_income = income_profile.monthly_net_income

    # Burn rate por categoria
    _safe(lambda: _burn_rate(ctx, df, monthly_income, BurnRateCategoryInput))
    # Anomalias
    _safe(lambda: _anomalies(ctx, df, income_profile, AnomalyInput))
    # Eventos de vida
    _safe(lambda: _life_events(ctx, df, income_profile, LifeEventInput))
    # Assinaturas que subiram
    _safe(lambda: _subscriptions(ctx, df, SubscriptionChangeInput))
    # Safe-to-spend
    _safe(lambda: _safe_to_spend(ctx, result, SafeToSpendInput))
    # Metas
    _safe(lambda: _goals(ctx, user_id, GoalProgressInput))
    # Detectores DB-based do engine (OPP, fiscal, desafios, compras, promoções)
    _safe(lambda: _engine_detectors(ctx, user_id))

    raw_notes = ProactiveNotifier().generate(ctx)
    relevant = NotificationRelevanceFilter().filter(
        raw_notes, monthly_income=monthly_income if monthly_income > 0 else None
    )
    relevant.sort(key=lambda n: {"CRITICAL": 0, "WARNING": 1, "INFO": 2}.get(n.priority, 3))
    return [_note_to_dict(n) for n in relevant]


def _safe(fn):
    try:
        fn()
    except Exception as exc:
        logger.debug("feed detector: %s", exc)


def _burn_rate(ctx, df, monthly_income, BurnRateCategoryInput):
    if df is None or df.is_empty():
        return
    from app.forecast.cashflow.burn_rate import BurnRateAnalyzer

    report = BurnRateAnalyzer().analyze(
        transactions_df=df, monthly_income=monthly_income if monthly_income > 0 else None
    )
    today = date.today()
    for cat in report.categories_over_pace:
        ctx.burn_rate_categories.append(BurnRateCategoryInput(
            category=cat.category, spent_so_far=cat.spent_so_far,
            monthly_budget=cat.monthly_budget, pct_consumed=cat.pct_consumed,
            current_day=today.day,
        ))


def _anomalies(ctx, df, income_profile, AnomalyInput):
    if df is None or df.is_empty():
        return
    from app.forecast.etl.spending_anomaly_detector import SpendingAnomalyDetector

    cutoff = date.today() - timedelta(days=30)
    recent = df.filter(pl.col("transaction_date").cast(pl.Date) >= cutoff)
    if recent.is_empty():
        return
    for a in SpendingAnomalyDetector().detect(
        transactions_df=recent, history_df=df, income_profile=income_profile
    )[:5]:
        ctx.anomalies.append(AnomalyInput(
            merchant=getattr(a, "merchant", a.anomaly_type),
            amount=getattr(a, "amount", 0.0),
            factor=getattr(a, "sigma_distance", getattr(a, "factor", 2.0)),
            anomaly_type=a.anomaly_type, description=a.description,
        ))


def _life_events(ctx, df, income_profile, LifeEventInput):
    if df is None or df.is_empty():
        return
    from app.optimizer.detectors.life_events_detector import LifeEventsDetector

    date_col = "date" if "date" in df.columns else "transaction_date"
    today = date.today()
    recent = df.filter(pl.col(date_col).cast(pl.Date) >= today - timedelta(days=60))
    history = df.filter(pl.col(date_col).cast(pl.Date) < today - timedelta(days=180))
    income = income_profile.monthly_net_income if income_profile else 0.0
    for evt in LifeEventsDetector().detect_all(
        txns_recent=recent, txns_history=history,
        income_recent=income, income_historical=income,
    ):
        ctx.life_events.append(LifeEventInput(
            event=evt.event, confidence=evt.confidence, trigger_action=evt.trigger_action,
        ))


def _subscriptions(ctx, df, SubscriptionChangeInput):
    if df is None or df.is_empty():
        return
    from app.subscriptions.subscription_detector import SubscriptionDetector

    report = SubscriptionDetector().detect(df)
    for sub in getattr(report, "subscriptions", []):
        if getattr(sub, "price_increased", False):
            old = getattr(sub, "previous_amount", 0.0)
            new = getattr(sub, "amount", 0.0)
            if old > 0 and new > old:
                ctx.subscription_changes.append(SubscriptionChangeInput(
                    merchant=sub.merchant, old_amount=old, new_amount=new,
                    pct_change=(new - old) / old,
                ))


def _safe_to_spend(ctx, result, SafeToSpendInput):
    sts = result.get("projections", {}).get("safe_to_spend")
    if sts is None:
        return
    daily = getattr(sts, "safe_to_spend_daily", 0.0)
    ctx.safe_to_spend = SafeToSpendInput(
        daily_safe_amount=daily,
        monthly_safe_amount=getattr(sts, "safe_to_spend_total", daily * 30),
    )


def _goals(ctx, user_id, GoalProgressInput):
    from app.goals.tracker import GoalTracker

    for goal in GoalTracker().list_goals(user_id=user_id, status="ACTIVE"):
        pct = (goal.current_amount / goal.target_amount * 100) if goal.target_amount > 0 else 0
        ctx.goal_progress.append(GoalProgressInput(
            goal_name=goal.name, goal_id=goal.id, pct_complete=pct,
            remaining_amount=max(0.0, goal.target_amount - goal.current_amount),
            target_date=goal.target_date,
        ))


def _engine_detectors(ctx, user_id):
    from app.notifications.engine import NotificationEngine

    ctx.savings_below_cdi = NotificationEngine._detect_savings_below_cdi(user_id)
    ctx.idle_money = NotificationEngine._detect_idle_money(user_id)
    ctx.fiscal_events = NotificationEngine._detect_fiscal_events(user_id)
    ctx.challenges = NotificationEngine._detect_challenges(user_id)
    ctx.purchase_followups = NotificationEngine._detect_purchase_followups(user_id)
    ctx.transfer_promos = NotificationEngine._detect_transfer_promos(user_id)


def _note_to_dict(n) -> dict:
    return {
        "type": n.type,
        "priority": n.priority,
        "title": n.title,
        "message": n.message,
        "action_hint": getattr(n, "action_hint", None),
        "metadata": getattr(n, "metadata", {}) or {},
    }


__all__ = ["dashboard_data", "build_feed"]
