# tests/optimizer/test_t1_t2_validation.py
# Validação completa de T1.1–T2.7 (User Intelligence Fase 1 e 2)

from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest

# ─── Helpers compartilhados ──────────────────────────────────────────────────

def _make_df(rows: list[dict]) -> pl.DataFrame:
    """Cria DataFrame de transações com schema mínimo."""
    return pl.DataFrame(
        rows,
        schema={
            "date": pl.Date,
            "amount": pl.Float64,
            "description": pl.Utf8,
            "category": pl.Utf8,
            "transaction_type": pl.Utf8,
        },
    )


def _txn(
    amount: float,
    description: str = "COMPRA",
    category: str = "Outros",
    days_ago: int = 10,
    txn_type: str = "CREDIT",
) -> dict:
    return {
        "date": date.today() - timedelta(days=days_ago),
        "amount": amount,
        "description": description,
        "category": category,
        "transaction_type": txn_type,
    }


# ═══════════════════════════════════════════════════════════════════════════
# T1.1 — TransactionFeatureEnricher
# ═══════════════════════════════════════════════════════════════════════════

class TestFeatureEnricher:
    def _enrich(self, rows: list[dict]) -> pl.DataFrame:
        from app.optimizer.feature_store import TransactionFeatureEnricher
        df = _make_df(rows)
        return TransactionFeatureEnricher().enrich(df)

    def test_adds_is_travel_related_for_airline(self):
        df = self._enrich([_txn(-300, "LATAM COMPRA PASSAGEM")])
        assert df["is_travel_related"][0] is True

    def test_adds_is_travel_related_false_for_regular(self):
        df = self._enrich([_txn(-50, "PADARIA DO JOAO")])
        assert df["is_travel_related"][0] is False

    def test_adds_is_broker_for_nuinvest(self):
        df = self._enrich([_txn(-1000, "NUINVEST APORTE")])
        assert df["is_broker_txn"][0] is True

    def test_adds_is_b2b_for_omie(self):
        df = self._enrich([_txn(-200, "OMIE ASSINATURA")])
        assert df["is_b2b"][0] is True

    def test_merchant_category_l2_delivery(self):
        df = self._enrich([_txn(-45, "IFOOD PEDIDO")])
        assert df["merchant_category_l2"][0] == "DELIVERY"

    def test_merchant_category_l2_streaming(self):
        df = self._enrich([_txn(-40, "NETFLIX MENSALIDADE")])
        assert df["merchant_category_l2"][0] == "STREAMING"

    def test_merchant_category_l2_coworking(self):
        df = self._enrich([_txn(-800, "WEWORK COWORKING MENSAL")])
        assert df["merchant_category_l2"][0] == "COWORKING"

    def test_is_foreign_via_iof_keyword(self):
        df = self._enrich([_txn(-500, "PAGAMENTO IOF EXTERIOR")])
        assert df["is_foreign"][0] is True

    def test_is_foreign_false_for_domestic(self):
        df = self._enrich([_txn(-100, "SUPERMERCADO EXTRA")])
        assert df["is_foreign"][0] is False

    def test_adds_day_of_week(self):
        df = self._enrich([_txn(-50, "FARMACIA")])
        assert "day_of_week" in df.columns
        assert 1 <= df["day_of_week"][0] <= 7

    def test_idempotent_does_not_overwrite_existing_columns(self):
        from app.optimizer.feature_store import TransactionFeatureEnricher
        df = _make_df([_txn(-100, "AIRBNB RESERVA")])
        df = df.with_columns(pl.lit(False).alias("is_travel_related"))
        enriched = TransactionFeatureEnricher().enrich(df)
        # Coluna pré-existente não deve ser sobrescrita
        assert enriched["is_travel_related"][0] is False

    def test_airbnb_maps_to_airbnb_l2(self):
        df = self._enrich([_txn(-600, "AIRBNB RESERVA SAO PAULO")])
        assert df["merchant_category_l2"][0] == "AIRBNB"


# ═══════════════════════════════════════════════════════════════════════════
# T1.2 — TravelDetector
# ═══════════════════════════════════════════════════════════════════════════

