# tests/optimizer/test_recommendation_feedback.py
# Testes do sistema de aprendizado com feedback de recomendações (M2.8)

from __future__ import annotations

import json
import uuid
from collections import defaultdict
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
    _extract_insight_signals,
    find_insight_in_report,
    get_feedback_stats,
    get_feedback_weights,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

def _make_insight(
    insight_id: str = "",
    insight_type: InsightType = InsightType.TROCAR_PRIMARIO,
    card_id: str = "nubank_roxinho",
    card_name: str = "Nubank Roxinho",
    confidence: float = 0.80,
    gain_expected: float = 80.0,
    gain_conservative: float = 50.0,
    effort: InsightEffort = InsightEffort.MEDIO,
    tags: list[str] | None = None,
) -> ActionableInsight:
    return ActionableInsight(
        insight_id=insight_id or str(uuid.uuid4()),
        type=insight_type,
        title="Trocar cartão",
        description="Descrição do insight",
        gain_interval=InsightInterval(
            conservative=gain_conservative,
            expected=gain_expected,
            optimistic=gain_expected * 1.2,
        ),
        effort=effort,
        confidence_score=confidence,
        priority_score=round(gain_expected * confidence, 2),
        card_id=card_id,
        card_name=card_name,
        tags=tags or [],
    )


def _insight_as_dict(insight: ActionableInsight) -> dict[str, Any]:
    """Converte ActionableInsight para o formato armazenado no full_report_json."""
    return {
        "insight_id": insight.insight_id,
        "type": insight.type.value,
        "title": insight.title,
        "description": insight.description,
        "gain_interval": {
            "conservative": insight.gain_interval.conservative,
            "expected": insight.gain_interval.expected,
            "optimistic": insight.gain_interval.optimistic,
        },
        "effort": insight.effort.value,
        "confidence_score": insight.confidence_score,
        "priority_score": insight.priority_score,
        "card_id": insight.card_id,
        "card_name": insight.card_name,
        "tags": insight.tags,
    }


# ─── insight_id atribuído pelo InsightGenerator ──────────────────────────────

