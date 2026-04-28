"""
app/notifications/relevance_filter.py — Filtro de Relevância e Confiança (MX.3)

Responsabilidade:
    Recebe a lista bruta de notificações do ProactiveNotifier e descarta
    aquelas que não atingem os critérios de relevância e confiança por tipo.

Etapas em ordem:
    1. Threshold de qualidade por tipo    — elimina sinal fraco / ruído,
                                            com thresholds relativos à renda
    1b. Deduplicação de GOAL_PROGRESS     — evita dois alertas do mesmo marco/meta
    2. Cap por tipo (máx. 2 por tipo)     — evita flood de um único assunto
    3. Cap global                         — CRITICAL ilimitado; WARNING+INFO
                                            limitados a _MAX_NON_CRITICAL slots

Regras de proteção:
    - Notificações CRITICAL nunca são descartadas em nenhuma etapa.
    - Thresholds escalam com a renda do usuário via _income_scaled():
      mesmo evento é ruído para quem ganha R$15k e relevante para quem ganha R$2k.
"""

from __future__ import annotations

import logging
from typing import Callable

from app.notifications.notifier import Notification

logger = logging.getLogger(__name__)


# ── Helpers de escala por renda ───────────────────────────────────────────────

def _income_scaled(income: float, pct: float, floor: float, cap: float) -> float:
    """
    Retorna income × pct limitado a [floor, cap].
    Se income <= 0, retorna floor (threshold conservador).

    Exemplos com pct=0.02, floor=30, cap=200:
        income=2k  → max(30,  40) = 40
        income=5k  → max(30, 100) = 100
        income=15k → min(300, 200) = 200
    """
    if income <= 0:
        return floor
    return max(floor, min(cap, income * pct))


# ── Per-type quality thresholds ───────────────────────────────────────────────
# Assinatura: (Notification, monthly_income: float) -> bool

def _burn_rate_relevant(n: Notification, income: float) -> bool:
    # Percentual do orçamento consumido — já é relativo, sem ajuste de renda
    return n.metadata.get("pct_consumed", 0.0) >= 75.0


def _anomaly_relevant(n: Notification, income: float) -> bool:
    # Fator mínimo: ≥2.5× o padrão (sinal objetivo, independente de renda)
    # Valor mínimo: escala com renda — 2% da renda mensal, entre R$30 e R$200
    factor = n.metadata.get("factor", 0.0)
    amount = n.metadata.get("amount", 0.0)
    min_amount = _income_scaled(income, 0.02, 30.0, 200.0)
    return factor >= 2.5 and amount >= min_amount


def _subscription_relevant(n: Notification, income: float) -> bool:
    # Reajuste relevante por percentual (≥15%) OU valor absoluto relativo à renda
    # Incremento absoluto: 0.2% da renda, entre R$5 e R$30
    pct = n.metadata.get("pct_change", 0.0)
    new = n.metadata.get("new_amount", 0.0)
    old = n.metadata.get("old_amount", 0.0)
    min_abs = _income_scaled(income, 0.002, 5.0, 30.0)
    return pct >= 15.0 or (new - old) >= min_abs


def _card_opportunity_relevant(n: Notification, income: float) -> bool:
    # Ganho perdido mínimo: 0.5% da renda mensal, entre R$15 e R$100
    min_gain = _income_scaled(income, 0.005, 15.0, 100.0)
    return n.metadata.get("monthly_gain_missed", 0.0) >= min_gain


def _waiver_relevant(n: Notification, income: float) -> bool:
    # Meta atingível:
    #   - diária ≤ 5% da renda mensal (entre R$100/dia e R$400/dia)
    #   - total restante ≤ R$3.000 (evita alertas de isenção inviáveis)
    daily  = n.metadata.get("daily_spend_needed", 9_999.0)
    amount = n.metadata.get("amount_needed", 0.0)
    max_daily = _income_scaled(income, 0.05, 100.0, 400.0)
    return amount > 0 and daily <= max_daily and amount <= 3_000.0


