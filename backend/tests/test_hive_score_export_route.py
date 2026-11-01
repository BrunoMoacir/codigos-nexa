import json

from app.health_score import router as health_router
from app.health_score.router import HealthScoreHistoryResponse, HealthScorePoint


def test_export_endpoint_retorna_download_json_sem_dados_brutos(monkeypatch) -> None:
    monkeypatch.setattr(
        health_router,
        "get_health_score_history_endpoint",
        lambda **kwargs: HealthScoreHistoryResponse(
            user_id="internal-user",
            current_score=77,
            trend="STABLE",
            history=[
                HealthScorePoint(date="2026-10", score=77, profile_type="EQUILIBRADO")
            ],
            data_quality="OK",
        ),
    )

    response = health_router.export_hive_score_endpoint(
        user_id="user-123", months=12, db=None
    )
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert response.media_type == "application/json"
    assert "hive_score_export.json" in response.headers["content-disposition"]
    assert payload["score"] == 77
    assert payload["history"][0]["date"] == "2026-10"
    assert "user_id" not in payload
    assert "transaction" not in response.body.decode().lower()
