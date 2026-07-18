# tests/opportunities/test_open_finance_connector_v3.py
# V3 (F8) — normalização do spec REAL do opendata-investments v1,
# canonicalização de marca, dedupe, flag promocional e paginação.
#
# A fixture _RAW_SPEC reproduz a estrutura verificada ao vivo (Nubank/BB,
# 2026-07-18): taxa em index.issueRemunerationRate.prices[] como fração do
# CDI ponderada por operationRate, condições em investmentConditions.

import pytest

from app.opportunities.connectors.open_finance_products import (
    OpenFinanceProductsConnector as C,
)
from app.opportunities.services.bank_names import canonical_brand


def _raw_spec(**overrides):
    raw = {
        "participant": {"brand": "Nubank", "name": "Nu Financeira S.A.", "cnpjNumber": "30680829000143"},
        "issuerInstitutionName": "NU PAGAMENTOS S.A.",
        "investmentType": "CDB",
        "index": {
            "indexer": "CDI",
            "issueRemunerationRate": {
                "prices": [
                    {"interval": "1_FAIXA", "value": "1.000000", "operationRate": "0.70"},
                    {"interval": "2_FAIXA", "value": "0.000000", "operationRate": "0.00"},
                    {"interval": "3_FAIXA", "value": "1.100000", "operationRate": "0.30"},
                ],
                "minimum": "0.000000",
                "maximum": "1.350000",
            },
        },
        "investmentConditions": {
            "minimumAmount": "100.00",
            "redemptionTerm": "DATA_VENCIMENTO",
            "expirationPeriod": "361_1080",
            "gracePeriod": "1_360",
        },
        "targetAudience": "PESSOA_NATURAL",
    }
    raw.update(overrides)
    return raw


# ── Normalização spec-first ──────────────────────────────────────────────────

def test_normalize_spec_real_taxa_ponderada():
    p = C._normalize_product("Fallback", _raw_spec())
    assert p is not None
    # média ponderada: (1.0*0.7 + 1.1*0.3) / 1.0 = 1.03 → 103%
    assert p["cdi_pct"] == pytest.approx(103.0, abs=0.01)
    assert p["cdi_pct_max"] == pytest.approx(135.0)
    assert p["bank_name"] == "Nubank"
    assert p["product_type"] == "CDB"
    assert p["min_amount"] == 100.0


def test_normalize_expiration_period_vira_liquidez():
    p = C._normalize_product("X", _raw_spec())
    # DATA_VENCIMENTO + "361_1080" → piso 361 dias → janela 12m
    assert p["liquidity_days"] == 361
    assert p["liquidity"] == "12m"


def test_normalize_resgate_diario():
    raw = _raw_spec()
    raw["investmentConditions"]["redemptionTerm"] = "DIARIA"
    p = C._normalize_product("X", raw)
    assert p["liquidity"] == "daily"
    assert p["liquidity_days"] == 1


def test_normalize_descarta_pessoa_juridica():
    assert C._normalize_product("X", _raw_spec(targetAudience="PESSOA_JURIDICA")) is None


def test_normalize_descarta_indexador_nao_cdi():
    raw = _raw_spec()
    raw["index"]["indexer"] = "IPCA"
    assert C._normalize_product("X", raw) is None


def test_normalize_lci_isenta_e_rdb_vira_cdb():
    lci = C._normalize_product("X", _raw_spec(investmentType="LCI"))
    assert lci["is_tax_exempt"] is True
    rdb = C._normalize_product("X", _raw_spec(investmentType="RDB"))
    assert rdb["product_type"] == "CDB"


def test_normalize_flag_promocional_acima_130():
    raw = _raw_spec()
    raw["index"]["issueRemunerationRate"]["prices"] = [
        {"interval": "1_FAIXA", "value": "2.000000", "operationRate": "1.00"},
    ]
    p = C._normalize_product("X", raw)
    assert p["cdi_pct"] == pytest.approx(200.0)
    assert p.get("promotional") is True


def test_normalize_taxa_implausivel_descartada():
    raw = _raw_spec()
    raw["index"]["issueRemunerationRate"]["prices"] = [
        {"interval": "1_FAIXA", "value": "2.500000", "operationRate": "1.00"},
    ]
    assert C._normalize_product("X", raw) is None  # 250% > teto de plausibilidade


# ── Canonicalização de marca ─────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("ITAU UNIBANCO S A", "Itaú"),
    ("Itau Unibanco S.A.", "Itaú"),
    ("MERCADO CREDITO", "Mercado Pago"),
    ("BANCO SAFRA S/A", "Banco Safra"),
    ("BANCO DE BRASILIA S/A", "BRB"),
    ("Nu Financeira S.A. - Sociedade de Credito, Financiamento e Investimento", "Nubank"),
    ("STONE PAGAMENTOS S.A.", "Stone"),
])
def test_canonical_brand_conhece_marcas(raw, expected):
    assert canonical_brand(raw) == expected


def test_canonical_brand_limpa_desconhecidos():
    assert canonical_brand("BANCO XYZ FANTASIA S.A.") == "Banco Xyz Fantasia"


# ── Dedupe ───────────────────────────────────────────────────────────────────

def test_dedupe_mantem_melhor_taxa_por_banco_tipo_liquidez():
    base = {"product_type": "CDB", "liquidity": "daily", "min_amount": 1.0}
    products = [
        {**base, "bank_name": "Itaú", "cdi_pct": 100.0},
        {**base, "bank_name": "ITAÚ", "cdi_pct": 105.0},
        {**base, "bank_name": "Itaú", "cdi_pct": 102.0, "liquidity": "12m"},
    ]
    result = C._dedupe(products)
    daily = [p for p in result if p["liquidity"] == "daily"]
    assert len(daily) == 1 and daily[0]["cdi_pct"] == 105.0
    assert len(result) == 2  # daily + 12m


# ── Paginação ────────────────────────────────────────────────────────────────

def test_fetch_institution_segue_next_e_evita_loop(monkeypatch):
    calls = []

    class FakeResp:
        def __init__(self, payload):
            self._p = payload
        def raise_for_status(self): ...
        def json(self): return self._p

    class FakeClient:
        def __init__(self, *a, **k): ...
        def __enter__(self): return self
        def __exit__(self, *a): ...
        def get(self, url, **k):
            calls.append(url)
            if len(calls) == 1:
                return FakeResp({"data": [_raw_spec()], "links": {"next": "http://x/page2"}})
            # página 2 aponta next para si mesma (loop) — deve parar
            return FakeResp({"data": [_raw_spec()], "links": {"next": "http://x/page2"}})

    import httpx
    monkeypatch.setattr(httpx, "Client", FakeClient)
    products = C()._fetch_institution("Nubank", "http://x/page1")
    assert len(calls) == 2          # page1 + page2, sem loop infinito
    assert len(products) == 2
