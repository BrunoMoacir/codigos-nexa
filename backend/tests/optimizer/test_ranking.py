# tests/optimizer/test_ranking.py
# Testes unitários para CardRanking
# Passo 2.3 — Funcionalidade 2: Nexa Optimizer

import pytest
from app.optimizer.ranking import CardRanking, _INTL_BONUS, _LOUNGE_BONUS
from app.optimizer.profiler import UserProfile
from app.optimizer.models import (
    CardSimulationResult, CardFlag, LiquidityRisk, BenefitTag
)


# ─── Helpers ────────────────────────────────────────────────────────────────────

def _make_result(
    card_id: str = "card-a",
    net_gain_expected: float = 500.0,
    liquidity_risk: LiquidityRisk = LiquidityRisk.SAFE,
    confidence_score: float = 0.8,
    eligibility_score: float = 0.9,
    benefit_tags: list[BenefitTag] = None,
) -> CardSimulationResult:
    return CardSimulationResult(
        card_id=card_id,
        card_name=card_id,
        issuer="Bank",
        flag=CardFlag.VISA,
        annuity_effective=0.0,
        annuity_waived=True,
        points_value_min=net_gain_expected * 0.8,
        points_value_expected=net_gain_expected,
        points_value_max=net_gain_expected * 1.2,
        net_gain_min=net_gain_expected * 0.8,
        net_gain_expected=net_gain_expected,
        net_gain_max=net_gain_expected * 1.2,
        liquidity_impact=0.0,
        liquidity_risk=liquidity_risk,
        confidence_score=confidence_score,
        eligibility_score=eligibility_score,
        benefit_tags=benefit_tags or [],
    )


def _make_profile(
    international_spend_monthly: float = 0.0,
    travel_spend_monthly: float = 0.0,
) -> UserProfile:
    return UserProfile(
        monthly_avg_spend=2000.0,
        international_spend_monthly=international_spend_monthly,
        travel_spend_monthly=travel_spend_monthly,
    )


@pytest.fixture
def ranking():
    return CardRanking()


# ─── Testes básicos ─────────────────────────────────────────────────────────────

class TestRankingBasic:
    def test_empty_list_returns_empty(self, ranking):
        assert ranking.rank([], _make_profile()) == []

    def test_single_card_returned(self, ranking):
        r = _make_result()
        assert ranking.rank([r], _make_profile()) == [r]

    def test_higher_net_gain_ranked_first(self, ranking):
        low = _make_result(card_id="low", net_gain_expected=200.0)
        high = _make_result(card_id="high", net_gain_expected=800.0)
        result = ranking.rank([low, high], _make_profile())
        assert result[0].card_id == "high"

    def test_equal_score_both_returned(self, ranking):
        a = _make_result(card_id="a", net_gain_expected=500.0)
        b = _make_result(card_id="b", net_gain_expected=500.0)
        result = ranking.rank([a, b], _make_profile())
        assert len(result) == 2


# ─── Penalidades de liquidez ────────────────────────────────────────────────────

class TestLiquidityPenalties:
    def test_critical_liquidity_penalizes_heavily(self, ranking):
        # critical: score -= net_gain × 0.8 → effective = 500 × 0.2 = 100
        # safe: 600 (no penalty)
        critical = _make_result(card_id="critical", net_gain_expected=500.0, liquidity_risk=LiquidityRisk.CRITICAL)
        safe = _make_result(card_id="safe", net_gain_expected=600.0, liquidity_risk=LiquidityRisk.SAFE)
        result = ranking.rank([critical, safe], _make_profile())
        # safe tem score 600 > critical 100
        assert result[0].card_id == "safe"

    def test_high_liquidity_penalizes(self, ranking):
        # high: 500 × (1 - 0.4) = 300
        high = _make_result(card_id="high-liq", net_gain_expected=500.0, liquidity_risk=LiquidityRisk.HIGH)
        safe = _make_result(card_id="safe", net_gain_expected=400.0, liquidity_risk=LiquidityRisk.SAFE)
        result = ranking.rank([high_liq := high, safe], _make_profile())
        # safe = 400 > high-liq = 300
        assert result[0].card_id == "safe"

    def test_warning_liquidity_small_penalty(self, ranking):
        # warning: 500 × (1 - 0.1) = 450
        # safe: 440 < 450 → warning vence mesmo com penalidade leve
        warn = _make_result(card_id="warn", net_gain_expected=500.0, liquidity_risk=LiquidityRisk.WARNING)
        safe = _make_result(card_id="safe", net_gain_expected=440.0, liquidity_risk=LiquidityRisk.SAFE)
        result = ranking.rank([warn, safe], _make_profile())
        assert result[0].card_id == "warn"

    def test_safe_liquidity_no_penalty(self, ranking):
        a = _make_result(card_id="a", net_gain_expected=500.0, liquidity_risk=LiquidityRisk.SAFE)
        b = _make_result(card_id="b", net_gain_expected=400.0, liquidity_risk=LiquidityRisk.SAFE)
        result = ranking.rank([a, b], _make_profile())
        assert result[0].card_id == "a"


# ─── Penalidade de confiança ────────────────────────────────────────────────────

