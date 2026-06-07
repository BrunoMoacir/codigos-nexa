# tests/optimizer/test_trend_usage.py
# Testes de uso efetivo de category_trends no ranking e nos insights.

from __future__ import annotations

import pytest

from app.optimizer.insight_generator import InsightGenerator
from app.optimizer.models import (
    ActionableInsight,
    BenefitTag,
    CardFlag,
    CardSimulationResult,
    InsightType,
    LiquidityRisk,
)
from app.optimizer.profiler import UserProfile
from app.optimizer.ranking import CardRanking


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _result(
    card_id: str = "card-a",
    net_gain_expected: float = 600.0,
    benefit_tags: list[BenefitTag] | None = None,
    annuity_effective: float = 0.0,
    confidence_score: float = 0.85,
    eligibility_score: float = 0.90,
    liquidity_risk: LiquidityRisk = LiquidityRisk.SAFE,
) -> CardSimulationResult:
    return CardSimulationResult(
        card_id=card_id,
        card_name=f"Cartão {card_id}",
        issuer="Banco",
        flag=CardFlag.VISA,
        annuity_effective=annuity_effective,
        annuity_waived=(annuity_effective == 0),
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


def _profile(
    category_trends: dict | None = None,
    spend_by_category: dict | None = None,
    monthly_avg_spend: float = 2000.0,
) -> UserProfile:
    return UserProfile(
        monthly_avg_spend=monthly_avg_spend,
        spend_by_category=spend_by_category or {},
        category_trends=category_trends or {},
    )


def _trend(
    direction: str,
    current: float,
    baseline: float,
    ratio: float | None = None,
) -> dict:
    if ratio is None:
        ratio = float("inf") if baseline == 0 and current > 0 else (current / baseline if baseline > 0 else 1.0)
    return {
        "direction": direction,
        "current_monthly": current,
        "baseline_monthly": baseline,
        "ratio": ratio,
    }


# ─── Testes de CardRanking._trend_bonus ──────────────────────────────────────

class TestTrendBonus:

    def _ranking(self):
        return CardRanking()

    def test_sem_trends_bonus_zero(self):
        profile = _profile(category_trends={})
        card = _result(benefit_tags=[BenefitTag.CASHBACK])
        bonus = self._ranking()._trend_bonus(card, profile)
        assert bonus == 0.0

    def test_categoria_subindo_com_beneficio_aumenta_score(self):
        """Alimentação SUBINDO + cartão com CASHBACK → bonus positivo."""
        profile = _profile(category_trends={
            "alimentacao": _trend("SUBINDO", current=1200.0, baseline=800.0, ratio=1.5),
        })
        card_cashback = _result(benefit_tags=[BenefitTag.CASHBACK])
        card_travel = _result(card_id="travel", benefit_tags=[BenefitTag.TRAVEL])

        bonus_cashback = self._ranking()._trend_bonus(card_cashback, profile)
        bonus_travel = self._ranking()._trend_bonus(card_travel, profile)

        assert bonus_cashback > 0.0
        assert bonus_travel == 0.0   # tag errada → sem bonus

    def test_categoria_reemergindo_gera_bonus(self):
        """Viagem REEMERGINDO (ratio=inf) → trata como +30% e gera bonus em card de viagem."""
        profile = _profile(category_trends={
            "viagem": _trend("REEMERGINDO", current=400.0, baseline=0.0),
        })
        card = _result(benefit_tags=[BenefitTag.TRAVEL])
        bonus = self._ranking()._trend_bonus(card, profile)
        assert bonus > 0.0

    def test_categoria_estavel_nao_da_bonus(self):
        profile = _profile(category_trends={
            "alimentacao": _trend("ESTAVEL", current=800.0, baseline=800.0, ratio=1.0),
        })
        card = _result(benefit_tags=[BenefitTag.CASHBACK])
        assert self._ranking()._trend_bonus(card, profile) == 0.0

    def test_categoria_caindo_nao_da_bonus(self):
        profile = _profile(category_trends={
            "alimentacao": _trend("CAINDO", current=500.0, baseline=900.0, ratio=0.55),
        })
        card = _result(benefit_tags=[BenefitTag.CASHBACK])
        assert self._ranking()._trend_bonus(card, profile) == 0.0

    def test_income_caindo_penaliza_anuidade_alta(self):
        """Renda CAINDO → penalidade em cartão com anuidade > R$400/ano."""
        profile = _profile(category_trends={
            "_income": _trend("CAINDO", current=3500.0, baseline=5000.0, ratio=0.70),
        })
        card_expensive = _result(annuity_effective=600.0, net_gain_expected=800.0)
        card_free = _result(annuity_effective=0.0, net_gain_expected=600.0)

        bonus_expensive = CardRanking()._trend_bonus(card_expensive, profile)
        bonus_free = CardRanking()._trend_bonus(card_free, profile)

        assert bonus_expensive < 0.0         # penalidade aplicada
        assert bonus_free == 0.0             # sem anuidade → sem penalidade

    def test_income_estavel_nao_penaliza(self):
        profile = _profile(category_trends={
            "_income": _trend("ESTAVEL", current=5000.0, baseline=5000.0, ratio=1.0),
        })
        card = _result(annuity_effective=600.0)
        assert CardRanking()._trend_bonus(card, profile) == 0.0

    def test_bonus_cap_por_categoria(self):
        """Bonus por categoria não pode ultrapassar R$300/ano (cap do método)."""
        profile = _profile(category_trends={
            "alimentacao": _trend("SUBINDO", current=50_000.0, baseline=1_000.0, ratio=50.0),
        })
        card = _result(benefit_tags=[BenefitTag.CASHBACK])
        bonus = CardRanking()._trend_bonus(card, profile)
        assert bonus <= 300.0

    def test_trend_bonus_eleva_score_total_no_rank(self):
        """Cartão com CASHBACK sobe no ranking quando alimentação está SUBINDO."""
        trends = {
            "alimentacao": _trend("SUBINDO", current=1200.0, baseline=700.0, ratio=1.71),
        }
        profile = _profile(category_trends=trends, monthly_avg_spend=2000.0)

        card_cashback = _result("cashback", net_gain_expected=500.0, benefit_tags=[BenefitTag.CASHBACK])
        card_travel = _result("travel", net_gain_expected=500.0, benefit_tags=[BenefitTag.TRAVEL])

        ranked = CardRanking().rank([card_travel, card_cashback], profile)
        assert ranked[0].card_id == "cashback"


# ─── Testes de InsightGenerator._try_tendencia_insights ──────────────────────

class TestTendenciaInsights:

    def _gen(self):
        return InsightGenerator()

    def test_sem_trends_retorna_vazio(self):
        profile = _profile(category_trends={})
        result = self._gen()._try_tendencia_insights([_result()], profile)
        assert result == []

    def test_categoria_subindo_gera_insight(self):
        """Farmácia SUBINDO + cartão com CASHBACK → insight MUDAR_CATEGORIA gerado."""
        profile = _profile(category_trends={
            "farmacia": _trend("SUBINDO", current=400.0, baseline=200.0, ratio=2.0),
        })
        card = _result(benefit_tags=[BenefitTag.CASHBACK])
        insights = self._gen()._try_tendencia_insights([card], profile)

        assert len(insights) >= 1
        assert insights[0].type == InsightType.MUDAR_CATEGORIA
        assert "tendencia" in insights[0].tags
        assert "farmacia" in insights[0].tags
        assert "farmacia" in insights[0].title.lower() or "farmácia" in insights[0].title.lower() or "farmácia" in insights[0].description.lower()

    def test_categoria_reemergindo_gera_insight(self):
        """Viagem REEMERGINDO → insight com mensagem específica."""
        profile = _profile(category_trends={
            "viagem": _trend("REEMERGINDO", current=300.0, baseline=0.0),
        })
        card = _result(benefit_tags=[BenefitTag.TRAVEL])
        insights = self._gen()._try_tendencia_insights([card], profile)

        assert len(insights) >= 1
        assert "tendencia" in insights[0].tags
        assert "reapareceu" in insights[0].title.lower() or "voltou" in insights[0].description.lower()

    def test_categoria_sem_beneficio_mapeado_nao_gera(self):
        """Categoria sem mapeamento em _CATEGORY_BENEFIT_MAP não gera insight."""
        profile = _profile(category_trends={
            "streaming": _trend("SUBINDO", current=200.0, baseline=100.0, ratio=2.0),
        })
        card = _result(benefit_tags=[BenefitTag.CASHBACK])
        insights = self._gen()._try_tendencia_insights([card], profile)
        assert not any("streaming" in i.tags for i in insights)

    def test_sem_cartao_com_beneficio_nao_gera(self):
        """Categoria subindo mas nenhum cartão tem o BenefitTag → sem insight."""
        profile = _profile(category_trends={
            "viagem": _trend("SUBINDO", current=500.0, baseline=200.0, ratio=2.5),
        })
        card_sem_travel = _result(benefit_tags=[BenefitTag.CASHBACK])  # CASHBACK, sem TRAVEL
        insights = self._gen()._try_tendencia_insights([card_sem_travel], profile)
        assert not any("viagem" in i.tags for i in insights)

    def test_gasto_muito_baixo_nao_gera(self):
        """Categoria subindo mas gasto atual < R$100/mês → sem insight."""
        profile = _profile(category_trends={
            "farmacia": _trend("SUBINDO", current=30.0, baseline=10.0, ratio=3.0),
        })
        card = _result(benefit_tags=[BenefitTag.CASHBACK])
        insights = self._gen()._try_tendencia_insights([card], profile)
        assert not any("farmacia" in i.tags for i in insights)

    def test_delivery_subindo_gera_insight(self):
        """_delivery SUBINDO → insight específico de delivery com tag 'delivery'."""
        profile = _profile(category_trends={
            "_delivery": _trend("SUBINDO", current=300.0, baseline=100.0, ratio=3.0),
        })
        card = _result(benefit_tags=[BenefitTag.CASHBACK])
        insights = self._gen()._try_tendencia_insights([card], profile)

        assert any("delivery" in i.tags for i in insights)
        delivery_insights = [i for i in insights if "delivery" in i.tags]
        assert delivery_insights[0].type == InsightType.MUDAR_CATEGORIA
        assert "delivery" in delivery_insights[0].description.lower()

    def test_delivery_reemergindo_gera_insight(self):
        profile = _profile(category_trends={
            "_delivery": _trend("REEMERGINDO", current=200.0, baseline=0.0),
        })
        card = _result(benefit_tags=[BenefitTag.CASHBACK])
        insights = self._gen()._try_tendencia_insights([card], profile)
        assert any("delivery" in i.tags for i in insights)

    def test_delivery_sem_cashback_card_nao_gera(self):
        profile = _profile(category_trends={
            "_delivery": _trend("SUBINDO", current=300.0, baseline=100.0, ratio=3.0),
        })
        card_travel = _result(benefit_tags=[BenefitTag.TRAVEL])  # sem CASHBACK
        insights = self._gen()._try_tendencia_insights([card_travel], profile)
        assert not any("delivery" in i.tags for i in insights)

    def test_income_caindo_forte_gera_insight_zero_anuidade(self):
        """Renda cai > 15% + cartão sem anuidade disponível → insight de precaução."""
        profile = _profile(category_trends={
            "_income": _trend("CAINDO", current=3000.0, baseline=5500.0, ratio=0.545),
        })
        card_free = _result("free", annuity_effective=0.0, net_gain_expected=400.0)
        card_expensive = _result("exp", annuity_effective=800.0, net_gain_expected=1000.0)

        insights = self._gen()._try_tendencia_insights([card_expensive, card_free], profile)
        renda_insights = [i for i in insights if "renda" in i.tags]

        assert len(renda_insights) >= 1
        assert renda_insights[0].card_id == "free"
        assert "tendencia" in renda_insights[0].tags
        assert "renda" in renda_insights[0].description.lower()

    def test_income_caindo_sem_cartao_zero_anuidade_nao_gera(self):
        """Renda cai mas todos os cartões têm anuidade → sem insight de renda."""
        profile = _profile(category_trends={
            "_income": _trend("CAINDO", current=3000.0, baseline=5000.0, ratio=0.60),
        })
        card = _result(annuity_effective=500.0)
        insights = self._gen()._try_tendencia_insights([card], profile)
        assert not any("renda" in i.tags for i in insights)

    def test_income_caindo_pouco_nao_gera(self):
        """Renda cai apenas 10% (ratio=0.90) → abaixo do gate de 15% → sem insight."""
        profile = _profile(category_trends={
            "_income": _trend("CAINDO", current=4500.0, baseline=5000.0, ratio=0.90),
        })
        card_free = _result(annuity_effective=0.0)
        card_exp = _result("exp", annuity_effective=600.0)
        insights = self._gen()._try_tendencia_insights([card_exp, card_free], profile)
        assert not any("renda" in i.tags for i in insights)

    def test_estrutura_do_insight(self):
        """Todo insight de tendência tem card_id, description não vazia e priority_score > 0."""
        profile = _profile(category_trends={
            "alimentacao": _trend("SUBINDO", current=800.0, baseline=500.0, ratio=1.6),
        })
        card = _result(benefit_tags=[BenefitTag.CASHBACK])
        insights = self._gen()._try_tendencia_insights([card], profile)

        for i in insights:
            assert i.card_id is not None
            assert len(i.description) > 10
            assert i.priority_score > 0.0
            assert i.gain_interval.expected > 0.0

    def test_insights_passam_pelo_generate(self):
        """Insights de tendência aparecem no output final do generate() quando qualificam."""
        profile = _profile(
            category_trends={
                "alimentacao": _trend("SUBINDO", current=800.0, baseline=400.0, ratio=2.0),
            },
            spend_by_category={"alimentacao": 800.0},
        )
        card = _result(
            confidence_score=0.90,
            eligibility_score=0.90,
            benefit_tags=[BenefitTag.CASHBACK],
            net_gain_expected=800.0,
        )
        all_insights = InsightGenerator().generate(
            ranked_results=[card],
            profile=profile,
            current_card_id=None,
            current_card_monthly_return=0.0,
            enable_cluster_tone=False,
        )
        trend_insights = [i for i in all_insights if "tendencia" in i.tags]
        assert len(trend_insights) >= 1