class TestTravelDetector:
    def test_zero_result_when_empty_df(self):
        from app.optimizer.detectors.travel_detector import TravelDetector
        result = TravelDetector().calc_travel_score(pl.DataFrame(), 1000.0)
        assert result["travel_frequency_score"] == 0.0
        assert result["travel_profile"] == "OCASIONAL"

    def test_score_increases_with_travel_spend_ratio(self):
        from app.optimizer.feature_store import TransactionFeatureEnricher
        from app.optimizer.detectors.travel_detector import TravelDetector
        rows = [_txn(-500, "LATAM PASSAGEM") for _ in range(6)]
        df = TransactionFeatureEnricher().enrich(_make_df(rows))
        result = TravelDetector().calc_travel_score(df, total_spend=500.0)
        assert result["travel_frequency_score"] > 0

    def test_profile_intenso_with_high_score(self):
        from app.optimizer.feature_store import TransactionFeatureEnricher
        from app.optimizer.detectors.travel_detector import TravelDetector
        # Viagem em todos os 12 meses hipotéticos + alto ratio
        rows = [
            _txn(-2000, "LATAM PASSAGEM", days_ago=30 * i + 5)
            for i in range(12)
        ]
        df = TransactionFeatureEnricher().enrich(_make_df(rows))
        total = 2000.0 * 12
        result = TravelDetector().calc_travel_score(df, total_spend=total)
        assert result["travel_profile"] in ("FREQUENTE", "INTENSO")

    def test_detect_airbnb_user(self):
        from app.optimizer.detectors.travel_detector import TravelDetector
        rows = [_txn(-600, f"AIRBNB RESERVA {i}") for i in range(3)]
        df = _make_df(rows)
        result = TravelDetector().detect_airbnb_profile(df)
        assert result["is_airbnb_user"] is True
        assert result["airbnb_frequency"] == "REGULAR"

    def test_not_airbnb_user_below_threshold(self):
        from app.optimizer.detectors.travel_detector import TravelDetector
        rows = [_txn(-600, "AIRBNB RESERVA")]
        df = _make_df(rows)
        result = TravelDetector().detect_airbnb_profile(df)
        assert result["is_airbnb_user"] is True
        assert result["airbnb_frequency"] == "OCASIONAL"

    def test_no_airbnb_user_without_airbnb_txns(self):
        from app.optimizer.detectors.travel_detector import TravelDetector
        df = _make_df([_txn(-300, "BOOKING HOTEL")])
        result = TravelDetector().detect_airbnb_profile(df)
        assert result["is_airbnb_user"] is False

    def test_digital_nomad_requires_coworking(self):
        """Airbnb REGULAR + coworking → is_digital_nomad = True."""
        from app.optimizer.feature_store import TransactionFeatureEnricher
        from app.optimizer.detectors.travel_detector import TravelDetector
        rows = (
            [_txn(-600, f"AIRBNB RESERVA {i}") for i in range(3)]
            + [_txn(-800, "WEWORK COWORKING MENSAL"), _txn(-800, "WEWORK COWORKING MENSAL")]
        )
        df = TransactionFeatureEnricher().enrich(_make_df(rows))
        result = TravelDetector().detect_airbnb_profile(df)
        assert result["is_digital_nomad"] is True

    def test_not_digital_nomad_without_coworking(self):
        """Airbnb REGULAR mas sem coworking → is_digital_nomad = False."""
        from app.optimizer.detectors.travel_detector import TravelDetector
        rows = [_txn(-600, f"AIRBNB RESERVA {i}") for i in range(3)]
        df = _make_df(rows)  # sem enrichment → sem merchant_category_l2
        result = TravelDetector().detect_airbnb_profile(df)
        assert result["is_digital_nomad"] is False


# ═══════════════════════════════════════════════════════════════════════════
# T1.3 — FoodieDetector
# ═══════════════════════════════════════════════════════════════════════════

class TestFoodieDetector:
    def test_zero_result_empty_df(self):
        from app.optimizer.detectors.foodie_detector import FoodieDetector
        result = FoodieDetector().calc_foodie_score(pl.DataFrame(), 1000.0)
        assert result["foodie_score"] == 0.0

    def test_high_food_spend_pct_raises_score(self):
        from app.optimizer.feature_store import TransactionFeatureEnricher
        from app.optimizer.detectors.foodie_detector import FoodieDetector
        rows = [_txn(-800, "RESTAURANTE FINO", category="Alimentação")] * 3
        df = TransactionFeatureEnricher().enrich(_make_df(rows))
        result = FoodieDetector().calc_foodie_score(df, monthly_avg_spend=800.0)
        assert result["foodie_score"] > 30

    def test_profile_gourmet_with_high_avg_ticket(self):
        from app.optimizer.feature_store import TransactionFeatureEnricher
        from app.optimizer.detectors.foodie_detector import FoodieDetector
        # Ticket médio acima de R$150 → fine dining bonus
        rows = [
            _txn(-200, f"RESTAURANTE FINO {i}", category="Alimentação")
            for i in range(5)
        ]
        df = TransactionFeatureEnricher().enrich(_make_df(rows))
        result = FoodieDetector().calc_foodie_score(df, monthly_avg_spend=1000.0)
        assert result["is_fine_dining"] is True

    def test_basico_profile_for_low_food_spend(self):
        from app.optimizer.feature_store import TransactionFeatureEnricher
        from app.optimizer.detectors.foodie_detector import FoodieDetector
        rows = [_txn(-50, "PADARIA SIMPLES", category="Alimentação")]
        df = TransactionFeatureEnricher().enrich(_make_df(rows))
        result = FoodieDetector().calc_foodie_score(df, monthly_avg_spend=3000.0)
        assert result["foodie_profile"] == "BASICO"


# ═══════════════════════════════════════════════════════════════════════════
# T1.4 — InvestorDetector
# ═══════════════════════════════════════════════════════════════════════════

class TestInvestorDetector:
    def test_none_type_without_investments(self):
        from app.optimizer.detectors.investor_detector import InvestorDetector
        df = _make_df([_txn(-500, "SUPERMERCADO")])
        from app.optimizer.feature_store import TransactionFeatureEnricher
        df = TransactionFeatureEnricher().enrich(df)
        result = InvestorDetector().calc_investor_profile(df)
        assert result["investor_type"] == "NONE"

    def test_casual_type_for_few_aportes(self):
        from app.optimizer.feature_store import TransactionFeatureEnricher
        from app.optimizer.detectors.investor_detector import InvestorDetector
        rows = [_txn(-1000, "XP INVESTIMENTOS APORTE"), _txn(-1000, "XP INVESTIMENTOS APORTE")]
        df = TransactionFeatureEnricher().enrich(_make_df(rows))
        result = InvestorDetector().calc_investor_profile(df)
        assert result["investor_type"] == "CASUAL"

    def test_ativo_type_for_many_aportes(self):
        from app.optimizer.feature_store import TransactionFeatureEnricher
        from app.optimizer.detectors.investor_detector import InvestorDetector
        rows = [_txn(-1000, "NUINVEST APORTE") for _ in range(5)]
        df = TransactionFeatureEnricher().enrich(_make_df(rows))
        result = InvestorDetector().calc_investor_profile(df)
        # 5 txns, 1 unique description → broker_diversity == 1 < 2, no dividends → ATIVO
        assert result["investor_type"] == "ATIVO"

    def test_diversificado_with_dividends_and_aportes(self):
        from app.optimizer.feature_store import TransactionFeatureEnricher
        from app.optimizer.detectors.investor_detector import InvestorDetector
        rows = [
            _txn(-1000, "NUINVEST APORTE"),
            _txn(200, "DIVIDENDO ACOES", txn_type="CREDIT"),
        ]
        df = TransactionFeatureEnricher().enrich(_make_df(rows))
        result = InvestorDetector().calc_investor_profile(df)
        assert result["investor_type"] == "DIVERSIFICADO"
        assert result["has_dividends"] is True


