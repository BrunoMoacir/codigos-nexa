from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.opportunities.models import (
    OpportunityItem,
    OpportunitiesResponse,
    SweepPreviewRequest,
)
from app.opportunities.services.sweep import build_sweep_preview


def _opportunities(idle_amount: float = 2500.0) -> OpportunitiesResponse:
    item = OpportunityItem(
        rank=1,
        bank_name="Banco Teste",
        product_type="CDB",
        rating="AAA",
        cdi_pct=105.0,
        annual_rate_gross_pct=15.0,
        annual_rate_net_pct=12.0,
        ir_rate=0.2,
        is_exempt=False,
        min_amount=100.0,
        liquidity="daily",
        liquidity_days=0,
        monthly_gain_brl=20.0,
        annual_gain_brl=240.0,
        eligible=True,
    )
    return OpportunitiesResponse(
        user_id="demo-ana",
        idle_amount=idle_amount,
        avg_income_3m=8500.0,
        avg_expenses_3m=5000.0,
        monthly_loss_in_checking=20.0,
        cdi_annual_pct=14.65,
        opportunities=[item],
        top_opportunity=item,
        recommendation="investir",
        generated_at="2026-10-21T12:00:00Z",
    )


def test_preview_usa_idle_amount_e_exige_consentimento() -> None:
    result = build_sweep_preview(
        "demo-ana",
        _opportunities(),
        SweepPreviewRequest(),
    )

    assert result.status == "REQUIRES_CONSENT"
    assert result.executable is False
    assert result.consent_required is True
    assert result.amount == 2500.0
    assert result.source == "IDLE_AMOUNT"
    assert result.top_opportunity.bank_name == "Banco Teste"
    assert "não movimentou" in result.reason


def test_preview_permite_valor_menor_que_o_idle() -> None:
    result = build_sweep_preview(
        "demo-ana",
        _opportunities(2500.0),
        SweepPreviewRequest(amount=1000.0, holding_months=24),
    )

    assert result.amount == 1000.0
    assert result.source == "REQUESTED_AMOUNT"
    assert result.holding_months == 24


@pytest.mark.parametrize("holding_months", [0, 361])
def test_preview_rejeita_prazo_fora_do_limite(holding_months: int) -> None:
    with pytest.raises(ValidationError):
        SweepPreviewRequest(holding_months=holding_months)


@pytest.mark.parametrize("amount", [0.0, -1.0, 2500.01])
def test_preview_rejeita_valor_invalido_ou_maior_que_idle(amount: float) -> None:
    with pytest.raises(ValueError):
        build_sweep_preview(
            "demo-ana",
            _opportunities(2500.0),
            SweepPreviewRequest(amount=amount),
        )


def test_preview_indica_quando_reserva_consumiu_todo_o_idle() -> None:
    result = build_sweep_preview(
        "demo-carla",
        _opportunities(0.0),
        SweepPreviewRequest(),
    )

    assert result.status == "NO_ELIGIBLE_AMOUNT"
    assert result.amount == 0.0
    assert result.top_opportunity is None


def test_preview_indica_quando_catalogo_nao_tem_produto_elegivel() -> None:
    opportunities = _opportunities()
    opportunities.opportunities[0].eligible = False

    result = build_sweep_preview(
        "demo-ana",
        opportunities,
        SweepPreviewRequest(),
    )

    assert result.status == "NO_ELIGIBLE_AMOUNT"
    assert result.amount == 2500.0
    assert result.top_opportunity is None


def test_endpoint_de_preview_nao_persiste_snapshot(monkeypatch) -> None:
    from app.opportunities import router

    captured = {}

    def analyze(**kwargs):
        captured.update(kwargs)
        return _opportunities()

    monkeypatch.setattr(router._engine, "analyze", analyze)

    result = router.preview_sweep(
        SweepPreviewRequest(amount=1000.0),
        user_id="demo-ana",
    )

    assert result.status == "REQUIRES_CONSENT"
    assert captured == {
        "user_id": "demo-ana",
        "holding_months": 12,
        "persist_snapshot": False,
    }


def test_endpoint_converte_valor_invalido_em_http_422(monkeypatch) -> None:
    from fastapi import HTTPException
    from app.opportunities import router

    monkeypatch.setattr(router._engine, "analyze", lambda **kwargs: _opportunities())

    with pytest.raises(HTTPException) as error:
        router.preview_sweep(
            SweepPreviewRequest(amount=5000.0),
            user_id="demo-ana",
        )

    assert error.value.status_code == 422
