"""
Testes de endpoint das features de retenção:
  GET /seasonality/{user_id}                (R2.c)
  GET /health-score/challenges/{user_id}    (R2.b)
  GET /purchase/checkout-context/{user_id}  (R1.a)
  GET /purchase/recent-review/{user_id}     (R1.a)
  GET /safe-to-spend/{user_id}/widget       (R1.d)

Serviços pesados são monkeypatchados; o teste valida contrato HTTP,
serialização e as regras de apresentação (verdict, status semafórico).
"""

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.security import get_current_user, require_owner

_USER = "test_user"


def _client(router) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[require_owner] = lambda: _USER
    return TestClient(app)


# ── R2.c — /seasonality ──────────────────────────────────────────────

class TestSeasonalityEndpoint:
    def test_retorna_eventos_personalizados(self, monkeypatch):
        from app.seasonality import service as svc_module
        from app.seasonality.profile_probe import SeasonalProfile
        from app.seasonality.router import router

        monkeypatch.setattr(
            svc_module, "build_profile",
            lambda uid, today=None: SeasonalProfile(is_mei=True),
        )
        # fixa a data para uma janela conhecida (15/01: IPVA + DASN + DAS)
        real_get_events = svc_module.SeasonalityService.get_events
        monkeypatch.setattr(
            svc_module.SeasonalityService, "get_events",
            lambda self, uid, today=None, profile=None: real_get_events(
                self, uid, today=date(2026, 1, 15), profile=profile
            ),
        )

        resp = _client(router).get(f"/seasonality/{_USER}")
        assert resp.status_code == 200
        body = resp.json()
        codes = {e["event_code"] for e in body["events"]}
        assert "DAS_MEI" in codes
        assert "IPVA_IPTU" in codes
        assert body["profile_signals"]["is_mei"] is True
        assert body["total"] == len(body["events"])


# ── R2.b — /health-score/challenges ──────────────────────────────────