def _transfer_promo_relevant(n: Notification, income: float) -> bool:
    # Bônus ≥ 20% e pontos mínimos — o valor dos pontos já é relativo
    bonus  = n.metadata.get("bonus_pct", 0.0)
    points = n.metadata.get("user_points", 0)
    return bonus >= 20 and points >= 1_000


def _score_relevant(n: Notification, income: float) -> bool:
    # Delta mínimo de 5 pontos — score é 0-100, income-neutral
    return abs(n.metadata.get("delta", 0.0)) >= 5.0


def _goal_relevant(n: Notification, income: float) -> bool:
    # Milestones de 25% são muito cedo; só 50%, 75% e 100%
    return n.metadata.get("milestone", 0.0) in {50.0, 75.0, 100.0}


def _safe_to_spend_relevant(n: Notification, income: float) -> bool:
    # Sempre relevante: o gerador já aplica thresholds rígidos
    return True


def _life_event_relevant(n: Notification, income: float) -> bool:
    # Confiança mínima de 0.75 — falso positivo de "bebê detectado" é crítico
    return n.metadata.get("confidence", 0.0) >= 0.75


_TYPE_FILTERS: dict[str, Callable[[Notification, float], bool]] = {
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

# ── Caps ──────────────────────────────────────────────────────────────────────

_MAX_NON_CRITICAL = 4   # slots para WARNING + INFO (CRITICAL é ilimitado)
_MAX_PER_TYPE     = 2   # máx. por tipo (não se aplica a CRITICAL)


# ── Classe principal ──────────────────────────────────────────────────────────

class NotificationRelevanceFilter:
    """
    Filtro de relevância e confiança para notificações proativas.

    Uso:
        raw = ProactiveNotifier().generate(ctx)
        filtered = NotificationRelevanceFilter().filter(raw, monthly_income=income)

    A lista de entrada deve estar ordenada CRITICAL → WARNING → INFO
    (ProactiveNotifier já garante isso). O filtro preserva essa ordem.
    """

    def filter(  # noqa: A003
        self,
        notifications: list[Notification],
        monthly_income: float = 0.0,
    ) -> list[Notification]:
        # ── Etapa 1: threshold de qualidade por tipo ──────────────────
        after_quality: list[Notification] = []
        dropped_quality = 0
        for n in notifications:
            fn = _TYPE_FILTERS.get(n.type)
            if fn is None or fn(n, monthly_income):
                after_quality.append(n)
            else:
                dropped_quality += 1

        # ── Etapa 1b: deduplicação de GOAL_PROGRESS ───────────────────
        # O gerador pode emitir dois alertas do mesmo marco para a mesma meta
        # quando pct_complete cai dentro da tolerância ±5 p.p.
        seen_goal_milestones: set[tuple[str, float]] = set()
        deduped: list[Notification] = []
        dropped_goal_dup = 0
        for n in after_quality:
            if n.type == "GOAL_PROGRESS":
                key = (n.metadata.get("goal_id", ""), n.metadata.get("milestone", 0.0))
                if key in seen_goal_milestones:
                    dropped_goal_dup += 1
                    continue
                seen_goal_milestones.add(key)
            deduped.append(n)
        after_quality = deduped

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

        # ── Etapa 3: cap global (CRITICAL ilimitado) ──────────────────
        # CRITICAL passa sempre — usuário em crise precisa ver todos os alertas.
        # WARNING + INFO preenchem os _MAX_NON_CRITICAL slots restantes.
        critical_notes = [n for n in after_type_cap if n.priority == "CRITICAL"]
        non_critical   = [n for n in after_type_cap if n.priority != "CRITICAL"]

        after_global   = critical_notes + non_critical[:_MAX_NON_CRITICAL]
        dropped_global = max(0, len(non_critical) - _MAX_NON_CRITICAL)

        total_dropped = dropped_quality + dropped_goal_dup + dropped_type + dropped_global
        if total_dropped > 0:
            logger.info(
                "NotificationRelevanceFilter | income=R$%.0f in=%d → out=%d "
                "(quality=%d goal_dup=%d type_cap=%d global_cap=%d)",
                monthly_income,
                len(notifications),
                len(after_global),
                dropped_quality,
                dropped_goal_dup,
                dropped_type,
                dropped_global,
            )

        return after_global
