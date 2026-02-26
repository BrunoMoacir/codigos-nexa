# tests/optimizer/test_simulator.py
# Testes unitários para CardSimulator
# Passo 2.3 — Funcionalidade 2: Nexa Optimizer

import pytest
from app.optimizer.simulator import CardSimulator
from app.optimizer.profiler import UserProfile
from app.optimizer.models import (
    CardRecord, CardFlag, CardType, LiquidityRisk, WaiverRules, BenefitTag
)


# ─── Fixtures ──────────────────────────────────────────────────────────────────

def _make_profile(
    monthly_avg_spend: float = 2000.0,
    data_coverage_months: int = 3,
    spending_stability: float = 0.8,
    committed_percentage: float = 0.2,
    international_spend_monthly: float = 0.0,
    travel_spend_monthly: float = 0.0,
    spend_by_category: dict = None,
    spend_by_source: dict = None,
) -> UserProfile:
    return UserProfile(
        monthly_avg_spend=monthly_avg_spend,
        committed_percentage=committed_percentage,
        spend_by_category=spend_by_category or {"Alimentação": 800.0, "Transporte": 400.0},
        spend_by_source=spend_by_source or {"debit": 1200.0, "credit": 800.0},
        international_spend_monthly=international_spend_monthly,
        travel_spend_monthly=travel_spend_monthly,
        estimated_monthly_income=5000.0,
        data_coverage_months=data_coverage_months,
        spending_stability=spending_stability,
    )


def _make_card(
    card_type: CardType = CardType.POINTS,
    base_annuity: float = 0.0,
    waiver_type: str = "always_free",
    waiver_threshold: float | None = None,
    points_per_brl: float | None = 1.0,
    points_conversion_rate: float = 10.0,
    cashback_pct: float | None = None,
    cashback_cap: float | None = None,
    data_trust_score: float = 1.0,
    benefit_tags: list[BenefitTag] = None,
) -> CardRecord:
    return CardRecord(
        card_id="test-card",
        name="Test Card",
        issuer="TestBank",
        flag=CardFlag.VISA,
        card_type=card_type,
        public_target="geral",
        min_income=0,
        requires_proof_of_income=False,
        secured_card=False,
        prepaid=False,
        consigned=False,
        base_annuity=base_annuity,
        waiver_rules=WaiverRules(
            type=waiver_type,
            threshold=waiver_threshold,
            description="test",
        ),
        cashback_pct=cashback_pct,
        cashback_cap=cashback_cap,
        points_per_brl=points_per_brl,
        points_conversion_rate=points_conversion_rate,
        benefit_tags=benefit_tags or [],
        benefits_detail=["Benefício 1", "Benefício 2", "Benefício 3", "Benefício 4"],
        data_trust_score=data_trust_score,
        last_updated="2026-01-01",
    )


@pytest.fixture
def sim():
    return CardSimulator()


# ─── Anuidade ──────────────────────────────────────────────────────────────────

class TestAnnuity:
    def test_always_free_waives_annuity(self, sim):
        card = _make_card(base_annuity=1200.0, waiver_type="always_free")
        result = sim.simulate(card, _make_profile())
        assert result.annuity_effective == 0.0
        assert result.annuity_waived is True

    def test_spend_threshold_met_waives_annuity(self, sim):
        # gasto anual = 2000 × 12 = 24000 >= 20000
        card = _make_card(base_annuity=1200.0, waiver_type="spend_threshold", waiver_threshold=20000.0)
        result = sim.simulate(card, _make_profile(monthly_avg_spend=2000.0))
        assert result.annuity_effective == 0.0
        assert result.annuity_waived is True

    def test_spend_threshold_not_met_charges_annuity(self, sim):
        # gasto anual = 1000 × 12 = 12000 < 20000
        card = _make_card(base_annuity=1200.0, waiver_type="spend_threshold", waiver_threshold=20000.0)
        result = sim.simulate(card, _make_profile(monthly_avg_spend=1000.0))
        assert result.annuity_effective == 1200.0
        assert result.annuity_waived is False

    def test_waiver_type_none_charges_full_annuity(self, sim):
        card = _make_card(base_annuity=600.0, waiver_type="none")
        result = sim.simulate(card, _make_profile())
        assert result.annuity_effective == 600.0
        assert result.annuity_waived is False

    def test_transaction_count_conservative_charges_annuity(self, sim):
        # Sem dados de contagem de transações, assume que threshold não é atingido
        card = _make_card(base_annuity=480.0, waiver_type="transaction_count")
        result = sim.simulate(card, _make_profile())
        assert result.annuity_effective == 480.0
        assert result.annuity_waived is False


# ─── Valor dos benefícios ───────────────────────────────────────────────────────

