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
    LIFE_STAGE_FAMILIA_BEBE,
    LIFE_STAGE_NOMADE_DIGITAL,
    LIFE_STAGE_INVESTIDOR_PREMIUM,
    LIFE_STAGE_SOLTEIRO_URBANO,
    LIFE_STAGE_NAO_IDENTIFICADO,
    LIFE_STAGE_MIN_CONFIDENCE as _LIFE_STAGE_MIN_CONF,
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

# Cashback estimado por categoria crescente: usado para calcular o bonus de tendência.
# 2% é conservador — um cashback típico em categorias populares; não usa dados do cartão
# para evitar complexidade de lookup, resultando em um bônus de ordenação, não de simulação.
_TREND_CASHBACK_RATE = 0.02

# Mapeamento categoria de gasto → BenefitTag mais relevante (espelhado no InsightGenerator)
_TREND_CATEGORY_BENEFIT: dict[str, BenefitTag] = {
    "alimentacao":   BenefitTag.CASHBACK,
    "supermercado":  BenefitTag.CASHBACK,
    "farmacia":      BenefitTag.CASHBACK,
    "saude":         BenefitTag.CASHBACK,
    "transporte":    BenefitTag.TRAVEL,
    "lazer":         BenefitTag.TRAVEL,
    "viagem":        BenefitTag.TRAVEL,
    "internacional": BenefitTag.INTERNACIONAL,
}


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
        score, benefits_bonus = self._compute_financial_score(result, profile)

        # Bônus por cluster — ajusta relevância de benefícios ao estilo de vida
        cluster = getattr(profile, "lifestyle_cluster", "NAO_CLASSIFICADO")

        if cluster == "EXPLORADOR_GLOBAL":
            if BenefitTag.LOUNGE in result.benefit_tags or BenefitTag.TRAVEL in result.benefit_tags:
                # Adiciona 25% do bonus já computado — NÃO recalcula o score do zero
                # para preservar o desconto de dominância (regra 40%) já aplicado acima.
                score += benefits_bonus * 0.25
            # Viajantes intensos ganham bônus adicional em seguro e milhas
            if getattr(profile, "travel_profile", "OCASIONAL") in ("FREQUENTE", "INTENSO"):
                if BenefitTag.INSURANCE in result.benefit_tags or BenefitTag.TRAVEL in result.benefit_tags:
                    score += benefits_bonus * 0.10

        elif cluster == "URBANO_FOODIE":
            if BenefitTag.CASHBACK in result.benefit_tags:
                food_spend = profile.spend_by_category.get("alimentacao", 0)
                if food_spend > 500:
                    # Foodies GOURMET/ENTUSIASTA valorizam mais o cashback em alimentação
                    foodie_mult = 1.5 if getattr(profile, "foodie_profile", "BASICO") in ("GOURMET", "ENTUSIASTA") else 1.0
                    score += food_spend * 0.005 * foodie_mult

        elif cluster == "INVESTIDOR_CAUTELOSO":
            if result.annuity_effective > 500:
                # Penaliza só quando o ROI não justifica claramente a anuidade (< 2×)
                if result.net_gain_expected < result.annuity_effective * 2.0:
                    score *= 0.90

        elif cluster == "FAMILIA_ESTRUTURADA":
            # Famílias valorizam cashback em supermercado, farmácia e saúde
            if BenefitTag.CASHBACK in result.benefit_tags:
                family_spend = (
                    profile.spend_by_category.get("supermercado", 0)
                    + profile.spend_by_category.get("saude", 0)
                    + profile.spend_by_category.get("educacao", 0)
                )
                if family_spend > 400:
                    score += family_spend * 0.004

        elif cluster == "DIGITAL_NATIVO":
            # Nativos digitais preferem cartões sem anuidade ou com cashback flat
            if result.annuity_effective == 0:
                score += 80
            elif result.annuity_effective <= 200:
                score += 30
            # Penaliza anuidade alta só quando o ROI não justifica (< 2.5×)
            if result.annuity_effective > 500:
                if result.net_gain_expected < result.annuity_effective * 2.5:
                    score *= 0.85

        elif cluster == "MICROEMPREENDEDOR":
            # MEI precisa de cartão sem anuidade ou com isenção fácil — renda PJ irregular
            if result.annuity_effective == 0:
                score += 100
            elif result.annuity_effective <= 200:
                score += 40
            elif result.annuity_effective > 400:
                # Penaliza só quando ROI não compensa (< 2×)
                if result.net_gain_expected < result.annuity_effective * 2.0:
                    score *= 0.80
            # Cashback plano é mais previsível para fluxo de caixa irregular
            if BenefitTag.CASHBACK in result.benefit_tags:
                score += 50

        elif cluster == "ESTRESSE_FINANCEIRO":
            # Usuário em estresse só deve ser direcionado a cartões sem anuidade
            if result.annuity_effective == 0:
                score += 60
            elif result.annuity_effective > 200:
                score *= 0.70

        # Clusters secundários: somente bonuses aditivos (sem penalties) a 50% de peso.
        # Penalties ficam restritas ao cluster primário — identidade principal determina riscos.
        for secondary in getattr(profile, "secondary_clusters", [])[:2]:
            score = self._secondary_cluster_additive_bonus(
                score, benefits_bonus, result, profile, secondary
            )

        # Life stage refinement — sinal mais específico que o cluster, aplicado após os bonuses
        # de cluster para não interferir com a lógica de dominância e penalties existentes.
        score += self._life_stage_score_bonus(result, profile)

        # 3. Penalidade de confiança (multiplicativa após bônus)
        if result.confidence_score < 0.4:
            score *= 0.5

        # 4. Penalidade de elegibilidade (multiplicativa, escalonada)
        if result.eligibility_score < 0.5:
            score *= 0.4
        elif result.eligibility_score < 0.7:
            score *= 0.75

        return score

    def _secondary_cluster_additive_bonus(
        self,
        score: float,
        benefits_bonus: float,
        result: CardSimulationResult,
        profile: UserProfile,
        cluster: str,
    ) -> float:
        """
        Bonuses aditivos de cluster secundário a 50% do peso do primário.

        Não aplica penalties multiplicativas (ex: score *= 0.70) — estas derivam
        da identidade primária e não devem ser duplicadas por sinais secundários.
        INVESTIDOR_CAUTELOSO só tem penalty → nenhum bonus aqui.
        """
        bonus = 0.0

        if cluster == "EXPLORADOR_GLOBAL":
            if BenefitTag.LOUNGE in result.benefit_tags or BenefitTag.TRAVEL in result.benefit_tags:
                bonus += benefits_bonus * 0.25
            travel_profile = getattr(profile, "travel_profile", "OCASIONAL")
            if travel_profile in ("FREQUENTE", "INTENSO"):
                if BenefitTag.INSURANCE in result.benefit_tags or BenefitTag.TRAVEL in result.benefit_tags:
                    bonus += benefits_bonus * 0.10

        elif cluster == "URBANO_FOODIE":
            if BenefitTag.CASHBACK in result.benefit_tags:
                food_spend = profile.spend_by_category.get("alimentacao", 0)
                if food_spend > 500:
                    foodie_mult = (
                        1.5 if getattr(profile, "foodie_profile", "BASICO") in ("GOURMET", "ENTUSIASTA")
                        else 1.0
                    )
                    bonus += food_spend * 0.005 * foodie_mult

        elif cluster == "FAMILIA_ESTRUTURADA":
            if BenefitTag.CASHBACK in result.benefit_tags:
                family_spend = (
                    profile.spend_by_category.get("supermercado", 0)
                    + profile.spend_by_category.get("saude", 0)
                    + profile.spend_by_category.get("educacao", 0)
                )
                if family_spend > 400:
                    bonus += family_spend * 0.004

        elif cluster == "DIGITAL_NATIVO":
            if result.annuity_effective == 0:
                bonus += 80
            elif result.annuity_effective <= 200:
                bonus += 30

        elif cluster == "MICROEMPREENDEDOR":
            if result.annuity_effective == 0:
                bonus += 100
            elif result.annuity_effective <= 200:
                bonus += 40
            if BenefitTag.CASHBACK in result.benefit_tags:
                bonus += 50

        elif cluster == "ESTRESSE_FINANCEIRO":
            if result.annuity_effective == 0:
                bonus += 60

        return score + bonus * 0.50

    def _life_stage_score_bonus(
        self,
        result: CardSimulationResult,
        profile: UserProfile,
    ) -> float:
        """
        Bônus aditivo baseado no estágio de vida detectado.

        Refinamento sobre os bônus de cluster: usa sinais mais específicos de comportamento.
        Valores na mesma escala que net_gain_expected (R$/ano) — pequenos bonuses de R$10-80
        para ajustar a ordenação entre cartões tecnicamente equivalentes.
        Escalado pela life_stage_confidence para que sinais fracos não distorçam o ranking.
        Só ativa quando confidence ≥ LIFE_STAGE_MIN_CONFIDENCE (0.50).
        """
        life_stage = getattr(profile, "life_stage", LIFE_STAGE_NAO_IDENTIFICADO)
        conf = getattr(profile, "life_stage_confidence", 0.0)

        if life_stage == LIFE_STAGE_NAO_IDENTIFICADO or conf < _LIFE_STAGE_MIN_CONF:
            return 0.0

        bonus = 0.0

        if life_stage == LIFE_STAGE_FAMILIA_BEBE:
            if BenefitTag.CASHBACK in result.benefit_tags:
                family_spend = (
                    profile.spend_by_category.get("farmacia", 0.0)
                    + profile.spend_by_category.get("supermercado", 0.0)
                )
                if family_spend > 200:
                    bonus = family_spend * 0.006  # ~R$14/ano por R$200/mês em família

        elif life_stage == LIFE_STAGE_NOMADE_DIGITAL:
            if BenefitTag.INTERNACIONAL in result.benefit_tags:
                bonus += 80  # economia de IOF para nômade (R$/ano)
            if BenefitTag.TRAVEL in result.benefit_tags:
                travel = getattr(profile, "travel_spend_monthly", 0.0)
                if travel > 300:
                    bonus += travel * 0.004  # ~R$14/ano por R$300/mês

        elif life_stage == LIFE_STAGE_INVESTIDOR_PREMIUM:
            # Premia ROI claro; penaliza anuidade alta sem retorno proporcional
            if result.annuity_effective == 0:
                bonus = 60
            elif result.net_gain_expected >= result.annuity_effective * 2.0:
                bonus = 50  # anuidade claramente justificada
            elif result.annuity_effective > 600 and result.net_gain_expected < result.annuity_effective * 1.5:
                bonus = -70  # custo de oportunidade > retorno esperado

        elif life_stage == LIFE_STAGE_SOLTEIRO_URBANO:
            if BenefitTag.CASHBACK in result.benefit_tags:
                trends = getattr(profile, "category_trends", {})
                delivery = trends.get("_delivery", {}).get("current_monthly", 0.0)
                food = profile.spend_by_category.get("alimentacao", 0.0)
                urban_spend = max(delivery, 0.0) + food
                if urban_spend > 300:
                    bonus += urban_spend * 0.005  # ~R$18/ano por R$300/mês
            if result.annuity_effective == 0:
                bonus += 30

        return bonus * conf  # escala pelo confidence do estágio

    # ── Score base sem cluster (usado pelo hyperscore para evitar double-counting) ──

    def _compute_financial_score(
        self, result: CardSimulationResult, profile: UserProfile
    ) -> tuple[float, float]:
        """Retorna (score_com_benefícios, benefits_bonus): liquidez + regra 40%, sem cluster nem penalidades."""
        multiplier = _LIQUIDITY_MULTIPLIER.get(result.liquidity_risk, 1.0)

        # Ordena pelo ganho CONSERVADOR (P25 para milhas), não pelo esperado.
        # O usuário continua vendo net_gain_expected — mas a decisão de qual
        # cartão fica em primeiro lugar não pode ser inclinada por uma
        # estimativa de milha no ponto médio de uma banda que chega a 3x,
        # concorrendo com cashback, que é valor certo.
        #
        # Cartão de cashback tem conservative == expected, então nada muda
        # para ele. Fallback para expected mantém compatibilidade com
        # simulações antigas/serializadas sem o campo novo.
        base_gain = getattr(result, "net_gain_conservative", None)
        if not base_gain:
            base_gain = result.net_gain_expected
        score = base_gain * multiplier

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
        if benefits_bonus > 0 and result.net_gain_expected > 0:
            if benefits_bonus > _BENEFIT_DOMINANCE_THRESHOLD * result.net_gain_expected:
                benefits_bonus *= _BENEFIT_DOMINANCE_DISCOUNT
        score += benefits_bonus

        # Bônus/penalidade por tendência de categoria — não entra em benefits_bonus
        # para não interferir com a regra de dominância 40% já computada acima.
        score += self._trend_bonus(result, profile)

        return score, benefits_bonus

    def _trend_bonus(self, result: CardSimulationResult, profile: UserProfile) -> float:
        """
        Bônus aditivo para categorias em crescimento e penalidade para renda em queda.

        Categorias SUBINDO/REEMERGINDO: eleva o score de cartões com BenefitTag
        relevante proporcionalmente ao cashback estimado sobre o incremento de gasto.
        O bônus é anualizado (net_gain_expected é anual) e cap em R$300/ano por categoria
        para não dominar o score financeiro.

        Renda CAINDO: aplica penalidade em cartões com anuidade > R$400/ano,
        proporcional à intensidade da queda. Penalidade cap em 20% da anuidade.
        """
        trends = getattr(profile, "category_trends", {})
        if not trends:
            return 0.0

        bonus = 0.0

        for cat, data in trends.items():
            if cat.startswith("_"):
                continue
            direction = data.get("direction", "ESTAVEL")
            if direction not in ("SUBINDO", "REEMERGINDO"):
                continue
            target_tag = _TREND_CATEGORY_BENEFIT.get(cat)
            if target_tag is None or target_tag not in result.benefit_tags:
                continue
            current_monthly = data.get("current_monthly", 0.0)
            if current_monthly < 50.0:
                continue

            ratio = data.get("ratio", 1.0)
            effective_ratio = 1.3 if ratio == float("inf") else min(ratio, 2.0)  # REEMERGINDO → +30%
            increment_monthly = current_monthly * max(effective_ratio - 1.0, 0.0)
            cat_bonus_annual = min(increment_monthly * _TREND_CASHBACK_RATE * 12, 300.0)
            bonus += cat_bonus_annual

        # Penalidade: renda caindo + anuidade alta → cartão mais arriscado agora
        income_data = trends.get("_income", {})
        if income_data.get("direction") == "CAINDO" and result.annuity_effective > 400:
            income_ratio = income_data.get("ratio", 1.0)
            drop = max(1.0 - income_ratio, 0.0)  # ex: ratio=0.80 → drop=0.20
            penalty = min(result.annuity_effective * drop * 0.5, result.annuity_effective * 0.20)
            bonus -= penalty

        return bonus

    def _compute_base_score(self, result: CardSimulationResult, profile: UserProfile) -> float:
        """
        Score financeiro puro: liquidez + benefícios + penalidades, SEM bônus de cluster.
        Usado por _compute_hyperscore como W2, para que W1 (cluster relevance) não
        duplique o ajuste que _compute_score já faria pelo cluster.
        """
        score, _ = self._compute_financial_score(result, profile)
        if result.confidence_score < 0.4:
            score *= 0.5
        if result.eligibility_score < 0.5:
            score *= 0.4
        elif result.eligibility_score < 0.7:
            score *= 0.75
        return score

    # ── Ranker hiperpersonalizado (T2.4) ─────────────────────────────────────

    # Valor de normalização para W2: R$3.000/ano ≈ ganho de um cartão premium brasileiro.
    # Cartões acima desse valor recebem score W2 = 1.0 (sem penalidade — são ótimos).
    _W2_NORMALIZATION = 3000.0

    def rank_hyperpersonalized(
        self,
        results: list[CardSimulationResult],
        profile: UserProfile,
    ) -> list[CardSimulationResult]:
        """
        Ranker hiperpersonalizado com 4 pesos (melhorias_analise_perfil.md §8.1):
            W1 = relevância ao cluster (40%)   → normalizado 0-100
            W2 = impacto financeiro (30%)       → normalizado 0-100 (ref: R$3k/ano)
            W3 = propensity estimada (20%)      → normalizado 0-100
            W4 = timing/adequação momento (10%) → normalizado 0-100

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
        """
        Score composto 0-100 com 4 pesos genuínos.

        W2 usa _compute_base_score (sem bônus de cluster) para evitar que o
        cluster seja contado duas vezes — uma vez em W1 e outra em W2.
        Todos os componentes são normalizados para 0-100 antes da ponderação.
        """
        cluster = getattr(profile, "lifestyle_cluster", "NAO_CLASSIFICADO")

        # W1: relevância ao cluster primário + boost de clusters secundários.
        # Para secundários: apenas o excesso acima do baseline neutro (0.5) contribui,
        # a 35% de peso — garante que clusters periféricos não sobrescrevam o primário.
        primary_rel = self._cluster_relevance(result, profile, cluster)
        for sec in getattr(profile, "secondary_clusters", [])[:2]:
            sec_rel = self._cluster_relevance(result, profile, sec)
            above_neutral = max(sec_rel - 0.5, 0.0)
            primary_rel = min(primary_rel + above_neutral * 0.35, 1.0)
        w1 = primary_rel * 100

        # W2: impacto financeiro sem cluster (R$/ano) normalizado por R$3k → 0-100
        base = self._compute_base_score(result, profile)
        w2 = min(max(base, 0.0) / self._W2_NORMALIZATION, 1.0) * 100

        # W3: propensity (0-1) → 0-100
        w3 = self._estimate_propensity(result, profile) * 100

        # W4: timing (0-1) → 0-100
        w4 = self._calc_timing_score(result, profile) * 100

        # Life stage micro-ajuste (bônus bruto normalizado, cap ±10 pts na escala 0-100)
        life_bonus = self._life_stage_score_bonus(result, profile)
        life_bonus_normalized = min(max(life_bonus / 100.0, -0.10), 0.10) * 100

        return 0.40 * w1 + 0.30 * w2 + 0.20 * w3 + 0.10 * w4 + life_bonus_normalized

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
            base_relevance = 0.3 + tag_overlap * 0.7
            # Viajantes INTENSO/FREQUENTE têm relevância elevada em travel tags
            travel_profile = getattr(profile, "travel_profile", "OCASIONAL")
            if travel_profile == "INTENSO":
                relevance = min(base_relevance * 1.15, 1.0)
            elif travel_profile == "FREQUENTE":
                relevance = min(base_relevance * 1.08, 1.0)
            else:
                relevance = base_relevance

        elif cluster == "URBANO_FOODIE":
            if BenefitTag.CASHBACK in result.benefit_tags:
                # Foodies mais intensos têm relevância maior em cashback
                foodie_profile = getattr(profile, "foodie_profile", "BASICO")
                if foodie_profile == "ENTUSIASTA":
                    relevance = 0.95
                elif foodie_profile == "GOURMET":
                    relevance = 0.88
                elif foodie_profile == "APRECIADOR":
                    relevance = 0.80
                else:
                    relevance = 0.72
            else:
                relevance = 0.3

        elif cluster == "INVESTIDOR_CAUTELOSO":
            if result.annuity_effective == 0:
                relevance = 0.9
            elif result.annuity_effective <= 300:
                relevance = 0.65
            else:
                # Anuidade alta: relevância padrão baixa, mas ROI forte eleva
                if result.net_gain_expected >= result.annuity_effective * 2.0:
                    relevance = 0.65  # fee claramente justificada
                else:
                    relevance = 0.3

        elif cluster == "ESTRESSE_FINANCEIRO":
            relevance = 0.9 if result.annuity_effective == 0 else 0.2

        elif cluster == "FAMILIA_ESTRUTURADA":
            if BenefitTag.CASHBACK in result.benefit_tags:
                relevance = 0.85
            elif result.annuity_effective == 0:
                relevance = 0.70
            else:
                relevance = 0.40

        elif cluster == "DIGITAL_NATIVO":
            if result.annuity_effective == 0:
                relevance = 0.90
            elif result.annuity_effective <= 200 and BenefitTag.CASHBACK in result.benefit_tags:
                relevance = 0.65
            else:
                # Anuidade alta: relevância baixa, mas ROI muito forte eleva
                if result.net_gain_expected >= result.annuity_effective * 2.5:
                    relevance = 0.60
                else:
                    relevance = 0.30

        elif cluster == "MICROEMPREENDEDOR":
            # MEI prioriza: sem anuidade > cashback plano > anuidade baixa
            if result.annuity_effective == 0 and BenefitTag.CASHBACK in result.benefit_tags:
                relevance = 0.95
            elif result.annuity_effective == 0:
                relevance = 0.85
            elif result.annuity_effective <= 200 and BenefitTag.CASHBACK in result.benefit_tags:
                relevance = 0.65
            elif result.annuity_effective <= 200:
                relevance = 0.50
            else:
                if result.net_gain_expected >= result.annuity_effective * 2.0:
                    relevance = 0.55
                else:
                    relevance = 0.20

        # Override global: gasto real de viagem eleva floor de relevância para cartões de viagem
        # Garante que viajantes frequentes recebam recomendações premium mesmo em clusters conservadores
        travel_tags = {BenefitTag.LOUNGE, BenefitTag.TRAVEL, BenefitTag.INSURANCE}
        user_travel_monthly = getattr(profile, "travel_spend_monthly", 0.0)
        if (
            user_travel_monthly > _TRAVEL_SPEND_THRESHOLD
            and bool(travel_tags & set(result.benefit_tags))
            and result.net_gain_expected > 0
        ):
            relevance = max(relevance, 0.65)

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
        # Quem poupa mais tem mais folga para pagar anuidade — maior propensão
        savings_rate = getattr(profile, "savings_rate", 0.0)
        if savings_rate >= 20:
            propensity += 0.10
        elif savings_rate >= 10:
            propensity += 0.05
        elif savings_rate < 0:
            propensity -= 0.10
        # Alto gasto em assinaturas sinaliza cartão com muitos benefícios mensais cobrados —
        # usuário já tem bastante comprometimento fixo, menor propensão a mais anuidade
        sub_burn = getattr(profile, "subscription_burn_monthly", 0.0)
        if sub_burn > 150 and result.annuity_effective > 300:
            propensity -= 0.08
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
        # Usuários mais resilientes têm timing melhor para cartões com anuidade
        resilience = getattr(profile, "resilience_score", 50.0)
        if resilience >= 70 and result.annuity_effective > 0:
            timing = min(timing + 0.15, 1.0)
        elif resilience < 30 and result.annuity_effective > 200:
            timing = max(timing - 0.20, 0.0)
        return round(timing, 3)