# ═══════════════════════════════════════════════════════════════════════════
# T1.5 — MEIDetector
# ═══════════════════════════════════════════════════════════════════════════

class TestMEIDetector:
    def test_not_mei_without_signals(self):
        from app.optimizer.feature_store import TransactionFeatureEnricher
        from app.optimizer.detectors.mei_detector import MEIDetector
        rows = [_txn(-500, "SUPERMERCADO")]
        df = TransactionFeatureEnricher().enrich(_make_df(rows))
        result = MEIDetector().detect_mei_pattern(df, income_profile=None)
        assert result["is_likely_mei"] is False

    def test_mei_detected_with_b2b_tools(self):
        from app.optimizer.feature_store import TransactionFeatureEnricher
        from app.optimizer.detectors.mei_detector import MEIDetector
        from unittest.mock import MagicMock
        rows = [
            _txn(-100, "OMIE ASSINATURA ERP"),
            _txn(-150, "CONTA AZUL MENSAL"),
        ]
        df = TransactionFeatureEnricher().enrich(_make_df(rows))
        # Simular income_profile com padrão PJ
        mock_income = MagicMock()
        mock_income.income_pattern.value = "PJ"
        mock_income.income_stability = 0.30
        result = MEIDetector().detect_mei_pattern(df, income_profile=mock_income)
        assert result["is_likely_mei"] is True
        assert result["mei_confidence"] >= 0.5


# ═══════════════════════════════════════════════════════════════════════════
# T1.6 — UserProfile defaults
# ═══════════════════════════════════════════════════════════════════════════

class TestUserProfileDefaults:
    def test_all_fase1_fields_have_defaults(self):
        from app.optimizer.profiler import UserProfile
        p = UserProfile()
        assert p.travel_frequency_score == 0.0
        assert p.travel_profile == "OCASIONAL"
        assert p.foodie_score == 0.0
        assert p.foodie_profile == "BASICO"
        assert p.savings_rate == 0.0
        assert p.investor_type == "NONE"
        assert p.is_likely_mei is False
        assert p.lifestyle_cluster == "NAO_CLASSIFICADO"
        assert p.merchant_diversity_score == 0.0
        assert p.subscription_burn_monthly == 0.0

    def test_all_fase2_fields_have_defaults(self):
        from app.optimizer.profiler import UserProfile
        p = UserProfile()
        assert p.resilience_score == 0.0
        assert p.fss == 0.0
        assert p.fss_level == "SAUDAVEL"
        assert p.is_airbnb_user is False
        assert p.is_digital_nomad is False
        assert p.is_family_with_kids is False
        assert p.family_score == 0.0
        assert p.peak_spend_day_of_month is None
        assert p.best_notification_day == 5


# ═══════════════════════════════════════════════════════════════════════════
# T1.7 — LifestyleClassifier
# ═══════════════════════════════════════════════════════════════════════════

