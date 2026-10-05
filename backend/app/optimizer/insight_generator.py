# app/optimizer/insight_generator.py
# InsightGenerator — Camada 5: Geração de Insights Acionáveis (Card Optimizer v2.1)

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from app.optimizer.constants import INTL_SPEND_THRESHOLD, TRAVEL_SPEND_THRESHOLD
from app.optimizer.models import (
    ActionableInsight,
    BenefitTag,
    CardSimulationResult,
    InsightEffort,
    InsightInterval,
    InsightType,
)
from app.core.formatacao import brl

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

# Estágios de vida — contexto para insights hiperpersonalizados
_LIFE_STAGE_CONTEXT: dict[str, dict] = {
    "FAMILIA_BEBE": {
        "prefix": "Com um filho pequeno em casa",
        "focus": "cashback em farmácia e supermercado",
        "card_priority_tags": [BenefitTag.CASHBACK],
        "top_categories": ["farmacia", "supermercado"],
    },
    "NOMADE_DIGITAL": {
        "prefix": "Como nômade digital",
        "focus": "sem IOF no exterior e sem anuidade fixa",
        "card_priority_tags": [BenefitTag.INTERNACIONAL, BenefitTag.TRAVEL],
        "top_categories": ["viagem"],
    },
    "INVESTIDOR_PREMIUM": {
        "prefix": "Como investidor ativo",
        "focus": "retorno líquido sobre o custo de oportunidade da anuidade",
        "card_priority_tags": [BenefitTag.CASHBACK, BenefitTag.PREMIUM],
        "top_categories": [],
    },
    "SOLTEIRO_URBANO": {
        "prefix": "Com seu estilo de vida urbano",
        "focus": "cashback em delivery e alimentação",
        "card_priority_tags": [BenefitTag.CASHBACK],
        "top_categories": ["alimentacao", "delivery"],
    },
}

