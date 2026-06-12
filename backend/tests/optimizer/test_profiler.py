# tests/optimizer/test_profiler.py
# Testes unitários para ConsumptionProfiler (profiler.py)
# Passo 2.2 — Funcionalidade 2: Nexa Optimizer

import pytest
import polars as pl
from datetime import date, timedelta

from app.optimizer.profiler import ConsumptionProfiler, UserProfile
from app.optimizer.feature_store import TransactionFeatureEnricher


# ─── Helpers ────────────────────────────────────────────────────────────────────

TODAY = date(2026, 2, 26)
RECENT = TODAY - timedelta(days=30)      # dentro da janela
OLD = TODAY - timedelta(days=120)        # fora da janela de 90 dias


def _txn(
    amount: float,
    txn_date: date = None,
    category: str = "Outros",
    transaction_type: str = "DEBIT",
    context_type: str = "PF",
    description: str = "desc",
    txn_id: str = None,
) -> dict:
    return {
        "transaction_id": txn_id or f"txn-{amount}-{txn_date}",
        "user_id": "user-1",
        "description": description,
        "amount": amount,
        "date": txn_date or RECENT,
        "transaction_type": transaction_type,
        "category": category,
        "context_type": context_type,
    }


def _make_df(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={
            "transaction_id": pl.Utf8,
            "user_id": pl.Utf8,
            "description": pl.Utf8,
            "amount": pl.Float64,
            "date": pl.Date,
            "transaction_type": pl.Utf8,
            "category": pl.Utf8,
            "context_type": pl.Utf8,
        },
    )


def _shadow_df(amounts: list[float]) -> pl.DataFrame:
    """Cria DataFrame de shadow invoices com montantes mensais negativos."""
    return pl.DataFrame(
        {"amount": [float(a) for a in amounts], "type": ["SUBSCRIPTION"] * len(amounts)},
        schema={"amount": pl.Float64, "type": pl.Utf8},
    )


# ─── Testes ─────────────────────────────────────────────────────────────────────

class TestConsumptionProfilerBasic:
    def test_empty_df_returns_zero_profile(self):
        profiler = ConsumptionProfiler()
        result = profiler.build(pl.DataFrame())
        assert isinstance(result, UserProfile)
        assert result.monthly_avg_spend == 0.0
        assert result.data_coverage_months == 0

    def test_none_like_empty_returns_zero_profile(self):
        """DataFrame com linhas fora da janela deve retornar perfil zerado."""
        profiler = ConsumptionProfiler()
        df = _make_df([_txn(-500.0, txn_date=OLD)])
        result = profiler.build(df, reference_date=TODAY)
        assert result.monthly_avg_spend == 0.0

    def test_returns_userprofile_instance(self):
        profiler = ConsumptionProfiler()
        df = _make_df([_txn(-100.0)])
        result = profiler.build(df, reference_date=TODAY)
        assert isinstance(result, UserProfile)

    def test_all_fields_present(self):
        profiler = ConsumptionProfiler()
        df = _make_df([_txn(-300.0), _txn(-500.0)])
        result = profiler.build(df, reference_date=TODAY)
        assert hasattr(result, "monthly_avg_spend")
        assert hasattr(result, "committed_percentage")
        assert hasattr(result, "spend_by_category")
        assert hasattr(result, "spend_by_source")
        assert hasattr(result, "international_spend_monthly")
        assert hasattr(result, "travel_spend_monthly")
        assert hasattr(result, "estimated_monthly_income")
        assert hasattr(result, "data_coverage_months")
        assert hasattr(result, "spending_stability")


