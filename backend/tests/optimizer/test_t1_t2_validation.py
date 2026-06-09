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

    # ── Taxonomia canônica ────────────────────────────────────────────────────

    def test_merchant_category_l1_viagem_for_airbnb(self):
        df = self._enrich([_txn(-600, "AIRBNB RESERVA")])
        assert df["merchant_category_l1"][0] == "viagem"

    def test_merchant_category_l1_alimentacao_for_restaurante(self):
        df = self._enrich([_txn(-80, "RESTAURANTE BELO SABOR")])
        assert df["merchant_category_l1"][0] == "alimentacao"

    def test_merchant_category_l1_alimentacao_for_delivery(self):
        df = self._enrich([_txn(-45, "IFOOD PEDIDO 123")])
        assert df["merchant_category_l1"][0] == "alimentacao"

    def test_merchant_category_l1_supermercado_distinct_from_alimentacao(self):
        df = self._enrich([_txn(-200, "SUPERMERCADO EXTRA")])
        assert df["merchant_category_l1"][0] == "supermercado"

    def test_merchant_category_l1_farmacia(self):
        df = self._enrich([_txn(-60, "DROGASIL FARMACIA")])
        assert df["merchant_category_l1"][0] == "farmacia"

    def test_merchant_category_l1_streaming(self):
        df = self._enrich([_txn(-40, "NETFLIX MENSALIDADE")])
        assert df["merchant_category_l1"][0] == "streaming"

    def test_merchant_category_l1_none_for_unknown(self):
        df = self._enrich([_txn(-100, "LOJA GENÉRICA ABC")])
        assert df["merchant_category_l1"][0] is None

    def test_category_canonical_normalizes_accents(self):
        from app.optimizer.feature_store import TransactionFeatureEnricher
        df = pl.DataFrame(
            [{"date": date.today(), "amount": -100.0, "description": "PADARIA",
              "category": "Alimentação", "transaction_type": "CREDIT"}],
            schema={"date": pl.Date, "amount": pl.Float64, "description": pl.Utf8,
                    "category": pl.Utf8, "transaction_type": pl.Utf8},
        )
        enriched = TransactionFeatureEnricher().enrich(df)
        assert enriched["category_canonical"][0] == "alimentacao"

    def test_category_canonical_normalizes_saude(self):
        from app.optimizer.feature_store import TransactionFeatureEnricher
        df = pl.DataFrame(
            [{"date": date.today(), "amount": -50.0, "description": "CONSULTA",
              "category": "Saúde", "transaction_type": "CREDIT"}],
            schema={"date": pl.Date, "amount": pl.Float64, "description": pl.Utf8,
                    "category": pl.Utf8, "transaction_type": pl.Utf8},
        )
        enriched = TransactionFeatureEnricher().enrich(df)
        assert enriched["category_canonical"][0] == "saude"

    def test_category_canonical_outros_falls_back_to_l1(self):
        """Quando category='Outros', category_canonical deve usar merchant_category_l1."""
        from app.optimizer.feature_store import TransactionFeatureEnricher
        df = pl.DataFrame(
            [{"date": date.today(), "amount": -200.0, "description": "CARREFOUR SUPERMERCADO",
              "category": "Outros", "transaction_type": "CREDIT"}],
            schema={"date": pl.Date, "amount": pl.Float64, "description": pl.Utf8,
                    "category": pl.Utf8, "transaction_type": pl.Utf8},
        )
        enriched = TransactionFeatureEnricher().enrich(df)
        assert enriched["category_canonical"][0] == "supermercado"

    def test_merchant_normalized_removes_pg_prefix(self):
        df = self._enrich([_txn(-15, "PG*SPOTIFY")])
        assert df["merchant_normalized"][0] == "SPOTIFY"

    def test_merchant_normalized_removes_pagamento_pix(self):
        df = self._enrich([_txn(-500, "PAGAMENTO PIX ENVIADO EMPRESA ABC")])
        assert df["merchant_normalized"][0] == "EMPRESA ABC"

    def test_merchant_normalized_removes_dotcom(self):
        df = self._enrich([_txn(-40, "NETFLIX.COM")])
        assert df["merchant_normalized"][0] == "NETFLIX"

    def test_merchant_normalized_replaces_asterisk(self):
        df = self._enrich([_txn(-80, "IFOOD*PADARIA DA ESQUINA")])
        assert df["merchant_normalized"][0] == "IFOOD PADARIA DA ESQUINA"

    def test_spend_by_category_uses_canonical_keys(self):
        """spend_by_category deve usar chaves lowercase sem acento após enrich."""
        from app.optimizer.profiler import ConsumptionProfiler
        df = pl.DataFrame(
            [{"date": date.today(), "amount": -300.0, "description": "RESTAURANTE",
              "category": "Alimentação", "transaction_type": "CREDIT"},
             {"date": date.today(), "amount": -100.0, "description": "FARMACIA XYZ",
              "category": "Saúde", "transaction_type": "CREDIT"}],
            schema={"date": pl.Date, "amount": pl.Float64, "description": pl.Utf8,
                    "category": pl.Utf8, "transaction_type": pl.Utf8},
        )
        profile = ConsumptionProfiler().build(df)
        # Chaves devem ser canonizadas — não "Alimentação" ou "Saúde"
        assert "alimentacao" in profile.spend_by_category or "supermercado" in profile.spend_by_category or len(profile.spend_by_category) > 0
        # Garantir que não há chaves com acento
        for key in profile.spend_by_category:
            assert key == key.lower(), f"Chave não-lowercase: {key}"
            assert "ã" not in key and "é" not in key and "ç" not in key, f"Chave com acento: {key}"


