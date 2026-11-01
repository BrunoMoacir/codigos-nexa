import json

from app.opportunities.connectors.open_finance_products import (
    OpenFinanceProductsConnector,
)


def test_fonte_suplementar_normaliza_e_marca_produto(tmp_path, monkeypatch) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "products": [
                    {
                        "bank_name": "Corretora Externa",
                        "product_type": "RDB",
                        "cdi_pct": 112,
                        "min_amount": 100,
                        "liquidity_days": 1,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXA_SUPPLEMENTAL_CATALOG_PATH", str(catalog))

    products = OpenFinanceProductsConnector._load_supplemental_catalog()

    assert products[0]["product_type"] == "CDB"
    assert products[0]["data_source"] == "supplemental"
    assert products[0]["liquidity"] == "daily"


def test_fonte_suplementar_descarta_oferta_invalida(tmp_path, monkeypatch) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps({"products": [{"bank_name": "Sem taxa", "product_type": "CDB"}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXA_SUPPLEMENTAL_CATALOG_PATH", str(catalog))

    assert OpenFinanceProductsConnector._load_supplemental_catalog() == []


def test_fonte_suplementar_e_open_finance_sao_mescladas(monkeypatch) -> None:
    supplemental = [
        {
            "bank_name": "Corretora Externa",
            "product_type": "CDB",
            "cdi_pct": 112.0,
            "liquidity": "daily",
            "liquidity_days": 1,
            "min_amount": 1.0,
        }
    ]
    monkeypatch.setattr(
        OpenFinanceProductsConnector,
        "_load_supplemental_catalog",
        classmethod(lambda cls: supplemental),
    )
    monkeypatch.setattr(
        "app.opportunities.connectors.open_finance_products._MIN_PRODUCTS_FOR_LIVE",
        1,
    )
    connector = OpenFinanceProductsConnector()
    monkeypatch.setattr(connector, "_discover_endpoints", lambda: [("Banco", "url")])
    monkeypatch.setattr(connector, "_fetch_institution", lambda *_: [])

    result = connector.fetch_rates()

    assert result["source"] == "open_finance+supplemental"
    assert result["products"] == supplemental
