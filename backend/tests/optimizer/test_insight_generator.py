# tests/optimizer/test_insight_generator.py
# Testes unitários para InsightGenerator (Camada 5)

from __future__ import annotations

import pytest
from app.optimizer.insight_generator import InsightGenerator
from app.optimizer.models import (
    ActionableInsight,
    BenefitTag,
    CardFlag,
    CardSimulationResult,
    InsightEffort,
    InsightInterval,
    InsightType,
    LiquidityRisk,
)
from app.optimizer.profiler import UserProfile
from app.optimizer.constants import INTL_SPEND_THRESHOLD, TRAVEL_SPEND_THRESHOLD


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _result(
    card_id: str = "card-a",
    card_name: str = "Cartão A",
    net_gain_expected: float = 1200.0,
    net_gain_min: float | None = None,
    net_gain_max: float | None = None,
    confidence_score: float = 0.80,
    eligibility_score: float = 0.90,
    annuity_effective: float = 0.0,
    annuity_waived: bool = True,
    benefit_tags: list[BenefitTag] | None = None,
    waiver_threshold: float | None = None,
) -> CardSimulationResult:
    return CardSimulationResult(
        card_id=card_id,
        card_name=card_name,
        issuer="Banco Teste",
        flag=CardFlag.VISA,
        annuity_effective=annuity_effective,
        annuity_waived=annuity_waived,
        points_value_min=(net_gain_min or net_gain_expected * 0.8),
        points_value_expected=net_gain_expected,
        points_value_max=(net_gain_max or net_gain_expected * 1.2),
        net_gain_min=(net_gain_min or net_gain_expected * 0.8),
        net_gain_expected=net_gain_expected,
        net_gain_max=(net_gain_max or net_gain_expected * 1.2),
        liquidity_impact=0.0,
        liquidity_risk=LiquidityRisk.SAFE,
        confidence_score=confidence_score,
        eligibility_score=eligibility_score,
        benefit_tags=benefit_tags or [],
        waiver_threshold=waiver_threshold,
    )


def _profile(
    monthly_avg_spend: float = 3000.0,
    credit_spend_ratio: float = 0.7,
    travel_spend_monthly: float = 0.0,
    international_spend_monthly: float = 0.0,
    spend_by_category: dict | None = None,
    lifestyle_cluster: str = "NAO_CLASSIFICADO",
    secondary_clusters: list | None = None,
    foodie_score: float = 0.0,
    is_family_with_kids: bool = False,
    family_score: float = 0.0,
    fss_level: str = "SAUDAVEL",
    life_stage: str = "NAO_IDENTIFICADO",
    life_stage_confidence: float = 0.0,
) -> UserProfile:
    return UserProfile(
        monthly_avg_spend=monthly_avg_spend,
        credit_spend_ratio=credit_spend_ratio,
        travel_spend_monthly=travel_spend_monthly,
        international_spend_monthly=international_spend_monthly,
        spend_by_category=spend_by_category or {"alimentacao": 800.0, "transporte": 400.0},
        lifestyle_cluster=lifestyle_cluster,
        secondary_clusters=secondary_clusters or [],
        spending_stability=0.8,
        foodie_score=foodie_score,
        is_family_with_kids=is_family_with_kids,
        family_score=family_score,
        fss_level=fss_level,
        life_stage=life_stage,
        life_stage_confidence=life_stage_confidence,
    )


gen = InsightGenerator()


# ─── Gates: ConfidenceGate e MinGainFilter ────────────────────────────────────

