import pytest
from pydantic import ValidationError

from app.defense.models import PortabilitySimulationRequest
from app.defense.services.portability_simulator import simulate_portability


def test_simulation_identifica_economia_com_taxa_menor() -> None:
    result = simulate_portability(
        PortabilitySimulationRequest(
            balance=10_000,
            current_monthly_rate=0.03,
            target_monthly_rate=0.02,
            remaining_months=12,
        )
    )

    assert result.status == "ADVANTAGEOUS"
    assert result.target_payment < result.current_payment
    assert result.estimated_savings > 0
    assert "CET" in result.disclaimer


def test_simulation_rejeita_proposta_com_taxa_maior() -> None:
    result = simulate_portability(
        PortabilitySimulationRequest(
            balance=10_000,
            current_monthly_rate=0.02,
            target_monthly_rate=0.03,
            remaining_months=12,
        )
    )

    assert result.status == "INVALID_TARGET"
    assert result.estimated_savings < 0


@pytest.mark.parametrize(
    ("field", "value"),
    [("balance", 0), ("current_monthly_rate", 0), ("remaining_months", 0)],
)
def test_simulation_rejeita_entrada_invalida(field: str, value: float) -> None:
    values = {
        "balance": 10_000,
        "current_monthly_rate": 0.03,
        "target_monthly_rate": 0.02,
        "remaining_months": 12,
    }
    values[field] = value

    with pytest.raises(ValidationError):
        PortabilitySimulationRequest(**values)


def test_simulation_preserva_parcela_atual_informada() -> None:
    result = simulate_portability(
        PortabilitySimulationRequest(
            balance=10_000,
            current_monthly_rate=0.03,
            target_monthly_rate=0.02,
            remaining_months=12,
            current_payment=1_100,
        )
    )

    assert result.current_payment == 1_100
    assert result.current_total_cost == 13_200
