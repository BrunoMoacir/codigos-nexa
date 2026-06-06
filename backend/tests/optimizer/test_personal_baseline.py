# tests/optimizer/test_personal_baseline.py
# Testes dedicados para PersonalBaseline e sua integração nos detectores.

from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest

from app.optimizer.detectors.personal_baseline import PersonalBaseline, compute_personal_baseline


# ─── Helpers ─────────────────────────────────────────────────────────────────

TODAY = date(2026, 1, 15)


def _txn(
    amount: float,
    days_ago: int,
    category: str = "outros",
    description: str = "COMPRA",
    context_type: str | None = None,
) -> dict:
    row = {
        "date": TODAY - timedelta(days=days_ago),
        "amount": amount,
        "category_canonical": category,
        "description": description,
    }
    if context_type is not None:
        row["context_type"] = context_type
    return row


def _make_df(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Date))


# ═══════════════════════════════════════════════════════════════════════════
# PersonalBaseline — métodos do dataclass
# ═══════════════════════════════════════════════════════════════════════════

class TestPersonalBaselineMethods:

    def _baseline(self, cats: dict[str, float], total: float = 1000.0, months: int = 3) -> PersonalBaseline:
        return PersonalBaseline(
            category_monthly_avg=cats,
            total_monthly_avg=total,
            data_months=months,
        )

    def test_monthly_avg_returns_known_category(self):
        b = self._baseline({"farmacia": 80.0})
        assert b.monthly_avg("farmacia") == 80.0

    def test_monthly_avg_returns_zero_for_unknown(self):
        b = self._baseline({"farmacia": 80.0})
        assert b.monthly_avg("educacao") == 0.0

    def test_deviation_ratio_no_history_returns_inf(self):
        b = self._baseline({})
        assert b.deviation_ratio("farmacia", 650.0) == float("inf")

    def test_deviation_ratio_with_history(self):
        b = self._baseline({"farmacia": 80.0})
        ratio = b.deviation_ratio("farmacia", 640.0)
        assert abs(ratio - 8.0) < 0.01

    def test_deviation_ratio_unchanged_returns_one(self):
        b = self._baseline({"alimentacao": 400.0})
        assert b.deviation_ratio("alimentacao", 400.0) == pytest.approx(1.0)

    # ── adjusted_threshold ────────────────────────────────────────────────

    def test_adjusted_threshold_no_history_reduces_gate(self):
        b = self._baseline({})
        # Sem histórico: gate = default * floor_ratio = 200 * 0.5 = 100
        assert b.adjusted_threshold("educacao", default=200.0) == pytest.approx(100.0)

    def test_adjusted_threshold_small_baseline_uses_spike(self):
        # Baseline 80 → max(80*1.5, 100) = max(120, 100) = 120
        b = self._baseline({"farmacia": 80.0})
        assert b.adjusted_threshold("farmacia", default=200.0, spike_ratio=1.5) == pytest.approx(120.0)

    def test_adjusted_threshold_large_baseline_raises_gate(self):
        # Baseline 400 → max(400*1.5, 100) = max(600, 100) = 600
        b = self._baseline({"educacao": 400.0})
        assert b.adjusted_threshold("educacao", default=200.0, spike_ratio=1.5) == pytest.approx(600.0)

    def test_adjusted_threshold_floor_ratio_respected(self):
        b = self._baseline({})
        # floor_ratio=0.25 → 200 * 0.25 = 50
        assert b.adjusted_threshold("educacao", default=200.0, floor_ratio=0.25) == pytest.approx(50.0)

    # ── has_data ─────────────────────────────────────────────────────────

    def test_has_data_true_with_two_or_more_months(self):
        b = self._baseline({}, months=2)
        assert b.has_data() is True

    def test_has_data_false_with_one_month(self):
        b = self._baseline({}, months=1)
        assert b.has_data() is False

    def test_has_data_false_with_zero_months(self):
        b = self._baseline({}, months=0)
        assert b.has_data() is False


