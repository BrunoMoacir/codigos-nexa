# tests/rights/test_rights_router_checks.py
# Endpoints de consulta real do T3 — SVR assistido e restituição autorizada

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import require_owner
from app.rights.connectors.serpro_restituicao import (
    RestituicaoResultado,
    SerproTokenAutorizacaoInvalido,
)
from app.rights.connectors.svr_public import (
    SvrCaptcha,
    SvrCaptchaInvalido,
    SvrIndisponivel,
    SvrResultado,
)
from app.rights.router import router, _serpro, _svr_public

USER = "user_rights_test"
CPF_VALIDO = "52998224725"


def _make_app(auth_user: str = USER):
    a = FastAPI()
    a.include_router(router)
    a.dependency_overrides[require_owner] = lambda user_id: auth_user
    return a


client = TestClient(_make_app())


# ── GET /rights/{user_id}/svr/captcha ────────────────────────────────────────

def test_svr_captcha_ok():
    with patch.object(
        _svr_public, "get_captcha",
        return_value=SvrCaptcha(imagem_base64="img==", hash="h=="),
    ):
        resp = client.get(f"/rights/{USER}/svr/captcha")
    assert resp.status_code == 200
    body = resp.json()
    assert body["imagem_base64"] == "img=="
    assert body["hash"] == "h=="
    assert "BACEN" in body["instrucao"]


def test_svr_captcha_indisponivel_503():
    with patch.object(_svr_public, "get_captcha", side_effect=SvrIndisponivel("fora")):
        resp = client.get(f"/rights/{USER}/svr/captcha")
    assert resp.status_code == 503


# ── POST /rights/{user_id}/svr/check ─────────────────────────────────────────

def _svr_body(**overrides):
    body = {
        "cpf": CPF_VALIDO,
        "data_nascimento": "1990-05-17",
        "captcha_hash": "h==",
        "captcha_resposta": "XK7P2",
    }
    body.update(overrides)
    return body


def test_svr_check_tem_valor():
    with patch.object(
        _svr_public, "consultar",
        return_value=SvrResultado(True, "***.982.***-**"),
    ):
        resp = client.post(f"/rights/{USER}/svr/check", json=_svr_body())
    assert resp.status_code == 200
    body = resp.json()
    assert body["tem_valor_a_receber"] is True
    assert body["consultado_em_nome_de"] == "***.982.***-**"
    assert any("GOV.BR" in p for p in body["proximos_passos"])


def test_svr_check_sem_valor():
    with patch.object(
        _svr_public, "consultar",
        return_value=SvrResultado(False, "***.982.***-**"),
    ):
        resp = client.post(f"/rights/{USER}/svr/check", json=_svr_body())
    assert resp.status_code == 200
    assert resp.json()["tem_valor_a_receber"] is False


def test_svr_check_captcha_errado_412():
    with patch.object(_svr_public, "consultar", side_effect=SvrCaptchaInvalido("errado")):
        resp = client.post(f"/rights/{USER}/svr/check", json=_svr_body())
    assert resp.status_code == 412


def test_svr_check_cpf_invalido_422():
    with patch.object(_svr_public, "consultar", side_effect=ValueError("CPF inválido")):
        resp = client.post(f"/rights/{USER}/svr/check", json=_svr_body(cpf="123"))
    assert resp.status_code == 422


def test_svr_check_data_invalida_422():
    resp = client.post(
        f"/rights/{USER}/svr/check", json=_svr_body(data_nascimento="17/05/1990")
    )
    assert resp.status_code == 422


def test_svr_check_indisponivel_503():
    with patch.object(_svr_public, "consultar", side_effect=SvrIndisponivel("fora")):
        resp = client.post(f"/rights/{USER}/svr/check", json=_svr_body())
    assert resp.status_code == 503


# ── POST /rights/{user_id}/ir/check ──────────────────────────────────────────

def test_ir_check_nao_configurado_retorna_orientacao(monkeypatch):
    monkeypatch.setattr(settings, "SERPRO_RESTITUICAO_TRIAL", False, raising=False)
    monkeypatch.setattr(settings, "SERPRO_CONSUMER_KEY", "", raising=False)
    monkeypatch.setattr(settings, "SERPRO_CONSUMER_SECRET", "", raising=False)

    resp = client.post(f"/rights/{USER}/ir/check", json={"token_compartilhamento": "abc"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "nao_configurado"
    assert any("e-CAC" in p for p in body["proximos_passos"])


def test_ir_check_encontrada(monkeypatch):
    monkeypatch.setattr(settings, "SERPRO_RESTITUICAO_TRIAL", True, raising=False)
    resultado = RestituicaoResultado(
        encontrada=True,
        valor=1234.56,
        situacao_codigo="02",
        situacao_descricao="Em fila de restituição",
        banco_codigo="001",
        titular_cpf_mascarado="***.456.***-**",
    )
    with patch.object(_serpro, "consultar", return_value=resultado):
        resp = client.post(f"/rights/{USER}/ir/check", json={"token_compartilhamento": "tok"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "encontrada"
    assert body["valor"] == pytest.approx(1234.56)
    assert any("fila de restituição" in p for p in body["proximos_passos"])


def test_ir_check_sem_restituicao(monkeypatch):
    monkeypatch.setattr(settings, "SERPRO_RESTITUICAO_TRIAL", True, raising=False)
    with patch.object(
        _serpro, "consultar",
        return_value=RestituicaoResultado(encontrada=False, detalhe="sem restituição"),
    ):
        resp = client.post(f"/rights/{USER}/ir/check", json={"token_compartilhamento": "tok"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "sem_restituicao"


def test_ir_check_token_autorizacao_invalido_403(monkeypatch):
    monkeypatch.setattr(settings, "SERPRO_RESTITUICAO_TRIAL", True, raising=False)
    with patch.object(
        _serpro, "consultar",
        side_effect=SerproTokenAutorizacaoInvalido("expirado"),
    ):
        resp = client.post(f"/rights/{USER}/ir/check", json={"token_compartilhamento": "tok"})
    assert resp.status_code == 403


# ── GET /rights/{user_id} — capacidades anotadas ─────────────────────────────

def test_overview_anota_capacidades(monkeypatch):
    monkeypatch.setattr(settings, "SERPRO_RESTITUICAO_TRIAL", True, raising=False)
    resp = client.get(f"/rights/{USER}")
    assert resp.status_code == 200
    rights = {r["category"]: r for r in resp.json()["rights"]}

    assert rights["svr_bacen"]["capability"] == "assisted_real"
    assert rights["svr_bacen"]["check_endpoint"] == "/api/v1/rights/{user_id}/svr/check"
    assert rights["ir_restituicao"]["capability"] == "authorized_real"
    assert rights["fgts"]["capability"] == "guided"
    assert rights["pis_pasep"]["capability"] == "guided"


def test_overview_ir_guiado_sem_serpro(monkeypatch):
    monkeypatch.setattr(settings, "SERPRO_RESTITUICAO_TRIAL", False, raising=False)
    monkeypatch.setattr(settings, "SERPRO_CONSUMER_KEY", "", raising=False)
    monkeypatch.setattr(settings, "SERPRO_CONSUMER_SECRET", "", raising=False)
    resp = client.get(f"/rights/{USER}")
    rights = {r["category"]: r for r in resp.json()["rights"]}
    assert rights["ir_restituicao"]["capability"] == "guided"