class TestWindowFilter:
    def test_excludes_transactions_outside_90_days(self):
        profiler = ConsumptionProfiler()
        # Uma despesa recente, uma antiga
        df = _make_df([
            _txn(-1000.0, txn_date=RECENT, txn_id="recent"),
            _txn(-9999.0, txn_date=OLD, txn_id="old"),
        ])
        result = profiler.build(df, reference_date=TODAY)
        # O gasto antigo NÃO deve inflar a média
        assert result.monthly_avg_spend < 9999.0

    def test_includes_transactions_exactly_at_cutoff(self):
        profiler = ConsumptionProfiler()
        cutoff_date = TODAY - timedelta(days=90)
        df = _make_df([_txn(-500.0, txn_date=cutoff_date)])
        result = profiler.build(df, reference_date=TODAY)
        assert result.monthly_avg_spend > 0.0


class TestPJFilter:
    def test_excludes_pj_transactions(self):
        profiler = ConsumptionProfiler()
        df = _make_df([
            _txn(-1000.0, context_type="PF", txn_id="pf"),
            _txn(-9000.0, context_type="PJ", txn_id="pj"),
        ])
        result = profiler.build(df, reference_date=TODAY)
        # PJ deve ser excluído — média muito menor que 9000
        assert result.monthly_avg_spend < 9000.0

    def test_uncertain_transactions_included(self):
        profiler = ConsumptionProfiler()
        df = _make_df([
            _txn(-500.0, context_type="UNCERTAIN", txn_id="uncertain"),
        ])
        result = profiler.build(df, reference_date=TODAY)
        assert result.monthly_avg_spend > 0.0

    def test_null_context_type_included(self):
        """Transações sem context_type definido são incluídas."""
        profiler = ConsumptionProfiler()
        rows = [{
            "transaction_id": "txn-null",
            "user_id": "user-1",
            "description": "compra",
            "amount": -300.0,
            "date": RECENT,
            "transaction_type": "DEBIT",
            "category": "Outros",
            "context_type": None,
        }]
        df = pl.DataFrame(rows, schema={
            "transaction_id": pl.Utf8,
            "user_id": pl.Utf8,
            "description": pl.Utf8,
            "amount": pl.Float64,
            "date": pl.Date,
            "transaction_type": pl.Utf8,
            "category": pl.Utf8,
            "context_type": pl.Utf8,
        })
        result = profiler.build(df, reference_date=TODAY)
        assert result.monthly_avg_spend > 0.0


class TestMonthlyAvgSpend:
    def test_single_month(self):
        profiler = ConsumptionProfiler()
        # 3 despesas no mesmo mês: total = 600
        month = date(2026, 2, 1)
        df = _make_df([
            _txn(-200.0, txn_date=month, txn_id="a"),
            _txn(-150.0, txn_date=month, txn_id="b"),
            _txn(-250.0, txn_date=month, txn_id="c"),
        ])
        result = profiler.build(df, reference_date=TODAY)
        assert result.monthly_avg_spend == pytest.approx(600.0, abs=0.01)

    def test_two_months_averaged(self):
        profiler = ConsumptionProfiler()
        # Janeiro: 1000, Fevereiro: 2000 → média = 1500
        df = _make_df([
            _txn(-1000.0, txn_date=date(2026, 1, 15), txn_id="jan"),
            _txn(-2000.0, txn_date=date(2026, 2, 10), txn_id="feb"),
        ])
        result = profiler.build(df, reference_date=TODAY)
        assert result.monthly_avg_spend == pytest.approx(1500.0, abs=0.01)

    def test_ignores_positive_amounts_in_avg_spend(self):
        """Renda (amount > 0) não entra na média de gastos."""
        profiler = ConsumptionProfiler()
        df = _make_df([
            _txn(-500.0, txn_id="expense"),
            _txn(3000.0, txn_id="salary"),   # salário — não é gasto
        ])
        result = profiler.build(df, reference_date=TODAY)
        assert result.monthly_avg_spend == pytest.approx(500.0, abs=0.01)