# ═══════════════════════════════════════════════════════════════════════════
# compute_personal_baseline — janelas e cálculos
# ═══════════════════════════════════════════════════════════════════════════

class TestComputePersonalBaseline:

    def test_empty_df_returns_empty_baseline(self):
        b = compute_personal_baseline(pl.DataFrame(), reference_date=TODAY)
        assert b.data_months == 0
        assert b.total_monthly_avg == 0.0

    def test_excludes_recent_90_days(self):
        # Transação 30 dias atrás deve ser EXCLUÍDA (dentro da janela recente)
        rows = [_txn(-500.0, days_ago=30, category="farmacia")]
        b = compute_personal_baseline(_make_df(rows), reference_date=TODAY)
        assert b.data_months == 0
        assert b.monthly_avg("farmacia") == 0.0

    def test_includes_transactions_91_days_ago(self):
        # 91 dias atrás = dentro da janela baseline (90–540)
        rows = [_txn(-120.0, days_ago=91, category="farmacia")]
        b = compute_personal_baseline(_make_df(rows), reference_date=TODAY)
        assert b.data_months == 1
        assert b.monthly_avg("farmacia") == pytest.approx(120.0, abs=0.5)

    def test_excludes_transactions_beyond_540_days(self):
        # 541 dias atrás = fora da janela histórica máxima
        rows = [_txn(-200.0, days_ago=541, category="farmacia")]
        b = compute_personal_baseline(_make_df(rows), reference_date=TODAY)
        assert b.data_months == 0

    def test_correct_monthly_average(self):
        # 3 meses com R$80/mês em farmácia (dias 91, 121, 151)
        rows = [
            _txn(-80.0, days_ago=91,  category="farmacia"),
            _txn(-80.0, days_ago=121, category="farmacia"),
            _txn(-80.0, days_ago=151, category="farmacia"),
        ]
        b = compute_personal_baseline(_make_df(rows), reference_date=TODAY)
        assert b.data_months == 3
        assert b.monthly_avg("farmacia") == pytest.approx(80.0, abs=1.0)

    def test_multiple_categories(self):
        rows = [
            _txn(-300.0, days_ago=100, category="alimentacao"),
            _txn(-80.0,  days_ago=100, category="farmacia"),
            _txn(-300.0, days_ago=130, category="alimentacao"),
            _txn(-80.0,  days_ago=130, category="farmacia"),
        ]
        b = compute_personal_baseline(_make_df(rows), reference_date=TODAY)
        assert b.monthly_avg("alimentacao") == pytest.approx(300.0, abs=1.0)
        assert b.monthly_avg("farmacia") == pytest.approx(80.0, abs=1.0)

    def test_excludes_pj_transactions(self):
        rows = [
            _txn(-500.0, days_ago=100, category="alimentacao", context_type="PJ"),
            _txn(-100.0, days_ago=100, category="alimentacao", context_type="PF"),
        ]
        b = compute_personal_baseline(_make_df(rows), reference_date=TODAY)
        # Somente PF entra — R$100/mês
        assert b.monthly_avg("alimentacao") == pytest.approx(100.0, abs=1.0)

    def test_ignores_credits(self):
        # Créditos (amount > 0) não entram no baseline de gastos
        rows = [
            _txn(-80.0, days_ago=100, category="farmacia"),
            _txn(+2000.0, days_ago=100, category="salario"),  # crédito
        ]
        b = compute_personal_baseline(_make_df(rows), reference_date=TODAY)
        assert b.monthly_avg("salario") == 0.0
        assert b.monthly_avg("farmacia") > 0


# ═══════════════════════════════════════════════════════════════════════════
# FamilyDetector — thresholds adaptativos
# ═══════════════════════════════════════════════════════════════════════════

