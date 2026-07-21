import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.retention.router import router

app = FastAPI()
app.include_router(router)

client = TestClient(app)

def test_get_cancellation_impact():
    user_id = "test_user_123"
    response = client.get(f"/retention/cancellation-impact/{user_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == user_id
    assert "total_saved_brl" in data
    assert "pending_alerts_count" in data
    assert "economizou" in data["message"]

def test_pause_account_success():
    payload = {
        "user_id": "test_user_123",
        "reason": "Vou viajar por 3 meses"
    }
    response = client.post("/retention/pause-account", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "test_user_123"
    assert data["status"] == "PAUSED"
    assert "pausada com sucesso" in data["message"]

def test_pause_account_missing_user():
    payload = {
        "user_id": "",
        "reason": "missing user"
    }
    response = client.post("/retention/pause-account", json=payload)
    
    assert response.status_code == 400
    assert response.json()["detail"] == "user_id is required"
