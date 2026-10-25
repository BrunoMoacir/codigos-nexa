from app.health_score.exporter import build_hive_score_export
from app.health_score.router import HealthScoreHistoryResponse, HealthScorePoint


def test_export_inclui_indicadores_agregados_e_historico() -> None:
    response = HealthScoreHistoryResponse(
        user_id="user-123",
        current_score=82,
        trend="IMPROVING",
        change_30d=4,
        change_90d=10,
        history=[
            HealthScorePoint(
                date="2026-09",
                score=72,
                savings_rate=12.5,
                profile_type="EQUILIBRADO",
            )
        ],
        data_quality="OK",
        resilience_score=85,
        fss_score=18.0,
        fss_level="SAUDAVEL",
        fss_signals=["overdraft_usage=0%"],
    )

    result = build_hive_score_export(response)

    assert result.schema_version == "1"
    assert result.score == 82
    assert result.history == [
        {
            "date": "2026-09",
            "score": 72,
            "savings_rate": 12.5,
            "profile_type": "EQUILIBRADO",
        }
    ]
    assert "transa" not in result.model_dump_json().lower()
    assert "CPF" not in result.model_dump_json()
