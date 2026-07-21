"""
tests/defense/test_connectors_defense.py — Conectores de defesa do consumidor

Testa INPCConnector, IPCAConnector e BacenCreditConnector usando apenas
fallbacks (sem chamadas reais de rede). Garante que o sistema funciona
offline e que os campos retornados estão corretos.

COMO RODAR:
    cd backend
    pytest tests/defense/test_connectors_defense.py -v
"""

import pytest


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# INPCConnector (série SGS 188)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestINPCConnector:
    """Valida o conector INPC criado para D5 (PDF V2 seção 4.1)."""

    @pytest.fixture
    def connector(self):
        from app.architect.connectors.inpc import INPCConnector
        return INPCConnector()

    def test_fallback_tem_campo_inpc_monthly(self, connector):
        fb = connector.get_fallback_rates()
        assert "inpc_monthly" in fb

    def test_fallback_inpc_e_decimal_valido(self, connector):
        fb = connector.get_fallback_rates()
        rate = fb["inpc_monthly"]
        assert isinstance(rate, float)
        assert 0.0 < rate < 0.05, f"Esperado 0–5% a.m., obtido {rate}"

    def test_get_inpc_monthly_sem_rede_usa_fallback(self, connector):
        from unittest.mock import patch
        with patch.object(connector, "fetch_rates", side_effect=Exception("sem rede")):
            rate = connector.get_inpc_monthly()
        assert isinstance(rate, float)
        assert rate > 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IPCAConnector (série SGS 433)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestIPCAConnector:

    @pytest.fixture
    def connector(self):
        from app.architect.connectors.ipca import IPCAConnector
        return IPCAConnector()

    def test_fallback_tem_campo_ipca_annual(self, connector):
        fb = connector.get_fallback_rates()
        assert "ipca_annual" in fb

    def test_fallback_ipca_e_decimal_valido(self, connector):
        fb = connector.get_fallback_rates()
        rate = fb["ipca_annual"]
        assert isinstance(rate, float)
        assert 0.0 < rate < 0.20, f"Esperado 0–20% a.a., obtido {rate}"

    def test_get_ipca_sem_rede_usa_fallback(self, connector):
        from unittest.mock import patch
        with patch.object(connector, "fetch_rates", side_effect=Exception("offline")):
            rate = connector.get_ipca()
        assert isinstance(rate, float)
        assert rate > 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BacenCreditConnector (séries 20714, 20706, 25433)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestBacenCreditConnector:

    @pytest.fixture
    def connector(self):
        from app.architect.connectors.bacen_credit import BacenCreditConnector
        return BacenCreditConnector()

    def test_fallback_tem_campos_obrigatorios(self, connector):
        fb = connector.get_fallback_rates()
        assert "rotativo_monthly" in fb
        assert "cheque_especial_monthly" in fb
        assert "consignado_monthly" in fb

    def test_rotativo_fallback_realista(self, connector):
        fb = connector.get_fallback_rates()
        rate = fb["rotativo_monthly"]
        assert 0.05 < rate < 0.25, f"Rotativo esperado 5–25% a.m., obtido {rate}"

    def test_consignado_menor_que_rotativo(self, connector):
        fb = connector.get_fallback_rates()
        assert fb["consignado_monthly"] < fb["rotativo_monthly"], (
            "Consignado deve ter taxa menor que rotativo"
        )

    def test_get_rates_sem_rede_usa_fallback(self, connector):
        from unittest.mock import patch
        with patch.object(connector, "fetch_rates", side_effect=Exception("offline")):
            rates = connector.get_rates()
        assert "rotativo_monthly" in rates
        assert rates["rotativo_monthly"] > 0
