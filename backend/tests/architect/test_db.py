"""
Tests for Architect persistence using the current SQLAlchemy layer.
"""

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.architect.models_orm import ArchitectSimulation, ArchitectSimulationMetrics
from app.architect.queries import (
    get_simulation,
    get_user_latest_simulation,
    get_user_metrics,
    get_user_simulations,
    save_simulation,
    update_simulation_metrics,
)
from app.core.database import Base


@pytest.fixture
def db_session_factory(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            ArchitectSimulation.__table__,
            ArchitectSimulationMetrics.__table__,
        ],
    )
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr("app.architect.queries.SessionLocal", factory)
    return factory


@pytest.fixture
def mock_request():
    req = MagicMock()
    req.target_amount = 50_000.0
    req.down_payment = 5_000.0
    req.max_monthly_budget = 2_000.0
    req.financing_months = 48
    req.asset_type.value = "VEICULO"
    req.amortization_type.value = "PRICE"
    req.model_dump.return_value = {
        "user_id": "user_test",
        "target_amount": 50_000.0,
        "asset_type": "VEICULO",
        "amortization_type": "PRICE",
        "financing_months": 48,
        "down_payment": 5_000.0,
        "max_monthly_budget": 2_000.0,
    }
    return req


@pytest.fixture
def mock_response():
    resp = MagicMock()
    resp.confidence_score = 0.80
    resp.liquidity_impact = -0.22
    resp.months_to_achieve = 1
    resp.recommended_strategy.value = "FINANCING"
    resp.costs.expected_cost = 63_000.0
    resp.model_dump.return_value = {
        "recommended_strategy": "FINANCING",
        "confidence_score": 0.80,
        "liquidity_impact": -0.22,
        "months_to_achieve": 1,
        "costs": {"expected_cost": 63_000.0, "min_cost": 60_000.0, "max_cost": 66_000.0},
        "action_plan": [{"step": 1, "action": "Assinar contrato"}],
    }
    return resp


def test_save_simulation_persists_row(db_session_factory, mock_request, mock_response):
    sim_id = save_simulation("user_test", mock_request, mock_response)

    assert uuid.UUID(sim_id)
    with db_session_factory() as db:
        row = db.query(ArchitectSimulation).filter_by(id=sim_id).first()

    assert row is not None
    assert row.user_id == "user_test"
    assert row.target_amount == 50_000.0
    assert row.asset_type == "VEICULO"
    assert row.recommended_strategy == "FINANCING"
    assert row.confidence_score == pytest.approx(0.80)
    assert row.liquidity_impact == pytest.approx(-0.22)


def test_save_simulation_updates_metrics(db_session_factory, mock_request, mock_response):
    save_simulation("user_test", mock_request, mock_response)

    metrics = get_user_metrics("user_test")

    assert metrics is not None
    assert metrics["total_simulations"] == 1
    assert metrics["favorite_strategy"] == "FINANCING"
    assert metrics["avg_confidence_score"] == pytest.approx(0.80)


def test_get_simulation_deserializes_payloads(db_session_factory, mock_request, mock_response):
    sim_id = save_simulation("user_test", mock_request, mock_response)

    sim = get_simulation(sim_id)

    assert sim is not None
    assert sim["id"] == sim_id
    assert sim["user_id"] == "user_test"
    assert sim["request"]["asset_type"] == "VEICULO"
    assert sim["response"]["recommended_strategy"] == "FINANCING"


def test_get_simulation_returns_none_for_missing_id(db_session_factory):
    assert get_simulation(str(uuid.uuid4())) is None


def test_get_user_simulations_filters_and_limits(db_session_factory, mock_request, mock_response):
    for _ in range(3):
        save_simulation("user_test", mock_request, mock_response)
    save_simulation("other_user", mock_request, mock_response)

    sims = get_user_simulations("user_test", limit=2, asset_type="VEICULO")

    assert len(sims) == 2
    assert all(sim["asset_type"] == "VEICULO" for sim in sims)


def test_get_user_simulations_returns_empty_list(db_session_factory):
    assert get_user_simulations("new_user") == []


def test_get_user_latest_simulation(db_session_factory, mock_request, mock_response):
    first = save_simulation("user_test", mock_request, mock_response)
    latest_id = save_simulation("user_test", mock_request, mock_response)

    latest = get_user_latest_simulation("user_test")

    assert latest is not None
    assert latest["id"] in {first, latest_id}
    assert latest["response"]["recommended_strategy"] == "FINANCING"


def test_get_user_latest_simulation_returns_none(db_session_factory):
    assert get_user_latest_simulation("missing_user") is None


def test_update_simulation_metrics_public(db_session_factory, mock_request, mock_response):
    save_simulation("user_test", mock_request, mock_response)

    assert update_simulation_metrics("user_test") is True
    assert get_user_metrics("user_test")["total_simulations"] == 1


def test_update_metrics_without_simulations_returns_false(db_session_factory):
    assert update_simulation_metrics("missing_user") is False
    assert get_user_metrics("missing_user") is None
