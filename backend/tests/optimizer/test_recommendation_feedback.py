# tests/optimizer/test_recommendation_feedback.py
# Testes do sistema de aprendizado com feedback de recomendações (M2.8)

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.optimizer.models import (
    ActionableInsight,
    FeedbackOutcome,
    InsightEffort,
    InsightInterval,
    InsightType,
    RecommendationFeedbackRequest,
)
from app.optimizer.queries import (
    INSIGHT_DETECTOR,
    _USER_MIN_SAMPLES,
    _USER_WEIGHT_MAX,
    _USER_WEIGHT_MIN,
    _extract_insight_signals,
    find_insight_in_report,
    get_feedback_stats,
    get_feedback_weights,
    get_global_feedback_weights,
    get_user_feedback_weights,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_row(
    user_id: str = "u-001",
    insight_type: str = "TROCAR_PRIMARIO",
    detector: str = "LifestyleClassifier",
    outcome: str = "ACCEPTED",
) -> MagicMock:
    row = MagicMock()
    row.user_id = user_id
    row.insight_type = insight_type
    row.detector = detector
    row.outcome = outcome
    return row


def _make_profile():
    from app.optimizer.profiler import UserProfile
    return UserProfile(
        monthly_avg_spend=3000.0, committed_percentage=0.3,
        spend_by_category={"alimentacao": 800.0}, spend_by_source={},
        travel_spend_monthly=0.0, international_spend_monthly=0.0,
        travel_frequency_score=10.0, travel_profile="OCASIONAL",
        foodie_score=30.0, foodie_profile="BASICO",
        lifestyle_cluster="DIGITAL_NATIVO", secondary_clusters=[], cluster_scores={},
        savings_rate=20.0, resilience_score=60.0, fss=40.0, fss_level="SAUDAVEL",
        spending_stability=0.8, data_coverage_months=6,
        estimated_monthly_income=6000.0, income_profile=None,
        life_stage="NAO_IDENTIFICADO", life_stage_confidence=0.0,
        is_family_with_kids=False, is_digital_nomad=False, is_likely_mei=False,
        investor_type="NONE", category_trends={}, spend_is_estimated=False,
    )


def _make_card(gain: float = 500.0):
    from app.optimizer.models import CardSimulationResult, CardFlag, LiquidityRisk, BenefitTag
    return CardSimulationResult(
        card_id="card-a", card_name="Card A", issuer="Bank", flag=CardFlag.VISA,
        annuity_effective=0.0, annuity_waived=True,
        points_value_min=gain * 0.8, points_value_expected=gain, points_value_max=gain * 1.2,
        net_gain_min=gain * 0.8, net_gain_expected=gain, net_gain_max=gain * 1.2,
        liquidity_impact=0.0, liquidity_risk=LiquidityRisk.SAFE,
        confidence_score=0.80, eligibility_score=0.90,
        benefit_tags=[BenefitTag.CASHBACK],
    )


# ─── insight_id gerado pelo InsightGenerator ─────────────────────────────────

class TestInsightIdAssignment:
    def test_all_insights_get_unique_uuids(self):
        from app.optimizer.insight_generator import InsightGenerator
        from app.optimizer.models import CardSimulationResult, CardFlag, LiquidityRisk, BenefitTag

        def card(cid: str, gain: float = 500.0) -> CardSimulationResult:
            return CardSimulationResult(
                card_id=cid, card_name=cid, issuer="Bank", flag=CardFlag.VISA,
                annuity_effective=0.0, annuity_waived=True,
                points_value_min=gain * 0.8, points_value_expected=gain, points_value_max=gain * 1.2,
                net_gain_min=gain * 0.8, net_gain_expected=gain, net_gain_max=gain * 1.2,
                liquidity_impact=0.0, liquidity_risk=LiquidityRisk.SAFE,
                confidence_score=0.80, eligibility_score=0.90,
                benefit_tags=[BenefitTag.CASHBACK],
            )

        gen = InsightGenerator()
        results = gen.generate(
            ranked_results=[card("card-a"), card("card-b", gain=300.0)],
            profile=_make_profile(),
        )
        ids = [i.insight_id for i in results]
        assert all(ids), "Todos os insights devem ter insight_id não-vazio"
        assert len(ids) == len(set(ids)), "insight_ids devem ser únicos"

    def test_insight_id_is_valid_uuid_string(self):
        from app.optimizer.insight_generator import InsightGenerator
        gen = InsightGenerator()
        results = gen.generate(ranked_results=[_make_card()], profile=_make_profile())
        for i in results:
            parsed = uuid.UUID(i.insight_id)
            assert str(parsed) == i.insight_id


# ─── _extract_insight_signals ────────────────────────────────────────────────

class TestExtractInsightSignals:
    def test_extracts_all_fields(self):
        insight = {
            "card_id": "inter_black", "card_name": "Inter Black",
            "confidence_score": 0.82,
            "gain_interval": {"conservative": 50.0, "expected": 80.0, "optimistic": 110.0},
            "effort": "Médio", "tags": ["viagem", "TRAVEL"],
        }
        s = _extract_insight_signals(insight)
        assert s["card_id"] == "inter_black"
        assert s["confidence_score"] == 0.82
        assert s["gain_expected_monthly"] == 80.0
        assert s["gain_conservative_monthly"] == 50.0
        assert s["effort"] == "Médio"
        assert s["tags"] == ["viagem", "TRAVEL"]

    def test_omits_none_fields(self):
        insight = {"card_id": None, "card_name": None, "confidence_score": 0.75,
                   "gain_interval": {"expected": 60.0, "conservative": 40.0},
                   "effort": "Baixo", "tags": []}
        s = _extract_insight_signals(insight)
        assert "card_id" not in s
        assert "card_name" not in s

    def test_handles_missing_gain_interval(self):
        insight = {"confidence_score": 0.70, "effort": "Alto", "tags": []}
        s = _extract_insight_signals(insight)
        assert "gain_expected_monthly" not in s
        assert s["effort"] == "Alto"


# ─── find_insight_in_report ──────────────────────────────────────────────────

class TestFindInsightInReport:
    def _report(self, insights: list[dict]) -> dict:
        return {"report_id": "r-001", "user_id": "u-001", "insights": insights}

    def test_finds_existing_insight(self):
        iid = str(uuid.uuid4())
        found = find_insight_in_report(
            self._report([
                {"insight_id": iid, "type": "TROCAR_PRIMARIO"},
                {"insight_id": str(uuid.uuid4()), "type": "PORTFOLIO_MULTI"},
            ]),
            iid,
        )
        assert found is not None
        assert found["type"] == "TROCAR_PRIMARIO"

    def test_returns_none_for_unknown_id(self):
        report = self._report([{"insight_id": str(uuid.uuid4()), "type": "TROCAR_PRIMARIO"}])
        assert find_insight_in_report(report, "nonexistent") is None

    def test_returns_none_for_empty_insights(self):
        assert find_insight_in_report(self._report([]), str(uuid.uuid4())) is None


# ─── INSIGHT_DETECTOR map ────────────────────────────────────────────────────

class TestInsightDetectorMap:
    def test_all_insight_types_covered(self):
        for insight_type in InsightType:
            assert insight_type.value in INSIGHT_DETECTOR

    def test_values_are_non_empty_strings(self):
        for key, val in INSIGHT_DETECTOR.items():
            assert isinstance(val, str) and val


# ─── get_feedback_stats ───────────────────────────────────────────────────────

class TestGetFeedbackStats:
    def test_aggregates_acceptance_rate(self):
        rows = [
            _make_row(outcome="ACCEPTED"), _make_row(outcome="ACCEPTED"),
            _make_row(outcome="REJECTED"),
            _make_row(insight_type="CANCELAR_CARTAO", detector="CardSimulator", outcome="IGNORED"),
        ]
        with patch("app.optimizer.queries.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db
            mock_db.query.return_value.filter.return_value.all.return_value = rows
            mock_db.query.return_value.all.return_value = rows
            stats = get_feedback_stats()

        trocar = next((s for s in stats if s["insight_type"] == "TROCAR_PRIMARIO"), None)
        assert trocar is not None
        assert trocar["total"] == 3
        assert trocar["accepted"] == 2
        assert trocar["rejected"] == 1
        assert trocar["acceptance_rate"] == pytest.approx(2 / 3, rel=1e-3)

    def test_empty_returns_empty_list(self):
        with patch("app.optimizer.queries.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db
            mock_db.query.return_value.all.return_value = []
            assert get_feedback_stats() == []


# ─── get_global_feedback_weights ─────────────────────────────────────────────

class TestGetGlobalFeedbackWeights:
    def _mock(self, stats):
        with patch("app.optimizer.queries.get_feedback_stats", return_value=stats):
            return get_global_feedback_weights()

    def test_weight_formula(self):
        stats = [{"detector": "LifestyleClassifier", "insight_type": "TROCAR_PRIMARIO",
                  "total": 20, "accepted": 16, "acceptance_rate": 0.8}]
        weights = self._mock(stats)
        assert weights["TROCAR_PRIMARIO"] == pytest.approx(1.3, rel=1e-3)

    def test_below_min_samples_excluded(self):
        stats = [{"detector": "CardSimulator", "insight_type": "CANCELAR_CARTAO",
                  "total": 5, "accepted": 4, "acceptance_rate": 0.8}]
        assert "CANCELAR_CARTAO" not in self._mock(stats)

    def test_full_acceptance_gives_15(self):
        stats = [{"detector": "X", "insight_type": "PORTFOLIO_MULTI",
                  "total": 100, "accepted": 100, "acceptance_rate": 1.0}]
        assert self._mock(stats)["PORTFOLIO_MULTI"] == pytest.approx(1.5, rel=1e-3)

    def test_zero_acceptance_gives_05(self):
        stats = [{"detector": "X", "insight_type": "CANCELAR_CARTAO",
                  "total": 100, "accepted": 0, "acceptance_rate": 0.0}]
        assert self._mock(stats)["CANCELAR_CARTAO"] == pytest.approx(0.5, rel=1e-3)


# ─── get_user_feedback_weights ───────────────────────────────────────────────

class TestGetUserFeedbackWeights:
    def _setup_db(self, rows: list):
        mock_session = MagicMock()
        mock_db = MagicMock()
        mock_session.return_value = mock_db
        mock_db.query.return_value.filter.return_value.all.return_value = rows
        return mock_session

    def test_returns_empty_when_below_min_samples(self):
        rows = [_make_row(user_id="u1", outcome="ACCEPTED")] * (_USER_MIN_SAMPLES - 1)
        with patch("app.optimizer.queries.SessionLocal", self._setup_db(rows)):
            weights = get_user_feedback_weights("u1")
        assert "TROCAR_PRIMARIO" not in weights

    def test_returns_weight_at_min_samples(self):
        rows = [_make_row(user_id="u1", outcome="ACCEPTED")] * _USER_MIN_SAMPLES
        with patch("app.optimizer.queries.SessionLocal", self._setup_db(rows)):
            weights = get_user_feedback_weights("u1")
        assert "TROCAR_PRIMARIO" in weights

    def test_user_weight_clamped_to_max_125(self):
        rows = [_make_row(user_id="u1", outcome="ACCEPTED")] * 20  # 100% acceptance
        with patch("app.optimizer.queries.SessionLocal", self._setup_db(rows)):
            weights = get_user_feedback_weights("u1")
        assert weights["TROCAR_PRIMARIO"] == pytest.approx(_USER_WEIGHT_MAX, rel=1e-3)

    def test_user_weight_clamped_to_min_075(self):
        rows = [_make_row(user_id="u1", outcome="REJECTED")] * 20  # 0% acceptance
        with patch("app.optimizer.queries.SessionLocal", self._setup_db(rows)):
            weights = get_user_feedback_weights("u1")
        assert weights["TROCAR_PRIMARIO"] == pytest.approx(_USER_WEIGHT_MIN, rel=1e-3)

    def test_mixed_outcomes_produce_intermediate_weight(self):
        # 7 accepted, 3 rejected = 70% acceptance → raw=1.2 → clamped=1.2
        rows = (
            [_make_row(user_id="u1", outcome="ACCEPTED")] * 7 +
            [_make_row(user_id="u1", outcome="REJECTED")] * 3
        )
        with patch("app.optimizer.queries.SessionLocal", self._setup_db(rows)):
            weights = get_user_feedback_weights("u1")
        expected = max(_USER_WEIGHT_MIN, min(_USER_WEIGHT_MAX, 0.5 + 0.7))
        assert weights["TROCAR_PRIMARIO"] == pytest.approx(expected, rel=1e-3)

    def test_returns_empty_for_user_with_no_feedback(self):
        with patch("app.optimizer.queries.SessionLocal", self._setup_db([])):
            weights = get_user_feedback_weights("unknown-user")
        assert weights == {}

    def test_each_insight_type_computed_independently(self):
        rows = (
            [_make_row(user_id="u1", insight_type="TROCAR_PRIMARIO",  outcome="ACCEPTED")] * 10 +
            [_make_row(user_id="u1", insight_type="CANCELAR_CARTAO", detector="CardSimulator", outcome="REJECTED")] * 10
        )
        with patch("app.optimizer.queries.SessionLocal", self._setup_db(rows)):
            weights = get_user_feedback_weights("u1")
        assert weights["TROCAR_PRIMARIO"]  == pytest.approx(_USER_WEIGHT_MAX, rel=1e-3)
        assert weights["CANCELAR_CARTAO"] == pytest.approx(_USER_WEIGHT_MIN, rel=1e-3)


# ─── get_feedback_weights (combinado) ────────────────────────────────────────

class TestGetFeedbackWeightsCombined:
    def test_without_user_id_returns_global(self):
        global_w = {"TROCAR_PRIMARIO": 1.3}
        with patch("app.optimizer.queries.get_global_feedback_weights", return_value=global_w):
            weights = get_feedback_weights(user_id=None)
        assert weights == global_w

    def test_user_with_no_data_falls_back_to_global(self):
        global_w = {"TROCAR_PRIMARIO": 1.3}
        with (
            patch("app.optimizer.queries.get_global_feedback_weights", return_value=global_w),
            patch("app.optimizer.queries.get_user_feedback_weights", return_value={}),
        ):
            weights = get_feedback_weights(user_id="u1")
        assert weights == global_w

    def test_multiplication_formula(self):
        # global=1.30 × user=0.75 = 0.975
        with (
            patch("app.optimizer.queries.get_global_feedback_weights",
                  return_value={"TROCAR_PRIMARIO": 1.30}),
            patch("app.optimizer.queries.get_user_feedback_weights",
                  return_value={"TROCAR_PRIMARIO": 0.75}),
        ):
            weights = get_feedback_weights(user_id="u1")
        assert weights["TROCAR_PRIMARIO"] == pytest.approx(1.30 * 0.75, rel=1e-3)

    def test_global_only_type_preserved_at_1x_user_multiplier(self):
        # insight_type presente no global mas não no usuário → usa global × 1.0
        with (
            patch("app.optimizer.queries.get_global_feedback_weights",
                  return_value={"TROCAR_PRIMARIO": 1.3, "PORTFOLIO_MULTI": 1.1}),
            patch("app.optimizer.queries.get_user_feedback_weights",
                  return_value={"TROCAR_PRIMARIO": 0.75}),
        ):
            weights = get_feedback_weights(user_id="u1")
        assert weights["PORTFOLIO_MULTI"] == pytest.approx(1.1 * 1.0, rel=1e-3)

    def test_user_only_type_preserved_at_1x_global_multiplier(self):
        # insight_type no usuário mas sem dados globais → usa 1.0 × user
        with (
            patch("app.optimizer.queries.get_global_feedback_weights",
                  return_value={}),
            patch("app.optimizer.queries.get_user_feedback_weights",
                  return_value={"MUDAR_CATEGORIA": 1.20}),
        ):
            weights = get_feedback_weights(user_id="u1")
        assert weights["MUDAR_CATEGORIA"] == pytest.approx(1.0 * 1.20, rel=1e-3)

    def test_example_from_spec(self):
        # global 80% aceitação → 1.30; usuário rejeita sempre → 0.75; final = 0.975
        with (
            patch("app.optimizer.queries.get_global_feedback_weights",
                  return_value={"TROCAR_PRIMARIO": 1.30}),
            patch("app.optimizer.queries.get_user_feedback_weights",
                  return_value={"TROCAR_PRIMARIO": 0.75}),
        ):
            final = get_feedback_weights(user_id="rejector")["TROCAR_PRIMARIO"]
        assert final == pytest.approx(0.975, rel=1e-3)


# ─── Integração: feedback_weights aplicado ao priority_score ─────────────────

class TestFeedbackWeightsInGenerator:
    def test_high_weight_boosts_priority_score(self):
        from app.optimizer.insight_generator import InsightGenerator
        gen = InsightGenerator()
        profile = _make_profile()
        card = _make_card()

        all_weights = {t.value: 1.5 for t in InsightType}
        no_weight = gen.generate(ranked_results=[card], profile=profile)
        with_weight = gen.generate(ranked_results=[card], profile=profile,
                                   feedback_weights=all_weights)
        if no_weight and with_weight:
            assert with_weight[0].priority_score > no_weight[0].priority_score

    def test_low_weight_reduces_priority_score(self):
        from app.optimizer.insight_generator import InsightGenerator
        gen = InsightGenerator()
        profile = _make_profile()
        card = _make_card()

        all_weights = {t.value: 0.5 for t in InsightType}
        no_weight = gen.generate(ranked_results=[card], profile=profile)
        with_weight = gen.generate(ranked_results=[card], profile=profile,
                                   feedback_weights=all_weights)
        if no_weight and with_weight:
            assert with_weight[0].priority_score < no_weight[0].priority_score

    def test_user_rejection_pattern_deprioritizes_insight(self):
        """Simula usuário que sempre rejeita TROCAR_PRIMARIO: peso final deve reduzir o score."""
        from app.optimizer.insight_generator import InsightGenerator
        gen = InsightGenerator()
        profile = _make_profile()
        card = _make_card()

        neutral = gen.generate(ranked_results=[card], profile=profile)
        # global=1.30 (popular) × user=0.75 (rejeitor) = 0.975 < 1.30
        biased = gen.generate(ranked_results=[card], profile=profile,
                              feedback_weights={"TROCAR_PRIMARIO": 0.975})
        if neutral and biased:
            trocar_neutral = next(
                (i for i in neutral if i.type == InsightType.TROCAR_PRIMARIO), None
            )
            trocar_biased = next(
                (i for i in biased if i.type == InsightType.TROCAR_PRIMARIO), None
            )
            if trocar_neutral and trocar_biased:
                assert trocar_biased.priority_score < trocar_neutral.priority_score


# ─── Pydantic schemas de feedback ────────────────────────────────────────────

class TestFeedbackSchemas:
    def test_feedback_request_requires_insight_id(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            RecommendationFeedbackRequest(outcome=FeedbackOutcome.ACCEPTED)

    def test_feedback_request_valid(self):
        req = RecommendationFeedbackRequest(
            insight_id=str(uuid.uuid4()),
            outcome=FeedbackOutcome.REJECTED,
            reason="Não quero trocar de cartão agora",
        )
        assert req.outcome == FeedbackOutcome.REJECTED
        assert req.reason == "Não quero trocar de cartão agora"

    def test_feedback_outcome_values(self):
        assert FeedbackOutcome.ACCEPTED.value == "ACCEPTED"
        assert FeedbackOutcome.IGNORED.value  == "IGNORED"
        assert FeedbackOutcome.REJECTED.value == "REJECTED"
