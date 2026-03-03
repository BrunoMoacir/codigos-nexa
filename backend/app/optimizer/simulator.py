# app/optimizer/simulator.py
# CardSimulator — calcula retorno financeiro de cada cartão para o perfil do usuário
# Passo 2.3 — Funcionalidade 2: Nexa Optimizer

from __future__ import annotations

import logging

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

# TODO: migrar para structlog (dependência já declarada em pyproject.toml)
logger = logging.getLogger(__name__)

# Fatores de variação para os 3 cenários (±20% do gasto base)
_SCENARIO_FACTORS: dict[str, float] = {
    "min": 0.8,
    "expected": 1.0,
    "max": 1.2,
}

_liquidity_checker = LiquidityChecker()


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
        spend_annual = profile.monthly_avg_spend * 12

        annuity_effective, annuity_waived = self._compute_annuity(card, spend_annual)

        values = {
            scenario: self._compute_benefit_value(card, spend_annual * factor)
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
        )

    # ─── Helpers privados ─────────────────────────────────────────────────────

    def _compute_annuity(self, card: CardRecord, spend_annual: float) -> tuple[float, bool]:
        """Retorna (annuity_effective, annuity_waived)."""
        wr = card.waiver_rules

        if wr.type == "always_free":
            return 0.0, True

        if wr.type == "spend_threshold" and wr.threshold is not None:
            if spend_annual >= wr.threshold:
                return 0.0, True
            return card.base_annuity, False

        # "transaction_count": conservador — assume que o usuário não atingirá o threshold
        # "none" ou desconhecido: anuidade sempre cobrada
        return card.base_annuity, False

    def _compute_benefit_value(self, card: CardRecord, spend_annual_scaled: float) -> float:
        """Calcula o valor monetário dos benefícios para um dado gasto anual.

        Convenção de unidade (obrigatória em knowledge_cards.json):
            points_conversion_rate = R$ por 1.000 pontos/milhas.
            Exemplos corretos: 16.0 (R$16/mil pts), 25.0 (R$25/mil milhas).
            Valores por ponto unitário (ex: 0.016) são incorretos no JSON e
            produzem estimativas 1000× menores sem nenhum erro visível.
        """
        if card.card_type == CardType.POINTS:
            if not card.points_per_brl or card.points_conversion_rate == 0:
                return 0.0
            points = spend_annual_scaled * card.points_per_brl
            return (points / 1000) * card.points_conversion_rate

        if card.card_type in (CardType.CASHBACK, CardType.INVESTBACK):
            if card.cashback_pct is None:
                return 0.0
            value = spend_annual_scaled * card.cashback_pct
            if card.cashback_cap:
                value = min(value, card.cashback_cap * 12)
            return value

        return 0.0

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
        Confiança na simulação (0.0–1.0).

        Penalidades:
        - Cobertura < 2 meses → × 0.5
        - Comprometimento > 80% → × 0.7

        Comportamento intencional com perfis novos: a multiplicação de três
        fatores parciais pode produzir valores muito baixos (ex.: coverage=1 mês,
        stability=0.5, trust=0.5 → score ≈ 0.042 após penalidade). Isso é
        conservador por design — poucos dados implicam baixa confiança. O
        CardRanking penalizará esses cartões com × 0.5 se score < 0.4, o que
        é aceitável: não faz sentido recomendar com confiança alta quando o
        histórico é insuficiente.
        """
        coverage_weight = min(profile.data_coverage_months, 6) / 6
        stability_weight = profile.spending_stability
        bank_trust_weight = card.data_trust_score

        score = coverage_weight * stability_weight * bank_trust_weight

        if profile.data_coverage_months < 2:
            score *= 0.5
        if profile.committed_percentage > 0.8:
            score *= 0.7

        # MI.4: renda instável → menor confiança na projeção de benefícios
        # Renda PJ/MIXED com alta variabilidade torna incerta a projeção de
        # gasto anual usada para calcular pontos/cashback acumulados.
        income_stability = getattr(profile.income_profile, "income_stability", None)
        if income_stability is not None and income_stability < 0.5:
            score *= 0.85

        return min(score, 1.0)

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

        # Cashback em categoria relevante.
        # break intencional: o cashback_pct dos cartões atuais é flat (sem distinção
        # de categoria), então uma razão com a categoria de maior gasto já é
        # representativa. Se futuramente o modelo suportar cashback_categories com
        # taxas diferenciadas, este bloco deve ser refatorado para iterar todas.
        if card.card_type in (CardType.CASHBACK, CardType.INVESTBACK) and card.cashback_pct:
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
            steps.append(
                f"Valor dos pontos: {pts_annual:,.0f} ÷ 1.000 "
                f"× R$ {card.points_conversion_rate} "
                f"= R$ {values['expected']:,.2f}/ano"
            )
        elif card.card_type in (CardType.CASHBACK, CardType.INVESTBACK) and card.cashback_pct:
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
        spend_annual = profile.monthly_avg_spend * 12

        # 1. Anuidade efetiva e isenção
        annuity_paid, annuity_waived = self._compute_annuity(card, spend_annual)

        # 2. Valor gerado em pontos/cashback com o gasto atual
        reward_value = self._compute_benefit_value(card, spend_annual)
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