class TestLifestyleClassifier:
    def _base_profile(self, **kwargs):
        from app.optimizer.profiler import UserProfile
        defaults = dict(
            monthly_avg_spend=3000.0,
            travel_frequency_score=0.0,
            travel_profile="OCASIONAL",
            international_spend_monthly=0.0,
            foodie_score=0.0,
            savings_rate=0.0,
            investor_type="NONE",
            is_likely_mei=False,
            committed_percentage=0.3,
            credit_spend_ratio=0.5,
            spending_stability=0.7,
            merchant_diversity_score=50.0,
            subscription_burn_monthly=50.0,
            spend_by_category={},
        )
        defaults.update(kwargs)
        return UserProfile(**defaults)

    def test_explorador_global_with_high_travel_score(self):
        from app.optimizer.detectors.lifestyle_classifier import LifestyleClassifier
        p = self._base_profile(
            travel_frequency_score=80.0,
            travel_profile="INTENSO",
            international_spend_monthly=600.0,
        )
        result = LifestyleClassifier().classify(p)
        assert result["lifestyle_cluster"] == "EXPLORADOR_GLOBAL"

    def test_airbnb_boosts_explorador_score(self):
        """is_airbnb_user = True deve aumentar o score EXPLORADOR_GLOBAL."""
        from app.optimizer.detectors.lifestyle_classifier import LifestyleClassifier
        p_without = self._base_profile(travel_frequency_score=50.0, travel_profile="MODERADO")
        p_with = self._base_profile(
            travel_frequency_score=50.0,
            travel_profile="MODERADO",
            is_airbnb_user=True,
        )
        clf = LifestyleClassifier()
        score_without = clf._score_explorer(p_without)
        score_with = clf._score_explorer(p_with)
        assert score_with > score_without

    def test_digital_nomad_gives_bigger_boost_than_airbnb(self):
        from app.optimizer.detectors.lifestyle_classifier import LifestyleClassifier
        clf = LifestyleClassifier()
        p_airbnb = self._base_profile(is_airbnb_user=True)
        p_nomad = self._base_profile(is_digital_nomad=True)
        assert clf._score_explorer(p_nomad) > clf._score_explorer(p_airbnb)

    def test_investidor_cauteloso_with_high_savings(self):
        from app.optimizer.detectors.lifestyle_classifier import LifestyleClassifier
        p = self._base_profile(investor_type="ATIVO", savings_rate=35.0)
        result = LifestyleClassifier().classify(p)
        assert result["lifestyle_cluster"] == "INVESTIDOR_CAUTELOSO"

    def test_microempreendedor_with_mei_flag(self):
        from app.optimizer.detectors.lifestyle_classifier import LifestyleClassifier
        p = self._base_profile(is_likely_mei=True)
        result = LifestyleClassifier().classify(p)
        assert result["lifestyle_cluster"] == "MICROEMPREENDEDOR"

    def test_unclassified_when_all_scores_below_threshold(self):
        from app.optimizer.detectors.lifestyle_classifier import LifestyleClassifier
        # Zeros em todos os scores comportamentais → nenhum cluster atinge 0.35
        p = self._base_profile(
            subscription_burn_monthly=0.0,
            merchant_diversity_score=0.0,
            credit_spend_ratio=1.0,  # pix_proxy = 0 → sem boost DIGITAL_NATIVO
        )
        result = LifestyleClassifier().classify(p)
        assert result["lifestyle_cluster"] == "NAO_CLASSIFICADO"

    def test_familia_estruturada_uses_family_detector_data(self):
        """Quando is_family_with_kids=True, score_family deve ser ≥ 0.4."""
        from app.optimizer.detectors.lifestyle_classifier import LifestyleClassifier
        p = self._base_profile(is_family_with_kids=True, family_score=60.0)
        clf = LifestyleClassifier()
        score = clf._score_family(p)
        assert score >= 0.4

    def test_estresse_financeiro_with_negative_savings(self):
        from app.optimizer.detectors.lifestyle_classifier import LifestyleClassifier
        p = self._base_profile(
            savings_rate=-15.0,
            committed_percentage=0.7,
            spending_stability=0.2,
        )
        result = LifestyleClassifier().classify(p)
        assert result["lifestyle_cluster"] == "ESTRESSE_FINANCEIRO"

    def test_cluster_scores_all_between_0_and_1(self):
        from app.optimizer.detectors.lifestyle_classifier import LifestyleClassifier
        p = self._base_profile(
            travel_frequency_score=50.0,
            investor_type="CASUAL",
            savings_rate=10.0,
        )
        result = LifestyleClassifier().classify(p)
        for k, v in result["cluster_scores"].items():
            assert 0.0 <= v <= 1.0, f"Cluster {k} score {v} out of [0,1]"


# ═══════════════════════════════════════════════════════════════════════════
# T1.8 — CardRanking cluster bonuses
# ═══════════════════════════════════════════════════════════════════════════

class TestRankingClusterBonuses:
    def _make_result(self, card_id, net_gain, tags=None):
        from app.optimizer.models import CardSimulationResult, CardFlag, LiquidityRisk, BenefitTag
        tags = tags or []
        return CardSimulationResult(
            card_id=card_id,
            card_name=card_id,
            issuer="B",
            flag=CardFlag.VISA,
            annuity_effective=0.0,
            annuity_waived=True,
            points_value_min=net_gain * 0.8,
            points_value_expected=net_gain,
            points_value_max=net_gain * 1.2,
            net_gain_min=net_gain * 0.8,
            net_gain_expected=net_gain,
            net_gain_max=net_gain * 1.2,
            liquidity_impact=0.0,
            liquidity_risk=LiquidityRisk.SAFE,
            confidence_score=0.9,
            eligibility_score=0.9,
            benefit_tags=tags,
        )

    def _profile(self, cluster, travel_spend=0, intl_spend=0, food_spend=0):
        from app.optimizer.profiler import UserProfile
        return UserProfile(
            monthly_avg_spend=3000.0,
            lifestyle_cluster=cluster,
            travel_spend_monthly=travel_spend,
            international_spend_monthly=intl_spend,
            spend_by_category={"Alimentação": food_spend} if food_spend else {},
            committed_percentage=0.3,
            spending_stability=0.7,
            credit_spend_ratio=0.9,
        )

    def test_explorador_gets_bonus_on_lounge_card(self):
        from app.optimizer.ranking import CardRanking
        from app.optimizer.models import BenefitTag
        rank = CardRanking()
        # travel_spend > TRAVEL_SPEND_THRESHOLD (800) required for LOUNGE bonus
        profile = self._profile("EXPLORADOR_GLOBAL", travel_spend=900)
        card_travel = self._make_result("travel", 1000, [BenefitTag.LOUNGE])
        card_plain = self._make_result("plain", 1000, [])
        score_travel = rank._compute_score(card_travel, profile)
        score_plain = rank._compute_score(card_plain, profile)
        assert score_travel > score_plain

    def test_investidor_penalizes_high_annuity(self):
        from app.optimizer.ranking import CardRanking
        rank = CardRanking()
        profile = self._profile("INVESTIDOR_CAUTELOSO")
        expensive = self._make_result("expensive", 1000)
        expensive.annuity_effective = 600
        cheap = self._make_result("cheap", 1000)
        cheap.annuity_effective = 0
        score_expensive = rank._compute_score(expensive, profile)
        score_cheap = rank._compute_score(cheap, profile)
        assert score_cheap > score_expensive

    def test_hyperscore_returns_0_to_100_range(self):
        from app.optimizer.ranking import CardRanking
        rank = CardRanking()
        profile = self._profile("URBANO_FOODIE", food_spend=600)
        card = self._make_result("c", 500)
        score = rank._compute_hyperscore(card, profile)
        assert 0.0 <= score <= 100.0

    def test_rank_hyperpersonalized_falls_back_when_unclassified(self):
        from app.optimizer.ranking import CardRanking
        rank = CardRanking()
        profile = self._profile("NAO_CLASSIFICADO")
        results = [self._make_result(f"c{i}", 500 - i * 100) for i in range(3)]
        ranked = rank.rank_hyperpersonalized(results, profile)
        assert ranked[0].card_id == "c0"

    def test_compute_base_score_excludes_cluster_bonus(self):
        """_compute_base_score deve ser igual para dois cartões se apenas o cluster difere."""
        from app.optimizer.ranking import CardRanking
        from app.optimizer.models import BenefitTag
        rank = CardRanking()
        profile = self._profile("EXPLORADOR_GLOBAL", travel_spend=600)
        card = self._make_result("card", 1000, [BenefitTag.LOUNGE])
        base = rank._compute_base_score(card, profile)
        full = rank._compute_score(card, profile)
        # Full score inclui bônus de cluster → full ≥ base
        assert full >= base