class TestChallengesEndpoint:
    def test_sync_do_mes_corrente(self, monkeypatch):
        from app.health_score.challenge_service import Challenge, ChallengeService
        from app.health_score.router import router

        fake = Challenge(
            id="c1", user_id=_USER, challenge_type="GUARDAR_VALOR",
            month="2026-07", title="Guardar R$ 500 no mês",
            target_label="R$ 500 poupados", target_value=500.0,
            progress_value=250.0, pct_progress=50.0, status="ACTIVE",
            metadata={"monthly_income_median_brl": 5000.0},
        )
        monkeypatch.setattr(ChallengeService, "sync", lambda self, uid, today=None: [fake])
        monkeypatch.setattr(
            ChallengeService, "_completed_months", lambda self, uid: {"2026-06": 2}
        )

        resp = _client(router).get(f"/health-score/challenges/{_USER}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["completed_total"] == 2
        ch = body["challenges"][0]
        assert ch["challenge_type"] == "GUARDAR_VALOR"
        assert ch["pct_progress"] == 50.0

    def test_mes_historico_nao_altera_nada(self, monkeypatch):
        from app.health_score.challenge_service import ChallengeService
        from app.health_score.router import router

        called = {"sync": False}
        monkeypatch.setattr(
            ChallengeService, "sync",
            lambda self, uid, today=None: called.__setitem__("sync", True) or [],
        )
        monkeypatch.setattr(
            ChallengeService, "list_challenges", lambda self, uid, month: []
        )
        monkeypatch.setattr(
            ChallengeService, "_completed_months", lambda self, uid: {}
        )

        resp = _client(router).get(f"/health-score/challenges/{_USER}?month=2026-05")
        assert resp.status_code == 200
        assert called["sync"] is False

    def test_month_invalido_retorna_422(self):
        from app.health_score.router import router

        resp = _client(router).get(f"/health-score/challenges/{_USER}?month=julho")
        assert resp.status_code == 422


# ── R1.a — /purchase/checkout-context ────────────────────────────────

def _fake_recommendation(user_id: str, amount: float):
    from app.purchase.models import (
        LiquidityImpact,
        PaymentMethod,
        PaymentOption,
        PurchaseRecommendation,
    )

    pix = PaymentOption(
        method=PaymentMethod.PIX_AVISTA, label="PIX à vista",
        total_cost=amount, net_cost=amount, net_cost_real=amount,
    )
    card = PaymentOption(
        method=PaymentMethod.CARTAO_AVISTA, label="Cartão Top à vista",
        total_cost=amount, reward_value=36.0,
        net_cost=amount - 36.0, net_cost_real=amount - 36.0,
    )
    return PurchaseRecommendation(
        user_id=user_id, amount=amount, category="Eletrônicos",
        recommended_method=PaymentMethod.CARTAO_AVISTA,
        recommended_label="Cartão Top à vista",
        recommended_net_cost=amount - 36.0,
        reasoning="Cartão dá cashback.",
        options=[card, pix],
        liquidity_impact=LiquidityImpact(
            safe_to_spend_before=4000.0, safe_to_spend_after=4000.0 - amount,
            affordable=True, risk_level="LOW",
        ),
        confidence_score=0.9,
    )


class TestCheckoutContextEndpoint:
    def test_verdict_e_opcoes_compactas(self, monkeypatch):
        import app.purchase.router as purchase_router_module
        from app.purchase.router import router

        monkeypatch.setattr(
            purchase_router_module.PurchaseAdvisor, "analyze",
            lambda self, req: _fake_recommendation(req.user_id, req.amount),
        )
        resp = _client(router).get(
            f"/purchase/checkout-context/{_USER}",
            params={"amount": 3000, "category": "Eletrônicos"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["recommended_method"] == "CARTAO_AVISTA"
        assert body["savings_vs_worst"] == pytest.approx(36.0)
        assert "Cartão Top à vista" in body["verdict"]
        assert len(body["options"]) == 2
        assert body["affordable"] is True

    def test_amount_obrigatorio(self):
        from app.purchase.router import router

        resp = _client(router).get(f"/purchase/checkout-context/{_USER}")
        assert resp.status_code == 422


class TestRecentReviewEndpoint:
    def test_agrega_total_deixado_na_mesa(self, monkeypatch):
        from app.notifications.notifier import PurchaseFollowupInput
        from app.purchase.post_purchase import PostPurchaseAnalyzer
        from app.purchase.router import router

        followup = PurchaseFollowupInput(
            transaction_id="tx1", merchant="magalu", amount=2500.0,
            category="Eletrônicos", purchase_date="2026-07-05",
            paid_method_label="PIX à vista",
            best_method_label="Cartão Top à vista",
            potential_savings_brl=30.0,
        )
        captured = {}

        def _fake_detect(self, uid, today=None, use_seen_marker=True):
            captured["use_seen_marker"] = use_seen_marker
            return [followup]

        monkeypatch.setattr(PostPurchaseAnalyzer, "detect", _fake_detect)
        resp = _client(router).get(f"/purchase/recent-review/{_USER}")
        # sob demanda: o endpoint deve ignorar o marcador do scheduler
        assert captured["use_seen_marker"] is False
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["total_savings_missed_brl"] == pytest.approx(30.0)
        assert body["reviews"][0]["merchant"] == "magalu"


# ── R1.d — /safe-to-spend/{user_id}/widget ───────────────────────────

class TestWidgetEndpoint:
    def _client_with_sts(self, monkeypatch, sts: dict) -> TestClient:
        import app.forecast.router_safe_to_spend as sts_module

        async def _fake_sts(user_id: str):
            return sts

        monkeypatch.setattr(sts_module, "get_safe_to_spend", _fake_sts)
        return _client(sts_module.router)

    def test_status_ok(self, monkeypatch):
        client = self._client_with_sts(monkeypatch, {
            "safe_to_spend_total": 3000.0, "spent_to_date": 900.0,
            "pct_consumed": 30.0, "risk_level": "LOW",
        })
        resp = client.get(f"/safe-to-spend/{_USER}/widget")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "OK"
        assert body["color"] == "#22c55e"
        assert body["remaining_month"] == pytest.approx(2100.0)
        assert body["daily"] > 0
        assert "R$" in body["headline"]

    def test_status_atencao_por_pct(self, monkeypatch):
        client = self._client_with_sts(monkeypatch, {
            "safe_to_spend_total": 3000.0, "spent_to_date": 2400.0,
            "pct_consumed": 80.0, "risk_level": "LOW",
        })
        assert client.get(f"/safe-to-spend/{_USER}/widget").json()["status"] == "ATENCAO"

    def test_status_critico_quando_estourado(self, monkeypatch):
        client = self._client_with_sts(monkeypatch, {
            "safe_to_spend_total": 3000.0, "spent_to_date": 2970.0,
            "pct_consumed": 99.0, "risk_level": "CRITICAL",
        })
        body = client.get(f"/safe-to-spend/{_USER}/widget").json()
        assert body["status"] == "CRITICO"
        assert body["color"] == "#ef4444"

    def test_payload_compacto(self, monkeypatch):
        client = self._client_with_sts(monkeypatch, {
            "safe_to_spend_total": 3000.0, "spent_to_date": 900.0,
            "pct_consumed": 30.0, "risk_level": "LOW",
        })
        body = client.get(f"/safe-to-spend/{_USER}/widget").json()
        assert set(body.keys()) == {
            "daily", "remaining_month", "pct_consumed", "status",
            "color", "headline", "subline", "updated_at",
        }
