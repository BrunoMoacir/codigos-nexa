"""
Contrato do chat que o app consome (C6), contra o banco de verdade.

Antes da correção:
  - pergunta e resposta eram gravadas com o mesmo created_at (now() do
    Postgres é o início da transação) e o histórico, ordenado só por ele,
    saía em ordem indeterminada — a resposta aparecia acima da pergunta;
  - o histórico era um só por usuário, enquanto a memória do agente é por
    dono+sessão: a tela mostrava conversas que o agente já não lembrava;
  - 'Nova conversa' só tinha como apagar TUDO;
  - a resposta não dizia a sessão nem as ferramentas usadas.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.router import _ferramentas_do_turno, _texto, router
from app.core.database import SessionLocal, get_db
from app.core.security import get_current_user, require_owner


@pytest.fixture
def usuario():
    return f"chat-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def cliente(usuario):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: usuario
    app.dependency_overrides[require_owner] = lambda user_id: usuario

    def _db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    yield TestClient(app)
    from app.agent.models import ChatMessage
    with SessionLocal() as db:
        db.query(ChatMessage).filter(ChatMessage.user_id == usuario).delete()
        db.commit()


def _conversar(cliente, usuario, texto, sessao, resposta="ok", ferramentas=()):
    estado = {"messages": [
        HumanMessage(content="turno antigo"),
        AIMessage(content="", tool_calls=[{"name": "ferramenta_antiga", "args": {}, "id": "a"}]),
        HumanMessage(content=f"[user_id={usuario}] {texto}"),
        AIMessage(content="", tool_calls=[{"name": n, "args": {}, "id": n} for n in ferramentas]),
        AIMessage(content=[{"type": "text", "text": resposta}]),
    ]}
    agente = MagicMock()
    agente.invoke.return_value = estado
    with patch("app.agent.router.settings") as cfg, patch("app.agent.router._get_agent", return_value=agente):
        cfg.LLM_PROVIDER = "anthropic"
        cfg.ANTHROPIC_API_KEY = "sk-teste"
        return cliente.post("/chat/", json={"user_id": usuario, "message": texto, "session_id": sessao})


class TestRespostaDoChat:

    def test_devolve_sessao_ferramentas_do_turno_e_horario(self, cliente, usuario):
        r = _conversar(cliente, usuario, "tarifas?", "s1", "R$ 10", ("get_bank_cost_analysis",))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["session_id"] == "s1"
        assert d["tools_used"] == ["get_bank_cost_analysis"], "só o turno atual, não o thread inteiro"
        assert d["response"] == "R$ 10", "blocos do Anthropic viram texto"
        assert d["created_at"] and "T" in d["created_at"]


class TestHistoricoPorSessao:

    def test_ordem_cronologica_mesmo_com_timestamp_empatado(self, cliente, usuario):
        for i in range(3):
            _conversar(cliente, usuario, f"pergunta {i}", "s1", f"resposta {i}")
        h = cliente.get("/chat/history", params={"user_id": usuario, "session_id": "s1"}).json()
        assert [m["content"] for m in h] == [
            "pergunta 0", "resposta 0", "pergunta 1", "resposta 1", "pergunta 2", "resposta 2",
        ]
        assert [m["role"] for m in h[:2]] == ["user", "assistant"]

    def test_filtra_pela_sessao(self, cliente, usuario):
        _conversar(cliente, usuario, "da sessão A", "A")
        _conversar(cliente, usuario, "da sessão B", "B")
        so_a = cliente.get("/chat/history", params={"user_id": usuario, "session_id": "A"}).json()
        assert {m["session_id"] for m in so_a} == {"A"}
        tudo = cliente.get("/chat/history", params={"user_id": usuario}).json()
        assert {m["session_id"] for m in tudo} == {"A", "B"}

    def test_apagar_uma_sessao_preserva_as_outras(self, cliente, usuario):
        _conversar(cliente, usuario, "fica", "A")
        _conversar(cliente, usuario, "sai", "B")
        with patch("app.agent.router.esquecer_conversas", return_value={"apagados": 1, "metodo": "teste"}) as esq:
            r = cliente.delete("/chat/history", params={"user_id": usuario, "session_id": "B"})
        assert r.status_code == 200 and r.json()["deleted_count"] == 2
        esq.assert_called_once_with(usuario, session_id="B")
        restante = cliente.get("/chat/history", params={"user_id": usuario}).json()
        assert {m["session_id"] for m in restante} == {"A"}


class TestAuxiliares:

    def test_texto_de_blocos(self):
        assert _texto([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]) == "ab"

    def test_ferramentas_so_depois_da_ultima_mensagem_humana(self):
        msgs = [
            HumanMessage(content="1"),
            AIMessage(content="", tool_calls=[{"name": "velha", "args": {}, "id": "1"}]),
            HumanMessage(content="2"),
            AIMessage(content="", tool_calls=[{"name": "nova", "args": {}, "id": "2"}]),
        ]
        assert _ferramentas_do_turno(msgs) == ["nova"]
