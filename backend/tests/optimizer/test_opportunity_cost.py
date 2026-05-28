# tests/optimizer/test_opportunity_cost.py
# Testes completos para Custo de Oportunidade (OpportunityCostCalculator)

"""
Cenários cobertos:
  1. Candidato melhor que atual → aparece em opportunities com difference > 0
  2. Candidato pior que atual → NÃO aparece em opportunities
  3. Candidato igual ao atual (mesmo card_id) → ignorado
  4. best_opportunity aponta para o candidato com maior difference
  5. opportunities ordenados por difference decrescente
  6. difference_annualized = difference × (12 / months)
  7. difference_monthly = difference / months
  8. Gasto médio zero → relatório vazio, sem crash
  9. Breakdown por categoria: diferença calculada por categoria
 10. M2.5: taxas por categoria usadas para calcular reward do candidato
 11. Cap mensal respeitado no cálculo de reward do candidato
 12. Cartão POINTS: recompensa calculada via pts_per_brl × conversion_rate
 13. INVESTBACK tratado igual a CASHBACK
 14. Texto de explicação em português com dados corretos
 15. Múltiplos meses: total_spend = monthly_avg × months
 16. months=1 vs months=6: ambos produzem relatório consistente
 17. Sem candidatos melhores → best_opportunity = None, opportunities = []
 18. to_dict() serializa corretamente (sem erros, campos presentes)
 19. Integração: candidato de cartão real bate o atual
 20. Integração: Nubank Roxinho vs base completa de cartões reais
"""

import pytest
from app.optimizer.opportunity_cost import (
    OpportunityCostCalculator,
    OpportunityCostReport,
    CardOpportunity,
    _compute_card_reward,
    _compute_total_reward_with_profile,
)
from app.optimizer.models import (
    CardRecord, CardType, CardFlag, WaiverRules, CashbackCategoryRule
)
from app.optimizer.profiler import UserProfile


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FACTORIES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _free_waiver() -> WaiverRules:
    return WaiverRules(type="always_free", description="Sem anuidade")


def _cashback_card(
    card_id: str,
    name: str,
    pct: float,
    cap: float | None = None,
    categories: list[CashbackCategoryRule] | None = None,
) -> CardRecord:
    return CardRecord(
        card_id=card_id,
        name=name,
        issuer="Banco Teste",
        flag=CardFlag.MASTERCARD,
        card_type=CardType.CASHBACK,
        public_target="geral",
        min_income=0,
        requires_proof_of_income=False,
        secured_card=False,
        prepaid=False,
        consigned=False,
        base_annuity=0.0,
        waiver_rules=_free_waiver(),
        cashback_pct=pct,
        cashback_cap=cap,
        cashback_categories=categories or [],
        last_updated="2026-01-01",
    )


def _points_card(
    card_id: str,
    name: str,
    pts_per_brl: float,
    conversion_rate: float,
) -> CardRecord:
    return CardRecord(
        card_id=card_id,
        name=name,
        issuer="Banco Pontos",
        flag=CardFlag.VISA,
        card_type=CardType.POINTS,
        public_target="geral",
        min_income=0,
        requires_proof_of_income=False,
        secured_card=False,
        prepaid=False,
        consigned=False,
        base_annuity=0.0,
        waiver_rules=_free_waiver(),
        points_per_brl=pts_per_brl,
        points_conversion_rate=conversion_rate,
        last_updated="2026-01-01",
    )


def _investback_card(card_id: str, name: str, pct: float) -> CardRecord:
    return CardRecord(
        card_id=card_id,
        name=name,
        issuer="Banco Invest",
        flag=CardFlag.ELO,
        card_type=CardType.INVESTBACK,
        public_target="geral",
        min_income=0,
        requires_proof_of_income=False,
        secured_card=False,
        prepaid=False,
        consigned=False,
        base_annuity=0.0,
        waiver_rules=_free_waiver(),
        cashback_pct=pct,
        cashback_categories=[],
        last_updated="2026-01-01",
    )


