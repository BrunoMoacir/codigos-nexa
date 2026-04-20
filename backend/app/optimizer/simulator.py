# app/optimizer/simulator.py
# CardSimulator — calcula retorno financeiro de cada cartão para o perfil do usuário
# Camada 2 (Scoring) + Camada 3 Anti-FP (Card Optimizer v2.1)

from __future__ import annotations

import logging

from app.optimizer.constants import TRAVEL_SPEND_THRESHOLD
from app.optimizer.miles_valuator import get_valuator
from app.optimizer.models import (
    BenefitTag,
    CardRecord,
    CardROIVerdict,
    CardSimulationResult,
    CardType,
    CurrentCardROI,
)
from app.optimizer.profiler import UserProfile
from app.optimizer.validators.liquidity_checker import LiquidityChecker

logger = logging.getLogger(__name__)

# Fatores de variação para os 3 cenários (±20% do gasto base)
_SCENARIO_FACTORS: dict[str, float] = {
    "min": 0.8,
    "expected": 1.0,
    "max": 1.2,
}

# Threshold de achievability para isenção de anuidade (v2.1 — antes era binário)
# Projeção de gasto anual deve atingir ≥ 80% de probabilidade de alcançar o threshold
_WAIVER_ACHIEVABILITY_GATE = 0.80

_liquidity_checker = LiquidityChecker()


# ─── BenefitViabilityFilter (Camada 3) ────────────────────────────────────────

class BenefitViabilityFilter:
    """
    Hard blocks em benefícios que o perfil do usuário não viabiliza.

    Benefícios bloqueados têm monthly_value = 0.00 — não podem compensar anuidade alta.
    Proxies usados quando não há campo direto (ex: flights_per_year):
        - travel_spend_monthly > TRAVEL_SPEND_THRESHOLD → flights_per_year ≥ 4 (proxy)
        - travel_spend_monthly > 0   → flights_per_year ≥ 1 (proxy mínimo)
        - international_spend_monthly > 50 → has_international_spend
    """

    # tag → condição que bloqueia completamente o benefício
    HARD_BLOCKS: dict[BenefitTag, object] = {
        BenefitTag.LOUNGE: lambda profile: profile.travel_spend_monthly < TRAVEL_SPEND_THRESHOLD,
        BenefitTag.INTERNACIONAL: lambda profile: profile.international_spend_monthly < 50,
    }

    def is_blocked(self, tag: BenefitTag, profile: UserProfile) -> bool:
        condition = self.HARD_BLOCKS.get(tag)
        if condition is None:
            return False
        return condition(profile)

    def filter_bonus_tags(
        self, benefit_tags: list[BenefitTag], profile: UserProfile
    ) -> list[BenefitTag]:
        """Retorna apenas as tags de benefício que passam no filtro de viabilidade."""
        return [t for t in benefit_tags if not self.is_blocked(t, profile)]


_benefit_filter = BenefitViabilityFilter()


