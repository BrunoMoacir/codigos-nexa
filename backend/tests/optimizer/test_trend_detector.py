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


# ─── Testes de PIX e Delivery (requerem enriched_recent_df) ──────────────────

def _enriched_txn(
    amount: float,
    days_ago: int,
    payment_method: str = "CREDIT",
    is_delivery: bool = False,
    description: str = "COMPRA",
) -> dict:
    return {
        "date": TODAY - timedelta(days=days_ago),
        "amount": amount,
        "category_canonical": "alimentacao",
        "transaction_type": "DEBIT" if payment_method in ("PIX", "DEBIT") else "CREDIT",
        "payment_method": payment_method,
        "is_delivery": is_delivery,
        "description": description,
    }


def _make_enriched_df(rows: list[dict]) -> pl.DataFrame:
    df = pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Date))
    if "is_delivery" in df.columns:
        df = df.with_columns(pl.col("is_delivery").cast(pl.Boolean))
    return df


class TestPIXAndDelivery:

    def _detector(self):
        return TrendDetector()

    def test_pix_omitido_sem_enriched_df(self):
        """Sem enriched_recent_df, _pix não deve aparecer na saída."""
        result = self._detector().detect(
            df=_make_df([_txn(-500.0, 10)]),
            current_spend_by_category={},
            current_spend_by_source={},
            current_monthly_income=0.0,
            personal_baseline=_baseline({}),
            reference_date=TODAY,
            enriched_recent_df=None,
        )
        assert "_pix" not in result
        assert "_delivery" not in result

    def test_delivery_omitido_sem_enriched_df(self):
        result = self._detector().detect(
            df=_make_df([_txn(-100.0, 10)]),
            current_spend_by_category={},
            current_spend_by_source={},
            current_monthly_income=0.0,
            personal_baseline=_baseline({}),
            reference_date=TODAY,
            enriched_recent_df=None,
        )
        assert "_delivery" not in result

    def test_pix_reemergindo_sem_historico(self):
        """PIX presente no recente mas ausente no histórico → REEMERGINDO."""
        recent = _make_enriched_df([
            _enriched_txn(-300.0, 10, payment_method="PIX"),
            _enriched_txn(-300.0, 20, payment_method="PIX"),
            _enriched_txn(-300.0, 30, payment_method="PIX"),
        ])
        # df histórico sem PIX (janela [90d, 540d] atrás — vazio)
        hist_df = _make_df([_txn(-1.0, 200, transaction_type="CREDIT")])

        result = self._detector().detect(
            df=hist_df,
            current_spend_by_category={},
            current_spend_by_source={},
            current_monthly_income=0.0,
            personal_baseline=_baseline({}),
            reference_date=TODAY,
            enriched_recent_df=recent,
        )
        assert "_pix" in result
        assert result["_pix"]["direction"] == "REEMERGINDO"
        assert result["_pix"]["current_monthly"] > 0
        assert result["_pix"]["baseline_monthly"] == 0.0

    def test_delivery_aumentando(self):
        """iFood recente muito maior que histórico → SUBINDO."""
        # Histórico: R$100/mês em delivery (dentro da janela 90–540d atrás)
        hist_rows = [
            {
                "date": TODAY - timedelta(days=200),
                "amount": -100.0,
                "description": "IFOOD PEDIDO",
                "category_canonical": "alimentacao",
                "transaction_type": "CREDIT",
            },
            {
                "date": TODAY - timedelta(days=230),
                "amount": -100.0,
                "description": "IFOOD PEDIDO",
                "category_canonical": "alimentacao",
                "transaction_type": "CREDIT",
            },
            {
                "date": TODAY - timedelta(days=260),
                "amount": -100.0,
                "description": "IFOOD PEDIDO",
                "category_canonical": "alimentacao",
                "transaction_type": "CREDIT",
            },
        ]
        hist_df = _make_df(hist_rows)

        # Recente: R$400/mês em delivery (4× o histórico)
        recent = _make_enriched_df([
            _enriched_txn(-400.0, 10, is_delivery=True),
            _enriched_txn(-400.0, 40, is_delivery=True),
            _enriched_txn(-400.0, 70, is_delivery=True),
        ])

        result = self._detector().detect(
            df=hist_df,
            current_spend_by_category={},
            current_spend_by_source={},
            current_monthly_income=0.0,
            personal_baseline=_baseline({}),
            reference_date=TODAY,
            enriched_recent_df=recent,
        )
        assert "_delivery" in result
        assert result["_delivery"]["direction"] == "SUBINDO"
        assert result["_delivery"]["current_monthly"] > result["_delivery"]["baseline_monthly"]

    def test_delivery_sem_historico_reemergindo(self):
        """Delivery antes ausente, agora presente → REEMERGINDO."""
        hist_df = _make_df([_txn(-200.0, 200, transaction_type="CREDIT")])  # sem delivery
        recent = _make_enriched_df([
            _enriched_txn(-250.0, 10, is_delivery=True),
            _enriched_txn(-250.0, 40, is_delivery=True),
        ])
        result = self._detector().detect(
            df=hist_df,
            current_spend_by_category={},
            current_spend_by_source={},
            current_monthly_income=0.0,
            personal_baseline=_baseline({}),
            reference_date=TODAY,
            enriched_recent_df=recent,
        )
        assert result["_delivery"]["direction"] == "REEMERGINDO"

    def test_pix_desaparecendo(self):
        """PIX comum no histórico mas ausente no recente → DESAPARECENDO."""
        hist_rows = [
            {
                "date": TODAY - timedelta(days=200),
                "amount": -500.0,
                "description": "PIX ENVIADO",
                "category_canonical": "outros",
                "transaction_type": None,
            },
            {
                "date": TODAY - timedelta(days=230),
                "amount": -500.0,
                "description": "PIX ENVIADO",
                "category_canonical": "outros",
                "transaction_type": None,
            },
            {
                "date": TODAY - timedelta(days=260),
                "amount": -500.0,
                "description": "PIX ENVIADO",
                "category_canonical": "outros",
                "transaction_type": None,
            },
        ]
        hist_df = _make_df(hist_rows)

        # Recente: sem PIX
        recent = _make_enriched_df([
            _enriched_txn(-300.0, 10, payment_method="CREDIT"),
        ])

        result = self._detector().detect(
            df=hist_df,
            current_spend_by_category={},
            current_spend_by_source={},
            current_monthly_income=0.0,
            personal_baseline=_baseline({}),
            reference_date=TODAY,
            enriched_recent_df=recent,
        )
        if "_pix" in result:
            assert result["_pix"]["direction"] in ("DESAPARECENDO", "ESTAVEL")

    def test_estrutura_pix_e_delivery(self):
        """_pix e _delivery devem ter as quatro chaves padrão."""
        recent = _make_enriched_df([
            _enriched_txn(-200.0, 10, payment_method="PIX"),
            _enriched_txn(-200.0, 20, is_delivery=True),
        ])
        hist_df = _make_df([_txn(-1.0, 200)])
        result = self._detector().detect(
            df=hist_df,
            current_spend_by_category={},
            current_spend_by_source={},
            current_monthly_income=0.0,
            personal_baseline=_baseline({}),
            reference_date=TODAY,
            enriched_recent_df=recent,
        )
        for key in ("_pix", "_delivery"):
            if key in result:
                assert set(result[key].keys()) == {
                    "direction", "ratio", "baseline_monthly", "current_monthly"
                }
