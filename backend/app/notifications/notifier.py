"""
app/notifications/notifier.py — Notificações Proativas Inteligentes (MX.3)

RESPONSABILIDADE:
    Gera notificações proativas baseadas em regras, combinando dados de:
    - BurnRateReport (velocidade de gasto)
    - BudgetSuggestion (análise 50/30/20)
    - SpendingAnomalies (gastos incomuns)
    - SubscriptionReport (assinaturas aumentadas)
    - CashflowEngine (safe-to-spend baixo)
    - HealthScore (score melhorou)
    - GoalTracker (progresso de metas)
    - Optimizer hints (oportunidade de cartão)

TIPOS DE NOTIFICAÇÃO (per spec MX.3):
    BURN_RATE_HIGH        — "Você já gastou {pct}% do orçamento de {category} no dia {day}"
    ANOMALY_DETECTED      — "Gasto incomum: R${amount} em {merchant} — {factor}x acima do padrão"
    SUBSCRIPTION_INCREASE — "{merchant} aumentou de R${old} para R${new}"
    CARD_OPPORTUNITY      — "Você deixou de ganhar R${amount} — vale trocar de cartão"
    WAIVER_ALERT         — "Faltam R${amount} para isentar a anuidade de {card}"
    TRANSFER_PROMO       — "Transferência com {bonus}% de bônus — seus pontos valem o dobro"
    SCORE_IMPROVED       — "Seu score financeiro subiu de {old} para {new} 🎉"
    GOAL_PROGRESS        — "Meta '{goal}': {pct}% concluída — faltam R${remaining}"
    SAFE_TO_SPEND_LOW    — "Sua margem segura caiu para R${amount}/dia"

DESIGN:
    - Puramente funcional: cada regra é uma função independente e testável
    - Sem I/O: recebe dataclasses calculadas ao invés de buscar dados
    - Prioridade: CRITICAL > WARNING > INFO
    - Deduplicação: cada tipo de notificação aparece no máximo 1x por contexto
    - Integrado: GET /notifications/{user_id} orquestra todos os geradores

USAGE:
    >>> notifier = ProactiveNotifier()
    >>> notes = notifier.generate(context)
    >>> for n in notes:
    ...     print(n.priority, n.message)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONSTANTES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NotificationPriority = Literal["CRITICAL", "WARNING", "INFO"]

NotificationType = Literal[
    "BURN_RATE_HIGH",
    "ANOMALY_DETECTED",
    "SUBSCRIPTION_INCREASE",
    "CARD_OPPORTUNITY",
    "WAIVER_ALERT",
    "TRANSFER_PROMO",
    "SCORE_IMPROVED",
    "GOAL_PROGRESS",
    "SAFE_TO_SPEND_LOW",
    "LIFE_EVENT",
    "TARIFA_AUMENTO_UNILATERAL",
]

# Thresholds para safe-to-spend baixo
_LOW_STS_DAILY_ABS    = 50.0    # R$/dia — abaixo disso é crítico
_WARN_STS_DAILY_ABS   = 100.0   # R$/dia — abaixo disso é warning

# % do burn rate (por categoria) que dispara notificação
_BURN_WARN_PCT   = 0.70   # 70% do orçamento já consumido
_BURN_CRIT_PCT   = 0.90   # 90% → CRITICAL

# Score improvement mínimo para notificar
_SCORE_MIN_DELTA = 2.0

# Progresso de meta para notificar (%, marcos)
_GOAL_MILESTONES = {25.0, 50.0, 75.0, 100.0}
_GOAL_MILESTONE_TOLERANCE = 5.0   # ± 5 p.p. ao redor do marco


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATACLASSES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class Notification:
    """
    Uma notificação proativa gerada pelo sistema.

    Attributes:
        id:              UUID único da notificação
        type:            Tipo (BURN_RATE_HIGH, ANOMALY_DETECTED, ...)
        priority:        CRITICAL | WARNING | INFO
        title:           Título curto (≤ 60 chars)
        message:         Mensagem completa em PT-BR
        generated_at:    Timestamp de geração (UTC)
        metadata:        Dados extras para ação (ex: category, amount)
        action_hint:     Sugestão de ação (ex: "Reduza gastos em restaurante")
    """
    id: str
    type: str
    priority: NotificationPriority
    title: str
    message: str
    generated_at: datetime
    metadata: dict = field(default_factory=dict)
    action_hint: str = ""

    def to_dict(self) -> dict:
        return {
            "id":           self.id,
            "type":         self.type,
            "priority":     self.priority,
            "title":        self.title,
            "message":      self.message,
            "generated_at": self.generated_at.isoformat(),
            "metadata":     self.metadata,
            "action_hint":  self.action_hint,
        }


@dataclass
class BurnRateCategoryInput:
    """Dados de burn rate de uma categoria para gerador de notificação."""
    category: str
    spent_so_far: float
    monthly_budget: float
    pct_consumed: float     # 0.0–1.0+
    current_day: int


@dataclass
class AnomalyInput:
    """Dados de uma anomalia de gasto."""
    merchant: str
    amount: float
    factor: float           # quantas vezes acima do padrão
    anomaly_type: str       # "NEW_MERCHANT" | "UNUSUAL_AMOUNT" | "LATE_NIGHT" ...
    description: str


@dataclass
class SubscriptionChangeInput:
    """Dados de mudança de assinatura."""
    merchant: str
    old_amount: float
    new_amount: float
    pct_change: float       # (new - old) / old


@dataclass
class CardOpportunityInput:
    """Dados de oportunidade de cartão."""
    card_name: str
    monthly_gain_missed: float   # R$/mês que o usuário "deixou na mesa"
    reason: str


@dataclass
class WaiverAlertInput:
    """Dados de alerta de isenção de anuidade."""
    card_name: str
    amount_needed: float    # R$ restantes para isentar
    daily_spend_needed: float


@dataclass
class TransferPromoInput:
    """Dados de promoção de transferência de pontos."""
    from_program: str
    to_program: str
    bonus_pct: float        # ex: 0.50 = +50%
    end_date: str           # "YYYY-MM-DD"
    user_points: int


@dataclass
class ScoreChangeInput:
    """Dados de mudança no health score."""
    old_score: float
    new_score: float
    delta: float


@dataclass
class GoalProgressInput:
    """Dados de progresso de uma meta financeira."""
    goal_name: str
    goal_id: str
    pct_complete: float     # 0–100
    remaining_amount: float
    target_date: Optional[str] = None


@dataclass
class SafeToSpendInput:
    """Dados do safe-to-spend."""
    daily_safe_amount: float
    monthly_safe_amount: float


@dataclass
class LifeEventInput:
    """Evento de vida detectado pelo LifeEventsDetector."""
    event: str           # "new_baby" | "home_change" | "wedding" | "new_education" | "income_increase" | "income_drop"
    confidence: float    # 0.0–1.0
    trigger_action: str  # ação definida no detector


@dataclass
class FeeDeltaInput:
    """Tarifa que aumentou vs. mês anterior (detectada em bank_fee_history)."""
    bank_name: str
    fee_type: str       # FeeType.value — ex: "TARIFA_MANUTENCAO"
    old_amount: float   # valor cobrado no mês anterior (R$)
    new_amount: float   # valor cobrado no mês atual (R$)
    delta_pct: float    # (new - old) / old — ex: 0.15 = +15%


@dataclass
class NotificationContext:
    """
    Contexto completo para geração de notificações proativas.

    Todos os campos são opcionais — preencha apenas os dados disponíveis.
    Os geradores são ativados automaticamente quando os dados relevantes
    estão presentes.
    """
    # Burn rate por categoria (lista de categorias com ritmo alto)
    burn_rate_categories: list[BurnRateCategoryInput] = field(default_factory=list)

    # Anomalias de gasto detectadas
    anomalies: list[AnomalyInput] = field(default_factory=list)

    # Assinaturas que aumentaram
    subscription_changes: list[SubscriptionChangeInput] = field(default_factory=list)

    # Oportunidade de cartão perdida
    card_opportunities: list[CardOpportunityInput] = field(default_factory=list)

    # Alertas de isenção de anuidade
    waiver_alerts: list[WaiverAlertInput] = field(default_factory=list)

    # Promoção de transferência de pontos
    transfer_promos: list[TransferPromoInput] = field(default_factory=list)

    # Variação do health score
    score_change: Optional[ScoreChangeInput] = None

    # Progresso de metas ativas
    goal_progress: list[GoalProgressInput] = field(default_factory=list)

    # Safe-to-spend atual
    safe_to_spend: Optional[SafeToSpendInput] = None

    # Eventos de vida detectados pelo LifeEventsDetector
    life_events: list[LifeEventInput] = field(default_factory=list)

    # Tarifas que aumentaram vs. mês anterior (detectadas em bank_fee_history)
    fee_deltas: list[FeeDeltaInput] = field(default_factory=list)

    # Dia do mês atual (para contexto em mensagens)
    current_day: int = 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GERADORES DE NOTIFICAÇÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _new_id() -> str:
    return str(uuid.uuid4())[:8]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def generate_burn_rate_notifications(
    categories: list[BurnRateCategoryInput],
) -> list[Notification]:
    """
    BURN_RATE_HIGH — alerta quando categoria consumiu >70% do orçamento
    antes do fim do mês.

    Prioridade:
        CRITICAL se pct_consumed ≥ 90%
        WARNING  se pct_consumed ≥ 70%
    """
    notes: list[Notification] = []
    for cat in categories:
        pct = cat.pct_consumed
        if pct < _BURN_WARN_PCT:
            continue

        priority: NotificationPriority = "CRITICAL" if pct >= _BURN_CRIT_PCT else "WARNING"
        pct_display = int(pct * 100)
        cat_label = cat.category.replace("_", " ").title()
        day = cat.current_day

        overshoot = cat.spent_so_far - cat.monthly_budget if pct > 1.0 else 0.0
        if pct > 1.0:
            title = f"⛔ Orçamento de {cat_label} estourado"
            message = (
                f"Você gastou R${cat.spent_so_far:,.0f} em {cat_label} — "
                f"R${overshoot:,.0f} acima do orçamento de R${cat.monthly_budget:,.0f}."
            )
            action_hint = f"Evite gastos em {cat_label} pelo resto do mês."
        else:
            title = f"⚠️ {pct_display}% do orçamento de {cat_label} usado"
            message = (
                f"Você já gastou {pct_display}% do orçamento de {cat_label} "
                f"(R${cat.spent_so_far:,.0f} de R${cat.monthly_budget:,.0f}) "
                f"no dia {day}."
            )
            remaining = cat.monthly_budget - cat.spent_so_far
            action_hint = f"Restam R${remaining:,.0f} até o fim do mês para {cat_label}."

        notes.append(Notification(
            id=_new_id(),
            type="BURN_RATE_HIGH",
            priority=priority,
            title=title,
            message=message,
            generated_at=_now(),
            metadata={
                "category": cat.category,
                "spent": round(cat.spent_so_far, 2),
                "budget": round(cat.monthly_budget, 2),
                "pct_consumed": round(pct * 100, 1),
                "day": day,
            },
            action_hint=action_hint,
        ))

    return notes


def generate_anomaly_notifications(
    anomalies: list[AnomalyInput],
    max_alerts: int = 3,
) -> list[Notification]:
    """
    ANOMALY_DETECTED — gasto incomum detectado.
    """
    notes: list[Notification] = []
    for anomaly in anomalies[:max_alerts]:
        factor_str = f"{anomaly.factor:.1f}x"
        merchant_label = anomaly.merchant.title()
        priority: NotificationPriority = "WARNING" if anomaly.factor < 3 else "CRITICAL"

        notes.append(Notification(
            id=_new_id(),
            type="ANOMALY_DETECTED",
            priority=priority,
            title=f"🔍 Gasto incomum em {merchant_label}",
            message=(
                f"Gasto de R${anomaly.amount:,.0f} em {merchant_label} — "
                f"{factor_str} acima do seu padrão habitual."
            ),
            generated_at=_now(),
            metadata={
                "merchant":     anomaly.merchant,
                "amount":       round(anomaly.amount, 2),
                "factor":       round(anomaly.factor, 2),
                "anomaly_type": anomaly.anomaly_type,
            },
            action_hint="Verifique se a compra foi reconhecida.",
        ))

    return notes


def generate_subscription_increase_notifications(
    changes: list[SubscriptionChangeInput],
) -> list[Notification]:
    """
    SUBSCRIPTION_INCREASE — assinatura que ficou mais cara.
    """
    notes: list[Notification] = []
    for change in changes:
        if change.new_amount <= change.old_amount:
            continue
        merchant = change.merchant.title()
        pct = int(change.pct_change * 100)
        annual_extra = (change.new_amount - change.old_amount) * 12

        notes.append(Notification(
            id=_new_id(),
            type="SUBSCRIPTION_INCREASE",
            priority="WARNING",
            title=f"📈 {merchant} ficou +{pct}% mais caro",
            message=(
                f"{merchant} aumentou de R${change.old_amount:,.2f} "
                f"para R${change.new_amount:,.2f}/mês (+{pct}%). "
                f"Isso representa R${annual_extra:,.0f} a mais por ano."
            ),
            generated_at=_now(),
            metadata={
                "merchant":       change.merchant,
                "old_amount":     round(change.old_amount, 2),
                "new_amount":     round(change.new_amount, 2),
                "pct_change":     round(change.pct_change * 100, 1),
                "annual_extra":   round(annual_extra, 2),
            },
            action_hint=f"Vale verificar se ainda usa o {merchant} e se o aumento justifica a continuidade.",
        ))

    return notes


def generate_card_opportunity_notifications(
    opportunities: list[CardOpportunityInput],
) -> list[Notification]:
    """
    CARD_OPPORTUNITY — usuário está perdendo cashback/pontos ao usar cartão errado.
    """
    notes: list[Notification] = []
    for opp in opportunities[:2]:   # máx. 2 cartões por vez
        annual_missed = opp.monthly_gain_missed * 12
        notes.append(Notification(
            id=_new_id(),
            type="CARD_OPPORTUNITY",
            priority="INFO",
            title=f"💳 Oportunidade: {opp.card_name}",
            message=(
                f"Nos últimos 3 meses você deixou de ganhar "
                f"R${opp.monthly_gain_missed:,.0f}/mês — "
                f"R${annual_missed:,.0f}/ano — com o {opp.card_name}. "
                f"{opp.reason}"
            ),
            generated_at=_now(),
            metadata={
                "card_name":            opp.card_name,
                "monthly_gain_missed":  round(opp.monthly_gain_missed, 2),
                "annual_missed":        round(annual_missed, 2),
            },
            action_hint=f"Considere usar o {opp.card_name} nas categorias onde ele pontua melhor.",
        ))

    return notes


def generate_waiver_alert_notifications(
    waiver_alerts: list[WaiverAlertInput],
) -> list[Notification]:
    """
    WAIVER_ALERT — faltam R$ X para isentar a anuidade.
    """
    notes: list[Notification] = []
    for alert in waiver_alerts:
        notes.append(Notification(
            id=_new_id(),
            type="WAIVER_ALERT",
            priority="INFO",
            title=f"🎯 Faltam R${alert.amount_needed:,.0f} para isentar {alert.card_name}",
            message=(
                f"Faltam R${alert.amount_needed:,.0f} em gastos para você "
                f"isentar a anuidade do {alert.card_name}. "
                f"Gaste mais R${alert.daily_spend_needed:,.0f}/dia até o fim do mês."
            ),
            generated_at=_now(),
            metadata={
                "card_name":           alert.card_name,
                "amount_needed":       round(alert.amount_needed, 2),
                "daily_spend_needed":  round(alert.daily_spend_needed, 2),
            },
            action_hint=f"Concentre seus gastos no {alert.card_name} até atingir o threshold de isenção.",
        ))

    return notes


def generate_transfer_promo_notifications(
    promos: list[TransferPromoInput],
) -> list[Notification]:
    """
    TRANSFER_PROMO — transferência de pontos com bônus.
    """
    notes: list[Notification] = []
    for promo in promos:
        bonus_pct = int(promo.bonus_pct * 100)
        equivalent = int(promo.user_points * (1 + promo.bonus_pct))
        notes.append(Notification(
            id=_new_id(),
            type="TRANSFER_PROMO",
            priority="INFO",
            title=f"🎁 Bônus +{bonus_pct}%: {promo.from_program} → {promo.to_program}",
            message=(
                f"{promo.from_program} → {promo.to_program} com +{bonus_pct}% de bônus "
                f"até {promo.end_date}. Seus {promo.user_points:,} pontos virariam "
                f"{equivalent:,} pontos em {promo.to_program}."
            ),
            generated_at=_now(),
            metadata={
                "from_program": promo.from_program,
                "to_program":   promo.to_program,
                "bonus_pct":    bonus_pct,
                "end_date":     promo.end_date,
                "user_points":  promo.user_points,
                "equivalent":   equivalent,
            },
            action_hint=f"Transfira antes de {promo.end_date} para aproveitar o bônus.",
        ))

    return notes


def generate_score_improved_notification(
    change: Optional[ScoreChangeInput],
) -> list[Notification]:
    """
    SCORE_IMPROVED — health score subiu.
    """
    if change is None:
        return []
    if abs(change.delta) < _SCORE_MIN_DELTA:
        return []

    direction = "subiu" if change.delta > 0 else "caiu"
    emoji = "📈" if change.delta > 0 else "📉"
    priority: NotificationPriority = "INFO" if change.delta > 0 else "WARNING"

    return [Notification(
        id=_new_id(),
        type="SCORE_IMPROVED",
        priority=priority,
        title=f"{emoji} Score financeiro {direction}!",
        message=(
            f"Seu score financeiro {direction} de {change.old_score:.0f} "
            f"para {change.new_score:.0f} "
            f"({'+' if change.delta > 0 else ''}{change.delta:.0f} pontos). "
            + ("Parabéns pelo progresso! 🎉" if change.delta > 0 else "Atenção com os gastos recentes.")
        ),
        generated_at=_now(),
        metadata={
            "old_score": round(change.old_score, 1),
            "new_score": round(change.new_score, 1),
            "delta":     round(change.delta, 1),
        },
        action_hint="" if change.delta > 0 else "Revise seus gastos dos últimos 30 dias.",
    )]


def generate_goal_progress_notifications(
    goals: list[GoalProgressInput],
) -> list[Notification]:
    """
    GOAL_PROGRESS — meta atingiu marco de 25%, 50%, 75% ou 100%.
    """
    notes: list[Notification] = []
    for goal in goals:
        pct = goal.pct_complete
        # Verifica se pct está próximo de algum marco
        near_milestone = next(
            (m for m in _GOAL_MILESTONES
             if abs(pct - m) <= _GOAL_MILESTONE_TOLERANCE),
            None
        )
        if near_milestone is None:
            continue

        if near_milestone == 100.0:
            title = f"🏆 Meta '{goal.goal_name}' concluída!"
            message = f"Parabéns! Você atingiu a meta '{goal.goal_name}'! 🎉"
            priority: NotificationPriority = "INFO"
            action_hint = ""
        else:
            title = f"🎯 {int(near_milestone)}% da meta '{goal.goal_name}'"
            message = (
                f"A meta '{goal.goal_name}' está {pct:.0f}% concluída. "
                f"Faltam R${goal.remaining_amount:,.0f} para o objetivo."
            )
            if goal.target_date:
                message += f" Prazo: {goal.target_date}."
            priority = "INFO"
            action_hint = f"Continue contribuindo para atingir sua meta!"

        notes.append(Notification(
            id=_new_id(),
            type="GOAL_PROGRESS",
            priority=priority,
            title=title,
            message=message,
            generated_at=_now(),
            metadata={
                "goal_id":          goal.goal_id,
                "goal_name":        goal.goal_name,
                "pct_complete":     round(pct, 1),
                "remaining_amount": round(goal.remaining_amount, 2),
                "milestone":        near_milestone,
            },
            action_hint=action_hint,
        ))

    return notes


def generate_safe_to_spend_low_notification(
    sts: Optional[SafeToSpendInput],
) -> list[Notification]:
    """
    SAFE_TO_SPEND_LOW — margem segura caiu abaixo do threshold.
    """
    if sts is None:
        return []

    daily = sts.daily_safe_amount

    if daily <= 0:
        return [Notification(
            id=_new_id(),
            type="SAFE_TO_SPEND_LOW",
            priority="CRITICAL",
            title="⛔ Sem margem disponível",
            message=(
                "Sua margem segura zerou. Todas as suas obrigações futuras "
                "comprometem 100% do saldo disponível. Evite qualquer gasto não essencial."
            ),
            generated_at=_now(),
            metadata={"daily_safe": 0.0, "monthly_safe": round(sts.monthly_safe_amount, 2)},
            action_hint="Priorize o pagamento de obrigações e corte gastos variáveis.",
        )]

    if daily <= _LOW_STS_DAILY_ABS:
        priority = "CRITICAL"
        title = f"⛔ Margem segura: apenas R${daily:,.0f}/dia"
        message = (
            f"Sua margem segura para gastar caiu para R${daily:,.0f}/dia "
            f"(R${sts.monthly_safe_amount:,.0f}/mês). Cuidado com qualquer gasto elevado."
        )
        action_hint = "Evite gastos não essenciais esta semana."
    elif daily <= _WARN_STS_DAILY_ABS:
        priority = "WARNING"
        title = f"⚠️ Margem segura baixa: R${daily:,.0f}/dia"
        message = (
            f"Sua margem segura caiu para R${daily:,.0f}/dia — "
            f"abaixo do recomendado (R${_WARN_STS_DAILY_ABS:.0f}/dia). "
            f"Planeje seus gastos com cuidado."
        )
        action_hint = "Revise gastos variáveis nos próximos dias."
    else:
        return []

    return [Notification(
        id=_new_id(),
        type="SAFE_TO_SPEND_LOW",
        priority=priority,
        title=title,
        message=message,
        generated_at=_now(),
        metadata={
            "daily_safe":   round(daily, 2),
            "monthly_safe": round(sts.monthly_safe_amount, 2),
        },
        action_hint=action_hint,
    )]


_TARIFA_AUMENTO_MIN_DELTA_PCT = 0.10   # 10% — abaixo disso pode ser arredondamento


def generate_tarifa_aumento_notifications(
    fee_deltas: list[FeeDeltaInput],
) -> list[Notification]:
    """
    TARIFA_AUMENTO_UNILATERAL — tarifa aumentou ≥10% vs. mês anterior.

    Gerada quando bank_fee_history registra aumento em qualquer (bank_name, fee_type).
    Usado pelo NotificationEngine proativo (D4 — detecção de mudança unilateral).
    """
    notes: list[Notification] = []
    for delta in fee_deltas:
        if delta.delta_pct < _TARIFA_AUMENTO_MIN_DELTA_PCT:
            continue

        pct_display = int(delta.delta_pct * 100)
        fee_label = delta.fee_type.replace("_", " ").title()
        extra_annual = round((delta.new_amount - delta.old_amount) * 12, 2)

        notes.append(Notification(
            id=_new_id(),
            type="TARIFA_AUMENTO_UNILATERAL",
            priority="WARNING",
            title=f"⚠️ {delta.bank_name}: {fee_label} +{pct_display}%",
            message=(
                f"{delta.bank_name} aumentou sua {fee_label} de "
                f"R${delta.old_amount:.2f} para R${delta.new_amount:.2f} "
                f"(+{pct_display}%). Isso representa R${extra_annual:.2f} a mais por ano."
            ),
            generated_at=_now(),
            metadata={
                "bank_name":     delta.bank_name,
                "fee_type":      delta.fee_type,
                "old_amount":    round(delta.old_amount, 2),
                "new_amount":    round(delta.new_amount, 2),
                "delta_pct":     round(delta.delta_pct * 100, 1),
                "extra_annual":  extra_annual,
            },
            action_hint=(
                "O banco deve comunicar alterações de tarifa com 30 dias de antecedência "
                "(Resolução BACEN 3.919/2010). Verifique se houve aviso prévio."
            ),
        ))

    return notes


_LIFE_EVENT_CONFIG: dict[str, dict] = {
    "new_baby": {
        "priority": "WARNING",
        "title": "👶 Bebê detectado no extrato",
        "message": (
            "Identificamos gastos com bebê nos últimos 60 dias. "
            "A chegada de um filho muda bastante o orçamento — vale revisar metas, "
            "reservas e cobertura de seguro de vida."
        ),
        "action_hint": "Crie uma meta de reserva para despesas de bebê e revise seu orçamento mensal.",
    },
    "home_change": {
        "priority": "INFO",
        "title": "🏠 Possível mudança de residência detectada",
        "message": (
            "Detectamos gastos com mudança ou reforma recentemente. "
            "É um bom momento para revisar custos fixos, seguro residencial e orçamento de moradia."
        ),
        "action_hint": "Revise gastos fixos com moradia e verifique se seu seguro cobre a nova residência.",
    },
    "wedding": {
        "priority": "INFO",
        "title": "💍 Casamento detectado — hora de planejar a dois",
        "message": (
            "Detectamos gastos com cerimônia ou casamento. "
            "Finanças a dois têm dinâmicas diferentes — contas compartilhadas, metas conjuntas e objetivos alinhados."
        ),
        "action_hint": "Considere criar metas conjuntas e alinhar objetivos financeiros com seu parceiro(a).",
    },
    "new_education": {
        "priority": "INFO",
        "title": "🎓 Início de curso ou faculdade detectado",
        "message": (
            "Identificamos gastos com educação superior recentemente. "
            "Uma meta de médio prazo pode ajudar a planejar os próximos semestres sem comprometer o orçamento."
        ),
        "action_hint": "Crie uma meta para cobrir os próximos 12 meses de mensalidades.",
    },
    "income_increase": {
        "priority": "INFO",
        "title": "📈 Aumento de renda detectado",
        "message": (
            "Sua renda recente está acima do histórico em mais de 20%. "
            "É o momento ideal para direcionar o incremento para investimentos ou metas antes de se acostumar a gastar mais."
        ),
        "action_hint": "Invista o aumento antes que ele vire novo custo fixo.",
    },
    "income_drop": {
        "priority": "CRITICAL",
        "title": "📉 Queda de renda detectada",
        "message": (
            "Sua renda recente caiu mais de 20% em relação ao histórico. "
            "Priorize a reserva de emergência e revise gastos fixos imediatamente."
        ),
        "action_hint": "Corte gastos discricionários e garanta pelo menos 3 meses de reserva de emergência.",
    },
}

# Confiança mínima para converter evento de vida em notificação
_LIFE_EVENT_MIN_CONFIDENCE = 0.60


def generate_life_event_notifications(
    events: list[LifeEventInput],
) -> list[Notification]:
    """
    LIFE_EVENT — evento de vida de alto impacto financeiro detectado.

    Converte eventos do LifeEventsDetector em notificações proativas.
    Filtra por confidence >= 0.60 para evitar falsos positivos.
    Cada tipo de evento aparece no máximo 1x (o de maior confiança).
    """
    seen: set[str] = set()
    notes: list[Notification] = []

    # Ordena por confiança descendente para garantir que, se houver duplicata,
    # o evento de maior confiança seja o que gera notificação.
    sorted_events = sorted(events, key=lambda e: e.confidence, reverse=True)

    for evt in sorted_events:
        if evt.confidence < _LIFE_EVENT_MIN_CONFIDENCE:
            continue
        if evt.event in seen:
            continue
        seen.add(evt.event)

        cfg = _LIFE_EVENT_CONFIG.get(evt.event)
        if cfg is None:
            continue

        confidence_pct = int(evt.confidence * 100)
        notes.append(Notification(
            id=_new_id(),
            type="LIFE_EVENT",
            priority=cfg["priority"],
            title=cfg["title"],
            message=cfg["message"],
            generated_at=_now(),
            metadata={
                "event":          evt.event,
                "confidence":     evt.confidence,
                "trigger_action": evt.trigger_action,
                "confidence_pct": confidence_pct,
            },
            action_hint=cfg["action_hint"],
        ))

    return notes


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ORQUESTRADOR PRINCIPAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Ordem de prioridade para sort
_PRIORITY_ORDER: dict[str, int] = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}


class ProactiveNotifier:
    """
    Orquestrador de notificações proativas (MX.3).

    Recebe um NotificationContext com todos os dados calculados e
    delega para cada gerador especializado. Retorna lista de
    Notification ordenadas por prioridade (CRITICAL → WARNING → INFO).

    Example:
        >>> ctx = NotificationContext(
        ...     burn_rate_categories=[BurnRateCategoryInput(
        ...         category="alimentacao",
        ...         spent_so_far=850.0,
        ...         monthly_budget=1000.0,
        ...         pct_consumed=0.85,
        ...         current_day=15,
        ...     )],
        ...     safe_to_spend=SafeToSpendInput(daily_safe_amount=45.0, monthly_safe_amount=1350.0),
        ... )
        >>> notes = ProactiveNotifier().generate(ctx)
        >>> notes[0].type
        'SAFE_TO_SPEND_LOW'   # CRITICAL primeiro
    """

    def generate(self, ctx: NotificationContext) -> list[Notification]:
        """
        Gera todas as notificações aplicáveis para o contexto fornecido.

        Executores são determinísticos: o mesmo contexto sempre produz as
        mesmas notificações. Não há estado interno nem efeitos colaterais.

        Args:
            ctx: NotificationContext com dados calculados de diversas fontes.

        Returns:
            Lista de Notification ordenada CRITICAL → WARNING → INFO.
            Cada tipo de notificação pode aparecer múltiplas vezes se
            múltiplas categorias/metas/etc. forem relevantes.
        """
        notes: list[Notification] = []

        # 1. Burn rate por categoria
        notes.extend(generate_burn_rate_notifications(ctx.burn_rate_categories))

        # 2. Anomalias de gasto
        notes.extend(generate_anomaly_notifications(ctx.anomalies))

        # 3. Assinaturas que ficaram mais caras
        notes.extend(generate_subscription_increase_notifications(ctx.subscription_changes))

        # 4. Oportunidade de cartão
        notes.extend(generate_card_opportunity_notifications(ctx.card_opportunities))

        # 5. Alerta de isenção de anuidade
        notes.extend(generate_waiver_alert_notifications(ctx.waiver_alerts))

        # 6. Promoção de transferência de pontos
        notes.extend(generate_transfer_promo_notifications(ctx.transfer_promos))

        # 7. Variação do health score
        notes.extend(generate_score_improved_notification(ctx.score_change))

        # 8. Progresso de metas
        notes.extend(generate_goal_progress_notifications(ctx.goal_progress))

        # 9. Safe-to-spend baixo
        notes.extend(generate_safe_to_spend_low_notification(ctx.safe_to_spend))

        # 10. Eventos de vida
        notes.extend(generate_life_event_notifications(ctx.life_events))

        # 11. Tarifas aumentadas unilateralmente (D4 — proativo via scheduler)
        notes.extend(generate_tarifa_aumento_notifications(ctx.fee_deltas))

        # Ordenar por prioridade
        notes.sort(key=lambda n: _PRIORITY_ORDER.get(n.priority, 3))

        logger.info(
            "ProactiveNotifier | geradas=%d (CRITICAL=%d, WARNING=%d, INFO=%d)",
            len(notes),
            sum(1 for n in notes if n.priority == "CRITICAL"),
            sum(1 for n in notes if n.priority == "WARNING"),
            sum(1 for n in notes if n.priority == "INFO"),
        )

        return notes


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# __all__
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
    "LifeEventInput",
    "generate_burn_rate_notifications",
    "generate_anomaly_notifications",
    "generate_subscription_increase_notifications",
    "generate_card_opportunity_notifications",
    "generate_waiver_alert_notifications",
    "generate_transfer_promo_notifications",
    "generate_score_improved_notification",
    "generate_goal_progress_notifications",
    "generate_safe_to_spend_low_notification",
    "generate_life_event_notifications",
    "FeeDeltaInput",
    "generate_tarifa_aumento_notifications",
]