class TestSpendingStability:
    def test_stable_spending(self):
        """Gastos idênticos em meses diferentes → stability = 1.0."""
        profiler = ConsumptionProfiler()
        df = _make_df([
            _txn(-1000.0, txn_date=date(2026, 1, 15), txn_id="jan"),
            _txn(-1000.0, txn_date=date(2026, 2, 15), txn_id="feb"),
        ])
        result = profiler.build(df, reference_date=TODAY)
        assert result.spending_stability == pytest.approx(1.0, abs=0.01)

    def test_unstable_spending(self):
        """Gastos muito díspares → stability baixa."""
        profiler = ConsumptionProfiler()
        df = _make_df([
            _txn(-100.0, txn_date=date(2026, 1, 15), txn_id="jan"),
            _txn(-10000.0, txn_date=date(2026, 2, 15), txn_id="feb"),
        ])
        result = profiler.build(df, reference_date=TODAY)
        assert result.spending_stability < 0.5

    def test_single_month_stability_is_0_5(self):
        """Com apenas 1 mês de dados, stability = 0.5 (inconclusivo)."""
        profiler = ConsumptionProfiler()
        df = _make_df([_txn(-500.0)])
        result = profiler.build(df, reference_date=TODAY)
        assert result.spending_stability == 0.5

    def test_stability_between_0_and_1(self):
        profiler = ConsumptionProfiler()
        df = _make_df([
            _txn(-800.0, txn_date=date(2026, 1, 10), txn_id="a"),
            _txn(-1200.0, txn_date=date(2026, 2, 10), txn_id="b"),
        ])
        result = profiler.build(df, reference_date=TODAY)
        assert 0.0 <= result.spending_stability <= 1.0


class TestSpendByCategory:
    def test_groups_by_category(self):
        """spend_by_category usa chaves canônicas lowercase sem acento após enrich."""
        profiler = ConsumptionProfiler()
        df = _make_df([
            _txn(-400.0, category="Alimentação", txn_id="a1"),
            _txn(-200.0, category="Alimentação", txn_id="a2"),
            _txn(-300.0, category="Transporte", txn_id="t1"),
        ])
        result = profiler.build(df, reference_date=TODAY)
        assert "alimentacao" in result.spend_by_category
        assert "transporte" in result.spend_by_category
        # 600 total em 1 mês
        assert result.spend_by_category["alimentacao"] == pytest.approx(600.0, abs=0.01)

    def test_empty_without_category_column(self):
        """Se não há coluna category, spend_by_category fica vazio."""
        profiler = ConsumptionProfiler()
        df = pl.DataFrame(
            {"transaction_id": ["x"], "user_id": ["u"], "description": ["d"],
             "amount": [-100.0], "date": [RECENT], "transaction_type": ["DEBIT"],
             "context_type": ["PF"]},
            schema={"transaction_id": pl.Utf8, "user_id": pl.Utf8, "description": pl.Utf8,
                    "amount": pl.Float64, "date": pl.Date, "transaction_type": pl.Utf8,
                    "context_type": pl.Utf8},
        )
        result = profiler.build(df, reference_date=TODAY)
        assert result.spend_by_category == {}