class TestFamilyDetectorBaseline:

    def _expenses_df(self, rows: list[dict]) -> pl.DataFrame:
        return _make_df(rows)

    def test_established_school_no_false_positive(self):
        """Usuário que já paga escola há meses não deve ter score inflado por isso."""
        from app.optimizer.detectors.family_detector import FamilyDetector

        # Histórico: R$350/mês em escola (baseline alto → threshold 525/mês)
        b = PersonalBaseline(
            category_monthly_avg={"educacao": 350.0},
            total_monthly_avg=3000.0,
            data_months=6,
        )
        # Recente: mesma R$350/mês em escola — comportamento normal
        rows = [_txn(-350.0, days_ago=20, category="educacao", description="ESCOLA MUNICIPAL")]
        result = FamilyDetector().detect_family_profile(self._expenses_df(rows), baseline=b)

        # Threshold adaptado = max(350*1.5, 33) = 525 → 350/mês < 525 → NÃO dispara
        assert "school_spend" not in str(result["supporting_signals"])
        assert result["family_score"] < 40

    def test_new_school_triggers_with_lower_threshold(self):
        """Usuário sem histórico de escola: gate reduzido → R$100 já dispara."""
        from app.optimizer.detectors.family_detector import FamilyDetector

        b = PersonalBaseline(
            category_monthly_avg={},  # sem histórico de educação
            total_monthly_avg=2000.0,
            data_months=4,
        )
        # R$120 em escola por 1 mês → monthly = 120, threshold = 67*0.5 = 33.5
        rows = [_txn(-120.0, days_ago=15, category="educacao", description="ESCOLA MUNICIPAL")]
        result = FamilyDetector().detect_family_profile(self._expenses_df(rows), baseline=b)

        assert "school_spend" in str(result["supporting_signals"])
        assert "school_categoria_nova" in str(result["supporting_signals"])

    def test_baby_spike_adds_deviation_signal(self):
        """Farmácia 8× acima do baseline → sinal baby_vs_baseline=8.1x."""
        from app.optimizer.detectors.family_detector import FamilyDetector

        b = PersonalBaseline(
            category_monthly_avg={"farmacia": 80.0},
            total_monthly_avg=3000.0,
            data_months=6,
        )
        # R$650 em produtos bebê em 1 mês (8.1× acima de R$80 baseline)
        rows = [_txn(-650.0, days_ago=10, category="farmacia", description="PAMPERS FRALDA")]
        result = FamilyDetector().detect_family_profile(self._expenses_df(rows), baseline=b)

        signals_str = str(result["supporting_signals"])
        assert "baby_products" in signals_str
        assert "baby_vs_baseline" in signals_str

    def test_without_baseline_uses_original_thresholds(self):
        """Sem baseline: comportamento original (threshold=100 total para bebê)."""
        from app.optimizer.detectors.family_detector import FamilyDetector

        # R$150 total de bebê no período — > 100 original → deve disparar
        rows = [_txn(-150.0, days_ago=10, description="PAMPERS FRALDA")]
        result_sem = FamilyDetector().detect_family_profile(self._expenses_df(rows))

        assert "baby_products" in str(result_sem["supporting_signals"])

    def test_baby_threshold_scales_with_baseline_farmacia(self):
        """Usuário que já gasta muito em farmácia precisa de spike maior para disparar."""
        from app.optimizer.detectors.family_detector import FamilyDetector

        # Baseline farmácia = R$300/mês → threshold_baby = max(300*2.0, 16.5) = 600/mês
        b = PersonalBaseline(
            category_monthly_avg={"farmacia": 300.0},
            total_monthly_avg=4000.0,
            data_months=5,
        )
        # R$400 em produtos bebê em 1 mês — abaixo do threshold adaptado (600)
        rows = [_txn(-400.0, days_ago=10, description="PAMPERS FRALDA")]
        result = FamilyDetector().detect_family_profile(self._expenses_df(rows), baseline=b)

        assert "baby_products" not in str(result["supporting_signals"])


# ═══════════════════════════════════════════════════════════════════════════
# FoodieDetector — desvio vs baseline e fine dining adaptativo
# ═══════════════════════════════════════════════════════════════════════════

