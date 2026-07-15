# tests/opportunities/test_savings_vs_cdi.py
"""
Ticket OPP4-C (docs/OPP4_POUPANCA_CDI_PLANO.md) — comparação genérica
poupança vs. CDI.

Duas camadas:
  1. Unidade de SavingsVsCdiService.analyze() — mocka os conectores
     (AnbimaConnector.get_cdi, BacenConnector.get_selic/get_tr_monthly),
     cobre os 4 status e os thresholds de severidade da seção 5.5 do plano.
  2. Router — confirma que GET /opportunities/savings-vs-cdi não é
     interceptado por GET /opportunities/{user_id} (risco real de
     roteamento: "savings-vs-cdi" poderia ser lido como user_id se a rota
     estática não vier registrada antes da dinâmica).
"""
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.opportunities.services.savings_vs_cdi import SavingsVsCdiService


def _service_with_mocked_rates(cdi_annual: float, selic_annual: float, tr_monthly: float):
    service = SavingsVsCdiService()
    service._anbima = type("_A", (), {"get_cdi": staticmethod(lambda: cdi_annual)})()
    service._bacen = type(
        "_B",
        (),
        {
            "get_selic": staticmethod(lambda: selic_annual),
            "get_tr_monthly": staticmethod(lambda: tr_monthly),
        },
    )()
    return service


class TestClassificacaoDeStatus:
    def test_cdi_bem_acima_da_poupanca_e_high(self):
        # CDI 14,75% vs. poupança ~6,17% (SELIC alta) — diferença grande
        service = _service_with_mocked_rates(cdi_annual=0.1475, selic_annual=0.1475, tr_monthly=0.0)
        result = service.analyze(amount_reference_brl=10_000)
        assert result.status == "BELOW_CDI"
        assert result.severity == "HIGH"
        assert result.estimated_loss_annual_brl >= 150.0

    def test_diferenca_pequena_e_near_cdi(self):
        # SELIC 7% (ramo <=8,5%) -> poupança calculada ~4,85% a.a.; CDI 5,0%
        # deixa a diferença em ~R$14,58/ano para R$10.000 (< threshold de R$30)
        service = _service_with_mocked_rates(cdi_annual=0.050, selic_annual=0.07, tr_monthly=0.0)
        result = service.analyze(amount_reference_brl=10_000)
        assert result.status in ("NEAR_CDI", "NO_ADVANTAGE")
        assert result.severity == "LOW"

    def test_poupanca_maior_ou_igual_ao_cdi_e_no_advantage(self):
        # cenário artificial (CDI baixo) só para exercitar o ramo "incoerente"
        service = _service_with_mocked_rates(cdi_annual=0.01, selic_annual=0.1475, tr_monthly=0.0)
        result = service.analyze(amount_reference_brl=10_000)
        assert result.status == "NO_ADVANTAGE"
        assert result.severity == "LOW"
        assert result.estimated_loss_annual_brl <= 0

    def test_falha_ao_buscar_taxas_e_data_unavailable(self):
        service = SavingsVsCdiService()
        with patch.object(service._anbima, "get_cdi", side_effect=Exception("BCB fora")):
            result = service.analyze(amount_reference_brl=10_000)
        assert result.status == "DATA_UNAVAILABLE"
        assert result.severity == "LOW"
        assert result.savings_annual_pct == 0.0


class TestValorDeReferencia:
    def test_default_amount_reference_e_10k(self):
        service = _service_with_mocked_rates(cdi_annual=0.1475, selic_annual=0.1475, tr_monthly=0.0)
        result = service.analyze()
        assert result.amount_reference_brl == pytest.approx(10_000.0)

    def test_perda_escala_com_o_valor_de_referencia(self):
        service = _service_with_mocked_rates(cdi_annual=0.1475, selic_annual=0.1475, tr_monthly=0.0)
        r1 = service.analyze(amount_reference_brl=10_000)
        r2 = service.analyze(amount_reference_brl=20_000)
        assert r2.estimated_loss_annual_brl == pytest.approx(r1.estimated_loss_annual_brl * 2, rel=1e-6)