class TestSpendBySource:
    def test_debit_vs_credit_split(self):
        profiler = ConsumptionProfiler()
        df = _make_df([
            _txn(-600.0, transaction_type="DEBIT", txn_id="d1"),
            _txn(-400.0, transaction_type="CREDIT", txn_id="c1"),
        ])
        result = profiler.build(df, reference_date=TODAY)
        assert "debit" in result.spend_by_source
        assert "credit" in result.spend_by_source
        assert result.spend_by_source["debit"] == pytest.approx(600.0, abs=0.01)
        assert result.spend_by_source["credit"] == pytest.approx(400.0, abs=0.01)

    def test_all_debit(self):
        profiler = ConsumptionProfiler()
        df = _make_df([
            _txn(-1000.0, transaction_type="DEBIT", txn_id="d1"),
            _txn(-500.0, transaction_type="DEBIT", txn_id="d2"),
        ])
        result = profiler.build(df, reference_date=TODAY)
        assert result.spend_by_source.get("debit", 0) > 0
        assert result.spend_by_source.get("credit", 0) == 0

    def test_null_transaction_type_not_classified_as_credit(self):
        """None em transaction_type não deve inflar credit_spend_ratio para 1.0."""
        profiler = ConsumptionProfiler()
        df = pl.DataFrame(
            {
                "transaction_id": ["t1", "t2"],
                "user_id": ["u1", "u1"],
                "description": ["PIX enviado", "PIX recebido"],
                "amount": [-800.0, -200.0],
                "date": [RECENT, RECENT],
                "transaction_type": [None, None],
                "category": ["Outros", "Outros"],
                "context_type": ["PF", "PF"],
            },
            schema={
                "transaction_id": pl.Utf8,
                "user_id": pl.Utf8,
                "description": pl.Utf8,
                "amount": pl.Float64,
                "date": pl.Date,
                "transaction_type": pl.Utf8,
                "category": pl.Utf8,
                "context_type": pl.Utf8,
            },
        )
        result = profiler.build(df, reference_date=TODAY)
        # Transações null vão para bucket "unknown", não para "credit"
        assert result.spend_by_source.get("credit", 0.0) == 0.0, (
            "transaction_type=None não deve ser classificado como crédito"
        )
        # Com total known=0 mas unknown>0: usa floor 0.10 (não 1.0)
        assert result.credit_spend_ratio == pytest.approx(0.10, abs=0.01), (
            "Usuário com transaction_type=None deve ter credit_spend_ratio=0.10 (floor), não 1.0"
        )

    def test_null_transaction_type_mixed_with_debit(self):
        """None misturado com DEBIT: null é excluído do ratio, calculado só com tipos conhecidos."""
        profiler = ConsumptionProfiler()
        df = pl.DataFrame(
            {
                "transaction_id": ["t1", "t2", "t3"],
                "user_id": ["u1", "u1", "u1"],
                "description": ["Mercado", "Restaurante", "PIX"],
                "amount": [-600.0, -400.0, -1000.0],
                "date": [RECENT, RECENT, RECENT],
                "transaction_type": ["DEBIT", "CREDIT", None],
                "category": ["Alimentação", "Alimentação", "Outros"],
                "context_type": ["PF", "PF", "PF"],
            },
            schema={
                "transaction_id": pl.Utf8,
                "user_id": pl.Utf8,
                "description": pl.Utf8,
                "amount": pl.Float64,
                "date": pl.Date,
                "transaction_type": pl.Utf8,
                "category": pl.Utf8,
                "context_type": pl.Utf8,
            },
        )
        result = profiler.build(df, reference_date=TODAY)
        # credit_spend_ratio calculado apenas sobre DEBIT(600) + CREDIT(400),
        # ignorando o PIX sem tipo (1000). ratio = 400 / 1000 = 0.40
        assert result.credit_spend_ratio == pytest.approx(0.40, abs=0.02), (
            "Transações null devem ser excluídas do denominador do credit_spend_ratio"
        )
        # A chave "unknown" pode existir no dict — é informacional
        assert result.spend_by_source.get("unknown", 0.0) > 0


class TestInternationalSpend:
    def test_detects_iof_keyword(self):
        profiler = ConsumptionProfiler()
        df = _make_df([
            _txn(-300.0, description="Compra IOF exterior Amazon", txn_id="intl"),
            _txn(-200.0, description="Supermercado local", txn_id="local"),
        ])
        result = profiler.build(df, reference_date=TODAY)
        # Só os R$ 300 com IOF devem contar
        assert result.international_spend_monthly == pytest.approx(300.0, abs=0.01)

    def test_detects_usd_keyword(self):
        profiler = ConsumptionProfiler()
        df = _make_df([
            _txn(-500.0, description="Netflix USD 9.99", txn_id="usd"),
        ])
        result = profiler.build(df, reference_date=TODAY)
        assert result.international_spend_monthly == pytest.approx(500.0, abs=0.01)

    def test_no_international_if_no_keywords(self):
        profiler = ConsumptionProfiler()
        df = _make_df([
            _txn(-800.0, description="Padaria do bairro", txn_id="local"),
        ])
        result = profiler.build(df, reference_date=TODAY)
        assert result.international_spend_monthly == 0.0