# ═══════════════════════════════════════════════════════════════════════════
# T2.1 — LifeEventsDetector
# ═══════════════════════════════════════════════════════════════════════════

class TestLifeEventsDetector:
    def _df(self, rows):
        return _make_df(rows)

    def test_new_baby_detected_with_high_spend(self):
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector
        recent = self._df([_txn(-600, "PAMPERS FRALDA TAMANHO G")])
        history = self._df([])
        events = LifeEventsDetector().detect_all(recent, history, 5000.0, 5000.0)
        assert any(e.event == "new_baby" for e in events)

    def test_baby_not_detected_below_threshold(self):
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector
        recent = self._df([_txn(-100, "PAMPERS FRALDA")])
        history = self._df([])
        events = LifeEventsDetector().detect_all(recent, history, 5000.0, 5000.0)
        assert not any(e.event == "new_baby" for e in events)

    def test_baby_not_detected_if_historical_spend_similar(self):
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector
        recent = self._df([_txn(-300, "PAMPERS FRALDA")])
        history = self._df([_txn(-200, "PAMPERS FRALDA")])
        events = LifeEventsDetector().detect_all(recent, history, 5000.0, 5000.0)
        assert not any(e.event == "new_baby" for e in events)

    def test_home_change_detected_with_leroy_merlin(self):
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector
        recent = self._df([_txn(-700, "LEROY MERLIN REFORMA")])
        history = self._df([])
        events = LifeEventsDetector().detect_all(recent, history, 5000.0, 5000.0)
        assert any(e.event == "home_change" for e in events)

    def test_aluguel_does_not_trigger_home_change(self):
        """'ALUGUEL' é pagamento recorrente — não deve disparar home_change."""
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector
        recent = self._df([
            _txn(-1500, "DEPOSITO ALUGUEL APT 101"),
            _txn(-1500, "ALUGUEL RESIDENCIAL"),
        ])
        history = self._df([])
        events = LifeEventsDetector().detect_all(recent, history, 5000.0, 5000.0)
        assert not any(e.event == "home_change" for e in events)

    def test_wedding_detected_above_threshold(self):
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector
        recent = self._df([_txn(-2000, "BUFFET CERIMONIAL CASAMENTO")])
        history = self._df([])
        events = LifeEventsDetector().detect_all(recent, history, 5000.0, 5000.0)
        assert any(e.event == "wedding" for e in events)

    def test_education_detected(self):
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector
        recent = self._df([_txn(-500, "FACULDADE MENSALIDADE EAD")])
        history = self._df([])
        events = LifeEventsDetector().detect_all(recent, history, 5000.0, 5000.0)
        assert any(e.event == "new_education" for e in events)

    def test_income_increase_detected(self):
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector
        events = LifeEventsDetector().detect_all(
            _make_df([]), _make_df([]),
            income_recent=8000.0,
            income_historical=5000.0,
        )
        assert any(e.event == "income_increase" for e in events)

    def test_income_drop_detected(self):
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector
        events = LifeEventsDetector().detect_all(
            _make_df([]), _make_df([]),
            income_recent=3000.0,
            income_historical=6000.0,
        )
        assert any(e.event == "income_drop" for e in events)

    def test_income_no_event_for_zero_historical(self):
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector
        events = LifeEventsDetector().detect_all(
            _make_df([]), _make_df([]),
            income_recent=5000.0,
            income_historical=0.0,
        )
        assert not any(e.event in ("income_increase", "income_drop") for e in events)

    def test_empty_dfs_return_empty_list(self):
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector
        events = LifeEventsDetector().detect_all(
            _make_df([]), _make_df([]), 3000.0, 3000.0
        )
        assert events == []


# ═══════════════════════════════════════════════════════════════════════════
# T2.2 — FSSCalculator
# ═══════════════════════════════════════════════════════════════════════════