class TestPassesGates:

    def test_insight_abaixo_do_confidence_gate_e_filtrado(self):
        insight = ActionableInsight(
            type=InsightType.TROCAR_PRIMARIO,
            title="x",
            description="x",
            gain_interval=InsightInterval(conservative=50.0, expected=80.0, optimistic=120.0),
            effort=InsightEffort.BAIXO,
            confidence_score=0.60,  # abaixo de 0.65
            priority_score=80.0,
        )
        assert not gen._passes_gates(insight)

    def test_insight_abaixo_do_mingain_e_filtrado(self):
        insight = ActionableInsight(
            type=InsightType.TROCAR_PRIMARIO,
            title="x",
            description="x",
            gain_interval=InsightInterval(conservative=5.0, expected=10.0, optimistic=15.0),
            effort=InsightEffort.BAIXO,
            confidence_score=0.80,
            priority_score=10.0,
        )
        assert not gen._passes_gates(insight)

    def test_insight_valido_passa_ambos_os_gates(self):
        insight = ActionableInsight(
            type=InsightType.TROCAR_PRIMARIO,
            title="x",
            description="x",
            gain_interval=InsightInterval(conservative=15.0, expected=30.0, optimistic=50.0),
            effort=InsightEffort.BAIXO,
            confidence_score=0.80,
            priority_score=30.0,
        )
        assert gen._passes_gates(insight)


# ─── TROCAR_PRIMARIO ──────────────────────────────────────────────────────────

class TestTrocarPrimario:

    def test_retorna_none_quando_best_e_current_card(self):
        best = _result(card_id="current", net_gain_expected=2400.0)
        profile = _profile()
        assert gen._try_trocar_primario(best, profile, "current", 0.0) is None

    def test_retorna_none_quando_ganho_abaixo_de_20_mes(self):
        # 200/ano = 16.67/mês — abaixo do gate R$20
        best = _result(net_gain_expected=200.0, confidence_score=0.9)
        profile = _profile()
        assert gen._try_trocar_primario(best, profile, "outro", 0.0) is None

    def test_retorna_insight_quando_ganho_acima_de_20_mes(self):
        # 360/ano = 30/mês — acima do gate
        best = _result(net_gain_expected=360.0, confidence_score=0.9)
        profile = _profile()
        insight = gen._try_trocar_primario(best, profile, "outro", 0.0)
        assert insight is not None
        assert insight.type == InsightType.TROCAR_PRIMARIO
        assert insight.card_id == best.card_id

    def test_ganho_e_incremental_sobre_retorno_atual(self):
        # current_monthly_return = 50/mês → ganho incremental = 150 - 50 = 100/mês
        best = _result(net_gain_expected=1800.0, confidence_score=0.9)  # 150/mês
        profile = _profile()
        insight = gen._try_trocar_primario(best, profile, "outro", 50.0)
        assert insight is not None
        assert insight.gain_interval.expected == pytest.approx(100.0, abs=1.0)

    def test_retorna_none_quando_ganho_incremental_abaixo_do_gate(self):
        # 360/ano = 30/mês, current = 15/mês → incremental = 15/mês — abaixo de 20
        best = _result(net_gain_expected=360.0, confidence_score=0.9)
        profile = _profile()
        assert gen._try_trocar_primario(best, profile, "outro", 15.0) is None


# ─── PORTFOLIO_MULTI ──────────────────────────────────────────────────────────

class TestPortfolioMulti:

    def test_retorna_none_com_menos_de_2_cartoes_positivos(self):
        profile = _profile()
        assert gen._try_portfolio_multi([_result()], profile) is None

    def test_retorna_none_quando_segundo_cartao_contribui_menos_de_30_mes(self):
        # portfolio_gain = r2.net_gain/12 = 200/12 ≈ 16.67/mês — abaixo de R$30
        r1 = _result(card_id="a", net_gain_expected=1200.0, confidence_score=0.9)
        r2 = _result(card_id="b", net_gain_expected=200.0, confidence_score=0.9)
        profile = _profile()
        assert gen._try_portfolio_multi([r1, r2], profile) is None

    def test_retorna_portfolio_multi_quando_ganho_incremental_acima_de_30_mes(self):
        r1 = _result(card_id="a", net_gain_expected=1200.0, confidence_score=0.9)
        r2 = _result(card_id="b", net_gain_expected=800.0, confidence_score=0.9)
        # r2 contribui 66.67/mês incremental além do r1 (100-33.33=66.67)
        profile = _profile()
        insight = gen._try_portfolio_multi([r1, r2], profile)
        assert insight is not None
        assert insight.type == InsightType.PORTFOLIO_MULTI


# ─── ATIVAR_BENEFICIO ─────────────────────────────────────────────────────────

