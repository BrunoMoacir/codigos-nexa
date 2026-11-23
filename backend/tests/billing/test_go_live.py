# tests/billing/test_go_live.py
# O que precisa estar certo para cobrar de verdade e ligar o enforcement.

import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.billing import gating
from app.billing.service import BillingService, CheckoutDeOutroUsuario
from app.billing.stripe_client import StripeClient, StripeIndisponivel
from app.core.config import settings


SUB_A = f"sub_a_{uuid.uuid4().hex[:10]}"
SUB_B = f"sub_b_{uuid.uuid4().hex[:10]}"
SUB_C = f"sub_c_{uuid.uuid4().hex[:10]}"
SUB_D = f"sub_d_{uuid.uuid4().hex[:10]}"
SUB_E = f"sub_e_{uuid.uuid4().hex[:10]}"
SUB_F = f"sub_f_{uuid.uuid4().hex[:10]}"
SUB_G = f"sub_g_{uuid.uuid4().hex[:10]}"
SUB_H = f"sub_h_{uuid.uuid4().hex[:10]}"
SUB_I = f"sub_i_{uuid.uuid4().hex[:10]}"
SUB_J = f"sub_j_{uuid.uuid4().hex[:10]}"


def _uid():
    return f"golive_{uuid.uuid4().hex[:10]}"


@pytest.fixture
def stripe_pronto(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_x", raising=False)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_x", raising=False)
    monkeypatch.setattr(settings, "STRIPE_PRICE_PRO_MONTHLY", "price_pro", raising=False)
    monkeypatch.setattr(settings, "STRIPE_PRICE_TOTAL_MONTHLY", "price_total", raising=False)


@pytest.fixture
def enforcement(monkeypatch, stripe_pronto):
    monkeypatch.setattr(settings, "BILLING_ENFORCEMENT_ENABLED", True, raising=False)


class StripeFalso(StripeClient):
    """Responde get_subscription/get_checkout_session de dicionários."""

    def __init__(self, assinaturas=None, sessoes=None, falha=False):
        super().__init__()
        self.assinaturas = assinaturas or {}
        self.sessoes = sessoes or {}
        self.falha = falha
        self.checkouts = []

    def get_subscription(self, subscription_id):
        if self.falha:
            raise StripeIndisponivel("fora do ar")
        return self.assinaturas[subscription_id]

    def get_checkout_session(self, session_id):
        return self.sessoes[session_id]

    def create_checkout_session(self, **kw):
        self.checkouts.append(kw)
        return {"id": "cs_novo", "url": "https://checkout.stripe.com/cs_novo"}


def _sub(sub_id, *, user=None, price="price_pro", status="active", fim=None, itens_com_periodo=False, customer="cus_1"):
    fim = fim or int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())
    item = {"price": {"id": price}}
    sub = {"id": sub_id, "status": status, "customer": customer, "metadata": {"user_id": user} if user else {},
           "items": {"data": [item]}, "cancel_at_period_end": False}
    if itens_com_periodo:
        item["current_period_end"] = fim  # API basil: período nos itens
    else:
        sub["current_period_end"] = fim
    return sub


def _evento(tipo, obj, eid=None):
    return {"id": eid or f"evt_{uuid.uuid4().hex[:12]}", "type": tipo, "data": {"object": obj}}


# ── enforcement só com o Stripe pronto ──────────────────────────────────────

def test_enforcement_pedido_sem_stripe_nao_bloqueia(monkeypatch):
    monkeypatch.setattr(settings, "BILLING_ENFORCEMENT_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "", raising=False)
    assert gating.enforcement_enabled() is False


def test_enforcement_sem_segredo_do_webhook_nao_bloqueia(monkeypatch):
    monkeypatch.setattr(settings, "BILLING_ENFORCEMENT_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_x", raising=False)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "", raising=False)
    assert gating.enforcement_enabled() is False


def test_enforcement_com_stripe_pronto(enforcement):
    assert gating.enforcement_enabled() is True


# ── janelas no fuso de São Paulo ────────────────────────────────────────────

