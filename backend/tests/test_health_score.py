# tests/test_health_score.py
# Testes de integração para MX.1 — Score Financeiro com Evolução Temporal

import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from datetime import date
from unittest.mock import patch, MagicMock

from app.health_score.router import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


# ── Helpers de Mock ──────────────────────────────────────────────────────────

def _empty_df() -> pl.DataFrame:
    return pl.DataFrame()


def _transactions_df() -> pl.DataFrame:
    """DataFrame mínimo com 15 linhas para passar o threshold INSUFFICIENT_DATA."""
    from datetime import date, timedelta
    n = 15
    base = date(2026, 2, 1)
    return pl.DataFrame({
        "user_id": ["user_test"] * n,
        "date": [base - timedelta(days=i) for i in range(n)],
        "amount": [-200.0] * (n - 2) + [3000.0, 2800.0],
        "description": ["Supermercado"] * (n - 2) + ["Salário", "Freelance"],
        "category": ["alimentacao"] * (n - 2) + ["renda", "renda"],
        "transaction_type": ["DEBIT"] * (n - 2) + ["CREDIT", "CREDIT"],
        "context_type": ["PF"] * n,
    })


# ── Testes ───────────────────────────────────────────────────────────────────

def test_history_no_transactions(monkeypatch):
    """Quando não há transações, retorna data_quality='NO_TRANSACTIONS' e score 0."""
    monkeypatch.setattr(
        "app.api.v1.routes.health_score._fetch_transactions_sync",
        lambda user_id: _empty_df()
    )
    monkeypatch.setattr(
        "app.api.v1.routes.health_score.get_health_score_history",
        lambda user_id, months: []
    )

    response = client.get("/health-score/history/user_sem_dados")
    assert response.status_code == 200
    data = response.json()
    assert data["data_quality"] == "NO_TRANSACTIONS"
    assert data["current_score"] == 0
    assert data["history"] == []


def test_history_with_enough_transactions(monkeypatch):
    """Com transações suficientes, deve calcular score e persistir snapshot."""
    saved = {}

    def mock_save(user_id, health_score, savings_rate, profile_type, safe_to_spend=None):
        saved["user_id"] = user_id
        saved["score"] = health_score
        return True

    monkeypatch.setattr(
        "app.api.v1.routes.health_score._fetch_transactions_sync",
        lambda user_id: _transactions_df()
    )
    monkeypatch.setattr(
        "app.api.v1.routes.health_score.save_health_score_snapshot",
        mock_save
    )
    monkeypatch.setattr(
        "app.api.v1.routes.health_score.get_health_score_history",
        lambda user_id, months: [{"date": "2026-03", "health_score": 65, "savings_rate": 0.1, "profile_type": "EQUILIBRADO", "safe_to_spend": None}]
    )

    response = client.get("/health-score/history/user_test")
    assert response.status_code == 200
    data = response.json()

    # Score foi calculado e está dentro do range válido
    assert 0 <= data["current_score"] <= 100
    # Snapshot foi salvo
    assert saved.get("user_id") == "user_test"
    # Histórico retornado
    assert len(data["history"]) == 1
    assert data["history"][0]["date"] == "2026-03"


def test_trend_improving(monkeypatch):
    """Tendência IMPROVING quando score aumentou ≥ 3 pontos nos últimos 3 meses."""
    monkeypatch.setattr(
        "app.api.v1.routes.health_score._fetch_transactions_sync",
        lambda user_id: _empty_df()
    )
    history_data = [
        {"date": "2025-11", "health_score": 55, "savings_rate": 0.05, "profile_type": "GASTADOR", "safe_to_spend": None},
        {"date": "2025-12", "health_score": 60, "savings_rate": 0.08, "profile_type": "EQUILIBRADO", "safe_to_spend": None},
        {"date": "2026-01", "health_score": 65, "savings_rate": 0.10, "profile_type": "EQUILIBRADO", "safe_to_spend": None},
        {"date": "2026-02", "health_score": 70, "savings_rate": 0.12, "profile_type": "EQUILIBRADO", "safe_to_spend": None},
    ]
    monkeypatch.setattr(
        "app.api.v1.routes.health_score.get_health_score_history",
        lambda user_id, months: history_data
    )

    response = client.get("/health-score/history/user_improving")
    assert response.status_code == 200
    data = response.json()
    assert data["trend"] == "IMPROVING"
    assert data["change_30d"] == 5   # 70 - 65
    assert data["change_90d"] == 15  # 70 - 55


def test_trend_declining(monkeypatch):
    """Tendência DECLINING quando score caiu ≥ 3 pontos."""
    monkeypatch.setattr(
        "app.api.v1.routes.health_score._fetch_transactions_sync",
        lambda user_id: _empty_df()
    )
    history_data = [
        {"date": "2025-12", "health_score": 75, "savings_rate": 0.20, "profile_type": "CONSERVADOR", "safe_to_spend": None},
        {"date": "2026-01", "health_score": 65, "savings_rate": 0.10, "profile_type": "EQUILIBRADO", "safe_to_spend": None},
        {"date": "2026-02", "health_score": 55, "savings_rate": 0.02, "profile_type": "GASTADOR", "safe_to_spend": None},
    ]
    monkeypatch.setattr(
        "app.api.v1.routes.health_score.get_health_score_history",
        lambda user_id, months: history_data
    )

    response = client.get("/health-score/history/user_declining")
    assert response.status_code == 200
    data = response.json()
    assert data["trend"] == "DECLINING"


def test_months_query_param(monkeypatch):
    """Parâmetro ?months é passado corretamente para a query de histórico."""
    captured = {}
    def capture_months(user_id, months):
        captured["months"] = months
        return []

    monkeypatch.setattr(
        "app.api.v1.routes.health_score._fetch_transactions_sync",
        lambda user_id: _empty_df()
    )
    monkeypatch.setattr(
        "app.api.v1.routes.health_score.get_health_score_history",
        capture_months
    )

    client.get("/health-score/history/user_x?months=12")
    assert captured.get("months") == 12