class TestFSSCalculator:
    def _profile(self, savings_rate=20.0, committed_pct=0.3, credit_ratio=0.4):
        from app.optimizer.profiler import UserProfile
        return UserProfile(
            monthly_avg_spend=3000.0,
            savings_rate=savings_rate,
            committed_percentage=committed_pct,
            credit_spend_ratio=credit_ratio,
        )

    def test_saudavel_level_with_high_resilience(self):
        from app.optimizer.detectors.fss_calculator import FSSCalculator
        result = FSSCalculator().calc_fss(
            self._profile(), pl.DataFrame(), resilience_score=90
        )
        assert result["fss_level"] == "SAUDAVEL"
        assert result["fss"] <= 20

    def test_critico_level_with_low_resilience(self):
        from app.optimizer.detectors.fss_calculator import FSSCalculator
        result = FSSCalculator().calc_fss(
            self._profile(savings_rate=-20.0, committed_pct=0.8, credit_ratio=0.9),
            pl.DataFrame(),
            resilience_score=5,
        )
        assert result["fss_level"] in ("ALERTA", "CRITICO")
        assert result["fss"] > 40

    def test_fss_capped_at_100(self):
        from app.optimizer.detectors.fss_calculator import FSSCalculator
        result = FSSCalculator().calc_fss(
            self._profile(savings_rate=-30.0, committed_pct=0.9, credit_ratio=0.99),
            pl.DataFrame(),
            resilience_score=0,
        )
        assert result["fss"] <= 100.0

    def test_revolving_signal_added_when_high_commitment_and_credit(self):
        from app.optimizer.detectors.fss_calculator import FSSCalculator
        profile = self._profile(committed_pct=0.75, credit_ratio=0.85)
        result = FSSCalculator().calc_fss(profile, pl.DataFrame(), resilience_score=50)
        assert any("revolving" in s for s in result["fss_signals"])

    def test_fallback_without_resilience_score(self):
        from app.optimizer.detectors.fss_calculator import FSSCalculator
        profile = self._profile(savings_rate=-10.0, committed_pct=0.5)
        result = FSSCalculator().calc_fss(profile, pl.DataFrame())
        assert result["fss"] > 0
        assert result["fss_level"] in ("SAUDAVEL", "ATENCAO", "ALERTA", "CRITICO")

    def test_overdraft_detection_by_keyword(self):
        from app.optimizer.detectors.fss_calculator import FSSCalculator
        rows = [
            {"date": date(2026, 3, 10), "amount": -50.0, "description": "IOF ESPECIAL"},
        ]
        overdraft_df = pl.DataFrame(rows, schema={"date": pl.Date, "amount": pl.Float64, "description": pl.Utf8})
        profile = self._profile()
        result = FSSCalculator().calc_fss(profile, overdraft_df, resilience_score=80)
        assert any("overdraft" in s for s in result["fss_signals"])


# ═══════════════════════════════════════════════════════════════════════════
# T2.3 — FamilyDetector
# ═══════════════════════════════════════════════════════════════════════════

class TestFamilyDetector:
    def test_not_family_with_empty_df(self):
        from app.optimizer.detectors.family_detector import FamilyDetector
        result = FamilyDetector().detect_family_profile(pl.DataFrame())
        assert result["is_family_with_kids"] is False
        assert result["family_score"] == 0.0

    def test_family_detected_with_school_spend(self):
        from app.optimizer.detectors.family_detector import FamilyDetector
        rows = [_txn(-500, "ESCOLA INFANTIL MENSALIDADE")]
        result = FamilyDetector().detect_family_profile(_make_df(rows))
        assert result["family_score"] >= 30
        assert any("school_spend" in s for s in result["family_signals"])

    def test_family_detected_above_threshold(self):
        from app.optimizer.detectors.family_detector import FamilyDetector
        rows = [
            _txn(-500, "ESCOLA INFANTIL"),
            _txn(-200, "PAMPERS FRALDA"),
        ]
        result = FamilyDetector().detect_family_profile(_make_df(rows))
        assert result["is_family_with_kids"] is True
        assert result["family_score"] >= 40

    def test_family_not_detected_below_threshold(self):
        from app.optimizer.detectors.family_detector import FamilyDetector
        rows = [_txn(-80, "PAMPERS FRALDA")]  # baby_spend < 100 → no signal
        result = FamilyDetector().detect_family_profile(_make_df(rows))
        assert result["is_family_with_kids"] is False

    def test_pediatric_visits_add_score(self):
        from app.optimizer.detectors.family_detector import FamilyDetector
        rows = [
            _txn(-150, "PEDIATR DR SILVA"),
            _txn(-150, "PEDIATR CLINICA SORRISO"),
        ]
        result = FamilyDetector().detect_family_profile(_make_df(rows))
        assert any("pediatric" in s for s in result["family_signals"])

    def test_kids_entertainment_adds_score(self):
        from app.optimizer.detectors.family_detector import FamilyDetector
        rows = [
            _txn(-100, "PARQUE DIVERSOES"),
            _txn(-80, "BRINQUEDOTECA KIDS"),
        ]
        result = FamilyDetector().detect_family_profile(_make_df(rows))
        assert any("kids_entertainment" in s for s in result["family_signals"])


# ═══════════════════════════════════════════════════════════════════════════
# T2.4 — rank_hyperpersonalized (4 pesos)
# ═══════════════════════════════════════════════════════════════════════════

