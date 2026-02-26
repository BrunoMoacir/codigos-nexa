# app/optimizer/ranking.py
# CardRanking — ordena cartões por retorno ajustado por risco e elegibilidade
# Passo 2.3 — Funcionalidade 2: Nexa Optimizer

from __future__ import annotations

import logging

from app.optimizer.models import BenefitTag, CardSimulationResult, LiquidityRisk
from app.optimizer.profiler import UserProfile

# TODO: migrar para structlog (dependência já declarada em pyproject.toml)
logger = logging.getLogger(__name__)

# Fração do net_gain_expected subtraída do score por risco de liquidez
_LIQUIDITY_PENALTY: dict[LiquidityRisk, float] = {
    LiquidityRisk.CRITICAL: 0.8,
    LiquidityRisk.HIGH: 0.4,
    LiquidityRisk.WARNING: 0.1,
    LiquidityRisk.SAFE: 0.0,
}

# Thresholds de gasto mensal para bônus de benefícios específicos
_INTL_SPEND_THRESHOLD = 500.0   # R$/mês para bônus INTERNACIONAL
_TRAVEL_SPEND_THRESHOLD = 800.0  # R$/mês para bônus LOUNGE

# Bônus anuais equivalentes adicionados ao score quando o perfil bate o benefício
_INTL_BONUS = 200.0   # R$/ano
_LOUNGE_BONUS = 300.0  # R$/ano


class CardRanking:
    """
    Ordena CardSimulationResult pelo retorno ajustado.

    Algoritmo:
        score_base = net_gain_expected
        − penalidade de liquidez (subtrativa)
        − penalidade de confiança baixa (multiplicativa)
        + bônus de benefícios relevantes ao perfil (aditivo)
        × penalidade de elegibilidade (multiplicativa)

    Regra especial pós-sort:
        Se o 1º card tiver eligibility_score < 0.4, promover o próximo
        card com eligibility_score >= 0.6 para a primeira posição.
    """

    def rank(
        self,
        results: list[CardSimulationResult],
        profile: UserProfile,
    ) -> list[CardSimulationResult]:
        """
        Retorna a lista ordenada por score (decrescente).

        Args:
            results: Lista de CardSimulationResult já com eligibility_score preenchido.
            profile: Perfil do usuário (usado para bônus de benefícios relevantes).

        Returns:
            Lista ordenada. O primeiro elemento é o cartão recomendado.
        """
        if not results:
            return []

        scored = [(r, self._compute_score(r, profile)) for r in results]
        scored.sort(key=lambda x: x[1], reverse=True)
        ranked = [r for r, _ in scored]

        # Regra de elegibilidade mínima: não recomendar cartão provavelmente inacessível
        if ranked and ranked[0].eligibility_score < 0.4:
            next_eligible = next(
                (r for r in ranked[1:] if r.eligibility_score >= 0.6), None
            )
            if next_eligible:
                ranked.remove(next_eligible)
                ranked.insert(0, next_eligible)
                # Após remove+insert, ranked[1] é o card que era ranked[0]
                # antes da promoção — ou seja, o card deslocado. Referência intencional.
                logger.info(
                    f"Ranking: promovendo {next_eligible.card_id} sobre "
                    f"{ranked[1].card_id} (eligibility baixa no 1º)"
                )

        return ranked

    # ─── Score ────────────────────────────────────────────────────────────────

    def _compute_score(
        self, result: CardSimulationResult, profile: UserProfile
    ) -> float:
        score = result.net_gain_expected

        # 1. Penalidade de liquidez (subtrativa, proporcional ao módulo do ganho).
        # Usa abs() para garantir que a penalidade sempre piore o score:
        # com net_gain negativo, score -= net_gain * pct subtrairia um valor
        # negativo (= somaria), reduzindo artificialmente a penalidade.
        penalty_pct = _LIQUIDITY_PENALTY.get(result.liquidity_risk, 0.0)
        score -= abs(result.net_gain_expected) * penalty_pct

        # 2. Bônus de benefícios relevantes ao perfil (aditivo)
        if (
            profile.international_spend_monthly > _INTL_SPEND_THRESHOLD
            and BenefitTag.INTERNACIONAL in result.benefit_tags
        ):
            score += _INTL_BONUS

        if (
            profile.travel_spend_monthly > _TRAVEL_SPEND_THRESHOLD
            and BenefitTag.LOUNGE in result.benefit_tags
        ):
            score += _LOUNGE_BONUS

        # 3. Penalidade de confiança baixa (multiplicativa, aplicada após os bônus).
        # Aplicar aqui garante que dados incertos também penalizem a estimativa
        # dos bônus de benefício — não apenas o ganho base.
        if result.confidence_score < 0.4:
            score *= 0.5

        # 4. Penalidade de elegibilidade (multiplicativa)
        if result.eligibility_score < 0.5:
            score *= 0.4
        elif result.eligibility_score < 0.7:
            score *= 0.75
        # >= 0.7: sem penalidade

        return score