class TestFoodieDetectorBaseline:

    def _food_df(self, monthly_spend: float, months: int = 1, ticket: float | None = None) -> pl.DataFrame:
        """DataFrame com transações de restaurante para testar FoodieDetector."""
        rows = []
        for m in range(months):
            d = TODAY - timedelta(days=10 + m * 30)
            amt = -(ticket or monthly_spend)
            rows.append({
                "date": d,
                "amount": float(amt),
                "description": f"RESTAURANTE_{m}",
                "category_canonical": "alimentacao",
                "merchant_category_l1": "alimentacao",
                "merchant_category_l2": "RESTAURANTE",
                "merchant_id": f"rest_{m}",
            })
        return pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Date))

    def test_food_spike_adds_food_vs_baseline_signal(self):
        """Quando gasto em alimentação dobra vs baseline → food_vs_baseline aparece."""
        from app.optimizer.detectors.foodie_detector import FoodieDetector

        b = PersonalBaseline(
            category_monthly_avg={"alimentacao": 400.0},
            total_monthly_avg=3000.0,
            data_months=6,
        )
        df = self._food_df(monthly_spend=900.0)  # 2.25× acima do baseline
        result = FoodieDetector().calc_foodie_score(df, monthly_avg_spend=3000.0, baseline=b)

        assert "food_vs_baseline" in str(result["supporting_signals"])

    def test_food_at_baseline_no_deviation_signal(self):
        """Gasto estável em alimentação não gera sinal de desvio."""
        from app.optimizer.detectors.foodie_detector import FoodieDetector

        b = PersonalBaseline(
            category_monthly_avg={"alimentacao": 400.0},
            total_monthly_avg=3000.0,
            data_months=6,
        )
        df = self._food_df(monthly_spend=420.0)  # 1.05× — praticamente inalterado
        result = FoodieDetector().calc_foodie_score(df, monthly_avg_spend=3000.0, baseline=b)

        assert "food_vs_baseline" not in str(result["supporting_signals"])

    def test_fine_dining_threshold_lower_for_low_spend_user(self):
        """Usuário com R$1.500/mês total: threshold de fine dining cai de R$150 → ~R$75."""
        from app.optimizer.detectors.foodie_detector import FoodieDetector

        b = PersonalBaseline(
            category_monthly_avg={"alimentacao": 200.0},
            total_monthly_avg=1500.0,  # 50% do padrão → threshold fine dining ÷ 2
            data_months=4,
        )
        # Ticket médio R$90 — abaixo de R$150 (padrão) mas > R$75 (adaptado)
        df = self._food_df(monthly_spend=90.0, ticket=90.0)
        result = FoodieDetector().calc_foodie_score(df, monthly_avg_spend=1500.0, baseline=b)

        assert result["is_fine_dining"] is True

    def test_fine_dining_threshold_unchanged_without_baseline(self):
        """Sem baseline, threshold de fine dining permanece em R$150."""
        from app.optimizer.detectors.foodie_detector import FoodieDetector

        # Ticket R$90 — abaixo de R$150 → não é fine dining
        df = self._food_df(monthly_spend=90.0, ticket=90.0)
        result = FoodieDetector().calc_foodie_score(df, monthly_avg_spend=1500.0)

        assert result["is_fine_dining"] is False

    def test_baseline_bonus_up_to_10_pts(self):
        """Spike de alimentação gera bonus máximo de 10 pts para 4× acima do baseline."""
        from app.optimizer.detectors.foodie_detector import FoodieDetector

        b = PersonalBaseline(
            category_monthly_avg={"alimentacao": 200.0},
            total_monthly_avg=3000.0,
            data_months=4,
        )
        df = self._food_df(monthly_spend=1000.0)  # 5× — bonus deve ser ≈ 10 pts (cap)
        result_com = FoodieDetector().calc_foodie_score(df, monthly_avg_spend=3000.0, baseline=b)
        result_sem = FoodieDetector().calc_foodie_score(df, monthly_avg_spend=3000.0)

        bonus = result_com["foodie_score"] - result_sem["foodie_score"]
        assert bonus >= 8.0  # próximo do cap de 10 pts

    def test_new_food_category_adds_nova_signal(self):
        """Categoria de alimentação nova (sem histórico) gera sinal alimentacao_categoria_nova."""
        from app.optimizer.detectors.foodie_detector import FoodieDetector

        b = PersonalBaseline(
            category_monthly_avg={},  # sem histórico de alimentação
            total_monthly_avg=3000.0,
            data_months=4,
        )
        df = self._food_df(monthly_spend=500.0)
        result = FoodieDetector().calc_foodie_score(df, monthly_avg_spend=3000.0, baseline=b)

        assert "alimentacao_categoria_nova" in str(result["supporting_signals"])


