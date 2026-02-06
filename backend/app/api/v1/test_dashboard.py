from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_dashboard_endpoint():
    r = client.get("/user/test-user/dashboard")

    assert r.status_code in (200, 404)

    if r.status_code == 200:
        body = r.json()
        assert "dashboard" in body
        dash = body["dashboard"]

        assert "safe_to_spend" in dash
        assert "shadow_invoices" in dash
        assert "profile" in dash
        assert "data_quality" in dash
