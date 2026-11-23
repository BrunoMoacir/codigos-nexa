# tests/test_pluggy_vinculo_de_item.py — POST /pluggy/items só vincula a
# conexão que a Pluggy diz ser DESTE usuário (clientUserId do connect token).
# Antes, qualquer item_id enviado era gravado: quem obtivesse o id do item de
# outra pessoa vinculava o banco dela à própria conta e sincronizava o extrato.

import uuid

import pytest
import requests
from fastapi.testclient import TestClient

from app.api.v1.routes import pluggy as rota_pluggy
from app.core.config import settings

BASE = "/api/v1"
SENHA = "SenhaForte@2026"


@pytest.fixture(scope="module")
def cliente():
    from app.main import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def pluggy_configurada(monkeypatch):
    monkeypatch.setattr(settings, "PLUGGY_CLIENT_ID", "id-de-teste")
    monkeypatch.setattr(settings, "PLUGGY_CLIENT_SECRET", "segredo-de-teste")


def _conta(cliente):
    email = f"plg_{uuid.uuid4().hex[:8]}@nexa.test"
    r = cliente.post(f"{BASE}/auth/register", json={"email": email, "password": SENHA, "accepted_terms": True})
    assert r.status_code == 201, r.text
    t = cliente.post(f"{BASE}/auth/token", data={"username": email, "password": SENHA})
    assert t.status_code == 200, t.text
    return r.json()["user_id"], {"Authorization": f"Bearer {t.json()['access_token']}"}


def _pluggy_falsa(monkeypatch, *, dono=None, erro_http=None, chamadas=None):
    class PluggyFalsa:
        def get_item(self, item_id):
            if chamadas is not None:
                chamadas.append(item_id)
            if erro_http:
                resposta = requests.Response()
                resposta.status_code = erro_http
                raise requests.HTTPError(response=resposta)
            return {"id": item_id, "clientUserId": dono, "connector": {"name": "Banco Teste"}}

    monkeypatch.setattr(rota_pluggy, "PluggyClient", PluggyFalsa)


def _itens_salvos(user_id):
    from app.core.database import SessionLocal
    from app.core.models.pluggy_item import PluggyItem

    with SessionLocal() as db:
        return [(i.item_id, i.connector_name) for i in db.query(PluggyItem).filter(PluggyItem.user_id == user_id)]


def test_vincula_item_criado_para_o_proprio_usuario(cliente, pluggy_configurada, monkeypatch):
    uid, auth = _conta(cliente)
    item = str(uuid.uuid4())
    _pluggy_falsa(monkeypatch, dono=uid)
    r = cliente.post(f"{BASE}/pluggy/items", json={"item_id": item}, headers=auth)
    assert r.status_code == 200, r.text
    assert _itens_salvos(uid) == [(item, "Banco Teste")]


def test_recusa_item_de_outra_conta(cliente, pluggy_configurada, monkeypatch):
    uid, auth = _conta(cliente)
    outro, _ = _conta(cliente)
    _pluggy_falsa(monkeypatch, dono=outro)
    r = cliente.post(f"{BASE}/pluggy/items", json={"item_id": str(uuid.uuid4())}, headers=auth)
    assert r.status_code == 403
    assert _itens_salvos(uid) == []


def test_recusa_item_sem_dono_declarado(cliente, pluggy_configurada, monkeypatch):
    # item criado fora do nosso connect token (sem clientUserId) não é de ninguém aqui
    uid, auth = _conta(cliente)
    _pluggy_falsa(monkeypatch, dono=None)
    r = cliente.post(f"{BASE}/pluggy/items", json={"item_id": str(uuid.uuid4())}, headers=auth)
    assert r.status_code == 403
    assert _itens_salvos(uid) == []


@pytest.mark.parametrize("codigo_pluggy, esperado", [(404, 404), (400, 404), (500, 502)])
def test_falha_da_pluggy_nao_vincula(cliente, pluggy_configurada, monkeypatch, codigo_pluggy, esperado):
    uid, auth = _conta(cliente)
    _pluggy_falsa(monkeypatch, erro_http=codigo_pluggy)
    r = cliente.post(f"{BASE}/pluggy/items", json={"item_id": str(uuid.uuid4())}, headers=auth)
    assert r.status_code == esperado
    assert "Traceback" not in r.text
    assert _itens_salvos(uid) == []


@pytest.mark.parametrize("item_id", ["../connectors", "abc", "00000000-0000-0000-0000-000000000000/../../x"])
def test_item_id_fora_do_formato_nem_chega_na_pluggy(cliente, pluggy_configurada, monkeypatch, item_id):
    # o item_id vira caminho na API da Pluggy, chamada com a NOSSA credencial
    _, auth = _conta(cliente)
    chamadas: list[str] = []
    _pluggy_falsa(monkeypatch, dono="qualquer", chamadas=chamadas)
    r = cliente.post(f"{BASE}/pluggy/items", json={"item_id": item_id}, headers=auth)
    assert r.status_code == 422
    assert chamadas == []


def test_sem_pluggy_configurada_responde_503(cliente, monkeypatch):
    monkeypatch.setattr(settings, "PLUGGY_CLIENT_ID", "")
    _, auth = _conta(cliente)
    r = cliente.post(f"{BASE}/pluggy/items", json={"item_id": str(uuid.uuid4())}, headers=auth)
    assert r.status_code == 503


def test_sem_login_nao_vincula(cliente):
    r = cliente.post(f"{BASE}/pluggy/items", json={"item_id": str(uuid.uuid4())})
    assert r.status_code == 401
