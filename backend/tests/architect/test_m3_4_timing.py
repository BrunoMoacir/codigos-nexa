# tests/architect/test_m3_4_timing.py
# Testes para M3.4 — "E se eu esperar X meses?"

import pytest

from app.architect.models import (
    SimulationRequest,
    AssetType,
    AmortizationMethod,
    StrategyType,
    TimingScenario,
)
from app.architect.simulators.strategy_engine import StrategyEngine

# ── Fixtures ────────────────────────────────────────────────────────────────────

def _make_request(
    target: float = 80_000.0,
    down: float = 10_000.0,
    monthly_budget: float = 2_500.0,
    financing_months: int = 48,
) -> SimulationRequest:
    return SimulationRequest(
        user_id="test_user",
        asset_type=AssetType.VEICULO,
        target_amount=target,
        down_payment=down,
        financing_months=financing_months,
        amortization_method=AmortizationMethod.PRICE,
        max_monthly_budget=monthly_budget,
    )


_RATES = {
    "selic_annual":    0.1325,
    "cdi_annual":      0.1325,
    "best_cet_annual": 0.20,
    "ipca_annual":     0.045,
    "consortium_admin_rate":        0.17,
    "consortium_months":            72.0,
    "consortium_reserve_fund_rate": 0.02,
}

_ENGINE = StrategyEngine()


# ── Testes: TimingScenario model ───────────────────────────────────────────────

def test_timing_scenario_model_valid():
    """TimingScenario deve ser construído sem erros com dados válidos."""
    ts = TimingScenario(
        wait_months=6,
        accumulated_down_payment=22_000.0,
        new_principal=58_000.0,
        recommended_strategy=StrategyType.FINANCING,
        total_cost_expected=75_000.0,
        total_cost_npv=-65_000.0,
        monthly_payment=1_900.0,
        saving_vs_now=3_200.0,
        comparison_text="Esperar 6 meses poupando R$2.000/mês.",
    )
    assert ts.wait_months == 6
    assert ts.monthly_payment == 1_900.0
    assert ts.saving_vs_now == 3_200.0


def test_timing_scenario_comparison_text_min_length():
    """comparison_text com menos de 10 chars deve lançar ValidationError."""
    with pytest.raises(Exception):
        TimingScenario(
            wait_months=0,
            accumulated_down_payment=10_000.0,
            new_principal=70_000.0,
            recommended_strategy=StrategyType.FINANCING,
            total_cost_expected=70_000.0,
            total_cost_npv=-60_000.0,
            monthly_payment=2_000.0,
            saving_vs_now=0.0,
            comparison_text="curta",  # < 10 chars
        )


# ── Testes: simulate_timing_scenarios ─────────────────────────────────────────

def test_default_returns_4_scenarios():
    """Padrão [0,3,6,12] → 4 cenários."""
    req = _make_request()
    results = _ENGINE.simulate_timing_scenarios(req, _RATES, monthly_savings=2_000.0)
    assert len(results) == 4
    assert [r.wait_months for r in results] == [0, 3, 6, 12]


def test_custom_scenarios():
    """Cenários customizados devem ser respeitados."""
    req = _make_request()
    results = _ENGINE.simulate_timing_scenarios(
        req, _RATES, monthly_savings=2_000.0, scenarios=[0, 24]
    )
    assert len(results) == 2
    assert results[0].wait_months == 0
    assert results[1].wait_months == 24


def test_wait_0_saving_vs_now_is_zero():
    """Cenário 'agora' (wait=0) deve ter saving_vs_now == 0."""
    req = _make_request()
    results = _ENGINE.simulate_timing_scenarios(req, _RATES, monthly_savings=2_000.0)
    now = next(r for r in results if r.wait_months == 0)
    assert now.saving_vs_now == 0.0


def test_more_savings_reduces_monthly_payment():
    """Esperar mais meses → maior entrada → menor parcela."""
    req = _make_request()
    results = _ENGINE.simulate_timing_scenarios(req, _RATES, monthly_savings=2_000.0)
    # Pegar cenários 0 e 12
    now   = next(r for r in results if r.wait_months == 0)
    later = next(r for r in results if r.wait_months == 12)
    assert later.monthly_payment < now.monthly_payment
    assert later.accumulated_down_payment > now.accumulated_down_payment


def test_down_payment_accumulates_correctly():
    """Entrada acumulada = down_payment + monthly_savings × wait_months (sem ultrapassar 95% do target)."""
    req = _make_request(target=80_000, down=10_000)
    results = _ENGINE.simulate_timing_scenarios(req, _RATES, monthly_savings=2_000.0)
    s3 = next(r for r in results if r.wait_months == 3)
    expected = 10_000 + 2_000 * 3   # = 16_000
    assert abs(s3.accumulated_down_payment - expected) < 0.01