# ═══════════════════════════════════════════════════════════════════════════
# TravelDetector — desvio vs baseline
# ═══════════════════════════════════════════════════════════════════════════

class TestTravelDetectorBaseline:

    def _travel_df(self, spend: float, months: int = 1) -> pl.DataFrame:
        rows = []
        for m in range(months):
            d = TODAY - timedelta(days=10 + m * 30)
            rows.append({
                "date": d,
                "amount": -float(spend),
                "description": "LATAM PASSAGEM",
                "is_travel_related": True,
                "is_foreign": False,
                "merchant_category_l1": "viagem",
                "merchant_category_l2": "VOO",
            })
        return pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Date))

    def test_travel_spike_adds_vs_baseline_signal(self):
        """Gasto em viagem 3× acima do baseline → travel_vs_baseline aparece."""
        from app.optimizer.detectors.travel_detector import TravelDetector

        b = PersonalBaseline(
            category_monthly_avg={"viagem": 200.0},
            total_monthly_avg=3000.0,
            data_months=6,
        )
        df = self._travel_df(spend=600.0)  # 3× acima
        result = TravelDetector().calc_travel_score(df, total_spend=3000.0, baseline=b)

        assert "travel_vs_baseline" in str(result["supporting_signals"])

    def test_travel_at_baseline_no_deviation_signal(self):
        """Gasto em viagem próximo do baseline não gera sinal de desvio."""
        from app.optimizer.detectors.travel_detector import TravelDetector

        b = PersonalBaseline(
            category_monthly_avg={"viagem": 200.0},
            total_monthly_avg=3000.0,
            data_months=6,
        )
        df = self._travel_df(spend=210.0)  # 1.05× — estável
        result = TravelDetector().calc_travel_score(df, total_spend=3000.0, baseline=b)

        assert "travel_vs_baseline" not in str(result["supporting_signals"])

    def test_no_travel_history_adds_nova_categoria_signal(self):
        """Sem histórico de viagem: qualquer gasto gera sinal de categoria nova."""
        from app.optimizer.detectors.travel_detector import TravelDetector

        b = PersonalBaseline(
            category_monthly_avg={},  # sem histórico de viagem/transporte
            total_monthly_avg=3000.0,
            data_months=4,
        )
        df = self._travel_df(spend=800.0)
        result = TravelDetector().calc_travel_score(df, total_spend=3000.0, baseline=b)

        assert "viagem_categoria_nova" in str(result["supporting_signals"])


# ═══════════════════════════════════════════════════════════════════════════
# LifeEventsDetector — level_ratio e thresholds adaptativos
# ═══════════════════════════════════════════════════════════════════════════