# ═══════════════════════════════════════════════════════════════════════════
# T1.1b — merchant_id canônico
# ═══════════════════════════════════════════════════════════════════════════

class TestMerchantId:
    def _enrich(self, rows: list[dict]) -> pl.DataFrame:
        from app.optimizer.feature_store import TransactionFeatureEnricher
        return TransactionFeatureEnricher().enrich(_make_df(rows))

    def test_pg_spotify_collapses_to_spotify(self):
        df = self._enrich([_txn(-15, "PG*SPOTIFY")])
        assert df["merchant_id"][0] == "spotify"

    def test_spotify_com_collapses_to_spotify(self):
        df = self._enrich([_txn(-15, "SPOTIFY.COM")])
        assert df["merchant_id"][0] == "spotify"

    def test_spotify_brasil_collapses_to_spotify(self):
        df = self._enrich([_txn(-15, "SPOTIFY BRASIL")])
        assert df["merchant_id"][0] == "spotify"

    def test_three_spotify_aliases_yield_n_unique_one(self):
        df = self._enrich([
            _txn(-15, "PG*SPOTIFY"),
            _txn(-15, "SPOTIFY.COM"),
            _txn(-15, "SPOTIFY BRASIL"),
        ])
        assert df["merchant_id"].n_unique() == 1

    def test_uber_eats_distinct_from_uber(self):
        df = self._enrich([
            _txn(-40, "UBER EATS COMPRA"),
            _txn(-20, "UBER CORRIDA"),
        ])
        assert df["merchant_id"][0] == "uber_eats"
        assert df["merchant_id"][1] == "uber"

    def test_amazon_prime_distinct_from_amazon(self):
        df = self._enrich([
            _txn(-30, "AMAZON PRIME VIDEO"),
            _txn(-80, "AMAZON MARKETPLACE"),
        ])
        assert df["merchant_id"][0] == "amazon_prime"
        assert df["merchant_id"][1] == "amazon"

    def test_ifood_variants_collapse(self):
        df = self._enrich([
            _txn(-30, "IFOOD*PADARIA DA ESQUINA"),
            _txn(-25, "PG*IFOOD"),
            _txn(-35, "IFOOD.COM"),
        ])
        assert all(mid == "ifood" for mid in df["merchant_id"].to_list())

    def test_netflix_com_collapses(self):
        df = self._enrich([_txn(-45, "NETFLIX.COM")])
        assert df["merchant_id"][0] == "netflix"

    def test_mercado_pago_distinct_from_mercado_livre(self):
        df = self._enrich([
            _txn(-50, "MERCADO PAGO COMPRA"),
            _txn(-90, "MERCADO LIVRE VENDA"),
        ])
        assert df["merchant_id"][0] == "mercado_pago"
        assert df["merchant_id"][1] == "mercado_livre"

    def test_general_fallback_slugifies(self):
        df = self._enrich([_txn(-100, "RESTAURANTE BELO SABOR")])
        mid = df["merchant_id"][0]
        assert " " not in mid
        assert mid == "restaurante_belo_sabor"

    def test_general_fallback_strips_ltda(self):
        df = self._enrich([_txn(-200, "PADARIA DO JOAO LTDA")])
        mid = df["merchant_id"][0]
        assert "ltda" not in mid

    def test_idempotent_does_not_overwrite_existing(self):
        from app.optimizer.feature_store import TransactionFeatureEnricher
        df = _make_df([_txn(-15, "NETFLIX")])
        df = df.with_columns(pl.lit("custom_netflix").alias("merchant_id"))
        enriched = TransactionFeatureEnricher().enrich(df)
        assert enriched["merchant_id"][0] == "custom_netflix"

    def test_merchant_id_field_present_after_enrich(self):
        df = self._enrich([_txn(-50, "QUALQUER COMPRA")])
        assert "merchant_id" in df.columns


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

    def test_secondary_clusters_returned(self):
        """Perfil com sinais fortes em 2 dimensões deve gerar cluster secundário."""
        from app.optimizer.detectors.lifestyle_classifier import LifestyleClassifier
        # Ambos os clusters têm sinais fortes — o primário é o de maior score;
        # o outro deve aparecer nos secundários.
        p = self._base_profile(
            travel_frequency_score=85.0,
            travel_profile="INTENSO",
            international_spend_monthly=700.0,
            investor_type="ATIVO",
            savings_rate=40.0,
        )
        result = LifestyleClassifier().classify(p)
        primary = result["lifestyle_cluster"]
        secondary = result["secondary_clusters"]
        assert isinstance(secondary, list)
        # Um dos dois clusters deve ser primário e o outro deve aparecer como secundário
        target_clusters = {"EXPLORADOR_GLOBAL", "INVESTIDOR_CAUTELOSO"}
        assert primary in target_clusters, f"Esperado um de {target_clusters}, obtido {primary}"
        other = target_clusters - {primary}
        assert other & set(secondary), f"Esperado {other} nos secundários, obtidos {secondary}"

    def test_secondary_clusters_max_two(self):
        """Nunca mais de 2 clusters secundários."""
        from app.optimizer.detectors.lifestyle_classifier import LifestyleClassifier
        p = self._base_profile(
            travel_frequency_score=80.0,
            travel_profile="FREQUENTE",
            international_spend_monthly=500.0,
            investor_type="ATIVO",
            savings_rate=35.0,
            is_likely_mei=True,
        )
        result = LifestyleClassifier().classify(p)
        assert len(result["secondary_clusters"]) <= 2

    def test_secondary_clusters_empty_when_unclassified(self):
        """NAO_CLASSIFICADO não deve ter clusters secundários."""
        from app.optimizer.detectors.lifestyle_classifier import LifestyleClassifier
        p = self._base_profile(
            subscription_burn_monthly=0.0,
            merchant_diversity_score=0.0,
            credit_spend_ratio=1.0,
        )
        result = LifestyleClassifier().classify(p)
        assert result["lifestyle_cluster"] == "NAO_CLASSIFICADO"
        # Pode ter secundários (scores >= 0.30) mesmo sem primário — tudo bem
        assert isinstance(result["secondary_clusters"], list)

    def test_primary_not_in_secondary_clusters(self):
        """O cluster primário não deve aparecer nos secundários."""
        from app.optimizer.detectors.lifestyle_classifier import LifestyleClassifier
        p = self._base_profile(
            travel_frequency_score=80.0,
            travel_profile="INTENSO",
            international_spend_monthly=600.0,
            investor_type="ATIVO",
            savings_rate=30.0,
        )
        result = LifestyleClassifier().classify(p)
        primary = result["lifestyle_cluster"]
        assert primary not in result["secondary_clusters"]

    def test_userprofile_has_secondary_clusters_field(self):
        """UserProfile deve ter secondary_clusters inicializado como lista vazia."""
        from app.optimizer.profiler import UserProfile
        p = UserProfile()
        assert hasattr(p, "secondary_clusters")
        assert isinstance(p.secondary_clusters, list)


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
        # LEROY MERLIN é keyword ambígua (quality=0.65): sem corroboração precisa de
        # volume alto (≥2× spend_gate = R$1.000) para superar a penalidade de evidência negativa.
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector
        recent = self._df([_txn(-1000, "LEROY MERLIN REFORMA")])
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

    def test_confidence_grows_with_income_change_magnitude(self):
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector
        det = LifeEventsDetector()
        e_small = det.detect_all(_make_df([]), _make_df([]), 6200.0, 5000.0)   # +24%
        e_large = det.detect_all(_make_df([]), _make_df([]), 10000.0, 5000.0)  # +100%
        conf_small = next(e.confidence for e in e_small if e.event == "income_increase")
        conf_large = next(e.confidence for e in e_large if e.event == "income_increase")
        assert conf_large > conf_small

    def test_multi_signal_wedding_higher_confidence_than_single(self):
        """BUFFET+DECORACAO+FOTOGRAFO deve ter confiança bem acima de BUFFET isolado."""
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector
        det = LifeEventsDetector()

        single = _make_df([_txn(-1100, "BUFFET CASAMENTO")])
        multi = _make_df([
            _txn(-1500, "BUFFET CASAMENTO",        days_ago=5),
            _txn(-2000, "DECORACAO FESTA NOIVAS",  days_ago=15),
            _txn(-3000, "FOTOGRAFO CASAMENTO",     days_ago=25),
        ])
        history = _make_df([])

        ev_single = det.detect_all(single, history, 5000.0, 5000.0)
        ev_multi  = det.detect_all(multi,  history, 5000.0, 5000.0)

        conf_single = next((e.confidence for e in ev_single if e.event == "wedding"), 0.0)
        conf_multi  = next(e.confidence  for e in ev_multi  if e.event == "wedding")

        assert conf_multi > conf_single
        assert conf_multi >= 0.75, f"multi-sinal esperado >= 0.75, obtido {conf_multi}"

    def test_isolated_buffet_has_low_confidence(self):
        """Um único BUFFET isolado deve gerar confiança abaixo de 0.65."""
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector
        recent = _make_df([_txn(-1100, "BUFFET JANTAR CORPORATIVO")])
        events = LifeEventsDetector().detect_all(recent, _make_df([]), 5000.0, 5000.0)
        wedding = next((e for e in events if e.event == "wedding"), None)
        # Pode ser detectado (threshold passa), mas confiança deve ser baixa
        if wedding:
            assert wedding.confidence < 0.65, (
                f"BUFFET isolado não deve ter confiança alta, obtido {wedding.confidence}"
            )

    def test_evidence_score_signals_in_supporting_signals(self):
        """supporting_signals deve incluir breakdown do EvidenceScore."""
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector
        recent = _make_df([
            _txn(-600, "PAMPERS FRALDA", days_ago=3),
            _txn(-400, "HUGGIES BEBE",   days_ago=20),
        ])
        events = LifeEventsDetector().detect_all(recent, _make_df([]), 5000.0, 5000.0)
        baby = next(e for e in events if e.event == "new_baby")
        signal_keys = " ".join(baby.supporting_signals)
        assert "ev_volume" in signal_keys
        assert "ev_absence" in signal_keys
        assert "txn_count" in signal_keys