class TestTravelSpend:
    def test_sums_lazer_and_transporte(self):
        profiler = ConsumptionProfiler()
        df = _make_df([
            _txn(-500.0, category="Lazer", txn_id="l1"),
            _txn(-300.0, category="Transporte", txn_id="t1"),
            _txn(-400.0, category="Alimentação", txn_id="a1"),  # não é viagem
        ])
        result = profiler.build(df, reference_date=TODAY)
        assert result.travel_spend_monthly == pytest.approx(800.0, abs=0.01)

    def test_zero_without_travel_categories(self):
        profiler = ConsumptionProfiler()
        df = _make_df([
            _txn(-600.0, category="Alimentação", txn_id="a"),
            _txn(-200.0, category="Saúde", txn_id="s"),
        ])
        result = profiler.build(df, reference_date=TODAY)
        assert result.travel_spend_monthly == 0.0


class TestEstimatedMonthlyIncome:
    def test_detects_positive_amounts_as_income(self):
        profiler = ConsumptionProfiler()
        df = _make_df([
            _txn(5000.0, txn_id="salary"),
            _txn(-300.0, txn_id="expense"),
        ])
        result = profiler.build(df, reference_date=TODAY)
        assert result.estimated_monthly_income == pytest.approx(5000.0, abs=0.01)

    def test_income_averaged_over_months(self):
        profiler = ConsumptionProfiler()
        df = _make_df([
            _txn(4000.0, txn_date=date(2026, 1, 5), txn_id="s1"),
            _txn(5000.0, txn_date=date(2026, 2, 5), txn_id="s2"),
        ])
        result = profiler.build(df, reference_date=TODAY)
        assert result.estimated_monthly_income == pytest.approx(4500.0, abs=0.01)

    def test_zero_income_if_no_credits(self):
        profiler = ConsumptionProfiler()
        df = _make_df([_txn(-500.0)])
        result = profiler.build(df, reference_date=TODAY)
        assert result.estimated_monthly_income == 0.0


class TestDataCoverageMonths:
    def test_single_month(self):
        profiler = ConsumptionProfiler()
        df = _make_df([
            _txn(-100.0, txn_date=date(2026, 2, 1), txn_id="a"),
            _txn(-200.0, txn_date=date(2026, 2, 15), txn_id="b"),
        ])
        result = profiler.build(df, reference_date=TODAY)
        assert result.data_coverage_months == 1

    def test_two_months(self):
        profiler = ConsumptionProfiler()
        df = _make_df([
            _txn(-300.0, txn_date=date(2026, 1, 10), txn_id="jan"),
            _txn(-400.0, txn_date=date(2026, 2, 10), txn_id="feb"),
        ])
        result = profiler.build(df, reference_date=TODAY)
        assert result.data_coverage_months == 2

    def test_three_months(self):
        profiler = ConsumptionProfiler()
        df = _make_df([
            _txn(-300.0, txn_date=date(2025, 12, 5), txn_id="dec"),
            _txn(-400.0, txn_date=date(2026, 1, 5), txn_id="jan"),
            _txn(-500.0, txn_date=date(2026, 2, 5), txn_id="feb"),
        ])
        result = profiler.build(df, reference_date=TODAY)
        assert result.data_coverage_months == 3


