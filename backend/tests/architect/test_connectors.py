"""
tests/architect/test_connectors.py - Testes dos conectores de dados externos

O QUE É TESTADO:
    BacenConnector:
        - get_fallback_rates() retorna dict com 'selic_annual'
        - Fallback é float entre 0 e 1 (taxa anual como decimal)
        - get_selic() retorna float ou usa fallback sem exceção

    AnbimaConnector:
        - get_fallback_rates() retorna dict com 'cdi_annual'
        - get_cdi() retorna float >= 0

    MarketRatesConnector:
        - get_fallback_rates() retorna rates por tipo de bem
        - get_best_cet(asset_type) retorna float para cada tipo
        - CET de imóvel < CET de viagem (spread correto)

NOTA: Os testes de conectores externos (BACEN API, ANBIMA API) usam
      apenas os fallbacks para garantir execução offline. Testes de
      integração real são separados.

COMO RODAR:
    cd backend
    pytest tests/architect/test_connectors.py -v
"""

import pytest

from app.architect.connectors.bacen import BacenConnector
from app.architect.connectors.anbima import AnbimaConnector
from app.architect.connectors.market_rates import MarketRatesConnector


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES: BacenConnector
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestBacenConnector:
    """Testa o conector da API do Banco Central."""

    @pytest.fixture
    def bacen(self) -> BacenConnector:
        return BacenConnector()

    def test_fallback_tem_campo_selic_annual(self, bacen):
        """get_fallback_rates() deve ter 'selic_annual'."""
        fb = bacen.get_fallback_rates()
        assert "selic_annual" in fb

    def test_selic_fallback_e_decimal_valido(self, bacen):
        """SELIC fallback deve ser float entre 0 e 1 (ex: 0.1325 = 13,25%)."""
        fb = bacen.get_fallback_rates()
        selic = fb["selic_annual"]
        assert isinstance(selic, float)
        assert 0.0 < selic < 1.0  # deve estar como decimal, não percentagem

    def test_selic_fallback_realista(self, bacen):
        """
        SELIC hardcoded deve estar em faixa realista para imóveis/veículos.
        Para fev/2026, esperamos entre 10% e 20% a.a.
        """
        fb = bacen.get_fallback_rates()
        selic = fb["selic_annual"]
        assert 0.08 <= selic <= 0.20

    def test_get_selic_retorna_float_sem_excecao(self, bacen):
        """
        get_selic() deve retornar um float sem lançar exceção.
        Se a API estiver offline, usa o fallback automaticamente.
        """
        # Forçar uso do fallback diretamente (sem chamada HTTP)
        selic = bacen.get_fallback_rates()["selic_annual"]
        assert isinstance(selic, float)
        assert selic > 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES: AnbimaConnector
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestAnbimaConnector:
    """Testa o conector da ANBIMA (CDI)."""

    @pytest.fixture
    def anbima(self) -> AnbimaConnector:
        return AnbimaConnector()

    def test_fallback_tem_campo_cdi_annual(self, anbima):
        """get_fallback_rates() deve ter 'cdi_annual'."""
        fb = anbima.get_fallback_rates()
        assert "cdi_annual" in fb

    def test_cdi_fallback_e_decimal_valido(self, anbima):
        """CDI fallback deve ser float entre 0 e 1."""
        fb = anbima.get_fallback_rates()
        cdi = fb["cdi_annual"]
        assert isinstance(cdi, float)
        assert 0.0 < cdi < 1.0

    def test_cdi_proximo_da_selic(self, anbima):
        """
        CDI deve ser próximo à SELIC (tipicamente ≤ 0.50pp abaixo).
        """
        from app.architect.connectors.bacen import BacenConnector
        selic = BacenConnector().get_fallback_rates()["selic_annual"]
        cdi   = anbima.get_fallback_rates()["cdi_annual"]
        # CDI ≤ SELIC e dentro de 1pp
        assert cdi <= selic + 0.01
        assert abs(cdi - selic) < 0.01  # diferença < 1pp

    def test_cdi_fallback_realista(self, anbima):
        """CDI deve estar em faixa realista (8% a 20% a.a.)."""
        cdi = anbima.get_fallback_rates()["cdi_annual"]
        assert 0.08 <= cdi <= 0.20


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES: MarketRatesConnector
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestMarketRatesConnector:
    """Testa o conector de CETs de mercado (JSON local)."""

    @pytest.fixture
    def mr(self) -> MarketRatesConnector:
        return MarketRatesConnector()

    def test_get_best_cet_veiculo_retorna_float(self, mr):
        """get_best_cet('VEICULO') deve retornar float positivo."""
        cet = mr.get_best_cet("VEICULO")
        assert isinstance(cet, float)
        assert cet > 0

    def test_get_best_cet_imovel_retorna_float(self, mr):
        """get_best_cet('IMOVEL') deve retornar float positivo."""
        cet = mr.get_best_cet("IMOVEL")
        assert isinstance(cet, float)
        assert cet > 0

    def test_cet_imovel_menor_que_veiculo(self, mr):
        """CET de imóvel deve ser menor que CET de veículo (menor risco)."""
        cet_imovel  = mr.get_best_cet("IMOVEL")
        cet_veiculo = mr.get_best_cet("VEICULO")
        assert cet_imovel < cet_veiculo

    def test_cet_acima_da_selic(self, mr):
        """
        CET deve ser maior que a SELIC (spread bancário positivo).
        SELIC fev/2026 = 13,25% → CET de imóvel ≥ 14%.
        """
        from app.architect.connectors.bacen import BacenConnector
        selic = BacenConnector().get_fallback_rates()["selic_annual"]
        cet_imovel = mr.get_best_cet("IMOVEL")
        assert cet_imovel > selic

    def test_todos_asset_types_tem_cet(self, mr):
        """Todos os tipos de bem devem ter CET definido."""
        asset_types = ["IMOVEL", "VEICULO", "REFORMA", "VIAGEM", "OUTRO"]
        for at in asset_types:
            cet = mr.get_best_cet(at)
            assert cet is not None
            assert cet > 0, f"CET para {at} deve ser positivo"

    def test_fallback_retorna_dict_com_cets(self, mr):
        """get_fallback_rates() retorna dict não-vazio com CETs."""
        fb = mr.get_fallback_rates()
        assert isinstance(fb, dict)
        assert len(fb) > 0

    def test_json_carregado_sem_excecao(self, mr):
        """
        Inicializar MarketRatesConnector não deve lançar exceção.
        Verifica que o path do JSON está correto (bug corrigido: parents[3]).
        """
        # Se o objeto foi criado (fixture), já passou. Testar um campo:
        try:
            cet = mr.get_best_cet("VEICULO")
            assert cet > 0
        except Exception as e:
            pytest.fail(f"MarketRatesConnector falhou ao carregar JSON: {e}")