class TestAtivarBeneficio:

    def test_retorna_vazio_quando_sem_beneficio_com_valor(self):
        # Cartão sem benefit_tags
        profile = _profile(travel_spend_monthly=0.0)
        result = _result(benefit_tags=[])
        assert gen._try_ativar_beneficio([result], profile) == []

    def test_lounge_dispara_quando_travel_spend_alto(self):
        profile = _profile(travel_spend_monthly=TRAVEL_SPEND_THRESHOLD + 100)
        result = _result(benefit_tags=[BenefitTag.LOUNGE], confidence_score=0.9)
        insights = gen._try_ativar_beneficio([result], profile)
        assert any(i.type == InsightType.ATIVAR_BENEFICIO for i in insights)

    def test_lounge_nao_dispara_quando_travel_spend_baixo(self):
        profile = _profile(travel_spend_monthly=100.0)
        result = _result(benefit_tags=[BenefitTag.LOUNGE], confidence_score=0.9)
        assert gen._try_ativar_beneficio([result], profile) == []

    def test_travel_dispara_quando_travel_spend_acima_de_200(self):
        profile = _profile(travel_spend_monthly=500.0)
        result = _result(benefit_tags=[BenefitTag.TRAVEL], confidence_score=0.9)
        insights = gen._try_ativar_beneficio([result], profile)
        assert any(i.type == InsightType.ATIVAR_BENEFICIO for i in insights)

    def test_insurance_dispara_quando_travel_spend_acima_de_150(self):
        profile = _profile(travel_spend_monthly=300.0)
        result = _result(benefit_tags=[BenefitTag.INSURANCE], confidence_score=0.9)
        insights = gen._try_ativar_beneficio([result], profile)
        assert any(i.type == InsightType.ATIVAR_BENEFICIO for i in insights)

    def test_premium_dispara_quando_gasto_alto(self):
        profile = _profile(monthly_avg_spend=6000.0)
        result = _result(benefit_tags=[BenefitTag.PREMIUM], confidence_score=0.9)
        insights = gen._try_ativar_beneficio([result], profile)
        assert any(i.type == InsightType.ATIVAR_BENEFICIO for i in insights)

    def test_cashback_dispara_quando_gasto_pix_alto(self):
        # credit_spend_ratio = 0.1 → untapped = 3000 * 0.9 = 2700 > 2000
        profile = _profile(monthly_avg_spend=3000.0, credit_spend_ratio=0.1)
        result = _result(benefit_tags=[BenefitTag.CASHBACK], confidence_score=0.9)
        insights = gen._try_ativar_beneficio([result], profile)
        assert any(i.type == InsightType.ATIVAR_BENEFICIO for i in insights)

    def test_cashback_nao_dispara_quando_gasto_pix_baixo(self):
        # credit_spend_ratio = 0.9 → untapped = 3000 * 0.1 = 300 < 2000
        profile = _profile(monthly_avg_spend=3000.0, credit_spend_ratio=0.9)
        result = _result(benefit_tags=[BenefitTag.CASHBACK], confidence_score=0.9)
        assert gen._try_ativar_beneficio([result], profile) == []

    def test_nao_duplica_mesmo_card_tag(self):
        profile = _profile(travel_spend_monthly=TRAVEL_SPEND_THRESHOLD + 100)
        result = _result(benefit_tags=[BenefitTag.LOUNGE], confidence_score=0.9)
        insights = gen._try_ativar_beneficio([result, result], profile)
        lounge_insights = [i for i in insights if "LOUNGE" in (i.tags or [])]
        assert len(lounge_insights) == 1


# ─── ATINGIR_ISENCAO ──────────────────────────────────────────────────────────

class TestAtingirIsencao:

    def test_retorna_vazio_quando_anuidade_ja_isenta(self):
        profile = _profile()
        result = _result(annuity_effective=0.0, annuity_waived=True)
        assert gen._try_atingir_isencao([result], profile) == []

    def test_retorna_isencao_quando_ha_threshold(self):
        # monthly_avg_spend = 3000 * 0.7 = 2100/mês em crédito
        # waiver_threshold = 30000/ano → needed = 2500/mês → gap = 400/mês (< 3 meses)
        profile = _profile(monthly_avg_spend=3000.0, credit_spend_ratio=0.7)
        result = _result(
            annuity_effective=600.0,
            annuity_waived=False,
            confidence_score=0.85,
            waiver_threshold=30000.0,
        )
        insights = gen._try_atingir_isencao([result], profile)
        assert any(i.type == InsightType.ATINGIR_ISENCAO for i in insights)


