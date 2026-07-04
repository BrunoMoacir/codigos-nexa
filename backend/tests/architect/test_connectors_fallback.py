"""
tests/architect/test_connectors_fallback.py

Testa a cadeia de fallback de 3 níveis dos conectores de taxas:
    Nível 1: fonte primária (BCB SGS / IBGE)
    Nível 2: fonte secundária (série alternativa / derivação)
    Nível 3: hardcoded estático

Usa unittest.mock para forçar falhas nas fontes sem fazer requisições reais.
"""

import pytest
from unittest.mock import patch, MagicMock

import httpx

from app.architect.connectors.base import BaseConnector, ConnectorError
from app.architect.connectors.bacen import BacenConnector
from app.architect.connectors.anbima import AnbimaConnector
from app.architect.connectors.ipca import IPCAConnector
from app.architect.connectors.market_rates import MarketRatesConnector

# Importados para que patch.object funcione na classe (lazy imports dentro dos métodos)
import app.architect.connectors.anbima as _anbima_mod
import app.architect.connectors.market_rates as _market_mod


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _fresh_connector(cls, **kwargs):
    """Retorna instância do conector sem cache — evita interferência entre testes."""
    c = cls(**kwargs)
    c.invalidate_cache()
    return c


def _mock_bcb_response(value: str) -> MagicMock:
    """Mock para httpx.Client.get retornando payload SGS."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = [{"data": "01/05/2026", "valor": value}]
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _mock_ibge_response(value: str) -> MagicMock:
    """Mock para httpx.Client.get retornando payload IBGE SIDRA."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = [{
        "resultados": [{
            "series": [{
                "localidade": {"id": "1", "nome": "Brasil"},
                "serie": {"202412": value},
            }]
        }]
    }]
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ─────────────────────────────────────────────────────────────────────
# BaseConnector — cadeia de fallback abstrata
# ─────────────────────────────────────────────────────────────────────

class TestBaseConnectorFallbackChain:

    def test_primary_success_returns_primary(self):
        connector = _fresh_connector(BacenConnector)
        with patch.object(connector, "fetch_rates", return_value={"selic_annual": 0.1500}):
            result = connector.get_rates()
        assert result["selic_annual"] == pytest.approx(0.1500)

    def test_primary_fails_secondary_used(self):
        connector = _fresh_connector(BacenConnector)
        with (
            patch.object(connector, "fetch_rates", side_effect=ConnectorError("BCB fora")),
            patch.object(connector, "fetch_rates_secondary", return_value={"selic_annual": 0.1490}),
        ):
            result = connector.get_rates()
        assert result["selic_annual"] == pytest.approx(0.1490)

    def test_primary_and_secondary_fail_hardcoded_used(self):
        connector = _fresh_connector(BacenConnector)
        with (
            patch.object(connector, "fetch_rates",           side_effect=ConnectorError("BCB fora")),
            patch.object(connector, "fetch_rates_secondary", side_effect=Exception("série 4390 fora")),
        ):
            result = connector.get_rates()
        # Hardcoded do BacenConnector é 0.1475
        assert result["selic_annual"] == pytest.approx(0.1475)

    def test_cache_hit_skips_all_sources(self):
        connector = _fresh_connector(BacenConnector)
        # Popula cache manualmente
        connector._set_cache(BacenConnector.__name__, {"selic_annual": 0.1234})
        with (
            patch.object(connector, "fetch_rates",           side_effect=Exception("não deve chamar")),
            patch.object(connector, "fetch_rates_secondary", side_effect=Exception("não deve chamar")),
        ):
            result = connector.get_rates()
        assert result["selic_annual"] == pytest.approx(0.1234)

    def test_secondary_returning_none_falls_through_to_hardcoded(self):
        connector = _fresh_connector(BacenConnector)
        with (
            patch.object(connector, "fetch_rates",           side_effect=ConnectorError("BCB fora")),
            patch.object(connector, "fetch_rates_secondary", return_value=None),
        ):
            result = connector.get_rates()
        assert "selic_annual" in result
        assert result["selic_annual"] == pytest.approx(0.1475)


