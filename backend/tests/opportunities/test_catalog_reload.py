# tests/opportunities/test_catalog_reload.py
"""
Invalidação do catálogo do BankComparator: instâncias singleton (router)
precisam enxergar o product_catalog.json novo gravado pelo job diário
sem reiniciar o processo (mtime + TTL de segurança).
"""
import json

import app.opportunities.services.bank_comparator as bc_module
from app.opportunities.services.bank_comparator import BankComparator


def _write_catalog(path, cdi_pct: float):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "updated_at": "2026-07-04",
        "source": "open_finance",
        "products": [{
            "bank_name": "Banco Teste",
            "product_type": "CDB",
            "cdi_pct": cdi_pct,
            "min_amount": 1.0,
            "liquidity": "daily",
            "liquidity_days": 1,
            "rating": "N/A",
        }],
    }), encoding="utf-8")


class TestCatalogReload:
    def test_novo_catalogo_e_percebido_sem_recriar_instancia(self, tmp_path, monkeypatch):
        live = tmp_path / "product_catalog.json"
        monkeypatch.setattr(bc_module, "_LIVE_CATALOG_PATH", live)

        comparator = BankComparator()  # nasce com o catálogo curado (live não existe)
        before = comparator.rank(amount=1_000, holding_months=12, cdi_annual=0.1465)
        assert not any(i.bank_name == "Banco Teste" for i in before)

        _write_catalog(live, cdi_pct=120.0)
        comparator._catalog_loaded_at = 0.0  # simula TTL expirado (15 min)

        after = comparator.rank(amount=1_000, holding_months=12, cdi_annual=0.1465)
        assert [i.bank_name for i in after] == ["Banco Teste"]

    def test_mtime_alterado_recarrega_apos_ttl(self, tmp_path, monkeypatch):
        live = tmp_path / "product_catalog.json"
        _write_catalog(live, cdi_pct=100.0)
        monkeypatch.setattr(bc_module, "_LIVE_CATALOG_PATH", live)

        comparator = BankComparator()
        first = comparator.rank(amount=1_000, holding_months=12, cdi_annual=0.1465)
        assert first[0].cdi_pct == 100.0

        _write_catalog(live, cdi_pct=115.0)
        import os
        os.utime(live, (live.stat().st_atime, live.stat().st_mtime + 10))
        comparator._catalog_loaded_at = 0.0

        second = comparator.rank(amount=1_000, holding_months=12, cdi_annual=0.1465)
        assert second[0].cdi_pct == 115.0

    def test_dentro_do_ttl_nao_recarrega(self, tmp_path, monkeypatch):
        live = tmp_path / "product_catalog.json"
        _write_catalog(live, cdi_pct=100.0)
        monkeypatch.setattr(bc_module, "_LIVE_CATALOG_PATH", live)

        comparator = BankComparator()
        comparator.rank(amount=1_000, holding_months=12, cdi_annual=0.1465)

        _write_catalog(live, cdi_pct=115.0)  # TTL ainda válido — não deve reler
        again = comparator.rank(amount=1_000, holding_months=12, cdi_annual=0.1465)
        assert again[0].cdi_pct == 100.0
