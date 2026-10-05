# tests/auth/test_password_reset_verification.py
# Reset de senha + verificação de e-mail — fluxos completos contra o app real

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
import app.api.v1.routes.auth as auth_module
from app.core.account_tokens import (
    PURPOSE_EMAIL_VERIFY,
    PURPOSE_PASSWORD_RESET,
    consume_token,
    issue_token,
)

client = TestClient(app)
BASE = "/api/v1/auth"


@pytest.fixture
def sent_emails(monkeypatch):
    """Captura (tipo, email, token) dos e-mails que o auth enviaria."""
    captured: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        auth_module, "_send_reset_email",
        lambda email, token: captured.append(("reset", email, token)),
    )
    monkeypatch.setattr(
        auth_module, "_send_verification_email",
        lambda email, token: captured.append(("verify", email, token)),
    )
    return captured


@pytest.fixture
def fresh_user(sent_emails):
    """Registra um usuário novo e devolve (email, senha, user_id)."""
    email = f"reset_test_{uuid.uuid4().hex[:10]}@nexa.test"
    password = "senhaForte123"
    resp = client.post(BASE + "/register", json={"email": email, "password": password, "accepted_terms": True})
    assert resp.status_code == 201, resp.text
    return email, password, resp.json()["user_id"]


def _login(email: str, password: str):
    return client.post(BASE + "/token", data={"username": email, "password": password})


# ── serviço de tokens ────────────────────────────────────────────────────────

class TestAccountTokens:
    def test_token_e_uso_unico(self):
        user_id = f"u_{uuid.uuid4().hex[:8]}"
        token = issue_token(user_id, PURPOSE_PASSWORD_RESET)
        assert consume_token(token, PURPOSE_PASSWORD_RESET) == user_id
        assert consume_token(token, PURPOSE_PASSWORD_RESET) is None  # 2º uso falha

    def test_token_nao_vale_para_outro_proposito(self):
        user_id = f"u_{uuid.uuid4().hex[:8]}"
        token = issue_token(user_id, PURPOSE_PASSWORD_RESET)
        assert consume_token(token, PURPOSE_EMAIL_VERIFY) is None

    def test_emitir_novo_invalida_o_anterior(self):
        user_id = f"u_{uuid.uuid4().hex[:8]}"
        antigo = issue_token(user_id, PURPOSE_PASSWORD_RESET)
        novo = issue_token(user_id, PURPOSE_PASSWORD_RESET)
        assert consume_token(antigo, PURPOSE_PASSWORD_RESET) is None
        assert consume_token(novo, PURPOSE_PASSWORD_RESET) == user_id

    def test_token_invalido_ou_curto(self):
        assert consume_token("qualquer-coisa-invalida-longa-o-suficiente", PURPOSE_PASSWORD_RESET) is None
        assert consume_token("curto", PURPOSE_PASSWORD_RESET) is None
        assert consume_token("", PURPOSE_PASSWORD_RESET) is None


# ── fluxo de reset de senha ──────────────────────────────────────────────────

class TestPasswordReset:
    def test_fluxo_completo_troca_a_senha(self, fresh_user, sent_emails):
        email, senha_antiga, _ = fresh_user

        resp = client.post(BASE + "/forgot-password", json={"email": email})
        assert resp.status_code == 202

        reset_tokens = [t for kind, e, t in sent_emails if kind == "reset" and e == email]
        assert len(reset_tokens) == 1

        resp = client.post(
            BASE + "/reset-password",
            json={"token": reset_tokens[0], "new_password": "novaSenha456"},
        )
        assert resp.status_code == 200

        # senha antiga morre, nova funciona
        assert _login(email, senha_antiga).status_code == 401
        assert _login(email, "novaSenha456").status_code == 200

    def test_email_inexistente_responde_202_sem_enviar(self, sent_emails):
        resp = client.post(
            BASE + "/forgot-password",
            json={"email": f"nao_existe_{uuid.uuid4().hex}@nexa.test"},
        )
        assert resp.status_code == 202  # anti-enumeração: mesma resposta
        assert not [e for e in sent_emails if e[0] == "reset"]

    def test_token_reusado_falha(self, fresh_user, sent_emails):
        email, _, _ = fresh_user
        client.post(BASE + "/forgot-password", json={"email": email})
        token = [t for kind, e, t in sent_emails if kind == "reset"][0]

        assert client.post(
            BASE + "/reset-password", json={"token": token, "new_password": "novaSenha456"}
        ).status_code == 200
        # reuso do mesmo link → 400 genérico
        assert client.post(
            BASE + "/reset-password", json={"token": token, "new_password": "outraSenha789"}
        ).status_code == 400

    def test_token_invalido_400(self):
        resp = client.post(
            BASE + "/reset-password",
            json={"token": "token-falso-" + "x" * 40, "new_password": "novaSenha456"},
        )
        assert resp.status_code == 400

    def test_senha_curta_422(self, fresh_user, sent_emails):
        email, _, _ = fresh_user
        client.post(BASE + "/forgot-password", json={"email": email})
        token = [t for kind, e, t in sent_emails if kind == "reset"][0]
        resp = client.post(BASE + "/reset-password", json={"token": token, "new_password": "curta"})
        assert resp.status_code == 422


# ── fluxo de verificação de e-mail ───────────────────────────────────────────

class TestEmailVerification:
    def test_registro_dispara_email_de_verificacao(self, fresh_user, sent_emails):
        email, _, _ = fresh_user
        verify = [t for kind, e, t in sent_emails if kind == "verify" and e == email]
        assert len(verify) == 1

    def test_verificacao_completa(self, fresh_user, sent_emails):
        email, _, user_id = fresh_user
        token = [t for kind, e, t in sent_emails if kind == "verify" and e == email][0]

        resp = client.post(BASE + "/verify-email", json={"token": token})
        assert resp.status_code == 200

        # flag persistida
        from app.core.database import SessionLocal
        from app.core.models.user import User

        with SessionLocal() as db:
            user = db.get(User, user_id)
            if user is not None:  # em dev-DuckDB o usuário pode não estar no SQLAlchemy DB
                assert bool(user.email_verified) is True

    def test_token_de_verificacao_reusado_falha(self, fresh_user, sent_emails):
        email, _, _ = fresh_user
        token = [t for kind, e, t in sent_emails if kind == "verify" and e == email][0]
        assert client.post(BASE + "/verify-email", json={"token": token}).status_code == 200
        assert client.post(BASE + "/verify-email", json={"token": token}).status_code == 400

    def test_resend_gera_token_novo_e_invalida_o_antigo(self, fresh_user, sent_emails):
        email, _, _ = fresh_user
        antigo = [t for kind, e, t in sent_emails if kind == "verify" and e == email][0]

        resp = client.post(BASE + "/resend-verification", json={"email": email})
        assert resp.status_code == 202
        novo = [t for kind, e, t in sent_emails if kind == "verify" and e == email][-1]
        assert novo != antigo

        assert client.post(BASE + "/verify-email", json={"token": antigo}).status_code == 400
        assert client.post(BASE + "/verify-email", json={"token": novo}).status_code == 200

    def test_resend_email_inexistente_202_sem_enviar(self, sent_emails):
        resp = client.post(
            BASE + "/resend-verification",
            json={"email": f"nao_existe_{uuid.uuid4().hex}@nexa.test"},
        )
        assert resp.status_code == 202
        assert not sent_emails