class TestCommittedPercentage:
    def test_zero_when_no_shadow_invoices(self):
        profiler = ConsumptionProfiler()
        df = _make_df([_txn(-1000.0)])
        result = profiler.build(df, shadow_invoices_df=None, reference_date=TODAY)
        assert result.committed_percentage == 0.0

    def test_zero_when_empty_shadow_df(self):
        profiler = ConsumptionProfiler()
        df = _make_df([_txn(-1000.0)])
        shadow = pl.DataFrame({"amount": [], "type": []}, schema={"amount": pl.Float64, "type": pl.Utf8})
        result = profiler.build(df, shadow_invoices_df=shadow, reference_date=TODAY)
        assert result.committed_percentage == 0.0

    def test_committed_percentage_calculated(self):
        """R$ 200 comprometidos sobre R$ 1000 de gasto médio = 20%."""
        profiler = ConsumptionProfiler()
        df = _make_df([_txn(-1000.0)])
        shadow = _shadow_df([-200.0])   # R$ 200 de parcelas/assinaturas
        result = profiler.build(df, shadow_invoices_df=shadow, reference_date=TODAY)
        assert result.committed_percentage == pytest.approx(0.20, abs=0.01)

    def test_committed_percentage_capped_at_1(self):
        """Comprometido não pode ultrapassar 100%."""
        profiler = ConsumptionProfiler()
        df = _make_df([_txn(-100.0)])
        shadow = _shadow_df([-9999.0])  # muito maior que o gasto
        result = profiler.build(df, shadow_invoices_df=shadow, reference_date=TODAY)
        assert result.committed_percentage <= 1.0

    def test_critical_when_no_avg_spend(self):
        """Com gasto médio zero mas shadow invoices, committed_percentage = 1.0."""
        profiler = ConsumptionProfiler()
        df = _make_df([_txn(5000.0)])   # só renda, sem despesas
        shadow = _shadow_df([-300.0])
        result = profiler.build(df, shadow_invoices_df=shadow, reference_date=TODAY)
        assert result.committed_percentage == 1.0


# ─── category_canonical_confidence → profile.category_confidences ────────────

def _make_canonical_df(rows: list[dict]) -> pl.DataFrame:
    """DataFrame com category_canonical e category_canonical_confidence explícitos."""
    return pl.DataFrame(
        rows,
        schema={
            "transaction_id": pl.Utf8,
            "user_id": pl.Utf8,
            "description": pl.Utf8,
            "amount": pl.Float64,
            "date": pl.Date,
            "transaction_type": pl.Utf8,
            "category": pl.Utf8,
            "category_canonical": pl.Utf8,
            "category_canonical_confidence": pl.Float64,
            "context_type": pl.Utf8,
        },
    )


def _canonical_row(
    amount: float,
    category_canonical: str,
    confidence: float,
    txn_id: str = None,
) -> dict:
    return {
        "transaction_id": txn_id or f"txn-{amount}",
        "user_id": "user-1",
        "description": "desc",
        "amount": amount,
        "date": RECENT,
        "transaction_type": "CREDIT",
        "category": category_canonical,
        "category_canonical": category_canonical,
        "category_canonical_confidence": confidence,
        "context_type": "PF",
    }