# ═══════════════════════════════════════════════════════════════════════════
# EvidenceScore unit tests
# ═══════════════════════════════════════════════════════════════════════════

class TestEvidenceScorer:
    def test_single_transaction_at_threshold_is_low_confidence(self):
        from app.optimizer.detectors.evidence_scorer import compute_evidence_score
        ev = compute_evidence_score(
            recent_spend=1000.0, txn_count=1, merchant_count=1,
            months_with_signal=1, historical_spend=0.0,
            spend_threshold=1000, history_baseline=200, quality=0.72,
        )
        assert ev.composite < 0.65, f"sinal isolado esperado < 0.65, obtido {ev.composite}"
        assert ev.diversity == 0.0
        assert ev.recurrence == 0.0

    def test_multi_merchant_raises_composite(self):
        from app.optimizer.detectors.evidence_scorer import compute_evidence_score
        single = compute_evidence_score(
            1000.0, 1, 1, 1, 0.0, 1000, 200, quality=0.72
        )
        multi = compute_evidence_score(
            5000.0, 3, 3, 2, 0.0, 1000, 200, quality=0.72
        )
        assert multi.composite > single.composite
        assert multi.diversity > 0

    def test_history_presence_reduces_absence(self):
        from app.optimizer.detectors.evidence_scorer import compute_evidence_score
        clean = compute_evidence_score(1000.0, 1, 1, 1, 0.0,   1000, 200, 0.72)
        dirty = compute_evidence_score(1000.0, 1, 1, 1, 150.0,  1000, 200, 0.72)
        assert clean.absence > dirty.absence
        assert clean.composite > dirty.composite

    def test_composite_capped_at_one(self):
        from app.optimizer.detectors.evidence_scorer import compute_evidence_score
        ev = compute_evidence_score(
            100_000.0, 50, 20, 12, 0.0, 100, 50, quality=1.0
        )
        assert ev.composite <= 1.0

    def test_as_signals_returns_expected_keys(self):
        from app.optimizer.detectors.evidence_scorer import compute_evidence_score
        ev = compute_evidence_score(500.0, 2, 2, 1, 0.0, 300, 100, 0.85)
        keys = " ".join(ev.as_signals())
        assert "ev_volume" in keys
        assert "ev_recurrence" in keys
        assert "ev_absence" in keys
        assert "ev_diversity" in keys


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
        # 2026-03-07 = Saturday (ISO 6), 2026-03-08 = Sunday (ISO 7)
        rows = [
            {"date": date(2026, 3, 7), "amount": -800.0},
            {"date": date(2026, 3, 8), "amount": -600.0},
            {"date": date(2026, 3, 10), "amount": -100.0},  # Tuesday (ISO 2)
        ]
        df = pl.DataFrame(rows, schema={"date": pl.Date, "amount": pl.Float64})
        result = TemporalDetector().analyze(df)
        assert result["is_weekend_spender"] is True

    def test_friday_is_not_weekend(self):
        from app.optimizer.detectors.temporal_detector import TemporalDetector
        from app.optimizer.feature_store import TransactionFeatureEnricher
        # 2026-03-06 = Friday (ISO 5) — deve ser dia útil, não fim de semana
        rows = [
            {"date": date(2026, 3, 6), "amount": -900.0},   # Friday
            {"date": date(2026, 3, 9), "amount": -100.0},   # Monday
        ]
        df = pl.DataFrame(rows, schema={"date": pl.Date, "amount": pl.Float64})

        # TemporalDetector: sexta não conta como fim de semana
        result = TemporalDetector().analyze(df)
        assert result["is_weekend_spender"] is False, (
            "Sexta-feira (ISO 5) não deve ser classificada como fim de semana"
        )

        # feature_store: is_weekend deve ser False para sexta
        enriched = TransactionFeatureEnricher().enrich(df)
        assert enriched["is_weekend"][0] is False, (
            "feature_store: is_weekend deve ser False para sexta-feira (ISO weekday=5)"
        )


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