class TestBenefitValues:
    def test_points_value_calculation(self, sim):
        # spend_annual = 2000 × 12 = 24000
        # points = 24000 × 2.0 = 48000
        # value = (48000 / 1000) × 16.0 = 768.0
        card = _make_card(points_per_brl=2.0, points_conversion_rate=16.0)
        result = sim.simulate(card, _make_profile(monthly_avg_spend=2000.0))
        assert result.points_value_expected == pytest.approx(768.0, abs=0.01)

    def test_points_scenarios_plus_minus_20_pct(self, sim):
        # expected = 768.0, min = 768 × 0.8 = 614.4, max = 768 × 1.2 = 921.6
        card = _make_card(points_per_brl=2.0, points_conversion_rate=16.0)
        result = sim.simulate(card, _make_profile(monthly_avg_spend=2000.0))
        assert result.points_value_min == pytest.approx(614.4, abs=0.01)
        assert result.points_value_expected == pytest.approx(768.0, abs=0.01)
        assert result.points_value_max == pytest.approx(921.6, abs=0.01)

    def test_cashback_value_calculation(self, sim):
        # spend_annual = 2000 × 12 = 24000
        # cashback = 24000 × 0.01 = 240.0
        card = _make_card(card_type=CardType.CASHBACK, points_per_brl=None, cashback_pct=0.01)
        result = sim.simulate(card, _make_profile(monthly_avg_spend=2000.0))
        assert result.points_value_expected == pytest.approx(240.0, abs=0.01)

    def test_cashback_cap_applied(self, sim):
        # cashback_pct=0.05, cashback_cap=100 (mensal) → cap anual = 1200
        # raw = 24000 × 0.05 = 1200 → exatamente no cap → 1200
        card = _make_card(
            card_type=CardType.CASHBACK, points_per_brl=None,
            cashback_pct=0.05, cashback_cap=100.0,
        )
        result = sim.simulate(card, _make_profile(monthly_avg_spend=2000.0))
        assert result.points_value_expected == pytest.approx(1200.0, abs=0.01)

    def test_cashback_cap_limits_high_spender(self, sim):
        # cashback_pct=0.05, cashback_cap=50/mês → cap anual = 600
        # raw = 24000 × 0.05 = 1200 > 600 → cap = 600
        card = _make_card(
            card_type=CardType.CASHBACK, points_per_brl=None,
            cashback_pct=0.05, cashback_cap=50.0,
        )
        result = sim.simulate(card, _make_profile(monthly_avg_spend=2000.0))
        assert result.points_value_expected == pytest.approx(600.0, abs=0.01)

    def test_zero_points_per_brl_returns_zero_value(self, sim):
        card = _make_card(points_per_brl=None)
        result = sim.simulate(card, _make_profile())
        assert result.points_value_expected == 0.0

    def test_net_gain_equals_value_minus_annuity(self, sim):
        # points_value_expected = 768, annuity = 500
        card = _make_card(
            base_annuity=500.0, waiver_type="none",
            points_per_brl=2.0, points_conversion_rate=16.0,
        )
        result = sim.simulate(card, _make_profile(monthly_avg_spend=2000.0))
        assert result.net_gain_expected == pytest.approx(768.0 - 500.0, abs=0.01)
        assert result.net_gain_min == pytest.approx(614.4 - 500.0, abs=0.01)
        assert result.net_gain_max == pytest.approx(921.6 - 500.0, abs=0.01)


# ─── Liquidez ──────────────────────────────────────────────────────────────────

class TestLiquidity:
    def test_zero_annuity_gives_zero_impact(self, sim):
        card = _make_card(base_annuity=0.0, waiver_type="always_free")
        result = sim.simulate(card, _make_profile(), safe_to_spend=1000.0)
        assert result.liquidity_impact == 0.0
        assert result.liquidity_risk == LiquidityRisk.SAFE

    def test_liquidity_impact_formula(self, sim):
        # annuity = 1200, safe_to_spend = 500
        # impact = (1200/12) / 500 = 100/500 = 0.2 → WARNING
        card = _make_card(base_annuity=1200.0, waiver_type="none")
        result = sim.simulate(card, _make_profile(), safe_to_spend=500.0)
        assert result.liquidity_impact == pytest.approx(0.2, abs=0.001)
        assert result.liquidity_risk == LiquidityRisk.WARNING

    def test_zero_safe_to_spend_with_annuity_is_critical(self, sim):
        card = _make_card(base_annuity=1200.0, waiver_type="none")
        result = sim.simulate(card, _make_profile(), safe_to_spend=0.0)
        assert result.liquidity_impact == 1.0
        assert result.liquidity_risk == LiquidityRisk.CRITICAL

    def test_none_safe_to_spend_with_annuity_is_critical(self, sim):
        card = _make_card(base_annuity=1200.0, waiver_type="none")
        result = sim.simulate(card, _make_profile(), safe_to_spend=None)
        assert result.liquidity_impact == 1.0
        assert result.liquidity_risk == LiquidityRisk.CRITICAL