def test_janela_diaria_vira_a_meia_noite_de_brasilia():
    sp = gating._FUSO
    noite = datetime(2026, 11, 22, 23, 30, tzinfo=sp)   # 02:30 UTC do dia 23
    madrugada = datetime(2026, 11, 23, 0, 10, tzinfo=sp)
    assert gating._window_bounds("daily", noite)[0] == "20261122"
    assert gating._window_bounds("daily", madrugada)[0] == "20261123"
    assert gating._window_bounds("daily", noite)[1] == 30 * 60


def test_janela_mensal_em_dezembro():
    sufixo, ttl = gating._window_bounds("monthly", datetime(2026, 12, 31, 12, 0, tzinfo=gating._FUSO))
    assert sufixo == "202612" and ttl == 12 * 3600


# ── webhook: o estado vem do Stripe, não do evento ──────────────────────────

def test_checkout_ativa_o_plano_pelo_price(stripe_pronto):
    user = _uid()
    svc = BillingService(StripeFalso({SUB_A: _sub(SUB_A, user=user, price="price_total")}))
    acao = svc.handle_webhook_event(_evento("checkout.session.completed",
                                            {"mode": "subscription", "client_reference_id": user, "subscription": SUB_A}))
    assert acao == "synced:total:active"
    assert svc.get_effective_plan(user) == "total"


def test_evento_antigo_fora_de_ordem_nao_reativa_quem_cancelou(stripe_pronto):
    user = _uid()
    stripe = StripeFalso({SUB_B: _sub(SUB_B, user=user)})
    svc = BillingService(stripe)
    svc.handle_webhook_event(_evento("customer.subscription.created", {"id": SUB_B}))
    stripe.assinaturas[SUB_B] = _sub(SUB_B, user=user, status="canceled")
    svc.handle_webhook_event(_evento("customer.subscription.deleted", {"id": SUB_B}))
    # o "updated" de antes do cancelamento chega por último — o Stripe diz canceled
    svc.handle_webhook_event(_evento("customer.subscription.updated", {"id": SUB_B, "status": "active"}))
    assert svc.get_effective_plan(user) == "free"


def test_boleto_pendente_nao_libera_o_plano(stripe_pronto):
    user = _uid()
    svc = BillingService(StripeFalso({SUB_C: _sub(SUB_C, user=user, status="incomplete")}))
    svc.handle_webhook_event(_evento("checkout.session.completed",
                                     {"mode": "subscription", "client_reference_id": user, "subscription": SUB_C}))
    assert svc.get_effective_plan(user) == "free"


def test_falha_ao_consultar_o_stripe_sobe_para_o_stripe_reenviar(stripe_pronto):
    svc = BillingService(StripeFalso(falha=True))
    with pytest.raises(StripeIndisponivel):
        svc.handle_webhook_event(_evento("checkout.session.completed",
                                         {"mode": "subscription", "client_reference_id": _uid(), "subscription": "sub_x"}))


def test_evento_repetido_e_ignorado(stripe_pronto):
    user = _uid()
    stripe = StripeFalso({SUB_D: _sub(SUB_D, user=user)})
    svc = BillingService(stripe)
    evento = _evento("customer.subscription.created", {"id": SUB_D})
    assert svc.handle_webhook_event(evento).startswith("synced")
    assert svc.handle_webhook_event(evento) == "duplicate"


def test_api_basil_periodo_nos_itens_e_assinatura_na_fatura(stripe_pronto):
    user = _uid()
    fim = int((datetime.now(timezone.utc) + timedelta(days=20)).timestamp())
    svc = BillingService(StripeFalso({SUB_E: _sub(SUB_E, user=user, itens_com_periodo=True, fim=fim)}))
    fatura = {"id": "in_1", "parent": {"subscription_details": {"subscription": SUB_E}}}
    assert svc.handle_webhook_event(_evento("invoice.paid", fatura)).startswith("synced:pro")
    registro = svc.get_record_dict(user)
    assert int(registro["current_period_end"].timestamp()) == fim