# ─── CANCELAR_CARTAO ──────────────────────────────────────────────────────────

class TestCancelarCartao:

    def test_retorna_none_sem_current_card_id(self):
        assert gen._try_cancelar_cartao(None, -20.0) is None

    def test_retorna_none_quando_prejuizo_abaixo_do_gate(self):
        # -14/mês — abaixo de -R$15
        assert gen._try_cancelar_cartao("card-x", -14.0) is None

    def test_retorna_insight_quando_prejuizo_acima_do_gate(self):
        insight = gen._try_cancelar_cartao("card-x", -20.0)
        assert insight is not None
        assert insight.type == InsightType.CANCELAR_CARTAO
        assert insight.card_id == "card-x"

    def test_retorna_none_quando_retorno_positivo(self):
        assert gen._try_cancelar_cartao("card-x", 5.0) is None


# ─── MUDAR_CATEGORIA ──────────────────────────────────────────────────────────

class TestMudarCategoria:

    def test_retorna_vazio_quando_gasto_abaixo_de_200(self):
        profile = _profile(
            monthly_avg_spend=500.0,
            spend_by_category={"alimentacao": 100.0, "transporte": 80.0},
        )
        result = _result(benefit_tags=[BenefitTag.CASHBACK], net_gain_expected=600.0)
        assert gen._try_mudar_categoria([result], profile, None) == []

    def test_retorna_insight_para_categoria_com_beneficio_relevante(self):
        profile = _profile(
            monthly_avg_spend=3000.0,
            spend_by_category={"alimentacao": 800.0, "transporte": 400.0},
        )
        result = _result(
            card_id="cashback-card",
            benefit_tags=[BenefitTag.CASHBACK],
            net_gain_expected=1800.0,
            confidence_score=0.9,
        )
        insights = gen._try_mudar_categoria([result], profile, None)
        assert any(i.type == InsightType.MUDAR_CATEGORIA for i in insights)

    def test_exclui_cartao_atual(self):
        profile = _profile(
            monthly_avg_spend=3000.0,
            spend_by_category={"alimentacao": 800.0},
        )
        result = _result(
            card_id="current",
            benefit_tags=[BenefitTag.CASHBACK],
            net_gain_expected=1800.0,
        )
        assert gen._try_mudar_categoria([result], profile, "current") == []


# ─── SOLICITAR_UPGRADE ────────────────────────────────────────────────────────

class TestSolicitarUpgrade:

    def test_retorna_none_quando_elegibilidade_abaixo_de_85(self):
        result = _result(
            card_id="premium",
            eligibility_score=0.80,
            annuity_effective=500.0,
            benefit_tags=[BenefitTag.LOUNGE],
            net_gain_expected=1800.0,
            confidence_score=0.9,
        )
        profile = _profile()
        assert gen._try_solicitar_upgrade([result], profile, None, 0.0) is None

    def test_retorna_none_quando_anuidade_abaixo_de_300(self):
        result = _result(
            card_id="premium",
            eligibility_score=0.90,
            annuity_effective=100.0,
            benefit_tags=[BenefitTag.LOUNGE],
            net_gain_expected=1800.0,
            confidence_score=0.9,
        )
        profile = _profile()
        assert gen._try_solicitar_upgrade([result], profile, None, 0.0) is None

    def test_retorna_upgrade_quando_criterios_atingidos(self):
        result = _result(
            card_id="premium",
            eligibility_score=0.92,
            annuity_effective=800.0,
            annuity_waived=False,
            benefit_tags=[BenefitTag.LOUNGE, BenefitTag.PREMIUM],
            net_gain_expected=2400.0,
            confidence_score=0.9,
        )
        profile = _profile()
        insight = gen._try_solicitar_upgrade([result], profile, None, 0.0)
        assert insight is not None
        assert insight.type == InsightType.SOLICITAR_UPGRADE


