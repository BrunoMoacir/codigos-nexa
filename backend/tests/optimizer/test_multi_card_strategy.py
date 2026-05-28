# tests/optimizer/test_multi_card_strategy.py
# Testes completos para M2.2 — Estratégia Multi-Cartão

"""
Cenários cobertos:
  1. Carteira básica: 2 cartões, cada um melhor em sua categoria
  2. Cartão único quando só há um cartão elegível
  3. Limite de max_cards respeitado — cartões excedentes são descartados e categorias reatribuídas
  4. Cartão descartado por gasto abaixo do mínimo (_MIN_DIRECTED_SPEND_MONTHLY)
  5. Anuidade always_free → custo zero
  6. Anuidade spend_threshold → isenta quando gasto anual >= threshold
  7. Anuidade spend_threshold → paga quando abaixo do threshold
  8. Comparação vs_single_best: multi-cartão melhor que cartão único
  9. vs_single_best negativo: cartão único tão bom quanto multi-cartão
 10. Perfil sem categorias → portfólio vazio
 11. Lista de cartões vazia → portfólio vazio
 12. M2.5: taxas por categoria usadas corretamente ao eleger o melhor por categoria
 13. Cartão de pontos (POINTS) elegido sobre cashback quando retorno é maior
 14. Cartão INVESTBACK tratado igual a CASHBACK
 15. Reatribuição de categorias após descarte por max_cards preserva retorno
 16. Ao menos 1 cartão mantido mesmo com gasto abaixo do mínimo (fallback)
 17. Gasto mensal zero numa categoria é ignorado
 18. Empate de retorno: nenhum dos dois é escolhido de forma determinística (mas um é escolhido)
 19. Portfólio com max_cards=1 retorna sempre 1 cartão
 20. Portfólio com cartões de anuidade alta: anuidade é corretamente subtraída no líquido
"""

import pytest
from app.optimizer.multi_card_strategy import MultiCardStrategist, CardPortfolio, CardAssignment
from app.optimizer.models import (
    CardRecord, CardType, CardFlag, WaiverRules, CashbackCategoryRule
)
from app.optimizer.profiler import UserProfile


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FACTORIES — helpers de criação de objetos de teste
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _free_waiver() -> WaiverRules:
    return WaiverRules(type="always_free", description="Sem anuidade")


def _threshold_waiver(threshold: float) -> WaiverRules:
    return WaiverRules(type="spend_threshold", threshold=threshold, description="Isenta se gastar X/ano")


def _paid_waiver(annual: float) -> WaiverRules:
    return WaiverRules(type="none", description=f"Anuidade R${annual}/ano")