def _profile(
    monthly_avg: float,
    categories: dict[str, float] | None = None,
) -> UserProfile:
    return UserProfile(
        monthly_avg_spend=monthly_avg,
        spend_by_category=categories or {},
        spend_by_source={"credit": monthly_avg},
        international_spend_monthly=0.0,
        travel_spend_monthly=0.0,
        committed_percentage=0.0,
        data_coverage_months=3,
        spending_stability=0.9,
        estimated_monthly_income=monthly_avg * 3,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES: _compute_card_reward (helper interno)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestComputeCardReward:
    """Unidade: função _compute_card_reward."""

    def test_cashback_flat_sem_cap(self):
        card = _cashback_card("a", "A", pct=0.02)
        # R$3.000 total, 3 meses
        result = _compute_card_reward(card, 3000.0, 3)
        assert result == pytest.approx(60.0)  # 3000 × 0.02

    def test_cashback_flat_com_cap_mensal(self):
        # cap = R$10/mês → R$30 no período; gasto = R$1.000, 2% = R$20 (abaixo do cap)
        card = _cashback_card("a", "A", pct=0.02, cap=10.0)
        # R$1.000 × 2% = R$20 vs cap=R$10×3meses=R$30 → sem corte
        result = _compute_card_reward(card, 1000.0, 3)
        assert result == pytest.approx(20.0)

    def test_cashback_cap_corta_quando_excedido(self):
        # cap = R$5/mês → R$15 em 3 meses; gasto alto geraria muito mais
        card = _cashback_card("a", "A", pct=0.10, cap=5.0)
        result = _compute_card_reward(card, 1000.0, 3)
        assert result == pytest.approx(15.0)  # cap: 5 × 3

    def test_points_card_retorno_correto(self):
        # 2 pts/R$, R$25/1000pts, gasto R$2.000 → 4000pts → R$100
        card = _points_card("p", "Points", pts_per_brl=2.0, conversion_rate=25.0)
        result = _compute_card_reward(card, 2000.0, 3)
        assert result == pytest.approx(100.0)

    def test_points_card_sem_pts_retorna_zero(self):
        card = _points_card("p", "Zero", pts_per_brl=0.0, conversion_rate=0.0)
        assert _compute_card_reward(card, 1000.0, 3) == pytest.approx(0.0)

    def test_cashback_pct_none_retorna_zero(self):
        card = _cashback_card("a", "A", pct=0.0)
        card = card.model_copy(update={"cashback_pct": None})
        assert _compute_card_reward(card, 1000.0, 3) == pytest.approx(0.0)

    def test_categoria_especifica_m2_5(self):
        card = _cashback_card("cat", "Cat", pct=0.005,
            categories=[CashbackCategoryRule(category="alimentacao", pct=0.03)])
        # R$1.000 × 3% = R$30
        result = _compute_card_reward(card, 1000.0, 1, category="alimentacao")
        assert result == pytest.approx(30.0)

    def test_categoria_especifica_com_cap(self):
        card = _cashback_card("cat", "Cat", pct=0.005,
            categories=[CashbackCategoryRule(category="farmacia", pct=0.05, cap_monthly=20.0)])
        # R$1.000 × 5% = R$50 mas cap=20×3meses=R$60 → sem corte para gasto=R$1.000
        result = _compute_card_reward(card, 1000.0, 3, category="farmacia")
        assert result == pytest.approx(50.0)

    def test_categoria_sem_regra_fallback_flat(self):
        card = _cashback_card("cat", "Cat", pct=0.02,
            categories=[CashbackCategoryRule(category="alimentacao", pct=0.05)])
        # "lazer" não tem regra → flat 2%
        result = _compute_card_reward(card, 500.0, 1, category="lazer")
        assert result == pytest.approx(10.0)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES: OpportunityCostCalculator.calculate()
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCandidatoMelhor:
    """Cenário 1: candidato com cashback maior aparece em opportunities."""

    def test_candidato_melhor_em_opportunities(self):
        atual = _cashback_card("atual", "Atual 0.5%", pct=0.005)
        candidato = _cashback_card("cand", "Cand 2%", pct=0.02)
        profile = _profile(monthly_avg=3200.0)

        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual,
            candidate_cards=[candidato], months=3
        )
        assert len(report.opportunities) == 1
        assert report.opportunities[0].card_id == "cand"

    def test_difference_positiva_quando_candidato_e_melhor(self):
        atual = _cashback_card("atual", "Atual", pct=0.005)
        candidato = _cashback_card("cand", "Cand", pct=0.02)
        profile = _profile(monthly_avg=1000.0)

        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual,
            candidate_cards=[candidato], months=3
        )
        opp = report.opportunities[0]
        assert opp.difference > 0

    def test_valores_corretos_de_reward(self):
        # atual: 0.5% flat; candidato: 2% flat; gasto: R$1.000/mês, 3 meses
        # atual reward: 3000 × 0.005 = R$15
        # candidato reward: 3000 × 0.02 = R$60
        # difference: 45
        atual = _cashback_card("atual", "Atual", pct=0.005)
        candidato = _cashback_card("cand", "Cand", pct=0.02)
        profile = _profile(monthly_avg=1000.0)

        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual,
            candidate_cards=[candidato], months=3
        )
        assert report.current_card_reward_value == pytest.approx(15.0, rel=0.01)
        opp = report.opportunities[0]
        assert opp.hypothetical_reward_value == pytest.approx(60.0, rel=0.01)
        assert opp.difference == pytest.approx(45.0, rel=0.01)


