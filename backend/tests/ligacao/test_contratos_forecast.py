"""
Contratos que o frontend consome do F1 — forecast, extrato e widget.

Cada teste aqui reprova o comportamento que existia antes da correção:
  - /forecast dava 500 para quem tinha dia negativo (negative_day = "Sim");
  - /transactions ignorava offset e devolvia em `total` o tamanho da página;
  - não havia resumo mensal, e o Organizar somava 100 lançamentos no navegador;
  - o widget dividia a margem por outro número de dias que o forecast e
    descontava o gasto do mês de uma margem que já é líquida dele.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.security import get_current_user


def _cliente(router, usuario: str) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: usuario
    return TestClient(app)


def _extrato() -> pl.DataFrame:
    # datas fixas: dois meses exatos, sem depender do dia em que o teste roda
    linhas = [
        ("t1", date(2026, 3, 10), -50.0, "padaria", "Alimentação"),
        ("t2", date(2026, 3, 10), -20.0, "cafe", "Alimentação"),
        ("t3", date(2026, 3, 5), 3000.0, "salario", "Renda"),
        ("t4", date(2026, 2, 2), -900.0, "aluguel", "Moradia"),
        ("t5", date(2026, 2, 1), 3000.0, "salario", "Renda"),
    ]
    return pl.DataFrame(
        {
            "transaction_id": [l[0] for l in linhas],
            "date": [l[1] for l in linhas],
            "amount": [l[2] for l in linhas],
            "description": [l[3] for l in linhas],
            "category": [l[4] for l in linhas],
        }
    )


# ── /forecast: primeiro dia negativo ───────────────────────────────────────

class TestPrimeiroDiaNegativo:

    def test_devolve_numero_e_data_em_vez_de_string(self):
        from app.forecast.router import primeiro_dia_negativo

        df = pl.DataFrame({
            "date": [date(2026, 10, 4), date(2026, 10, 5), date(2026, 10, 6)],
            "projected_balance": [120.0, -30.0, -80.0],
        })
        assert primeiro_dia_negativo(df) == (2, "2026-10-05")

    def test_sem_dia_negativo_e_nulo(self):
        from app.forecast.router import primeiro_dia_negativo

        df = pl.DataFrame({"date": [date(2026, 10, 4)], "projected_balance": [10.0]})
        assert primeiro_dia_negativo(df) == (None, None)

    def test_o_schema_de_resposta_aceita_o_valor(self):
        """O 500 era o ValidationError do ForecastResponse sobre 'Sim'."""
        from app.forecast.schemas_cashflow import CashflowSummaryResponse

        resumo = CashflowSummaryResponse(
            horizon_days=30, starting_balance=100.0, ending_balance=-50.0,
            worst_balance=-80.0, negative_day=2, risk_level="CRITICAL",
            total_shadow_impact=0.0, days_at_risk=29, first_negative_date="2026-10-05",
        )
        assert resumo.negative_day == 2


# ── /transactions: paginação e contagem real ──────────────────────────────

class TestTransacoesPaginadas:

    @pytest.fixture
    def cliente(self):
        from app.forecast.router_transactions import router

        usuario = f"teste-{uuid.uuid4().hex[:8]}"  # chave de cache única
        with patch("app.core.db.queries.get_transactions_for_user", return_value=_extrato()):
            yield _cliente(router, usuario), usuario

    def test_total_e_a_contagem_real_e_offset_pagina(self, cliente):
        c, u = cliente
        p1 = c.get(f"/transactions/{u}", params={"limit": 2, "offset": 0}).json()
        p2 = c.get(f"/transactions/{u}", params={"limit": 2, "offset": 2}).json()
        assert p1["total"] == 5 and p2["total"] == 5
        assert p1["has_more"] is True
        ids = [t["id"] for t in p1["transactions"] + p2["transactions"]]
        assert len(set(ids)) == 4, "páginas consecutivas não podem repetir lançamento"

    def test_ultima_pagina_diz_que_acabou(self, cliente):
        c, u = cliente
        p3 = c.get(f"/transactions/{u}", params={"limit": 2, "offset": 4}).json()
        assert len(p3["transactions"]) == 1 and p3["has_more"] is False

    def test_cada_item_traz_id_e_tipo(self, cliente):
        c, u = cliente
        itens = c.get(f"/transactions/{u}", params={"limit": 10}).json()["transactions"]
        assert {t["type"] for t in itens} == {"income", "expense"}
        assert all(t["id"] == t["transaction_id"] for t in itens)

    def test_filtro_por_tipo(self, cliente):
        c, u = cliente
        r = c.get(f"/transactions/{u}", params={"transaction_type": "income"}).json()
        assert r["total"] == 2 and all(t["amount"] > 0 for t in r["transactions"])

    def test_extrato_vazio_e_200_com_lista_vazia(self):
        from app.forecast.router_transactions import router

        u = f"vazio-{uuid.uuid4().hex[:8]}"
        with patch("app.core.db.queries.get_transactions_for_user", return_value=pl.DataFrame()):
            r = _cliente(router, u).get(f"/transactions/{u}")
        assert r.status_code == 200
        assert r.json()["transactions"] == [] and r.json()["total"] == 0


# ── /transactions/{uid}/summary ────────────────────────────────────────────

class TestResumoDoExtrato:

    def test_meses_cronologicos_totais_e_categorias(self):
        from app.forecast.router_transactions import router

        u = f"resumo-{uuid.uuid4().hex[:8]}"
        with patch("app.core.db.queries.get_transactions_for_user", return_value=_extrato()):
            d = _cliente(router, u).get(f"/transactions/{u}/summary").json()

        meses = [m["month"] for m in d["months"]]
        assert meses == sorted(meses) and len(meses) == 2
        assert d["totals"]["income"] == 6000.0
        assert d["totals"]["expenses"] == 970.0
        assert d["totals"]["savings_rate_pct"] == pytest.approx((6000 - 970) / 6000 * 100, abs=0.1)
        assert d["by_category"][0]["category"] == "Moradia"
        assert sum(c["pct"] for c in d["by_category"]) == pytest.approx(100.0, abs=0.2)
        assert d["data_as_of"] == "2026-03-10"
        assert d["period"] == {"start": "2026-02-01", "end": "2026-03-10"}


# ── /safe-to-spend e widget: fonte única ──────────────────────────────────

def _resultado_pipeline(margem: float, diaria: float, ultima: date) -> dict:
    sts = SimpleNamespace(
        safe_to_spend_total=margem, safe_to_spend_daily=diaria,
        current_balance=5000.0, risk_level="LOW",
    )
    df = pl.DataFrame({"date": [ultima], "amount": [-100.0]})
    return {
        "status": "success",
        "projections": {"safe_to_spend": sts},
        "analysis": {},
        "transactions": {"pf_pj_classified_df": df},
    }


class TestWidgetFonteUnica:

    def _widget(self, margem, diaria, ultima):
        from app.forecast import router_safe_to_spend as mod

        runner = SimpleNamespace(run_from_db=lambda **_: _resultado_pipeline(margem, diaria, ultima))
        with patch("app.runner.get_runner", return_value=runner):
            return asyncio.run(mod.get_safe_to_spend_widget(user_id=f"w-{uuid.uuid4().hex[:6]}"))

    def test_diario_igual_ao_do_forecast(self):
        w = self._widget(10674.8, 355.83, date.today())
        assert w["daily"] == 355.83

    def test_dado_velho_nao_vira_tranquilidade(self):
        w = self._widget(10674.8, 355.83, date.today() - timedelta(days=35))
        assert w["stale"] is True and w["status"] != "OK"
        assert "sincronize" in w["subline"]

    def test_margem_zero_explica_por_que(self):
        w = self._widget(0.0, 0.0, date.today())
        assert w["status"] == "CRITICO"
        assert "Sem margem segura" in w["subline"]

    def test_valor_em_formato_brasileiro(self):
        w = self._widget(40000.0, 1333.33, date.today())
        assert w["headline"].startswith("R$ 1.333")


def test_anomalias_com_mesmo_titulo_tem_ids_distintos():
    """Três 'Gasto bem acima do normal' tinham o mesmo id: dispensar um sumia com todos."""
    from datetime import datetime, timezone

    from app.forecast.router_alerts import AlertItem, _id_estavel

    def anomalia(msg):
        return AlertItem(id="x", type="SPENDING_ANOMALY", level="WARNING",
                         title="Gasto bem acima do normal", message=msg,
                         due_date=datetime.now(timezone.utc), action_url=None)

    a = _id_estavel("u1", anomalia("Gasto de R$ 144,07 em Transporte"))
    b = _id_estavel("u1", anomalia("Gasto de R$ 640,00 em Alimentação"))
    assert a != b
    assert a == _id_estavel("u1", anomalia("Gasto de R$ 144,07 em Transporte"))  # estável entre leituras
