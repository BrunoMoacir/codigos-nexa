# tests/opportunities/test_open_finance_connector.py
"""
V2 (docs/OPP.md §3.3/§7) — OpenFinanceProductsConnector: normalização do
payload de dados abertos e fallback para o catálogo curado.
"""
from unittest.mock import patch

import pytest

from app.architect.connectors.base import ConnectorError
from app.opportunities.connectors.open_finance_products import (
    OpenFinanceProductsConnector,
)


class TestNormalizacao:
    def test_produto_cdb_pos_fixado_cdi_e_normalizado(self):
        raw = {
            "participant": {"brandName": "Banco Exemplo"},
            "investmentType": "CDB",
            "remuneration": {"indexer": "CDI", "postFixedIndexerRate": 1.10},
            "minimumAmount": 500.0,
            "redemptionTerm": {"days": 1},
        }
        product = OpenFinanceProductsConnector._normalize_product("Fallback", raw)
        assert product is not None
        assert product["bank_name"] == "Banco Exemplo"
        assert product["product_type"] == "CDB"
        assert product["cdi_pct"] == pytest.approx(110.0)
        assert product["min_amount"] == 500.0
        assert product["liquidity"] == "daily"
        assert product["fgc_covered"] is True

    def test_rdb_vira_cdb(self):
        raw = {
            "investmentType": "RDB",
            "remuneration": {"indexer": "DI", "rate": 0.95},
        }
        product = OpenFinanceProductsConnector._normalize_product("Banco X", raw)
        assert product["product_type"] == "CDB"
        assert product["cdi_pct"] == pytest.approx(95.0)

    def test_lci_marca_isencao(self):
        raw = {
            "investmentType": "LCI",
            "remuneration": {"indexer": "CDI", "postFixedIndexerRate": 0.90},
        }
        product = OpenFinanceProductsConnector._normalize_product("Banco X", raw)
        assert product["is_tax_exempt"] is True

    def test_taxa_percentual_nao_e_reescalada(self):
        raw = {
            "investmentType": "CDB",
            "remuneration": {"indexer": "CDI", "rate": 102.0},
        }
        product = OpenFinanceProductsConnector._normalize_product("Banco X", raw)
        assert product["cdi_pct"] == pytest.approx(102.0)

    def test_tipo_nao_suportado_e_descartado(self):
        raw = {"investmentType": "DEBENTURE", "remuneration": {"rate": 1.0}}
        assert OpenFinanceProductsConnector._normalize_product("Banco X", raw) is None

    def test_taxa_implausivel_e_descartada(self):
        raw = {
            "investmentType": "CDB",
            "remuneration": {"indexer": "CDI", "postFixedIndexerRate": 25.0},
        }
        assert OpenFinanceProductsConnector._normalize_product("Banco X", raw) is None

    def test_sem_prazo_declarado_assume_12m(self):
        """Assumir liquidez diária seria otimista demais no ranking."""
        raw = {
            "investmentType": "CDB",
            "remuneration": {"indexer": "CDI", "postFixedIndexerRate": 1.0},
        }
        product = OpenFinanceProductsConnector._normalize_product("Banco X", raw)
        assert product["liquidity_days"] == 360
        assert product["liquidity"] == "12m"


class TestFallback:
    def test_fallback_e_o_catalogo_curado(self):
        connector = OpenFinanceProductsConnector()
        fallback = connector.get_fallback_rates()
        assert fallback["source"] == "curated"
        assert len(fallback["products"]) >= 12

    def test_get_rates_usa_fallback_quando_diretorio_falha(self):
        connector = OpenFinanceProductsConnector()
        with patch.object(
            connector, "_discover_endpoints", side_effect=ConnectorError("diretório fora")
        ):
            catalog = connector.get_rates()
        assert catalog["source"] == "curated"
        assert catalog["products"]

    def test_get_products_filtra_por_tipo(self):
        connector = OpenFinanceProductsConnector()
        with patch.object(
            connector, "_discover_endpoints", side_effect=ConnectorError("diretório fora")
        ):
            cdbs = connector.get_products("CDB")
        assert cdbs
        assert all(p["product_type"] == "CDB" for p in cdbs)

    def test_poucos_produtos_normalizados_nao_substituem_o_curado(self):
        """fetch_rates lança ConnectorError quando o catálogo vivo é raso —
        o job de refresh nunca grava um catálogo pior que o curado."""
        connector = OpenFinanceProductsConnector()
        with patch.object(connector, "_discover_endpoints", return_value=[]):
            with pytest.raises(ConnectorError):
                connector.fetch_rates()
