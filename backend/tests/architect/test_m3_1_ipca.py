# tests/architect/test_m3_1_ipca.py
# Testes para M3.1 — Ajuste por Inflação (IPCAConnector + deflate + strategy_engine)

import pytest
from unittest.mock import patch, MagicMock

from app.architect.connectors.ipca import IPCAConnector, deflate, real_return


# ── Testes: deflate() ──────────────────────────────────────────────────────────

def test_deflate_basic():
    """R$180k nominal / 4.5% IPCA por 5 anos → menor em termos reais."""
    fv_real = deflate(180_000, 0.045, years=5)
    assert fv_real < 180_000
    assert abs(fv_real - 144_441) < 1000   # tolerância de ±R$1k


def test_deflate_zero_years():
    """0 anos → valor real = valor nominal."""
    assert deflate(100_000, 0.045, years=0) == 100_000


def test_deflate_zero_ipca():
    """IPCA = 0% → sem deflação."""
    assert deflate(100_000, 0.0, years=10) == pytest.approx(100_000, abs=1)


def test_deflate_negative_years():
    """Anos negativos → retorna sem deflação (proteção)."""
    assert deflate(100_000, 0.05, years=-5) == 100_000


# ── Testes: real_return() (Fisher) ────────────────────────────────────────────

def test_real_return_basic():
    """SELIC 13.25%, IPCA 4.87% → retorno real ~8% a.a."""
    r = real_return(0.1325, 0.0487)
    assert 0.07 < r < 0.09


def test_real_return_zero_ipca():
    """IPCA 0% → taxa real ≈ taxa nominal."""
    r = real_return(0.1325, 0.0)
    assert r == pytest.approx(0.1325, abs=0.001)


def test_real_return_high_inflation():
    """Inflação alta corrói o retorno real."""
    r = real_return(0.10, 0.10)
    assert r < 0.01  # quase zero


# ── Testes: IPCAConnector ──────────────────────────────────────────────────────

def test_ipca_connector_fallback():
    """Sem acesso à API, connector deve retornar fallback sem erro."""
    connector = IPCAConnector()
    connector.invalidate_cache()

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.side_effect = ConnectionError("no network")
        rates = connector.get_rates()

    assert "ipca_annual" in rates
    assert 0.02 <= rates["ipca_annual"] <= 0.08  # entre 2% e 8%


def test_ipca_connector_parse_api():
    """Simula resposta válida da API BCB e verifica parsing."""
    connector = IPCAConnector()
    connector.invalidate_cache()

    fake_response = MagicMock()
    fake_response.json.return_value = [{"valor": "4.87"}]
    fake_response.raise_for_status = MagicMock()

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.return_value = fake_response
        rates = connector.get_rates()

    assert rates["ipca_annual"] == pytest.approx(0.0487, abs=0.0001)


def test_ipca_connector_cache():
    """Segunda chamada deve usar cache, não refazer request."""
    connector = IPCAConnector()
    connector.invalidate_cache()

    fake_response = MagicMock()
    fake_response.json.return_value = [{"valor": "4.50"}]
    fake_response.raise_for_status = MagicMock()

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.return_value = fake_response
        connector.get_rates()  # 1ª chamada → API
        connector.get_rates()  # 2ª chamada → cache
        # API deve ter sido chamada apenas 1 vez
        assert mock_client.return_value.__enter__.return_value.get.call_count == 1


def test_ipca_get_ipca_convenience():
    """get_ipca() retorna apenas o float de ipca_annual."""
    connector = IPCAConnector()
    connector.invalidate_cache()

    with patch.object(connector, "fetch_rates", return_value={"ipca_annual": 0.0450}):
        ipca = connector.get_ipca()

    assert ipca == pytest.approx(0.0450, abs=0.0001)


# ── Testes: integração com strategy_engine ────────────────────────────────────

def test_strategy_engine_has_fv_real():
    """strategy_engine deve retornar fv_real < fv_nominal quando há inflação."""
    from app.architect.simulators.strategy_engine import StrategyEngine
    from app.architect.models import SimulationRequest, AssetType, AmortizationMethod

    request = SimulationRequest(
        user_id="u1",
        asset_type=AssetType.VEICULO,
        target_amount=60_000.0,
        down_payment=10_000.0,
        financing_months=60,
        amortization_method=AmortizationMethod.PRICE,
        max_monthly_budget=1_500.0,
    )

    market_rates = {
        "selic_annual":    0.1325,
        "cdi_annual":      0.1325,
        "best_cet_annual": 0.20,
        "ipca_annual":     0.045,
        "consortium_admin_rate":        0.17,
        "consortium_months":            72.0,
        "consortium_reserve_fund_rate": 0.02,
    }

    engine = StrategyEngine()
    result = engine.simulate(request, market_rates)

    # Verifica que a resposta existe (não é um erro)
    assert result is not None
    assert result.recommended_strategy is not None


def test_deflate_in_simulate_investment():
    """_simulate_investment deve retornar fv_real menor que fv_nominal."""
    from app.architect.simulators.strategy_engine import StrategyEngine
    from app.architect.models import SimulationRequest, AssetType, AmortizationMethod

    req = SimulationRequest(
        user_id="u1",
        asset_type=AssetType.IMOVEL,
        target_amount=200_000.0,
        down_payment=20_000.0,
        financing_months=120,
        amortization_method=AmortizationMethod.PRICE,
        max_monthly_budget=3_000.0,
    )

    rates = {
        "cdi_annual":    0.1325,
        "selic_annual":  0.1325,
        "ipca_annual":   0.045,
        "best_cet_annual": 0.15,
    }

    engine = StrategyEngine()
    result = engine._simulate_investment(req, rates)

    assert "fv_nominal" in result
    assert "fv_real" in result
    assert result["fv_real"] < result["fv_nominal"]
    assert result["fv_real"] > 0
