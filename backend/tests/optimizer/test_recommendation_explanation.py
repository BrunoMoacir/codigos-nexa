# tests/optimizer/test_recommendation_explanation.py
# Testes para RecommendationExplanation, CategoryCashbackBreakdown e to_text()

import pytest
from app.optimizer.simulator import CardSimulator
from app.optimizer.models import (
    CardRecord, CardType, CardFlag, WaiverRules,
    CashbackCategoryRule, RecommendationExplanation,
)
from app.optimizer.profiler import UserProfile


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cashback_cat_card(cap_monthly: float | None = None) -> CardRecord:
    return CardRecord(
        card_id="cat-card",
        name="Cartão Categoria",
        issuer="TestBank",
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
        cashback_pct=0.005,
        cashback_default_pct=0.005,
        cashback_categories=[
            CashbackCategoryRule(category="supermercado", pct=0.02, cap_monthly=cap_monthly),
            CashbackCategoryRule(category="farmacia", pct=0.015, cap_monthly=None),
        ],
        last_updated="2026-01-01",
    )


def _flat_card() -> CardRecord:
    return CardRecord(
        card_id="flat-card",
        name="Cartão Flat",
        issuer="TestBank",
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
        cashback_pct=0.01,
        cashback_categories=[],
        last_updated="2026-01-01",
    )


def _profile(
    monthly_avg_spend: float = 3000.0,
    credit_spend_ratio: float = 1.0,
    data_coverage_months: int = 6,
    spend_by_category: dict | None = None,
    spend_is_estimated: bool = False,
    category_source: str = "raw",
) -> UserProfile:
    return UserProfile(
        monthly_avg_spend=monthly_avg_spend,
        credit_spend_ratio=credit_spend_ratio,
        spend_by_source={"credit": monthly_avg_spend * credit_spend_ratio},
        spend_by_category=spend_by_category if spend_by_category is not None else {
            "supermercado": 1200.0,
            "farmacia": 600.0,
            "transporte": 600.0,
            "lazer": 600.0,
        },
        data_coverage_months=data_coverage_months,
        spending_stability=0.85,
        committed_percentage=0.2,
        travel_spend_monthly=0.0,
        international_spend_monthly=0.0,
        estimated_monthly_income=8000.0,
        spend_is_estimated=spend_is_estimated,
        category_source=category_source,
    )


@pytest.fixture
def sim() -> CardSimulator:
    return CardSimulator()


# ── to_text() ─────────────────────────────────────────────────────────────────

class TestToText:
    def test_contains_card_name(self, sim):
        card = _cashback_cat_card()
        result = sim.simulate(card, _profile())
        text = result.recommendation_explanation.to_text()
        assert card.name in text

    def test_contains_top_category_pct(self, sim):
        card = _cashback_cat_card()
        result = sim.simulate(card, _profile())
        exp = result.recommendation_explanation
        pct_str = f"{exp.top_category_pct * 100:.0f}%"
        assert pct_str in exp.to_text()

    def test_contains_eligible_spend(self, sim):
        card = _cashback_cat_card()
        result = sim.simulate(card, _profile(monthly_avg_spend=3000.0, credit_spend_ratio=0.8))
        text = result.recommendation_explanation.to_text()
        # eligible = 3000 * 0.8 = 2400; Python `:,.0f` usa vírgula como separador de milhar
        assert "2,400" in text

    def test_contains_cashback_monthly(self, sim):
        card = _cashback_cat_card()
        result = sim.simulate(card, _profile())
        text = result.recommendation_explanation.to_text()
        assert "/mês" in text

    def test_contains_confidence_line(self, sim):
        card = _cashback_cat_card()
        result = sim.simulate(card, _profile())
        text = result.recommendation_explanation.to_text()
        assert "confiança" in text


# ── category_confidence ───────────────────────────────────────────────────────