def test_principal_equals_target_minus_down():
    """new_principal = target_amount - accumulated_down_payment."""
    req = _make_request(target=80_000, down=10_000)
    results = _ENGINE.simulate_timing_scenarios(req, _RATES, monthly_savings=2_000.0)
    for s in results:
        assert abs(s.new_principal - (80_000 - s.accumulated_down_payment)) < 0.01


def test_down_payment_capped_at_95_percent():
    """Se poupança acumulada ultrapassar 95% do target, deve ser limitada."""
    req = _make_request(target=80_000, down=75_000.0)  # já quase no limite
    # Após 3 meses: 75k + 2k*3 = 81k > 95% de 80k = 76k
    results = _ENGINE.simulate_timing_scenarios(req, _RATES, monthly_savings=2_000.0)
    for s in results:
        assert s.accumulated_down_payment <= 80_000 * 0.95 + 0.01


def test_comparison_text_wait0_mentions_agora():
    """Texto do cenário wait=0 deve mencionar 'agora'."""
    req = _make_request()
    results = _ENGINE.simulate_timing_scenarios(req, _RATES, monthly_savings=2_000.0)
    now = next(r for r in results if r.wait_months == 0)
    assert "agora" in now.comparison_text.lower()


def test_comparison_text_waitN_mentions_months():
    """Texto do cenário wait>0 deve mencionar o número de meses."""
    req = _make_request()
    results = _ENGINE.simulate_timing_scenarios(req, _RATES, monthly_savings=2_000.0)
    s12 = next(r for r in results if r.wait_months == 12)
    assert "12 meses" in s12.comparison_text.lower()


def test_inflation_note_included_for_long_waits():
    """Para esperas longas (12m), nota de inflação deve aparecer no texto."""
    req = _make_request(target=200_000)
    results = _ENGINE.simulate_timing_scenarios(req, _RATES, monthly_savings=2_000.0)
    s12 = next(r for r in results if r.wait_months == 12)
    # A diferença de inflação vai ser > R$500 para R$200k em 12 meses a 4.5%
    assert "poder de compra" in s12.comparison_text.lower() or "infla" in s12.comparison_text.lower()


def test_all_scenarios_have_positive_total_cost():
    """Custo total deve ser positivo em todos os cenários."""
    req = _make_request()
    results = _ENGINE.simulate_timing_scenarios(req, _RATES, monthly_savings=2_000.0)
    for s in results:
        assert s.total_cost_expected > 0
        assert s.monthly_payment > 0


def test_duplicate_scenarios_not_repeated():
    """Duplicatas em scenarios devem ser eliminadas."""
    req = _make_request()
    results = _ENGINE.simulate_timing_scenarios(
        req, _RATES, monthly_savings=2_000.0, scenarios=[6, 6, 6]
    )
    assert len(results) == 1


# ── Testes: API endpoint ────────────────────────────────────────────────────────

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.architect.router import router as arch_router
from app.core.security import get_current_user

_app = FastAPI()
_app.include_router(arch_router)
_app.dependency_overrides[get_current_user] = lambda: "test_user"
_client = TestClient(_app)

_BASE_BODY = {
    "user_id": "test_user",
    "asset_type": "VEICULO",
    "target_amount": 80000.0,
    "down_payment": 10000.0,
    "financing_months": 48,
    "amortization_method": "PRICE",
}


def test_api_timing_scenarios_200():
    """POST /timing-scenarios → 200 e lista de cenários."""
    resp = _client.post(
        "/architect/timing-scenarios?monthly_savings=2000",
        json=_BASE_BODY,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 4
    assert data[0]["wait_months"] == 0


def test_api_timing_scenarios_custom_windows():
    """?wait_months=0,6 → apenas 2 cenários."""
    resp = _client.post(
        "/architect/timing-scenarios?monthly_savings=2000&wait_months=0,6",
        json=_BASE_BODY,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[1]["wait_months"] == 6


def test_api_timing_scenarios_missing_savings():
    """Sem monthly_savings → 422."""
    resp = _client.post("/architect/timing-scenarios", json=_BASE_BODY)
    assert resp.status_code == 422


def test_api_timing_scenarios_invalid_months():
    """wait_months com valor não inteiro → 422."""
    resp = _client.post(
        "/architect/timing-scenarios?monthly_savings=2000&wait_months=abc,6",
        json=_BASE_BODY,
    )
    assert resp.status_code == 422