def test_price_desconhecido_nao_concede_plano(stripe_pronto):
    user = _uid()
    svc = BillingService(StripeFalso({SUB_F: _sub(SUB_F, user=user, price="price_de_outro_produto")}))
    assert svc.handle_webhook_event(_evento("customer.subscription.created", {"id": SUB_F})) == "synced:free:active"


def test_dono_divergente_e_recusado(stripe_pronto):
    svc = BillingService(StripeFalso({SUB_G: _sub(SUB_G, user=_uid())}))
    acao = svc.handle_webhook_event(_evento("checkout.session.completed",
                                            {"mode": "subscription", "client_reference_id": _uid(), "subscription": SUB_G}))
    assert acao == "ignored:unknown_owner"


def test_past_due_tem_carencia_limitada():
    agora = datetime.now(timezone.utc)
    rec = SimpleNamespace(plan="pro", status="past_due", current_period_end=agora - timedelta(days=3))
    assert BillingService._plano_efetivo(rec, agora) == "pro"
    rec.current_period_end = agora - timedelta(days=8)
    assert BillingService._plano_efetivo(rec, agora) == "free"


# ── checkout ────────────────────────────────────────────────────────────────

def test_quem_ja_assina_nao_abre_segundo_checkout(stripe_pronto):
    from app.billing.service import AssinaturaJaAtiva

    user = _uid()
    stripe = StripeFalso({SUB_H: _sub(SUB_H, user=user)})
    svc = BillingService(stripe)
    svc.handle_webhook_event(_evento("customer.subscription.created", {"id": SUB_H}))
    with pytest.raises(AssinaturaJaAtiva):
        svc.create_checkout(user_id=user, plan_id="total", customer_email=None, success_url="s", cancel_url="c")
    assert stripe.checkouts == []


def test_checkout_reaproveita_o_cliente_e_manda_idempotencia(stripe_pronto):
    user = _uid()
    stripe = StripeFalso({SUB_I: _sub(SUB_I, user=user, status="canceled", customer="cus_antigo")})
    svc = BillingService(stripe)
    svc.handle_webhook_event(_evento("customer.subscription.deleted", {"id": SUB_I}))
    svc.create_checkout(user_id=user, plan_id="pro", customer_email=None, success_url="s", cancel_url="c")
    chamada = stripe.checkouts[0]
    assert chamada["customer_id"] == "cus_antigo"
    assert chamada["idempotency_key"]


def test_confirmar_sessao_de_outra_conta_e_recusado(stripe_pronto):
    svc = BillingService(StripeFalso(sessoes={"cs_1": {"client_reference_id": "outra", "mode": "subscription"}}))
    with pytest.raises(CheckoutDeOutroUsuario):
        svc.confirm_checkout(user_id=_uid(), session_id="cs_1")


def test_confirmar_sessao_propria_libera_na_hora(stripe_pronto):
    user = _uid()
    svc = BillingService(StripeFalso(
        assinaturas={SUB_J: _sub(SUB_J, user=user)},
        sessoes={"cs_2": {"client_reference_id": user, "mode": "subscription", "subscription": SUB_J}},
    ))
    assert svc.confirm_checkout(user_id=user, session_id="cs_2") == "pro"


def test_rotas_de_confirmacao_e_409():
    from app.billing.router import _service, router
    from app.core.security import require_owner

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_owner] = lambda user_id: "dono"
    cliente = TestClient(app)
    with patch.object(_service, "confirm_checkout", side_effect=CheckoutDeOutroUsuario()):
        assert cliente.post("/billing/checkout/dono/confirm", json={"session_id": "cs_x"}).status_code == 403
    with patch.object(_service, "confirm_checkout", side_effect=ValueError()):
        assert cliente.post("/billing/checkout/dono/confirm", json={"session_id": "../x"}).status_code == 422
    from app.billing.service import AssinaturaJaAtiva
    with patch.object(_service, "create_checkout", side_effect=AssinaturaJaAtiva("pro")):
        resp = cliente.post("/billing/checkout/dono", json={"plan": "total"})
    assert resp.status_code == 409 and resp.json()["detail"]["error"] == "already_subscribed"


# ── cliente Stripe ──────────────────────────────────────────────────────────

