"""
tests/architect/conftest.py - Fixtures compartilhadas para toda a suíte da F3

Feature: F3 - Nexa Architect
Version: 1.0.0

COMO USAR:
    Essas fixtures são carregadas automaticamente pelo pytest para
    todos os testes dentro de tests/architect/.
    Basta declarar o nome como parâmetro do teste:

        def test_algo(base_request, market_rates):
            ...
"""

import sys
from pathlib import Path
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

# Garante que backend/ seja raiz do Python para todos os testes desta pasta
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.architect.models import (
    AmortizationMethod,
    AssetType,
    RiskProfile,
    SimulationRequest,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REQUESTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def base_request() -> SimulationRequest:
    """
    Request padrão: veículo R$50k, entrada R$10k, budget R$2k, 48m PRICE.
    Usado como base na maioria dos testes.
    """
    return SimulationRequest(
        user_id="test_user_001",
        target_amount=50_000.0,
        down_payment=10_000.0,
        max_monthly_budget=2_000.0,
        risk_profile=RiskProfile.MODERADO,
        asset_type=AssetType.VEICULO,
        include_consortium=True,
        financing_months=48,
        amortization_method=AmortizationMethod.PRICE,
    )


@pytest.fixture
def imovel_request() -> SimulationRequest:
    """Request para imóvel de R$350k — prazo longo, SAC."""
    return SimulationRequest(
        user_id="test_user_002",
        target_amount=350_000.0,
        down_payment=70_000.0,
        max_monthly_budget=3_500.0,
        risk_profile=RiskProfile.CONSERVADOR,
        asset_type=AssetType.IMOVEL,
        include_consortium=True,
        financing_months=240,
        amortization_method=AmortizationMethod.SAC,
    )


@pytest.fixture
def minimal_request() -> SimulationRequest:
    """Request mínimo: apenas campos obrigatórios."""
    return SimulationRequest(
        user_id="user_minimal",
        target_amount=20_000.0,
    )


@pytest.fixture
def request_sem_consortium() -> SimulationRequest:
    """Request sem consórcio na comparação."""
    return SimulationRequest(
        user_id="test_no_cons",
        target_amount=30_000.0,
        down_payment=5_000.0,
        max_monthly_budget=1_500.0,
        include_consortium=False,
        financing_months=36,
    )


@pytest.fixture
def request_com_data_futura() -> SimulationRequest:
    """Request com target_date no futuro."""
    return SimulationRequest(
        user_id="test_date",
        target_amount=40_000.0,
        down_payment=8_000.0,
        target_date=date.today() + timedelta(days=730),  # 2 anos
        max_monthly_budget=1_800.0,
        financing_months=24,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAXAS DE MERCADO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def market_rates() -> dict:
    """Taxas realistas para fevereiro/2026."""
    return {
        "selic_annual":    0.1325,  # 13,25% a.a.
        "cdi_annual":      0.1315,  # 13,15% a.a.
        "best_cet_annual": 0.1950,  # 19,50% a.a. (veículo avg)
    }


@pytest.fixture
def market_rates_imovel() -> dict:
    """Taxas para imóvel (CET menor)."""
    return {
        "selic_annual":    0.1325,
        "cdi_annual":      0.1315,
        "best_cet_annual": 0.1475,  # 14,75% a.a. (imóvel min)
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MOCKS DE CONECTORES (para isolar testes do service)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def mock_bacen():
    """Mock do BacenConnector — retorna SELIC fixa."""
    m = MagicMock()
    m.get_selic.return_value = 0.1325
    m.get_fallback_rates.return_value = {"selic_annual": 0.1325}
    return m


@pytest.fixture
def mock_anbima():
    """Mock do AnbimaConnector — retorna CDI fixo."""
    m = MagicMock()
    m.get_cdi.return_value = 0.1315
    m.get_fallback_rates.return_value = {"cdi_annual": 0.1315}
    return m


@pytest.fixture
def mock_market_rates():
    """Mock do MarketRatesConnector — CET de veículo."""
    m = MagicMock()
    m.get_best_cet.return_value = 0.1950
    m.get_fallback_rates.return_value = {"cet_VEICULO_min": 0.1620}
    return m


@pytest.fixture
def mock_bacen_erro():
    """Mock do BacenConnector que lança Exception."""
    m = MagicMock()
    m.get_selic.side_effect = ConnectionError("BACEN offline")
    m.get_fallback_rates.return_value = {"selic_annual": 0.1325}
    return m
