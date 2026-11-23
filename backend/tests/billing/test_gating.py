# tests/billing/test_gating.py
# Gating de planos e limites de uso — dark launch (flag) e enforcement

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.billing import gating
from app.billing.gating import consume_usage, require_plan, usage_snapshot
from app.billing.plans import plan_satisfies
from app.core.config import settings
from app.core.security import require_owner

USER = "user_gating_test"


@pytest.fixture(autouse=True)
def _memoria_limpa(monkeypatch):
    """Contadores em memória zerados e Redis fora do caminho em cada teste."""
    monkeypatch.setattr(gating, "_memory_counters", {})
    import app.core.cache as cache_module
    monkeypatch.setattr(cache_module, "get_redis", lambda: None)


@pytest.fixture
def enforcement_on(monkeypatch):
    monkeypatch.setattr(settings, "BILLING_ENFORCEMENT_ENABLED", True, raising=False)
    # enforcement só vale com o Stripe pronto para cobrar
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_x", raising=False)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_x", raising=False)


@pytest.fixture
def enforcement_off(monkeypatch):
    monkeypatch.setattr(settings, "BILLING_ENFORCEMENT_ENABLED", False, raising=False)


def _app_with_gate(required_plan: str):
    app = FastAPI()

    @app.get("/gated/{user_id}")
    def gated(user_id: str = require_plan(required_plan)):
        return {"ok": True, "user_id": user_id}

    app.dependency_overrides[require_owner] = lambda user_id: USER
    return TestClient(app)


# ── hierarquia de planos ─────────────────────────────────────────────────────

@pytest.mark.parametrize("user_plan,required,ok", [
    ("free", "pro", False), ("free", "total", False),
    ("pro", "pro", True), ("pro", "total", False),
    ("total", "pro", True), ("total", "total", True),
    ("plano_desconhecido", "pro", False),
])
def test_plan_satisfies(user_plan, required, ok):
    assert plan_satisfies(user_plan, required) is ok


# ── require_plan ─────────────────────────────────────────────────────────────

def test_free_bloqueado_com_402_quando_enforcement_ligado(enforcement_on):
    client = _app_with_gate("total")
    with patch("app.billing.service.BillingService.get_effective_plan", return_value="free"):
        resp = client.get(f"/gated/{USER}")
    assert resp.status_code == 402
    detail = resp.json()["detail"]
    assert detail["error"] == "upgrade_required"
    assert detail["required_plan"] == "total"
    assert detail["price_brl_monthly"] == 39.90


def test_free_passa_em_dark_launch(enforcement_off):
    client = _app_with_gate("total")
    with patch("app.billing.service.BillingService.get_effective_plan", return_value="free"):
        resp = client.get(f"/gated/{USER}")
    assert resp.status_code == 200  # só loga would_block


def test_total_passa_no_gate_pro(enforcement_on):
    client = _app_with_gate("pro")
    with patch("app.billing.service.BillingService.get_effective_plan", return_value="total"):
        resp = client.get(f"/gated/{USER}")
    assert resp.status_code == 200


# ── limites de uso ───────────────────────────────────────────────────────────

def test_free_chat_5_por_dia(enforcement_on):
    with patch("app.billing.service.BillingService.get_effective_plan", return_value="free"):
        for _ in range(5):
            consume_usage(USER, "chat_messages")  # 5 primeiros passam
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            consume_usage(USER, "chat_messages")  # 6º bloqueia
        assert exc.value.status_code == 402


def test_free_estoura_limite_mas_dark_launch_permite(enforcement_off):
    with patch("app.billing.service.BillingService.get_effective_plan", return_value="free"):
        for _ in range(10):
            consume_usage(USER, "chat_messages")  # nunca levanta


def test_total_ilimitado(enforcement_on):
    with patch("app.billing.service.BillingService.get_effective_plan", return_value="total"):
        for _ in range(50):
            consume_usage(USER, "chat_messages")


def test_pro_negociador_1_por_mes(enforcement_on):
    with patch("app.billing.service.BillingService.get_effective_plan", return_value="pro"):
        consume_usage(USER, "negotiator_scripts")  # 1º do mês passa
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            consume_usage(USER, "negotiator_scripts")


def test_free_negociador_bloqueado_no_primeiro_uso(enforcement_on):
    with patch("app.billing.service.BillingService.get_effective_plan", return_value="free"):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            consume_usage(USER, "negotiator_scripts")  # limite 0


def test_pro_chat_ilimitado(enforcement_on):
    with patch("app.billing.service.BillingService.get_effective_plan", return_value="pro"):
        for _ in range(20):
            consume_usage(USER, "chat_messages")


# ── snapshot de uso ──────────────────────────────────────────────────────────

def test_usage_snapshot_reflete_consumo(enforcement_on):
    with patch("app.billing.service.BillingService.get_effective_plan", return_value="free"):
        consume_usage(USER, "chat_messages")
        consume_usage(USER, "chat_messages")
        snap = {u["key"]: u for u in usage_snapshot(USER)}
    assert snap["chat_messages"]["used"] == 2
    assert snap["chat_messages"]["limit"] == 5
    assert snap["purchase_checks"]["used"] == 0


# ── check_usage: verifica sem consumir (chat debita só depois do sucesso) ────

def test_check_usage_nao_consome(enforcement_on):
    with patch("app.billing.gating._get_plan", return_value="free"):
        for _ in range(3):
            gating.check_usage(USER, "chat_messages")
        snap = {u["key"]: u for u in usage_snapshot(USER)}
    assert snap["chat_messages"]["used"] == 0


def test_check_usage_bloqueia_quando_o_proximo_passaria_do_limite(enforcement_on):
    from fastapi import HTTPException

    with patch("app.billing.gating._get_plan", return_value="free"):
        for _ in range(5):  # Free = 5 mensagens/dia
            consume_usage(USER, "chat_messages")
        with pytest.raises(HTTPException) as exc:
            gating.check_usage(USER, "chat_messages")
    assert exc.value.status_code == 402