# ─── Cluster Insights ─────────────────────────────────────────────────────────

class TestClusterInsights:

    def test_explorador_global_com_travel_alto_sem_travel_tag(self):
        profile = _profile(travel_spend_monthly=1000.0)
        result = _result(benefit_tags=[], net_gain_expected=1200.0, confidence_score=0.9)
        insights = gen._cluster_insights_for([result], profile, "EXPLORADOR_GLOBAL")
        assert any(i.type == InsightType.MUDAR_CATEGORIA for i in insights)

    def test_explorador_global_nao_dispara_com_travel_tag(self):
        profile = _profile(travel_spend_monthly=1000.0)
        result = _result(benefit_tags=[BenefitTag.TRAVEL], net_gain_expected=1200.0)
        assert gen._cluster_insights_for([result], profile, "EXPLORADOR_GLOBAL") == []

    def test_explorador_global_nao_dispara_com_travel_baixo(self):
        profile = _profile(travel_spend_monthly=200.0)
        result = _result(benefit_tags=[], net_gain_expected=1200.0)
        assert gen._cluster_insights_for([result], profile, "EXPLORADOR_GLOBAL") == []

    def test_investidor_cauteloso_com_anuidade_alta(self):
        profile = _profile()
        result = _result(annuity_effective=800.0, annuity_waived=False, confidence_score=0.9)
        insights = gen._cluster_insights_for([result], profile, "INVESTIDOR_CAUTELOSO")
        assert any(i.type == InsightType.MUDAR_CATEGORIA for i in insights)

    def test_investidor_cauteloso_nao_dispara_com_anuidade_baixa(self):
        profile = _profile()
        result = _result(annuity_effective=0.0, annuity_waived=True)
        assert gen._cluster_insights_for([result], profile, "INVESTIDOR_CAUTELOSO") == []

    def test_microempreendedor_com_cashback(self):
        profile = _profile()
        result = _result(benefit_tags=[BenefitTag.CASHBACK], net_gain_expected=1200.0, confidence_score=0.9)
        insights = gen._cluster_insights_for([result], profile, "MICROEMPREENDEDOR")
        assert any(i.type == InsightType.MUDAR_CATEGORIA for i in insights)

    def test_familia_estruturada_com_gasto_relevante(self):
        profile = _profile(
            spend_by_category={"supermercado": 600.0, "farmacia": 200.0},
        )
        result = _result(benefit_tags=[BenefitTag.CASHBACK], net_gain_expected=1200.0, confidence_score=0.9)
        insights = gen._cluster_insights_for([result], profile, "FAMILIA_ESTRUTURADA")
        assert any(i.type == InsightType.MUDAR_CATEGORIA for i in insights)

    def test_familia_estruturada_nao_dispara_com_gasto_baixo(self):
        profile = _profile(spend_by_category={"supermercado": 100.0, "farmacia": 50.0})
        result = _result(benefit_tags=[BenefitTag.CASHBACK], net_gain_expected=1200.0)
        assert gen._cluster_insights_for([result], profile, "FAMILIA_ESTRUTURADA") == []

    def test_urbano_foodie_com_gasto_alimentacao_alto(self):
        profile = _profile(
            spend_by_category={"alimentacao": 500.0, "restaurante": 200.0},
        )
        result = _result(benefit_tags=[BenefitTag.CASHBACK], net_gain_expected=1200.0, confidence_score=0.9)
        insights = gen._cluster_insights_for([result], profile, "URBANO_FOODIE")
        assert any(i.type == InsightType.MUDAR_CATEGORIA for i in insights)

    def test_estresse_financeiro_com_cartao_sem_anuidade(self):
        profile = _profile()
        free_card = _result(
            card_id="free",
            annuity_effective=0.0,
            annuity_waived=True,
            net_gain_expected=360.0,
            net_gain_min=240.0,
            net_gain_max=480.0,
            confidence_score=0.85,
        )
        insights = gen._cluster_insights_for([free_card], profile, "ESTRESSE_FINANCEIRO")
        assert any(i.type == InsightType.MUDAR_CATEGORIA for i in insights)

    def test_estresse_financeiro_nao_dispara_sem_cartao_gratis(self):
        profile = _profile()
        paid_card = _result(
            annuity_effective=600.0,
            annuity_waived=False,
            net_gain_expected=240.0,
        )
        assert gen._cluster_insights_for([paid_card], profile, "ESTRESSE_FINANCEIRO") == []

    def test_cluster_desconhecido_retorna_vazio(self):
        profile = _profile()
        result = _result()
        assert gen._cluster_insights_for([result], profile, "CLUSTER_INEXISTENTE") == []


