# tests/optimizer/test_trend_detector.py
# Testes unitários para TrendDetector.

from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest

from app.optimizer.detectors.personal_baseline import PersonalBaseline
from app.optimizer.detectors.trend_detector import TrendDetector, _classify, _MIN_MONTHLY

TODAY = date(2026, 1, 15)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _txn(
    amount: float,
    days_ago: int,
    category: str = "outros",
    transaction_type: str | None = "CREDIT",
    context_type: str | None = None,
) -> dict:
    row = {
        "date": TODAY - timedelta(days=days_ago),
        "amount": amount,
        "category_canonical": category,
        "transaction_type": transaction_type,
    }
    if context_type is not None:
        row["context_type"] = context_type
    return row


def _income_txn(amount: float, days_ago: int) -> dict:
    return {
        "date": TODAY - timedelta(days=days_ago),
        "amount": amount,
        "category_canonical": "renda",
        "transaction_type": None,
    }


def _make_df(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Date))


def _baseline(cat_avg: dict[str, float], data_months: int = 3) -> PersonalBaseline:
    total = sum(cat_avg.values())
    return PersonalBaseline(
        category_monthly_avg=cat_avg,
        total_monthly_avg=total,
        data_months=data_months,
    )


# ─── Testes de _classify ──────────────────────────────────────────────────────

class TestClassify:

    def test_estavel_sem_dados(self):
        direction, ratio = _classify(0.0, 0.0)
        assert direction == "ESTAVEL"
        assert ratio == 1.0

    def test_reemergindo(self):
        direction, ratio = _classify(200.0, 0.0)
        assert direction == "REEMERGINDO"
        assert ratio == float("inf")

    def test_desaparecendo(self):
        direction, ratio = _classify(0.0, 500.0)
        assert direction == "DESAPARECENDO"
        assert ratio == 0.0

    def test_subindo(self):
        direction, ratio = _classify(1200.0, 800.0)
        assert direction == "SUBINDO"
        assert ratio == pytest.approx(1.5, rel=1e-3)

    def test_caindo(self):
        direction, ratio = _classify(600.0, 1000.0)
        assert direction == "CAINDO"
        assert ratio == pytest.approx(0.6, rel=1e-3)

    def test_estavel_dentro_da_banda(self):
        direction, _ = _classify(1050.0, 1000.0)
        assert direction == "ESTAVEL"

    def test_fronteira_inferior_exata(self):
        direction, _ = _classify(800.0, 1000.0)
        assert direction == "CAINDO"

    def test_fronteira_superior_exata(self):
        direction, _ = _classify(1200.0, 1000.0)
        assert direction == "SUBINDO"

    def test_ruido_abaixo_min_monthly(self):
        # Ambos abaixo de _MIN_MONTHLY → ESTAVEL
        direction, _ = _classify(_MIN_MONTHLY - 1, _MIN_MONTHLY - 1)
        assert direction == "ESTAVEL"


# ─── Testes de TrendDetector.detect ──────────────────────────────────────────

