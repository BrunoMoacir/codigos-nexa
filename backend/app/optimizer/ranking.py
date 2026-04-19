# app/optimizer/ranking.py
# CardRanking — ordena cartões por retorno ajustado por risco e elegibilidade
# Camada 3 — Motor Anti-Falsos-Positivos + Ranking (Card Optimizer v2.1)

from __future__ import annotations

import logging

from app.optimizer.models import BenefitTag, CardSimulationResult, LiquidityRisk
from app.optimizer.profiler import UserProfile

logger = logging.getLogger(__name__)

# Multiplicador aplicado ao net_gain por nível de risco de liquidez (v2.1)
# Substitui abordagem subtrativa anterior — alinhado com apply_liquidity_penalty da arquitetura
_LIQUIDITY_MULTIPLIER: dict[LiquidityRisk, float] = {
    LiquidityRisk.SAFE: 1.00,
    LiquidityRisk.WARNING: 0.90,   # −10%
    LiquidityRisk.HIGH: 0.60,      # −40%
    LiquidityRisk.CRITICAL: 0.20,  # −80%
}

# Thresholds de gasto mensal para bônus de benefícios específicos (BenefitViabilityFilter)
_INTL_SPEND_THRESHOLD = 500.0    # R$/mês — proxy para has_international_spend
_TRAVEL_SPEND_THRESHOLD = 800.0  # R$/mês — proxy para flights_per_year ≥ 4

# Bônus anuais adicionados ao score quando perfil valida o benefício
_INTL_BONUS = 200.0   # R$/ano
_LOUNGE_BONUS = 300.0  # R$/ano

# Se benefícios somados > 40% do ganho base, aplicar desconto de 15% (regra anti-FP)
_BENEFIT_DOMINANCE_THRESHOLD = 0.40
_BENEFIT_DOMINANCE_DISCOUNT = 0.85


class CardRanking:
    """
    Ordena CardSimulationResult pelo retorno ajustado por risco e elegibilidade.

    Algoritmo (v2.1 — multiplicativo):
        1. score = net_gain_expected × liquidity_multiplier
        2. benefits_bonus = bônus filtrados por BenefitViabilityFilter
           (com regra 40%: se bonus > 40% do ganho base → desconto 15%)
        3. score += benefits_bonus
        4. score *= confidence_penalty  (se confidence < 0.4)
        5. score *= eligibility_penalty (escalonado)

    Regra pós-sort:
        Se o 1º card tiver eligibility_score < 0.4 e houver outro com ≥ 0.6,
        promover o de maior elegibilidade para o topo.
    """

    def rank(
        self,
        results: list[CardSimulationResult],
        profile: UserProfile,
    ) -> list[CardSimulationResult]:
        """Retorna a lista ordenada por score (decrescente)."""
        if not results:
            return []

        scored = [(r, self._compute_score(r, profile)) for r in results]
        scored.sort(key=lambda x: x[1], reverse=True)
        ranked = [r for r, _ in scored]

        # Regra de elegibilidade mínima
        if ranked and ranked[0].eligibility_score < 0.4:
            next_eligible = next(
                (r for r in ranked[1:] if r.eligibility_score >= 0.6), None
            )
            if next_eligible:
                ranked.remove(next_eligible)
                ranked.insert(0, next_eligible)
                logger.info(
                    "Ranking: promovendo %s sobre %s (eligibility baixa no 1º)",
                    next_eligible.card_id,
                    ranked[1].card_id,
                )

        return ranked

    # ─── Score ────────────────────────────────────────────────────────────────

    def _compute_score(self, result: CardSimulationResult, profile: UserProfile) -> float:
        # 1. Liquidez: multiplicativo sobre o net_gain (v2.1 — antes era subtrativo)
        multiplier = _LIQUIDITY_MULTIPLIER.get(result.liquidity_risk, 1.0)
        score = result.net_gain_expected * multiplier

        # 2. BenefitViabilityFilter + ProfileAwareBenefitUtilization
        # Hard blocks: benefícios só contam se o perfil viabiliza o uso
        benefits_bonus = 0.0

        if (
            profile.international_spend_monthly > _INTL_SPEND_THRESHOLD
            and BenefitTag.INTERNACIONAL in result.benefit_tags
        ):
            benefits_bonus += _INTL_BONUS

        if (
            profile.travel_spend_monthly > _TRAVEL_SPEND_THRESHOLD
            and BenefitTag.LOUNGE in result.benefit_tags
        ):
            benefits_bonus += _LOUNGE_BONUS

        # Regra 40%: se benefícios dominam > 40% do ganho base, desconto de 15%
        # Previne que cartões premium com benefícios de luxo dominem ranking
        if benefits_bonus > 0 and result.net_gain_expected > 0:
            if benefits_bonus > _BENEFIT_DOMINANCE_THRESHOLD * result.net_gain_expected:
                benefits_bonus *= _BENEFIT_DOMINANCE_DISCOUNT

        score += benefits_bonus

        # 3. Penalidade de confiança (multiplicativa após bônus)
        if result.confidence_score < 0.4:
            score *= 0.5

        # 4. Penalidade de elegibilidade (multiplicativa, escalonada)
        if result.eligibility_score < 0.5:
            score *= 0.4
        elif result.eligibility_score < 0.7:
            score *= 0.75

        return score
