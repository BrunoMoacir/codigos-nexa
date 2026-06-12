# tests/optimizer/test_opportunity_score.py
# Testes unitários para OpportunityScoreCalculator

from __future__ import annotations

import pytest
from app.optimizer.opportunity_score import compute_opportunity_score
from app.optimizer.models import CardSimulationResult, CardFlag, LiquidityRisk, BenefitTag
from app.optimizer.profiler import UserProfile
from app.forecast.etl.income_profiler import IncomeProfile


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _result(
    net_gain_expected: float = 1200.0,
    confidence_score: float = 0.80,
    eligibility_score: float = 0.90,
) -> CardSimulationResult:
    return CardSimulationResult(
        card_id="card-test",
        card_name="Cartão Teste",
        issuer="Banco Teste",
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
        liquidity_risk=LiquidityRisk.SAFE,
        confidence_score=confidence_score,
        eligibility_score=eligibility_score,
    )


def _profile(
    spending_stability: float = 0.80,
    income_confidence: float = 0.85,
    category_trends: dict | None = None,
) -> UserProfile:
    income = IncomeProfile(
        monthly_net_income=5000.0,
        income_pattern="CLT",
        confidence=income_confidence,
    )
    return UserProfile(
        monthly_avg_spend=3000.0,
        spending_stability=spending_stability,
        income_profile=income,
        category_trends=category_trends or {},
    )


# ─── Testes base ──────────────────────────────────────────────────────────────

class TestComputeOpportunityScore:

    def test_score_positivo_com_todos_fatores_altos(self):
        result = _result(net_gain_expected=1200.0, confidence_score=1.0, eligibility_score=1.0)
        profile = _profile(spending_stability=1.0, income_confidence=1.0)
        score, breakdown = compute_opportunity_score(result, profile)
        # Sem trends → recurrence = spending_stability = 1.0
        # score = 1200 × 1.0 × 1.0 × 1.0 × 1.0 = 1200
        assert score == pytest.approx(1200.0, abs=1.0)
        assert breakdown["opportunity_score"] == score

    def test_score_zero_quando_ganho_negativo(self):
        result = _result(net_gain_expected=-100.0)
        profile = _profile()
        score, breakdown = compute_opportunity_score(result, profile)
        assert score == 0.0
        assert breakdown["opportunity_score"] == 0.0

    def test_score_zero_quando_ganho_zero(self):
        result = _result(net_gain_expected=0.0)
        profile = _profile()
        score, breakdown = compute_opportunity_score(result, profile)
        assert score == 0.0

    def test_breakdown_contem_todos_os_campos(self):
        result = _result()
        profile = _profile()
        score, breakdown = compute_opportunity_score(result, profile)
        campos = {"net_gain_expected", "profile_confidence", "pattern_stability",
                  "spending_recurrence", "card_eligibility", "opportunity_score"}
        assert campos <= set(breakdown.keys())

    def test_profile_confidence_combina_sim_e_renda(self):
        # sim_conf=1.0, income_conf=0.0 → profile_confidence = 0.60×1 + 0.40×0 = 0.60
        result = _result(confidence_score=1.0, eligibility_score=1.0)
        income = IncomeProfile(monthly_net_income=5000.0, income_pattern="CLT", confidence=0.0)
        profile = UserProfile(
            monthly_avg_spend=3000.0,
            spending_stability=1.0,
            income_profile=income,
            category_trends={},
        )
        score, breakdown = compute_opportunity_score(result, profile)
        assert breakdown["profile_confidence"] == pytest.approx(0.60, abs=0.01)

    def test_sem_income_profile_usa_fallback_05(self):
        result = _result(confidence_score=1.0, eligibility_score=1.0)
        profile = UserProfile(
            monthly_avg_spend=3000.0,
            spending_stability=1.0,
            income_profile=None,
            category_trends={},
        )
        score, breakdown = compute_opportunity_score(result, profile)
        # profile_confidence = 0.60×1.0 + 0.40×0.5 = 0.80
        assert breakdown["profile_confidence"] == pytest.approx(0.80, abs=0.01)


# ─── Fator: recorrência do gasto ──────────────────────────────────────────────