class TestCamposDeTransparencia:
    def test_cdi_reference_igual_a_cdi_bruto_hoje(self):
        """Decisão registrada na doc/model: cdi_reference_annual_pct = CDI bruto por ora."""
        service = _service_with_mocked_rates(cdi_annual=0.1475, selic_annual=0.1475, tr_monthly=0.0)
        result = service.analyze()
        assert result.cdi_reference_annual_pct == pytest.approx(result.cdi_annual_pct)

    def test_estimated_loss_monthly_e_annual_dividido_por_12(self):
        # abs (não rel): monthly e annual são arredondados independentemente
        # para 2 casas na implementação, o que introduz um erro de centavos
        service = _service_with_mocked_rates(cdi_annual=0.1475, selic_annual=0.1475, tr_monthly=0.0)
        result = service.analyze()
        assert result.estimated_loss_monthly_brl == pytest.approx(
            result.estimated_loss_annual_brl / 12, abs=0.01
        )

    def test_reason_menciona_valor_de_referencia_quando_below_cdi(self):
        service = _service_with_mocked_rates(cdi_annual=0.1475, selic_annual=0.1475, tr_monthly=0.0)
        result = service.analyze(amount_reference_brl=10_000)
        assert "10.000" in result.reason or "10,000" in result.reason or "10000" in result.reason


# ─────────────────────────────────────────────────────────────────────
# Router — ordem de registro da rota estática vs. dinâmica
# ─────────────────────────────────────────────────────────────────────

def _make_app():
    from app.core.security import get_current_user
    from app.opportunities.router import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: "user_test"
    return app


class TestRotaSavingsVsCdiNaoEhInterceptadaPorUserId:
    def test_get_savings_vs_cdi_retorna_200_nao_tenta_tratar_como_user_id(self):
        """Risco real: se GET /{user_id} estivesse registrado antes de
        GET /savings-vs-cdi, esta chamada cairia lá com user_id='savings-vs-cdi'
        e provavelmente devolveria erro 500 (tenta calcular idle_amount para um
        'usuário' que é na verdade o nome da rota)."""
        app = _make_app()
        client = TestClient(app)

        with patch.object(SavingsVsCdiService, "analyze") as mock_analyze:
            from app.opportunities.models import SavingsVsCdiResult
            from datetime import datetime, timezone

            mock_analyze.return_value = SavingsVsCdiResult(
                amount_reference_brl=10_000.0,
                savings_annual_pct=6.17,
                cdi_annual_pct=14.75,
                cdi_reference_annual_pct=14.75,
                spread_pct_points=8.58,
                estimated_loss_monthly_brl=71.5,
                estimated_loss_annual_brl=858.0,
                status="BELOW_CDI",
                severity="HIGH",
                reason="teste",
                generated_at=datetime.now(timezone.utc),
            )
            resp = client.get("/opportunities/savings-vs-cdi")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "BELOW_CDI"
        # mock_analyze foi chamado com amount_reference_brl, não com um "user_id"
        mock_analyze.assert_called_once()

    def test_query_param_amount_reference_brl_e_repassado(self):
        app = _make_app()
        client = TestClient(app)

        with patch.object(SavingsVsCdiService, "analyze") as mock_analyze:
            from app.opportunities.models import SavingsVsCdiResult
            from datetime import datetime, timezone

            mock_analyze.return_value = SavingsVsCdiResult(
                amount_reference_brl=5_000.0,
                savings_annual_pct=6.17,
                cdi_annual_pct=14.75,
                cdi_reference_annual_pct=14.75,
                spread_pct_points=8.58,
                estimated_loss_monthly_brl=35.7,
                estimated_loss_annual_brl=429.0,
                status="BELOW_CDI",
                severity="MEDIUM",
                reason="teste",
                generated_at=datetime.now(timezone.utc),
            )
            resp = client.get("/opportunities/savings-vs-cdi?amount_reference_brl=5000")

        assert resp.status_code == 200
        mock_analyze.assert_called_once_with(amount_reference_brl=5000.0)