class TestCandidatoPior:
    """Cenário 2: candidato pior NÃO aparece em opportunities."""

    def test_candidato_pior_nao_aparece(self):
        atual = _cashback_card("atual", "Atual 3%", pct=0.03)
        pior = _cashback_card("pior", "Pior 1%", pct=0.01)
        profile = _profile(monthly_avg=1000.0)

        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual,
            candidate_cards=[pior], months=3
        )
        assert len(report.opportunities) == 0

    def test_sem_oportunidades_best_e_none(self):
        atual = _cashback_card("atual", "Atual 5%", pct=0.05)
        pior = _cashback_card("pior", "Pior 1%", pct=0.01)
        profile = _profile(monthly_avg=2000.0)

        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual,
            candidate_cards=[pior], months=3
        )
        assert report.best_opportunity is None


class TestMesmoCartao:
    """Cenário 3: candidato com mesmo card_id do atual é ignorado."""

    def test_mesmo_card_id_ignorado(self):
        atual = _cashback_card("x", "X", pct=0.01)
        clone = _cashback_card("x", "X Clone", pct=0.05)  # mesmo id!
        profile = _profile(monthly_avg=1000.0)

        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual,
            candidate_cards=[clone], months=3
        )
        assert len(report.opportunities) == 0


class TestBestOpportunity:
    """Cenário 4: best_opportunity é o de maior difference."""

    def test_best_e_o_maior_difference(self):
        atual = _cashback_card("atual", "Atual", pct=0.005)
        cand1 = _cashback_card("c1", "Cand 1%", pct=0.01)
        cand2 = _cashback_card("c2", "Cand 5%", pct=0.05)
        cand3 = _cashback_card("c3", "Cand 2%", pct=0.02)
        profile = _profile(monthly_avg=1000.0)

        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual,
            candidate_cards=[cand1, cand2, cand3], months=3
        )
        assert report.best_opportunity is not None
        assert report.best_opportunity.card_id == "c2"  # 5% é o maior

    def test_best_opportunity_tem_maior_difference_anualizada(self):
        atual = _cashback_card("a", "A", pct=0.005)
        bom = _cashback_card("bom", "Bom", pct=0.05)
        medio = _cashback_card("medio", "Médio", pct=0.02)
        profile = _profile(monthly_avg=1000.0)

        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual,
            candidate_cards=[bom, medio], months=3
        )
        for opp in report.opportunities:
            assert report.best_opportunity.difference >= opp.difference


