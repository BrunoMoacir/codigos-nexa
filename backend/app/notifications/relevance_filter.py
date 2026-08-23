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
    - Thresholds escalam com a renda do usuário via _income_scaled():
      mesmo evento é ruído para quem ganha R$15k e relevante para quem ganha R$2k.
    - CRITICAL é imune aos caps (etapas 2 e 3) e aos portões de RELEVÂNCIA da
      etapa 1 — mas nunca aos de VALIDADE. Ver a distinção abaixo.

Duas naturezas de portão na etapa 1, e a diferença importa:

    RELEVÂNCIA — "isso é grande o bastante para te interromper?"
        Valor da anomalia, ganho do cartão, reajuste da assinatura. São
        julgamentos de magnitude, quase todos escalados pela renda. Se o
        gerador já decidiu que a nota é CRITICAL, magnitude deixa de ser a
        pergunta: CRITICAL passa por cima.

    VALIDADE — "esse sinal é real?"
        Confiança do evento de vida, marco de meta, janela do prazo fiscal.
        Uma nota CRITICAL que não passa num portão desses não é urgente, é
        malformada — e um falso "detectamos um bebê" fica PIOR alto.
        CRITICAL nunca é imune a esses.

A etapa 1 não fazia distinção nenhuma e também não olhava prioridade: uma
anomalia CRITICAL de R$ 150 (fator 4,2× — o gerador marca CRITICAL a partir
de 3×) era descartada para quem ganha R$ 15 mil exatamente como um WARNING,
enquanto as etapas 2 e 3 checavam `n.priority == "CRITICAL"` e a protegiam.
A invariante estava escrita em três lugares e implementada em dois terços.
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


def _anomaly_valid(n: Notification, income: float) -> bool:
    # VALIDADE: é mesmo uma anomalia? ≥2.5× o padrão. Independente de renda
    # e de prioridade — abaixo disso o sinal não se sustenta.
    return n.metadata.get("factor", 0.0) >= 2.5


def _anomaly_relevant(n: Notification, income: float) -> bool:
    # RELEVÂNCIA: vale te interromper? 2% da renda mensal, entre R$30 e R$200.
    min_amount = _income_scaled(income, 0.02, 30.0, 200.0)
    return n.metadata.get("amount", 0.0) >= min_amount


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


def _savings_below_cdi_relevant(n: Notification, income: float) -> bool:
    # O gerador já filtra por severity >= MEDIUM; aqui só barra perda irrisória
    return n.metadata.get("estimated_loss_annual_brl", 0.0) >= 30.0


def _idle_money_relevant(n: Notification, income: float) -> bool:
    # Ganho mensal mínimo na troca: 0.2% da renda, entre R$5 e R$50
    min_gain = _income_scaled(income, 0.002, 5.0, 50.0)
    return n.metadata.get("top_gain_monthly_brl", 0.0) >= min_gain


def _fiscal_season_relevant(n: Notification, income: float) -> bool:
    # Prazo é prazo: obrigação legal é sempre relevante. Eventos de
    # planejamento (restituição, 13º, FGTS) só dentro de 45 dias do deadline
    # — o gerador já garante isso pela janela do calendário.
    return n.metadata.get("days_until_deadline", 999) <= 45


def _challenge_relevant(n: Notification, income: float) -> bool:
    # Conclusão sempre vale card (é a recompensa); progresso exige ≥70%
    # — o gerador já filtra, aqui é cinto e suspensório.
    if n.type == "CHALLENGE_COMPLETED":
        return True
    return n.metadata.get("pct_progress", 0.0) >= 70.0


def _purchase_followup_relevant(n: Notification, income: float) -> bool:
    # Economia perdida mínima: 0.3% da renda, entre R$10 e R$80 — mesma
    # família de escala do CARD_OPPORTUNITY (é o primo retroativo dele)
    min_savings = _income_scaled(income, 0.003, 10.0, 80.0)
    return n.metadata.get("potential_savings_brl", 0.0) >= min_savings


# ── Portões de VALIDADE — o sinal é real? CRITICAL NUNCA é imune ─────────────
_VALIDITY_FILTERS: dict[str, Callable[[Notification, float], bool]] = {
    # Falso "detectamos um bebê" fica pior alto, não melhor.
    "LIFE_EVENT":          _life_event_relevant,
    # 25% não é marco; o produto notifica 50/75/100.
    "GOAL_PROGRESS":       _goal_relevant,
    "CHALLENGE_PROGRESS":  _challenge_relevant,
    # A oferta se qualifica ou não — não é questão de magnitude.
    "TRANSFER_PROMO":      _transfer_promo_relevant,
    # Fora da janela do calendário, o prazo não é notícia.
    "FISCAL_SEASON":       _fiscal_season_relevant,
    # É mesmo uma anomalia (≥2,5× o padrão)?
    "ANOMALY_DETECTED":    _anomaly_valid,
}

# ── Portões de RELEVÂNCIA — grande o bastante? CRITICAL passa por cima ───────
_RELEVANCE_FILTERS: dict[str, Callable[[Notification, float], bool]] = {
    "BURN_RATE_HIGH":        _burn_rate_relevant,
    "ANOMALY_DETECTED":      _anomaly_relevant,
    "SUBSCRIPTION_INCREASE": _subscription_relevant,
    "CARD_OPPORTUNITY":      _card_opportunity_relevant,
    "WAIVER_ALERT":          _waiver_relevant,
    "SCORE_IMPROVED":        _score_relevant,
    "SAFE_TO_SPEND_LOW":     _safe_to_spend_relevant,
    "SAVINGS_BELOW_CDI":     _savings_below_cdi_relevant,
    "IDLE_MONEY_DETECTED":   _idle_money_relevant,
    "CHALLENGE_COMPLETED":   _challenge_relevant,
    "PURCHASE_FOLLOWUP":     _purchase_followup_relevant,
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
        # ── Etapa 1: validade sempre; relevância só para não-CRITICAL ──
        after_quality: list[Notification] = []
        dropped_quality = 0
        for n in notifications:
            valida = _VALIDITY_FILTERS.get(n.type)
            if valida is not None and not valida(n, monthly_income):
                dropped_quality += 1
                continue

            if n.priority != "CRITICAL":
                relevante = _RELEVANCE_FILTERS.get(n.type)
                if relevante is not None and not relevante(n, monthly_income):
                    dropped_quality += 1
                    continue

            after_quality.append(n)

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