def test_cliente_fixa_a_versao_da_api_e_valida_ids(stripe_pronto):
    vistos = []

    def resposta(req):
        vistos.append(req)
        return httpx.Response(200, json={"id": "sub_1"})

    cliente = StripeClient(transport=httpx.MockTransport(resposta))
    cliente.get_subscription("sub_1")
    assert vistos[0].headers["Stripe-Version"] == settings.STRIPE_API_VERSION
    with pytest.raises(ValueError):
        cliente.get_subscription("../customers")
    with pytest.raises(ValueError):
        cliente.get_checkout_session("sub_1")


def test_price_por_lookup_key(monkeypatch, stripe_pronto):
    from app.billing import stripe_client

    monkeypatch.setattr(settings, "STRIPE_PRICE_PRO_MONTHLY", "", raising=False)
    stripe_client._price_cache.clear()
    cliente = StripeClient(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json={"data": [{"id": "price_lk"}]})))
    assert cliente.price_id_for("pro") == "price_lk"
    assert cliente.plan_for_price({"id": "x", "lookup_key": "hive_total_mensal"}) == "total"
    assert cliente.plan_for_price({"id": "price_lk"}) == "pro"
    stripe_client._price_cache.clear()


# ── limite de bancos e ferramentas do agente ────────────────────────────────

def test_free_com_um_banco_nao_conecta_outro(enforcement):
    with patch("app.billing.gating._get_plan", return_value="free"):
        gating.check_bank_limit("u", conexoes_atuais=0)
        with pytest.raises(HTTPException) as exc:
            gating.check_bank_limit("u", conexoes_atuais=1)
    assert exc.value.status_code == 402


def test_pro_conecta_bancos_a_vontade(enforcement):
    with patch("app.billing.gating._get_plan", return_value="pro"):
        gating.check_bank_limit("u", conexoes_atuais=5)


def test_ferramenta_paga_bloqueada_no_chat_com_enforcement(enforcement):
    from app.agent.planos_das_ferramentas import bloqueio_da_ferramenta

    with patch("app.billing.gating._get_plan", return_value="free"):
        msg = bloqueio_da_ferramenta("get_defense_analysis", "u")
        assert msg and "PLANO TOTAL" in msg
        assert bloqueio_da_ferramenta("get_financial_forecast", "u") is None


def test_ferramenta_paga_roda_com_enforcement_desligado(monkeypatch):
    from app.agent.planos_das_ferramentas import bloqueio_da_ferramenta

    monkeypatch.setattr(settings, "BILLING_ENFORCEMENT_ENABLED", False, raising=False)
    with patch("app.billing.gating._get_plan", return_value="free"):
        assert bloqueio_da_ferramenta("get_defense_analysis", "u") is None


def test_ferramentas_mapeadas_existem_no_agente():
    from app.agent.planos_das_ferramentas import FERRAMENTA_RECURSO, FERRAMENTA_USO
    from app.agent.graph import AGENT_TOOLS

    nomes = {t.name for t in AGENT_TOOLS}
    assert set(FERRAMENTA_RECURSO) <= nomes
    assert set(FERRAMENTA_USO) <= nomes


# ── script de setup contra um Stripe em memória ─────────────────────────────