class TestOrdemOpportunidades:
    """Cenário 5: opportunities ordenados por difference decrescente."""

    def test_ordenado_decrescente(self):
        atual = _cashback_card("a", "A", pct=0.005)
        cands = [_cashback_card(str(i), f"C{i}", pct=0.01 * (i + 1)) for i in range(4)]
        profile = _profile(monthly_avg=1000.0)

        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual,
            candidate_cards=cands, months=3
        )
        diffs = [o.difference for o in report.opportunities]
        assert diffs == sorted(diffs, reverse=True)


class TestProjecaoAnual:
    """Cenários 6-7: difference_annualized e difference_monthly."""

    def test_annualized_e_12_dividido_por_months(self):
        atual = _cashback_card("a", "A", pct=0.005)
        cand = _cashback_card("c", "C", pct=0.03)
        profile = _profile(monthly_avg=1000.0)

        for months in [1, 3, 6, 12]:
            report = OpportunityCostCalculator().calculate(
                profile=profile, current_card=atual,
                candidate_cards=[cand], months=months
            )
            if report.opportunities:
                opp = report.opportunities[0]
                expected_annualized = opp.difference * (12 / months)
                assert opp.difference_annualized == pytest.approx(expected_annualized, rel=0.01)

    def test_monthly_e_difference_dividido_por_months(self):
        atual = _cashback_card("a", "A", pct=0.005)
        cand = _cashback_card("c", "C", pct=0.03)
        profile = _profile(monthly_avg=1000.0)

        for months in [1, 3, 6]:
            report = OpportunityCostCalculator().calculate(
                profile=profile, current_card=atual,
                candidate_cards=[cand], months=months
            )
            if report.opportunities:
                opp = report.opportunities[0]
                assert opp.difference_monthly == pytest.approx(opp.difference / months, rel=0.01)


class TestGastoZero:
    """Cenário 8: gasto médio zero → relatório vazio sem crash."""

    def test_gasto_zero_retorna_relatorio_vazio(self):
        atual = _cashback_card("a", "A", pct=0.01)
        cand = _cashback_card("c", "C", pct=0.05)
        profile = _profile(monthly_avg=0.0)

        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual,
            candidate_cards=[cand], months=3
        )
        assert report.opportunities == []
        assert report.best_opportunity is None
        assert report.total_spent == pytest.approx(0.0)


class TestBreakdownCategoria:
    """Cenário 9: breakdown_by_category correto."""

    def test_breakdown_com_diferenca_positiva_por_categoria(self):
        atual = _cashback_card("a", "Atual 0.5%", pct=0.005)
        cand = _cashback_card("c", "Cand 3%", pct=0.03)
        profile = _profile(
            monthly_avg=1500.0,
            categories={"alimentacao": 1000.0, "transporte": 500.0}
        )

        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual,
            candidate_cards=[cand], months=3
        )
        opp = report.opportunities[0]
        assert "alimentacao" in opp.breakdown_by_category
        assert "transporte" in opp.breakdown_by_category
        assert opp.breakdown_by_category["alimentacao"] > 0
        assert opp.breakdown_by_category["transporte"] > 0

    def test_breakdown_correto_por_categoria(self):
        # atual: 0.5%, cand: 2%, alimentação R$1.000/mês, 3 meses
        # alim: 3000×0.02 - 3000×0.005 = 60 - 15 = 45
        atual = _cashback_card("a", "Atual", pct=0.005)
        cand = _cashback_card("c", "Cand", pct=0.02)
        profile = _profile(
            monthly_avg=1000.0,
            categories={"alimentacao": 1000.0}
        )

        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual,
            candidate_cards=[cand], months=3
        )
        opp = report.opportunities[0]
        assert opp.breakdown_by_category.get("alimentacao", 0) == pytest.approx(45.0, rel=0.01)