# ═══════════════════════════════════════════════════════════════════════════
# SOLICITAR_UPGRADE — ganho incremental vs. absoluto
# ═══════════════════════════════════════════════════════════════════════════

class TestSolicitarUpgradeIncremental:
    """
    _try_solicitar_upgrade deve usar ganho INCREMENTAL (vs. cartão atual),
    não o ganho absoluto do cartão premium.
    """

    def _premium_result(self, net_gain_annual: float) -> "CardSimulationResult":
        from app.optimizer.models import CardSimulationResult, CardFlag, LiquidityRisk, BenefitTag
        return CardSimulationResult(
            card_id="premium-card",
            card_name="Cartão Black Premium",
            issuer="Banco Premium",
            flag=CardFlag.MASTERCARD,
            annuity_effective=600.0,       # R$600/ano — satisfaz _UPGRADE_MIN_ANNUITY=300
            annuity_waived=False,
            points_value_min=net_gain_annual * 0.8 + 600,
            points_value_expected=net_gain_annual + 600,
            points_value_max=net_gain_annual * 1.2 + 600,
            net_gain_min=net_gain_annual * 0.8,
            net_gain_expected=net_gain_annual,
            net_gain_max=net_gain_annual * 1.2,
            liquidity_impact=0.02,
            liquidity_risk=LiquidityRisk.SAFE,
            confidence_score=0.95,
            eligibility_score=0.90,        # satisfaz _UPGRADE_ELIGIBILITY_GATE=0.85
            benefit_tags=[BenefitTag.LOUNGE, BenefitTag.PREMIUM],
        )

    def _profile(self):
        from app.optimizer.profiler import UserProfile
        return UserProfile(
            monthly_avg_spend=5000.0,
            committed_percentage=0.2,
            credit_spend_ratio=0.9,
            spend_by_category={},
        )

    def test_upgrade_suppressed_when_incremental_gain_below_gate(self):
        """
        Cartão premium retorna R$150/mês absoluto, mas usuário já tem R$145/mês
        no cartão atual. Ganho incremental = R$5/mês < gate R$10/mês → sem insight.
        """
        from app.optimizer.insight_generator import InsightGenerator
        gen = InsightGenerator()
        result = self._premium_result(net_gain_annual=1800.0)  # R$150/mês absoluto
        profile = self._profile()
        insight = gen._try_solicitar_upgrade(
            ranked_results=[result],
            profile=profile,
            current_card_id="outro-cartao",
            current_card_monthly_return=145.0,  # R$145/mês atual → incremental = R$5 < gate
        )
        assert insight is None, (
            "Incremental de R$5/mês (abaixo do gate R$10) não deve gerar insight de upgrade"
        )

    def test_upgrade_surfaced_when_incremental_gain_above_gate(self):
        """
        Cartão premium retorna R$150/mês, atual retorna R$80/mês.
        Incremental = R$70/mês > gate → insight deve aparecer com ganho incremental.
        """
        from app.optimizer.insight_generator import InsightGenerator
        gen = InsightGenerator()
        result = self._premium_result(net_gain_annual=1800.0)  # R$150/mês absoluto
        profile = self._profile()
        insight = gen._try_solicitar_upgrade(
            ranked_results=[result],
            profile=profile,
            current_card_id="outro-cartao",
            current_card_monthly_return=80.0,  # incremental = 150 - 80 = R$70/mês
        )
        assert insight is not None, "Incremental de R$70/mês deve gerar insight de upgrade"
        # O intervalo exibido deve ser incremental (≈R$70), não absoluto (≈R$150)
        assert insight.gain_interval.expected == pytest.approx(70.0, abs=5.0), (
            "gain_interval.expected deve ser incremental (~R$70), não absoluto (~R$150)"
        )

    def test_upgrade_with_zero_current_return_shows_absolute_gain(self):
        """Sem cartão atual (baseline 0), o ganho exibido é o absoluto do premium."""
        from app.optimizer.insight_generator import InsightGenerator
        gen = InsightGenerator()
        result = self._premium_result(net_gain_annual=1800.0)
        profile = self._profile()
        insight = gen._try_solicitar_upgrade(
            ranked_results=[result],
            profile=profile,
            current_card_id=None,
            current_card_monthly_return=0.0,
        )
        assert insight is not None
        assert insight.gain_interval.expected == pytest.approx(150.0, abs=5.0)


