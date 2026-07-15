# tests/opportunities/test_router_v2_endpoints.py
"""
Rotas novas do OPP (OPP.3 + V2): as rotas estáticas /treasury-vs-cdb-vs-savings
e /products precisam vir registradas ANTES de GET /{user_id} — mesmo risco de
roteamento já coberto para /savings-vs-cdi (FastAPI casa rotas na ordem de
registro dentro do mesmo método HTTP).
"""
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.opportunities.models import (
    TreasuryComparisonEntry,
    TreasuryComparisonResponse,
)
from app.opportunities.services.treasury_comparator import TreasuryComparatorService


def _make_app():
    from app.core.security import get_current_user
    from app.opportunities.router import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: "user_test"
    return app


def _fake_treasury_response():
    entry = TreasuryComparisonEntry(
        label="Tesouro SELIC",
        investment_type="TESOURO_SELIC",
        annual_rate_gross_pct=15.0,
        annual_rate_net_pct=11.86,
        net_yield_brl=1186.0,
        ir_rate=0.20,
        is_exempt=False,
        fgc_covered=False,
        liquidity="daily",
    )
    return TreasuryComparisonResponse(
        amount=10_000.0,
        holding_months=12,
        selic_annual_pct=15.0,
        cdi_annual_pct=14.65,
        savings_annual_pct=6.17,
        entries=[entry],
        winner="Tesouro SELIC",
        winner_vs_savings_brl=569.0,
        recommendation="...",
        disclaimer="...",
        generated_at=datetime.now(timezone.utc),
    )


class TestRotasEstaticasNaoInterceptadasPorUserId:
    def test_treasury_vs_cdb_vs_savings_retorna_200(self):
        client = TestClient(_make_app())
        with patch.object(
            TreasuryComparatorService, "compare", return_value=_fake_treasury_response()
        ):
            resp = client.get("/opportunities/treasury-vs-cdb-vs-savings")
        assert resp.status_code == 200
        body = resp.json()
        assert body["winner"] == "Tesouro SELIC"
        assert body["disclaimer"]

    def test_products_retorna_catalogo_com_transparencia(self):
        client = TestClient(_make_app())
        resp = client.get("/opportunities/products")
        assert resp.status_code == 200
        body = resp.json()
        assert body["source"] in ("curated", "open_finance")
        assert body["product_count"] >= 12
        assert body["institution_count"] >= 10
        assert all("bank_name" in p for p in body["products"])

    def test_compare_inclui_disclaimer(self):
        client = TestClient(_make_app())
        resp = client.post(
            "/opportunities/compare", json={"amount": 10_000, "holding_months": 12}
        )
        assert resp.status_code == 200
        assert resp.json()["disclaimer"]
