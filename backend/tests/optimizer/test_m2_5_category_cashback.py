# tests/optimizer/test_m2_5_category_cashback.py
# Testes para M2.5 — Cashback por Categoria Detalhado

import pytest
from app.optimizer.simulator import CardSimulator
from app.optimizer.models import (
    CardRecord, CardType, CardFlag, WaiverRules,
    CashbackCategoryRule,
)
from app.optimizer.profiler import UserProfile


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cashback_card_with_categories() -> CardRecord:
    """Cartão cashback com taxas diferenciadas por categoria (similar Inter Black)."""
    return CardRecord(
        card_id="test-cashback-cat",
        name="Test Cashback Card",
        issuer="Test",
        flag=CardFlag.MASTERCARD,
        card_type=CardType.CASHBACK,
        public_target="geral",
        min_income=0,
        requires_proof_of_income=False,
        secured_card=False,
        prepaid=False,
        consigned=False,
        base_annuity=0.0,
        waiver_rules=WaiverRules(type="always_free", description="Sem anuidade"),
        cashback_pct=0.005,            # taxa base flat
        cashback_default_pct=0.005,    # taxa padrão para categorias não cobertas
        cashback_categories=[
            CashbackCategoryRule(category="alimentacao", pct=0.015, cap_monthly=None),
            CashbackCategoryRule(category="farmacia",    pct=0.020, cap_monthly=40.0),
            CashbackCategoryRule(category="transporte",  pct=0.010, cap_monthly=None),
        ],
        last_updated="2026-01-01",
    )


def _flat_cashback_card() -> CardRecord:
    """Cartão cashback simples, sem regras de categoria (comportamento original)."""
    return CardRecord(
        card_id="test-flat",
        name="Test Flat Cashback",
        issuer="Test",
        flag=CardFlag.VISA,
        card_type=CardType.CASHBACK,
        public_target="geral",
        min_income=0,
        requires_proof_of_income=False,
        secured_card=False,
        prepaid=False,
        consigned=False,
        base_annuity=0.0,
        waiver_rules=WaiverRules(type="always_free", description="Sem anuidade"),
        cashback_pct=0.005,
        cashback_categories=[],        # sem regras → usa cashback_pct flat
        last_updated="2026-01-01",
    )


def _profile_alimentacao_heavy() -> UserProfile:
    """Perfil com 70% dos gastos em alimentação — deve se beneficiar mais da taxa maior."""
    return UserProfile(
        monthly_avg_spend=2000.0,
        spend_by_category={
            "alimentacao": 1400.0,   # 70%
            "lazer": 300.0,          # 15%
            "transporte": 300.0,     # 15%
        },
        spend_by_source={"credit": 2000.0},
        international_spend_monthly=0.0,
        travel_spend_monthly=0.0,
        committed_percentage=0.0,
        data_coverage_months=3,
        spending_stability=0.8,
        estimated_monthly_income=6000.0,
    )


def _profile_farmacia_heavy() -> UserProfile:
    """Perfil com muitos gastos em farmácia (categoria com cap mensal)."""
    return UserProfile(
        monthly_avg_spend=1000.0,
        spend_by_category={
            "farmacia": 800.0,      # quase tudo em farmácia
            "lazer":    200.0,
        },
        spend_by_source={"credit": 1000.0},
        international_spend_monthly=0.0,
        travel_spend_monthly=0.0,
        committed_percentage=0.0,
        data_coverage_months=3,
        spending_stability=0.8,
        estimated_monthly_income=3000.0,
    )


# ── Testes unitários ──────────────────────────────────────────────────────────

def test_category_cashback_higher_than_flat():
    """Com taxas por categoria maiores, retorno deve superar o cashback flat."""
    card_cat = _cashback_card_with_categories()
    card_flat = _flat_cashback_card()
    profile = _profile_alimentacao_heavy()

    sim = CardSimulator()
    spend_annual = profile.monthly_avg_spend * 12

    value_cat  = sim._compute_benefit_value(card_cat,  spend_annual, profile)
    value_flat = sim._compute_benefit_value(card_flat, spend_annual, profile)

    # 70% em alimentação a 1.5% >> 0.5% flat
    assert value_cat > value_flat


