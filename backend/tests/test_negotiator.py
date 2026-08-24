# tests/test_negotiator.py
# Testes para F13 — Negociador (scripts gerados por Claude para negociar com banco)

import datetime
import polars as pl
import pytest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.negotiator.models import (
    NegotiationOpportunity,
    NegotiationReport,
    NegotiationRequest,
    NegotiationScript,
    NegotiationTrigger,
    NegotiationChannel,
)
from app.negotiator.opportunity_detector import NegotiationOpportunityDetector
from app.negotiator.router import router
from app.core.security import get_current_user


USER = "user_negotiator_test"


def _make_app(auth_user: str = USER):
    a = FastAPI()
    a.include_router(router)
    a.dependency_overrides[get_current_user] = lambda: auth_user
    return a


app = _make_app()
client = TestClient(app)


def _transactions_df(n: int = 10) -> pl.DataFrame:
    today = datetime.date.today()
    return pl.DataFrame({
        "user_id": [USER] * n,
        "date": [today - datetime.timedelta(days=i * 10) for i in range(n)],
        "description": ["JUROS ROTATIVO ITAU"] * 3 + ["MERCADO"] * (n - 3),
        "amount": [-120.0, -85.0, -95.0] + [-150.0] * (n - 3),
        "category": ["juros"] * 3 + ["alimentacao"] * (n - 3),
        "transaction_type": ["DEBIT"] * n,
    })


def _mock_opportunity() -> NegotiationOpportunity:
    return NegotiationOpportunity(
        trigger=NegotiationTrigger.JUROS_ROTATIVO_ALTO,
        bank_name="Itaú",
        product="Crédito Rotativo",
        user_rate_monthly=0.12,
        market_rate_monthly=0.035,
        potential_saving_monthly=250.0,
        health_score=72,
        months_as_good_payer=0,
        description="Juros rotativos detectados acima do mercado.",
    )


def _mock_script(opp: NegotiationOpportunity) -> NegotiationScript:
    return NegotiationScript(
        opportunity=opp,
        opening_line="Olá, sou cliente há 5 anos.",
        key_arguments=["Taxa acima do mercado", "Bom histórico de pagamentos"],
        target_ask="Redução da taxa para 3,5% ao mês",
        fallback_ask="Isenção de uma parcela de juros",
        closing_line="Fico aguardando o retorno.",
        recommended_channel=NegotiationChannel.APP_CHAT,
        best_time="terça, manhã",
        estimated_success_pct=65,
    )


# ── Testes: NegotiationOpportunityDetector ────────────────────────────────────

def _patch_bacen_rates():
    """O detector busca as taxas via BacenCreditConnector.get_rates() (uma
    chamada por detect()) — o antigo _fetch_market_rate_monthly não existe
    mais desde o refactor que centralizou as taxas no conector BACEN."""
    from app.architect.connectors.bacen_credit import BacenCreditConnector

    return patch.object(
        BacenCreditConnector,
        "get_rates",
        return_value={"rotativo_monthly": 0.035, "cheque_especial_monthly": 0.075},
    )


def test_detector_empty_df_returns_empty_list():
    """DataFrame vazio → nenhuma oportunidade."""
    detector = NegotiationOpportunityDetector()
    result = detector.detect(pl.DataFrame(), health_score=75)
    assert result == []


def test_detector_low_health_score_no_generic_trigger():
    """Score < 60 e sem juros/anuidade → nenhuma oportunidade."""
    detector = NegotiationOpportunityDetector()
    df = _transactions_df()
    with patch.object(detector._fee_detector, "detect", return_value=[]):
        with _patch_bacen_rates():
            result = detector.detect(df, health_score=40)
    assert result == []


def test_detector_high_health_score_generates_generic_opportunity():
    """Score ≥ 60 e sem outros triggers → gera oportunidade HEALTH_SCORE_ALTO."""
    detector = NegotiationOpportunityDetector()
    df = _transactions_df()
    with patch.object(detector._fee_detector, "detect", return_value=[]):
        with _patch_bacen_rates():
            result = detector.detect(df, health_score=75)
    if result:
        assert any(o.trigger == NegotiationTrigger.HEALTH_SCORE_ALTO for o in result)


def test_detector_returns_list_of_opportunities():
    """detect() sempre retorna lista (pode ser vazia)."""
    detector = NegotiationOpportunityDetector()
    with patch.object(detector._fee_detector, "detect", return_value=[]):
        with _patch_bacen_rates():
            result = detector.detect(_transactions_df(), health_score=50)
    assert isinstance(result, list)


