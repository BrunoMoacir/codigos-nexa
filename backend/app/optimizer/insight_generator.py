# app/optimizer/insight_generator.py
# InsightGenerator — Camada 5: Geração de Insights Acionáveis (Card Optimizer v2.1)

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.optimizer.models import (
    ActionableInsight,
    BenefitTag,
    CardSimulationResult,
    InsightEffort,
    InsightInterval,
    InsightType,
)

if TYPE_CHECKING:
    from app.optimizer.profiler import UserProfile

logger = logging.getLogger(__name__)

# Effort multipliers para priority_score (seção 7.3 da arquitetura)
_EFFORT_MULTIPLIER: dict[InsightEffort, float] = {
    InsightEffort.BAIXO: 1.20,
    InsightEffort.MEDIO: 1.00,
    InsightEffort.ALTO:  0.70,
}

# Gates de ativação por tipo de insight (ganho mínimo mensal em R$)
_TRIGGER_GAIN_TROCAR_PRIMARIO  = 20.0   # R$/mês
_TRIGGER_GAIN_PORTFOLIO_MULTI  = 30.0   # R$/mês
_TRIGGER_GAIN_ATIVAR_BENEFICIO = 20.0   # R$/mês
_TRIGGER_LOSS_CANCELAR_CARTAO  = -15.0  # R$/mês (prejuízo)
_TRIGGER_GAIN_MUDAR_CATEGORIA  = 15.0   # R$/mês por categoria
_UPGRADE_ELIGIBILITY_GATE      = 0.85   # elegibilidade mínima para surfaçar upgrade
_UPGRADE_MIN_ANNUITY           = 300.0  # anuidade mínima que indica cartão premium (R$/ano)
_MIN_CATEGORY_SPEND_MONTHLY    = 200.0  # gasto mínimo em categoria para insight MUDAR_CATEGORIA

# Mapeamento de categoria de gasto → BenefitTag mais relevante
_CATEGORY_BENEFIT_MAP: dict[str, BenefitTag] = {
    "alimentacao":  BenefitTag.CASHBACK,
    "supermercado": BenefitTag.CASHBACK,
    "farmacia":     BenefitTag.CASHBACK,
    "transporte":   BenefitTag.TRAVEL,
    "lazer":        BenefitTag.TRAVEL,
    "viagem":       BenefitTag.TRAVEL,
    "internacional": BenefitTag.INTERNACIONAL,
}

# Tags que identificam cartões premium para SOLICITAR_UPGRADE
_UPGRADE_PREMIUM_TAGS: frozenset[BenefitTag] = frozenset({
    BenefitTag.LOUNGE, BenefitTag.PREMIUM, BenefitTag.INSURANCE,
})

# ConfidenceGate para surfaçar insights (regra de ouro do anti-falso-positivo)
_INSIGHT_CONFIDENCE_GATE = 0.65
# MinGainFilter — P25 do ganho deve ser ≥ R$10/mês para surfaçar
_INSIGHT_MIN_MONTHLY_GAIN = 10.0