def test_cap_monthly_is_respected():
    """Com cap_monthly=40 em farmácia, o cashback anual de farmácia não deve ultrapassar R$ 480."""
    card = _cashback_card_with_categories()
    profile = _profile_farmacia_heavy()  # R$800/mês em farmácia → seria R$800*2%=R$16, mas cap=R$40 → cap não atinge

    sim = CardSimulator()
    spend_annual = profile.monthly_avg_spend * 12

    # R$800/mês em farmácia × 2% = R$16/mês → abaixo de cap R$40 → sem corte
    value = sim._compute_category_cashback(card, profile, spend_annual)
    # farmácia: 16/mês × 12 = R$192/ano; lazer: 200×0.5%×12=R$12/ano → total ~R$204
    assert value == pytest.approx(204.0, rel=0.05)


def test_cap_monthly_cuts_high_spend():
    """Quando gasto em farmácia supera o cap, cashback deve ser cortado."""
    from dataclasses import replace
    card = _cashback_card_with_categories()
    # Perfil com gasto MUITO alto em farmácia: R$3.000/mês → 2% = R$60/mês, cap=R$40
    profile = UserProfile(
        monthly_avg_spend=3000.0,
        spend_by_category={"farmacia": 3000.0},
        spend_by_source={"credit": 3000.0},
        international_spend_monthly=0.0,
        travel_spend_monthly=0.0,
        committed_percentage=0.0,
        data_coverage_months=3,
        spending_stability=0.8,
        estimated_monthly_income=10000.0,
    )

    sim = CardSimulator()
    spend_annual = profile.monthly_avg_spend * 12
    value = sim._compute_category_cashback(card, profile, spend_annual)

    # cap=R$40/mês × 12 = R$480/ano máximo para farmácia
    assert value == pytest.approx(480.0, rel=0.01)


def test_uncovered_category_uses_default_pct():
    """Categoria não coberta (ex: 'lazer') deve usar cashback_default_pct."""
    card = _cashback_card_with_categories()
    profile = UserProfile(
        monthly_avg_spend=1000.0,
        spend_by_category={"lazer": 1000.0},  # lazer não tem regra → usa 0.5%
        spend_by_source={"credit": 1000.0},
        international_spend_monthly=0.0,
        travel_spend_monthly=0.0,
        committed_percentage=0.0,
        data_coverage_months=3,
        spending_stability=0.8,
        estimated_monthly_income=4000.0,
    )

    sim = CardSimulator()
    spend_annual = profile.monthly_avg_spend * 12
    value = sim._compute_benefit_value(card, spend_annual, profile)

    # lazer a 0.5% flat: 1000 × 0.005 × 12 = R$60/ano
    assert value == pytest.approx(60.0, rel=0.01)


def test_no_category_rules_falls_back_to_flat():
    """Cartão sem cashback_categories usa lógica flat original."""
    card = _flat_cashback_card()
    profile = _profile_alimentacao_heavy()

    sim = CardSimulator()
    spend_annual = profile.monthly_avg_spend * 12
    value = sim._compute_benefit_value(card, spend_annual, profile)

    # 0.5% flat sobre todo o gasto
    expected = spend_annual * 0.005
    assert value == pytest.approx(expected, rel=0.01)


def test_no_profile_falls_back_to_flat():
    """Sem profile (None), mesmo cartão com categorias usa cashback_pct flat."""
    card = _cashback_card_with_categories()

    sim = CardSimulator()
    spend_annual = 24_000.0  # R$2k/mês × 12
    value = sim._compute_benefit_value(card, spend_annual, profile=None)

    expected = spend_annual * 0.005
    assert value == pytest.approx(expected, rel=0.01)


def test_knowledge_cards_load_with_categories():
    """Inter Black carregado do JSON deve ter cashback_categories populado."""
    from app.optimizer.card_loader import CardKnowledgeBase
    cards = CardKnowledgeBase().load()
    inter = next((c for c in cards if c.card_id == "inter-black"), None)
    assert inter is not None, "inter-black não encontrado"
    assert len(inter.cashback_categories) > 0, "inter-black deve ter cashback_categories"
    assert any(r.category == "alimentacao" for r in inter.cashback_categories)
    assert any(r.pct > 0.005 for r in inter.cashback_categories)  # pelo menos uma taxa > base


def test_simulate_uses_category_cashback():
    """O método simulate() completo deve usar category rules quando disponíveis."""
    from app.optimizer.card_loader import CardKnowledgeBase
    cards = CardKnowledgeBase().load()
    inter = next(c for c in cards if c.card_id == "inter-black")

    profile = _profile_alimentacao_heavy()
    flat_card = _flat_cashback_card()

    sim = CardSimulator()
    result_inter = sim.simulate(inter, profile)
    result_flat  = sim.simulate(flat_card, profile)

    # Inter Black com categorias deve render mais que flat 0.5%
    assert result_inter.points_value_expected >= result_flat.points_value_expected