class CardSimulator:
    """
    Calcula o retorno financeiro real de cada cartão para o perfil específico do usuário.

    Simula 3 cenários de gasto (pessimista/esperado/otimista) e calcula:
    - Anuidade efetiva (com verificação de isenção)
    - Valor dos pontos ou cashback
    - Ganho líquido por cenário
    - Impacto de liquidez
    - Confidence score
    - Âncoras e justificativas para o LLM
    """

    def simulate(
        self,
        card: CardRecord,
        profile: UserProfile,
        safe_to_spend: float | None = None,
    ) -> CardSimulationResult:
        """
        Simula o retorno do cartão para o perfil dado.

        Args:
            card: Cartão a ser simulado (CardRecord da base de conhecimento).
            profile: Perfil de consumo do usuário (output do ConsumptionProfiler).
            safe_to_spend: Margem diária disponível da F1 (opcional; sem ela
                           o liquidity_impact não pode ser calculado).

        Returns:
            CardSimulationResult com todos os campos financeiros preenchidos.
            eligibility_score e eligibility_reasons são deixados nos defaults (0.0 / [])
            e preenchidos pelo OptimizerService via CardKnowledgeBase.
        """
        spend_annual = profile.monthly_avg_spend * profile.credit_spend_ratio * 12

        annuity_effective, annuity_waived = self._compute_annuity(card, spend_annual)

        values = {
            scenario: self._compute_benefit_value(card, spend_annual * factor, profile, scenario)
            for scenario, factor in _SCENARIO_FACTORS.items()
        }

        net_gain_min = values["min"] - annuity_effective
        net_gain_expected = values["expected"] - annuity_effective
        net_gain_max = values["max"] - annuity_effective

        liquidity_impact = self._compute_liquidity_impact(annuity_effective, safe_to_spend)
        liquidity_risk = _liquidity_checker.check(liquidity_impact)

        confidence_score = self._compute_confidence(card, profile)

        spending_anchor = self._build_spending_anchor(profile)
        profile_match_reasons = self._build_match_reasons(
            card, profile, spend_annual, annuity_effective, annuity_waived, values["expected"]
        )
        explanation_steps = self._build_explanation_steps(
            card, profile, spend_annual, annuity_effective, annuity_waived, values, net_gain_expected
        )

        waiver_threshold = (
            card.waiver_rules.threshold
            if card.waiver_rules.type == "spend_threshold" and card.waiver_rules.threshold
            else None
        )

        return CardSimulationResult(
            card_id=card.card_id,
            card_name=card.name,
            issuer=card.issuer,
            flag=card.flag,
            annuity_effective=round(annuity_effective, 2),
            annuity_waived=annuity_waived,
            points_value_min=round(values["min"], 2),
            points_value_expected=round(values["expected"], 2),
            points_value_max=round(values["max"], 2),
            net_gain_min=round(net_gain_min, 2),
            net_gain_expected=round(net_gain_expected, 2),
            net_gain_max=round(net_gain_max, 2),
            liquidity_impact=round(liquidity_impact, 4),
            liquidity_risk=liquidity_risk,
            confidence_score=round(confidence_score, 4),
            eligibility_score=0.0,
            eligibility_reasons=[],
            profile_match_reasons=profile_match_reasons,
            spending_anchor=spending_anchor,
            explanation_steps=explanation_steps,
            benefit_highlights=card.benefits_detail[:3],
            benefit_tags=list(card.benefit_tags),
            waiver_threshold=waiver_threshold,
        )

    # ─── Helpers privados ─────────────────────────────────────────────────────

    def _compute_annuity(self, card: CardRecord, spend_annual: float) -> tuple[float, bool]:
        """
        Retorna (annuity_effective, annuity_waived).

        WaiverAchievabilityCheck (v2.1): a isenção só é marcada como True se a
        projeção de gasto anual tiver ≥ 80% de probabilidade de atingir o threshold.
        Abaixo de 80%, a anuidade é cobrada integralmente (conservador).
        """
        wr = card.waiver_rules

        if wr.type == "always_free":
            return 0.0, True

        if wr.type == "spend_threshold" and wr.threshold is not None:
            achievability = self._compute_waiver_achievability(spend_annual, wr.threshold)
            if achievability >= _WAIVER_ACHIEVABILITY_GATE:
                return 0.0, True
            return card.base_annuity, False

        # "transaction_count": conservador — assume que o usuário não atingirá o threshold
        # "none" ou desconhecido: anuidade sempre cobrada
        return card.base_annuity, False

    def _compute_waiver_achievability(self, spend_annual: float, threshold: float) -> float:
        """
        Calcula a probabilidade (0–1) de o gasto anual projetado atingir o threshold de isenção.

        Fórmula: achievability = max(0, 1 − gap / threshold)
        onde gap = threshold − projected_annual (quanto falta).

        Um gap negativo (gasto acima do threshold) retorna 1.0.
        """
        if threshold <= 0:
            return 1.0
        gap = threshold - spend_annual
        return max(0.0, 1.0 - gap / threshold)

    def _compute_benefit_value(
        self,
        card: CardRecord,
        spend_annual_scaled: float,
        profile: "UserProfile | None" = None,
        scenario: str = "expected",
    ) -> float:
        """Calcula o valor monetário dos benefícios para um dado gasto anual.

        M2.3: Para cartões POINTS com `loyalty_program` definido, usa o
        MilesValuator para aplicar taxa de conversão dinâmica por cenário de
        resgate (pessimistic/expected/optimistic). Sem loyalty_program, usa
        points_conversion_rate fixo do CardRecord (compatibilidade retroativa).

        M2.5: Se o cartão tem `cashback_categories` definidas, usa taxas por
        categoria cruzando com o `profile.spend_by_category`. Para categorias
        sem regra específica, aplica `cashback_default_pct` (ou `cashback_pct`
        como fallback). Quando não há perfil disponível, distribui o gasto
        total uniformemente como antes (compatibilidade retroativa).

        Convenção de unidade (obrigatória em knowledge_cards.json):
            points_conversion_rate = R$ por 1.000 pontos/milhas.
        """
        if card.card_type == CardType.POINTS:
            if not card.points_per_brl:
                return 0.0
            # M2.3: valoração dinâmica via programa de fidelidade
            if card.loyalty_program:
                value = get_valuator().compute_points_value(
                    card.points_per_brl, spend_annual_scaled, card.loyalty_program, scenario
                )
                if value > 0:
                    return value
            # Fallback: taxa fixa do CardRecord
            if card.points_conversion_rate == 0:
                return 0.0
            points = spend_annual_scaled * card.points_per_brl
            return (points / 1000) * card.points_conversion_rate

        if card.card_type in (CardType.CASHBACK, CardType.INVESTBACK):
            # M2.5: usar taxas por categoria quando disponíveis + perfil conhecido
            if card.cashback_categories and profile is not None:
                return self._compute_category_cashback(card, profile, spend_annual_scaled)

            # Fallback: cashback flat (comportamento original)
            flat_pct = card.cashback_pct
            if flat_pct is None:
                return 0.0
            value = spend_annual_scaled * flat_pct
            if card.cashback_cap:
                value = min(value, card.cashback_cap * 12)
            return value

        return 0.0

    def _compute_category_cashback(
        self,
        card: CardRecord,
        profile: "UserProfile",
        spend_annual_scaled: float,
    ) -> float:
        """M2.5 — Calcula cashback usando regras diferenciadas por categoria.

        Para cada categoria no perfil do usuário:
          1. Busca regra específica em card.cashback_categories
          2. Se encontrar: aplica pct da regra, respeitando cap_monthly anualizado
          3. Se não encontrar: aplica cashback_default_pct (ou cashback_pct como fallback)

        O spend_annual_scaled é usado para escalar proporcionalmente o gasto
        de cada categoria (mantém a distribuição relativa do perfil).
        """
        from app.optimizer.models import CashbackCategoryRule

        # Fator de escala: spend_annual_scaled / soma real das categorias
        total_category_spend = sum(profile.spend_by_category.values())
        scale = (spend_annual_scaled / 12) / total_category_spend if total_category_spend > 0 else 1.0

        # Índice de regras por categoria para lookup O(1)
        category_rules: dict[str, CashbackCategoryRule] = {
            rule.category: rule for rule in card.cashback_categories
        }

        # Taxa padrão para categorias não cobertas
        default_pct = card.cashback_default_pct or card.cashback_pct or 0.0

        total_cashback = 0.0
        for category, monthly_spend in profile.spend_by_category.items():
            scaled_monthly = monthly_spend * scale
            rule = category_rules.get(category)
            if rule:
                monthly_cb = scaled_monthly * rule.pct
                if rule.cap_monthly is not None:
                    monthly_cb = min(monthly_cb, rule.cap_monthly)
            else:
                monthly_cb = scaled_monthly * default_pct
            total_cashback += monthly_cb * 12  # anualizar

        # Teto geral do cartão (se definido)
        if card.cashback_cap:
            total_cashback = min(total_cashback, card.cashback_cap * 12)

        return total_cashback

    def _compute_liquidity_impact(
        self, annuity_effective: float, safe_to_spend: float | None
    ) -> float:
        """
        Calcula a fração da margem mensal comprometida pela parcela da anuidade.

        Retorna 0.0 se a anuidade for zero (independente do safe_to_spend).
        Retorna 1.0 se safe_to_spend for None, zero ou negativo e houver anuidade.

        Limitação conhecida: quando safe_to_spend=None (F1 não disponível),
        todos os cartões com anuidade recebem liquidity_impact=1.0 → CRITICAL,
        o que o CardRanking penaliza em 80%. O OptimizerService deve usar
        monthly_income como fallback antes de chamar o simulador para evitar
        que recomendações úteis desapareçam por falta de dado de liquidez.
        """
        if annuity_effective == 0.0:
            return 0.0
        if not safe_to_spend or safe_to_spend <= 0:
            return 1.0
        return (annuity_effective / 12) / safe_to_spend

    def _compute_confidence(self, card: CardRecord, profile: UserProfile) -> float:
        """
        ConfidenceScorer — confiança na simulação (0.0–1.0).

        Fórmula multiplicativa (v2.1 — alinhado com arquitetura):
            confidence = data_trust_score
                       × coverage_penalty     (por faixa de meses)
                       × commitment_penalty   (× 0.7 se > 80% comprometido)
                       × income_confidence    (da hierarquia do IncomeProfiler)
                       × stability_factor     (por faixa de CV)

        Penalidades de cobertura:
            ≥ 6 meses: sem penalidade
            3–5 meses: × 0.85
            2 meses:   × 0.50
            < 2 meses: × 0.25 (não bloqueado aqui; gate está no OptimizerService)

        Penalidades de CV (spend_stability_cv):
            ≤ 0.15: sem penalidade
            0.15–0.35: × 0.90
            0.35–0.60: × 0.75
            > 0.60:    × 0.60
        """
        score = card.data_trust_score

        # Coverage penalty (por faixa de meses)
        months = profile.data_coverage_months
        if months >= 6:
            pass
        elif months >= 3:
            score *= 0.85
        elif months >= 2:
            score *= 0.50
        else:
            score *= 0.25

        # Commitment penalty
        if profile.committed_percentage > 0.8:
            score *= 0.7

        # Income confidence (da hierarquia do IncomeProfiler)
        income_conf = getattr(profile.income_profile, "confidence", 1.0) or 1.0
        score *= income_conf

        # Spend stability factor — baseado no CV puro (v2.1)
        cv = getattr(profile, "spend_stability_cv", 1.0 - profile.spending_stability)
        if cv <= 0.15:
            pass
        elif cv <= 0.35:
            score *= 0.90
        elif cv <= 0.60:
            score *= 0.75
        else:
            score *= 0.60

        return min(round(score, 4), 1.0)

    def _top_categories(self, profile: UserProfile, n: int = 3) -> list[str]:
        """Retorna as N categorias com maior gasto médio mensal."""
        sorted_cats = sorted(
            profile.spend_by_category.items(), key=lambda x: x[1], reverse=True
        )
        return [cat for cat, _ in sorted_cats[:n]]

    def _build_spending_anchor(self, profile: UserProfile) -> dict:
        """Ancora o cálculo no gasto real observado para uso do LLM."""
        return {
            "debit_monthly": profile.spend_by_source.get("debit", 0.0),
            "credit_monthly": profile.spend_by_source.get("credit", 0.0),
            "total_monthly": profile.monthly_avg_spend,
            "main_categories": self._top_categories(profile),
            "international_monthly": profile.international_spend_monthly,
            "travel_monthly": profile.travel_spend_monthly,
        }

    def _build_match_reasons(
        self,
        card: CardRecord,
        profile: UserProfile,
        spend_annual: float,
        annuity_effective: float,
        annuity_waived: bool,
        expected_value: float,
    ) -> list[str]:
        """Razões em linguagem natural explicando por que este cartão se encaixa no perfil."""
        reasons: list[str] = []

        # Isenção de anuidade pelo volume de gastos
        if annuity_waived and card.base_annuity > 0:
            threshold = card.waiver_rules.threshold or 0
            reasons.append(
                f"Seu gasto anual projetado de R$ {spend_annual:,.0f} "
                f"isenta a anuidade de R$ {card.base_annuity:,.0f}"
                + (f" (threshold: R$ {threshold:,.0f})" if threshold else "")
            )

        # Cashback em categoria relevante — M2.5 ou flat
        if card.card_type in (CardType.CASHBACK, CardType.INVESTBACK):
            if card.cashback_categories:
                # M2.5: mostrar as duas maiores taxas por categoria
                rules_by_pct = sorted(card.cashback_categories, key=lambda r: r.pct, reverse=True)
                highlights = [f"{r.category} {r.pct * 100:.0f}%" for r in rules_by_pct[:2]]
                if highlights:
                    reasons.append(
                        f"Cashback diferenciado por categoria: {', '.join(highlights)}"
                        + (" e outras" if len(rules_by_pct) > 2 else "")
                    )
            elif card.cashback_pct:
                top_cats = self._top_categories(profile, n=3)
                for cat in top_cats:
                    cat_spend = profile.spend_by_category.get(cat, 0.0)
                    if cat_spend > 100:
                        annual_cashback = cat_spend * 12 * card.cashback_pct
                        reasons.append(
                            f"Seu gasto médio de R$ {cat_spend:,.0f}/mês em {cat} "
                            f"rende {card.cashback_pct * 100:.0f}% de cashback "
                            f"= R$ {annual_cashback:,.0f}/ano"
                        )
                        break

        # Gasto internacional expressivo
        if profile.international_spend_monthly > 300 and BenefitTag.INTERNACIONAL in card.benefit_tags:
            reasons.append(
                f"Seu gasto de R$ {profile.international_spend_monthly:,.0f}/mês no exterior "
                f"se beneficia do câmbio diferenciado e zero IOF deste cartão"
            )

        # Frequência de viagens + acesso a lounge
        if profile.travel_spend_monthly > 600 and BenefitTag.LOUNGE in card.benefit_tags:
            reasons.append(
                f"Com seus gastos de R$ {profile.travel_spend_monthly:,.0f}/mês em viagens, "
                f"o acesso a salas VIP incluso pode valer R$ 500/ano ou mais"
            )

        return reasons

    def _build_explanation_steps(
        self,
        card: CardRecord,
        profile: UserProfile,
        spend_annual: float,
        annuity_effective: float,
        annuity_waived: bool,
        values: dict[str, float],
        net_gain_expected: float,
    ) -> list[str]:
        """Passo a passo do cálculo para transparência ao usuário."""
        steps: list[str] = []
        months = profile.data_coverage_months

        steps.append(
            f"Gasto mensal observado: R$ {profile.monthly_avg_spend:,.2f} "
            f"(média dos últimos {months} {'mês' if months == 1 else 'meses'})"
        )
        steps.append(
            f"Gasto anual projetado: R$ {profile.monthly_avg_spend:,.2f} × 12 "
            f"= R$ {spend_annual:,.2f}"
        )

        if annuity_waived:
            threshold = card.waiver_rules.threshold
            if threshold:
                steps.append(
                    f"Anuidade: isenta — gasto anual de R$ {spend_annual:,.0f} "
                    f"≥ threshold de R$ {threshold:,.0f}"
                )
            else:
                steps.append("Anuidade: sem cobrança (sempre isento)")
        else:
            steps.append(f"Anuidade: R$ {annuity_effective:,.2f}/ano")

        if card.card_type == CardType.POINTS and card.points_per_brl:
            pts_annual = spend_annual * card.points_per_brl
            steps.append(
                f"Pontos gerados: R$ {spend_annual:,.0f} × {card.points_per_brl} "
                f"= {pts_annual:,.0f} pontos/ano"
            )
            # M2.3: usar taxa real do MilesValuator (P50) em vez do fallback estático
            if card.loyalty_program:
                dynamic_rate = get_valuator().get_rate(card.loyalty_program, "expected")
                if dynamic_rate:
                    steps.append(
                        f"Valor dos pontos ({card.loyalty_program} P50): "
                        f"{pts_annual:,.0f} ÷ 1.000 × R$ {dynamic_rate:.1f} "
                        f"= R$ {values['expected']:,.2f}/ano"
                    )
                else:
                    steps.append(
                        f"Valor dos pontos: {pts_annual:,.0f} ÷ 1.000 "
                        f"× R$ {card.points_conversion_rate} "
                        f"= R$ {values['expected']:,.2f}/ano"
                    )
            else:
                steps.append(
                    f"Valor dos pontos: {pts_annual:,.0f} ÷ 1.000 "
                    f"× R$ {card.points_conversion_rate} "
                    f"= R$ {values['expected']:,.2f}/ano"
                )
        elif card.card_type in (CardType.CASHBACK, CardType.INVESTBACK):
            if card.cashback_categories and profile is not None:
                rules_by_pct = sorted(card.cashback_categories, key=lambda r: r.pct, reverse=True)
                cat_desc = ", ".join(f"{r.category} {r.pct * 100:.0f}%" for r in rules_by_pct[:2])
                steps.append(
                    f"Cashback por categoria ({cat_desc}...): R$ {values['expected']:,.2f}/ano"
                )
            elif card.cashback_pct:
                steps.append(
                    f"Cashback: R$ {spend_annual:,.0f} × {card.cashback_pct * 100:.1f}% "
                    f"= R$ {values['expected']:,.2f}/ano"
                )

        steps.append(
            f"Ganho líquido esperado: R$ {values['expected']:,.2f} − "
            f"R$ {annuity_effective:,.2f} = R$ {net_gain_expected:,.2f}/ano"
        )
        steps.append(
            f"Cenário pessimista (gasto −20%): R$ {values['min'] - annuity_effective:,.2f}"
        )
        steps.append(
            f"Cenário otimista (gasto +20%): R$ {values['max'] - annuity_effective:,.2f}"
        )

        return steps

    # ─── M2.4: ROI do Cartão Atual ────────────────────────────────────────────

    def calculate_current_card_roi(
        self,
        card: CardRecord,
        profile: UserProfile,
    ) -> CurrentCardROI:
        """
        M2.4 — Calcula se o cartão atual do usuário está se pagando.

        Args:
            card: CardRecord do cartão que o usuário já possui.
            profile: Perfil de consumo do usuário (output do ConsumptionProfiler).

        Returns:
            CurrentCardROI com ROI real, veredicto e explicação em linguagem natural.
        """
        spend_annual = profile.monthly_avg_spend * profile.credit_spend_ratio * 12

        # 1. Anuidade efetiva e isenção
        annuity_paid, annuity_waived = self._compute_annuity(card, spend_annual)

        # 2. Valor gerado em pontos/cashback com o gasto atual
        # Passa profile (M2.5: cashback por categoria) e scenario="expected" (M2.3: taxa dinâmica)
        reward_value = self._compute_benefit_value(card, spend_annual, profile, "expected")
        net_roi = reward_value - annuity_paid

        # 3. Quanto falta gastar para isentar a anuidade
        spend_needed_for_waiver: float | None = None
        months_to_reach_waiver: float | None = None

        if not annuity_waived and card.waiver_rules.type == "spend_threshold" and card.waiver_rules.threshold:
            # threshold é anual na estrutura do card
            monthly_needed = card.waiver_rules.threshold / 12
            monthly_current = profile.monthly_avg_spend
            if monthly_current > 0:
                spend_needed_for_waiver = max(monthly_needed - monthly_current, 0)
                months_to_reach_waiver = (
                    None  # threshold é de gasto acumulado anual, não há prazo fixo
                )
            else:
                spend_needed_for_waiver = monthly_needed

        # 4. Auditoria de benefícios: quais o perfil usa vs. ignora
        benefits_used, benefits_unused = self._audit_benefits(card, profile)

        # 5. Veredicto
        verdict = self._compute_roi_verdict(net_roi)

        # 6. Explicação em linguagem natural
        explanation = self._build_roi_explanation(
            card, profile, spend_annual, annuity_paid, annuity_waived,
            reward_value, net_roi, spend_needed_for_waiver, verdict,
        )

        return CurrentCardROI(
            card_id=card.card_id,
            card_name=card.name,
            annuity_paid=round(annuity_paid, 2),
            reward_value_generated=round(reward_value, 2),
            net_roi=round(net_roi, 2),
            annuity_waived=annuity_waived,
            spend_needed_for_waiver=round(spend_needed_for_waiver, 2) if spend_needed_for_waiver is not None else None,
            months_to_reach_waiver=months_to_reach_waiver,
            benefits_used=benefits_used,
            benefits_unused=benefits_unused,
            verdict=verdict,
            explanation=explanation,
        )

    def _audit_benefits(
        self,
        card: CardRecord,
        profile: UserProfile,
    ) -> tuple[list[str], list[str]]:
        """Separa benefícios do cartão em usados e não usados com base no perfil."""
        used: list[str] = []
        unused: list[str] = []

        for tag in card.benefit_tags:
            if tag == BenefitTag.INTERNACIONAL:
                if profile.international_spend_monthly > 100:
                    used.append("Compras internacionais / IOF reduzido")
                else:
                    unused.append("Compras internacionais / IOF reduzido")

            elif tag == BenefitTag.LOUNGE:
                if profile.travel_spend_monthly > 300:
                    used.append("Acesso a salas VIP (viagens recorrentes)")
                else:
                    unused.append("Acesso a salas VIP (você não viaja com frequência)")

            elif tag == BenefitTag.TRAVEL:
                if profile.travel_spend_monthly > 200:
                    used.append("Benefícios de viagem (seguro, assistência)")
                else:
                    unused.append("Benefícios de viagem (pouco uso detectado)")

            elif tag == BenefitTag.CASHBACK:
                if profile.monthly_avg_spend > 500:
                    used.append("Cashback sobre gastos mensais")
                else:
                    unused.append("Cashback (gasto muito baixo para usar bem)")

        return used, unused

    def _compute_roi_verdict(self, net_roi: float) -> CardROIVerdict:
        """
        Classifica o ROI:
          VALE_A_PENA: net_roi ≥ 0 (anuidade se paga pelos benefícios)
          MARGINAL:    -200 < net_roi < 0 (preju​ízo pequeno, pode valer pelos benefícios intangíveis)
          NAO_VALE:    net_roi ≤ -200 (preju​ízo relevante — troca recomendada)
        """
        if net_roi >= 0:
            return CardROIVerdict.VALE_A_PENA
        if net_roi > -200:
            return CardROIVerdict.MARGINAL
        return CardROIVerdict.NAO_VALE

    def _build_roi_explanation(
        self,
        card: CardRecord,
        profile: UserProfile,
        spend_annual: float,
        annuity_paid: float,
        annuity_waived: bool,
        reward_value: float,
        net_roi: float,
        spend_needed_for_waiver: float | None,
        verdict: CardROIVerdict,
    ) -> str:
        """Gera texto explicativo em português para apresentar ao usuário."""
        parts: list[str] = []

        monthly_spend = profile.monthly_avg_spend

        if annuity_waived:
            parts.append(
                f"Sua anuidade do {card.name} está **isenta** — "
                f"seu gasto anual (R$ {spend_annual:,.0f}) supera o threshold necessário."
            )
        else:
            parts.append(
                f"Você paga **R$ {annuity_paid:,.0f}/ano** de anuidade no {card.name}."
            )

        if reward_value > 0:
            parts.append(
                f"Com seu gasto médio de R$ {monthly_spend:,.0f}/mês, "
                f"você gera **R$ {reward_value:,.0f}/ano** em pontos/cashback."
            )
        else:
            parts.append("O cartão não gera retorno mensurável em pontos ou cashback.")

        if verdict == CardROIVerdict.VALE_A_PENA:
            parts.append(
                f"Resultado: **ganho líquido de R$ {net_roi:,.0f}/ano** — "
                "a anuidade está se pagando."
            )
        elif verdict == CardROIVerdict.MARGINAL:
            parts.append(
                f"Resultado: **prejuízo de R$ {abs(net_roi):,.0f}/ano** — "
                "o cartão pode valer pelos benefícios extras (lounge, seguro, etc.), "
                "mas em termos de pontos/cashback não cobre a anuidade."
            )
        else:
            parts.append(
                f"Resultado: **prejuízo de R$ {abs(net_roi):,.0f}/ano** — "
                "a anuidade não está sendo justificada pelo uso atual. "
                "Vale considerar um cartão sem anuidade ou com melhor retorno."
            )

        if spend_needed_for_waiver and spend_needed_for_waiver > 0:
            parts.append(
                f"Para isentar a anuidade, você precisaria gastar mais "
                f"**R$ {spend_needed_for_waiver:,.0f}/mês** (hoje gasta R$ {monthly_spend:,.0f}/mês)."
            )

        return " ".join(parts)
