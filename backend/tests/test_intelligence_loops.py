# tests/test_intelligence_loops.py
# Loops fechados de aprendizado + monitoramento de acurácia em produção:
#   negotiation_history (desfechos) → calibração → ganho apresentado
#   feedback/cobertura → intelligence_metrics (série temporal)

import json
from datetime import date

import pytest

import app.negotiator.calibration as cal_module
from app.negotiator.calibration import (
    MIN_SAMPLES,
    compute_calibration,
    get_calibration_factor,
)


@pytest.fixture(autouse=True)
def _cache_limpo(monkeypatch, tmp_path):
    """Cada teste com arquivo de calibração isolado e cache zerado."""
    monkeypatch.setattr(cal_module, "CALIBRATION_PATH", tmp_path / "calib.json")
    monkeypatch.setattr(cal_module, "_cache", {"loaded_at": 0.0, "mtime": 0.0, "data": None})
    return tmp_path


def _write_calibration(path, triggers):
    path.write_text(json.dumps({"triggers": triggers, "computed_at": "2026-07-19"}))


# ── leitura do fator ─────────────────────────────────────────────────────────

def test_fator_disponivel_para_trigger_calibrado(tmp_path):
    _write_calibration(cal_module.CALIBRATION_PATH, {
        "JUROS_ROTATIVO_ALTO": {"factor": 0.63, "samples": 12, "success_rate": 0.58},
    })
    assert get_calibration_factor("JUROS_ROTATIVO_ALTO") == (0.63, 12)


def test_sem_arquivo_retorna_none():
    assert get_calibration_factor("JUROS_ROTATIVO_ALTO") is None


def test_trigger_nao_calibrado_retorna_none(tmp_path):
    _write_calibration(cal_module.CALIBRATION_PATH, {
        "ANUIDADE_ALTA": {"factor": 0.8, "samples": 7, "success_rate": 0.7},
    })
    assert get_calibration_factor("JUROS_ROTATIVO_ALTO") is None


# ── cômputo a partir de desfechos reais ──────────────────────────────────────

class _FakeDB:
    def __init__(self, rows):
        self._rows = rows
    def __enter__(self):
        return self
    def __exit__(self, *a):
        ...
    def execute(self, *_a, **_k):
        class R:
            def __init__(self, rows): self._rows = rows
            def fetchall(self): return self._rows
        return R(self._rows)


def test_compute_calibration_mediana_e_bounds(monkeypatch):
    # 6 desfechos de JUROS: realizações 0.5,0.6,0.7 + recusados (0) → mediana honesta
    rows = [
        ("JUROS_ROTATIVO_ALTO", "sucesso", 100.0, 50.0),
        ("JUROS_ROTATIVO_ALTO", "sucesso", 100.0, 60.0),
        ("JUROS_ROTATIVO_ALTO", "parcial", 100.0, 70.0),
        ("JUROS_ROTATIVO_ALTO", "recusado", 100.0, None),   # conta como 0
        ("JUROS_ROTATIVO_ALTO", "sucesso", 100.0, 55.0),
        ("JUROS_ROTATIVO_ALTO", "parcial", 100.0, 65.0),
        # ANUIDADE: só 2 amostras → abaixo de MIN_SAMPLES, sem fator
        ("ANUIDADE_ALTA", "sucesso", 30.0, 30.0),
        ("ANUIDADE_ALTA", "recusado", 30.0, None),
    ]
    import app.core.database as db_module
    monkeypatch.setattr(db_module, "SessionLocal", lambda: _FakeDB(rows))

    result = compute_calibration()
    juros = result["triggers"]["JUROS_ROTATIVO_ALTO"]
    assert juros["samples"] == 6
    assert 0.5 <= juros["factor"] <= 0.65          # mediana de [0.5,0.55,0.6,0.65,0.7,0]
    assert juros["success_rate"] == pytest.approx(5 / 6, abs=0.01)
    assert "ANUIDADE_ALTA" not in result["triggers"]  # < MIN_SAMPLES


def test_fator_limitado_a_bounds(monkeypatch):
    # realizações absurdas (3x o estimado) não podem inflar o fator além de 1.2
    rows = [("HEALTH_SCORE_ALTO", "sucesso", 10.0, 30.0)] * MIN_SAMPLES
    import app.core.database as db_module
    monkeypatch.setattr(db_module, "SessionLocal", lambda: _FakeDB(rows))
    result = compute_calibration()
    assert result["triggers"]["HEALTH_SCORE_ALTO"]["factor"] == 1.2


# ── job de métricas ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_job_persiste_calibracao_e_metricas(monkeypatch, tmp_path):
    import app.jobs.intelligence_metrics as job_module

    monkeypatch.setattr(
        job_module, "_reco_feedback_metrics",
        lambda: [("reco_acceptance_rate", "CARD_SWITCH", 0.42, 57)],
    )
    monkeypatch.setattr(
        job_module, "_negotiation_metrics_and_calibration",
        lambda: (
            [("negotiation_realization_factor", "JUROS_ROTATIVO_ALTO", 0.63, 12)],
            {"triggers": {"JUROS_ROTATIVO_ALTO": {"factor": 0.63, "samples": 12,
                                                  "success_rate": 0.58}}},
        ),
    )
    monkeypatch.setattr(job_module, "_coverage_metrics", lambda: [])
    monkeypatch.setattr(job_module, "_agent_metrics", lambda: [])

    persisted: list = []
    monkeypatch.setattr(job_module, "_persist_metrics", lambda m: persisted.extend(m))

    await job_module.run_intelligence_metrics.__wrapped__()  # sem o job_guard

    assert cal_module.CALIBRATION_PATH.exists()
    saved = json.loads(cal_module.CALIBRATION_PATH.read_text())
    assert saved["triggers"]["JUROS_ROTATIVO_ALTO"]["factor"] == 0.63
    assert ("reco_acceptance_rate", "CARD_SWITCH", 0.42, 57) in persisted


# ── integração com o relatório do negociador ─────────────────────────────────

def test_router_do_negociador_aplica_fator(tmp_path):
    _write_calibration(cal_module.CALIBRATION_PATH, {
        "JUROS_ROTATIVO_ALTO": {"factor": 0.5, "samples": 10, "success_rate": 0.6},
    })
    factor = get_calibration_factor("JUROS_ROTATIVO_ALTO")
    assert factor == (0.5, 10)
    # ganho apresentado = potencial × fator (a nota de origem é adicionada aos warnings)
    assert 200.0 * factor[0] == pytest.approx(100.0)