class TestConfidencePenalty:
    def test_low_confidence_halves_score(self, ranking):
        # low_conf: 500 × 0.5 = 250
        # high_conf: 300
        low_conf = _make_result(card_id="low-conf", net_gain_expected=500.0, confidence_score=0.3)
        high_conf = _make_result(card_id="high-conf", net_gain_expected=300.0, confidence_score=0.8)
        result = ranking.rank([low_conf, high_conf], _make_profile())
        assert result[0].card_id == "high-conf"

    def test_confidence_at_threshold_not_penalized(self, ranking):
        # exactly 0.4 → no penalty
        at_threshold = _make_result(card_id="threshold", net_gain_expected=300.0, confidence_score=0.4)
        lower = _make_result(card_id="lower", net_gain_expected=200.0, confidence_score=0.8)
        result = ranking.rank([at_threshold, lower], _make_profile())
        assert result[0].card_id == "threshold"


# ─── Bônus de benefícios ────────────────────────────────────────────────────────

class TestBenefitBonuses:
    def test_international_bonus_applied(self, ranking):
        # profile com gasto internacional > 500
        # intl card: 300 + 200 bonus = 500 > plain: 400
        intl_card = _make_result(
            card_id="intl", net_gain_expected=300.0,
            benefit_tags=[BenefitTag.INTERNACIONAL]
        )
        plain = _make_result(card_id="plain", net_gain_expected=400.0)
        profile = _make_profile(international_spend_monthly=600.0)
        result = ranking.rank([plain, intl_card], profile)
        assert result[0].card_id == "intl"

    def test_no_international_bonus_below_threshold(self, ranking):
        intl_card = _make_result(
            card_id="intl", net_gain_expected=300.0,
            benefit_tags=[BenefitTag.INTERNACIONAL]
        )
        plain = _make_result(card_id="plain", net_gain_expected=400.0)
        profile = _make_profile(international_spend_monthly=300.0)  # abaixo do threshold
        result = ranking.rank([plain, intl_card], profile)
        assert result[0].card_id == "plain"

    def test_lounge_bonus_applied(self, ranking):
        # profile com travel > 800
        # lounge card: 300 + 300 bonus = 600 > plain: 500
        lounge_card = _make_result(
            card_id="lounge", net_gain_expected=300.0,
            benefit_tags=[BenefitTag.LOUNGE]
        )
        plain = _make_result(card_id="plain", net_gain_expected=500.0)
        profile = _make_profile(travel_spend_monthly=900.0)
        result = ranking.rank([plain, lounge_card], profile)
        assert result[0].card_id == "lounge"


# ─── Penalidade de elegibilidade ────────────────────────────────────────────────

class TestEligibilityPenalty:
    def test_eligibility_below_07_penalized(self, ranking):
        # eligibility 0.65: score × 0.75 → 500 × 0.75 = 375
        # other: 400 (no penalty)
        low_elig = _make_result(card_id="low-elig", net_gain_expected=500.0, eligibility_score=0.65)
        other = _make_result(card_id="other", net_gain_expected=400.0, eligibility_score=0.9)
        result = ranking.rank([low_elig, other], _make_profile())
        assert result[0].card_id == "other"

    def test_eligibility_below_05_penalized_heavily(self, ranking):
        # eligibility 0.45: score × 0.4 → 1000 × 0.4 = 400
        # other: 450 > 400
        very_low = _make_result(card_id="very-low", net_gain_expected=1000.0, eligibility_score=0.45)
        other = _make_result(card_id="other", net_gain_expected=450.0, eligibility_score=0.9)
        result = ranking.rank([very_low, other], _make_profile())
        assert result[0].card_id == "other"

    def test_high_eligibility_no_penalty(self, ranking):
        a = _make_result(card_id="a", net_gain_expected=500.0, eligibility_score=0.95)
        b = _make_result(card_id="b", net_gain_expected=400.0, eligibility_score=0.80)
        result = ranking.rank([a, b], _make_profile())
        assert result[0].card_id == "a"


# ─── Regra de elegibilidade mínima ─────────────────────────────────────────────

class TestMinimumEligibilityRule:
    def test_promotes_next_card_when_best_has_very_low_eligibility(self, ranking):
        # best por score mas eligibility < 0.4 → promover próximo com >= 0.6
        best_score_low_elig = _make_result(
            card_id="best-but-inacessible",
            net_gain_expected=1000.0,
            eligibility_score=0.2,
        )
        acceptable = _make_result(
            card_id="acceptable",
            net_gain_expected=500.0,
            eligibility_score=0.75,
        )
        result = ranking.rank([best_score_low_elig, acceptable], _make_profile())
        assert result[0].card_id == "acceptable"

    def test_no_promotion_if_no_card_with_enough_eligibility(self, ranking):
        low1 = _make_result(card_id="low1", net_gain_expected=1000.0, eligibility_score=0.2)
        low2 = _make_result(card_id="low2", net_gain_expected=500.0, eligibility_score=0.3)
        result = ranking.rank([low1, low2], _make_profile())
        # sem promoção possível — mantém ordem por score
        assert result[0].card_id in ("low1", "low2")

    def test_no_promotion_when_best_eligibility_is_sufficient(self, ranking):
        good = _make_result(card_id="good", net_gain_expected=1000.0, eligibility_score=0.5)
        other = _make_result(card_id="other", net_gain_expected=500.0, eligibility_score=0.9)
        result = ranking.rank([good, other], _make_profile())
        # eligibility 0.5 >= 0.4 → sem promoção forçada
        assert result[0].card_id == "good"
