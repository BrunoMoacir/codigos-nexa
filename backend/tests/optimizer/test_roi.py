# tests/optimizer/test_roi.py
# Testes para M2.4 — ROI do Cartão Atual ("Sua anuidade está se pagando?")

import pytest
from app.optimizer.simulator import CardSimulator
from app.optimizer.models import (
    CardRecord, CardType, CardFlag, WaiverRules, BenefitTag,
    CardROIVerdict, CurrentCardROI,
)
from app.optimizer.profiler import UserProfile


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _cashback_card(
    base_annuity: float = 0.0,
    threshold: float | None = None,
    waiver_type: str | None = None,
) -> CardRecord:
    if waiver_type is None:
        waiver_type = "spend_threshold" if threshold else ("always_free" if base_annuity == 0.0 else "none")
    return CardRecord(
        card_id="inter_black",
        name="Inter Black",
        issuer="Banco Inter",
        flag=CardFlag.VISA,
        card_type=CardType.CASHBACK,
        public_target="premium",
        min_income=12000.0,
        requires_proof_of_income=False,
        secured_card=False,
        prepaid=False,
        consigned=False,
        base_annuity=base_annuity,
        waiver_rules=WaiverRules(
            type=waiver_type,
            threshold=threshold,
            description="Regra de isenção",
        ),
        cashback_pct=0.01,
        benefit_tags=[BenefitTag.CASHBACK],
        last_updated="2026-01-01",
    )


def _profile(monthly_spend: float = 2000.0) -> UserProfile:
    return UserProfile(
        monthly_avg_spend=monthly_spend,
        spend_by_category={"alimentacao": monthly_spend * 0.4, "lazer": monthly_spend * 0.2},
        spend_by_source={"credit": monthly_spend},
        international_spend_monthly=0.0,
        travel_spend_monthly=0.0,
        committed_percentage=0.0,
        data_coverage_months=3,
        spending_stability=0.8,
        estimated_monthly_income=6000.0,
    )


# ── Testes unitários do CardSimulator ─────────────────────────────────────────

def test_roi_positive_free_card():
    """Cartão sem anuidade + cashback → net_roi positivo → VALE_A_PENA."""
    card = _cashback_card(base_annuity=0.0)
    profile = _profile(monthly_spend=2000.0)
    roi = CardSimulator().calculate_current_card_roi(card, profile)

    assert roi.card_id == "inter_black"
    assert roi.annuity_paid == 0.0
    assert roi.annuity_waived is True
    assert roi.reward_value_generated > 0  # 1% de 24k = R$ 240
    assert roi.net_roi > 0
    assert roi.verdict == CardROIVerdict.VALE_A_PENA
    assert "isenta" in roi.explanation.lower() or "not vale" not in roi.explanation.lower()


def test_roi_negative_high_annuity():
    """Anuidade alta com pouco gasto → net_roi muito negativo → NAO_VALE."""
    card = _cashback_card(base_annuity=2856.0, waiver_type="none")  # sem regra de isenção
    profile = _profile(monthly_spend=1500.0)   # cashback = 1500*12*0.01 = R$180
    roi = CardSimulator().calculate_current_card_roi(card, profile)

    assert roi.annuity_paid == 2856.0
    assert roi.annuity_waived is False
    assert roi.net_roi < -200   # 180 - 2856 = -2676
    assert roi.verdict == CardROIVerdict.NAO_VALE
    assert "prejuízo" in roi.explanation


def test_roi_marginal():
    """Anuidade pequena, pouco cashback → MARGINAL (anuidade=type=none, não isenta)."""
    card = _cashback_card(base_annuity=100.0, waiver_type="none")  # R$100/ano
    profile = _profile(monthly_spend=500.0)  # cashback = 500*12*0.01 = R$60/ano
    roi = CardSimulator().calculate_current_card_roi(card, profile)

    # net_roi = 60 - 100 = -40 → entre -200 e 0 → MARGINAL
    assert -200 < roi.net_roi < 0
    assert roi.verdict == CardROIVerdict.MARGINAL