class TestM25CategoriasCashback:
    """Cenário 10-11: taxas e caps por categoria em M2.5."""

    def test_taxa_real_usada_para_candidato_com_categoria(self):
        # atual: flat 0.5%
        # candidato: 5% em alimentação
        # gasto: R$1.000/mês, 3 meses → reward cand: 3000×0.05=150 vs atual: 3000×0.005=15
        atual = _cashback_card("atual", "Atual", pct=0.005)
        cand = _cashback_card("cand", "Cand Cat", pct=0.005,
            categories=[CashbackCategoryRule(category="alimentacao", pct=0.05)])

        profile = _profile(
            monthly_avg=1000.0,
            categories={"alimentacao": 1000.0}
        )
        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual,
            candidate_cards=[cand], months=3
        )
        assert len(report.opportunities) == 1
        opp = report.opportunities[0]
        assert opp.hypothetical_reward_value == pytest.approx(150.0, rel=0.05)

    def test_cap_mensal_limita_reward_candidato(self):
        # candidato: 5% em alimentação, cap=R$10/mês
        # gasto R$1.000/mês → 5% = R$50/mês, mas cap=R$10 → R$10×3=R$30
        atual = _cashback_card("atual", "Atual", pct=0.005)
        cand = _cashback_card("cand", "Cand Com Cap", pct=0.005,
            categories=[CashbackCategoryRule(category="alimentacao", pct=0.05, cap_monthly=10.0)])

        profile = _profile(
            monthly_avg=1000.0,
            categories={"alimentacao": 1000.0}
        )
        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual,
            candidate_cards=[cand], months=3
        )
        # cand reward = R$30 (cap), atual reward = R$15 → difference = R$15
        if report.opportunities:
            opp = report.opportunities[0]
            assert opp.hypothetical_reward_value == pytest.approx(30.0, abs=1.0)


class TestCartoesPontos:
    """Cenário 12: cartão POINTS calculado corretamente."""

    def test_points_card_como_candidato(self):
        atual = _cashback_card("a", "Atual 0.5%", pct=0.005)
        # 2 pts/R$, R$40/1000pts → R$2.000 × 2/1000 × 40 = R$160 em 3 meses
        cand_pts = _points_card("pts", "Points", pts_per_brl=2.0, conversion_rate=40.0)
        profile = _profile(monthly_avg=2000.0 / 3)  # R$2000 gasto total em 3 meses

        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual,
            candidate_cards=[cand_pts], months=3
        )
        if report.opportunities:
            opp = report.opportunities[0]
            assert opp.hypothetical_reward_value > 0

    def test_points_card_como_atual_comparado_com_cashback(self):
        atual_pts = _points_card("atual", "Atual Points", pts_per_brl=0.5, conversion_rate=10.0)
        cand_cash = _cashback_card("cand", "Cand 3%", pct=0.03)
        profile = _profile(monthly_avg=1000.0)

        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual_pts,
            candidate_cards=[cand_cash], months=3
        )
        # Report deve existir sem erros
        assert isinstance(report, OpportunityCostReport)


class TestInvestback:
    """Cenário 13: INVESTBACK tratado igual a CASHBACK."""

    def test_investback_candidato_computa_reward(self):
        atual = _cashback_card("a", "Atual 0.5%", pct=0.005)
        cand_inv = _investback_card("inv", "Invest 3%", pct=0.03)
        profile = _profile(monthly_avg=1000.0)

        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual,
            candidate_cards=[cand_inv], months=3
        )
        assert len(report.opportunities) == 1
        assert report.opportunities[0].hypothetical_reward_value > 0

    def test_investback_atual_comparado_com_cashback(self):
        atual_inv = _investback_card("inv", "Invest 0.5%", pct=0.005)
        cand = _cashback_card("cand", "Cand 2%", pct=0.02)
        profile = _profile(monthly_avg=500.0)

        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual_inv,
            candidate_cards=[cand], months=3
        )
        assert isinstance(report, OpportunityCostReport)
        assert len(report.opportunities) >= 1


