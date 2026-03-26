import pytest
from fastapi.testclient import TestClient

# Mocking external dependencies before importing the main app router
from app.optimizer.router import router as optimizer_router
from fastapi import FastAPI

app = FastAPI()
app.include_router(optimizer_router)
client = TestClient(app)

class MockConnection:
    def execute(self, *args, **kwargs):
        class MockResult:
            def pl(self):
                import polars as pl
                return pl.DataFrame(schema={
                    "date": pl.Date, "amount": pl.Float64, "description": pl.Utf8,
                    "category": pl.Utf8, "pf_pj_label": pl.Utf8, "type": pl.Utf8
                })
        return MockResult()
    def close(self): pass

def test_analyze_endpoint_missing_user_id():
    response = client.post(
        "/optimizer/analyze",
        json={"safe_to_spend": 2000, "current_cards": []}
    )
    # Pydantic validation error for missing user_id
    assert response.status_code == 422 

def test_analyze_endpoint_validation_error(monkeypatch):
    monkeypatch.setattr("app.db.queries.get_connection", lambda: MockConnection())
    response = client.post(
        "/optimizer/analyze",
        json={
            "user_id": "test_user",
            # Missing both safe_to_spend and monthly_income
            "safe_to_spend": None,
            "monthly_income": None,
            "current_cards": []
        }
    )
    # Our custom ValueError in InputValidator via HTTPException
    assert response.status_code == 400
    assert "informe safe_to_spend ou monthly_income" in response.json()["detail"]

def test_analyze_endpoint_success(monkeypatch):
    # Mock duckdb save to prevent test state pollution
    monkeypatch.setattr("app.db.queries.get_connection", lambda: MockConnection())
    monkeypatch.setattr("app.optimizer.services.optimizer_service.save_optimization_report", lambda r: None)
    
    response = client.post(
        "/optimizer/analyze",
        json={
            "user_id": "test_user_api",
            "safe_to_spend": 1500,
            "monthly_income": 4000,
            "current_cards": []
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "report_id" in data
    assert data["user_id"] == "test_user_api"
    assert "recommendation_type" in data