# ─────────────────────────────────────────────────────────────────────
# BacenConnector — fonte secundária: SGS série 4390
# ─────────────────────────────────────────────────────────────────────

class TestBacenConnectorSecondary:

    def test_secondary_parses_selic_4390(self):
        connector = _fresh_connector(BacenConnector)
        mock_resp = _mock_bcb_response("14.75")
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.return_value = mock_resp
            result = connector.fetch_rates_secondary()
        assert result["selic_annual"] == pytest.approx(0.1475)

    def test_secondary_converts_percent_to_decimal(self):
        connector = _fresh_connector(BacenConnector)
        mock_resp = _mock_bcb_response("10.50")
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.return_value = mock_resp
            result = connector.fetch_rates_secondary()
        assert result["selic_annual"] == pytest.approx(0.1050)

    def test_primary_fails_secondary_provides_selic(self):
        connector = _fresh_connector(BacenConnector)
        mock_resp = _mock_bcb_response("14.75")
        with patch("httpx.Client") as mock_client_cls:
            # Primeira chamada (primária, série 432) falha; segunda (secundária, série 4390) sucede
            mock_client_cls.return_value.__enter__.return_value.get.side_effect = [
                httpx.ConnectError("timeout"),
                mock_resp,
            ]
            result = connector.get_rates()
        assert result["selic_annual"] == pytest.approx(0.1475)


# ─────────────────────────────────────────────────────────────────────
# BacenConnector — TR (série 226), Ticket OPP4-A
# ─────────────────────────────────────────────────────────────────────

class TestBacenConnectorTR:
    """
    fetch_rates() busca SELIC (432) e TR (226) na mesma chamada — ver nota de
    acoplamento no docstring do módulo bacen.py. get_tr_monthly() usa .get()
    defensivo porque fetch_rates_secondary() (série 4390) só cobre SELIC.
    """

    def test_fetch_rates_retorna_selic_e_tr(self):
        connector = _fresh_connector(BacenConnector)
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.side_effect = [
                _mock_bcb_response("14.75"),
                _mock_bcb_response("0.0000"),
            ]
            result = connector.fetch_rates()
        assert result["selic_annual"] == pytest.approx(0.1475)
        assert result["tr_monthly"] == pytest.approx(0.0)

    def test_tr_positiva_convertida_para_decimal(self):
        connector = _fresh_connector(BacenConnector)
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.side_effect = [
                _mock_bcb_response("14.75"),
                _mock_bcb_response("0.15"),   # 0,15% a.m.
            ]
            result = connector.fetch_rates()
        assert result["tr_monthly"] == pytest.approx(0.0015)

    def test_payload_tr_vazio_lanca_connector_error(self):
        connector = _fresh_connector(BacenConnector)
        tr_vazio = MagicMock()
        tr_vazio.json.return_value = []
        tr_vazio.raise_for_status = MagicMock()
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.side_effect = [
                _mock_bcb_response("14.75"),
                tr_vazio,
            ]
            with pytest.raises(ConnectorError):
                connector.fetch_rates()

    def test_payload_tr_malformado_lanca_connector_error(self):
        connector = _fresh_connector(BacenConnector)
        tr_malformado = MagicMock()
        tr_malformado.json.return_value = [{"data": "01/05/2026"}]  # sem "valor"
        tr_malformado.raise_for_status = MagicMock()
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.side_effect = [
                _mock_bcb_response("14.75"),
                tr_malformado,
            ]
            with pytest.raises(ConnectorError):
                connector.fetch_rates()

    def test_falha_na_tr_aciona_fallback_de_selic_tambem(self):
        """Documenta o acoplamento aceito (ver docstring do módulo): falha na
        série de TR também aciona o fallback de SELIC, mesmo que a SELIC em si
        tivesse respondido com sucesso."""
        connector = _fresh_connector(BacenConnector)
        with (
            patch("httpx.Client") as mock_client_cls,
            patch.object(connector, "fetch_rates_secondary", return_value=None),
        ):
            mock_client_cls.return_value.__enter__.return_value.get.side_effect = [
                _mock_bcb_response("14.75"),
                httpx.ConnectError("TR fora"),
            ]
            result = connector.get_rates()
        assert result["selic_annual"] == pytest.approx(0.1475)  # hardcoded, não os 14.75 buscados
        assert result["tr_monthly"] == pytest.approx(0.0)

    def test_get_tr_monthly_shorthand(self):
        connector = _fresh_connector(BacenConnector)
        with patch.object(
            connector, "fetch_rates", return_value={"selic_annual": 0.15, "tr_monthly": 0.001}
        ):
            assert connector.get_tr_monthly() == pytest.approx(0.001)

    def test_get_tr_monthly_usa_fallback_defensivo_quando_secundaria_nao_tem_tr(self):
        """fetch_rates_secondary() (série 4390) só cobre SELIC — get_tr_monthly()
        não pode lançar KeyError quando o resultado veio por esse caminho."""
        connector = _fresh_connector(BacenConnector)
        with (
            patch.object(connector, "fetch_rates", side_effect=ConnectorError("BCB fora")),
            patch.object(connector, "fetch_rates_secondary", return_value={"selic_annual": 0.1490}),
        ):
            tr = connector.get_tr_monthly()
        assert tr == pytest.approx(BacenConnector._TR_FALLBACK_MONTHLY)

    def test_get_selic_nao_quebra_com_a_mudanca(self):
        connector = _fresh_connector(BacenConnector)
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.side_effect = [
                _mock_bcb_response("14.75"),
                _mock_bcb_response("0.0"),
            ]
            selic = connector.get_selic()
        assert selic == pytest.approx(0.1475)


