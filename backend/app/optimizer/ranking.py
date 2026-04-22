# app/optimizer/ranking.py
# CardRanking — ordena cartões por retorno ajustado por risco e elegibilidade
# Camada 3 — Motor Anti-Falsos-Positivos + Ranking (Card Optimizer v2.1)

from __future__ import annotations

import logging

from app.optimizer.constants import (
    INTL_SPEND_THRESHOLD as _INTL_SPEND_THRESHOLD,
    TRAVEL_SPEND_THRESHOLD as _TRAVEL_SPEND_THRESHOLD,
    INTL_RANKING_BONUS as _INTL_BONUS,
    LOUNGE_RANKING_BONUS as _LOUNGE_BONUS,
)
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

        # Bônus por cluster — ajusta relevância de benefícios ao estilo de vida
        cluster = getattr(profile, "lifestyle_cluster", "NAO_CLASSIFICADO")

        if cluster == "EXPLORADOR_GLOBAL":
            if BenefitTag.LOUNGE in result.benefit_tags or BenefitTag.TRAVEL in result.benefit_tags:
                benefits_bonus *= 1.25
                score = result.net_gain_expected * multiplier + benefits_bonus

        elif cluster == "URBANO_FOODIE":
            if BenefitTag.CASHBACK in result.benefit_tags:
                food_spend = profile.spend_by_category.get("Alimentação", 0)
                if food_spend > 500:
                    score += food_spend * 0.005

        elif cluster == "INVESTIDOR_CAUTELOSO":
            if result.annuity_effective > 500:
                score *= 0.90

        # 3. Penalidade de confiança (multiplicativa após bônus)
        if result.confidence_score < 0.4:
            score *= 0.5

        # 4. Penalidade de elegibilidade (multiplicativa, escalonada)
        if result.eligibility_score < 0.5:
            score *= 0.4
        elif result.eligibility_score < 0.7:
            score *= 0.75

        return score

    # ── Ranker hiperpersonalizado (T2.4) ─────────────────────────────────────

    def rank_hyperpersonalized(
        self,
        results: list[CardSimulationResult],
        profile: UserProfile,
    ) -> list[CardSimulationResult]:
        """
        Ranker hiperpersonalizado com 4 pesos (melhorias_analise_perfil.md §8.1):
            W1 = relevância ao cluster (40%)
            W2 = impacto financeiro em R$ (30%)
            W3 = propensity estimada (20%)
            W4 = timing/adequação momento (10%)

        Backward compatible: se UserProfile não tem cluster classificado, recai no rank() clássico.
        """
        if not results:
            return []

        has_cluster = (
            hasattr(profile, "lifestyle_cluster")
            and profile.lifestyle_cluster != "NAO_CLASSIFICADO"
        )
        if not has_cluster:
            return self.rank(results, profile)

        scored = [(r, self._compute_hyperscore(r, profile)) for r in results]
        scored.sort(key=lambda x: x[1], reverse=True)
        ranked = [r for r, _ in scored]

        if ranked and ranked[0].eligibility_score < 0.4:
            next_eligible = next(
                (r for r in ranked[1:] if r.eligibility_score >= 0.6), None
            )
            if next_eligible:
                ranked.remove(next_eligible)
                ranked.insert(0, next_eligible)

        return ranked

    def _compute_hyperscore(
        self,
        result: CardSimulationResult,
        profile: UserProfile,
    ) -> float:
        cluster = getattr(profile, "lifestyle_cluster", "NAO_CLASSIFICADO")

        w2_financial = self._compute_score(result, profile)
        w1_cluster = self._cluster_relevance(result, profile, cluster) * 200
        w3_propensity = self._estimate_propensity(result, profile) * 100
        w4_timing = self._calc_timing_score(result, profile) * 50

        return (
            0.40 * w1_cluster
            + 0.30 * w2_financial
            + 0.20 * w3_propensity
            + 0.10 * w4_timing
        )

    def _cluster_relevance(
        self,
        result: CardSimulationResult,
        profile: UserProfile,
        cluster: str,
    ) -> float:
        relevance = 0.5

        if cluster == "EXPLORADOR_GLOBAL":
            travel_tags = {BenefitTag.LOUNGE, BenefitTag.TRAVEL, BenefitTag.INSURANCE}
            tag_overlap = len(travel_tags & set(result.benefit_tags)) / len(travel_tags)
            relevance = 0.3 + tag_overlap * 0.7

        elif cluster == "URBANO_FOODIE":
            relevance = 0.8 if BenefitTag.CASHBACK in result.benefit_tags else 0.3

        elif cluster == "INVESTIDOR_CAUTELOSO":
            if result.annuity_effective == 0:
                relevance = 0.9
            elif result.annuity_effective <= 300:
                relevance = 0.65
            else:
                relevance = 0.3

        elif cluster == "ESTRESSE_FINANCEIRO":
            relevance = 0.9 if result.annuity_effective == 0 else 0.2

        return relevance

    def _estimate_propensity(
        self,
        result: CardSimulationResult,
        profile: UserProfile,
    ) -> float:
        propensity = 0.5
        propensity += (result.eligibility_score - 0.5) * 0.4
        if result.confidence_score >= 0.8:
            propensity += 0.1
        if result.net_gain_expected > 1200:
            propensity += 0.15
        return round(min(max(propensity, 0.0), 1.0), 3)

    def _calc_timing_score(
        self,
        result: CardSimulationResult,
        profile: UserProfile,
    ) -> float:
        timing = 0.5
        fss_level = getattr(profile, "fss_level", "SAUDAVEL")
        if fss_level in ("ALERTA", "CRITICO"):
            timing = 0.1 if result.annuity_effective > 300 else 0.6
        return timing