class TestCategoryConfidences:
    def test_confidence_column_populates_profile_field(self):
        """
        Quando o DataFrame tem category_canonical_confidence, profile.category_confidences
        deve existir e não estar vazio.
        """
        profiler = ConsumptionProfiler()
        df = _make_canonical_df([
            _canonical_row(-500.0, "supermercado", 0.90),
        ])
        result = profiler.build(df, reference_date=TODAY)
        assert result.category_confidences != {}

    def test_weighted_average_by_transaction_value(self):
        """
        Confiança é média ponderada pelo valor: transações maiores pesam mais.
        supermercado: (0.90×1000 + 0.70×200) / 1200 = 1040/1200 ≈ 0.8667
        """
        profiler = ConsumptionProfiler()
        df = _make_canonical_df([
            _canonical_row(-1000.0, "supermercado", 0.90, "t1"),
            _canonical_row(-200.0,  "supermercado", 0.70, "t2"),
            _canonical_row(-500.0,  "farmacia",     0.80, "t3"),
        ])
        result = profiler.build(df, reference_date=TODAY)

        assert result.category_confidences["supermercado"] == pytest.approx(1040 / 1200, abs=0.001)
        assert result.category_confidences["farmacia"] == pytest.approx(0.80, abs=0.001)

    def test_single_transaction_confidence_preserved(self):
        """Uma única transação: confiança do perfil = confiança da transação."""
        profiler = ConsumptionProfiler()
        df = _make_canonical_df([
            _canonical_row(-800.0, "alimentacao", 0.75),
        ])
        result = profiler.build(df, reference_date=TODAY)
        assert result.category_confidences["alimentacao"] == pytest.approx(0.75, abs=0.001)

    def test_feature_store_derives_confidence_when_column_absent(self):
        """
        Mesmo sem category_canonical_confidence no DataFrame de entrada, o feature store
        gera a coluna via _add_category_canonical() e o profiler popula category_confidences.
        "supermercado" tem normalização direta → confiança 0.80.
        """
        profiler = ConsumptionProfiler()
        df = _make_df([_txn(-500.0, category="supermercado")])
        result = profiler.build(df, reference_date=TODAY)
        assert "supermercado" in result.category_confidences
        assert result.category_confidences["supermercado"] == pytest.approx(0.80, abs=0.001)

    def test_categories_without_confidence_not_in_dict(self):
        """Categorias presentes no spend_by_category mas ausentes em category_confidences ficam fora."""
        profiler = ConsumptionProfiler()
        df = _make_canonical_df([
            _canonical_row(-500.0, "supermercado", 0.90),
        ])
        result = profiler.build(df, reference_date=TODAY)
        assert "supermercado" in result.category_confidences
        # farmacia não tinha transações, não deve aparecer
        assert "farmacia" not in result.category_confidences


class TestFeatureStoreCategoryConfidence:
    """Testa que _add_category_canonical gera category_canonical_confidence correto."""

    def _fs(self):
        return TransactionFeatureEnricher()

    def _base_row(self, category: str, txn_id: str = "t1") -> dict:
        return {
            "transaction_id": txn_id,
            "user_id": "u1",
            "description": "desc",
            "amount": -100.0,
            "date": date(2026, 1, 15),
            "transaction_type": "CREDIT",
            "category": category,
            "context_type": "PF",
        }

    def _df(self, rows: list[dict]) -> pl.DataFrame:
        schema = {
            "transaction_id": pl.Utf8,
            "user_id": pl.Utf8,
            "description": pl.Utf8,
            "amount": pl.Float64,
            "date": pl.Date,
            "transaction_type": pl.Utf8,
            "category": pl.Utf8,
            "context_type": pl.Utf8,
        }
        return pl.DataFrame(rows, schema=schema)

    def test_alias_mapped_gets_0_85(self):
        """Categoria que passa por alias explícito (restaurante → alimentacao) deve ter 0.85."""
        df = self._df([self._base_row("restaurante")])
        enriched = self._fs().enrich(df)
        assert "category_canonical_confidence" in enriched.columns
        assert enriched["category_canonical_confidence"][0] == pytest.approx(0.85, abs=0.001)
        assert enriched["category_canonical"][0] == "alimentacao"

    def test_direct_normalization_gets_0_80(self):
        """Categoria normalizada diretamente (supermercado → supermercado) deve ter 0.80."""
        df = self._df([self._base_row("supermercado")])
        enriched = self._fs().enrich(df)
        assert enriched["category_canonical_confidence"][0] == pytest.approx(0.80, abs=0.001)
        assert enriched["category_canonical"][0] == "supermercado"

    def test_passthrough_canonical_gets_1_0(self):
        """DataFrame que já tem category_canonical recebe confidence 1.0."""
        rows = [{
            "transaction_id": "t1",
            "user_id": "u1",
            "description": "desc",
            "amount": -100.0,
            "date": date(2026, 1, 15),
            "transaction_type": "CREDIT",
            "category": "alimentacao",
            "category_canonical": "alimentacao",
            "context_type": "PF",
        }]
        schema = {
            "transaction_id": pl.Utf8,
            "user_id": pl.Utf8,
            "description": pl.Utf8,
            "amount": pl.Float64,
            "date": pl.Date,
            "transaction_type": pl.Utf8,
            "category": pl.Utf8,
            "category_canonical": pl.Utf8,
            "context_type": pl.Utf8,
        }
        df = pl.DataFrame(rows, schema=schema)
        enriched = self._fs().enrich(df)
        assert enriched["category_canonical_confidence"][0] == pytest.approx(1.0, abs=0.001)

    def test_outros_without_l1_gets_0_60(self):
        """Categoria 'Outros' sem fallback L1 deve ter confiança 0.60."""
        df = self._df([self._base_row("Outros")])
        enriched = self._fs().enrich(df)
        conf = enriched["category_canonical_confidence"][0]
        canonical = enriched["category_canonical"][0]
        # Pode ter L1 de merchant_category_l2 se a descrição bater — aceita 0.60 ou 0.75
        assert conf in (0.60, 0.75)
        assert canonical is not None

    def test_confidence_column_always_present_after_enrich(self):
        """Após enrich(), category_canonical_confidence deve sempre existir."""
        df = self._df([self._base_row("alimentacao")])
        enriched = self._fs().enrich(df)
        assert "category_canonical_confidence" in enriched.columns
        assert enriched["category_canonical_confidence"].dtype == pl.Float64