class TestInsightIdAssignment:
    def test_insights_receive_unique_uuids(self):
        from app.optimizer.insight_generator import InsightGenerator
        from app.optimizer.models import CardSimulationResult, CardFlag, LiquidityRisk, BenefitTag

        def _card(cid: str, gain: float = 500.0) -> CardSimulationResult:
            return CardSimulationResult(
                card_id=cid, card_name=cid, issuer="Bank", flag=CardFlag.VISA,
                annuity_effective=0.0, annuity_waived=True,
                points_value_min=gain * 0.8, points_value_expected=gain, points_value_max=gain * 1.2,
                net_gain_min=gain * 0.8, net_gain_expected=gain, net_gain_max=gain * 1.2,
                liquidity_impact=0.0, liquidity_risk=LiquidityRisk.SAFE,
                confidence_score=0.80, eligibility_score=0.90,
                benefit_tags=[BenefitTag.CASHBACK],
            )

        from tests.optimizer.test_ranking import _make_profile  # type: ignore
        try:
            from tests.optimizer.test_ranking import _make_profile
            profile = _make_profile()
        except Exception:
            from app.optimizer.profiler import UserProfile
            profile = UserProfile(
                monthly_avg_spend=2000.0,
                committed_percentage=0.3,
                spend_by_category={"alimentacao": 500.0},
                spend_by_source={},
                travel_spend_monthly=0.0,
                international_spend_monthly=0.0,
                travel_frequency_score=10.0,
                travel_profile="OCASIONAL",
                foodie_score=30.0,
                foodie_profile="BASICO",
                lifestyle_cluster="DIGITAL_NATIVO",
                secondary_clusters=[],
                cluster_scores={},
                savings_rate=20.0,
                resilience_score=60.0,
                fss=40.0,
                fss_level="SAUDAVEL",
                spending_stability=0.8,
                data_coverage_months=6,
                estimated_monthly_income=5000.0,
                income_profile=None,
                life_stage="NAO_IDENTIFICADO",
                life_stage_confidence=0.0,
                is_family_with_kids=False,
                is_digital_nomad=False,
                is_likely_mei=False,
                investor_type="NONE",
                category_trends={},
                spend_is_estimated=False,
            )

        gen = InsightGenerator()
        results = gen.generate(
            ranked_results=[_card("card-a"), _card("card-b", gain=300.0)],
            profile=profile,
        )

        ids = [i.insight_id for i in results]
        assert all(ids), "Todos os insights devem ter insight_id não-vazio"
        assert len(ids) == len(set(ids)), "Todos os insight_ids devem ser únicos"

    def test_insight_id_is_valid_uuid(self):
        from app.optimizer.insight_generator import InsightGenerator
        from app.optimizer.models import CardSimulationResult, CardFlag, LiquidityRisk, BenefitTag
        from app.optimizer.profiler import UserProfile

        profile = UserProfile(
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
        card = CardSimulationResult(
            card_id="card-x", card_name="Card X", issuer="Bank", flag=CardFlag.VISA,
            annuity_effective=0.0, annuity_waived=True,
            points_value_min=400.0, points_value_expected=500.0, points_value_max=600.0,
            net_gain_min=400.0, net_gain_expected=500.0, net_gain_max=600.0,
            liquidity_impact=0.0, liquidity_risk=LiquidityRisk.SAFE,
            confidence_score=0.80, eligibility_score=0.90,
            benefit_tags=[BenefitTag.CASHBACK],
        )
        gen = InsightGenerator()
        results = gen.generate(ranked_results=[card], profile=profile)
        for i in results:
            parsed = uuid.UUID(i.insight_id)  # levanta ValueError se inválido
            assert str(parsed) == i.insight_id


# ─── _extract_insight_signals ────────────────────────────────────────────────

class TestExtractInsightSignals:
    def test_extracts_all_fields(self):
        insight = {
            "card_id": "inter_black",
            "card_name": "Inter Black",
            "confidence_score": 0.82,
            "gain_interval": {"conservative": 50.0, "expected": 80.0, "optimistic": 110.0},
            "effort": "Médio",
            "tags": ["viagem", "TRAVEL"],
        }
        signals = _extract_insight_signals(insight)
        assert signals["card_id"] == "inter_black"
        assert signals["confidence_score"] == 0.82
        assert signals["gain_expected_monthly"] == 80.0
        assert signals["gain_conservative_monthly"] == 50.0
        assert signals["effort"] == "Médio"
        assert signals["tags"] == ["viagem", "TRAVEL"]

    def test_omits_none_fields(self):
        insight = {"card_id": None, "card_name": None, "confidence_score": 0.75,
                   "gain_interval": {"expected": 60.0, "conservative": 40.0},
                   "effort": "Baixo", "tags": []}
        signals = _extract_insight_signals(insight)
        assert "card_id" not in signals
        assert "card_name" not in signals

    def test_handles_missing_gain_interval(self):
        insight = {"confidence_score": 0.70, "effort": "Alto", "tags": []}
        signals = _extract_insight_signals(insight)
        assert "gain_expected_monthly" not in signals
        assert signals["effort"] == "Alto"


# ─── find_insight_in_report ──────────────────────────────────────────────────

class TestFindInsightInReport:
    def _make_report(self, insights: list[dict]) -> dict:
        return {"report_id": "r-001", "user_id": "u-001", "insights": insights}

    def test_finds_existing_insight(self):
        iid = str(uuid.uuid4())
        report = self._make_report([
            {"insight_id": iid, "type": "TROCAR_PRIMARIO"},
            {"insight_id": str(uuid.uuid4()), "type": "PORTFOLIO_MULTI"},
        ])
        found = find_insight_in_report(report, iid)
        assert found is not None
        assert found["type"] == "TROCAR_PRIMARIO"

    def test_returns_none_for_missing_id(self):
        report = self._make_report([{"insight_id": str(uuid.uuid4()), "type": "TROCAR_PRIMARIO"}])
        assert find_insight_in_report(report, "nonexistent-id") is None

    def test_returns_none_for_empty_insights(self):
        report = self._make_report([])
        assert find_insight_in_report(report, str(uuid.uuid4())) is None


# ─── INSIGHT_DETECTOR map ────────────────────────────────────────────────────

class TestInsightDetectorMap:
    def test_all_insight_types_have_detector(self):
        for insight_type in InsightType:
            assert insight_type.value in INSIGHT_DETECTOR, (
                f"InsightType.{insight_type.value} não tem detector mapeado"
            )

    def test_detector_values_are_strings(self):
        for key, value in INSIGHT_DETECTOR.items():
            assert isinstance(value, str) and value, f"Detector para {key} deve ser string não-vazia"


# ─── get_feedback_stats ───────────────────────────────────────────────────────

class TestGetFeedbackStats:
    def _make_feedback_row(self, detector: str, insight_type: str, outcome: str):
        row = MagicMock()
        row.detector = detector
        row.insight_type = insight_type
        row.outcome = outcome
        return row

    def test_aggregates_acceptance_rate(self):
        rows = [
            self._make_feedback_row("LifestyleClassifier", "TROCAR_PRIMARIO", "ACCEPTED"),
            self._make_feedback_row("LifestyleClassifier", "TROCAR_PRIMARIO", "ACCEPTED"),
            self._make_feedback_row("LifestyleClassifier", "TROCAR_PRIMARIO", "REJECTED"),
            self._make_feedback_row("CardSimulator",       "CANCELAR_CARTAO",  "IGNORED"),
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

            stats = get_feedback_stats()

        assert stats == []


# ─── get_feedback_weights ────────────────────────────────────────────────────

class TestGetFeedbackWeights:
    def _mock_stats(self, stats: list[dict]):
        with patch("app.optimizer.queries.get_feedback_stats", return_value=stats):
            return get_feedback_weights()

    def test_weight_is_05_plus_acceptance_rate(self):
        stats = [{"detector": "LifestyleClassifier", "insight_type": "TROCAR_PRIMARIO",
                  "total": 20, "accepted": 16, "acceptance_rate": 0.8}]
        weights = self._mock_stats(stats)
        assert weights["TROCAR_PRIMARIO"] == pytest.approx(0.5 + 0.8, rel=1e-3)

    def test_below_10_feedbacks_excluded(self):
        stats = [{"detector": "CardSimulator", "insight_type": "CANCELAR_CARTAO",
                  "total": 5, "accepted": 4, "acceptance_rate": 0.8}]
        weights = self._mock_stats(stats)
        assert "CANCELAR_CARTAO" not in weights

    def test_range_05_to_15(self):
        stats = [
            {"detector": "LifestyleClassifier", "insight_type": "TROCAR_PRIMARIO",
             "total": 100, "accepted": 100, "acceptance_rate": 1.0},
            {"detector": "CardSimulator", "insight_type": "CANCELAR_CARTAO",
             "total": 100, "accepted": 0, "acceptance_rate": 0.0},
        ]
        weights = self._mock_stats(stats)
        assert weights["TROCAR_PRIMARIO"] == pytest.approx(1.5, rel=1e-3)
        assert weights["CANCELAR_CARTAO"] == pytest.approx(0.5, rel=1e-3)


# ─── Integração: feedback_weights aplicado ao priority_score ─────────────────

class TestFeedbackWeightsInGenerator:
    def _base_profile(self):
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

    def _base_card(self, gain: float = 500.0):
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

    def test_high_weight_boosts_priority_score(self):
        from app.optimizer.insight_generator import InsightGenerator
        gen = InsightGenerator()
        profile = self._base_profile()
        card = self._base_card()

        results_no_weight = gen.generate(
            ranked_results=[card], profile=profile, feedback_weights=None
        )
        results_with_weight = gen.generate(
            ranked_results=[card], profile=profile,
            feedback_weights={"TROCAR_PRIMARIO": 1.5, "PORTFOLIO_MULTI": 1.5,
                              "ATIVAR_BENEFICIO": 1.5, "CANCELAR_CARTAO": 1.5,
                              "ATINGIR_ISENCAO": 1.5, "MUDAR_CATEGORIA": 1.5,
                              "SOLICITAR_UPGRADE": 1.5},
        )
        if results_no_weight and results_with_weight:
            assert results_with_weight[0].priority_score > results_no_weight[0].priority_score

    def test_low_weight_reduces_priority_score(self):
        from app.optimizer.insight_generator import InsightGenerator
        gen = InsightGenerator()
        profile = self._base_profile()
        card = self._base_card()

        results_no_weight = gen.generate(
            ranked_results=[card], profile=profile, feedback_weights=None
        )
        results_with_weight = gen.generate(
            ranked_results=[card], profile=profile,
            feedback_weights={"TROCAR_PRIMARIO": 0.5, "PORTFOLIO_MULTI": 0.5,
                              "ATIVAR_BENEFICIO": 0.5, "CANCELAR_CARTAO": 0.5,
                              "ATINGIR_ISENCAO": 0.5, "MUDAR_CATEGORIA": 0.5,
                              "SOLICITAR_UPGRADE": 0.5},
        )
        if results_no_weight and results_with_weight:
            assert results_with_weight[0].priority_score < results_no_weight[0].priority_score


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
