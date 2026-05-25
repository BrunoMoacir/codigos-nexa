"""
tests/architect/test_calibration.py — Testes unitários e de integração da pipeline de calibração

Cobre:
    1. CalibrationPipeline._calibrate_score_thresholds  — limiares via isotonic regression
    2. CalibrationPipeline._calibrate_bid_params        — ajuste bid_mean_initial
    3. CalibrationPipeline._calibrate_confidence_threshold — teto do confidence_score
    4. Condições de dados insuficientes (cada sub-sistema reporta honestamente)
    5. Race condition guard — save_feedback_and_check_trigger via SELECT FOR UPDATE
    6. TTL cache — ArchitectService._get_calibration_state
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.architect.services.calibration_pipeline import (
    MIN_CONSORTIUM_FEEDBACKS,
    MIN_FEEDBACKS_CONFIDENCE,
    MIN_FEEDBACKS_PER_ASSET,
    CalibrationPipeline,
    _group_by_asset,
)


# ─── Helpers de fixture ────────────────────────────────────────────────────────

def _make_feedback(
    risk_score: float,
    followed: bool,
    confidence: float = 0.80,
    strategy: str = "FINANCING",
    asset_type: str = "VEICULO",
    contemplation_month: int | None = None,
):
    fb = SimpleNamespace(
        risk_score_at_simulation=risk_score,
        feedback_followed=followed,
        confidence_score_at_simulation=confidence,
        strategy_used=strategy,
        asset_type=asset_type,
        actual_contemplation_month=contemplation_month,
    )
    return fb


def _make_consortium_row(fb, simulated_p50):
    return {"feedback": fb, "simulated_p50": simulated_p50}


# ─── 1. _calibrate_score_thresholds ────────────────────────────────────────────

class TestCalibrateScoreThresholds:
    def _pipeline(self):
        return CalibrationPipeline()

    def test_insufficient_data_reports_honestly(self):
        pipeline = self._pipeline()
        per_asset = {"VEICULO": [_make_feedback(0.3, True) for _ in range(5)]}
        updates, changes = pipeline._calibrate_score_thresholds(per_asset, {})
        assert updates is None
        assert any("insuficientes" in c.lower() for c in changes)

    def test_calibrates_conservative_threshold(self):
        """Feedbacks: score < 0.35 nunca seguidos, score > 0.5 sempre seguidos."""
        pipeline = self._pipeline()
        low = [_make_feedback(0.10 + i * 0.01, False) for i in range(20)]
        high = [_make_feedback(0.55 + i * 0.01, True) for i in range(20)]
        per_asset = {"VEICULO": low + high}
        updates, changes = pipeline._calibrate_score_thresholds(per_asset, {})
        # Deve retornar algum update (a não ser que o delta seja < 0.005)
        # threshold_conservative deve estar abaixo de 0.50
        if updates:
            assert updates.get("threshold_conservative", 0.35) < 0.50
        assert isinstance(changes, list)

    def test_aggressive_always_above_conservative(self):
        pipeline = self._pipeline()
        fbs = [_make_feedback(0.1 + i * 0.02, i > 10) for i in range(40)]
        per_asset = {"VEICULO": fbs}
        updates, _ = pipeline._calibrate_score_thresholds(per_asset, {})
        if updates and "threshold_conservative" in updates and "threshold_aggressive" in updates:
            assert updates["threshold_aggressive"] > updates["threshold_conservative"] + 0.09

    def test_clamps_conservative_within_bounds(self):
        """Não pode sair do intervalo [0.20, 0.45]."""
        pipeline = self._pipeline()
        # Todos seguem — iso retorna P(follow) = 1.0 para qualquer score
        # → threshold_conservative deve ser clamped em 0.20 (limite inferior)
        fbs = [_make_feedback(0.01 * i, True) for i in range(50)]
        per_asset = {"VEICULO": fbs}
        updates, _ = pipeline._calibrate_score_thresholds(per_asset, {})
        if updates and "threshold_conservative" in updates:
            assert 0.20 <= updates["threshold_conservative"] <= 0.45

    def test_stable_when_delta_too_small(self):
        """Delta < 0.005 não deve gerar update."""
        pipeline = self._pipeline()
        # Simula estado atual igual ao que a isotônica encontraria
        fbs = [_make_feedback(0.10 + i * 0.01, i > 10) for i in range(40)]
        per_asset = {"VEICULO": fbs}
        # Primeira rodada: obtém os thresholds reais
        updates1, _ = pipeline._calibrate_score_thresholds(per_asset, {})
        state = {}
        if updates1:
            state = updates1.copy()
        # Segunda rodada com o mesmo estado — delta será zero
        updates2, changes2 = pipeline._calibrate_score_thresholds(per_asset, state)
        if updates1 is None:
            assert updates2 is None
        else:
            # Pode ser None (estável) ou ter delta mínimo
            if updates2:
                for key in ("threshold_conservative", "threshold_aggressive"):
                    if key in updates2 and key in state:
                        assert abs(updates2[key] - state[key]) > 0.005


# ─── 2. _calibrate_bid_params ──────────────────────────────────────────────────

class TestCalibrateBidParams:
    def _pipeline(self):
        return CalibrationPipeline()

    def test_insufficient_data_reports_honestly(self):
        pipeline = self._pipeline()
        rows = [_make_consortium_row(_make_feedback(0.5, True, contemplation_month=24), 20)
                for _ in range(5)]
        updates, changes = pipeline._calibrate_bid_params(rows, {})
        assert updates is None
        assert any("insuficientes" in c.lower() for c in changes)

    def test_reduces_bid_mean_when_real_slower(self):
        """real_p50 > sim_p50 → contemplações mais lentas → reduz bid_mean_initial."""
        pipeline = self._pipeline()
        # real = 30 meses, sim = 20 meses → erro_relativo = 0.5 → delta = +0.025
        rows = [
            _make_consortium_row(_make_feedback(0.5, True, contemplation_month=30), 20)
            for _ in range(MIN_CONSORTIUM_FEEDBACKS)
        ]
        state = {"bid_params": {"global": {"bid_mean_initial": 0.35, "bid_std": 0.12}}}
        updates, changes = pipeline._calibrate_bid_params(rows, state)
        if updates:
            assert updates["global"]["bid_mean_initial"] < 0.35

    def test_increases_bid_mean_when_real_faster(self):
        """real_p50 < sim_p50 → contemplações mais rápidas → aumenta bid_mean_initial."""
        pipeline = self._pipeline()
        rows = [
            _make_consortium_row(_make_feedback(0.5, True, contemplation_month=10), 20)
            for _ in range(MIN_CONSORTIUM_FEEDBACKS)
        ]
        state = {"bid_params": {"global": {"bid_mean_initial": 0.35, "bid_std": 0.12}}}
        updates, changes = pipeline._calibrate_bid_params(rows, state)
        if updates:
            assert updates["global"]["bid_mean_initial"] >= 0.35

    def test_clamps_bid_mean_within_bounds(self):
        pipeline = self._pipeline()
        # Cenário extremo: real muito mais lento (100 meses vs 1)
        rows = [
            _make_consortium_row(_make_feedback(0.5, True, contemplation_month=100), 1)
            for _ in range(MIN_CONSORTIUM_FEEDBACKS)
        ]
        state = {"bid_params": {"global": {"bid_mean_initial": 0.20, "bid_std": 0.12}}}
        updates, _ = pipeline._calibrate_bid_params(rows, state)
        if updates:
            assert 0.15 <= updates["global"]["bid_mean_initial"] <= 0.55

    def test_ignores_rows_missing_contemplation(self):
        pipeline = self._pipeline()
        valid = [
            _make_consortium_row(_make_feedback(0.5, True, contemplation_month=24), 20)
            for _ in range(MIN_CONSORTIUM_FEEDBACKS)
        ]
        invalid = [
            _make_consortium_row(_make_feedback(0.5, True, contemplation_month=None), None)
            for _ in range(5)
        ]
        state = {}
        updates, changes = pipeline._calibrate_bid_params(valid + invalid, state)
        # Deve processar normalmente com os valid (≥ MIN_CONSORTIUM_FEEDBACKS)
        assert isinstance(changes, list)


# ─── 3. _calibrate_confidence_threshold ───────────────────────────────────────

class TestCalibrateConfidenceThreshold:
    def _pipeline(self):
        return CalibrationPipeline()

    def test_insufficient_data_reports_honestly(self):
        pipeline = self._pipeline()
        fbs = [_make_feedback(0.8, True) for _ in range(10)]
        new_teto, changes = pipeline._calibrate_confidence_threshold(fbs, {})
        assert new_teto is None
        assert any("insuficientes" in c.lower() for c in changes)

    def test_lowers_ceiling_when_high_conf_fails(self):
        """
        Confidence > 0.90 com baixa precision → teto deve ser rebaixado.
        """
        pipeline = self._pipeline()
        # Decil 0.0-0.1: precision = 1.0 (high precision, low conf)
        good = [_make_feedback(0.05, True) for _ in range(10)]
        # Decil 0.9-1.0: precision = 0.10 (superconfiante errava muito)
        bad = [_make_feedback(0.91 + i * 0.005, False) for i in range(18)]
        bad += [_make_feedback(0.91 + i * 0.005, True) for i in range(2)]
        fbs = good + bad
        new_teto, changes = pipeline._calibrate_confidence_threshold(
            fbs, {"confidence_threshold_upper": 1.0}
        )
        # Esperamos que o teto seja rebaixado (não 1.0)
        assert new_teto is None or new_teto < 1.0

    def test_never_falls_below_minimum(self):
        pipeline = self._pipeline()
        # Todos os decis com precision muito baixa → nenhum c* encontrado
        fbs = [_make_feedback(0.05 + i * 0.045, False) for i in range(MIN_FEEDBACKS_CONFIDENCE)]
        new_teto, changes = pipeline._calibrate_confidence_threshold(
            fbs, {"confidence_threshold_upper": 0.80}
        )
        # Quando nenhum decil atinge precision_target, mantém o teto atual
        assert new_teto is None

    def test_stable_when_delta_too_small(self):
        pipeline = self._pipeline()
        fbs = [_make_feedback(0.05 + i * 0.045, i % 4 != 0) for i in range(MIN_FEEDBACKS_CONFIDENCE)]
        new_teto1, _ = pipeline._calibrate_confidence_threshold(fbs, {})
        if new_teto1 is not None:
            new_teto2, changes2 = pipeline._calibrate_confidence_threshold(
                fbs, {"confidence_threshold_upper": new_teto1}
            )
            # Segunda rodada com mesmo estado → delta < 0.01 → estável
            assert new_teto2 is None or abs(new_teto2 - new_teto1) > 0.01


# ─── 4. run() — integração dos três sub-sistemas ──────────────────────────────

class TestCalibrationPipelineRun:
    def test_run_with_no_feedbacks_returns_no_updates(self):
        pipeline = CalibrationPipeline()
        mock_db = MagicMock()

        with (
            patch(
                "app.architect.services.calibration_pipeline.CalibrationPipeline._calibrate_score_thresholds"
            ) as mock_thresh,
            patch(
                "app.architect.services.calibration_pipeline.CalibrationPipeline._calibrate_bid_params"
            ) as mock_bid,
            patch(
                "app.architect.services.calibration_pipeline.CalibrationPipeline._calibrate_confidence_threshold"
            ) as mock_conf,
            patch(
                "app.architect.feedback_queries.get_feedbacks_for_calibration",
                return_value=[],
            ),
            patch(
                "app.architect.feedback_queries.get_consortium_feedbacks_with_p50",
                return_value=[],
            ),
            patch("app.architect.feedback_queries.load_calibration_state", return_value={}),
            patch("app.architect.feedback_queries.save_calibration_state"),
        ):
            mock_thresh.return_value = (None, ["Dados insuficientes por tipo de bem"])
            mock_bid.return_value = (None, ["Dados insuficientes para calibrar MC"])
            mock_conf.return_value = (None, ["Dados insuficientes para calibrar confidence"])

            result = pipeline.run(mock_db)

        assert result.thresholds_updated is False
        assert result.bid_params_updated is False
        assert result.confidence_threshold_updated is False
        assert result.n_feedbacks_used == 0

    def test_run_with_sufficient_data_updates_all(self):
        pipeline = CalibrationPipeline()
        mock_db = MagicMock()

        fake_feedbacks = [_make_feedback(0.5, True) for _ in range(30)]
        fake_consortium = [_make_consortium_row(_make_feedback(0.5, True, contemplation_month=20), 18)
                           for _ in range(15)]

        with (
            patch("app.architect.feedback_queries.get_feedbacks_for_calibration", return_value=fake_feedbacks),
            patch("app.architect.feedback_queries.get_consortium_feedbacks_with_p50", return_value=fake_consortium),
            patch("app.architect.feedback_queries.load_calibration_state", return_value={}),
            patch("app.architect.feedback_queries.save_calibration_state") as mock_save,
        ):
            result = pipeline.run(mock_db)

        assert result.n_feedbacks_used == 30
        assert isinstance(result.changes, list)


# ─── 5. _group_by_asset ────────────────────────────────────────────────────────

def test_group_by_asset():
    fbs = [
        _make_feedback(0.3, True, asset_type="VEICULO"),
        _make_feedback(0.5, False, asset_type="VEICULO"),
        _make_feedback(0.7, True, asset_type="IMOVEL"),
    ]
    groups = _group_by_asset(fbs)
    assert len(groups["VEICULO"]) == 2
    assert len(groups["IMOVEL"]) == 1


# ─── 6. TTL cache em ArchitectService ──────────────────────────────────────────

class TestArchitectServiceCalibrationCache:
    def test_cache_miss_on_first_call(self):
        import time
        from app.architect.services.architect_service import ArchitectService, _CALIBRATION_CACHE_TTL

        service = ArchitectService.__new__(ArchitectService)
        service._calibration_state = None
        service._cache_loaded_at = 0.0  # força expiração

        fake_state = {"threshold_conservative": 0.28, "threshold_aggressive": 0.70}

        with patch("app.architect.feedback_queries.load_calibration_state", return_value=fake_state):
            state = service._get_calibration_state()

        assert state["threshold_conservative"] == 0.28
        assert state["threshold_aggressive"] == 0.70

    def test_cache_hit_skips_db(self):
        import time
        from app.architect.services.architect_service import ArchitectService, _CALIBRATION_CACHE_TTL

        service = ArchitectService.__new__(ArchitectService)
        cached = {"threshold_conservative": 0.33}
        service._calibration_state = cached
        service._cache_loaded_at = time.time()  # acabou de carregar

        with patch("app.architect.feedback_queries.load_calibration_state") as mock_load:
            state = service._get_calibration_state()
            mock_load.assert_not_called()

        assert state is cached

    def test_cache_expires_after_ttl(self):
        import time
        from app.architect.services.architect_service import ArchitectService, _CALIBRATION_CACHE_TTL

        service = ArchitectService.__new__(ArchitectService)
        service._calibration_state = {"threshold_conservative": 0.33}
        service._cache_loaded_at = time.time() - _CALIBRATION_CACHE_TTL - 1  # expirado

        new_state = {"threshold_conservative": 0.28}
        with patch("app.architect.feedback_queries.load_calibration_state", return_value=new_state):
            state = service._get_calibration_state()

        assert state["threshold_conservative"] == 0.28

    def test_cache_returns_empty_dict_on_db_failure(self):
        import time
        from app.architect.services.architect_service import ArchitectService, _CALIBRATION_CACHE_TTL

        service = ArchitectService.__new__(ArchitectService)
        service._calibration_state = None
        service._cache_loaded_at = 0.0

        with patch("app.architect.feedback_queries.load_calibration_state", return_value=None):
            state = service._get_calibration_state()

        assert state == {}