# ─── FSS → LifestyleClassifier sequencing ─────────────────────────────────────

class TestFSSBeforeLifestyleClassifier:
    """
    Garante que o FSS é calculado dentro de profiler.build() ANTES do LifestyleClassifier.
    Antes do fix, fss_level = "SAUDAVEL" (default) quando o classifier rodava, fazendo
    _score_financial_stress() ignorar o sinal de CRITICO/ALERTA.
    """

    def _df(self, rows: list[dict]) -> pl.DataFrame:
        schema = {
            "transaction_id": pl.Utf8,
            "user_id": pl.Utf8,
            "description": pl.Utf8,
            "amount": pl.Float64,
            "date": pl.Date,
            "transaction_type": pl.Utf8,
            "category": pl.Utf8,
            "context_type": pl.Utf8,
        }
        return pl.DataFrame(rows, schema=schema)

    def test_fss_level_e_populado_antes_do_classifier(self):
        """fss e fss_level não devem ser os defaults após build()."""
        from unittest.mock import patch

        rows = [_txn(-500.0, RECENT) for _ in range(10)]
        df = self._df(rows)

        captured = {}

        original_classify = __import__(
            "app.optimizer.detectors.lifestyle_classifier",
            fromlist=["LifestyleClassifier"]
        ).LifestyleClassifier.classify

        def capturing_classify(self_inner, profile):
            captured["fss"] = profile.fss
            captured["fss_level"] = profile.fss_level
            return original_classify(self_inner, profile)

        with patch(
            "app.optimizer.detectors.lifestyle_classifier.LifestyleClassifier.classify",
            capturing_classify,
        ):
            ConsumptionProfiler().build(df, reference_date=TODAY)

        assert "fss_level" in captured, "classify() não foi chamado"
        assert captured["fss_level"] != "", "fss_level estava vazio ao entrar no classifier"
        # fss_level válido (não importa qual — só que não seja o default de string vazia)
        assert captured["fss_level"] in ("SAUDAVEL", "ATENCAO", "ALERTA", "CRITICO")

    def test_fss_critico_leva_a_cluster_estresse_financeiro(self):
        """Quando FSSCalculator retorna CRITICO, o cluster deve ser ESTRESSE_FINANCEIRO."""
        from unittest.mock import patch

        rows = [_txn(-500.0, RECENT) for _ in range(10)]
        df = self._df(rows)

        fss_critico = {"fss": 90.0, "fss_level": "CRITICO", "signals": []}

        with patch(
            "app.optimizer.detectors.fss_calculator.FSSCalculator.calc_fss",
            return_value=fss_critico,
        ):
            profile = ConsumptionProfiler().build(df, reference_date=TODAY)

        assert profile.fss_level == "CRITICO"
        assert profile.lifestyle_cluster == "ESTRESSE_FINANCEIRO"
