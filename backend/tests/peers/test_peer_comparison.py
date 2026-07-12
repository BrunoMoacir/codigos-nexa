# tests/peers/test_peer_comparison.py
# Testes para MX.4 — Comparação Anônima com Perfis Similares

import pytest
from unittest.mock import MagicMock

from app.peers.peer_comparison import (
    PeerComparator,
    PeerComparisonReport,
    CategoryComparison,
    _BENCHMARKS,
    _DELTA_THRESHOLD,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FIXTURE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def cmp():
    return PeerComparator()


def _media_spending():
    """Gastos na média exata do bracket MEDIA (R$5000/mês)."""
    income = 5_000.0
    benchmarks = _BENCHMARKS["MEDIA"]
    return income, {
        cat: benchmarks[cat] * income
        for cat in benchmarks
        if cat != "poupanca"
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# _get_bracket
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestGetBracket:
    def test_baixa_boundary(self, cmp):
        assert cmp._get_bracket(1_000) == "BAIXA"
        assert cmp._get_bracket(3_000) == "BAIXA"

    def test_media_boundary(self, cmp):
        assert cmp._get_bracket(3_001) == "MEDIA"
        assert cmp._get_bracket(8_000) == "MEDIA"

    def test_alta_boundary(self, cmp):
        assert cmp._get_bracket(8_001) == "ALTA"
        assert cmp._get_bracket(20_000) == "ALTA"

    def test_premium_boundary(self, cmp):
        assert cmp._get_bracket(20_001) == "PREMIUM"
        assert cmp._get_bracket(100_000) == "PREMIUM"

    def test_typical_values(self, cmp):
        assert cmp._get_bracket(2_500) == "BAIXA"
        assert cmp._get_bracket(5_000) == "MEDIA"
        assert cmp._get_bracket(15_000) == "ALTA"
        assert cmp._get_bracket(30_000) == "PREMIUM"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# _normalize_category
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestNormalizeCategory:
    def test_aliases_moradia(self, cmp):
        assert cmp._normalize_category("habitacao") == "moradia"
        assert cmp._normalize_category("aluguel") == "moradia"

    def test_aliases_alimentacao(self, cmp):
        assert cmp._normalize_category("supermercado") == "alimentacao"
        assert cmp._normalize_category("mercado") == "alimentacao"

    def test_aliases_transporte(self, cmp):
        assert cmp._normalize_category("uber") == "transporte"
        assert cmp._normalize_category("combustivel") == "transporte"
        assert cmp._normalize_category("onibus") == "transporte"

    def test_aliases_saude(self, cmp):
        assert cmp._normalize_category("farmacia") == "saude"
        assert cmp._normalize_category("medico") == "saude"
        assert cmp._normalize_category("plano_de_saude") == "saude"

    def test_aliases_lazer(self, cmp):
        assert cmp._normalize_category("entretenimento") == "lazer"
        assert cmp._normalize_category("streaming") == "lazer"
        assert cmp._normalize_category("restaurante") == "lazer"
        assert cmp._normalize_category("delivery") == "lazer"

    def test_aliases_vestuario(self, cmp):
        assert cmp._normalize_category("roupas") == "vestuario"
        assert cmp._normalize_category("moda") == "vestuario"

    def test_unknown_passthrough(self, cmp):
        assert cmp._normalize_category("moradia") == "moradia"
        assert cmp._normalize_category("alimentacao") == "alimentacao"

    def test_case_insensitive(self, cmp):
        assert cmp._normalize_category("UBER") == "transporte"
        assert cmp._normalize_category("Farmacia") == "saude"

    def test_truly_unknown_returns_key(self, cmp):
        assert cmp._normalize_category("pet_shop") == "pet_shop"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# _savings_percentile_label
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestSavingsPercentile:
    # ratio = user/bench. Usa valores que resultam claramente acima/abaixo dos limiares
    # para evitar imprecisões de ponto flutuante (ex: 0.30/0.20 = 1.4999... em CPython).

    def test_top10_above_1_5x(self, cmp):
        # ratio = 0.32/0.20 = 1.6  ≥ 1.5 → top 10%
        assert cmp._savings_percentile_label(0.32, 0.20) == "top 10%"

    def test_top25_at_1_2x(self, cmp):
        # ratio = 0.25/0.20 = 1.25  ≥ 1.2 e < 1.5 → top 25%
        assert cmp._savings_percentile_label(0.25, 0.20) == "top 25%"

    def test_top40_at_1x(self, cmp):
        # ratio = 0.20/0.20 = 1.0  ≥ 1.0 e < 1.2 → top 40%
        assert cmp._savings_percentile_label(0.20, 0.20) == "top 40%"

    def test_metade_inferior_below_1x(self, cmp):
        # ratio = 0.17/0.20 = 0.85  ≥ 0.8 e < 1.0 → metade inferior
        assert cmp._savings_percentile_label(0.17, 0.20) == "metade inferior"

    def test_30_inferiores_at_0_5x(self, cmp):
        # ratio = 0.10/0.20 = 0.5  ≥ 0.5 e < 0.8 → 30% inferiores
        assert cmp._savings_percentile_label(0.10, 0.20) == "30% inferiores"

    def test_10_inferiores_below_0_5x(self, cmp):
        assert cmp._savings_percentile_label(0.05, 0.20) == "10% inferiores"

    def test_zero_benchmark_returns_top50(self, cmp):
        assert cmp._savings_percentile_label(0.10, 0.0) == "top 50%"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# compare() — validações básicas
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCompareBasic:
    def test_raises_on_zero_income(self, cmp):
        with pytest.raises(ValueError):
            cmp.compare(monthly_income=0, category_spending={})

    def test_raises_on_negative_income(self, cmp):
        with pytest.raises(ValueError):
            cmp.compare(monthly_income=-1000, category_spending={})

    def test_returns_report_type(self, cmp):
        report = cmp.compare(5_000, {"moradia": 1_500})
        assert isinstance(report, PeerComparisonReport)

    def test_report_has_9_categories(self, cmp):
        """Deve ter 8 gastos + poupança = 9 categorias."""
        report = cmp.compare(5_000, {})
        assert len(report.categories) == 9

    def test_empty_spending_produces_valid_report(self, cmp):
        report = cmp.compare(5_000, {})
        assert report.income_bracket == "MEDIA"
        assert report.monthly_income == 5_000
        # Com gasto zero, poupança = 100% da renda
        assert report.user_savings_rate == pytest.approx(1.0, abs=0.01)

    def test_income_bracket_assignment(self, cmp):
        assert cmp.compare(2_000, {}).income_bracket == "BAIXA"
        assert cmp.compare(5_000, {}).income_bracket == "MEDIA"
        assert cmp.compare(12_000, {}).income_bracket == "ALTA"
        assert cmp.compare(25_000, {}).income_bracket == "PREMIUM"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# compare() — cálculo de poupança
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestSavingsCalculation:
    def test_savings_calculated_as_residual(self, cmp):
        """Sem savings_amount, poupança = renda - gastos."""
        income = 5_000.0
        spending = {"moradia": 1_500, "alimentacao": 900}
        report = cmp.compare(income, spending)
        expected_savings = income - 1_500 - 900
        expected_rate = expected_savings / income
        assert report.user_savings_rate == pytest.approx(expected_rate, abs=0.01)

    def test_explicit_savings_overrides_residual(self, cmp):
        income = 5_000.0
        report = cmp.compare(income, {"moradia": 4_000}, savings_amount=500.0)
        assert report.user_savings_rate == pytest.approx(0.10, abs=0.01)

    def test_negative_residual_clamps_to_zero(self, cmp):
        """Gastos > renda: poupança deve ser 0, não negativa."""
        report = cmp.compare(5_000, {"moradia": 6_000})
        assert report.user_savings_rate == pytest.approx(0.0, abs=0.01)

    def test_poupanca_category_in_report(self, cmp):
        report = cmp.compare(5_000, {"moradia": 1_500})
        cats = {c.category for c in report.categories}
        assert "poupanca" in cats


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# compare() — classificação acima/na_media/abaixo
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCategoryStatus:
    def _moradia_status(self, cmp, income, spending_moradia):
        report = cmp.compare(income, {"moradia": spending_moradia})
        return next(c for c in report.categories if c.category == "moradia")

    def test_acima_when_delta_exceeds_threshold(self, cmp):
        # MEDIA benchmark moradia = 30% → gasto 40% = +10 p.p. (acima de 3 p.p.)
        comp = self._moradia_status(cmp, 5_000, 2_000)  # 40% de 5000
        assert comp.status == "acima"
        assert comp.delta_pct == pytest.approx(0.10, abs=0.01)

    def test_abaixo_when_delta_below_threshold(self, cmp):
        # MEDIA benchmark moradia = 30% → gasto 10% = -20 p.p.
        comp = self._moradia_status(cmp, 5_000, 500)  # 10% de 5000
        assert comp.status == "abaixo"
        assert comp.delta_pct < -_DELTA_THRESHOLD

    def test_na_media_within_threshold(self, cmp):
        # MEDIA benchmark moradia = 30% → gasto exato = na_media
        comp = self._moradia_status(cmp, 5_000, 1_500)  # 30% de 5000
        assert comp.status == "na_media"
        assert abs(comp.delta_pct) <= _DELTA_THRESHOLD

    def test_user_pct_matches_spending_over_income(self, cmp):
        income = 8_000.0
        comp = self._moradia_status(cmp, income, 2_000)
        assert comp.user_pct == pytest.approx(2_000 / 8_000, abs=0.001)
        assert comp.user_amount_brl == pytest.approx(2_000.0, abs=0.01)

    def test_benchmark_amount_brl_correct(self, cmp):
        income = 5_000.0
        bench_pct = _BENCHMARKS["MEDIA"]["moradia"]  # 0.30
        report = cmp.compare(income, {})
        moradia = next(c for c in report.categories if c.category == "moradia")
        assert moradia.benchmark_amount_brl == pytest.approx(bench_pct * income, abs=0.01)
        assert moradia.benchmark_pct == pytest.approx(bench_pct, abs=0.001)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# compare() — normalização de categorias e "outros"
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCategoryNormalization:
    def test_alias_mapped_correctly(self, cmp):
        """'uber' deve ser normalizado para 'transporte'."""
        income = 5_000.0
        report_alias = cmp.compare(income, {"uber": 500})
        report_canon = cmp.compare(income, {"transporte": 500})
        transp_alias = next(c for c in report_alias.categories if c.category == "transporte")
        transp_canon = next(c for c in report_canon.categories if c.category == "transporte")
        assert transp_alias.user_amount_brl == pytest.approx(transp_canon.user_amount_brl, abs=0.01)

    def test_unknown_category_goes_to_outros(self, cmp):
        income = 5_000.0
        report = cmp.compare(income, {"pet_shop": 300, "brinquedos": 200})
        outros = next(c for c in report.categories if c.category == "outros")
        assert outros.user_amount_brl == pytest.approx(500.0, abs=0.01)

    def test_negative_amounts_treated_as_abs(self, cmp):
        """Valores negativos (estilo transações) devem ser absolutos."""
        income = 5_000.0
        report_neg = cmp.compare(income, {"moradia": -1_500})
        report_pos = cmp.compare(income, {"moradia": 1_500})
        moradia_neg = next(c for c in report_neg.categories if c.category == "moradia")
        moradia_pos = next(c for c in report_pos.categories if c.category == "moradia")
        assert moradia_neg.user_amount_brl == pytest.approx(moradia_pos.user_amount_brl, abs=0.01)

    def test_multiple_aliases_same_category_sum(self, cmp):
        """'habitacao' e 'aluguel' somam em 'moradia'."""
        income = 5_000.0
        report = cmp.compare(income, {"habitacao": 600, "aluguel": 900})
        moradia = next(c for c in report.categories if c.category == "moradia")
        assert moradia.user_amount_brl == pytest.approx(1_500.0, abs=0.01)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# compare() — highlights e summary_text
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestHighlightsAndSummary:
    def test_highlights_above_populated(self, cmp):
        """Gasto muito alto em moradia deve aparecer em highlights_above."""
        report = cmp.compare(5_000, {"moradia": 3_000})  # 60%, benchmark 30%
        assert "Moradia" in report.highlights_above

    def test_highlights_below_populated(self, cmp):
        """Gasto muito baixo em moradia deve aparecer em highlights_below."""
        report = cmp.compare(5_000, {"moradia": 100})  # 2%, benchmark 30%
        assert "Moradia" in report.highlights_below

    def test_poupanca_excluded_from_highlights(self, cmp):
        """Poupança nunca deve aparecer em highlights_above ou highlights_below."""
        report = cmp.compare(5_000, {})  # poupança = 100% (extremo)
        assert "Poupança" not in report.highlights_above
        assert "Poupança" not in report.highlights_below

    def test_summary_text_is_non_empty(self, cmp):
        report = cmp.compare(5_000, {"moradia": 1_500})
        assert isinstance(report.summary_text, str)
        assert len(report.summary_text) > 20

    def test_summary_contains_savings_info(self, cmp):
        report = cmp.compare(5_000, {"moradia": 1_500})
        assert "poupança" in report.summary_text.lower() or "%" in report.summary_text

    def test_na_media_not_in_highlights(self, cmp):
        """Categoria na média não deve aparecer em highlights."""
        income = 5_000.0
        bench = _BENCHMARKS["MEDIA"]["moradia"]  # 30%
        report = cmp.compare(income, {"moradia": bench * income})
        assert "Moradia" not in report.highlights_above
        assert "Moradia" not in report.highlights_below


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# compare() — cada bracket usa benchmarks corretos
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.mark.parametrize("income,bracket", [
    (2_000, "BAIXA"),
    (5_000, "MEDIA"),
    (12_000, "ALTA"),
    (25_000, "PREMIUM"),
])
def test_benchmark_pct_matches_bracket(cmp, income, bracket):
    report = cmp.compare(income, {})
    moradia = next(c for c in report.categories if c.category == "moradia")
    expected = _BENCHMARKS[bracket]["moradia"]
    assert moradia.benchmark_pct == pytest.approx(expected, abs=0.001)
    assert report.income_bracket == bracket


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# to_dict() — serialização
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestToDict:
    def test_required_keys_present(self, cmp):
        d = cmp.compare(5_000, {"moradia": 1_500}).to_dict()
        for key in ["income_bracket", "bracket_label", "monthly_income",
                    "user_savings_rate", "benchmark_savings_rate",
                    "savings_percentile_label", "categories",
                    "highlights_above", "highlights_below", "summary_text"]:
            assert key in d, f"Chave ausente: {key}"

    def test_categories_list_of_dicts(self, cmp):
        d = cmp.compare(5_000, {}).to_dict()
        assert isinstance(d["categories"], list)
        cat = d["categories"][0]
        for key in ["category", "label", "user_pct", "benchmark_pct",
                    "user_amount_brl", "benchmark_amount_brl", "delta_pct",
                    "status", "insight"]:
            assert key in cat

    def test_savings_rate_as_percentage(self, cmp):
        """to_dict deve converter taxa decimal para %."""
        report = cmp.compare(5_000, {"moradia": 1_500})
        d = report.to_dict()
        # user_savings_rate no to_dict é * 100
        assert d["user_savings_rate"] == pytest.approx(
            round(report.user_savings_rate * 100, 1), abs=0.1
        )

    def test_monthly_income_preserved(self, cmp):
        d = cmp.compare(8_500, {}).to_dict()
        assert d["monthly_income"] == pytest.approx(8_500, abs=0.01)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API — GET /peers/compare/{user_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.peers.router import router as peers_router
from app.core.security import get_current_user

_app = FastAPI()
_app.include_router(peers_router)
_app.dependency_overrides[get_current_user] = lambda: "u1"
_client = TestClient(_app)


def _expenses_only_df():
    """Transações sem nenhum crédito — renda inestimável pelo IncomeProfiler."""
    import datetime
    import polars as pl

    today = datetime.date.today().isoformat()
    return pl.DataFrame([
        {"date": today, "amount": -1500.0, "category": "moradia", "description": "aluguel"},
        {"date": today, "amount": -500.0, "category": "alimentacao", "description": "mercado"},
    ])


def _no_cache(monkeypatch):
    """Desliga o cache Redis do endpoint para o mock ser sempre chamado."""
    import app.core.cache as cache_module

    monkeypatch.setattr(cache_module, "get_redis", lambda: None)


def test_api_missing_income_returns_422(monkeypatch):
    """Sem monthly_income E sem como estimar (só despesas) → 422.

    Desde que o endpoint ganhou estimativa de renda via IncomeProfiler,
    o 422 só acontece quando a estimativa também falha; usuário sem
    transação nenhuma retorna 404 antes (ver test_api_no_data_returns_404).
    """
    _no_cache(monkeypatch)
    monkeypatch.setattr(
        "app.peers.router.get_transactions_for_user",
        lambda user_id: _expenses_only_df(),
    )
    resp = _client.get("/peers/compare/u1")
    assert resp.status_code == 422
    assert "monthly_income" in resp.json()["detail"]


def test_api_wrong_user_returns_403():
    """Token de u1 acessando dados de u2 deve retornar 403."""
    resp = _client.get("/peers/compare/u2?monthly_income=5000")
    assert resp.status_code == 403


def test_api_zero_income_returns_422(monkeypatch):
    """income=0 é inválido; sem crédito nas transações a estimativa falha → 422."""
    _no_cache(monkeypatch)
    monkeypatch.setattr(
        "app.peers.router.get_transactions_for_user",
        lambda user_id: _expenses_only_df(),
    )
    resp = _client.get("/peers/compare/u1?monthly_income=0")
    assert resp.status_code == 422


def test_api_returns_200_with_mock(monkeypatch):
    """Endpoint com dados mockados deve retornar 200 e estrutura correta."""
    import polars as pl
    import datetime

    # Datas recentes para não serem filtradas pelo cutoff de history_months
    today = datetime.date.today().isoformat()
    fake_df = pl.DataFrame([
        {"date": today, "amount": -1500.0, "category": "moradia"},
        {"date": today, "amount": -500.0, "category": "alimentacao"},
    ])

    monkeypatch.setattr(
        "app.peers.router.get_transactions_for_user",
        lambda user_id: fake_df,
    )

    resp = _client.get("/peers/compare/u1?monthly_income=5000")
    assert resp.status_code == 200
    data = resp.json()
    assert "income_bracket" in data
    assert "categories" in data
    assert isinstance(data["categories"], list)


def test_api_no_data_returns_404(monkeypatch):
    """Sem transações, endpoint deve retornar 404 (comportamento definido no router)."""
    import polars as pl
    from app.core.cache import get_redis

    monkeypatch.setattr(
        "app.peers.router.get_transactions_for_user",
        lambda user_id: pl.DataFrame(),
    )
    # Remove cache para garantir que a função mockada seja chamada
    r = get_redis()
    if r:
        r.delete("nexa:cache:peers:monthly_income=7777.0:user_id=u1")

    resp = _client.get("/peers/compare/u1?monthly_income=7777")
    assert resp.status_code == 404