# ─── Confidence score ───────────────────────────────────────────────────────────

class TestConfidenceScore:
    def test_full_confidence_with_ideal_profile(self, sim):
        # coverage=6, stability=1.0, trust=1.0 → 1.0 × 1.0 × 1.0 = 1.0
        card = _make_card(data_trust_score=1.0)
        profile = _make_profile(data_coverage_months=6, spending_stability=1.0, committed_percentage=0.0)
        result = sim.simulate(card, profile)
        assert result.confidence_score == pytest.approx(1.0, abs=0.01)

    def test_low_coverage_penalized(self, sim):
        # coverage=1 (<2) → weight=1/6, + × 0.5 penalty → very low
        card = _make_card(data_trust_score=1.0)
        profile = _make_profile(data_coverage_months=1, spending_stability=1.0, committed_percentage=0.0)
        result = sim.simulate(card, profile)
        # 1/6 × 1.0 × 1.0 × 0.5 = ~0.0833
        assert result.confidence_score == pytest.approx(1/6 * 0.5, abs=0.01)

    def test_high_committed_percentage_penalized(self, sim):
        # coverage=6, stability=1.0, trust=1.0, committed=0.9 > 0.8 → × 0.7
        card = _make_card(data_trust_score=1.0)
        profile = _make_profile(data_coverage_months=6, spending_stability=1.0, committed_percentage=0.9)
        result = sim.simulate(card, profile)
        assert result.confidence_score == pytest.approx(1.0 * 0.7, abs=0.01)

    def test_trust_score_factored_in(self, sim):
        # coverage=6, stability=1.0, trust=0.7 → 0.7
        card = _make_card(data_trust_score=0.7)
        profile = _make_profile(data_coverage_months=6, spending_stability=1.0, committed_percentage=0.0)
        result = sim.simulate(card, profile)
        assert result.confidence_score == pytest.approx(0.7, abs=0.01)


# ─── Spending anchor e razões ───────────────────────────────────────────────────

class TestSpendingAnchorAndReasons:
    def test_spending_anchor_populated(self, sim):
        card = _make_card()
        profile = _make_profile(
            spend_by_source={"debit": 1200.0, "credit": 800.0},
            international_spend_monthly=150.0,
            travel_spend_monthly=300.0,
        )
        result = sim.simulate(card, profile)
        assert result.spending_anchor["debit_monthly"] == 1200.0
        assert result.spending_anchor["credit_monthly"] == 800.0
        assert result.spending_anchor["total_monthly"] == profile.monthly_avg_spend
        assert result.spending_anchor["international_monthly"] == 150.0
        assert isinstance(result.spending_anchor["main_categories"], list)

    def test_match_reason_for_waiver(self, sim):
        # gasto anual = 3000 × 12 = 36000 >= 30000 → isenção
        card = _make_card(base_annuity=1200.0, waiver_type="spend_threshold", waiver_threshold=30000.0)
        result = sim.simulate(card, _make_profile(monthly_avg_spend=3000.0))
        assert any("isenta" in r for r in result.profile_match_reasons)

    def test_no_waiver_reason_when_not_waived(self, sim):
        card = _make_card(base_annuity=1200.0, waiver_type="spend_threshold", waiver_threshold=999999.0)
        result = sim.simulate(card, _make_profile(monthly_avg_spend=1000.0))
        assert not any("isenta" in r for r in result.profile_match_reasons)

    def test_international_reason_when_relevant(self, sim):
        card = _make_card(benefit_tags=[BenefitTag.INTERNACIONAL])
        profile = _make_profile(international_spend_monthly=400.0)
        result = sim.simulate(card, profile)
        assert any("exterior" in r.lower() or "iof" in r.lower() for r in result.profile_match_reasons)

    def test_explanation_steps_populated(self, sim):
        card = _make_card()
        result = sim.simulate(card, _make_profile())
        assert len(result.explanation_steps) >= 4

    def test_benefit_highlights_max_3(self, sim):
        card = _make_card()
        result = sim.simulate(card, _make_profile())
        assert len(result.benefit_highlights) <= 3

    def test_benefit_tags_copied_from_card(self, sim):
        card = _make_card(benefit_tags=[BenefitTag.LOUNGE, BenefitTag.TRAVEL])
        result = sim.simulate(card, _make_profile())
        assert BenefitTag.LOUNGE in result.benefit_tags
        assert BenefitTag.TRAVEL in result.benefit_tags
