"""
Origem dos dados (C11): o Perfil e a Home diziam "Dados reais" lendo uma
flag de localStorage que a tela de conexões gravava sem saber o conector —
persona de demonstração e sandbox apareciam como Open Finance real.
"""

from __future__ import annotations

import uuid

import pytest

from app.api.v1.routes.pluggy import _origem_da_conexao

BASE = "/api/v1"


@pytest.mark.parametrize("item_id,conector,esperado", [
    ("demo-item-demo-ana-nubank", "Nubank", "demonstracao"),
    ("a1b2c3", "Pluggy Bank", "sandbox"),
    ("a1b2c3", "Sandbox Bank (PF)", "sandbox"),
    ("a1b2c3", "Nubank", "open_finance"),
    ("a1b2c3", None, "open_finance"),
])
def test_origem_por_conexao(item_id, conector, esperado):
    assert _origem_da_conexao(item_id, conector) == esperado


@pytest.fixture
def cliente():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, raise_server_exceptions=False)


def _login(cliente):
    email = f"c11_{uuid.uuid4().hex[:8]}@nexa.test"
    r = cliente.post(f"{BASE}/auth/register", json={"email": email, "password": "SenhaForte@2024", "accepted_terms": True})
    assert r.status_code == 201, r.text
    t = cliente.post(f"{BASE}/auth/token", data={"username": email, "password": "SenhaForte@2024"})
    assert t.status_code == 200, t.text
    return {"Authorization": f"Bearer {t.json()['access_token']}"}


def test_usuario_sem_conexao_tem_origem_none(cliente):
    r = cliente.get(f"{BASE}/pluggy/connections", headers=_login(cliente))
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["total"] == 0
    assert corpo["data_source"] == "none"
    assert "pluggy_configured" in corpo