# ─────────────────────────────────────────────────────────────────────
# AnbimaConnector — fonte secundária: CDI derivado da SELIC
# ─────────────────────────────────────────────────────────────────────

class TestAnbimaConnectorSecondary:

    def test_secondary_derives_cdi_from_selic(self):
        connector = _fresh_connector(AnbimaConnector)
        with patch.object(BacenConnector, "get_selic", return_value=0.1475):
            result = connector.fetch_rates_secondary()
        assert result["cdi_annual"] == pytest.approx(0.1475 - 0.001, rel=1e-4)

    def test_cdi_secondary_is_always_below_selic(self):
        connector = _fresh_connector(AnbimaConnector)
        for selic in [0.10, 0.1325, 0.1475, 0.1650]:
            with patch.object(BacenConnector, "get_selic", return_value=selic):
                result = connector.fetch_rates_secondary()
            assert result["cdi_annual"] < selic

    def test_primary_fails_secondary_provides_cdi(self):
        connector = _fresh_connector(AnbimaConnector)
        with (
            patch.object(connector, "fetch_rates", side_effect=ConnectorError("BCB fora")),
            patch.object(BacenConnector, "get_selic", return_value=0.1475),
        ):
            result = connector.get_rates()
        assert result["cdi_annual"] == pytest.approx(0.1475 - 0.001, rel=1e-4)


# ─────────────────────────────────────────────────────────────────────
# IPCAConnector — fonte secundária: IBGE SIDRA
# ─────────────────────────────────────────────────────────────────────

