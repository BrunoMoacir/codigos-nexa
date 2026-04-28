"""
app/notifications/relevance_filter.py — Filtro de Relevância e Confiança (MX.3)

Responsabilidade:
    Recebe a lista bruta de notificações do ProactiveNotifier e descarta
    aquelas que não atingem os critérios de relevância e confiança por tipo.

Etapas em ordem:
    1. Threshold de qualidade por tipo  — elimina sinal fraco / ruído
    2. Cap por tipo (máx. 2 por tipo)   — evita flood de um único assunto
    3. Cap global   (máx. 5 total)      — limita volume total ao usuário

Regras de proteção:
    - Notificações CRITICAL nunca são descartadas pelo cap por tipo.
    - O cap global é aplicado depois de todos os outros filtros, priorizando
      a ordem CRITICAL → WARNING → INFO (já garantida pelo ProactiveNotifier).
"""

from __future__ import annotations

import logging
from typing import Callable

from app.notifications.notifier import Notification

logger = logging.getLogger(__name__)


# ── Per-type quality thresholds ───────────────────────────────────────────────

def _burn_rate_relevant(n: Notification) -> bool:
    # Eleva o bar de 70% (gerador) para 75% para reduzir alertas prematuros
    return n.metadata.get("pct_consumed", 0.0) >= 75.0


def _anomaly_relevant(n: Notification) -> bool:
    # Exige anomalia significativa: ≥2.5× o padrão E valor mínimo de R$100
    factor = n.metadata.get("factor", 0.0)
    amount = n.metadata.get("amount", 0.0)
    return factor >= 2.5 and amount >= 100.0


def _subscription_relevant(n: Notification) -> bool:
    # Reajuste relevante: ≥15% de aumento OU incremento absoluto ≥ R$10/mês
    pct = n.metadata.get("pct_change", 0.0)    # já em %, ex: 15.0
    new = n.metadata.get("new_amount", 0.0)
    old = n.metadata.get("old_amount", 0.0)
    return pct >= 15.0 or (new - old) >= 10.0


def _card_opportunity_relevant(n: Notification) -> bool:
    # Só vale a pena notificar se o ganho perdido for ≥ R$30/mês
    return n.metadata.get("monthly_gain_missed", 0.0) >= 30.0


def _waiver_relevant(n: Notification) -> bool:
    # Alerta de isenção só faz sentido se a meta for alcançável (≤ R$400/dia)
    # e ainda houver valor restante
    daily = n.metadata.get("daily_spend_needed", 9_999.0)
    amount = n.metadata.get("amount_needed", 0.0)
    return amount > 0 and daily <= 400.0


def _transfer_promo_relevant(n: Notification) -> bool:
    # Promoção relevante: bônus ≥ 20% e usuário tem pontos suficientes (≥ 1 000)
    bonus = n.metadata.get("bonus_pct", 0.0)   # já em %, ex: 50
    points = n.metadata.get("user_points", 0)
    return bonus >= 20 and points >= 1_000


def _score_relevant(n: Notification) -> bool:
    # Eleva o bar de 2 (gerador) para 5 pontos — mudança pequena é ruído
    return abs(n.metadata.get("delta", 0.0)) >= 5.0


def _goal_relevant(n: Notification) -> bool:
    # Milestones de 25% são muito cedo para notificar; só 50%, 75% e 100%
    return n.metadata.get("milestone", 0.0) in {50.0, 75.0, 100.0}


def _safe_to_spend_relevant(n: Notification) -> bool:
    # Sempre relevante: o gerador já aplica thresholds rígidos (R$50/dia e R$100/dia)
    return True


def _life_event_relevant(n: Notification) -> bool:
    # Eleva o bar de 0.60 (gerador) para 0.75 — eventos de vida geram ação real,
    # falsos positivos são muito prejudiciais à confiança do usuário
    return n.metadata.get("confidence", 0.0) >= 0.75


_TYPE_FILTERS: dict[str, Callable[[Notification], bool]] = {
    "BURN_RATE_HIGH":        _burn_rate_relevant,
    "ANOMALY_DETECTED":      _anomaly_relevant,
    "SUBSCRIPTION_INCREASE": _subscription_relevant,
    "CARD_OPPORTUNITY":      _card_opportunity_relevant,
    "WAIVER_ALERT":          _waiver_relevant,
    "TRANSFER_PROMO":        _transfer_promo_relevant,
    "SCORE_IMPROVED":        _score_relevant,
    "GOAL_PROGRESS":         _goal_relevant,
    "SAFE_TO_SPEND_LOW":     _safe_to_spend_relevant,
    "LIFE_EVENT":            _life_event_relevant,
}

# ── Caps globais ──────────────────────────────────────────────────────────────

_MAX_TOTAL    = 5   # máx. notificações entregues ao usuário
_MAX_PER_TYPE = 2   # máx. por tipo (não se aplica a CRITICAL)


# ── Classe principal ──────────────────────────────────────────────────────────

class NotificationRelevanceFilter:
    """
    Filtro de relevância e confiança para notificações proativas.

    Uso:
        raw = ProactiveNotifier().generate(ctx)
        filtered = NotificationRelevanceFilter().filter(raw)

    A lista de entrada deve estar ordenada CRITICAL → WARNING → INFO
    (ProactiveNotifier já garante isso). O filtro preserva essa ordem.
    """

    def filter(self, notifications: list[Notification]) -> list[Notification]:  # noqa: A003
        # ── Etapa 1: threshold de qualidade por tipo ──────────────────
        after_quality: list[Notification] = []
        dropped_quality = 0
        for n in notifications:
            fn = _TYPE_FILTERS.get(n.type)
            if fn is None or fn(n):
                after_quality.append(n)
            else:
                dropped_quality += 1

        # ── Etapa 2: cap por tipo (CRITICAL é imune) ──────────────────
        type_counts: dict[str, int] = {}
        after_type_cap: list[Notification] = []
        dropped_type = 0
        for n in after_quality:
            if n.priority == "CRITICAL":
                after_type_cap.append(n)
                continue
            count = type_counts.get(n.type, 0)
            if count < _MAX_PER_TYPE:
                after_type_cap.append(n)
                type_counts[n.type] = count + 1
            else:
                dropped_type += 1

        # ── Etapa 3: cap global ───────────────────────────────────────
        after_global = after_type_cap[:_MAX_TOTAL]
        dropped_global = max(0, len(after_type_cap) - _MAX_TOTAL)

        total_dropped = dropped_quality + dropped_type + dropped_global
        if total_dropped > 0:
            logger.info(
                "NotificationRelevanceFilter | in=%d → out=%d "
                "(quality=%d type_cap=%d global_cap=%d)",
                len(notifications),
                len(after_global),
                dropped_quality,
                dropped_type,
                dropped_global,
            )

        return after_global