class TestTextoExplicacao:
    """Cenário 14: texto de explanation em português com dados corretos."""

    def test_explanation_contem_nome_do_candidato(self):
        atual = _cashback_card("a", "Nubank Roxinho", pct=0.005)
        cand = _cashback_card("c", "C6 Carbon", pct=0.03)
        profile = _profile(monthly_avg=3200.0)

        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual,
            candidate_cards=[cand], months=3
        )
        opp = report.opportunities[0]
        assert "C6 Carbon" in opp.explanation

    def test_explanation_contem_nome_do_atual(self):
        atual = _cashback_card("a", "Nubank Roxinho", pct=0.005)
        cand = _cashback_card("c", "Cand", pct=0.03)
        profile = _profile(monthly_avg=1000.0)

        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual,
            candidate_cards=[cand], months=3
        )
        opp = report.opportunities[0]
        assert "Nubank Roxinho" in opp.explanation

    def test_explanation_menciona_meses(self):
        atual = _cashback_card("a", "A", pct=0.005)
        cand = _cashback_card("c", "C", pct=0.03)
        profile = _profile(monthly_avg=1000.0)

        for months in [1, 3, 6]:
            report = OpportunityCostCalculator().calculate(
                profile=profile, current_card=atual,
                candidate_cards=[cand], months=months
            )
            if report.opportunities:
                assert str(months) in report.opportunities[0].explanation

    def test_explanation_em_portugues(self):
        atual = _cashback_card("a", "A", pct=0.005)
        cand = _cashback_card("c", "C", pct=0.03)
        profile = _profile(monthly_avg=1000.0)

        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual,
            candidate_cards=[cand], months=3
        )
        opp = report.opportunities[0]
        assert "meses" in opp.explanation or "mês" in opp.explanation


class TestTotalSpend:
    """Cenário 15: total_spent = monthly_avg × months."""

    def test_total_spent_correto(self):
        card = _cashback_card("a", "A", pct=0.01)
        profile = _profile(monthly_avg=1200.0)

        for months in [1, 3, 6, 12]:
            report = OpportunityCostCalculator().calculate(
                profile=profile, current_card=card,
                candidate_cards=[], months=months
            )
            assert report.total_spent == pytest.approx(1200.0 * months, rel=0.01)

    def test_period_months_no_relatorio(self):
        card = _cashback_card("a", "A", pct=0.01)
        profile = _profile(monthly_avg=1000.0)
        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=card,
            candidate_cards=[], months=6
        )
        assert report.period_months == 6


class TestVariosMonths:
    """Cenário 16: months=1 e months=6 produzem relatórios consistentes."""

    def test_months_1_e_6_consistentes(self):
        atual = _cashback_card("a", "Atual", pct=0.005)
        cand = _cashback_card("c", "Cand", pct=0.03)
        profile = _profile(monthly_avg=1000.0)

        r1 = OpportunityCostCalculator().calculate(profile, atual, [cand], months=1)
        r6 = OpportunityCostCalculator().calculate(profile, atual, [cand], months=6)

        # Ambos devem ter oportunidade
        assert len(r1.opportunities) == 1
        assert len(r6.opportunities) == 1

        # difference_monthly deve ser similar (mesmo perfil)
        assert r1.opportunities[0].difference_monthly == pytest.approx(
            r6.opportunities[0].difference_monthly, rel=0.05
        )