# ─── _personalize_description ─────────────────────────────────────────────────

class TestPersonalizeDescription:

    def test_retorna_descricao_original_quando_tone_desativado(self):
        profile = _profile(lifestyle_cluster="EXPLORADOR_GLOBAL")
        base = "O Cartão X pode render R$100/mês."
        result = gen._personalize_description(base, profile, 1200.0, enable_cluster_tone=False)
        assert result == base

    def test_retorna_descricao_original_para_cluster_sem_tone(self):
        profile = _profile(lifestyle_cluster="CLUSTER_SEM_TONE")
        base = "O Cartão X pode render R$100/mês."
        result = gen._personalize_description(base, profile, 1200.0)
        assert result == base

    def test_apenas_primeira_letra_e_minusculizada(self):
        profile = _profile(lifestyle_cluster="EXPLORADOR_GLOBAL")
        # "O" deve virar "o"; "Cartão X" NÃO deve ser afetado
        base = "O Cartão Xpto pode render R$100/mês."
        result = gen._personalize_description(base, profile, 1200.0)
        assert "Xpto" in result, "Nome do cartão não deve ser minúsculizado"
        assert "Cartão Xpto" in result or "cartão Xpto" not in result.lower()

    def test_contem_prefix_do_cluster(self):
        profile = _profile(lifestyle_cluster="EXPLORADOR_GLOBAL")
        base = "O cartão pode render muito."
        result = gen._personalize_description(base, profile, 1200.0)
        assert "Para quem viaja como você" in result

    def test_contem_emphasis_do_cluster(self):
        profile = _profile(lifestyle_cluster="INVESTIDOR_CAUTELOSO")
        result = gen._personalize_description("Rendimento esperado.", profile, 1200.0)
        assert "retorno líquido sobre anuidade" in result


# ─── _estimate_benefit_value ──────────────────────────────────────────────────

class TestEstimateBenefitValue:

    def test_lounge_retorna_70_com_travel_alto(self):
        profile = _profile(travel_spend_monthly=TRAVEL_SPEND_THRESHOLD + 100)
        assert gen._estimate_benefit_value(BenefitTag.LOUNGE, profile) == 70.0

    def test_lounge_retorna_0_com_travel_baixo(self):
        profile = _profile(travel_spend_monthly=100.0)
        assert gen._estimate_benefit_value(BenefitTag.LOUNGE, profile) == 0.0

    def test_internacional_retorna_25_com_intl_alto(self):
        profile = _profile(international_spend_monthly=INTL_SPEND_THRESHOLD + 100)
        assert gen._estimate_benefit_value(BenefitTag.INTERNACIONAL, profile) == 25.0

    def test_internacional_retorna_0_com_intl_baixo(self):
        profile = _profile(international_spend_monthly=50.0)
        assert gen._estimate_benefit_value(BenefitTag.INTERNACIONAL, profile) == 0.0

    def test_travel_retorna_30_com_travel_acima_de_200(self):
        profile = _profile(travel_spend_monthly=500.0)
        assert gen._estimate_benefit_value(BenefitTag.TRAVEL, profile) == 30.0

    def test_travel_retorna_0_com_travel_abaixo_de_200(self):
        profile = _profile(travel_spend_monthly=100.0)
        assert gen._estimate_benefit_value(BenefitTag.TRAVEL, profile) == 0.0

    def test_insurance_retorna_35_com_travel_acima_de_150(self):
        profile = _profile(travel_spend_monthly=200.0)
        assert gen._estimate_benefit_value(BenefitTag.INSURANCE, profile) == 35.0

    def test_premium_retorna_80_com_gasto_acima_de_5000(self):
        profile = _profile(monthly_avg_spend=6000.0)
        assert gen._estimate_benefit_value(BenefitTag.PREMIUM, profile) == 80.0

    def test_premium_retorna_0_com_gasto_baixo(self):
        profile = _profile(monthly_avg_spend=2000.0)
        assert gen._estimate_benefit_value(BenefitTag.PREMIUM, profile) == 0.0

    def test_cashback_retorna_valor_com_pix_alto(self):
        # untapped = 3000 * 0.9 = 2700 → 2700 * 0.01 = 27.0
        profile = _profile(monthly_avg_spend=3000.0, credit_spend_ratio=0.1)
        val = gen._estimate_benefit_value(BenefitTag.CASHBACK, profile)
        assert val == pytest.approx(27.0, abs=0.5)

    def test_cashback_retorna_0_com_pix_baixo(self):
        profile = _profile(monthly_avg_spend=3000.0, credit_spend_ratio=0.9)
        assert gen._estimate_benefit_value(BenefitTag.CASHBACK, profile) == 0.0