class TestTrendDetector:

    def _detector(self):
        return TrendDetector()

    def test_retorna_vazio_sem_baseline(self):
        """Sem baseline histórico (data_months < 2) não gera tendências por categoria."""
        baseline = _baseline({}, data_months=0)
        df = _make_df([_txn(-500.0, 10, "alimentacao")])
        result = self._detector().detect(
            df=df,
            current_spend_by_category={"alimentacao": 500.0},
            current_spend_by_source={},
            current_monthly_income=0.0,
            personal_baseline=baseline,
            reference_date=TODAY,
        )
        # Sem baseline, não deve haver chaves de categoria
        assert "alimentacao" not in result

    def test_categoria_subindo(self):
        baseline = _baseline({"alimentacao": 800.0})
        df = _make_df([_txn(-100.0, 200, "alimentacao")])  # histórico irrelevante
        result = self._detector().detect(
            df=df,
            current_spend_by_category={"alimentacao": 1200.0},
            current_spend_by_source={},
            current_monthly_income=0.0,
            personal_baseline=baseline,
            reference_date=TODAY,
        )
        assert result["alimentacao"]["direction"] == "SUBINDO"
        assert result["alimentacao"]["ratio"] == pytest.approx(1.5, rel=1e-3)
        assert result["alimentacao"]["baseline_monthly"] == 800.0
        assert result["alimentacao"]["current_monthly"] == 1200.0

    def test_categoria_caindo(self):
        baseline = _baseline({"farmacia": 600.0})
        result = self._detector().detect(
            df=_make_df([_txn(-1.0, 200)]),
            current_spend_by_category={"farmacia": 300.0},
            current_spend_by_source={},
            current_monthly_income=0.0,
            personal_baseline=baseline,
            reference_date=TODAY,
        )
        assert result["farmacia"]["direction"] == "CAINDO"

    def test_categoria_reemergindo(self):
        """Viagem que estava ausente no baseline e reaparece no período recente."""
        baseline = _baseline({"alimentacao": 800.0})  # sem viagem
        result = self._detector().detect(
            df=_make_df([_txn(-1.0, 200)]),
            current_spend_by_category={"alimentacao": 800.0, "viagem": 400.0},
            current_spend_by_source={},
            current_monthly_income=0.0,
            personal_baseline=baseline,
            reference_date=TODAY,
        )
        assert result["viagem"]["direction"] == "REEMERGINDO"
        assert result["viagem"]["ratio"] == float("inf")

    def test_ignora_categoria_outros(self):
        baseline = _baseline({"outros": 100.0, "alimentacao": 500.0})
        result = self._detector().detect(
            df=_make_df([_txn(-1.0, 200)]),
            current_spend_by_category={"outros": 200.0, "alimentacao": 600.0},
            current_spend_by_source={},
            current_monthly_income=0.0,
            personal_baseline=baseline,
            reference_date=TODAY,
        )
        assert "outros" not in result
        assert "alimentacao" in result

    def test_income_caindo(self):
        """Renda histórica alta, renda recente menor: tendência CAINDO."""
        # Histórico: renda média de R$5000/mês (~180d atrás = dentro da janela 90-540d)
        rows = [
            _income_txn(5000.0, 200),
            _income_txn(5000.0, 230),
            _income_txn(5000.0, 260),
        ]
        df = _make_df(rows)
        baseline = _baseline({})

        result = self._detector().detect(
            df=df,
            current_spend_by_category={},
            current_spend_by_source={},
            current_monthly_income=3000.0,
            personal_baseline=baseline,
            reference_date=TODAY,
        )
        assert "_income" in result
        assert result["_income"]["direction"] == "CAINDO"

    def test_income_subindo(self):
        rows = [
            _income_txn(3000.0, 200),
            _income_txn(3000.0, 230),
            _income_txn(3000.0, 260),
        ]
        df = _make_df(rows)
        result = self._detector().detect(
            df=df,
            current_spend_by_category={},
            current_spend_by_source={},
            current_monthly_income=5000.0,
            personal_baseline=_baseline({}),
            reference_date=TODAY,
        )
        assert result["_income"]["direction"] == "SUBINDO"

    def test_credit_aumentando(self):
        """Histórico com gasto baixo em crédito; atual com gasto alto → crédito SUBINDO."""
        rows = [
            # histórico (200d atrás = dentro de [90d, 540d] atrás)
            {"date": TODAY - timedelta(days=200), "amount": -300.0,
             "category_canonical": "alimentacao", "transaction_type": "CREDIT"},
            {"date": TODAY - timedelta(days=230), "amount": -300.0,
             "category_canonical": "alimentacao", "transaction_type": "CREDIT"},
            {"date": TODAY - timedelta(days=260), "amount": -300.0,
             "category_canonical": "alimentacao", "transaction_type": "CREDIT"},
        ]
        df = _make_df(rows)
        result = self._detector().detect(
            df=df,
            current_spend_by_category={},
            current_spend_by_source={"credit": 800.0, "debit": 200.0},
            current_monthly_income=0.0,
            personal_baseline=_baseline({}),
            reference_date=TODAY,
        )
        assert "_credit" in result
        assert result["_credit"]["direction"] == "SUBINDO"

    def test_debit_reduzindo(self):
        """Histórico com alto débito; atual com débito baixo → débito CAINDO."""
        rows = [
            {"date": TODAY - timedelta(days=200), "amount": -1000.0,
             "category_canonical": "alimentacao", "transaction_type": "DEBIT"},
            {"date": TODAY - timedelta(days=230), "amount": -1000.0,
             "category_canonical": "alimentacao", "transaction_type": "DEBIT"},
            {"date": TODAY - timedelta(days=260), "amount": -1000.0,
             "category_canonical": "alimentacao", "transaction_type": "DEBIT"},
        ]
        df = _make_df(rows)
        result = self._detector().detect(
            df=df,
            current_spend_by_category={},
            current_spend_by_source={"debit": 400.0},
            current_monthly_income=0.0,
            personal_baseline=_baseline({}),
            reference_date=TODAY,
        )
        assert "_debit" in result
        assert result["_debit"]["direction"] == "CAINDO"

    def test_df_vazio_retorna_vazio(self):
        df = pl.DataFrame({"date": [], "amount": []}).with_columns(pl.col("date").cast(pl.Date))
        result = self._detector().detect(
            df=df,
            current_spend_by_category={},
            current_spend_by_source={},
            current_monthly_income=0.0,
            personal_baseline=_baseline({}),
            reference_date=TODAY,
        )
        assert result == {}

    def test_exclui_pj_do_historico(self):
        """Transações PJ não devem contaminar o baseline histórico de renda."""
        rows = [
            _income_txn(10000.0, 200),   # PJ — deve ser excluído
            _income_txn(3000.0, 230),    # PF
        ]
        rows[0]["context_type"] = "PJ"
        rows[1]["context_type"] = None
        df = _make_df(rows)
        result = self._detector().detect(
            df=df,
            current_spend_by_category={},
            current_spend_by_source={},
            current_monthly_income=3000.0,
            personal_baseline=_baseline({}),
            reference_date=TODAY,
        )
        # Renda histórica só conta a transação PF (R$3000); com current=3000 → ESTAVEL
        assert result.get("_income", {}).get("direction") == "ESTAVEL"

    def test_estrutura_de_saida(self):
        """Cada entry deve ter as quatro chaves obrigatórias."""
        baseline = _baseline({"alimentacao": 500.0})
        result = self._detector().detect(
            df=_make_df([_txn(-1.0, 200)]),
            current_spend_by_category={"alimentacao": 600.0},
            current_spend_by_source={},
            current_monthly_income=0.0,
            personal_baseline=baseline,
            reference_date=TODAY,
        )
        entry = result["alimentacao"]
        assert set(entry.keys()) == {"direction", "ratio", "baseline_monthly", "current_monthly"}