def test_roi_spend_needed_for_waiver():
    """Calcula quanto falta gastar por mês para isentar anuidade."""
    # threshold = R$36.000/ano → R$ 3.000/mês
    card = _cashback_card(base_annuity=2856.0, threshold=36_000.0)
    profile = _profile(monthly_spend=2000.0)
    roi = CardSimulator().calculate_current_card_roi(card, profile)

    assert roi.annuity_waived is False
    assert roi.spend_needed_for_waiver is not None
    # Precisa de R$ 3.000/mês mas só gasta R$ 2.000 → falta R$ 1.000
    assert abs(roi.spend_needed_for_waiver - 1000.0) < 1.0


def test_roi_already_waived_no_spend_needed():
    """Gasto supera threshold → já isento → spend_needed = None."""
    card = _cashback_card(base_annuity=2856.0, threshold=18_000.0)  # threshold R$ 1.500/mês
    profile = _profile(monthly_spend=2000.0)
    roi = CardSimulator().calculate_current_card_roi(card, profile)

    assert roi.annuity_waived is True
    assert roi.spend_needed_for_waiver is None or roi.spend_needed_for_waiver == 0.0


def test_roi_benefit_audit_unused_travel():
    """Usuário sem viagens → benefícios de viagem marcados como não usados."""
    from app.optimizer.models import BenefitTag
    card = _cashback_card()
    card = card.model_copy(update={"benefit_tags": [BenefitTag.LOUNGE, BenefitTag.TRAVEL]})
    profile = _profile()
    # travel_spend_monthly = 0 → ambos devem estar em benefits_unused

    roi = CardSimulator().calculate_current_card_roi(card, profile)
    assert len(roi.benefits_unused) >= 1
    # Lounge não é usado (travel = 0)
    assert any("VIP" in b or "viagem" in b.lower() for b in roi.benefits_unused)


def test_roi_explanation_not_empty():
    """Explicação em linguagem natural deve ser sempre preenchida."""
    card = _cashback_card(base_annuity=1200.0)
    profile = _profile(monthly_spend=3000.0)
    roi = CardSimulator().calculate_current_card_roi(card, profile)
    assert len(roi.explanation) > 20


# ── Testes da API endpoint ────────────────────────────────────────────────────

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.optimizer.router import router

_app = FastAPI()
_app.include_router(router)
_client = TestClient(_app)


def test_api_roi_with_monthly_spend_override():
    """API aceita monthly_spend como override e retorna ROI sem banco de dados."""
    # nubank_roxinho é um dos cartões reais no knowledge_cards.json
    # Primeiro descobrimos um card_id válido
    cards_response = _client.get("/optimizer/cards")
    assert cards_response.status_code == 200
    cards = cards_response.json()["cards"]
    first_card_id = cards[0]["card_id"]

    response = _client.get(
        f"/optimizer/roi/{first_card_id}",
        params={"user_id": "test_user", "monthly_spend": 3000}
    )
    assert response.status_code == 200
    data = response.json()
    assert "net_roi" in data
    assert "verdict" in data
    assert data["verdict"] in ("VALE_A_PENA", "MARGINAL", "NAO_VALE")
    assert "explanation" in data


def test_api_roi_card_not_found():
    """Cartão inexistente retorna 404."""
    response = _client.get(
        "/optimizer/roi/cartao_invalido_xpto",
        params={"user_id": "test_user", "monthly_spend": 2000}
    )
    assert response.status_code == 404


def test_api_roi_no_transactions_no_spend():
    """Sem monthly_spend mas passando user_id desconhecido deve retornar 422 ou 404."""
    # Sem monthly_spend e sem dados reais de transacoes para um user_id inventado
    cards_response = _client.get("/optimizer/cards")
    first_card_id = cards_response.json()["cards"][0]["card_id"]

    response = _client.get(
        f"/optimizer/roi/{first_card_id}"
        # SEM monthly_spend e SEM user_id que tenha dados no banco de test
        # Como o banco de test provavelmente nao tem a tabela, retorna 422
    )
    # 422 porque user_id e obrigatorio
    assert response.status_code == 422


class _MockEmptyConnection:
    def execute(self, *args, **kwargs):
        import polars as pl
        class _R:
            def pl(self):
                return pl.DataFrame()
        return _R()
    def close(self): pass