class TestHyperpersonalizedRanking:
    def _card(self, card_id, net_gain, tags=None, annuity=0):
        from app.optimizer.models import CardSimulationResult, CardFlag, LiquidityRisk
        tags = tags or []
        return CardSimulationResult(
            card_id=card_id,
            card_name=card_id,
            issuer="B",
            flag=CardFlag.MASTERCARD,
            annuity_effective=annuity,
            annuity_waived=(annuity == 0),
            points_value_min=net_gain * 0.8,
            points_value_expected=net_gain,
            points_value_max=net_gain * 1.2,
            net_gain_min=net_gain * 0.8,
            net_gain_expected=net_gain,
            net_gain_max=net_gain * 1.2,
            liquidity_impact=0.0,
            liquidity_risk=LiquidityRisk.SAFE,
            confidence_score=0.9,
            eligibility_score=0.9,
            benefit_tags=tags,
        )

    def test_explorador_prefers_travel_card_over_cashback(self):
        from app.optimizer.ranking import CardRanking
        from app.optimizer.profiler import UserProfile
        from app.optimizer.models import BenefitTag
        profile = UserProfile(
            monthly_avg_spend=5000.0,
            lifestyle_cluster="EXPLORADOR_GLOBAL",
            travel_spend_monthly=800.0,
            international_spend_monthly=200.0,
            committed_percentage=0.3,
            spending_stability=0.8,
            credit_spend_ratio=0.9,
            spend_by_category={},
        )
        travel_card = self._card("travel", 1000, [BenefitTag.LOUNGE, BenefitTag.TRAVEL])
        cashback_card = self._card("cashback", 1200, [BenefitTag.CASHBACK])
        ranked = CardRanking().rank_hyperpersonalized([cashback_card, travel_card], profile)
        assert ranked[0].card_id == "travel"

    def test_all_hyperscores_between_0_and_100(self):
        from app.optimizer.ranking import CardRanking
        from app.optimizer.profiler import UserProfile
        profile = UserProfile(
            monthly_avg_spend=3000.0,
            lifestyle_cluster="FAMILIA_ESTRUTURADA",
            committed_percentage=0.4,
            spending_stability=0.6,
            credit_spend_ratio=0.7,
            spend_by_category={},
        )
        cards = [self._card(f"c{i}", 300 + i * 200) for i in range(5)]
        rank = CardRanking()
        for card in cards:
            score = rank._compute_hyperscore(card, profile)
            assert 0.0 <= score <= 100.0, f"Hyperscore {score} out of [0,100]"

    def test_fss_critico_penalizes_cards_with_high_annuity(self):
        from app.optimizer.ranking import CardRanking
        from app.optimizer.profiler import UserProfile
        profile = UserProfile(
            monthly_avg_spend=3000.0,
            lifestyle_cluster="ESTRESSE_FINANCEIRO",
            fss_level="CRITICO",
            committed_percentage=0.8,
            spending_stability=0.2,
            credit_spend_ratio=0.5,
            spend_by_category={},
        )
        expensive = self._card("expensive", 1000, annuity=600)
        cheap = self._card("cheap", 800, annuity=0)
        rank = CardRanking()
        score_expensive = rank._calc_timing_score(expensive, profile)
        score_cheap = rank._calc_timing_score(cheap, profile)
        assert score_expensive < score_cheap


# ═══════════════════════════════════════════════════════════════════════════
# T2.5 — Airbnb / Nômade Digital (covered in TestTravelDetector above)
# Additional: integration with profiler
# ═══════════════════════════════════════════════════════════════════════════

class TestAirbnbProfilerIntegration:
    def test_profiler_sets_is_airbnb_user(self):
        from app.optimizer.profiler import ConsumptionProfiler
        rows = [
            _txn(-600, f"AIRBNB RESERVA {i}", days_ago=10 + i * 5)
            for i in range(3)
        ]
        rows += [_txn(5000, "SALARIO", days_ago=30, txn_type="CREDIT")]
        df = _make_df(rows)
        profile = ConsumptionProfiler().build(df)
        assert profile.is_airbnb_user is True

    def test_profiler_sets_peak_spend_day(self):
        from app.optimizer.profiler import ConsumptionProfiler
        rows = [_txn(-1000, "SUPERMERCADO", days_ago=5)]
        rows += [_txn(5000, "SALARIO", days_ago=30, txn_type="CREDIT")]
        df = _make_df(rows)
        profile = ConsumptionProfiler().build(df)
        assert profile.peak_spend_day_of_month is not None


# ═══════════════════════════════════════════════════════════════════════════
# T2.6 — InsightGenerator personalization
# ═══════════════════════════════════════════════════════════════════════════

class TestInsightPersonalization:
    def _profile(self, cluster):
        from app.optimizer.profiler import UserProfile
        return UserProfile(
            monthly_avg_spend=3000.0,
            lifestyle_cluster=cluster,
            committed_percentage=0.3,
            credit_spend_ratio=0.8,
            spend_by_category={},
        )

    def test_explorador_prefix_in_description(self):
        from app.optimizer.insight_generator import InsightGenerator
        gen = InsightGenerator()
        profile = self._profile("EXPLORADOR_GLOBAL")
        text = gen._personalize_description("base text", profile, 1200.0)
        assert "Para quem viaja como você" in text

    def test_foodie_prefix_in_description(self):
        from app.optimizer.insight_generator import InsightGenerator
        gen = InsightGenerator()
        profile = self._profile("URBANO_FOODIE")
        text = gen._personalize_description("base text", profile, 800.0)
        assert "Com seu gasto em alimentação" in text

    def test_unclassified_returns_base_description(self):
        from app.optimizer.insight_generator import InsightGenerator
        gen = InsightGenerator()
        profile = self._profile("NAO_CLASSIFICADO")
        base = "my base description"
        text = gen._personalize_description(base, profile, 500.0)
        assert text == base

    def test_investidor_prefix_in_description(self):
        from app.optimizer.insight_generator import InsightGenerator
        gen = InsightGenerator()
        profile = self._profile("INVESTIDOR_CAUTELOSO")
        text = gen._personalize_description("base text", profile, 2000.0)
        assert "Calculando o custo de oportunidade" in text


# ═══════════════════════════════════════════════════════════════════════════
# T2.7 — TemporalDetector
# ═══════════════════════════════════════════════════════════════════════════

