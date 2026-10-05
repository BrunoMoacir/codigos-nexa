"""
app/api/v1/routes/notifications.py — Notificações Proativas (MX.3)

Endpoint: GET /notifications/{user_id}

Orquestra todas as fontes de dados e retorna notificações proativas
ordenadas por prioridade (CRITICAL → WARNING → INFO).

Pipeline de filtragem:
    1. ProactiveNotifier.generate()     — gera candidatos brutos
    2. NotificationRelevanceFilter      — quality + caps (income-relative)
    3. NotificationStateStore.filter_unseen — remove já-vistos (TTL por tipo)
    4. NotificationStateStore.mark_shown    — persiste estado + evento 'shown'
    5. Resposta inclui fingerprint por notificação para o cliente enviar eventos

Endpoint de eventos: POST /notifications/{user_id}/events
    Recebe {fingerprint, notification_type, event_type} e persiste no DuckDB.
    Alimenta o feedback loop de calibração dos thresholds.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import polars as pl
from fastapi import APIRouter, HTTPException, Query, status, Depends, Response
from pydantic import BaseModel

from app.core.security import require_owner
from app.notifications.notifier import (
    ProactiveNotifier,
    NotificationContext,
    BurnRateCategoryInput,
    AnomalyInput,
    SubscriptionChangeInput,
    SafeToSpendInput,
    ScoreChangeInput,
    GoalProgressInput,
    LifeEventInput,
)
from app.notifications.relevance_filter import NotificationRelevanceFilter
from app.notifications.state_store import NotificationStateStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications (MX.3)"])

_notifier          = ProactiveNotifier()
_relevance_filter  = NotificationRelevanceFilter()
_state_store       = NotificationStateStore()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: GET /notifications/{user_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="MX.3 — Notificações Proativas Inteligentes",
    description=(
        "Gera notificações proativas baseadas em eventos financeiros detectados. "
        "Pipeline: geração → filtro de relevância (income-relative) → "
        "deduplicação por estado (TTL) → persiste eventos 'shown'. "
        "Cada notificação inclui um fingerprint estável para o cliente "
        "enviar eventos de interação (tapped/dismissed)."
    ),
)
def get_notifications(
    user_id: str = Depends(require_owner),
    monthly_income: float = Query(
        default=0.0,
        ge=0,
        description="Renda mensal líquida — calibra thresholds de relevância.",
    ),
    include_info: bool = Query(
        default=True,
        description="Se False, retorna apenas CRITICAL e WARNING.",
    ),
) -> dict:
    logger.info("GET /notifications/%s | income=R$%.0f", user_id, monthly_income)

    ctx = NotificationContext()

    # ── 1. NexaRunner: busca transações e cashflow ─────────────────
    try:
        from app.runner import get_runner
        from app.forecast.etl.income_profiler import IncomeProfiler
        from app.forecast.etl.spending_anomaly_detector import SpendingAnomalyDetector
        from app.forecast.cashflow.burn_rate import BurnRateAnalyzer
        from app.goals.tracker import GoalTracker

        import os

        mode = "prod" if os.getenv("APP_MODE", "dev") == "prod" else "dev"

        # O extrato DESTE usuário, do banco. Era `.run()` sem user_id: em dev
        # rodava sobre o mock fixo da Pluggy (jan/2026), em produção sobre um
        # item sandbox criado na hora — ninguém via notificação sobre o próprio
        # dinheiro. É o mesmo caminho do /forecast.
        runner_result = get_runner(mode).run_from_db(user_id, horizon_days=30) or {}

        transactions_data = runner_result.get("transactions", {})
        transactions_df: pl.DataFrame | None = transactions_data.get("pf_pj_classified_df")

        # Enriquecer uma vez — merchant_id, category_canonical etc. ficam disponíveis
        # para burn rate, anomalia, assinaturas e life events sem re-enriquecimento.
        if transactions_df is not None and not transactions_df.is_empty():
            from app.optimizer.feature_store import TransactionFeatureEnricher
            transactions_df = TransactionFeatureEnricher().enrich(transactions_df)

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

        # ── 5. Eventos de vida ─────────────────────────────────────
        try:
            from app.optimizer.detectors.life_events_detector import LifeEventsDetector

            if transactions_df is not None and not transactions_df.is_empty():
                date_col = "date" if "date" in transactions_df.columns else "transaction_date"
                today = date.today()
                # transactions_df já enriquecido no início do bloco principal.
                txns_recent  = transactions_df.filter(
                    pl.col(date_col).cast(pl.Date) >= today - timedelta(days=60)
                )
                txns_history = transactions_df.filter(
                    pl.col(date_col).cast(pl.Date) < today - timedelta(days=180)
                )
                income_recent = income_profile.monthly_net_income if income_profile else 0.0
                for evt in LifeEventsDetector().detect_all(
                    txns_recent=txns_recent,
                    txns_history=txns_history,
                    income_recent=income_recent,
                    income_historical=income_recent,
                ):
                    ctx.life_events.append(LifeEventInput(
                        event=evt.event,
                        confidence=evt.confidence,
                        trigger_action=evt.trigger_action,
                    ))
        except Exception as le_exc:
            logger.debug("LifeEventsDetector indisponível: %s", le_exc)

        # ── 6. Assinaturas com preço aumentado ─────────────────────
        try:
            from app.subscriptions.subscription_detector import SubscriptionDetector
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

        # ── 7. Safe-to-spend ───────────────────────────────────────
        projections = runner_result.get("projections", {})
        sts_obj = projections.get("safe_to_spend")
        if sts_obj is not None:
            daily   = getattr(sts_obj, "safe_to_spend_daily", 0.0)
            monthly = getattr(sts_obj, "safe_to_spend_total", daily * 30)
            ctx.safe_to_spend = SafeToSpendInput(
                daily_safe_amount=daily,
                monthly_safe_amount=monthly,
            )

        # ── 8. Metas ativas ────────────────────────────────────────
        # GoalTracker exige a sessão por injeção: construído vazio, levantava
        # "requires a database session" no except abaixo e meta nenhuma jamais
        # gerou notificação.
        try:
            from app.core.database import SessionLocal

            with SessionLocal() as _db_metas:
                metas_ativas = GoalTracker(_db_metas).list_goals(user_id=user_id, status="ACTIVE")
            for goal in metas_ativas:
                pct       = (goal.current_amount / goal.target_amount * 100) if goal.target_amount > 0 else 0
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

        # ── 9. OPP — poupança vs CDI e dinheiro parado (OPP4-D / Etapa 6) ──
        # Reaproveita os detectores do NotificationEngine (mesmo contrato do
        # serviço; nenhum cálculo duplicado — regra do plano OPP.4).
        try:
            from app.notifications.engine import NotificationEngine
            ctx.savings_below_cdi = NotificationEngine._detect_savings_below_cdi(user_id)
            ctx.idle_money = NotificationEngine._detect_idle_money(user_id)
        except Exception as opp_exc:
            logger.debug("Detectores OPP indisponíveis: %s", opp_exc)

        # ── 10. R2.c/R2.b/R1.a — sazonalidade fiscal, desafios e follow-up
        # de compras. Mesmos detectores do engine proativo: feed reativo e
        # canal proativo mostram exatamente os mesmos cards.
        try:
            from app.notifications.engine import NotificationEngine
            ctx.fiscal_events = NotificationEngine._detect_fiscal_events(user_id)
            ctx.challenges = NotificationEngine._detect_challenges(user_id)
            ctx.purchase_followups = NotificationEngine._detect_purchase_followups(user_id)
        except Exception as ret_exc:
            logger.debug("Detectores de retenção indisponíveis: %s", ret_exc)

    except Exception as exc:
        logger.warning("NexaRunner indisponível para /notifications/%s: %s", user_id, exc)

    # ── Pipeline de filtragem ──────────────────────────────────────

    # Etapa A: geração bruta
    raw_notes = _notifier.generate(ctx)

    # Etapa B: relevância e confiança (quality + caps, income-relative)
    relevant = _relevance_filter.filter(raw_notes, monthly_income=monthly_income)

    # Etapa C: só sai do feed o que o usuário DISPENSOU. Antes era
    # `filter_unseen` + `mark_shown` aqui mesmo: a leitura marcava tudo como
    # visto, e a segunda abertura da tela (ou o refetch do react-query, que a
    # página de Estratégias disparava logo após montar) voltava vazia —
    # "Sem notificações recentes" para quem tinha alerta crítico.
    visiveis = _state_store.filter_dismissed(user_id, relevant)

    # Etapa D: filtro de prioridade solicitado pelo cliente
    if not include_info:
        visiveis = [n for n in visiveis if n.priority != "INFO"]

    # O fingerprint é o id ESTÁVEL do card (o `id` do Notification é um UUID
    # novo a cada geração e não serve para mandar evento).
    fingerprints = _state_store.annotate_fingerprints(user_id, visiveis)
    ja_vistas = _state_store.seen_fingerprints(user_id, list(fingerprints.values()))

    by_priority = {
        "CRITICAL": sum(1 for n in visiveis if n.priority == "CRITICAL"),
        "WARNING":  sum(1 for n in visiveis if n.priority == "WARNING"),
        "INFO":     sum(1 for n in visiveis if n.priority == "INFO"),
    }

    logger.info(
        "GET /notifications/%s | raw=%d relevant=%d visiveis=%d "
        "CRITICAL=%d WARNING=%d INFO=%d income=R$%.0f",
        user_id, len(raw_notes), len(relevant), len(visiveis),
        by_priority["CRITICAL"], by_priority["WARNING"], by_priority["INFO"],
        monthly_income,
    )

    itens = []
    for n in visiveis:
        fp = fingerprints.get(n.id, "")
        item = n.to_dict()
        item.update({
            "id": fp,
            "fingerprint": fp,
            "created_at": item.get("generated_at"),
            "action_route": _ROTA_DA_ACAO.get(n.type),
            "seen": fp in ja_vistas,
        })
        itens.append(item)

    return {
        "user_id":       user_id,
        "total":         len(itens),
        "by_priority":   by_priority,
        "notifications": itens,
    }


# Tela do app onde o usuário age sobre cada tipo de card.
_ROTA_DA_ACAO: dict[str, str] = {
    "BURN_RATE_HIGH":            "/organizar",
    "ANOMALY_DETECTED":          "/organizar",
    "SAFE_TO_SPEND_LOW":         "/dashboard",
    "SUBSCRIPTION_INCREASE":     "/organizar",
    "SCORE_IMPROVED":            "/organizar",
    "CHALLENGE_COMPLETED":       "/organizar",
    "CHALLENGE_PROGRESS":        "/organizar",
    "GOAL_PROGRESS":             "/goals",
    "CARD_OPPORTUNITY":          "/strategies",
    "WAIVER_ALERT":              "/strategies",
    "TRANSFER_PROMO":            "/strategies",
    "PURCHASE_FOLLOWUP":         "/strategies",
    "SAVINGS_BELOW_CDI":         "/feed",
    "IDLE_MONEY_DETECTED":       "/feed",
    "FISCAL_SEASON":             "/impostos",
    "TARIFA_AUMENTO_UNILATERAL": "/defesa",
    "LIFE_EVENT":                "/chat",
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: POST /notifications/{user_id}/events
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class NotificationEventRequest(BaseModel):
    fingerprint:       str
    notification_type: str
    # "shown" (o app exibiu) | "tapped"/"clicked" (seguiu a ação) |
    # "dismissed" (tirou do feed) | "acted" (fez o que o card pedia)
    event_type:        str


_ALIAS_DE_EVENTO = {"clicked": "tapped"}


@router.post(
    "/{user_id}/events",
    status_code=status.HTTP_200_OK,
    summary="MX.3 — Registrar evento de interação com notificação",
    description=(
        "Registra que o usuário tocou ou dispensou uma notificação. "
        "Alimenta o feedback loop de calibração dos thresholds de relevância. "
        "event_type aceita: 'tapped' | 'dismissed'."
    ),
)
def post_notification_event(
    body: NotificationEventRequest,
    user_id: str = Depends(require_owner),
) -> dict:
    evento = _ALIAS_DE_EVENTO.get(body.event_type, body.event_type)
    if evento not in _state_store.EVENTOS_VALIDOS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"event_type inválido: '{body.event_type}'. "
                "Use 'shown', 'tapped' (ou 'clicked'), 'dismissed' ou 'acted'."
            ),
        )

    _state_store.log_event(
        user_id=user_id,
        fingerprint=body.fingerprint,
        notification_type=body.notification_type,
        event_type=evento,
    )

    logger.info(
        "POST /notifications/%s/events | type=%s event=%s fp=%s",
        user_id, body.notification_type, body.event_type, body.fingerprint,
    )
    return {"ok": True}