# T2.6 — Templates de linguagem personalizados por cluster
_CLUSTER_TONE: dict[str, dict] = {
    "EXPLORADOR_GLOBAL": {
        "prefix": "Para quem viaja como você",
        "emphasis": "milhas e lounge",
        "currency_framing": "passagem grátis",
    },
    "URBANO_FOODIE": {
        "prefix": "Com seu gasto em alimentação",
        "emphasis": "cashback e benefícios em restaurantes",
        "currency_framing": "refeição grátis",
    },
    "INVESTIDOR_CAUTELOSO": {
        "prefix": "Calculando o custo de oportunidade",
        "emphasis": "retorno líquido sobre anuidade",
        "currency_framing": "rendimento no investimento",
    },
    "FAMILIA_ESTRUTURADA": {
        "prefix": "Para sua família",
        "emphasis": "cashback em supermercado e farmácia",
        "currency_framing": "mês de compras grátis",
    },
}


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
        current_card_monthly_return: float | None = 0.0,
        enable_cluster_tone: bool = True,
        feedback_weights: dict[str, float] | None = None,
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

        # 1. TROCAR_PRIMARIO — requer ROI do cartão atual conhecido; None suprime o insight
        # para evitar mostrar ganho absoluto como se fosse ganho incremental.
        if current_card_monthly_return is not None:
            insight = self._try_trocar_primario(
                best, profile, current_card_id, current_card_monthly_return,
                enable_cluster_tone=enable_cluster_tone,
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

        # 5. CANCELAR_CARTAO — idem: requer retorno mensal real para calcular a perda.
        if current_card_monthly_return is not None:
            insight = self._try_cancelar_cartao(current_card_id, current_card_monthly_return)
            if insight:
                insights.append(insight)

        # 6. MUDAR_CATEGORIA
        insights.extend(self._try_mudar_categoria(ranked_results, profile, current_card_id))

        # 7. SOLICITAR_UPGRADE — idem: ganho incremental requer baseline real.
        if current_card_monthly_return is not None:
            insight = self._try_solicitar_upgrade(
                ranked_results, profile, current_card_id, current_card_monthly_return
            )
            if insight:
                insights.append(insight)

        # 8. Insights por cluster de estilo de vida (apenas TREATMENT)
        if enable_cluster_tone:
            insights.extend(self._generate_cluster_insights(ranked_results, profile))

        # 9. Insights por tendência de categoria e renda
        insights.extend(self._try_tendencia_insights(ranked_results, profile))

        # 10. Insights por estágio de vida (LifeStageDetector)
        insights.extend(self._try_life_stage_insights(ranked_results, profile))

        # 11. Filtrar, aplicar pesos de feedback e ranquear
        valid = [i for i in insights if self._passes_gates(i)]

        if feedback_weights:
            for insight in valid:
                weight = feedback_weights.get(insight.type.value, 1.0)
                insight.priority_score = round(insight.priority_score * weight, 2)

        valid.sort(key=lambda i: i.priority_score, reverse=True)

        # Atribuir UUIDs únicos para rastreamento de feedback
        for insight in valid:
            insight.insight_id = str(uuid.uuid4())

        return valid

    # ─── Geradores por tipo ────────────────────────────────────────────────────

    def _try_trocar_primario(
        self,
        best: CardSimulationResult,
        profile: "UserProfile",
        current_card_id: str | None,
        current_monthly_return: float,
        enable_cluster_tone: bool = True,
    ) -> ActionableInsight | None:
        if best.card_id == current_card_id:
            return None

        monthly_gain = (best.net_gain_expected / 12) - current_monthly_return
        if monthly_gain < _TRIGGER_GAIN_TROCAR_PRIMARIO:
            return None

        interval = self._make_interval(best, current_monthly_return)
        effort = InsightEffort.MEDIO

        base_description = (
            f"Com seu padrão de gastos, o {best.card_name} pode render "
            f"{interval.display_text()} a mais do que seu cartão atual."
        )
        description = self._personalize_description(
            base_description, profile, best.net_gain_expected,
            enable_cluster_tone=enable_cluster_tone,
        )

        return ActionableInsight(
            type=InsightType.TROCAR_PRIMARIO,
            title=f"Trocar para {best.card_name}",
            description=description,
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

        current_monthly_credit_spend = profile.monthly_avg_spend * getattr(profile, "credit_spend_ratio", 1.0)

        for result in ranked_results[:5]:
            if result.annuity_waived or result.annuity_effective <= 0:
                continue

            monthly_annuity = result.annuity_effective / 12
            if monthly_annuity < 10:
                continue

            # Gap de gasto: quanto a mais por mês para atingir o threshold de isenção
            monthly_gap: float | None = None
            if result.waiver_threshold and result.waiver_threshold > 0:
                needed_monthly = result.waiver_threshold / 12
                raw_gap = needed_monthly - current_monthly_credit_spend
                monthly_gap = round(max(raw_gap, 0.0), 2)

            effort = InsightEffort.MEDIO
            interval = InsightInterval(
                conservative=monthly_annuity * 0.8,
                expected=monthly_annuity,
                optimistic=monthly_annuity,
            )

            if monthly_gap is not None and monthly_gap > 0:
                description = (
                    f"Gastando mais {brl(monthly_gap, 0)}/mês no {result.card_name} "
                    f"você elimina a anuidade de {interval.display_text()}."
                )
            elif monthly_gap == 0.0:
                description = (
                    f"Você já está próximo do threshold de isenção do {result.card_name}. "
                    f"Concentrar seus gastos nele pode eliminar a anuidade de {interval.display_text()}."
                )
            else:
                description = (
                    f"Aumentar gastos no {result.card_name} pode eliminar a anuidade "
                    f"de {interval.display_text()}."
                )

            insights.append(ActionableInsight(
                type=InsightType.ATINGIR_ISENCAO,
                title=f"Isentar anuidade do {result.card_name}",
                description=description,
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
                f"Cancelá-lo pode economizar {brl(annual_savings, 0)}/ano em anuidade "
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
                    f"Você gasta {brl(monthly_spend, 0)}/mês em {category}. "
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
        current_card_monthly_return: float = 0.0,
    ) -> ActionableInsight | None:
        """
        Ativa quando o usuário tem eligibility ≥ 85% para um cartão premium
        (LOUNGE, PREMIUM ou INSURANCE) com anuidade ≥ R$300/ano e retorno positivo.

        O ganho exibido e o gate mínimo usam o ganho INCREMENTAL (vs. cartão atual),
        não o ganho absoluto do cartão premium.
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

            monthly_gain = result.net_gain_expected / 12 - current_card_monthly_return
            if monthly_gain < _INSIGHT_MIN_MONTHLY_GAIN:
                continue

            effort = InsightEffort.ALTO
            interval = self._make_interval(result, current_card_monthly_return)
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

    def _try_life_stage_insights(
        self,
        ranked: list[CardSimulationResult],
        profile: "UserProfile",
    ) -> list[ActionableInsight]:
        """
        Gera até 1 insight hiperpersonalizado por estágio de vida detectado.

        Cada estágio prioriza benefit_tags e categorias de gasto diferentes,
        gerando recomendações mais relevantes que os insights genéricos de cluster.
        Só dispara quando life_stage_confidence ≥ 0.50 para evitar falsos positivos.
        """
        life_stage = getattr(profile, "life_stage", "NAO_IDENTIFICADO")
        confidence = getattr(profile, "life_stage_confidence", 0.0)

        if life_stage == "NAO_IDENTIFICADO" or confidence < 0.50:
            return []

        ctx = _LIFE_STAGE_CONTEXT.get(life_stage)
        if not ctx or not ranked:
            return []

        priority_tags: list[BenefitTag] = ctx["card_priority_tags"]

        # Busca o melhor cartão com os benefit_tags relevantes para o estágio
        best = next(
            (r for r in ranked[:5] if any(t in r.benefit_tags for t in priority_tags)),
            ranked[0],
        )

        if life_stage == "FAMILIA_BEBE":
            return self._life_stage_familia_bebe(best, profile, confidence)
        if life_stage == "NOMADE_DIGITAL":
            return self._life_stage_nomade_digital(best, profile, confidence)
        if life_stage == "INVESTIDOR_PREMIUM":
            return self._life_stage_investidor_premium(best, profile, confidence)
        if life_stage == "SOLTEIRO_URBANO":
            return self._life_stage_solteiro_urbano(best, profile, confidence)

        return []

    def _life_stage_familia_bebe(
        self,
        best: CardSimulationResult,
        profile: "UserProfile",
        stage_confidence: float,
    ) -> list[ActionableInsight]:
        pharmacy = profile.spend_by_category.get("farmacia", 0.0)
        supermarket = profile.spend_by_category.get("supermercado", 0.0)
        family_spend = pharmacy + supermarket

        if family_spend < 200:
            return []

        # Estimativa conservadora: 2% de cashback médio sobre farmácia + supermercado
        gain_monthly = round(family_spend * 0.02, 2)
        interval = InsightInterval(
            conservative=gain_monthly * 0.70,
            expected=gain_monthly,
            optimistic=gain_monthly * 1.50,
        )
        effort = InsightEffort.BAIXO
        confidence = round(min(stage_confidence * best.confidence_score * 1.2, 0.90), 3)

        return [ActionableInsight(
            type=InsightType.MUDAR_CATEGORIA,
            title="Cashback em farmácia e supermercado para sua família",
            description=(
                f"Com filho pequeno em casa, você gasta {brl(family_spend, 0)}/mês entre "
                f"farmácia e supermercado. O {best.card_name} tem cashback nessas categorias "
                f"e pode retornar {interval.display_text()}."
            ),
            gain_interval=interval,
            effort=effort,
            confidence_score=confidence,
            priority_score=self._priority(gain_monthly, effort, confidence),
            card_id=best.card_id,
            card_name=best.card_name,
            tags=["familia_bebe", "farmacia", "supermercado", BenefitTag.CASHBACK.value],
        )]

    def _life_stage_nomade_digital(
        self,
        best: CardSimulationResult,
        profile: "UserProfile",
        stage_confidence: float,
    ) -> list[ActionableInsight]:
        intl_spend = getattr(profile, "international_spend_monthly", 0.0)
        travel_spend = getattr(profile, "travel_spend_monthly", 0.0)
        relevant_spend = max(intl_spend, travel_spend)

        if relevant_spend < 100:
            return []

        # IOF no cartão normal é 6.38% sobre gasto internacional — economia real
        iof_savings_monthly = round(intl_spend * 0.0638, 2) if intl_spend > 0 else 0.0
        # Se não tem gasto internacional mas tem viagem, usa 2% de retorno estimado
        gain_monthly = iof_savings_monthly if iof_savings_monthly > 0 else round(travel_spend * 0.02, 2)

        interval = InsightInterval(
            conservative=gain_monthly * 0.70,
            expected=gain_monthly,
            optimistic=gain_monthly * 1.40,
        )
        effort = InsightEffort.BAIXO
        confidence = round(min(stage_confidence * best.confidence_score * 1.2, 0.90), 3)

        desc_intl = (
            f"Com {brl(intl_spend, 0)}/mês em gastos internacionais, "
            f"o IOF pode custar {brl(iof_savings_monthly, 0)}/mês. "
        ) if intl_spend > 50 else (
            f"Com {brl(travel_spend, 0)}/mês em viagens, "
        )

        return [ActionableInsight(
            type=InsightType.MUDAR_CATEGORIA,
            title="Cartão sem IOF para seu estilo nômade",
            description=(
                f"{desc_intl}O {best.card_name} tem benefícios internacionais "
                f"que podem economizar {interval.display_text()}."
            ),
            gain_interval=interval,
            effort=effort,
            confidence_score=confidence,
            priority_score=self._priority(gain_monthly, effort, confidence),
            card_id=best.card_id,
            card_name=best.card_name,
            tags=["nomade_digital", BenefitTag.INTERNACIONAL.value, BenefitTag.TRAVEL.value],
        )]

    def _life_stage_investidor_premium(
        self,
        best: CardSimulationResult,
        profile: "UserProfile",
        stage_confidence: float,
    ) -> list[ActionableInsight]:
        monthly_gain = best.net_gain_expected / 12
        if monthly_gain < _INSIGHT_MIN_MONTHLY_GAIN:
            return []

        # Para investidor, o custo de oportunidade da anuidade é o framing central
        annuity_monthly = best.annuity_effective / 12
        interval = self._make_interval(best)
        effort = InsightEffort.BAIXO
        confidence = round(min(stage_confidence * best.confidence_score * 1.15, 0.90), 3)

        if best.annuity_waived:
            annuity_note = f"anuidade isenta no seu volume de gastos"
        elif annuity_monthly > 0:
            annuity_note = f"anuidade de {brl(annuity_monthly, 0)}/mês coberta pelo retorno"
        else:
            annuity_note = "sem anuidade"

        return [ActionableInsight(
            type=InsightType.MUDAR_CATEGORIA,
            title=f"Retorno líquido superior com {best.card_name}",
            description=(
                f"Como investidor ativo, cada real em anuidade é custo de oportunidade. "
                f"O {best.card_name} ({annuity_note}) pode retornar "
                f"{interval.display_text()} líquidos sobre seu padrão de gastos."
            ),
            gain_interval=interval,
            effort=effort,
            confidence_score=confidence,
            priority_score=self._priority(monthly_gain, effort, confidence),
            card_id=best.card_id,
            card_name=best.card_name,
            tags=["investidor_premium", "retorno_liquido", BenefitTag.CASHBACK.value],
        )]

    def _life_stage_solteiro_urbano(
        self,
        best: CardSimulationResult,
        profile: "UserProfile",
        stage_confidence: float,
    ) -> list[ActionableInsight]:
        trends = getattr(profile, "category_trends", {})
        delivery_monthly = trends.get("_delivery", {}).get("current_monthly", 0.0)
        if delivery_monthly == 0:
            delivery_monthly = profile.spend_by_category.get("delivery", 0.0)

        food_spend = profile.spend_by_category.get("alimentacao", 0.0)
        relevant_spend = max(delivery_monthly, food_spend)

        if relevant_spend < 100:
            return []

        # Delivery/alimentação: ~3% cashback em cartões especializados
        gain_monthly = round(relevant_spend * 0.03, 2)
        interval = InsightInterval(
            conservative=gain_monthly * 0.60,
            expected=gain_monthly,
            optimistic=gain_monthly * 1.50,
        )
        effort = InsightEffort.BAIXO
        confidence = round(min(stage_confidence * best.confidence_score * 1.2, 0.90), 3)

        if delivery_monthly > 0:
            spend_desc = f"{brl(delivery_monthly, 0)}/mês em delivery"
        else:
            spend_desc = f"{brl(food_spend, 0)}/mês em alimentação"

        return [ActionableInsight(
            type=InsightType.MUDAR_CATEGORIA,
            title="Cashback em alimentação e delivery",
            description=(
                f"Com {spend_desc} e pouco supermercado, seu perfil urbano "
                f"aproveita melhor cashback em restaurantes e apps. "
                f"O {best.card_name} pode retornar {interval.display_text()} nessas categorias."
            ),
            gain_interval=interval,
            effort=effort,
            confidence_score=confidence,
            priority_score=self._priority(gain_monthly, effort, confidence),
            card_id=best.card_id,
            card_name=best.card_name,
            tags=["solteiro_urbano", "delivery", "alimentacao", BenefitTag.CASHBACK.value],
        )]

    def _generate_cluster_insights(
        self,
        ranked: list[CardSimulationResult],
        profile: "UserProfile",
    ) -> list[ActionableInsight]:
        """
        Insights específicos por cluster de estilo de vida.

        Gera insights para o cluster primário e para cada cluster secundário
        (máx 1 insight por cluster secundário, para não criar ruído).
        """
        insights: list[ActionableInsight] = []
        primary_cluster = getattr(profile, "lifestyle_cluster", "NAO_CLASSIFICADO")

        insights.extend(self._cluster_insights_for(ranked, profile, primary_cluster))

        for secondary in getattr(profile, "secondary_clusters", [])[:2]:
            secondary_insights = self._cluster_insights_for(ranked, profile, secondary)
            if secondary_insights:
                insights.append(secondary_insights[0])  # apenas o mais relevante

        return insights

    def _cluster_insights_for(
        self,
        ranked: list[CardSimulationResult],
        profile: "UserProfile",
        cluster: str,
    ) -> list[ActionableInsight]:
        """Insights para um cluster específico (primário ou secundário)."""
        insights: list[ActionableInsight] = []

        if cluster == "EXPLORADOR_GLOBAL" and profile.travel_spend_monthly > 500:
            top_card = ranked[0] if ranked else None
            if top_card and BenefitTag.TRAVEL not in top_card.benefit_tags:
                annual_travel = profile.travel_spend_monthly * 12
                effort = InsightEffort.MEDIO
                interval = InsightInterval(
                    conservative=80.0,
                    expected=120.0,
                    optimistic=200.0,
                )
                insights.append(ActionableInsight(
                    type=InsightType.MUDAR_CATEGORIA,
                    title="Seu perfil de viajante merece milhas",
                    description=(
                        f"Você gastou {brl(annual_travel, 0)}/ano em viagens "
                        f"sem acumular milhas. Um cartão de milhas premium poderia gerar "
                        f"uma passagem gratuita por ano no seu padrão de uso."
                    ),
                    gain_interval=interval,
                    effort=effort,
                    confidence_score=top_card.confidence_score,
                    priority_score=self._priority(120.0, effort, top_card.confidence_score),
                    tags=["viagem", BenefitTag.TRAVEL.value],
                ))

        elif cluster == "INVESTIDOR_CAUTELOSO":
            top_card = ranked[0] if ranked else None
            if top_card and top_card.annuity_effective > 500:
                effort = InsightEffort.BAIXO
                monthly_savings = top_card.annuity_effective / 12
                interval = InsightInterval(
                    conservative=monthly_savings * 0.8,
                    expected=monthly_savings,
                    optimistic=monthly_savings,
                )
                insights.append(ActionableInsight(
                    type=InsightType.MUDAR_CATEGORIA,
                    title="Anuidade alta reduz seu retorno real",
                    description=(
                        f"Como investidor, cada {brl(top_card.annuity_effective, 0)}/ano em anuidade "
                        f"representa custo de oportunidade. Considere cartões com isenção "
                        f"por volume ou anuidade zero com cashback equivalente."
                    ),
                    gain_interval=interval,
                    effort=effort,
                    confidence_score=top_card.confidence_score,
                    priority_score=self._priority(monthly_savings, effort, top_card.confidence_score),
                    tags=["investidor", "anuidade"],
                ))

        elif cluster == "MICROEMPREENDEDOR":
            top_card = ranked[0] if ranked else None
            if top_card and BenefitTag.CASHBACK in top_card.benefit_tags:
                effort = InsightEffort.BAIXO
                monthly_gain = top_card.net_gain_expected / 12
                interval = self._make_interval(top_card)
                insights.append(ActionableInsight(
                    type=InsightType.MUDAR_CATEGORIA,
                    title="Cashback para separar gastos PJ e PF",
                    description=(
                        f"MEIs se beneficiam de cartões com cashback em compras do negócio. "
                        f"O {top_card.card_name} pode retornar {interval.display_text()} "
                        f"sobre seus gastos mistos."
                    ),
                    gain_interval=interval,
                    effort=effort,
                    confidence_score=top_card.confidence_score,
                    priority_score=self._priority(monthly_gain, effort, top_card.confidence_score),
                    tags=["mei", BenefitTag.CASHBACK.value],
                ))

        elif cluster == "FAMILIA_ESTRUTURADA":
            top_card = ranked[0] if ranked else None
            if top_card and BenefitTag.CASHBACK in top_card.benefit_tags:
                family_spend = (
                    profile.spend_by_category.get("supermercado", 0)
                    + profile.spend_by_category.get("farmacia", 0)
                )
                if family_spend > 300:
                    effort = InsightEffort.BAIXO
                    interval = self._make_interval(top_card)
                    insights.append(ActionableInsight(
                        type=InsightType.MUDAR_CATEGORIA,
                        title="Cashback em supermercado e farmácia",
                        description=(
                            f"Sua família gasta {brl(family_spend, 0)}/mês em supermercado e farmácia. "
                            f"O {top_card.card_name} pode devolver {interval.display_text()} "
                            f"nessas categorias do dia a dia."
                        ),
                        gain_interval=interval,
                        effort=effort,
                        confidence_score=top_card.confidence_score,
                        priority_score=self._priority(interval.expected, effort, top_card.confidence_score),
                        tags=["familia", BenefitTag.CASHBACK.value],
                    ))

        elif cluster == "URBANO_FOODIE":
            top_card = ranked[0] if ranked else None
            food_spend = (
                profile.spend_by_category.get("alimentacao", 0)
                + profile.spend_by_category.get("restaurante", 0)
            )
            if top_card and BenefitTag.CASHBACK in top_card.benefit_tags and food_spend > 400:
                effort = InsightEffort.BAIXO
                interval = self._make_interval(top_card)
                insights.append(ActionableInsight(
                    type=InsightType.MUDAR_CATEGORIA,
                    title="Seu gasto em alimentação merece cashback",
                    description=(
                        f"Você gasta {brl(food_spend, 0)}/mês em alimentação e restaurantes. "
                        f"O {top_card.card_name} pode retornar {interval.display_text()} "
                        f"sobre esses gastos frequentes."
                    ),
                    gain_interval=interval,
                    effort=effort,
                    confidence_score=top_card.confidence_score,
                    priority_score=self._priority(interval.expected, effort, top_card.confidence_score),
                    tags=["alimentacao", BenefitTag.CASHBACK.value],
                ))

        elif cluster == "ESTRESSE_FINANCEIRO":
            # Para perfis estressados: priorizar cartões sem anuidade para reduzir custo fixo.
            free_cards = [r for r in ranked if r.annuity_effective == 0 or r.annuity_waived]
            if free_cards:
                top_free = free_cards[0]
                effort = InsightEffort.BAIXO
                interval = self._make_interval(top_free)
                if interval.expected >= _TRIGGER_GAIN_ATIVAR_BENEFICIO:
                    insights.append(ActionableInsight(
                        type=InsightType.MUDAR_CATEGORIA,
                        title="Cartão sem anuidade reduz custo fixo",
                        description=(
                            f"O {top_free.card_name} não cobra anuidade e ainda pode gerar "
                            f"{interval.display_text()} de retorno — sem comprometer seu orçamento."
                        ),
                        gain_interval=interval,
                        effort=effort,
                        confidence_score=top_free.confidence_score,
                        priority_score=self._priority(interval.expected, effort, top_free.confidence_score),
                        tags=["sem_anuidade", "estresse_financeiro"],
                    ))

        return insights

    def _try_tendencia_insights(
        self,
        ranked_results: list[CardSimulationResult],
        profile: "UserProfile",
    ) -> list[ActionableInsight]:
        """
        Gera insights acionáveis a partir das tendências de categoria e renda.

        Dispara quando uma categoria está SUBINDO ou REEMERGINDO e há um cartão
        ranqueado com benefício relevante nela. Também gera alerta quando a renda
        cai mais de 15% e há um cartão sem anuidade entre os ranqueados.

        Cap de 3 insights por chamada para não criar ruído — os com maior
        priority_score sobrevivem ao filtro do generate().
        """
        trends = getattr(profile, "category_trends", {})
        if not trends or not ranked_results:
            return []

        insights: list[ActionableInsight] = []

        # ── 1. Categorias de gasto em ascensão ───────────────────────────────
        # Ordena por gasto atual decrescente para surfaçar o sinal mais impactante primeiro
        cat_trends = sorted(
            ((cat, data) for cat, data in trends.items() if not cat.startswith("_")),
            key=lambda x: x[1].get("current_monthly", 0.0),
            reverse=True,
        )

        for cat, data in cat_trends:
            if len(insights) >= 2:  # máx 2 insights de categoria
                break
            direction = data.get("direction", "ESTAVEL")
            if direction not in ("SUBINDO", "REEMERGINDO"):
                continue

            current = data.get("current_monthly", 0.0)
            baseline = data.get("baseline_monthly", 0.0)
            ratio = data.get("ratio", 1.0)

            min_spend = 50.0 if direction == "REEMERGINDO" else 100.0
            if current < min_spend:
                continue

            target_tag = _CATEGORY_BENEFIT_MAP.get(cat)
            if target_tag is None:
                continue

            best = next(
                (r for r in ranked_results[:5] if target_tag in r.benefit_tags),
                None,
            )
            if best is None:
                continue

            # Ganho estimado: 2% de cashback sobre o gasto atual na categoria
            gain_monthly = round(current * 0.02, 2)
            interval = InsightInterval(
                conservative=gain_monthly * 0.70,
                expected=gain_monthly,
                optimistic=gain_monthly * 1.50,
            )
            confidence = round(best.confidence_score * (0.75 if direction == "REEMERGINDO" else 0.80), 3)

            if direction == "REEMERGINDO":
                desc = (
                    f"{cat.capitalize()} voltou ao seu padrão: {brl(current, 0)}/mês. "
                    f"O {best.card_name} tem {target_tag.value} que pode retornar "
                    f"{interval.display_text()} nesta categoria."
                )
                title = f"{cat.capitalize()} reapareceu — aproveite o benefício"
            else:
                pct = round((ratio - 1.0) * 100) if ratio != float("inf") else None
                pct_str = f"+{pct}%" if pct is not None else "comportamento novo"
                desc = (
                    f"Seu gasto em {cat} subiu {pct_str} "
                    f"({brl(baseline, 0)} → {brl(current, 0)}/mês). "
                    f"O {best.card_name} tem {target_tag.value} que pode retornar "
                    f"{interval.display_text()} sobre esse crescimento."
                )
                title = f"{cat.capitalize()} em alta — otimize o retorno"

            insights.append(ActionableInsight(
                type=InsightType.MUDAR_CATEGORIA,
                title=title,
                description=desc,
                gain_interval=interval,
                effort=InsightEffort.BAIXO,
                confidence_score=confidence,
                priority_score=self._priority(gain_monthly, InsightEffort.BAIXO, confidence),
                card_id=best.card_id,
                card_name=best.card_name,
                tags=[cat, target_tag.value, "tendencia"],
            ))

        # ── 2. Delivery em crescimento (sinal L2 separado de alimentacao) ─────
        delivery = trends.get("_delivery", {})
        del_direction = delivery.get("direction", "ESTAVEL")
        if del_direction in ("SUBINDO", "REEMERGINDO"):
            del_current = delivery.get("current_monthly", 0.0)
            del_baseline = delivery.get("baseline_monthly", 0.0)
            if del_current >= 50.0:
                best = next(
                    (r for r in ranked_results[:5] if BenefitTag.CASHBACK in r.benefit_tags),
                    None,
                )
                if best:
                    gain_monthly = round(del_current * 0.03, 2)  # delivery cards: ~3% cashback
                    interval = InsightInterval(
                        conservative=gain_monthly * 0.60,
                        expected=gain_monthly,
                        optimistic=gain_monthly * 1.50,
                    )
                    confidence = round(best.confidence_score * 0.75, 3)
                    if del_direction == "REEMERGINDO":
                        desc = (
                            f"Delivery voltou: {brl(del_current, 0)}/mês em iFood/Rappi. "
                            f"O {best.card_name} tem cashback que pode retornar "
                            f"{interval.display_text()}."
                        )
                        title = "Delivery de volta — cashback para recuperar parte do gasto"
                    else:
                        desc = (
                            f"Seus pedidos de delivery cresceram "
                            f"({brl(del_baseline, 0)} → {brl(del_current, 0)}/mês). "
                            f"O {best.card_name} tem cashback que pode retornar "
                            f"{interval.display_text()} sobre esse gasto."
                        )
                        title = "Delivery em alta — cashback para recuperar parte do gasto"
                    insights.append(ActionableInsight(
                        type=InsightType.MUDAR_CATEGORIA,
                        title=title,
                        description=desc,
                        gain_interval=interval,
                        effort=InsightEffort.BAIXO,
                        confidence_score=confidence,
                        priority_score=self._priority(gain_monthly, InsightEffort.BAIXO, confidence),
                        card_id=best.card_id,
                        card_name=best.card_name,
                        tags=["delivery", BenefitTag.CASHBACK.value, "tendencia"],
                    ))

        # ── 3. Renda em queda: recomendar cartão sem anuidade ────────────────
        income = trends.get("_income", {})
        if income.get("direction") == "CAINDO":
            income_ratio = income.get("ratio", 1.0)
            if income_ratio < 0.85:  # queda > 15%
                zero_annuity = [r for r in ranked_results[:8] if r.annuity_effective == 0]
                if zero_annuity:
                    best_free = zero_annuity[0]
                    top_annuity = max(
                        (r.annuity_effective for r in ranked_results[:3]), default=0.0
                    )
                    avoided_monthly = (top_annuity - best_free.annuity_effective) / 12
                    if avoided_monthly > 0:
                        drop_pct = round((1.0 - income_ratio) * 100)
                        hist_income = income.get("baseline_monthly", 0.0)
                        curr_income = income.get("current_monthly", 0.0)
                        interval = InsightInterval(
                            conservative=avoided_monthly * 0.80,
                            expected=avoided_monthly,
                            optimistic=avoided_monthly,
                        )
                        confidence = round(best_free.confidence_score * 0.70, 3)
                        insights.append(ActionableInsight(
                            type=InsightType.MUDAR_CATEGORIA,
                            title="Renda em queda — prefira cartão sem anuidade",
                            description=(
                                f"Sua renda caiu {drop_pct}% nos últimos meses "
                                f"({brl(hist_income, 0)} → {brl(curr_income, 0)}/mês). "
                                f"O {best_free.card_name} não tem anuidade e mantém "
                                f"os benefícios sem comprometer seu orçamento."
                            ),
                            gain_interval=interval,
                            effort=InsightEffort.MEDIO,
                            confidence_score=confidence,
                            priority_score=self._priority(avoided_monthly, InsightEffort.MEDIO, confidence),
                            card_id=best_free.card_id,
                            card_name=best_free.card_name,
                            tags=["renda", "anuidade", "tendencia"],
                        ))

        return insights

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _personalize_description(
        self,
        base_description: str,
        profile: "UserProfile",
        gain_annual: float,
        enable_cluster_tone: bool = True,
    ) -> str:
        """Enriquece o texto do insight com contexto do cluster (T2.6)."""
        if not enable_cluster_tone:
            return base_description
        cluster = getattr(profile, "lifestyle_cluster", "NAO_CLASSIFICADO")
        tone = _CLUSTER_TONE.get(cluster)
        if not tone:
            return base_description
        _desc = base_description[:1].lower() + base_description[1:] if base_description else base_description
        return (
            f"{tone['prefix']}, {_desc} "
            f"Foco em {tone['emphasis']} — equivale a {brl(gain_annual, 0)}/ano."
        )

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
        if tag == BenefitTag.LOUNGE and profile.travel_spend_monthly > TRAVEL_SPEND_THRESHOLD:
            return 70.0  # R$70/uso × ~1 uso/mês
        if tag == BenefitTag.INTERNACIONAL and profile.international_spend_monthly > INTL_SPEND_THRESHOLD:
            return 25.0  # estimativa de economia em IOF
        if tag == BenefitTag.TRAVEL and profile.travel_spend_monthly > 200:
            return 30.0  # seguro viagem e assistência — estimativa conservadora
        if tag == BenefitTag.INSURANCE and profile.travel_spend_monthly > 150:
            return 35.0  # seguro de compra/viagem — custo equivalente de mercado
        if tag == BenefitTag.PREMIUM and profile.monthly_avg_spend > 5000:
            return 80.0  # concierge, sala VIP e benefícios premium
        if tag == BenefitTag.CASHBACK:
            # Usuário com alto gasto em PIX/débito pode migrar para o cartão e capturar cashback
            untapped = profile.monthly_avg_spend * (1.0 - getattr(profile, "credit_spend_ratio", 1.0))
            if untapped > 2000:
                return round(untapped * 0.01, 2)  # conservador: 1% sobre gasto não-crédito
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
