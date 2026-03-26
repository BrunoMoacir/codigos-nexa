import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from app.optimizer.router import router as optimizer_router
from app.optimizer.models import OptimizationRequest

app = FastAPI()
app.include_router(optimizer_router)
client = TestClient(app)

def test_health_check_endpoint():
    response = client.get("/optimizer/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "module": "optimizer"}

def test_list_available_cards_endpoint():
    response = client.get("/optimizer/cards")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "cards" in data
    assert data["total"] > 0

def test_list_user_reports_empty(monkeypatch):
    monkeypatch.setattr("app.api.v1.routes.optimizer.get_optimization_reports", lambda user_id: [])
    response = client.get("/optimizer/reports/user_empty")
    assert response.status_code == 200
    assert response.json() == {"reports": []}

def test_get_report_detail_not_found(monkeypatch):
    monkeypatch.setattr("app.api.v1.routes.optimizer.get_optimization_report_by_id", lambda rid: None)
    response = client.get("/optimizer/reports/non_existent_id/detail")
    assert response.status_code == 404
    assert response.json()["detail"] == "Relatório não encontrado"