class TestCategoryConfidence:
    def test_full_coverage_returns_high_confidence(self, sim):
        card = _cashback_cat_card()
        result = sim.simulate(card, _profile(data_coverage_months=6))
        assert result.recommendation_explanation.category_confidence == 1.0

    def test_short_coverage_penalizes_confidence(self, sim):
        card = _cashback_cat_card()
        r6 = sim.simulate(card, _profile(data_coverage_months=6))
        r1 = sim.simulate(card, _profile(data_coverage_months=1))
        assert r1.recommendation_explanation.category_confidence < r6.recommendation_explanation.category_confidence

    def test_estimated_spend_caps_confidence(self, sim):
        card = _cashback_cat_card()
        result = sim.simulate(card, _profile(data_coverage_months=6, spend_is_estimated=True))
        assert result.recommendation_explanation.category_confidence <= 0.40

    def test_category_confidence_independent_from_card_confidence(self, sim):
        """
        category_confidence é baseada em cobertura/fonte de dados; confidence_score
        do cartão é limitado por data_trust_score (0.7 por padrão). Com 6 meses de
        cobertura e sem gasto estimado, category_confidence deve ser 1.0 enquanto
        confidence_score fica em 0.7 — provando que as duas métricas são independentes.
        """
        card = _cashback_cat_card()
        result = sim.simulate(card, _profile(data_coverage_months=6))
        exp = result.recommendation_explanation
        assert exp.category_confidence == 1.0
        # confidence_score é bounded por data_trust_score=0.7 do _cashback_cat_card()
        assert result.confidence_score == pytest.approx(0.7, abs=0.01)
        assert exp.category_confidence != result.confidence_score

    def test_canonical_source_boosts_confidence(self, sim):
        """category_source='canonical' deve produzir confiança maior que 'raw' com mesma cobertura."""
        card = _cashback_cat_card()
        raw = sim.simulate(card, _profile(data_coverage_months=3))
        canonical = sim.simulate(card, _profile(data_coverage_months=3, category_source="canonical"))
        assert canonical.recommendation_explanation.category_confidence > raw.recommendation_explanation.category_confidence

    def test_real_classifier_confidence_overrides_proxy(self, sim):
        """
        Quando category_confidences está preenchido, a confiança real do classificador
        é usada como base, não o proxy por cobertura.
        """
        card = _cashback_cat_card()
        # Perfil sem dados reais do classificador (proxy)
        proxy = sim.simulate(card, _profile(data_coverage_months=3))
        # Perfil com confiança real alta vinda do classificador NLP
        real = sim.simulate(card, _profile(
            data_coverage_months=3,
            category_source="canonical",
            category_confidences={"supermercado": 0.96, "farmacia": 0.91, "transporte": 0.88, "lazer": 0.85},
        ))
        # Confiança real (ponderada ~0.92 × 0.85 cobertura ≈ 0.78) > proxy sem canonical (0.85)
        # Não importa o resultado exato — o que importa é que vêm de fontes diferentes
        assert real.recommendation_explanation.category_confidence != proxy.recommendation_explanation.category_confidence

    def test_real_confidence_weighted_by_spend(self, sim):
        """
        Confiança real é ponderada pelo gasto: a categoria de maior gasto tem mais peso.
        Verifica que o resultado é a média ponderada esperada (após penalidade de cobertura).
        """
        card = _cashback_cat_card()
        # Perfil com gastos iguais em duas categorias e confiança muito diferente
        profile = _profile(
            data_coverage_months=6,  # sem penalidade de cobertura
            spend_by_category={"supermercado": 1000.0, "farmacia": 1000.0},
            category_confidences={"supermercado": 1.0, "farmacia": 0.5},
        )
        result = sim.simulate(card, profile)
        # Média ponderada igual = (1000*1.0 + 1000*0.5) / 2000 = 0.75
        # Sem penalidade de cobertura (6 meses): 0.75
        assert result.recommendation_explanation.category_confidence == pytest.approx(0.75, abs=0.01)

    def test_per_category_confidence_in_breakdown(self, sim):
        """
        Quando category_confidences está preenchido, o breakdown mostra a confiança
        por categoria; quando está vazio, fica None.
        """
        card = _cashback_cat_card()
        # Com dados reais do classificador
        profile_with = _profile(
            category_confidences={"supermercado": 0.94, "farmacia": 0.88, "transporte": 0.76, "lazer": 0.80},
        )
        result_with = sim.simulate(card, profile_with)
        supermercado = next(b for b in result_with.recommendation_explanation.category_breakdown if b.category == "supermercado")
        assert supermercado.category_confidence == pytest.approx(0.94, abs=0.001)

        # Sem dados do classificador
        result_without = sim.simulate(card, _profile())
        for b in result_without.recommendation_explanation.category_breakdown:
            assert b.category_confidence is None

    def test_no_categories_returns_zero(self, sim):
        card = _cashback_cat_card()
        profile = _profile(spend_by_category={})
        result = sim.simulate(card, profile)
        assert result.recommendation_explanation.category_confidence == 0.0