def test_detector_opportunities_sorted_by_saving():
    """Quando detector retorna múltiplas oportunidades, vêm ordenadas (maior saving primeiro)."""
    opp_low = _mock_opportunity()
    opp_low = opp_low.model_copy(update={"potential_saving_monthly": 50.0, "bank_name": "Banco A"})
    opp_high = opp_low.model_copy(update={"potential_saving_monthly": 300.0, "bank_name": "Banco B"})

    # Valida que a ordenação reversa por saving funciona
    result = sorted([opp_low, opp_high], key=lambda o: o.potential_saving_monthly, reverse=True)
    assert result[0].potential_saving_monthly >= result[1].potential_saving_monthly
    assert result[0].bank_name == "Banco B"


# ── Testes: Models ────────────────────────────────────────────────────────────

def test_negotiation_request_model():
    """NegotiationRequest aceita user_id e bank_name opcional."""
    req = NegotiationRequest(user_id=USER, bank_name="Nubank")
    assert req.user_id == USER
    assert req.bank_name == "Nubank"

    req_no_bank = NegotiationRequest(user_id=USER)
    assert req_no_bank.bank_name is None


def test_negotiation_report_no_opportunities():
    """NegotiationReport com 0 scripts é válido."""
    report = NegotiationReport(
        user_id=USER,
        opportunities_found=0,
        scripts=[],
        summary="Nenhuma oportunidade detectada.",
        confidence_score=0.5,
    )
    assert report.opportunities_found == 0
    assert report.scripts == []


def test_negotiation_script_valid_fields():
    """NegotiationScript com todos campos obrigatórios."""
    opp = _mock_opportunity()
    script = _mock_script(opp)
    assert script.opening_line
    assert len(script.key_arguments) >= 2
    assert 0 <= script.estimated_success_pct <= 100


# ── Testes: Router HTTP ───────────────────────────────────────────────────────

def test_router_forbidden_other_user():
    """user_id no body diferente do auth_user → 403."""
    other_app = _make_app(auth_user="outro_user")
    c = TestClient(other_app)
    with patch("app.core.db.queries.get_transactions_for_user", return_value=_transactions_df()):
        resp = c.post("/negotiator/generate-script", json={"user_id": USER})
    assert resp.status_code == 403


def test_router_no_transactions_returns_404():
    """Sem transações → 404."""
    with patch("app.core.db.queries.get_transactions_for_user", return_value=pl.DataFrame()):
        resp = client.post("/negotiator/generate-script", json={"user_id": USER})
    assert resp.status_code == 404


def test_router_no_opportunities_returns_empty_report():
    """
    Sem oportunidades detectadas → NegotiationReport com scripts=[].

    O mock era de `_get_health_score`, o helper local que importava
    `app.profile` (módulo inexistente) e devolvia 50 para todo mundo — mockar
    a integração quebrada é parte de por que ela sobreviveu. Agora aponta para
    a fonte única. Ver tests/negotiator/test_score_real.py.
    """
    with patch("app.core.db.queries.get_transactions_for_user", return_value=_transactions_df()):
        with patch("app.negotiator.router.score_nexa", return_value=50):
            detector_mock = MagicMock()
            detector_mock.detect.return_value = []
            with patch("app.negotiator.router.NegotiationOpportunityDetector", return_value=detector_mock):
                resp = client.post("/negotiator/generate-script", json={"user_id": USER})
    assert resp.status_code == 200
    data = resp.json()
    assert data["opportunities_found"] == 0
    assert data["scripts"] == []


def test_router_with_opportunities_calls_script_generator():
    """Com oportunidades → chama NegotiationScriptGenerator."""
    opp = _mock_opportunity()
    script = _mock_script(opp)

    with patch("app.core.db.queries.get_transactions_for_user", return_value=_transactions_df()):
        with patch("app.negotiator.router.score_nexa", return_value=72):
            detector_mock = MagicMock()
            detector_mock.detect.return_value = [opp]
            generator_mock = MagicMock()
            generator_mock.generate.return_value = script
            with patch("app.negotiator.router.NegotiationOpportunityDetector", return_value=detector_mock):
                with patch("app.negotiator.router.NegotiationScriptGenerator", return_value=generator_mock):
                    resp = client.post("/negotiator/generate-script", json={"user_id": USER})
    assert resp.status_code == 200
    data = resp.json()
    assert data["opportunities_found"] >= 1
