# tests/rights/test_serpro_restituicao_connector.py
# Conector da API Consulta Restituição (SERPRO) — T3 consulta autorizada

import base64

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.core.config import settings
from app.rights.connectors.serpro_restituicao import (
    SerproIndisponivel,
    SerproRestituicaoConnector,
    SerproTokenAutorizacaoInvalido,
)

TOKEN = "tokenDeCompartilhamentoValido123"


@pytest.fixture
def rsa_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    der = key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return key, base64.b64encode(der).decode()


def _encrypt(public_key, plaintext: str) -> str:
    ct = public_key.encrypt(plaintext.encode(), padding.PKCS1v15())
    return base64.b64encode(ct).decode()


@pytest.fixture
def trial_mode(monkeypatch):
    monkeypatch.setattr(settings, "SERPRO_RESTITUICAO_TRIAL", True, raising=False)


def _payload(public_key):
    return {
        "autorizacao": {
            "token": TOKEN,
            "titular": "12345678909",
            "avisoLegal": "Acesso autorizado pelo cidadão (LGPD art. 7º/11º).",
        },
        "idServico": "9001",
        "servico": "APIConsultaRestituicao",
        "versao": "1.0",
        "dados": [
            {"codigo": "1", "texto": "Valor da Restituição", "valor": _encrypt(public_key, "1.234,56")},
            {"codigo": "2", "texto": "Código da Situação Declaração", "valor": _encrypt(public_key, "02")},
            {"codigo": "3", "texto": "Descrição da Situação Declaração", "valor": _encrypt(public_key, "Em fila de restituição")},
            {"codigo": "4", "texto": "Código do Banco", "valor": _encrypt(public_key, "001")},
        ],
    }


def test_trial_is_configured_sem_credenciais(trial_mode):
    assert SerproRestituicaoConnector().is_configured is True


def test_producao_sem_credenciais_nao_configurado(monkeypatch):
    monkeypatch.setattr(settings, "SERPRO_RESTITUICAO_TRIAL", False, raising=False)
    monkeypatch.setattr(settings, "SERPRO_CONSUMER_KEY", "", raising=False)
    monkeypatch.setattr(settings, "SERPRO_CONSUMER_SECRET", "", raising=False)
    assert SerproRestituicaoConnector().is_configured is False


def test_consultar_encontrada_decripta_campos(trial_mode, monkeypatch, rsa_keypair):
    key, key_b64 = rsa_keypair
    monkeypatch.setattr(settings, "SERPRO_RESTITUICAO_PRIVATE_KEY_B64", key_b64, raising=False)

    def handler(request):
        assert request.url.path.endswith(f"/Consultar/{TOKEN}")
        assert request.headers["Authorization"].startswith("Bearer ")
        return httpx.Response(200, json=_payload(key.public_key()))

    resultado = SerproRestituicaoConnector(
        transport=httpx.MockTransport(handler)
    ).consultar(TOKEN)

    assert resultado.encontrada is True
    assert resultado.valor == pytest.approx(1234.56)
    assert resultado.situacao_codigo == "02"
    assert resultado.situacao_descricao == "Em fila de restituição"
    assert resultado.banco_codigo == "001"
    assert resultado.titular_cpf_mascarado == "***.456.***-**"
    assert resultado.campos_nao_decriptados is False


def test_consultar_sem_chave_privada_marca_nao_decriptado(trial_mode, monkeypatch, rsa_keypair):
    key, _ = rsa_keypair
    monkeypatch.setattr(settings, "SERPRO_RESTITUICAO_PRIVATE_KEY_B64", "", raising=False)

    def handler(request):
        return httpx.Response(200, json=_payload(key.public_key()))

    resultado = SerproRestituicaoConnector(
        transport=httpx.MockTransport(handler)
    ).consultar(TOKEN)

    assert resultado.encontrada is True
    assert resultado.valor is None
    assert resultado.campos_nao_decriptados is True


def test_consultar_404_sem_restituicao(trial_mode):
    def handler(request):
        return httpx.Response(404, text="O CPF não possui restituição disponível no exercício atual.")

    resultado = SerproRestituicaoConnector(
        transport=httpx.MockTransport(handler)
    ).consultar(TOKEN)
    assert resultado.encontrada is False


@pytest.mark.parametrize("status", [401, 403])
def test_consultar_token_invalido(trial_mode, status):
    def handler(request):
        return httpx.Response(status)

    with pytest.raises(SerproTokenAutorizacaoInvalido):
        SerproRestituicaoConnector(transport=httpx.MockTransport(handler)).consultar(TOKEN)


def test_consultar_token_vazio_falha_antes_da_rede(trial_mode):
    def handler(request):  # pragma: no cover
        raise AssertionError("não deveria chamar a rede com token vazio")

    with pytest.raises(SerproTokenAutorizacaoInvalido):
        SerproRestituicaoConnector(transport=httpx.MockTransport(handler)).consultar("  ")


def test_consultar_gateway_fora_gera_indisponivel(trial_mode):
    def handler(request):
        return httpx.Response(502)

    with pytest.raises(SerproIndisponivel):
        SerproRestituicaoConnector(transport=httpx.MockTransport(handler)).consultar(TOKEN)


def test_producao_obtem_e_cacheia_token_oauth(monkeypatch, rsa_keypair):
    key, key_b64 = rsa_keypair
    monkeypatch.setattr(settings, "SERPRO_RESTITUICAO_TRIAL", False, raising=False)
    monkeypatch.setattr(settings, "SERPRO_CONSUMER_KEY", "ck", raising=False)
    monkeypatch.setattr(settings, "SERPRO_CONSUMER_SECRET", "cs", raising=False)
    monkeypatch.setattr(settings, "SERPRO_RESTITUICAO_PRIVATE_KEY_B64", key_b64, raising=False)

    calls = {"token": 0, "consulta": 0}

    def handler(request):
        if request.url.path == "/token":
            calls["token"] += 1
            expected = base64.b64encode(b"ck:cs").decode()
            assert request.headers["Authorization"] == f"Basic {expected}"
            return httpx.Response(200, json={"access_token": "tok123", "expires_in": 3600})
        calls["consulta"] += 1
        assert request.headers["Authorization"] == "Bearer tok123"
        assert "/consulta-restituicao/v1/" in str(request.url)
        return httpx.Response(200, json=_payload(key.public_key()))

    connector = SerproRestituicaoConnector(transport=httpx.MockTransport(handler))
    connector.consultar(TOKEN)
    connector.consultar(TOKEN)

    assert calls["consulta"] == 2
    assert calls["token"] == 1  # segunda chamada usa o cache do token
