# app/optimizer/multi_card_strategy.py
# M2.2 — Estratégia Multi-Cartão ("Carteira ideal")

"""
Calcula a carteira ótima de até N cartões para o perfil de gastos do usuário.

ALGORITMO (greedy por categoria):
  1. Para cada categoria de gasto, elege o cartão que maximiza o retorno
  2. Limita ao max_cards de maior contribuição anual
  3. Reatribui categorias dos cartões descartados ao melhor dos mantidos
  4. Remove cartões com gasto direcionado < threshold mínimo
  5. Calcula retorno total e compara vs melhor cartão único

NOTA M2.5: cashback_categories em CardRecord é atualmente list[str] (nomes de
categorias, sem percentual). Para categorias especiais do cartão usamos um
multiplicador aproximado (1.5×). Quando M2.5 for implementado e cashback_categories
passar a incluir percentuais por categoria, basta atualizar _return_for_category().
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.optimizer.models import CardRecord
    from app.optimizer.profiler import UserProfile

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONSTANTES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Gasto mensal mínimo direcionado a um cartão para justificar mantê-lo na carteira.
# Abaixo disso, o cartão é descartado e suas categorias são reatribuídas.
_MIN_DIRECTED_SPEND_MONTHLY = 200.0

# Multiplicador de retorno para categorias listadas em cashback_categories do cartão.
# Representa o benefício de categorias especiais até M2.5 implementar pct por categoria.
_CATEGORY_BONUS_MULTIPLIER = 1.5


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATACLASSES DE RESULTADO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class CardAssignment:
    """Um cartão na carteira com as categorias de gasto atribuídas a ele."""
    card: "CardRecord"
    assigned_categories: list[str] = field(default_factory=list)
    monthly_spend_directed: float = 0.0      # R$/mês que vai para este cartão
    annual_return_from_this_card: float = 0.0  # retorno anual só deste cartão
    effective_annuity: float = 0.0           # anuidade paga (0 se isenta)
    reason: str = ""                         # "Melhor cashback em Alimentação (2%)"


@dataclass
class CardPortfolio:
    """Resultado da otimização multi-cartão."""
    cards: list[CardAssignment]
    total_annual_return: float    # soma dos retornos de todos os cartões
    total_annuity_cost: float     # soma das anuidades efetivas
    net_annual_gain: float        # total_annual_return − total_annuity_cost
    vs_single_best: float         # ganho adicional vs melhor cartão único
    single_best_net_gain: float   # referência: retorno líquido do melhor cartão único
    explanation: str


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLASSE PRINCIPAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MultiCardStrategist:
    """
    Monta a carteira ideal de cartões para o perfil de gastos do usuário.

    Example:
        >>> strategist = MultiCardStrategist()
        >>> portfolio = strategist.optimize_portfolio(profile, eligible_cards, max_cards=3)
        >>> print(portfolio.net_annual_gain)
        1240.0
    """

    def optimize_portfolio(
        self,
        profile: "UserProfile",
        eligible_cards: list["CardRecord"],
        max_cards: int = 3,
    ) -> CardPortfolio:
        """
        Calcula a carteira ótima de até max_cards cartões.

        Args:
            profile: Perfil de consumo com spend_by_category.
            eligible_cards: Cartões elegíveis para o usuário (já filtrados por renda).
            max_cards: Máximo de cartões na carteira (1–5).

        Returns:
            CardPortfolio com cartões, retornos, anuidades e explicação.
        """
        if not eligible_cards or not profile.spend_by_category:
            return self._empty_portfolio()

        # ── 1. Eleger melhor cartão por categoria ───────────────────────
        # card_id → CardAssignment acumulado
        assignments: dict[str, CardAssignment] = {}

        for category, monthly_spend in profile.spend_by_category.items():
            if monthly_spend <= 0:
                continue

            best_card, monthly_return, reason = self._best_card_for_category(
                eligible_cards, category, monthly_spend
            )
            if best_card is None:
                continue

            cid = best_card.card_id
            if cid not in assignments:
                assignments[cid] = CardAssignment(card=best_card)

            a = assignments[cid]
            a.assigned_categories.append(category)
            a.monthly_spend_directed += monthly_spend
            # RETORNO BRUTO: annual_return_from_this_card acumula retorno antes
            # de descontar a anuidade. A anuidade efetiva é calculada separadamente
            # em _effective_annuity() e subtraída apenas nos totais finais
            # (net_annual_gain = total_annual_return − total_annuity_cost).
            a.annual_return_from_this_card += monthly_return * 12
            if not a.reason:
                a.reason = reason

        if not assignments:
            return self._empty_portfolio()

        # ── 2. Calcular anuidades (antes de qualquer descarte) ──────────
        for a in assignments.values():
            a.effective_annuity = self._effective_annuity(
                a.card, a.monthly_spend_directed
            )

        # ── 3. Limitar a max_cards — descartar menor contribuição líquida
        sorted_all = sorted(
            assignments.values(),
            key=lambda a: a.annual_return_from_this_card - a.effective_annuity,
            reverse=True,
        )

        if len(sorted_all) > max_cards:
            kept = sorted_all[:max_cards]
            discarded = sorted_all[max_cards:]
            kept_cards = [a.card for a in kept]

            # Reatribuir categorias dos cartões removidos ao melhor dos mantidos
            for dropped in discarded:
                for category in dropped.assigned_categories:
                    monthly_spend = profile.spend_by_category.get(category, 0)
                    if monthly_spend <= 0:
                        continue

                    best_card, monthly_return, reason = self._best_card_for_category(
                        kept_cards, category, monthly_spend
                    )
                    if best_card is None:
                        continue

                    target = next(
                        (a for a in kept if a.card.card_id == best_card.card_id), None
                    )
                    if target is None:
                        continue

                    if category not in target.assigned_categories:
                        target.assigned_categories.append(category)
                    target.monthly_spend_directed += monthly_spend
                    # Retorno bruto acumulado; anuidade recalculada após o loop
                    target.annual_return_from_this_card += monthly_return * 12

            # Recalcular anuidades após reatribuição
            for a in kept:
                a.effective_annuity = self._effective_annuity(
                    a.card, a.monthly_spend_directed
                )

            sorted_all = kept

        # ── 4. Remover cartões com gasto abaixo do mínimo ───────────────
        final = [
            a for a in sorted_all
            if a.monthly_spend_directed >= _MIN_DIRECTED_SPEND_MONTHLY
        ]
        if not final:
            final = sorted_all[:1]  # manter ao menos 1

        # ── 5. Totais e comparação vs cartão único ──────────────────────
        total_return = sum(a.annual_return_from_this_card for a in final)
        total_annuity = sum(a.effective_annuity for a in final)
        net_gain = total_return - total_annuity

        single_best = self._single_best_net_gain(eligible_cards, profile)
        vs_single_best = net_gain - single_best

        explanation = self._build_explanation(final, net_gain, vs_single_best)

        logger.info(
            f"[multi-card] Carteira montada: {len(final)} cartão(ns), "
            f"retorno líquido R$ {net_gain:.2f}/ano, "
            f"R$ {vs_single_best:.2f} a mais que cartão único"
        )

        return CardPortfolio(
            cards=final,
            total_annual_return=round(total_return, 2),
            total_annuity_cost=round(total_annuity, 2),
            net_annual_gain=round(net_gain, 2),
            vs_single_best=round(vs_single_best, 2),
            single_best_net_gain=round(single_best, 2),
            explanation=explanation,
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HELPERS PRIVADOS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _return_for_category(
        self,
        card: "CardRecord",
        category: str,
        monthly_spend: float,
    ) -> float:
        """
        Retorno mensal (R$) do cartão para um gasto em uma categoria específica.

        Para POINTS: (spend × points_per_brl / 1000) × points_conversion_rate
        Para CASHBACK: spend × cashback_pct [× bonus se categoria especial]
                       aplicando cap mensal se houver

        SEMÂNTICA DE cashback_cap:
            cashback_cap é um cap MENSAL (R$/mês), consistente com simulator.py
            que usa `card.cashback_cap * 12` para obter o cap anual.
            Aqui aplicamos o cap no retorno mensal; o chamador multiplica por 12
            para obter o retorno anual — o que resulta em `cap_mensal × 12` de
            retorno anual máximo, que é a semântica correta.
        """
        from app.optimizer.models import CardType

        if card.card_type == CardType.POINTS:
            if not card.points_per_brl or card.points_conversion_rate == 0:
                return 0.0
            points = monthly_spend * card.points_per_brl
            return (points / 1000) * card.points_conversion_rate

        if card.card_type in (CardType.CASHBACK, CardType.INVESTBACK):
            if card.cashback_pct is None:
                return 0.0
            # Bonus para categorias com taxa diferenciada (M2.5 refinará com pct real)
            multiplier = (
                _CATEGORY_BONUS_MULTIPLIER
                if category and category in card.cashback_categories
                else 1.0
            )
            value = monthly_spend * card.cashback_pct * multiplier
            if card.cashback_cap:
                value = min(value, card.cashback_cap)  # cap mensal
            return value

        return 0.0

    def _best_card_for_category(
        self,
        cards: list["CardRecord"],
        category: str,
        monthly_spend: float,
    ) -> tuple[Optional["CardRecord"], float, str]:
        """
        Retorna (melhor_cartão, retorno_mensal_R$, motivo) para a categoria.
        Se nenhum cartão tiver retorno > 0, retorna (None, 0.0, "").
        """
        from app.optimizer.models import CardType

        best_card: Optional["CardRecord"] = None
        best_return = 0.0
        best_reason = ""

        for card in cards:
            ret = self._return_for_category(card, category, monthly_spend)
            if ret > best_return:
                best_return = ret
                best_card = card

                if card.card_type == CardType.CASHBACK:
                    pct = (card.cashback_pct or 0) * 100
                    is_special = category in card.cashback_categories
                    label = f"{pct * _CATEGORY_BONUS_MULTIPLIER:.1f}%" if is_special else f"{pct:.1f}%"
                    best_reason = f"Melhor cashback em {category} ({label})"
                elif card.card_type == CardType.INVESTBACK:
                    pct = (card.cashback_pct or 0) * 100
                    best_reason = f"Melhor investback em {category} ({pct:.1f}%)"
                else:  # POINTS
                    best_reason = (
                        f"Melhor retorno em {category} "
                        f"({card.points_per_brl} pts/R$ → "
                        f"R$ {best_return:.2f}/mês)"
                    )

        return best_card, best_return, best_reason

    def _effective_annuity(
        self, card: "CardRecord", monthly_spend_directed: float
    ) -> float:
        """
        Anuidade efetiva considerando regra de isenção do cartão.

        - always_free → R$ 0
        - spend_threshold → R$ 0 se gasto anual >= threshold
        - transaction_count / none → anuidade cheia (sem dados de contagem aqui)
        """
        annual_spend = monthly_spend_directed * 12
        rules = card.waiver_rules

        if rules.type == "always_free":
            return 0.0

        if rules.type == "spend_threshold" and rules.threshold:
            if annual_spend >= rules.threshold:
                return 0.0

        return card.base_annuity

    def _single_best_net_gain(
        self, eligible_cards: list["CardRecord"], profile: "UserProfile"
    ) -> float:
        """
        Retorno líquido anual do melhor cartão único sobre todo o gasto do usuário.
        Usado como baseline para calcular vs_single_best.
        """
        best = 0.0
        for card in eligible_cards:
            annual_return = sum(
                self._return_for_category(card, cat, spend) * 12
                for cat, spend in profile.spend_by_category.items()
            )
            annuity = self._effective_annuity(card, profile.monthly_avg_spend)
            net = annual_return - annuity
            if net > best:
                best = net
        return best

    def _build_explanation(
        self,
        assignments: list[CardAssignment],
        net_gain: float,
        vs_single_best: float,
    ) -> str:
        n = len(assignments)
        parts = [
            f"Carteira ideal com {n} cartão(ns) gera R$ {net_gain:.0f}/ano líquido."
        ]
        if vs_single_best > 0:
            parts.append(
                f"R$ {vs_single_best:.0f} a mais que usar somente o melhor cartão."
            )
        elif vs_single_best <= 0:
            parts.append(
                "Neste perfil, um único cartão é tão eficiente quanto a carteira multi-cartão."
            )
        for a in assignments:
            cats = ", ".join(a.assigned_categories[:3])
            if len(a.assigned_categories) > 3:
                cats += f" +{len(a.assigned_categories) - 3}"
            annuity_note = f" (anuidade R$ {a.effective_annuity:.0f}/ano)" if a.effective_annuity > 0 else " (sem anuidade)"
            parts.append(
                f"• {a.card.name}: {cats}{annuity_note} → "
                f"R$ {a.annual_return_from_this_card:.0f}/ano"
            )
        return " ".join(parts)

    def _empty_portfolio(self) -> CardPortfolio:
        return CardPortfolio(
            cards=[],
            total_annual_return=0.0,
            total_annuity_cost=0.0,
            net_annual_gain=0.0,
            vs_single_best=0.0,
            single_best_net_gain=0.0,
            explanation="Sem dados suficientes para montar carteira ideal.",
        )
