"""
Contratos das rotas que o chat por conversas, a tela de cartões e o passo 1
do cadastro consomem:

  - GET  /chat/sessions     → uma linha por session_id, título = 1ª pergunta,
                               mais recente primeiro, só do dono do token;
  - GET  /chat/history      → com session_id, só aquela conversa;
  - GET  /pluggy/cards e POST /pluggy/cards/manual → cartões do usuário do token;
  - GET  /auth/check-email  → mesma regra de e-mail do cadastro (sem caixa).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

BASE = "/api/v1"
SENHA = "SenhaForte@2024"


@pytest.fixture
def cliente():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, raise_server_exceptions=False)


def _conta(cliente):
    email = f"c12_{uuid.uuid4().hex[:8]}@nexa.test"
    r = cliente.post(f"{BASE}/auth/register", json={"email": email, "password": SENHA, "accepted_terms": True})
    assert r.status_code == 201, r.text
    t = cliente.post(f"{BASE}/auth/token", data={"username": email, "password": SENHA})
    assert t.status_code == 200, t.text
    return r.json()["user_id"], {"Authorization": f"Bearer {t.json()['access_token']}"}, email


def _gravar(user_id: str, session_id: str | None, mensagens: list[tuple[str, str]], inicio: datetime):
    from app.agent.models import ChatMessage
    from app.core.database import SessionLocal

    with SessionLocal() as db:
        for i, (role, content) in enumerate(mensagens):
            db.add(ChatMessage(user_id=user_id, session_id=session_id, role=role, content=content,
                               created_at=inicio + timedelta(seconds=i)))
        db.commit()


class TestConversas:

    def test_uma_linha_por_conversa_com_titulo_e_ordem(self, cliente):
        uid, auth, _ = _conta(cliente)
        agora = datetime.now(UTC)
        _gravar(uid, "antiga", [("human", "Quanto posso gastar?"), ("assistant", "R$ 419 hoje.")], agora - timedelta(days=2))
        _gravar(uid, "recente", [("human", "x" * 120), ("assistant", "ok"), ("human", "e agora?")], agora - timedelta(hours=1))
        _gravar(uid, None, [("human", "mensagem de antes das conversas")], agora)

        r = cliente.get(f"{BASE}/chat/sessions", params={"user_id": uid}, headers=auth)
        assert r.status_code == 200, r.text
        conversas = r.json()

        assert [c["session_id"] for c in conversas] == ["recente", "antiga"]
        assert conversas[0]["title"] == "x" * 80
        assert conversas[0]["message_count"] == 3
        assert conversas[1]["title"] == "Quanto posso gastar?"

    def test_historico_filtrado_pela_conversa(self, cliente):
        uid, auth, _ = _conta(cliente)
        agora = datetime.now(UTC)
        _gravar(uid, "a", [("human", "pergunta A"), ("assistant", "resposta A")], agora)
        _gravar(uid, "b", [("human", "pergunta B")], agora)

        r = cliente.get(f"{BASE}/chat/history", params={"user_id": uid, "session_id": "a"}, headers=auth)
        assert r.status_code == 200, r.text
        itens = r.json()
        assert [m["content"] for m in itens] == ["pergunta A", "resposta A"]
        assert [m["role"] for m in itens] == ["user", "assistant"]

    def test_conversas_de_outra_pessoa_sao_recusadas(self, cliente):
        dono, _, _ = _conta(cliente)
        _, auth_outro, _ = _conta(cliente)
        _gravar(dono, "privada", [("human", "meu salário")], datetime.now(UTC))

        r = cliente.get(f"{BASE}/chat/sessions", params={"user_id": dono}, headers=auth_outro)
        assert r.status_code == 403, r.text

    def test_sem_token_nao_lista(self, cliente):
        uid, _, _ = _conta(cliente)
        assert cliente.get(f"{BASE}/chat/sessions", params={"user_id": uid}).status_code == 401


class TestCartoes:

    def test_cartao_manual_aparece_so_para_o_dono(self, cliente):
        _, auth, _ = _conta(cliente)
        _, auth_outro, _ = _conta(cliente)

        assert cliente.get(f"{BASE}/pluggy/cards", headers=auth).json() == []

        novo = cliente.post(f"{BASE}/pluggy/cards/manual", headers=auth, json={
            "bank_name": "Banco Regional", "brand": "VISA", "last4": "4321",
            "credit_limit": 5000, "available_credit_limit": 3200,
        })
        assert novo.status_code == 200, novo.text
        assert novo.json()["bank_name"] == "Banco Regional"

        meus = cliente.get(f"{BASE}/pluggy/cards", headers=auth).json()
        assert [c["last4"] for c in meus] == ["4321"]
        assert meus[0]["credit_limit"] == 5000
        assert cliente.get(f"{BASE}/pluggy/cards", headers=auth_outro).json() == []

    def test_sem_token_nao_lista(self, cliente):
        assert cliente.get(f"{BASE}/pluggy/cards").status_code == 401


class TestEmailDisponivel:

    def test_email_novo_esta_livre(self, cliente):
        r = cliente.get(f"{BASE}/auth/check-email", params={"email": f"livre_{uuid.uuid4().hex[:8]}@nexa.test"})
        assert r.status_code == 200 and r.json() == {"available": True}

    def test_email_cadastrado_em_outra_caixa_nao_esta_livre(self, cliente):
        # O cadastro recusa "ANA@x.com" se "ana@x.com" existe; o aviso do passo 1 tem de concordar.
        _, _, email = _conta(cliente)
        r = cliente.get(f"{BASE}/auth/check-email", params={"email": email.upper()})
        assert r.status_code == 200 and r.json() == {"available": False}