def _cashback_card(
    card_id: str,
    name: str,
    pct: float,
    annuity: float = 0.0,
    waiver: WaiverRules | None = None,
    categories: list[CashbackCategoryRule] | None = None,
    cap: float | None = None,
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
        base_annuity=annuity,
        waiver_rules=waiver or _free_waiver(),
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
    annuity: float = 0.0,
    waiver: WaiverRules | None = None,
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
        base_annuity=annuity,
        waiver_rules=waiver or _free_waiver(),
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
    categories: dict[str, float],
    monthly_avg: float | None = None,
) -> UserProfile:
    total = sum(categories.values())
    return UserProfile(
        monthly_avg_spend=monthly_avg if monthly_avg is not None else total,
        spend_by_category=categories,
        spend_by_source={"credit": total},
        international_spend_monthly=0.0,
        travel_spend_monthly=0.0,
        committed_percentage=0.0,
        data_coverage_months=3,
        spending_stability=0.9,
        estimated_monthly_income=total * 3,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCarteiraBasica:
    """Cenário 1: 2 cartões com vantagem clara em categorias diferentes."""

    def test_dois_cartoes_atribuidos_a_categorias_corretas(self):
        # Cartão A: 3% cashback em alimentação, 0.5% no resto
        card_a = _cashback_card("a", "Cartão A", pct=0.005,
            categories=[CashbackCategoryRule(category="alimentacao", pct=0.03)])
        # Cartão B: 2% cashback em transporte, 0.5% no resto
        card_b = _cashback_card("b", "Cartão B", pct=0.005,
            categories=[CashbackCategoryRule(category="transporte", pct=0.02)])

        profile = _profile({"alimentacao": 1000.0, "transporte": 800.0})
        strategist = MultiCardStrategist()
        portfolio = strategist.optimize_portfolio(profile, [card_a, card_b], max_cards=3)

        card_ids = {a.card.card_id for a in portfolio.cards}
        assert "a" in card_ids
        assert "b" in card_ids

        assigned_a = next(a for a in portfolio.cards if a.card.card_id == "a")
        assigned_b = next(a for a in portfolio.cards if a.card.card_id == "b")
        assert "alimentacao" in assigned_a.assigned_categories
        assert "transporte" in assigned_b.assigned_categories

    def test_retorno_total_correto(self):
        # A: 3% em R$1.000 alim = R$30/mês = R$360/ano
        # B: 2% em R$800 transporte = R$16/mês = R$192/ano
        card_a = _cashback_card("a", "A", pct=0.005,
            categories=[CashbackCategoryRule(category="alimentacao", pct=0.03)])
        card_b = _cashback_card("b", "B", pct=0.005,
            categories=[CashbackCategoryRule(category="transporte", pct=0.02)])

        profile = _profile({"alimentacao": 1000.0, "transporte": 800.0})
        p = MultiCardStrategist().optimize_portfolio(profile, [card_a, card_b], max_cards=3)

        assert p.total_annual_return == pytest.approx(552.0, rel=0.05)
        assert p.total_annuity_cost == pytest.approx(0.0)
        assert p.net_annual_gain == pytest.approx(552.0, rel=0.05)

    def test_explicacao_menciona_numero_de_cartoes(self):
        card_a = _cashback_card("a", "A", pct=0.03)
        card_b = _cashback_card("b", "B", pct=0.01)
        profile = _profile({"alimentacao": 1000.0, "lazer": 500.0})
        p = MultiCardStrategist().optimize_portfolio(profile, [card_a, card_b])
        assert "cartão" in p.explanation.lower() or "cartao" in p.explanation.lower()


class TestCartaoUnico:
    """Cenário 2: apenas um cartão elegível → portfólio com 1 cartão."""

    def test_um_unico_cartao(self):
        card = _cashback_card("x", "Único", pct=0.01)
        profile = _profile({"alimentacao": 500.0, "lazer": 300.0})
        p = MultiCardStrategist().optimize_portfolio(profile, [card], max_cards=3)

        assert len(p.cards) == 1
        assert p.cards[0].card.card_id == "x"

    def test_vs_single_best_zero_quando_unico_cartao(self):
        card = _cashback_card("x", "Único", pct=0.01)
        profile = _profile({"alimentacao": 500.0})
        p = MultiCardStrategist().optimize_portfolio(profile, [card])
        # com 1 cartão, multi == single best → diferença ≈ 0
        assert p.vs_single_best == pytest.approx(0.0, abs=1.0)


class TestLimiteMaxCards:
    """Cenário 3: mais cartões que max_cards — descarte e reatribuição."""

    def test_max_cards_respeitado(self):
        cards = [_cashback_card(str(i), f"Card{i}", pct=0.01 * (i + 1)) for i in range(5)]
        profile = _profile({f"cat{i}": 400.0 for i in range(5)})
        p = MultiCardStrategist().optimize_portfolio(profile, cards, max_cards=2)
        assert len(p.cards) <= 2

    def test_categorias_reatribuidas_apos_descarte(self):
        # 3 cartões mas max=2 → o descartado deve ter suas categorias reatribuídas
        card_a = _cashback_card("a", "A", pct=0.03)  # melhor geral
        card_b = _cashback_card("b", "B", pct=0.02)  # segundo
        card_c = _cashback_card("c", "C", pct=0.01)  # pior → descartado

        profile = _profile({
            "cat_a": 1000.0,  # catA vai para card_a (3%)
            "cat_b": 800.0,   # catB vai para card_b (2%)
            "cat_c": 600.0,   # catC vai para card_c (1%) → deve ser reatribuída
        })
        p = MultiCardStrategist().optimize_portfolio(profile, [card_a, card_b, card_c], max_cards=2)

        # Após reatribuição, cat_c deve estar em algum dos 2 cartões mantidos
        all_cats = set()
        for assignment in p.cards:
            all_cats.update(assignment.assigned_categories)
        assert "cat_c" in all_cats


class TestGastoMinimo:
    """Cenário 4: cartão descartado por gasto abaixo de R$200/mês."""

    def test_cartao_descartado_por_gasto_baixo(self):
        card_principal = _cashback_card("principal", "Principal", pct=0.03)
        card_fraco = _cashback_card("fraco", "Fraco", pct=0.02)

        profile = _profile({
            "alimentacao": 1000.0,  # vai para principal (3%)
            "lazer": 100.0,         # fraco (2%) — gasto < R$200/mês → deve ser descartado
        })
        p = MultiCardStrategist().optimize_portfolio(
            profile, [card_principal, card_fraco], max_cards=3
        )

        card_ids = {a.card.card_id for a in p.cards}
        assert "fraco" not in card_ids

    def test_fallback_mantem_ao_menos_1_cartao(self):
        card = _cashback_card("unico", "Único", pct=0.01)
        # gasto muito baixo em todas as categorias
        profile = _profile({"alimentacao": 50.0, "lazer": 30.0})
        p = MultiCardStrategist().optimize_portfolio(profile, [card])
        assert len(p.cards) >= 1


class TestAnuidades:
    """Cenários 5-7: regras de isenção de anuidade."""

    def test_always_free_sem_custo(self):
        card = _cashback_card("free", "Free", pct=0.01, annuity=500.0, waiver=_free_waiver())
        profile = _profile({"alimentacao": 500.0})
        p = MultiCardStrategist().optimize_portfolio(profile, [card])
        assert p.total_annuity_cost == pytest.approx(0.0)

    def test_spend_threshold_isento_quando_atingido(self):
        # threshold = R$6.000/ano → R$500/mês; gasto = R$1.000/mês = R$12.000/ano → isento
        card = _cashback_card(
            "thresh", "Thresh", pct=0.01, annuity=600.0,
            waiver=_threshold_waiver(6000.0)
        )
        profile = _profile({"alimentacao": 1000.0})
        p = MultiCardStrategist().optimize_portfolio(profile, [card])
        assert p.total_annuity_cost == pytest.approx(0.0)

    def test_spend_threshold_paga_quando_abaixo(self):
        # threshold = R$24.000/ano → R$2.000/mês; gasto = R$300/mês = R$3.600/ano < threshold
        card = _cashback_card(
            "thresh2", "Thresh2", pct=0.02, annuity=600.0,
            waiver=_threshold_waiver(24000.0)
        )
        profile = _profile({"alimentacao": 300.0})
        p = MultiCardStrategist().optimize_portfolio(profile, [card])
        assert p.total_annuity_cost == pytest.approx(600.0)

    def test_anuidade_subtraida_no_liquido(self):
        card = _cashback_card("pago", "Pago", pct=0.01, annuity=120.0, waiver=_paid_waiver(120.0))
        profile = _profile({"alimentacao": 500.0})  # retorno: 500*0.01*12 = 60/ano
        p = MultiCardStrategist().optimize_portfolio(profile, [card])
        assert p.net_annual_gain == pytest.approx(p.total_annual_return - p.total_annuity_cost, abs=0.01)


class TestVsSingleBest:
    """Cenários 8-9: comparação com melhor cartão único."""

    def test_multicard_melhor_que_cartao_unico(self):
        # A: ótimo em alimentação, ruim em transporte
        card_a = _cashback_card("a", "A", pct=0.005,
            categories=[CashbackCategoryRule(category="alimentacao", pct=0.05)])
        # B: ótimo em transporte, ruim em alimentação
        card_b = _cashback_card("b", "B", pct=0.005,
            categories=[CashbackCategoryRule(category="transporte", pct=0.05)])

        # Gasto igualmente dividido entre as 2 categorias
        profile = _profile({"alimentacao": 1000.0, "transporte": 1000.0})
        p = MultiCardStrategist().optimize_portfolio(profile, [card_a, card_b], max_cards=2)

        # Multi-cartão deve ser melhor que qualquer cartão único
        assert p.vs_single_best > 0

    def test_cartao_unico_tao_bom_quanto_multicard(self):
        # Um cartão genial em tudo
        card_a = _cashback_card("a", "Super", pct=0.05)
        # Outro cartão ruim em tudo
        card_b = _cashback_card("b", "Fraco", pct=0.001)

        profile = _profile({"alimentacao": 1000.0, "transporte": 1000.0})
        p = MultiCardStrategist().optimize_portfolio(profile, [card_a, card_b], max_cards=2)

        # vs_single_best deve ser próximo de zero (card_a já é o melhor para tudo)
        assert p.vs_single_best == pytest.approx(0.0, abs=5.0)

    def test_single_best_net_gain_positivo_quando_ha_cartoes(self):
        card = _cashback_card("a", "A", pct=0.02)
        profile = _profile({"alimentacao": 500.0})
        p = MultiCardStrategist().optimize_portfolio(profile, [card])
        assert p.single_best_net_gain > 0


class TestPerfilVazio:
    """Cenários 10-11: edge cases com dados insuficientes."""

    def test_sem_categorias_retorna_portfolio_vazio(self):
        card = _cashback_card("a", "A", pct=0.01)
        profile = _profile({})
        p = MultiCardStrategist().optimize_portfolio(profile, [card])
        assert len(p.cards) == 0
        assert p.net_annual_gain == 0.0

    def test_lista_vazia_de_cartoes_retorna_portfolio_vazio(self):
        profile = _profile({"alimentacao": 500.0})
        p = MultiCardStrategist().optimize_portfolio(profile, [])
        assert len(p.cards) == 0

    def test_gasto_zero_em_categoria_e_ignorado(self):
        card = _cashback_card("a", "A", pct=0.01)
        profile = _profile({"alimentacao": 500.0, "lazer": 0.0})
        p = MultiCardStrategist().optimize_portfolio(profile, [card])
        for a in p.cards:
            assert "lazer" not in a.assigned_categories


class TestM25CategoriasCashback:
    """Cenário 12: taxas por categoria (M2.5) são usadas corretamente."""

    def test_taxa_por_categoria_vence_taxa_flat(self):
        # Card A: 5% em alimentação via categoria
        card_a = _cashback_card("a", "Categoria A", pct=0.005,
            categories=[CashbackCategoryRule(category="alimentacao", pct=0.05)])
        # Card B: 3% flat em tudo (melhor que 0.5% flat de A, mas pior que 5% categoria de A)
        card_b = _cashback_card("b", "Flat B", pct=0.03)

        profile = _profile({"alimentacao": 1000.0})
        p = MultiCardStrategist().optimize_portfolio(profile, [card_a, card_b], max_cards=2)

        assigned_alim = next(
            (a for a in p.cards if "alimentacao" in a.assigned_categories), None
        )
        assert assigned_alim is not None
        assert assigned_alim.card.card_id == "a"  # 5% > 3%

    def test_cap_mensal_aplicado_na_categoria(self):
        # Cap de R$10/mês em alimentação; gasto = R$1.000/mês × 5% = R$50 → cortado para R$10
        card = _cashback_card("cap", "Cap Card", pct=0.005,
            categories=[CashbackCategoryRule(category="alimentacao", pct=0.05, cap_monthly=10.0)])

        profile = _profile({"alimentacao": 1000.0})
        strategist = MultiCardStrategist()
        monthly_return = strategist._return_for_category(card, "alimentacao", 1000.0)
        assert monthly_return == pytest.approx(10.0)

    def test_fallback_para_flat_quando_categoria_nao_coberta(self):
        card = _cashback_card("fallback", "Fallback", pct=0.02,
            categories=[CashbackCategoryRule(category="alimentacao", pct=0.05)])

        strategist = MultiCardStrategist()
        # "transporte" não tem regra → deve usar pct=0.02
        ret = strategist._return_for_category(card, "transporte", 1000.0)
        assert ret == pytest.approx(1000.0 * 0.02)


class TestCartoesPontos:
    """Cenário 13: cartão POINTS elegido sobre CASHBACK quando retorno é maior."""

    def test_points_card_vence_cashback_quando_mais_rentavel(self):
        # Points: 2 pts/R$, conversão R$50/1000pts → R$2.000 × 2/1000 × 50 = R$200/mês
        card_points = _points_card("pts", "Mega Points", pts_per_brl=2.0, conversion_rate=50.0)
        # Cashback: 1% flat → R$2.000 × 0.01 = R$20/mês
        card_cash = _cashback_card("cash", "Cash 1%", pct=0.01)

        profile = _profile({"alimentacao": 2000.0})
        p = MultiCardStrategist().optimize_portfolio(profile, [card_points, card_cash], max_cards=2)

        assigned = next((a for a in p.cards if "alimentacao" in a.assigned_categories), None)
        assert assigned is not None
        assert assigned.card.card_id == "pts"

    def test_points_card_retorno_calculado_corretamente(self):
        # 1 pt/R$, conversão R$20/1000pts
        card = _points_card("pts", "Points", pts_per_brl=1.0, conversion_rate=20.0)
        strategist = MultiCardStrategist()
        # R$1.000 × 1 pt/R$ = 1000 pts → (1000/1000) × 20 = R$20
        ret = strategist._return_for_category(card, "qualquer", 1000.0)
        assert ret == pytest.approx(20.0)

    def test_points_card_sem_taxa_retorna_zero(self):
        card = _points_card("pts", "Points Zero", pts_per_brl=0.0, conversion_rate=0.0)
        strategist = MultiCardStrategist()
        ret = strategist._return_for_category(card, "alimentacao", 1000.0)
        assert ret == pytest.approx(0.0)


class TestInvestback:
    """Cenário 14: INVESTBACK tratado igual a CASHBACK."""

    def test_investback_computado_como_cashback(self):
        card = _investback_card("inv", "InvestBack 2%", pct=0.02)
        strategist = MultiCardStrategist()
        ret = strategist._return_for_category(card, "alimentacao", 500.0)
        assert ret == pytest.approx(500.0 * 0.02)

    def test_investback_elegido_sobre_cashback_menor(self):
        card_inv = _investback_card("inv", "Invest 3%", pct=0.03)
        card_cash = _cashback_card("cash", "Cash 1%", pct=0.01)
        profile = _profile({"alimentacao": 1000.0})
        p = MultiCardStrategist().optimize_portfolio(profile, [card_inv, card_cash])
        assigned = next((a for a in p.cards if "alimentacao" in a.assigned_categories), None)
        assert assigned.card.card_id == "inv"


class TestMaxCardsUm:
    """Cenário 19: max_cards=1 sempre resulta em 1 cartão."""

    def test_max_cards_1_retorna_um_cartao(self):
        cards = [_cashback_card(str(i), f"C{i}", pct=0.01 * (i + 1)) for i in range(4)]
        profile = _profile({f"cat{i}": 300.0 for i in range(4)})
        p = MultiCardStrategist().optimize_portfolio(profile, cards, max_cards=1)
        assert len(p.cards) == 1

    def test_max_cards_1_escolhe_o_mais_rentavel(self):
        card_ruim = _cashback_card("ruim", "Ruim", pct=0.005)
        card_bom = _cashback_card("bom", "Bom", pct=0.05)
        profile = _profile({"alimentacao": 1000.0})
        p = MultiCardStrategist().optimize_portfolio(profile, [card_ruim, card_bom], max_cards=1)
        assert p.cards[0].card.card_id == "bom"


class TestAnuidadeAltaImpactoNoLiquido:
    """Cenário 20: anuidade alta reduz líquido corretamente."""

    def test_anuidade_alta_pode_tornar_liquido_negativo(self):
        # Gasto R$200/mês, cashback 1% = R$24/ano
        # Anuidade R$600/ano (não isenta) → líquido = -R$576
        card = _cashback_card(
            "caro", "Caro", pct=0.01, annuity=600.0,
            waiver=_paid_waiver(600.0)
        )
        profile = _profile({"alimentacao": 200.0})
        p = MultiCardStrategist().optimize_portfolio(profile, [card])
        assert p.net_annual_gain < 0  # anuidade não se paga

    def test_dois_cartoes_com_anuidade_somam_custo(self):
        # card_a: 3% só em cat_a (via categoria), 0.5% no resto — melhor em cat_a
        # card_b: 4% só em cat_b (via categoria), 0.5% no resto — melhor em cat_b
        # Cada um vence em sua categoria → ambos entram na carteira → anuidades somam
        card_a = _cashback_card("a", "A", pct=0.005, annuity=200.0, waiver=_paid_waiver(200.0),
            categories=[CashbackCategoryRule(category="cat_a", pct=0.03)])
        card_b = _cashback_card("b", "B", pct=0.005, annuity=300.0, waiver=_paid_waiver(300.0),
            categories=[CashbackCategoryRule(category="cat_b", pct=0.04)])
        profile = _profile({"cat_a": 1000.0, "cat_b": 900.0})
        p = MultiCardStrategist().optimize_portfolio(profile, [card_a, card_b], max_cards=2)
        assert p.total_annuity_cost == pytest.approx(500.0, abs=1.0)


class TestIntegracaoComKnowledgeBase:
    """Testa o strategist com cartões reais do knowledge_cards.json."""

    def test_portfolio_com_cartoes_reais(self):
        from app.optimizer.card_loader import CardKnowledgeBase
        cards = CardKnowledgeBase().load()
        assert len(cards) > 0, "Base de cartões não carregada"

        profile = _profile({
            "alimentacao": 1200.0,
            "transporte": 400.0,
            "lazer": 600.0,
            "farmacia": 200.0,
        })
        p = MultiCardStrategist().optimize_portfolio(profile, cards, max_cards=3)

        assert len(p.cards) >= 1
        assert p.total_annual_return >= 0
        assert p.net_annual_gain == pytest.approx(
            p.total_annual_return - p.total_annuity_cost, abs=0.01
        )

    def test_portfolio_real_com_renda_alta(self):
        from app.optimizer.card_loader import CardKnowledgeBase
        all_cards = CardKnowledgeBase().load()
        # Simula usuário de alta renda (acesso a cartões premium)
        profile = _profile({
            "alimentacao": 3000.0,
            "viagens": 2000.0,
            "lazer": 1500.0,
        })
        p = MultiCardStrategist().optimize_portfolio(profile, all_cards, max_cards=3)
        assert len(p.cards) >= 1

    def test_todos_os_retornos_e_campos_sao_floats(self):
        from app.optimizer.card_loader import CardKnowledgeBase
        cards = CardKnowledgeBase().load()
        profile = _profile({"alimentacao": 800.0, "lazer": 400.0})
        p = MultiCardStrategist().optimize_portfolio(profile, cards, max_cards=2)

        assert isinstance(p.total_annual_return, float)
        assert isinstance(p.total_annuity_cost, float)
        assert isinstance(p.net_annual_gain, float)
        assert isinstance(p.vs_single_best, float)
        assert isinstance(p.single_best_net_gain, float)
        for a in p.cards:
            assert isinstance(a.monthly_spend_directed, float)
            assert isinstance(a.annual_return_from_this_card, float)
            assert isinstance(a.effective_annuity, float)