class TestSpendingRecurrence:

    def test_sem_trends_usa_spending_stability(self):
        result = _result(net_gain_expected=1000.0, confidence_score=1.0, eligibility_score=1.0)
        profile = _profile(spending_stability=0.70, income_confidence=1.0, category_trends={})
        score, breakdown = compute_opportunity_score(result, profile)
        assert breakdown["spending_recurrence"] == pytest.approx(0.70, abs=0.01)

    def test_categorias_estaveis_recebem_credito_total(self):
        trends = {
            "alimentacao": {"direction": "ESTAVEL", "current_monthly": 1000.0},
            "transporte":  {"direction": "ESTAVEL", "current_monthly": 500.0},
        }
        result = _result(net_gain_expected=1000.0, confidence_score=1.0, eligibility_score=1.0)
        profile = _profile(spending_stability=0.5, income_confidence=1.0, category_trends=trends)
        _, breakdown = compute_opportunity_score(result, profile)
        assert breakdown["spending_recurrence"] == pytest.approx(1.0, abs=0.01)

    def test_categorias_subindo_recebem_credito_total(self):
        trends = {
            "alimentacao": {"direction": "SUBINDO", "current_monthly": 800.0},
        }
        result = _result(net_gain_expected=1000.0, confidence_score=1.0, eligibility_score=1.0)
        profile = _profile(category_trends=trends)
        _, breakdown = compute_opportunity_score(result, profile)
        assert breakdown["spending_recurrence"] == pytest.approx(1.0, abs=0.01)

    def test_categorias_caindo_recebem_credito_parcial(self):
        trends = {
            "alimentacao": {"direction": "ESTAVEL",    "current_monthly": 600.0},
            "transporte":  {"direction": "CAINDO",     "current_monthly": 400.0},
        }
        # stable: 600 + 400×0.4 = 760 / 1000 = 0.76
        result = _result(net_gain_expected=1000.0, confidence_score=1.0, eligibility_score=1.0)
        profile = _profile(category_trends=trends)
        _, breakdown = compute_opportunity_score(result, profile)
        assert breakdown["spending_recurrence"] == pytest.approx(0.76, abs=0.01)

    def test_categorias_desaparecendo_nao_contribuem(self):
        trends = {
            "alimentacao":  {"direction": "ESTAVEL",      "current_monthly": 500.0},
            "subscriptions": {"direction": "DESAPARECENDO", "current_monthly": 500.0},
        }
        # stable: 500 / 1000 = 0.50
        result = _result(net_gain_expected=1000.0, confidence_score=1.0, eligibility_score=1.0)
        profile = _profile(category_trends=trends)
        _, breakdown = compute_opportunity_score(result, profile)
        assert breakdown["spending_recurrence"] == pytest.approx(0.50, abs=0.01)

    def test_chaves_especiais_ignoradas(self):
        trends = {
            "_income":     {"direction": "CAINDO",  "current_monthly": 5000.0},
            "_delivery":   {"direction": "SUBINDO", "current_monthly": 200.0},
            "alimentacao": {"direction": "ESTAVEL", "current_monthly": 800.0},
        }
        result = _result(net_gain_expected=1000.0, confidence_score=1.0, eligibility_score=1.0)
        profile = _profile(category_trends=trends)
        _, breakdown = compute_opportunity_score(result, profile)
        # apenas "alimentacao" conta: 800/800 = 1.0 (chaves _ ignoradas)
        assert breakdown["spending_recurrence"] == pytest.approx(1.0, abs=0.01)


# ─── Propriedade multiplicativa ───────────────────────────────────────────────

class TestPropriedadeMultiplicativa:

    def test_fator_zero_zera_score(self):
        result = _result(net_gain_expected=1200.0, confidence_score=0.8, eligibility_score=0.0)
        profile = _profile(spending_stability=0.8)
        score, _ = compute_opportunity_score(result, profile)
        assert score == 0.0

    def test_score_cresce_com_ganho_esperado(self):
        profile = _profile(spending_stability=0.8, income_confidence=0.8)
        score_baixo, _ = compute_opportunity_score(_result(net_gain_expected=500.0), profile)
        score_alto, _  = compute_opportunity_score(_result(net_gain_expected=2000.0), profile)
        assert score_alto > score_baixo

    def test_maior_confianca_eleva_score(self):
        profile = _profile(spending_stability=0.8, income_confidence=0.8)
        score_fraco, _ = compute_opportunity_score(
            _result(confidence_score=0.5, eligibility_score=0.9), profile
        )
        score_forte, _ = compute_opportunity_score(
            _result(confidence_score=0.95, eligibility_score=0.9), profile
        )
        assert score_forte > score_fraco

    def test_maior_elegibilidade_eleva_score(self):
        profile = _profile(spending_stability=0.8, income_confidence=0.8)
        score_baixo, _ = compute_opportunity_score(
            _result(eligibility_score=0.50), profile
        )
        score_alto, _ = compute_opportunity_score(
            _result(eligibility_score=0.95), profile
        )
        assert score_alto > score_baixo

    def test_score_nunca_negativo(self):
        result = _result(net_gain_expected=500.0, confidence_score=0.3, eligibility_score=0.3)
        profile = _profile(spending_stability=0.1)
        score, _ = compute_opportunity_score(result, profile)
        assert score >= 0.0