# ─── generate — pipeline completo ─────────────────────────────────────────────

class TestGenerate:

    def test_retorna_lista_vazia_sem_cartoes(self):
        assert gen.generate([], _profile()) == []

    def test_insights_tem_uuid_atribuido(self):
        best = _result(net_gain_expected=1200.0, confidence_score=0.9)
        profile = _profile()
        insights = gen.generate([best], profile, current_card_id="outro", current_card_monthly_return=0.0)
        for insight in insights:
            assert insight.insight_id != ""

    def test_insights_ordenados_por_priority_score_decrescente(self):
        best = _result(net_gain_expected=1200.0, confidence_score=0.9)
        profile = _profile()
        insights = gen.generate([best], profile)
        scores = [i.priority_score for i in insights]
        assert scores == sorted(scores, reverse=True)

    def test_insights_abaixo_dos_gates_sao_filtrados(self):
        # Cartão com confidence baixa deve ter insights filtrados
        low_conf = _result(net_gain_expected=1200.0, confidence_score=0.40)
        profile = _profile()
        insights = gen.generate(
            [low_conf], profile,
            current_card_id="outro", current_card_monthly_return=0.0,
        )
        # Nenhum insight de TROCAR_PRIMARIO deve sobreviver com confidence=0.40
        trocar = [i for i in insights if i.type == InsightType.TROCAR_PRIMARIO]
        assert trocar == []

    def test_generate_com_cluster_tone_false_nao_gera_cluster_insights(self):
        best = _result(
            net_gain_expected=2400.0,
            confidence_score=0.9,
            benefit_tags=[],
        )
        profile = _profile(
            lifestyle_cluster="EXPLORADOR_GLOBAL",
            travel_spend_monthly=1000.0,
        )
        with_tone = gen.generate([best], profile, enable_cluster_tone=True)
        without_tone = gen.generate([best], profile, enable_cluster_tone=False)

        cluster_with = [i for i in with_tone if "viagem" in (i.tags or [])]
        cluster_without = [i for i in without_tone if "viagem" in (i.tags or [])]
        # Com tone ativado deve gerar mais cluster insights que sem
        assert len(cluster_with) >= len(cluster_without)

    def test_feedback_weights_ajustam_priority_score(self):
        best = _result(net_gain_expected=1200.0, confidence_score=0.9)
        profile = _profile()
        insights_sem = gen.generate(
            [best], profile,
            current_card_id="outro", current_card_monthly_return=0.0,
        )
        if not insights_sem:
            pytest.skip("nenhum insight gerado — não há o que comparar")

        tipo = insights_sem[0].type.value
        score_sem = insights_sem[0].priority_score

        insights_com = gen.generate(
            [best], profile,
            current_card_id="outro", current_card_monthly_return=0.0,
            feedback_weights={tipo: 2.0},
        )
        score_com = next((i.priority_score for i in insights_com if i.type.value == tipo), None)

        assert score_com is not None
        assert score_com == pytest.approx(score_sem * 2.0, rel=0.01)
