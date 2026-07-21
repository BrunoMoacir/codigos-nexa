# tests/costs/test_open_finance_fees.py
# Baseline vivo de tarifas via Open Finance (opendata-accounts) — F5/D4
#
# A fixture _RAW reproduz a estrutura real verificada ao vivo (Santander,
# 2026-07-18): fees.priorityServices[].prices[] com value + customers.rate
# por faixa, e serviceBundles[].prices[] com monthlyFee.

import json

import pytest

from app.costs.connectors.open_finance_fees import OpenFinanceFeesConnector as C
from app.costs.market_fees_db import MarketFeesDB


def _raw(**overrides):
    raw = {
        "participant": {"brand": "Banco Teste", "name": "BANCO TESTE S.A."},
        "type": "CONTA_DEPOSITO_A_VISTA",
        "fees": {
            "priorityServices": [
                {
                    "name": "TED_PESSOAL",
                    "code": "TED_PESSOAL",
                    "prices": [
                        {"interval": "1_FAIXA", "value": "0.00", "customers": {"rate": "0.60"}},
                        {"interval": "2_FAIXA", "value": "10.00", "customers": {"rate": "0.40"}},
                    ],
                    "maximum": {"value": "24.50"},
                },
            ]
        },
        "serviceBundles": [
            {
                "name": "PADRONIZADO I",
                "prices": [
                    {"interval": "1_FAIXA", "monthlyFee": "0.00", "value": "0.00",
                     "customers": {"rate": "0.50"}},
                    {"interval": "2_FAIXA", "monthlyFee": "40.00", "value": "40.00",
                     "customers": {"rate": "0.50"}},
                ],
                "minimum": {"value": "0.00"},
                "maximum": {"value": "40.00"},
            },
        ],
    }
    raw.update(overrides)
    return raw


# ── normalização ─────────────────────────────────────────────────────────────

def test_normaliza_servico_com_preco_tipico_ponderado():
    inst = C._normalize_institution("Fallback", _raw())
    assert inst is not None
    ted = inst["services"][0]
    # 0.00×0.60 + 10.00×0.40 = 4.00
    assert ted["typical"] == pytest.approx(4.00)
    assert ted["max"] == pytest.approx(24.50)
    assert ted["code"] == "TED_PESSOAL"


def test_pacote_mensal_ponderado_e_limites():
    inst = C._normalize_institution("X", _raw())
    # monthlyFee: 0×0.5 + 40×0.5 = 20
    assert inst["monthly_package_typical"] == pytest.approx(20.0)
    assert inst["monthly_package_min"] == pytest.approx(0.0)
    assert inst["monthly_package_max"] == pytest.approx(40.0)


def test_pacote_implausivel_descartado():
    raw = _raw()
    raw["serviceBundles"][0]["prices"] = [
        {"interval": "1_FAIXA", "monthlyFee": "2000.00", "customers": {"rate": "1.0"}},
    ]
    inst = C._normalize_institution("X", raw)
    assert inst["monthly_package_typical"] is None  # > R$ 500 → dado ruim


def test_marca_canonicalizada():
    raw = _raw()
    raw["participant"] = {"brand": "ITAU UNIBANCO S A"}
    inst = C._normalize_institution("Fallback", raw)
    assert inst["bank_name"] == "Itaú"


def test_item_sem_fees_e_sem_bundles_descartado():
    assert C._normalize_institution("X", {"participant": {"brand": "Vazio"}}) is None


def test_fallback_estatico_no_formato_vivo():
    fb = C().get_fallback_rates()
    assert fb["source"] == "static"
    nubank = next(i for i in fb["institutions"] if i["bank_name"] == "Nubank")
    assert nubank["monthly_package_typical"] == 0.0


# ── MarketFeesDB com baseline vivo ───────────────────────────────────────────

@pytest.fixture
def live_baseline(tmp_path, monkeypatch):
    import app.costs.market_fees_db as fees_module

    path = tmp_path / "market_fees_live.json"
    path.write_text(json.dumps({
        "source": "open_finance",
        "institutions": [
            {"bank_name": "Banco do Brasil", "monthly_package_typical": 25.22,
             "services": []},
            {"bank_name": "Nubank", "monthly_package_typical": 0.0, "services": []},
        ],
    }))
    monkeypatch.setattr(fees_module, "_LIVE_FEES_PATH", path)
    return path


def test_market_fees_db_prefere_baseline_vivo(live_baseline):
    db = MarketFeesDB()
    assert db.live_available is True
    assert db.get_avg_for_bank("Banco do Brasil") == pytest.approx(25.22)


def test_matching_tolerante_de_nomes(live_baseline):
    db = MarketFeesDB()
    # "BB" do extrato precisa casar com "Banco do Brasil" do baseline
    assert db.get_avg_for_bank("banco do brasil s.a.") == pytest.approx(25.22)


def test_fallback_estatico_sem_arquivo(tmp_path, monkeypatch):
    import app.costs.market_fees_db as fees_module

    monkeypatch.setattr(fees_module, "_LIVE_FEES_PATH", tmp_path / "nao_existe.json")
    db = MarketFeesDB()
    assert db.live_available is False
    assert db.get_avg_for_bank("Itaú") == pytest.approx(42.90)  # tabela estática


def test_banco_fora_do_baseline_vivo_usa_estatico(live_baseline):
    db = MarketFeesDB()
    # Itaú não está no baseline vivo da fixture → cai na tabela estática
    assert db.get_avg_for_bank("Itaú") == pytest.approx(42.90)