class InsightGenerator:
    """
    Gera e ranqueia insights acionáveis a partir dos resultados do Optimizer.

    Taxonomia implementada (seção 7.1 da arquitetura v2.1):
        TROCAR_PRIMARIO   — melhor cartão ≠ atual, ganho > R$20/mês
        PORTFOLIO_MULTI   — 2+ cartões melhoram retorno > R$30/mês
        ATIVAR_BENEFICIO  — benefício não usado com valor > R$20/mês
        CANCELAR_CARTAO   — cartão com retorno líquido < -R$15/mês
        ATINGIR_ISENCAO   — gap < 3 meses de gasto para waiver
        MUDAR_CATEGORIA   — cartão existente melhor em categoria não usada
        SOLICITAR_UPGRADE — usuário atingiu 90%+ dos critérios do próximo tier

    Regra de ouro: Se estiver em dúvida se deve mostrar um insight, não mostre.
    Confiança vale mais que completude.
    """

    def generate(
        self,
        ranked_results: list[CardSimulationResult],
        profile: "UserProfile",
        current_card_id: str | None = None,
        current_card_monthly_return: float = 0.0,
    ) -> list[ActionableInsight]:
        """
        Gera lista de insights ranqueados por priority_score.

        Args:
            ranked_results: Cartões já simulados e ranqueados (Camada 4).
            profile: Perfil de consumo do usuário.
            current_card_id: ID do cartão principal atual (para TROCAR_PRIMARIO).
            current_card_monthly_return: Retorno mensal do cartão atual em R$.

        Returns:
            Lista de ActionableInsight ranqueados por priority_score (decrescente).
            Apenas insights que passam no ConfidenceGate e MinGainFilter.
        """
        insights: list[ActionableInsight] = []

        if not ranked_results:
            return []

        best = ranked_results[0]

        # 1. TROCAR_PRIMARIO
        insight = self._try_trocar_primario(
            best, profile, current_card_id, current_card_monthly_return
        )
        if insight:
            insights.append(insight)

        # 2. PORTFOLIO_MULTI
        insight = self._try_portfolio_multi(ranked_results, profile)
        if insight:
            insights.append(insight)

        # 3. ATIVAR_BENEFICIO
        insights.extend(self._try_ativar_beneficio(ranked_results, profile))

        # 4. ATINGIR_ISENCAO
        insights.extend(self._try_atingir_isencao(ranked_results, profile))

        # 5. CANCELAR_CARTAO
        insight = self._try_cancelar_cartao(current_card_id, current_card_monthly_return)
        if insight:
            insights.append(insight)

        # 6. MUDAR_CATEGORIA
        insights.extend(self._try_mudar_categoria(ranked_results, profile, current_card_id))

        # 7. SOLICITAR_UPGRADE
        insight = self._try_solicitar_upgrade(ranked_results, profile, current_card_id)
        if insight:
            insights.append(insight)

        # 8. Filtrar e ranquear
        valid = [i for i in insights if self._passes_gates(i)]
        valid.sort(key=lambda i: i.priority_score, reverse=True)

        return valid

    # ─── Geradores por tipo ────────────────────────────────────────────────────

    def _try_trocar_primario(
        self,
        best: CardSimulationResult,
        profile: "UserProfile",
        current_card_id: str | None,
        current_monthly_return: float,
    ) -> ActionableInsight | None:
        if best.card_id == current_card_id:
            return None

        monthly_gain = (best.net_gain_expected / 12) - current_monthly_return
        if monthly_gain < _TRIGGER_GAIN_TROCAR_PRIMARIO:
            return None

        interval = self._make_interval(best, current_monthly_return)
        effort = InsightEffort.MEDIO

        return ActionableInsight(
            type=InsightType.TROCAR_PRIMARIO,
            title=f"Trocar para {best.card_name}",
            description=(
                f"Com seu padrão de gastos, o {best.card_name} pode render "
                f"{interval.display_text()} a mais do que seu cartão atual."
            ),
            gain_interval=interval,
            effort=effort,
            confidence_score=best.confidence_score,
            priority_score=self._priority(monthly_gain, effort, best.confidence_score),
            card_id=best.card_id,
            card_name=best.card_name,
        )

    def _try_portfolio_multi(
        self,
        ranked_results: list[CardSimulationResult],
        profile: "UserProfile",
    ) -> ActionableInsight | None:
        # Verifica se 2+ cartões com retorno positivo formam um portfólio melhor
        positive_cards = [r for r in ranked_results if r.net_gain_expected > 0]
        if len(positive_cards) < 2:
            return None

        # Ganho combinado dos top 2 (simplificado sem otimizador de portfólio completo)
        top2_monthly = sum(r.net_gain_expected / 12 for r in positive_cards[:2])
        best_monthly = positive_cards[0].net_gain_expected / 12

        portfolio_gain = top2_monthly - best_monthly
        if portfolio_gain < _TRIGGER_GAIN_PORTFOLIO_MULTI:
            return None

        confidence = min(r.confidence_score for r in positive_cards[:2])
        interval = InsightInterval(
            conservative=portfolio_gain * 0.8,
            expected=portfolio_gain,
            optimistic=portfolio_gain * 1.3,
        )
        effort = InsightEffort.BAIXO

        return ActionableInsight(
            type=InsightType.PORTFOLIO_MULTI,
            title="Estratégia com 2 cartões",
            description=(
                f"Usar {positive_cards[0].card_name} + {positive_cards[1].card_name} "
                f"pode aumentar seu retorno em {interval.display_text()} adicionais."
            ),
            gain_interval=interval,
            effort=effort,
            confidence_score=confidence,
            priority_score=self._priority(portfolio_gain, effort, confidence),
        )

    def _try_ativar_beneficio(
        self,
        ranked_results: list[CardSimulationResult],
        profile: "UserProfile",
    ) -> list[ActionableInsight]:
        insights: list[ActionableInsight] = []
        seen_tags: set[str] = set()

        for result in ranked_results[:5]:
            for tag in result.benefit_tags:
                tag_key = f"{result.card_id}:{tag}"
                if tag_key in seen_tags:
                    continue

                # Verificar se o benefício tem alto valor mas baixa utilização detectada
                benefit_value_monthly = self._estimate_benefit_value(tag, profile)
                if benefit_value_monthly < _TRIGGER_GAIN_ATIVAR_BENEFICIO:
                    continue

                seen_tags.add(tag_key)
                effort = InsightEffort.BAIXO
                interval = InsightInterval(
                    conservative=benefit_value_monthly * 0.5,
                    expected=benefit_value_monthly,
                    optimistic=benefit_value_monthly * 1.5,
                )

                insights.append(ActionableInsight(
                    type=InsightType.ATIVAR_BENEFICIO,
                    title=f"Ativar benefício {tag.value}",
                    description=(
                        f"O {result.card_name} tem benefício {tag.value} que "
                        f"pode valer {interval.display_text()} com seu perfil."
                    ),
                    gain_interval=interval,
                    effort=effort,
                    confidence_score=result.confidence_score,
                    priority_score=self._priority(benefit_value_monthly, effort, result.confidence_score),
                    card_id=result.card_id,
                    card_name=result.card_name,
                    tags=[tag.value],
                ))

        return insights

    def _try_atingir_isencao(
        self,
        ranked_results: list[CardSimulationResult],
        profile: "UserProfile",
    ) -> list[ActionableInsight]:
        insights: list[ActionableInsight] = []

        for result in ranked_results[:5]:
            # Só aplica se o cartão ainda paga anuidade (não foi isentado)
            if result.annuity_waived or result.annuity_effective <= 0:
                continue

            monthly_annuity = result.annuity_effective / 12
            if monthly_annuity < 10:
                continue

            effort = InsightEffort.MEDIO
            interval = InsightInterval(
                conservative=monthly_annuity * 0.8,
                expected=monthly_annuity,
                optimistic=monthly_annuity,
            )

            insights.append(ActionableInsight(
                type=InsightType.ATINGIR_ISENCAO,
                title=f"Isentar anuidade do {result.card_name}",
                description=(
                    f"Aumentar gastos no {result.card_name} pode eliminar a anuidade "
                    f"de {interval.display_text()}."
                ),
                gain_interval=interval,
                effort=effort,
                confidence_score=result.confidence_score,
                priority_score=self._priority(monthly_annuity, effort, result.confidence_score),
                card_id=result.card_id,
                card_name=result.card_name,
            ))

        return insights

    def _try_cancelar_cartao(
        self,
        current_card_id: str | None,
        current_card_monthly_return: float,
    ) -> ActionableInsight | None:
        """
        Ativa quando o cartão atual gera prejuízo líquido > R$15/mês.

        Requer que optimizer_service passe current_card_monthly_return calculado
        via M2.4 (CurrentCardROI). Sem esse dado (default 0.0) o insight nunca dispara,
        o que é o comportamento correto — não cancelar sem evidência.
        """
        if not current_card_id:
            return None
        if current_card_monthly_return >= _TRIGGER_LOSS_CANCELAR_CARTAO:
            return None

        monthly_loss = abs(current_card_monthly_return)
        annual_savings = monthly_loss * 12
        interval = InsightInterval(
            conservative=monthly_loss * 0.8,
            expected=monthly_loss,
            optimistic=monthly_loss * 1.1,
        )
        effort = InsightEffort.MEDIO
        confidence = 0.80

        return ActionableInsight(
            type=InsightType.CANCELAR_CARTAO,
            title="Considere cancelar este cartão",
            description=(
                f"Seu cartão atual está gerando prejuízo de {interval.display_text()}. "
                f"Cancelá-lo pode economizar R${annual_savings:.0f}/ano em anuidade "
                f"sem retorno correspondente."
            ),
            gain_interval=interval,
            effort=effort,
            confidence_score=confidence,
            priority_score=self._priority(monthly_loss, effort, confidence),
            card_id=current_card_id,
        )

    def _try_mudar_categoria(
        self,
        ranked_results: list[CardSimulationResult],
        profile: "UserProfile",
        current_card_id: str | None,
    ) -> list[ActionableInsight]:
        """
        Para cada categoria de alto gasto do usuário, verifica se um cartão
        ranqueado tem benefício específico que justifique direcionar aquele gasto.
        """
        insights: list[ActionableInsight] = []
        seen_categories: set[str] = set()
        total_spend = max(profile.monthly_avg_spend, 1.0)

        top_categories = sorted(
            profile.spend_by_category.items(), key=lambda x: x[1], reverse=True
        )

        for category, monthly_spend in top_categories[:3]:
            if monthly_spend < _MIN_CATEGORY_SPEND_MONTHLY:
                break
            if category in seen_categories:
                continue

            target_tag = _CATEGORY_BENEFIT_MAP.get(category)
            if not target_tag:
                continue

            best = next(
                (r for r in ranked_results[:5]
                 if target_tag in r.benefit_tags and r.card_id != current_card_id),
                None,
            )
            if best is None:
                continue

            # Ganho proporcional ao peso da categoria no gasto total
            category_ratio = min(monthly_spend / total_spend, 1.0)
            category_gain_monthly = (best.net_gain_expected / 12) * category_ratio

            if category_gain_monthly < _TRIGGER_GAIN_MUDAR_CATEGORIA:
                continue

            seen_categories.add(category)
            effort = InsightEffort.BAIXO
            interval = InsightInterval(
                conservative=category_gain_monthly * 0.7,
                expected=category_gain_monthly,
                optimistic=category_gain_monthly * 1.3,
            )

            insights.append(ActionableInsight(
                type=InsightType.MUDAR_CATEGORIA,
                title=f"Otimizar gastos em {category}",
                description=(
                    f"Você gasta R${monthly_spend:.0f}/mês em {category}. "
                    f"O {best.card_name} tem benefício {target_tag.value} que pode render "
                    f"{interval.display_text()} adicionais nesta categoria."
                ),
                gain_interval=interval,
                effort=effort,
                confidence_score=best.confidence_score,
                priority_score=self._priority(category_gain_monthly, effort, best.confidence_score),
                card_id=best.card_id,
                card_name=best.card_name,
                tags=[category, target_tag.value],
            ))

        return insights

    def _try_solicitar_upgrade(
        self,
        ranked_results: list[CardSimulationResult],
        profile: "UserProfile",
        current_card_id: str | None,
    ) -> ActionableInsight | None:
        """
        Ativa quando o usuário tem eligibility ≥ 85% para um cartão premium
        (LOUNGE, PREMIUM ou INSURANCE) com anuidade ≥ R$300/ano e retorno positivo.
        """
        for result in ranked_results[:5]:
            if result.card_id == current_card_id:
                continue
            if result.eligibility_score < _UPGRADE_ELIGIBILITY_GATE:
                continue
            if result.annuity_effective < _UPGRADE_MIN_ANNUITY:
                continue

            premium_tags = [t for t in result.benefit_tags if t in _UPGRADE_PREMIUM_TAGS]
            if not premium_tags:
                continue

            monthly_gain = result.net_gain_expected / 12
            if monthly_gain < _INSIGHT_MIN_MONTHLY_GAIN:
                continue

            effort = InsightEffort.ALTO
            interval = self._make_interval(result)
            confidence = result.confidence_score * result.eligibility_score

            return ActionableInsight(
                type=InsightType.SOLICITAR_UPGRADE,
                title=f"Upgrade para {result.card_name}",
                description=(
                    f"Seu perfil financeiro qualifica para o {result.card_name}, "
                    f"cartão premium com {', '.join(t.value for t in premium_tags[:2])}. "
                    f"O retorno estimado é {interval.display_text()}."
                ),
                gain_interval=interval,
                effort=effort,
                confidence_score=confidence,
                priority_score=self._priority(monthly_gain, effort, confidence),
                card_id=result.card_id,
                card_name=result.card_name,
                tags=[t.value for t in premium_tags],
            )

        return None

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _make_interval(
        self,
        result: CardSimulationResult,
        current_monthly_return: float = 0.0,
    ) -> InsightInterval:
        """Monta InsightInterval em R$/mês a partir dos 3 cenários do CardSimulationResult."""
        conservative = (result.net_gain_min / 12) - current_monthly_return
        expected = (result.net_gain_expected / 12) - current_monthly_return
        optimistic = (result.net_gain_max / 12) - current_monthly_return
        return InsightInterval(
            conservative=max(conservative, 0),
            expected=max(expected, 0),
            optimistic=max(optimistic, 0),
        )

    def _estimate_benefit_value(self, tag, profile: "UserProfile") -> float:
        """Estimativa simplificada de valor mensal do benefício com base no perfil."""
        if tag == BenefitTag.LOUNGE and profile.travel_spend_monthly > 800:
            return 70.0  # R$70/uso × ~1 uso/mês
        if tag == BenefitTag.INTERNACIONAL and profile.international_spend_monthly > 500:
            return 25.0  # estimativa de economia em IOF
        return 0.0

    def _priority(self, monthly_gain: float, effort: InsightEffort, confidence: float) -> float:
        """
        priority_score = monthly_gain × effort_multiplier × confidence_score

        Esforço Baixo → ×1.20 (fácil de executar, alta conversão)
        Esforço Médio → ×1.00 (neutro)
        Esforço Alto  → ×0.70 (fricção reduz taxa de execução)
        """
        multiplier = _EFFORT_MULTIPLIER.get(effort, 1.0)
        return round(monthly_gain * multiplier * confidence, 2)

    def _passes_gates(self, insight: ActionableInsight) -> bool:
        """
        ConfidenceGate + MinGainFilter — regra de ouro do anti-falso-positivo.

        Descarta silenciosamente insights com:
        - confidence_score < 0.65
        - ganho conservador (P25) < R$10/mês
        """
        if insight.confidence_score < _INSIGHT_CONFIDENCE_GATE:
            logger.debug(
                "InsightGate: descartando %s (confidence=%.2f)", insight.type, insight.confidence_score
            )
            return False
        if insight.gain_interval.conservative < _INSIGHT_MIN_MONTHLY_GAIN:
            logger.debug(
                "InsightGate: descartando %s (P25=R$%.0f/mês)", insight.type, insight.gain_interval.conservative
            )
            return False
        return True
