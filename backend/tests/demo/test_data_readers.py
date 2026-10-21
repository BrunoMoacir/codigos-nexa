from __future__ import annotations

from unittest.mock import patch

from demo import data_readers


def test_rows_degrada_para_lista_vazia_quando_banco_falha() -> None:
    with patch(
        "app.core.database.SessionLocal",
        side_effect=RuntimeError("banco indisponível"),
    ):
        assert data_readers.accounts("demo-ana") == []


def test_goals_degrada_para_lista_vazia_quando_tracker_falha() -> None:
    with patch(
        "app.goals.tracker.GoalTracker",
        side_effect=RuntimeError("tracker indisponível"),
    ):
        assert data_readers.goals("demo-ana") == []


def test_learning_loops_preserva_formato_quando_fontes_falham() -> None:
    with (
        patch(
            "app.negotiator.calibration.compute_calibration",
            side_effect=RuntimeError("calibração indisponível"),
        ),
        patch(
            "app.optimizer.queries.get_feedback_stats",
            side_effect=RuntimeError("feedback indisponível"),
        ),
        patch("demo.data_readers._rows", return_value=[]),
    ):
        assert data_readers.learning_loops() == {
            "calibration": {},
            "feedback": [],
            "metrics": [],
        }
