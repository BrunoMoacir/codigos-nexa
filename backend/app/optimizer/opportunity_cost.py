"""
app/optimizer/opportunity_cost.py - Calculadora de Custo de Oportunidade

RESPONSABILIDADE:
    Mostra ao usuário quanto ele DEIXOU DE GANHAR por usar o cartão errado.
    É o argumento mais forte para motivar a troca de cartão.

CONCEITO:
    "Em janeiro você gastou R$ 3.200 no Nubank Roxinho (0,5 pts/R$).
    Se tivesse usado o C6 Carbon (2,0 pts/R$), teria ganho 6.400 pontos a mais
    — equivalentes a R$ 102 em milhas. Nos últimos 3 meses: R$ 287."

INTEGRAÇÃO:
    - Endpoint: GET /api/v1/optimizer/opportunity-cost
        params: user_id, current_card_id, months (default 3)
    - Injetável no OptimizationReport como campo opportunity_cost_summary
    - O agente usa na strategy_text: "Você está deixando de ganhar R$ X/mês..."

LIMITAÇÕES CONHECIDAS:
    - Recompensas calculadas com taxa flat (sem distinção de categoria).
      A M2.5 (Cashback por Categoria) expandirá isso com rates por categoria.
    - Cashback cap é tratado como mensal (conforme CardRecord.cashback_cap).
    - Anuidade não é subtraída aqui — foco é em reward bruto.
      O ROI líquido (reward - annuity) é responsabilidade da M2.4.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.optimizer.miles_valuator import get_valuator
from app.optimizer.models import CardRecord, CardType
from app.optimizer.profiler import UserProfile

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATACLASSES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class CardOpportunity:
    """
    Quanto o usuário teria ganho a mais usando um cartão candidato.

    Attributes:
        card_id: ID do cartão candidato
        card_name: Nome do cartão candidato
        issuer: Emissor do cartão
        hypothetical_reward_value: Recompensa que teria gerado no período (R$)
        difference: Ganho a mais vs. cartão atual (R$) — positivo = candidato melhor
        difference_annualized: Projeção anual da diferença (R$)
        difference_monthly: Média mensal da diferença (R$)
        breakdown_by_category: Diferença por categoria de gasto ({categoria: R$})
        explanation: Texto pronto para o LLM usar na strategy_text

    Example:
        >>> opp.difference_annualized
        287.0
        >>> opp.explanation
        'Se tivesse usado C6 Carbon nos últimos 3 meses, teria ganho R$ 72 a mais...'
    """
    card_id: str
    card_name: str
    issuer: str
    hypothetical_reward_value: float
    difference: float
    difference_annualized: float
    difference_monthly: float
    breakdown_by_category: dict[str, float] = field(default_factory=dict)
    explanation: str = ""

    def to_dict(self) -> dict:
        return {
            "card_id": self.card_id,
            "card_name": self.card_name,
            "issuer": self.issuer,
            "hypothetical_reward_value": self.hypothetical_reward_value,
            "difference": self.difference,
            "difference_annualized": self.difference_annualized,
            "difference_monthly": self.difference_monthly,
            "breakdown_by_category": self.breakdown_by_category,
            "explanation": self.explanation,
        }


@dataclass
class OpportunityCostReport:
    """
    Relatório de custo de oportunidade do cartão atual vs. candidatos.

    Attributes:
        current_card_id: ID do cartão que o usuário usa hoje
        current_card_name: Nome do cartão atual
        period_months: Janela de análise (meses)
        total_spent: Gasto total estimado no período (R$)
        current_card_reward_value: Recompensa gerada pelo cartão atual no período (R$)
        opportunities: Cartões candidatos com diferença positiva, ordenados por ganho
        best_opportunity: Cartão com maior ganho (None se não há oportunidade melhor)

    Example:
        >>> report.current_card_reward_value
        48.0
        >>> report.best_opportunity.difference_annualized
        287.0
    """
    current_card_id: str
    current_card_name: str
    period_months: int
    total_spent: float
    current_card_reward_value: float
    opportunities: list[CardOpportunity]
    best_opportunity: CardOpportunity | None

    def to_dict(self) -> dict:
        return {
            "current_card_id": self.current_card_id,
            "current_card_name": self.current_card_name,
            "period_months": self.period_months,
            "total_spent": self.total_spent,
            "current_card_reward_value": self.current_card_reward_value,
            "opportunities": [o.to_dict() for o in self.opportunities],
            "best_opportunity": self.best_opportunity.to_dict() if self.best_opportunity else None,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER INTERNO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _compute_card_reward(card: CardRecord, total_spend: float, months: int) -> float:
    """
    Calcula o valor monetário de recompensas para um dado gasto total.

    Espelha a lógica de CardSimulator._compute_benefit_value() mas opera sobre
    o gasto total do período (não anualizado), aplicando o cashback_cap por mês.

    M2.3: Para cartões POINTS com loyalty_program, usa o cenário "expected"
    do MilesValuator em vez da taxa fixa do CardRecord.

    Args:
        card: Cartão a simular
        total_spend: Gasto total no período (R$)
        months: Duração do período — usado para normalizar o cashback_cap mensal

    Returns:
        Valor total de recompensas no período (R$)
    """
    if card.card_type == CardType.POINTS:
        if not card.points_per_brl:
            return 0.0
        # M2.3: valoração dinâmica via programa de fidelidade (cenário esperado)
        if card.loyalty_program:
            value = get_valuator().compute_points_value(
                card.points_per_brl, total_spend, card.loyalty_program, "expected"
            )
            if value > 0:
                return value
        # Fallback: taxa fixa
        if card.points_conversion_rate == 0:
            return 0.0
        points = total_spend * card.points_per_brl
        return (points / 1000) * card.points_conversion_rate

    if card.card_type in (CardType.CASHBACK, CardType.INVESTBACK):
        if card.cashback_pct is None:
            return 0.0
        value = total_spend * card.cashback_pct
        # cashback_cap é mensal no CardRecord → cap do período = cap × meses
        if card.cashback_cap:
            value = min(value, card.cashback_cap * months)
        return value

    return 0.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CALCULATOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class OpportunityCostCalculator:
    """
    Calcula quanto o usuário deixou de ganhar por usar o cartão atual
    em vez de cada cartão candidato.

    Usa o UserProfile (já computado pelo ConsumptionProfiler) como base de gasto,
    evitando reprocessar as transações.

    Example:
        >>> calc = OpportunityCostCalculator()
        >>> report = calc.calculate(
        ...     profile=profile,
        ...     current_card=nubank_card,
        ...     candidate_cards=other_cards,
        ...     months=3,
        ... )
        >>> print(report.best_opportunity.explanation)
        'Se tivesse usado C6 Carbon nos últimos 3 meses...'
    """

    def calculate(
        self,
        profile: UserProfile,
        current_card: CardRecord,
        candidate_cards: list[CardRecord],
        months: int = 3,
    ) -> OpportunityCostReport:
        """
        Calcula custo de oportunidade do cartão atual vs. candidatos.

        Args:
            profile: Perfil de consumo do usuário (output do ConsumptionProfiler)
            current_card: CardRecord do cartão que o usuário usa hoje
            candidate_cards: Lista de cartões a comparar. Tipicamente todos os
                cartões da CardKnowledgeBase exceto o atual.
            months: Janela de comparação em meses (padrão: 3). Corresponde ao
                período de histórico recente mais confiável.

        Returns:
            OpportunityCostReport com todos os candidatos e o melhor identificado.
        """
        if profile.monthly_avg_spend <= 0:
            logger.warning("OpportunityCostCalculator: gasto médio zero — retornando relatório vazio.")
            return self._empty_report(current_card, months)

        total_spend = profile.monthly_avg_spend * months

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # RECOMPENSA DO CARTÃO ATUAL no período
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        current_reward = _compute_card_reward(current_card, total_spend, months)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # COMPARAR COM CADA CANDIDATO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        opportunities: list[CardOpportunity] = []

        for candidate in candidate_cards:
            if candidate.card_id == current_card.card_id:
                continue  # não comparar consigo mesmo

            candidate_reward = _compute_card_reward(candidate, total_spend, months)
            difference = candidate_reward - current_reward

            # Só reportar candidatos melhores que o atual
            if difference <= 0:
                continue

            difference_annualized = difference * (12 / months) if months > 0 else 0.0
            difference_monthly    = difference / months if months > 0 else 0.0

            breakdown = self._breakdown_by_category(
                profile, current_card, candidate, months
            )

            explanation = self._build_explanation(
                profile, current_card, candidate,
                current_reward, candidate_reward,
                difference, difference_annualized, months,
            )

            opportunities.append(CardOpportunity(
                card_id=candidate.card_id,
                card_name=candidate.name,
                issuer=candidate.issuer,
                hypothetical_reward_value=round(candidate_reward, 2),
                difference=round(difference, 2),
                difference_annualized=round(difference_annualized, 2),
                difference_monthly=round(difference_monthly, 2),
                breakdown_by_category=breakdown,
                explanation=explanation,
            ))

        # Ordenar por maior ganho
        opportunities.sort(key=lambda o: o.difference, reverse=True)

        best = opportunities[0] if opportunities else None

        logger.info(
            f"OpportunityCost: cartão={current_card.name}, "
            f"gasto={total_spend:.0f} ({months}m), "
            f"reward_atual={current_reward:.2f}, "
            f"candidatos_melhores={len(opportunities)}"
        )

        return OpportunityCostReport(
            current_card_id=current_card.card_id,
            current_card_name=current_card.name,
            period_months=months,
            total_spent=round(total_spend, 2),
            current_card_reward_value=round(current_reward, 2),
            opportunities=opportunities,
            best_opportunity=best,
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PRIVATE HELPERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _breakdown_by_category(
        self,
        profile: UserProfile,
        current_card: CardRecord,
        candidate: CardRecord,
        months: int,
    ) -> dict[str, float]:
        """
        Diferença de recompensa por categoria de gasto.

        Como os cartões atuais usam taxa flat (sem distinção de categoria),
        a diferença por categoria é proporcional ao gasto em cada categoria.
        A M2.5 expandirá isso com rates diferenciados por categoria.

        NOTA — cashback_cap por categoria vs. global:
            _compute_card_reward aplica cashback_cap independentemente para cada
            categoria (cap × months por categoria). Isso difere do cálculo global,
            onde o cap é aplicado ao gasto total do período. Em cartões com cap
            baixo e gasto concentrado em poucas categorias, a soma dos breakdown
            pode divergir ligeiramente do valor total reportado no CardOpportunity.
            Simplificação intencional: o breakdown é orientativo (LLM/UI), não
            serve como base de cálculo — o valor autoritativo é `difference`.
        """
        breakdown: dict[str, float] = {}

        for category, monthly_avg in profile.spend_by_category.items():
            if monthly_avg <= 0:
                continue

            cat_spend = monthly_avg * months
            current_cat  = _compute_card_reward(current_card, cat_spend, months)
            candidate_cat = _compute_card_reward(candidate, cat_spend, months)
            diff = candidate_cat - current_cat

            if abs(diff) > 0.01:  # filtrar diferenças negligenciáveis
                breakdown[category] = round(diff, 2)

        return breakdown

    def _build_explanation(
        self,
        profile: UserProfile,
        current_card: CardRecord,
        candidate: CardRecord,
        current_reward: float,
        candidate_reward: float,
        difference: float,
        difference_annualized: float,
        months: int,
    ) -> str:
        """
        Texto em português pronto para ser inserido na strategy_text do agente.

        Segue o formato do exemplo da doc:
            "Em X meses você gastou R$ Y no [Cartão Atual].
            Se tivesse usado [Candidato], teria ganho R$ Z a mais
            — equivalente a R$ W/ano."
        """
        period_label = f"{months} {'mês' if months == 1 else 'meses'}"
        total_spend  = profile.monthly_avg_spend * months

        # Descrever o tipo de recompensa do candidato
        if candidate.card_type == CardType.POINTS:
            reward_desc = (
                f"{candidate.points_per_brl or 0:.1f} pts/R$ "
                f"→ R$ {candidate.points_conversion_rate:.0f}/mil pts"
            )
        elif candidate.card_type in (CardType.CASHBACK, CardType.INVESTBACK):
            pct = (candidate.cashback_pct or 0) * 100
            reward_desc = f"{pct:.1f}% de cashback"
        else:
            reward_desc = "benefícios"

        return (
            f"Nos últimos {period_label} você gastou R$ {total_spend:,.0f} "
            f"no {current_card.name} e gerou R$ {current_reward:,.2f} em recompensas. "
            f"Se tivesse usado o {candidate.name} ({reward_desc}), "
            f"teria ganho R$ {candidate_reward:,.2f} — "
            f"R$ {difference:,.2f} a mais no período "
            f"(R$ {difference_annualized:,.0f}/ano projetado)."
        )

    def _empty_report(self, current_card: CardRecord, months: int) -> OpportunityCostReport:
        """Relatório neutro para perfis sem dados de gasto."""
        return OpportunityCostReport(
            current_card_id=current_card.card_id,
            current_card_name=current_card.name,
            period_months=months,
            total_spent=0.0,
            current_card_reward_value=0.0,
            opportunities=[],
            best_opportunity=None,
        )


__all__ = [
    "OpportunityCostCalculator",
    "OpportunityCostReport",
    "CardOpportunity",
]
