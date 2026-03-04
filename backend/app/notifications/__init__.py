# app/notifications/__init__.py
"""
Módulo de Notificações Proativas (MX.3)

Gera notificações baseadas em eventos financeiros detectados:
    - BURN_RATE_HIGH: saldo de orçamento por categoria
    - ANOMALY_DETECTED: gastos incomuns
    - SUBSCRIPTION_INCREASE: assinaturas que ficaram mais caras
    - CARD_OPPORTUNITY: oportunidade perdida de cashback
    - WAIVER_ALERT: falta pouco para isentar anuidade
    - TRANSFER_PROMO: bonus de transferência de pontos
    - SCORE_IMPROVED: health score melhorou
    - GOAL_PROGRESS: marco de meta atingido
    - SAFE_TO_SPEND_LOW: margem segura abaixo do limiar

USAGE:
    from app.notifications import ProactiveNotifier, NotificationContext

    ctx = NotificationContext(safe_to_spend=SafeToSpendInput(45.0, 1350.0))
    notes = ProactiveNotifier().generate(ctx)
"""

from .notifier import (
    ProactiveNotifier,
    Notification,
    NotificationContext,
    BurnRateCategoryInput,
    AnomalyInput,
    SubscriptionChangeInput,
    CardOpportunityInput,
    WaiverAlertInput,
    TransferPromoInput,
    ScoreChangeInput,
    GoalProgressInput,
    SafeToSpendInput,
)

__all__ = [
    "ProactiveNotifier",
    "Notification",
    "NotificationContext",
    "BurnRateCategoryInput",
    "AnomalyInput",
    "SubscriptionChangeInput",
    "CardOpportunityInput",
    "WaiverAlertInput",
    "TransferPromoInput",
    "ScoreChangeInput",
    "GoalProgressInput",
    "SafeToSpendInput",
]

__version__ = "1.0.0"
