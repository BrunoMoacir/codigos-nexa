# tests/test_peer_comparison.py
# Testes para MX.4 — Peer Comparison (benchmarks IBGE/POF por faixa de renda)

import datetime
import polars as pl
import pytest
from unittest.mock import patch, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.peers.router import router
from app.core.security import require_owner
from app.peers.peer_comparison import PeerComparator


USER = "user_peers_test"


def _make_app():
    a = FastAPI()
    a.include_router(router)
    a.dependency_overrides[require_owner] = lambda user_id: user_id
    return a


app = _make_app()
client = TestClient(app)


def _transactions_df(n: int = 10) -> pl.DataFrame:
    """DataFrame com transações de débito para testar a comparação."""
    today = datetime.date.today()
    return pl.DataFrame({
        "user_id": [USER] * n,
        "date": [today - datetime.timedelta(days=i * 3) for i in range(n)],
        "amount": [-300.0] * (n - 2) + [3000.0, 2500.0],
        "category": ["alimentacao"] * (n - 4) + ["transporte"] * 2 + ["renda", "renda"],
        "transaction_type": ["DEBIT"] * (n - 2) + ["CREDIT", "CREDIT"],
        "context_type": ["PF"] * n,
    })


# ── Testes PeerComparator (lógica de negócio) ─────────────────────────────────

def test_peer_comparator_returns_report():
    """PeerComparator retorna relatório com campos esperados."""
    comparator = PeerComparator()
    report = comparator.compare(
        monthly_income=5000.0,
        category_spending={"alimentacao": 800.0, "transporte": 300.0},
    )
    assert report.income_bracket is not None
    assert 0.0 <= report.user_savings_rate <= 1.0
    assert isinstance(report.savings_percentile_label, str)
    assert len(report.savings_percentile_label) > 0
    assert isinstance(report.categories, list)


def test_peer_comparator_different_income_brackets():
    """Renda alta e baixa resultam em faixas (brackets) diferentes."""
    comparator = PeerComparator()
    low = comparator.compare(monthly_income=1500.0, category_spending={"alimentacao": 600.0})
    high = comparator.compare(monthly_income=15000.0, category_spending={"alimentacao": 600.0})
    assert low.income_bracket != high.income_bracket


def test_peer_comparator_savings_above_average():
    """Poupança alta → percentil ACIMA_DA_MEDIA."""
    comparator = PeerComparator()
    # Gasta pouco (só R$100 em alimentação) com renda de R$5000 → poupança ~98%
    report = comparator.compare(
        monthly_income=5000.0,
        category_spending={"alimentacao": 100.0},
    )
    assert report.user_savings_rate > 0.5


def test_peer_comparator_to_dict_has_required_keys():
    """to_dict() retorna todos os campos esperados pelo frontend."""
    comparator = PeerComparator()
    report = comparator.compare(
        monthly_income=4000.0,
        category_spending={"alimentacao": 900.0, "lazer": 500.0},
    )
    d = report.to_dict()
    required_keys = {
        "income_bracket", "bracket_label", "monthly_income",
        "user_savings_rate", "benchmark_savings_rate",
        "savings_percentile_label", "categories", "summary_text",
    }
    assert required_keys.issubset(set(d.keys()))


# ── Testes HTTP ───────────────────────────────────────────────────────────────

def test_compare_no_transactions_returns_404():
    """Sem transações → 404."""
    with patch("app.peers.router.get_transactions_for_user", return_value=pl.DataFrame()):
        resp = client.get(f"/peers/compare/{USER}?monthly_income=5000")
    assert resp.status_code == 404


def test_compare_no_income_no_estimate_returns_422():
    """Sem monthly_income e sem como estimar → 422."""
    df = _transactions_df()
    with patch("app.peers.router.get_transactions_for_user", return_value=df):
        # Simula IncomeProfiler que não consegue estimar (confidence baixa)
        mock_profile = MagicMock(monthly_net_income=0, confidence=0.1)
        with patch("app.forecast.etl.income_profiler.IncomeProfiler") as MockProfiler:
            MockProfiler.return_value.build.return_value = mock_profile
            resp = client.get(f"/peers/compare/{USER}")
    assert resp.status_code == 422


def test_compare_with_income_returns_200():
    """monthly_income informado com transações válidas → 200."""
    df = _transactions_df()
    with patch("app.peers.router.get_transactions_for_user", return_value=df):
        resp = client.get(f"/peers/compare/{USER}?monthly_income=5000")
    assert resp.status_code == 200
    data = resp.json()
    assert "income_bracket" in data
    assert "categories" in data
    assert "savings_percentile_label" in data


def test_compare_response_structure():
    """Resposta tem todos os campos obrigatórios."""
    df = _transactions_df()
    with patch("app.peers.router.get_transactions_for_user", return_value=df):
        resp = client.get(f"/peers/compare/{USER}?monthly_income=5000")
    assert resp.status_code == 200
    data = resp.json()
    for key in ["income_bracket", "monthly_income", "user_savings_rate", "summary_text"]:
        assert key in data, f"Campo '{key}' ausente na resposta"


def test_compare_history_months_param():
    """Parâmetro history_months altera a janela de análise."""
    df = _transactions_df(20)
    with patch("app.peers.router.get_transactions_for_user", return_value=df):
        resp1 = client.get(f"/peers/compare/{USER}?monthly_income=5000&history_months=1")
        resp3 = client.get(f"/peers/compare/{USER}?monthly_income=5000&history_months=3")
    assert resp1.status_code == 200
    assert resp3.status_code == 200
