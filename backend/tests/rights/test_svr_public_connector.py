# tests/rights/test_svr_public_connector.py
# Conector da consulta pública oficial do SVR (T3 — consulta assistida)

import json
from datetime import date

import httpx
import pytest

from app.rights.connectors.svr_public import (
    SvrCaptchaInvalido,
    SvrIndisponivel,
    SvrPublicConnector,
    mask_cpf,
    validate_cpf,
)

# CPF válido de teste (dígitos verificadores corretos, uso comum em exemplos)
CPF_VALIDO = "52998224725"
NASCIMENTO = date(1990, 5, 17)


def _transport(handler):
    return httpx.MockTransport(handler)


# ── validação de CPF ─────────────────────────────────────────────────────────

def test_validate_cpf_aceita_valido_com_mascara():
    assert validate_cpf("529.982.247-25") == CPF_VALIDO


@pytest.mark.parametrize("cpf", ["12345678900", "11111111111", "123", ""])
def test_validate_cpf_rejeita_invalidos(cpf):
    with pytest.raises(ValueError):
        validate_cpf(cpf)


def test_mask_cpf_nunca_expoe_digitos_sensiveis():
    masked = mask_cpf(CPF_VALIDO)
    assert masked == "***.982.***-**"
    assert CPF_VALIDO[:3] not in masked and CPF_VALIDO[-2:] not in masked


# ── captcha ──────────────────────────────────────────────────────────────────

def test_get_captcha_ok():
    def handler(request):
        assert request.url.path.endswith("/captcha")
        return httpx.Response(200, json={"imagemBase64": "iVBOR...", "hash": "abc=="})

    captcha = SvrPublicConnector(transport=_transport(handler)).get_captcha()
    assert captcha.imagem_base64 == "iVBOR..."
    assert captcha.hash == "abc=="


def test_get_captcha_resposta_incompleta_gera_indisponivel():
    def handler(request):
        return httpx.Response(200, json={"outra": "coisa"})

    with pytest.raises(SvrIndisponivel):
        SvrPublicConnector(transport=_transport(handler)).get_captcha()


def test_get_captcha_http_500_gera_indisponivel():
    def handler(request):
        return httpx.Response(500)

    with pytest.raises(SvrIndisponivel):
        SvrPublicConnector(transport=_transport(handler)).get_captcha()


# ── consulta ─────────────────────────────────────────────────────────────────

def test_consultar_tem_valor():
    def handler(request):
        # rota: /valoresAReceber/{cpf}/{dataISO}/{hash}/{resposta}
        parts = request.url.path.split("/")
        assert parts[-4] == CPF_VALIDO
        assert parts[-3] == "1990-05-17"
        return httpx.Response(200, json={"temValorAReceber": True})

    resultado = SvrPublicConnector(transport=_transport(handler)).consultar(
        cpf="529.982.247-25",
        data_nascimento=NASCIMENTO,
        captcha_hash="h==",
        captcha_resposta="XK7P2",
    )
    assert resultado.tem_valor_a_receber is True
    assert resultado.consultado_em_nome_de == "***.982.***-**"


def test_consultar_sem_valor():
    def handler(request):
        return httpx.Response(200, json={"temValorAReceber": False})

    resultado = SvrPublicConnector(transport=_transport(handler)).consultar(
        CPF_VALIDO, NASCIMENTO, "h==", "ABC12"
    )
    assert resultado.tem_valor_a_receber is False


def test_consultar_captcha_errado_412():
    def handler(request):
        return httpx.Response(412)

    with pytest.raises(SvrCaptchaInvalido):
        SvrPublicConnector(transport=_transport(handler)).consultar(
            CPF_VALIDO, NASCIMENTO, "h==", "ERRADO"
        )


def test_consultar_resposta_captcha_vazia_falha_antes_da_rede():
    def handler(request):  # pragma: no cover - não deve ser chamado
        raise AssertionError("não deveria chamar a rede com captcha vazio")

    with pytest.raises(SvrCaptchaInvalido):
        SvrPublicConnector(transport=_transport(handler)).consultar(
            CPF_VALIDO, NASCIMENTO, "h==", "   "
        )


def test_consultar_cpf_invalido_falha_antes_da_rede():
    def handler(request):  # pragma: no cover
        raise AssertionError("não deveria chamar a rede com CPF inválido")

    with pytest.raises(ValueError):
        SvrPublicConnector(transport=_transport(handler)).consultar(
            "11111111111", NASCIMENTO, "h==", "ABC12"
        )


def test_consultar_hash_captcha_url_encoded():
    """Hash com '/' e '+' (base64) não pode quebrar o path."""
    seen = {}

    def handler(request):
        seen["raw_path"] = request.url.raw_path.decode()
        return httpx.Response(200, json={"temValorAReceber": False})

    SvrPublicConnector(transport=_transport(handler)).consultar(
        CPF_VALIDO, NASCIMENTO, "a/b+c==", "ABC12"
    )
    assert "a%2Fb%2Bc%3D%3D" in seen["raw_path"]


def test_consultar_falha_de_rede_gera_indisponivel():
    def handler(request):
        raise httpx.ConnectError("boom")

    with pytest.raises(SvrIndisponivel):
        SvrPublicConnector(transport=_transport(handler)).consultar(
            CPF_VALIDO, NASCIMENTO, "h==", "ABC12"
        )
