from app.defense.models import PortabilitySimulationRequest
from app.defense.router import simulate_portability_route


def test_rota_de_simulacao_de_portabilidade_delega_ao_servico() -> None:
    result = simulate_portability_route(
        PortabilitySimulationRequest(
            balance=20_000,
            current_monthly_rate=0.025,
            target_monthly_rate=0.018,
            remaining_months=24,
        ),
        user_id="user-1",
    )

    assert result.status == "ADVANTAGEOUS"
    assert result.estimated_savings > 0