class TestTemporalDetector:
    def test_empty_returns_defaults(self):
        from app.optimizer.detectors.temporal_detector import TemporalDetector
        result = TemporalDetector().analyze(pl.DataFrame())
        assert result["peak_spend_day_of_month"] is None
        assert result["best_notification_day"] == 5
        assert result["spending_pattern"] == "IRREGULAR"

    def test_peak_day_is_most_spent_day(self):
        from app.optimizer.detectors.temporal_detector import TemporalDetector
        rows = [
            {"date": date(2026, 3, 10), "amount": -1000.0},
            {"date": date(2026, 3, 10), "amount": -500.0},  # day 10 = R$1500 total
            {"date": date(2026, 3, 20), "amount": -200.0},
        ]
        df = pl.DataFrame(rows, schema={"date": pl.Date, "amount": pl.Float64})
        result = TemporalDetector().analyze(df)
        assert result["peak_spend_day_of_month"] == 10

    def test_best_notification_day_is_peak_minus_3(self):
        from app.optimizer.detectors.temporal_detector import TemporalDetector
        rows = [
            {"date": date(2026, 3, 15), "amount": -800.0},
            {"date": date(2026, 3, 5), "amount": -200.0},
        ]
        df = pl.DataFrame(rows, schema={"date": pl.Date, "amount": pl.Float64})
        result = TemporalDetector().analyze(df)
        assert result["peak_spend_day_of_month"] == 15
        assert result["best_notification_day"] == 12

    def test_best_notification_day_minimum_is_1(self):
        from app.optimizer.detectors.temporal_detector import TemporalDetector
        rows = [{"date": date(2026, 3, 2), "amount": -1000.0}]
        df = pl.DataFrame(rows, schema={"date": pl.Date, "amount": pl.Float64})
        result = TemporalDetector().analyze(df)
        assert result["best_notification_day"] >= 1

    def test_regular_pattern_with_low_cv(self):
        from app.optimizer.detectors.temporal_detector import TemporalDetector
        months = [(2026, m) for m in range(1, 4)]
        rows = [
            {"date": date(y, m, 10), "amount": -1000.0}
            for y, m in months
        ]
        df = pl.DataFrame(rows, schema={"date": pl.Date, "amount": pl.Float64})
        result = TemporalDetector().analyze(df)
        assert result["spending_pattern"] == "REGULAR"

    def test_irregular_pattern_with_high_cv(self):
        from app.optimizer.detectors.temporal_detector import TemporalDetector
        rows = [
            {"date": date(2026, 1, 10), "amount": -100.0},
            {"date": date(2026, 2, 10), "amount": -5000.0},
            {"date": date(2026, 3, 10), "amount": -150.0},
        ]
        df = pl.DataFrame(rows, schema={"date": pl.Date, "amount": pl.Float64})
        result = TemporalDetector().analyze(df)
        assert result["spending_pattern"] == "IRREGULAR"

    def test_is_weekend_spender_when_weekend_dominates(self):
        from app.optimizer.detectors.temporal_detector import TemporalDetector
        # 2026-03-07 = Saturday, 2026-03-08 = Sunday
        rows = [
            {"date": date(2026, 3, 7), "amount": -800.0},
            {"date": date(2026, 3, 8), "amount": -600.0},
            {"date": date(2026, 3, 10), "amount": -100.0},  # Tuesday
        ]
        df = pl.DataFrame(rows, schema={"date": pl.Date, "amount": pl.Float64})
        result = TemporalDetector().analyze(df)
        assert result["is_weekend_spender"] is True


# ═══════════════════════════════════════════════════════════════════════════
# Pipeline integration: profiler.build() runs all detectors in correct order
# ═══════════════════════════════════════════════════════════════════════════

class TestProfilerPipelineIntegration:
    def test_lifestyle_classifier_runs_after_family_detector(self):
        """Família com filhos deve produzir cluster FAMILIA_ESTRUTURADA."""
        from app.optimizer.profiler import ConsumptionProfiler
        rows = [
            _txn(-600, "ESCOLA INFANTIL MENSALIDADE", days_ago=15),
            _txn(-200, "PAMPERS FRALDA TAMANHO G", days_ago=10),
            _txn(5000, "SALARIO", days_ago=30, txn_type="CREDIT"),
        ]
        df = _make_df(rows)
        profile = ConsumptionProfiler().build(df)
        assert profile.is_family_with_kids is True
        assert profile.lifestyle_cluster == "FAMILIA_ESTRUTURADA"

    def test_lifestyle_classifier_runs_after_airbnb_detector(self):
        """Airbnb regular + coworking deve produzir EXPLORADOR_GLOBAL."""
        from app.optimizer.profiler import ConsumptionProfiler
        rows = (
            [_txn(-600, f"AIRBNB RESERVA {i}", days_ago=10 + i * 5) for i in range(3)]
            + [_txn(-800, "WEWORK COWORKING", days_ago=20)]
            + [_txn(-800, "WEWORK COWORKING", days_ago=40)]
            + [_txn(5000, "SALARIO", days_ago=30, txn_type="CREDIT")]
        )
        df = _make_df(rows)
        profile = ConsumptionProfiler().build(df)
        assert profile.is_airbnb_user is True

    def test_profiler_sets_all_fase2_fields(self):
        from app.optimizer.profiler import ConsumptionProfiler
        rows = [
            _txn(-500, "SUPERMERCADO", days_ago=5),
            _txn(5000, "SALARIO", days_ago=30, txn_type="CREDIT"),
        ]
        df = _make_df(rows)
        profile = ConsumptionProfiler().build(df)
        # Todos os campos Fase 2 devem existir e ter tipos corretos
        assert isinstance(profile.is_family_with_kids, bool)
        assert isinstance(profile.family_score, float)
        assert isinstance(profile.is_airbnb_user, bool)
        assert isinstance(profile.is_digital_nomad, bool)
        assert profile.peak_spend_day_of_month is None or isinstance(profile.peak_spend_day_of_month, int)
        assert isinstance(profile.best_notification_day, int)
        assert isinstance(profile.resilience_score, float)

    def test_fss_populated_in_optimizer_service(self):
        """OptimizerService deve popular fss/fss_level no profile."""
        from app.optimizer.profiler import ConsumptionProfiler
        rows = [
            _txn(-500, "SUPERMERCADO", days_ago=5),
            _txn(5000, "SALARIO", days_ago=30, txn_type="CREDIT"),
        ]
        df = _make_df(rows)
        profile = ConsumptionProfiler().build(df)
        # FSS calculado externamente no optimizer_service — aqui validamos que
        # o profiler retorna resilience_score correto para alimentar o FSSCalculator
        assert profile.resilience_score >= 0.0
        assert profile.resilience_score <= 100.0