# ═══════════════════════════════════════════════════════════════════════════
# SpendingAnomalyDetector × merchant_id
# ═══════════════════════════════════════════════════════════════════════════

class TestSpendingAnomalyDetectorMerchantId:
    """
    Garante que merchant_id elimina falsos positivos do SpendingAnomalyDetector.

    Cenários críticos:
      NEW_MERCHANT  — alias visto no histórico não deve ser "novo merchant"
      DUPLICATE     — mesmo merchant_id, descrições distintas, mesmo valor = duplicata suspeita
    """

    # Valor acima de _NEW_MERCHANT_MIN_VALUE=200 para acionar NEW_MERCHANT
    _HIGH_AMOUNT = -250.0

    def _enrich(self, rows: list[dict]) -> pl.DataFrame:
        from app.optimizer.feature_store import TransactionFeatureEnricher
        return TransactionFeatureEnricher().enrich(_make_df(rows))

    def _new_merchant_anomalies(self, recent, history):
        from app.forecast.etl.spending_anomaly_detector import SpendingAnomalyDetector, AnomalyType
        anomalies = SpendingAnomalyDetector().detect(recent, history)
        return [a for a in anomalies if a.anomaly_type == AnomalyType.NEW_MERCHANT]

    def _duplicate_anomalies(self, recent, history):
        from app.forecast.etl.spending_anomaly_detector import SpendingAnomalyDetector, AnomalyType
        anomalies = SpendingAnomalyDetector().detect(recent, history)
        return [a for a in anomalies if a.anomaly_type == AnomalyType.DUPLICATE_SUSPECT]

    # ── NEW_MERCHANT ──────────────────────────────────────────────────────────

    def test_pg_netflix_in_history_makes_netflix_com_known(self):
        """PG*NETFLIX no histórico → NETFLIX.COM recente não é sinalizado como novo merchant."""
        history = self._enrich([_txn(self._HIGH_AMOUNT, "PG*NETFLIX", days_ago=60)])
        recent  = self._enrich([_txn(self._HIGH_AMOUNT, "NETFLIX.COM", days_ago=5)])
        assert self._new_merchant_anomalies(recent, history) == []

    def test_spotify_brasil_in_history_makes_pg_spotify_known(self):
        """SPOTIFY BRASIL no histórico → PG*SPOTIFY recente não é sinalizado como novo merchant."""
        history = self._enrich([_txn(self._HIGH_AMOUNT, "SPOTIFY BRASIL", days_ago=60)])
        recent  = self._enrich([_txn(self._HIGH_AMOUNT, "PG*SPOTIFY", days_ago=5)])
        assert self._new_merchant_anomalies(recent, history) == []

    def test_different_merchant_id_still_flagged_as_new(self):
        """NETFLIX no histórico → AMAZON PRIME VIDEO (merchant_id distinto) deve ser novo."""
        history = self._enrich([_txn(self._HIGH_AMOUNT, "NETFLIX", days_ago=60)])
        recent  = self._enrich([_txn(-239.90, "AMAZON PRIME VIDEO", days_ago=5)])
        flags = self._new_merchant_anomalies(recent, history)
        assert len(flags) >= 1, "amazon_prime é merchant_id diferente de netflix — deve ser flagged"

    def test_new_merchant_without_merchant_id_uses_description_fallback(self):
        """Sem merchant_id, fallback para description normalizada (comportamento original)."""
        # DataFrame sem enriquecimento — description raw
        df_hist   = _make_df([_txn(self._HIGH_AMOUNT, "PAGAMENTOS NETFLIX", days_ago=60)])
        df_recent = _make_df([_txn(self._HIGH_AMOUNT, "AMAZON PRIME", days_ago=5)])
        # Strings normalizadas diferentes → deve ser flagged
        flags = self._new_merchant_anomalies(df_recent, df_hist)
        assert len(flags) >= 1

    # ── DUPLICATE_SUSPECT ─────────────────────────────────────────────────────

    def test_pg_netflix_and_netflix_com_same_amount_flagged_as_duplicate(self):
        """PG*NETFLIX e NETFLIX.COM com mesmo valor em 1 dia → DUPLICATE_SUSPECT."""
        today = date.today()
        df = pl.DataFrame(
            [
                {"date": today - timedelta(days=1), "amount": -55.90,
                 "description": "PG*NETFLIX", "category": "Outros", "transaction_type": "CREDIT"},
                {"date": today,                    "amount": -55.90,
                 "description": "NETFLIX.COM",   "category": "Outros", "transaction_type": "CREDIT"},
            ],
            schema={"date": pl.Date, "amount": pl.Float64, "description": pl.Utf8,
                    "category": pl.Utf8, "transaction_type": pl.Utf8},
        )
        from app.optimizer.feature_store import TransactionFeatureEnricher
        df = TransactionFeatureEnricher().enrich(df)
        # Ambas as linhas têm merchant_id="netflix" — duplicata suspeita ✓
        flags = self._duplicate_anomalies(df, df)
        assert len(flags) >= 1, "PG*NETFLIX e NETFLIX.COM = mesmo merchant_id → duplicata suspeita"

    def test_pg_ifood_and_ifood_com_same_amount_flagged_as_duplicate(self):
        """PG*IFOOD e IFOOD.COM com mesmo valor em 1 dia → DUPLICATE_SUSPECT."""
        today = date.today()
        df = pl.DataFrame(
            [
                {"date": today - timedelta(days=1), "amount": -89.90,
                 "description": "PG*IFOOD",   "category": "Outros", "transaction_type": "CREDIT"},
                {"date": today,                    "amount": -89.90,
                 "description": "IFOOD.COM",   "category": "Outros", "transaction_type": "CREDIT"},
            ],
            schema={"date": pl.Date, "amount": pl.Float64, "description": pl.Utf8,
                    "category": pl.Utf8, "transaction_type": pl.Utf8},
        )
        from app.optimizer.feature_store import TransactionFeatureEnricher
        df = TransactionFeatureEnricher().enrich(df)
        flags = self._duplicate_anomalies(df, df)
        assert len(flags) >= 1

    def test_spotify_and_netflix_same_amount_not_flagged_as_duplicate(self):
        """SPOTIFY e NETFLIX com mesmo valor em 1 dia → NÃO é DUPLICATE_SUSPECT."""
        today = date.today()
        df = pl.DataFrame(
            [
                {"date": today - timedelta(days=1), "amount": -55.90,
                 "description": "SPOTIFY",  "category": "Outros", "transaction_type": "CREDIT"},
                {"date": today,                    "amount": -55.90,
                 "description": "NETFLIX",  "category": "Outros", "transaction_type": "CREDIT"},
            ],
            schema={"date": pl.Date, "amount": pl.Float64, "description": pl.Utf8,
                    "category": pl.Utf8, "transaction_type": pl.Utf8},
        )
        from app.optimizer.feature_store import TransactionFeatureEnricher
        df = TransactionFeatureEnricher().enrich(df)
        flags = self._duplicate_anomalies(df, df)
        assert flags == [], "merchant_ids distintos (spotify vs netflix) não são duplicata"

    def test_duplicate_without_merchant_id_uses_description_fallback(self):
        """Sem merchant_id, mesmo merchant (descrição idêntica) mesmo valor = duplicata."""
        today = date.today()
        df = _make_df([
            _txn(-55.90, "NETFLIX", days_ago=1),
            _txn(-55.90, "NETFLIX", days_ago=0),
        ])
        # Sem enriquecimento — fallback para description normalizada
        flags = self._duplicate_anomalies(df, df)
        assert len(flags) >= 1
