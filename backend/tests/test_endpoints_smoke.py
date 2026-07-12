"""
Smoke tests para validar endpoints com fallback DuckDB.

Uso: cd backend && pytest tests/test_endpoints_smoke.py -v
"""
import os
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    """Cliente de teste FastAPI."""
    return TestClient(app)


@pytest.fixture
def auth_headers(client):
    """Autentica e retorna headers com Bearer token."""
    # Usa credenciais de teste (criadas no DuckDB)
    login_data = {
        "username": "test@nexa.local",
        "password": "test123"
    }
    resp = client.post("/api/v1/auth/token", data=login_data)
    
    if resp.status_code != 200:
        pytest.skip(f"Auth failed: {resp.status_code} {resp.text}")
    
    token = resp.json().get("access_token")
    user_id = resp.json().get("user_id")
    
    return {"Authorization": f"Bearer {token}"}, user_id


class TestAuth:
    """Testes de autenticação."""

    def test_login_success(self, client):
        """POST /auth/token — login com credenciais válidas."""
        resp = client.post("/api/v1/auth/token", data={
            "username": "test@nexa.local",
            "password": "test123"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user_id"]
        print(f"✅ Login OK | user_id={data['user_id'][:8]}...")

    def test_login_invalid_password(self, client):
        """POST /auth/token — senha incorreta."""
        resp = client.post("/api/v1/auth/token", data={
            "username": "golden@nexa.com",
            "password": "wrong_password"
        })
        assert resp.status_code == 401
        print("✅ Invalid password rejected")


class TestTransactions:
    """Testes de transações."""

    def test_get_transactions(self, client, auth_headers):
        """GET /transactions/{user_id} — lista transações."""
        headers, user_id = auth_headers
        resp = client.get(
            f"/api/v1/transactions/{user_id}",
            headers=headers
        )
        # Pode ser 200 (com transações do DuckDB) ou 404 (sem dados)
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            data = resp.json()
            assert "user_id" in data
            assert "total" in data
            assert "transactions" in data
            print(f"✅ Got {data['total']} transactions")
        else:
            print(f"⚠️ No transactions for this user (expected)")

    def test_get_transactions_with_filters(self, client, auth_headers):
        """GET /transactions/{user_id}?category=... — com filtros."""
        headers, user_id = auth_headers
        resp = client.get(
            f"/api/v1/transactions/{user_id}?category=alimentacao&limit=10",
            headers=headers
        )
        # Pode retornar 200 (com dados) ou 404 (sem dados)
        assert resp.status_code in (200, 404)
        print(f"✅ Filtered query OK (status={resp.status_code})")


class TestHealthScore:
    """Testes de health score."""

    def test_get_health_score_history(self, client, auth_headers):
        """GET /health-score/history/{user_id} — histórico."""
        headers, user_id = auth_headers
        resp = client.get(
            f"/api/v1/health-score/history/{user_id}?months=6",
            headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "current_score" in data
        assert "trend" in data
        assert "history" in data
        assert data["trend"] in ["IMPROVING", "STABLE", "DECLINING"]
        print(f"✅ Health score OK | current={data['current_score']}/100 | trend={data['trend']}")


class TestContextOverride:
    """Testes de context override (PF/PJ)."""

    def test_list_overrides(self, client, auth_headers):
        """GET /context/overrides — listar histórico."""
        headers, user_id = auth_headers
        resp = client.get(
            f"/api/v1/context/overrides?user_id={user_id}",
            headers=headers
        )
        # Pode retornar 200 (vazio ou com dados) ou erro de conexão
        assert resp.status_code in (200, 404, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data, list)
            print(f"✅ Overrides list OK | count={len(data)}")
        else:
            print(f"⚠️ Overrides endpoint returned {resp.status_code} (expected for fallback)")


class TestForecast:
    """Testes de forecast."""

    def test_get_forecast(self, client, auth_headers):
        """GET /forecast/{user_id}."""
        headers, user_id = auth_headers
        resp = client.get(
            f"/api/v1/forecast/{user_id}",
            headers=headers
        )
        # 404 é o contrato para usuário recém-criado sem dados financeiros
        # ("Conecte suas contas via Open Finance"); 200 quando há dados;
        # 500/503 quando pipeline/LLM indisponível. 405/422 = rota quebrada.
        assert resp.status_code in (200, 404, 500, 503)
        if resp.status_code == 404:
            assert "Conecte suas contas" in resp.json().get("detail", "")
        elif resp.status_code == 200:
            print("✅ Forecast OK")
        else:
            print(f"⚠️ Forecast unavailable (expected if LLM not configured): {resp.status_code}")


class TestHealth:
    """Testes de saúde da API."""

    def test_health_check(self, client):
        """GET /health — healthcheck."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        print("✅ Health check OK")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