class TestIPCAConnectorSecondary:

    def test_secondary_parses_ibge_response(self):
        connector = _fresh_connector(IPCAConnector)
        mock_resp = _mock_ibge_response("4.83")
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.return_value = mock_resp
            result = connector.fetch_rates_secondary()
        assert result["ipca_annual"] == pytest.approx(0.0483, rel=1e-3)

    def test_secondary_converts_percent_to_decimal(self):
        connector = _fresh_connector(IPCAConnector)
        mock_resp = _mock_ibge_response("3.20")
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.return_value = mock_resp
            result = connector.fetch_rates_secondary()
        assert result["ipca_annual"] == pytest.approx(0.0320, rel=1e-3)

    def test_primary_fails_secondary_provides_ipca(self):
        connector = _fresh_connector(IPCAConnector)
        mock_resp = _mock_ibge_response("4.50")
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.side_effect = [
                httpx.ConnectError("BCB timeout"),
                mock_resp,
            ]
            result = connector.get_rates()
        assert result["ipca_annual"] == pytest.approx(0.0450, rel=1e-3)

    def test_ibge_malformed_response_raises_connector_error(self):
        connector = _fresh_connector(IPCAConnector)
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"resultados": []}]  # sem series
        mock_resp.raise_for_status = MagicMock()
        with (
            patch("httpx.Client") as mock_client_cls,
            pytest.raises(ConnectorError),
        ):
            mock_client_cls.return_value.__enter__.return_value.get.return_value = mock_resp
            connector.fetch_rates_secondary()


# ─────────────────────────────────────────────────────────────────────
# MarketRatesConnector — fonte secundária: SELIC-derived CETs
# ─────────────────────────────────────────────────────────────────────

class TestMarketRatesConnectorSecondary:

    def test_secondary_produces_all_asset_types(self):
        connector = _fresh_connector(MarketRatesConnector)
        with patch.object(BacenConnector, "get_selic", return_value=0.1475):
            result = connector.fetch_rates_secondary()

        for asset in ("IMOVEL", "VEICULO", "REFORMA", "VIAGEM", "OUTRO"):
            assert f"cet_{asset}_min" in result
            assert f"cet_{asset}_avg" in result
            assert f"cet_{asset}_max" in result

    def test_secondary_cet_respects_ordering_min_lt_avg_lt_max(self):
        connector = _fresh_connector(MarketRatesConnector)
        with patch.object(BacenConnector, "get_selic", return_value=0.1475):
            result = connector.fetch_rates_secondary()

        for asset in ("IMOVEL", "VEICULO", "REFORMA", "VIAGEM", "OUTRO"):
            mn  = result[f"cet_{asset}_min"]
            avg = result[f"cet_{asset}_avg"]
            mx  = result[f"cet_{asset}_max"]
            assert mn < avg < mx, f"{asset}: min={mn} avg={avg} max={mx}"

    def test_secondary_cet_above_selic_for_all_types(self):
        selic = 0.1475
        connector = _fresh_connector(MarketRatesConnector)
        with patch.object(BacenConnector, "get_selic", return_value=selic):
            result = connector.fetch_rates_secondary()

        for asset in ("IMOVEL", "VEICULO", "REFORMA", "VIAGEM", "OUTRO"):
            assert result[f"cet_{asset}_min"] > selic, f"{asset} min deveria ser > SELIC"

    def test_secondary_imovel_cet_lower_than_veiculo(self):
        connector = _fresh_connector(MarketRatesConnector)
        with patch.object(BacenConnector, "get_selic", return_value=0.1475):
            result = connector.fetch_rates_secondary()
        assert result["cet_IMOVEL_avg"] < result["cet_VEICULO_avg"]

    def test_secondary_adjusts_when_selic_changes(self):
        connector = _fresh_connector(MarketRatesConnector)
        with patch.object(BacenConnector, "get_selic", return_value=0.1000):
            result_low = connector.fetch_rates_secondary()

        connector.invalidate_cache()
        with patch.object(BacenConnector, "get_selic", return_value=0.1500):
            result_high = connector.fetch_rates_secondary()

        assert result_high["cet_IMOVEL_avg"] > result_low["cet_IMOVEL_avg"]

    def test_primary_fails_secondary_provides_cets(self):
        connector = _fresh_connector(MarketRatesConnector)
        with (
            patch.object(connector, "fetch_rates", side_effect=ConnectorError("BCB fora")),
            patch.object(BacenConnector, "get_selic", return_value=0.1475),
        ):
            result = connector.get_rates()

        assert "cet_IMOVEL_avg" in result
        assert result["cet_IMOVEL_avg"] > 0.14