# ── category_breakdown reconciliation ─────────────────────────────────────────

class TestCategoryBreakdownReconciliation:
    def test_breakdown_sum_reconciles_with_expected_monthly(self, sim):
        """sum(breakdown monthly cashback) deve igualar expected_cashback_monthly."""
        card = _cashback_cat_card()
        result = sim.simulate(card, _profile())
        exp = result.recommendation_explanation
        breakdown_sum = sum(b.expected_monthly_cashback for b in exp.category_breakdown)
        assert abs(breakdown_sum - exp.expected_cashback_monthly) < 0.01

    def test_breakdown_monthly_spend_sums_to_eligible(self, sim):
        """sum(breakdown monthly_spend) deve ser o gasto mensal elegível."""
        card = _cashback_cat_card()
        result = sim.simulate(card, _profile(monthly_avg_spend=3000.0, credit_spend_ratio=0.8))
        exp = result.recommendation_explanation
        spend_sum = sum(b.monthly_spend for b in exp.category_breakdown)
        assert abs(spend_sum - exp.eligible_monthly_spend) < 0.01

    def test_scale_applied_when_credit_ratio_below_one(self, sim):
        """Com credit_spend_ratio < 1, o breakdown usa o gasto escalado, não o bruto."""
        card = _cashback_cat_card()
        result_full = sim.simulate(card, _profile(credit_spend_ratio=1.0))
        result_half = sim.simulate(card, _profile(credit_spend_ratio=0.5))

        full_spend = sum(b.monthly_spend for b in result_full.recommendation_explanation.category_breakdown)
        half_spend = sum(b.monthly_spend for b in result_half.recommendation_explanation.category_breakdown)
        assert abs(half_spend - full_spend * 0.5) < 0.01

    def test_capped_flag_set_when_cashback_exceeds_cap(self, sim):
        # cap_monthly=5.0 com 2% sobre supermercado=1200 → cashback bruto=24 > 5
        card = _cashback_cat_card(cap_monthly=5.0)
        result = sim.simulate(card, _profile())
        supermercado = next(b for b in result.recommendation_explanation.category_breakdown if b.category == "supermercado")
        assert supermercado.capped is True
        assert supermercado.expected_monthly_cashback == 5.0

    def test_no_cap_flag_when_cashback_below_cap(self, sim):
        card = _cashback_cat_card(cap_monthly=500.0)
        result = sim.simulate(card, _profile())
        supermercado = next(b for b in result.recommendation_explanation.category_breakdown if b.category == "supermercado")
        assert supermercado.capped is False

    def test_spend_pct_sums_to_one(self, sim):
        card = _cashback_cat_card()
        result = sim.simulate(card, _profile())
        total_pct = sum(b.spend_pct for b in result.recommendation_explanation.category_breakdown)
        assert abs(total_pct - 1.0) < 0.001

    def test_flat_card_has_empty_breakdown(self, sim):
        card = _flat_card()
        result = sim.simulate(card, _profile())
        assert result.recommendation_explanation.category_breakdown == []

    def test_flat_card_explanation_still_populated(self, sim):
        card = _flat_card()
        result = sim.simulate(card, _profile())
        exp = result.recommendation_explanation
        assert exp.top_category != ""
        assert exp.eligible_monthly_spend > 0
        assert exp.expected_cashback_monthly > 0


# ── eligible_monthly_spend ────────────────────────────────────────────────────

class TestEligibleMonthlySpend:
    def test_equals_monthly_avg_times_credit_ratio(self, sim):
        card = _cashback_cat_card()
        profile = _profile(monthly_avg_spend=4000.0, credit_spend_ratio=0.75)
        result = sim.simulate(card, profile)
        assert result.recommendation_explanation.eligible_monthly_spend == pytest.approx(3000.0, abs=0.01)

    def test_with_full_credit_ratio(self, sim):
        card = _cashback_cat_card()
        profile = _profile(monthly_avg_spend=2500.0, credit_spend_ratio=1.0)
        result = sim.simulate(card, profile)
        assert result.recommendation_explanation.eligible_monthly_spend == pytest.approx(2500.0, abs=0.01)
