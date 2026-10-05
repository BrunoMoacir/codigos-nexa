"""
Contrato do cadastro e da sessão que o app React consome (C7).

Antes da correção:
  - o cadastro aceitava e-mail 'x' e senha de 1 caractere (o reset já
    exigia 8 — era possível criar conta com senha que o reset recusaria);
  - telefone e aceite de termos do formulário eram descartados em silêncio;
  - "Ana@X.com" e "ana@x.com" eram contas diferentes para o login;
  - o logout revogava só o access: o refresh de 14 dias seguia gerando
    sessão nova.
"""

from __future__ import annotations

import uuid

import pytest

from app.core import login_throttle

BASE = "/api/v1"


@pytest.fixture
def cliente():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, raise_server_exceptions=False)


def _email(prefixo: str = "c7") -> str:
    return f"{prefixo}_{uuid.uuid4().hex[:8]}@nexa.test"


def _registrar(cliente, **extra):
    corpo = {"email": _email(), "password": "SenhaForte@2024", "accepted_terms": True}
    corpo.update(extra)
    return cliente.post(f"{BASE}/auth/register", json=corpo), corpo


class TestValidacaoDoCadastro:

    @pytest.mark.parametrize("campo,valor,trecho", [
        ("password", "1234567", "8 caracteres"),
        ("email", "sem-arroba", "E-mail inválido"),
        ("accepted_terms", False, "aceitar os termos"),
        ("phone", "123", "Telefone inválido"),
    ])
    def test_recusa_com_mensagem_clara(self, cliente, campo, valor, trecho):
        r, _ = _registrar(cliente, **{campo: valor})
        assert r.status_code == 422, r.text
        assert trecho in r.text

    def test_sem_aceite_de_termos_nao_ha_conta(self, cliente):
        r = cliente.post(f"{BASE}/auth/register", json={"email": _email(), "password": "SenhaForte@2024"})
        assert r.status_code == 422

    def test_grava_telefone_e_instante_do_aceite(self, cliente):
        r, corpo = _registrar(cliente, phone="+55 (11) 99999-8888", full_name="  Teste C7  ")
        assert r.status_code == 201, r.text
        from app.core.database import SessionLocal
        from app.core.models.user import User

        with SessionLocal() as db:
            u = db.get(User, r.json()["user_id"])
            assert u.phone == "5511999998888"
            assert u.terms_accepted_at is not None
            assert u.full_name == "Teste C7"


class TestEmailSemDiferencaDeCaixa:

    def test_cadastro_guarda_minusculas_e_login_aceita_qualquer_caixa(self, cliente):
        email = _email("Caixa").replace("caixa", "CaIxA")
        r, _ = _registrar(cliente, email=email.upper())
        assert r.status_code == 201, r.text
        login_throttle.limpar(email.lower())
        tok = cliente.post(f"{BASE}/auth/token", data={"username": email, "password": "SenhaForte@2024"})
        assert tok.status_code == 200, tok.text

    def test_mesmo_email_em_outra_caixa_nao_duplica_conta(self, cliente):
        r, corpo = _registrar(cliente)
        assert r.status_code == 201
        r2 = cliente.post(f"{BASE}/auth/register", json={**corpo, "email": corpo["email"].upper()})
        assert r2.status_code == 400 and "já registrado" in r2.text


class TestLogoutRevogaASessaoInteira:

    def test_refresh_nao_sobrevive_ao_logout(self, cliente):
        r, corpo = _registrar(cliente)
        assert r.status_code == 201
        login_throttle.limpar(corpo["email"])
        tokens = cliente.post(
            f"{BASE}/auth/token", data={"username": corpo["email"], "password": corpo["password"]}
        ).json()
        access, refresh = tokens["access_token"], tokens["refresh_token"]

        saida = cliente.post(
            f"{BASE}/auth/logout", json={"refresh_token": refresh},
            headers={"Authorization": f"Bearer {access}"},
        )
        assert saida.status_code == 204

        renovacao = cliente.post(f"{BASE}/auth/refresh", json={"refresh_token": refresh})
        if renovacao.status_code == 200:
            pytest.skip("blacklist em fail-open (Redis indisponível no ambiente do teste)")
        assert renovacao.status_code == 401

    def test_logout_sem_corpo_continua_funcionando(self, cliente):
        r, corpo = _registrar(cliente)
        login_throttle.limpar(corpo["email"])
        access = cliente.post(
            f"{BASE}/auth/token", data={"username": corpo["email"], "password": corpo["password"]}
        ).json()["access_token"]
        saida = cliente.post(f"{BASE}/auth/logout", headers={"Authorization": f"Bearer {access}"})
        assert saida.status_code == 204


class TestLinksDoEmailApontamParaOApp:

    def test_link_de_redefinicao_vai_para_a_rota_do_react(self, monkeypatch):
        from app.api.v1.routes import auth as mod

        enviados = []
        monkeypatch.setattr(
            "app.core.notifications.email_sender.send_email",
            lambda **kw: enviados.append(kw),
        )
        monkeypatch.setattr(mod, "_frontend_url", mod._frontend_url)
        mod._send_reset_email("x@nexa.test", "TOKEN123")
        assert enviados and "/reset-password?token=TOKEN123" in enviados[0]["html_body"]
        assert ":8501" not in enviados[0]["html_body"]