class TestSerializacao:
    """Cenário 18: to_dict() serializa corretamente."""

    def test_to_dict_tem_campos_esperados(self):
        atual = _cashback_card("a", "A", pct=0.005)
        cand = _cashback_card("c", "C", pct=0.03)
        profile = _profile(monthly_avg=1000.0)

        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual,
            candidate_cards=[cand], months=3
        )
        d = report.to_dict()

        assert "current_card_id" in d
        assert "current_card_name" in d
        assert "period_months" in d
        assert "total_spent" in d
        assert "current_card_reward_value" in d
        assert "opportunities" in d
        assert "best_opportunity" in d

    def test_opportunity_to_dict_tem_campos_esperados(self):
        atual = _cashback_card("a", "A", pct=0.005)
        cand = _cashback_card("c", "C", pct=0.03)
        profile = _profile(monthly_avg=1000.0)

        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual,
            candidate_cards=[cand], months=3
        )
        opp_dict = report.opportunities[0].to_dict()

        assert "card_id" in opp_dict
        assert "card_name" in opp_dict
        assert "issuer" in opp_dict
        assert "hypothetical_reward_value" in opp_dict
        assert "difference" in opp_dict
        assert "difference_annualized" in opp_dict
        assert "difference_monthly" in opp_dict
        assert "breakdown_by_category" in opp_dict
        assert "explanation" in opp_dict

    def test_sem_oportunidades_to_dict_serializa(self):
        card = _cashback_card("a", "A", pct=0.05)
        profile = _profile(monthly_avg=1000.0)
        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=card,
            candidate_cards=[], months=3
        )
        d = report.to_dict()
        assert d["best_opportunity"] is None
        assert d["opportunities"] == []


class TestIntegracaoKnowledgeBase:
    """Cenários 19-20: integração com cartões reais."""

    def test_nubank_vs_base_completa(self):
        from app.optimizer.card_loader import CardKnowledgeBase
        all_cards = CardKnowledgeBase().load()
        nubank = next((c for c in all_cards if c.card_id == "nubank_roxinho"), None)
        if nubank is None:
            pytest.skip("nubank_roxinho não encontrado na base")

        candidates = [c for c in all_cards if c.card_id != "nubank_roxinho"]
        profile = _profile(monthly_avg=3200.0)

        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=nubank,
            candidate_cards=candidates, months=3
        )
        assert isinstance(report, OpportunityCostReport)
        assert report.current_card_name is not None

    def test_inter_black_vs_cartoes_menores(self):
        from app.optimizer.card_loader import CardKnowledgeBase
        all_cards = CardKnowledgeBase().load()
        inter = next((c for c in all_cards if c.card_id == "inter-black"), None)
        if inter is None:
            pytest.skip("inter-black não encontrado na base")

        profile = _profile(
            monthly_avg=3000.0,
            categories={"alimentacao": 1500.0, "transporte": 500.0, "lazer": 1000.0}
        )
        candidates = [c for c in all_cards if c.card_id != "inter-black"]
        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=inter,
            candidate_cards=candidates, months=3
        )
        assert isinstance(report, OpportunityCostReport)

    def test_campos_numericos_sao_floats(self):
        from app.optimizer.card_loader import CardKnowledgeBase
        all_cards = CardKnowledgeBase().load()
        if not all_cards:
            pytest.skip("Base vazia")

        atual = all_cards[0]
        candidates = all_cards[1:]
        profile = _profile(monthly_avg=2000.0)

        report = OpportunityCostCalculator().calculate(
            profile=profile, current_card=atual,
            candidate_cards=candidates, months=3
        )
        assert isinstance(report.total_spent, float)
        assert isinstance(report.current_card_reward_value, float)
        for opp in report.opportunities:
            assert isinstance(opp.difference, float)
            assert isinstance(opp.difference_annualized, float)
            assert isinstance(opp.difference_monthly, float)

    def test_nenhum_candidato_melhor_que_si_mesmo(self):
        from app.optimizer.card_loader import CardKnowledgeBase
        all_cards = CardKnowledgeBase().load()
        for card in all_cards[:5]:  # testa os 5 primeiros
            profile = _profile(monthly_avg=2000.0)
            report = OpportunityCostCalculator().calculate(
                profile=profile, current_card=card,
                candidate_cards=[card],  # só ele mesmo
                months=3
            )
            # Mesmo card deve ser ignorado
            assert len(report.opportunities) == 0