class StripeEmMemoria:
    def __init__(self):
        self.produtos, self.prices, self.portais, self.webhooks = {}, [], [], []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        caminho = req.url.path.removeprefix("/v1")
        form = dict(httpx.QueryParams(req.content.decode())) if req.content else {}
        if req.method == "GET" and caminho.startswith("/products/"):
            pid = caminho.split("/")[-1]
            if pid in self.produtos:
                return httpx.Response(200, json=self.produtos[pid])
            return httpx.Response(404, json={"error": {"message": f"No such product: '{pid}'"}})
        if req.method == "POST" and caminho == "/products":
            self.produtos[form["id"]] = form
            return httpx.Response(200, json=form)
        if req.method == "GET" and caminho == "/prices":
            chave = req.url.params.get("lookup_keys[]")
            achados = [p for p in self.prices if p["lookup_key"] == chave]
            return httpx.Response(200, json={"data": achados[-1:]})
        if req.method == "POST" and caminho == "/prices":
            price = {"id": f"price_{len(self.prices)}", "lookup_key": form["lookup_key"],
                     "unit_amount": int(form["unit_amount"]), "currency": form["currency"],
                     "recurring": {"interval": form["recurring[interval]"]}}
            self.prices.append(price)
            return httpx.Response(200, json=price)
        if caminho == "/billing_portal/configurations" and req.method == "GET":
            return httpx.Response(200, json={"data": self.portais})
        if caminho.startswith("/billing_portal/configurations") and req.method == "POST":
            if caminho == "/billing_portal/configurations":
                self.portais.append({"id": f"bpc_{len(self.portais)}", "metadata": {"hive": form.get("metadata[hive]")}})
            return httpx.Response(200, json=self.portais[-1])
        if caminho == "/webhook_endpoints" and req.method == "GET":
            return httpx.Response(200, json={"data": self.webhooks})
        if caminho.startswith("/webhook_endpoints") and req.method == "POST":
            if caminho == "/webhook_endpoints":
                hook = {"id": "we_1", "url": form["url"], "secret": "whsec_criado", "api_version": form["api_version"]}
                self.webhooks.append(hook)
                return httpx.Response(200, json=hook)
            return httpx.Response(200, json={"id": "we_1", "url": self.webhooks[0]["url"]})
        return httpx.Response(400, json={"error": {"message": f"rota não simulada {req.method} {caminho}"}})


def test_setup_cria_tudo_e_e_idempotente(monkeypatch):
    from scripts.stripe_setup import configurar

    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_x", raising=False)
    fake = StripeEmMemoria()
    cliente = StripeClient(transport=httpx.MockTransport(fake))
    url = "https://api.exemplo.com/api/v1/billing/webhook"
    ambiente = configurar(cliente, webhook_url=url, live=False, dry_run=False, log=lambda _m: None)
    assert ambiente["STRIPE_WEBHOOK_SECRET"] == "whsec_criado"
    assert {p["lookup_key"] for p in fake.prices} == {"hive_pro_mensal", "hive_total_mensal"}
    assert {p["unit_amount"] for p in fake.prices} == {1990, 3990}
    assert fake.webhooks[0]["api_version"] == settings.STRIPE_API_VERSION

    de_novo = configurar(cliente, webhook_url=url, live=False, dry_run=False, log=lambda _m: None)
    assert len(fake.prices) == 2 and len(fake.portais) == 1 and len(fake.webhooks) == 1
    assert "STRIPE_WEBHOOK_SECRET" not in de_novo  # o segredo só existe na criação


def test_setup_recusa_chave_de_producao_sem_live(monkeypatch):
    from scripts.stripe_setup import ErroDeConfiguracao, configurar

    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_live_x", raising=False)
    with pytest.raises(ErroDeConfiguracao):
        configurar(StripeClient(), webhook_url=None, live=False, dry_run=True, log=lambda _m: None)


def test_setup_recusa_webhook_sem_https(monkeypatch):
    from scripts.stripe_setup import ErroDeConfiguracao, configurar

    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_x", raising=False)
    with pytest.raises(ErroDeConfiguracao):
        configurar(StripeClient(), webhook_url="http://x.com/api/v1/billing/webhook", live=False, dry_run=True,
                   log=lambda _m: None)


def test_webhook_com_falha_responde_500_para_o_stripe_reenviar(monkeypatch):
    import hashlib
    import hmac
    import time

    from app.billing.router import _service, router

    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_t", raising=False)
    app = FastAPI()
    app.include_router(router)
    payload = json.dumps(_evento("invoice.paid", {"subscription": "sub_1"})).encode()
    ts = int(time.time())
    sig = hmac.new(b"whsec_t", f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    with patch.object(_service, "handle_webhook_event", side_effect=StripeIndisponivel("x")):
        resp = TestClient(app).post("/billing/webhook", content=payload,
                                    headers={"Stripe-Signature": f"t={ts},v1={sig}"})
    assert resp.status_code == 500
    assert "x" not in resp.text.replace("Falha ao processar o evento.", "")