class TestLifeEventsDetectorBaseline:

    def _txns(self, rows: list[dict]) -> pl.DataFrame:
        schema = {"date": pl.Date, "amount": pl.Float64, "description": pl.Utf8}
        return pl.DataFrame(rows, schema=schema)

    def _empty(self) -> pl.DataFrame:
        return pl.DataFrame({"date": [], "amount": [], "description": []},
                            schema={"date": pl.Date, "amount": pl.Float64, "description": pl.Utf8})

    # ── _level_ratio ─────────────────────────────────────────────────────

    def test_level_ratio_no_baseline_returns_one(self):
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector
        det = LifeEventsDetector()
        assert det._level_ratio(None) == pytest.approx(1.0)

    def test_level_ratio_reference_3000_returns_one(self):
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector
        b = PersonalBaseline(category_monthly_avg={}, total_monthly_avg=3000.0, data_months=3)
        assert LifeEventsDetector()._level_ratio(b) == pytest.approx(1.0)

    def test_level_ratio_low_spend_below_one(self):
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector
        b = PersonalBaseline(category_monthly_avg={}, total_monthly_avg=1500.0, data_months=3)
        assert LifeEventsDetector()._level_ratio(b) == pytest.approx(0.5)

    def test_level_ratio_high_spend_capped_at_two(self):
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector
        b = PersonalBaseline(category_monthly_avg={}, total_monthly_avg=9000.0, data_months=3)
        assert LifeEventsDetector()._level_ratio(b) == pytest.approx(2.0)

    def test_level_ratio_minimum_floor_at_0_33(self):
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector
        b = PersonalBaseline(category_monthly_avg={}, total_monthly_avg=200.0, data_months=3)
        assert LifeEventsDetector()._level_ratio(b) == pytest.approx(0.33)

    # ── Evento new_baby com threshold adaptativo ──────────────────────────

    def test_baby_gate_lower_for_low_income_user(self):
        """Usuário com R$1.500/mês: gate cai de R$200 → R$100 → detecta gasto menor."""
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector

        b = PersonalBaseline(category_monthly_avg={}, total_monthly_avg=1500.0, data_months=4)
        # R$150 em fraldas: abaixo do gate fixo (200) mas acima do gate adaptado (100)
        recent = self._txns([{"date": TODAY - timedelta(days=10), "amount": -150.0, "description": "PAMPERS FRALDA"}])
        history = self._empty()

        result = LifeEventsDetector().detect_all(recent, history, 1500.0, 1500.0, baseline=b)
        assert any(e.event == "new_baby" for e in result)

    def test_baby_gate_higher_for_high_income_user(self):
        """Usuário com R$6.000/mês: gate sobe para R$400 → R$250 não dispara."""
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector

        b = PersonalBaseline(category_monthly_avg={}, total_monthly_avg=6000.0, data_months=4)
        # R$250 em fraldas — acima do gate fixo (200) mas abaixo do adaptado (400)
        recent = self._txns([{"date": TODAY - timedelta(days=10), "amount": -250.0, "description": "PAMPERS FRALDA"}])
        history = self._empty()

        result = LifeEventsDetector().detect_all(recent, history, 6000.0, 6000.0, baseline=b)
        assert not any(e.event == "new_baby" for e in result)

    def test_baby_event_includes_level_ratio_signal(self):
        """Quando baseline está presente e evento é detectado, spend_level_ratio aparece."""
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector

        b = PersonalBaseline(category_monthly_avg={}, total_monthly_avg=3000.0, data_months=4)
        recent = self._txns([
            {"date": TODAY - timedelta(days=5),  "amount": -300.0, "description": "PAMPERS FRALDA"},
            {"date": TODAY - timedelta(days=20), "amount": -250.0, "description": "HUGGIES BEBE"},
        ])
        history = self._empty()

        result = LifeEventsDetector().detect_all(recent, history, 3000.0, 3000.0, baseline=b)
        baby_events = [e for e in result if e.event == "new_baby"]
        if baby_events:
            signals = str(baby_events[0].supporting_signals)
            assert "spend_level_ratio" in signals

    def test_without_baseline_preserves_original_behavior(self):
        """Sem baseline: gate original de R$200 permanece."""
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector

        # R$150 em fraldas — abaixo do gate original de R$200 → não detecta
        recent = self._txns([{"date": TODAY - timedelta(days=10), "amount": -150.0, "description": "PAMPERS FRALDA"}])
        history = self._empty()

        result = LifeEventsDetector().detect_all(recent, history, 3000.0, 3000.0)
        assert not any(e.event == "new_baby" for e in result)
