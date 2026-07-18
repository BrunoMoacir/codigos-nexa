"""
app/rights/connectors/svr_public.py — Consulta Pública do SVR BACEN (T3)

Cliente da consulta pública oficial do Sistema de Valores a Receber:
https://valoresareceber.bcb.gov.br/publico

A consulta pública é a etapa 1 do fluxo oficial do BACEN: informa SE existe
valor a receber para um CPF/CNPJ + data de nascimento (ou abertura), sem
revelar o montante. O montante e o resgate exigem login GOV.BR no portal.

Fluxo assistido (o mesmo do site oficial, dentro da Nexa):
  1. `get_captcha()`      → imagem base64 + hash, exibida ao usuário no app
  2. usuário digita a resposta do captcha (humano permanece no loop — a Nexa
     NUNCA resolve nem contorna o captcha)
  3. `consultar(...)`     → {tem_valor_a_receber: bool} da API pública

API mapeada do próprio frontend oficial (bundle Angular, 2026-07):
  GET /publico/rest/captcha
  GET /publico/rest/valoresAReceber/{cpfCnpj}/{dataISO}/{hashCaptcha}/{resposta}
  HTTP 412 → resposta de captcha incorreta/expirada (gerar novo captcha)

LGPD: CPF e data de nascimento são usados apenas na chamada, nunca
persistidos; logs registram somente CPF mascarado.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://valoresareceber.bcb.gov.br/publico/rest"
_TIMEOUT = 15.0
_USER_AGENT = "NexaAI/1.0 (consulta publica SVR; fluxo assistido pelo titular)"


def mask_cpf(cpf: str) -> str:
    """'12345678909' → '***.456.***-**' — para logs (LGPD)."""
    digits = "".join(ch for ch in cpf if ch.isdigit())
    if len(digits) != 11:
        return "***"
    return f"***.{digits[3:6]}.***-**"


def validate_cpf(cpf: str) -> str:
    """
    Valida CPF (dígitos verificadores) e retorna apenas os 11 dígitos.
    Levanta ValueError para CPF malformado — evita chamada inútil ao BACEN.
    """
    digits = "".join(ch for ch in cpf if ch.isdigit())
    if len(digits) != 11 or digits == digits[0] * 11:
        raise ValueError("CPF inválido")
    for i in (9, 10):
        weights = range(i + 1, 1, -1)
        total = sum(int(d) * w for d, w in zip(digits[:i], weights))
        check = (total * 10) % 11 % 10
        if check != int(digits[i]):
            raise ValueError("CPF inválido")
    return digits


@dataclass
class SvrCaptcha:
    imagem_base64: str
    hash: str
    audio_base64: str | None = None  # acessibilidade, quando fornecido


@dataclass
class SvrResultado:
    tem_valor_a_receber: bool
    consultado_em_nome_de: str  # CPF mascarado


class SvrCaptchaInvalido(Exception):
    """Resposta de captcha incorreta ou expirada (HTTP 412) — gerar novo."""


class SvrIndisponivel(Exception):
    """SVR fora do ar, em fila de espera ou resposta inesperada."""


class SvrPublicConnector:
    """
    Cliente da consulta pública do SVR. `transport` é injetável para testes
    (httpx.MockTransport); em produção usa HTTPS direto ao BACEN.
    """

    def __init__(self, transport: httpx.BaseTransport | None = None):
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=_BASE_URL,
            timeout=_TIMEOUT,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
            transport=self._transport,
        )

    def get_captcha(self) -> SvrCaptcha:
        """Obtém o desafio oficial do BACEN para exibir ao usuário."""
        try:
            with self._client() as client:
                resp = client.get("/captcha")
        except httpx.HTTPError as exc:
            raise SvrIndisponivel(f"Falha de rede ao obter captcha do SVR: {exc}") from exc

        if resp.status_code != 200:
            raise SvrIndisponivel(f"SVR captcha retornou HTTP {resp.status_code}")

        data = resp.json()
        imagem = data.get("imagemBase64") or data.get("imagem")
        hash_ = data.get("hash") or data.get("hashCaptcha")
        if not imagem or not hash_:
            raise SvrIndisponivel("Resposta do captcha SVR sem imagem ou hash")
        return SvrCaptcha(
            imagem_base64=imagem,
            hash=hash_,
            audio_base64=data.get("audioBase64"),
        )

    def consultar(
        self,
        cpf: str,
        data_nascimento: date,
        captcha_hash: str,
        captcha_resposta: str,
    ) -> SvrResultado:
        """
        Consulta pública oficial: existe valor a receber para este CPF?

        A resposta do captcha vem digitada pelo usuário — exatamente como no
        portal oficial. HTTP 412 indica captcha incorreto/expirado.
        """
        cpf_digits = validate_cpf(cpf)
        if not captcha_resposta.strip():
            raise SvrCaptchaInvalido("Resposta do captcha vazia")

        path = (
            f"/valoresAReceber/{cpf_digits}/{data_nascimento.isoformat()}"
            f"/{quote(captcha_hash, safe='')}/{quote(captcha_resposta.strip(), safe='')}"
        )
        try:
            with self._client() as client:
                resp = client.get(path)
        except httpx.HTTPError as exc:
            raise SvrIndisponivel(f"Falha de rede na consulta SVR: {exc}") from exc

        if resp.status_code == 412:
            raise SvrCaptchaInvalido("Captcha incorreto ou expirado")
        if resp.status_code != 200:
            raise SvrIndisponivel(f"SVR retornou HTTP {resp.status_code}")

        data = resp.json()
        if "temValorAReceber" not in data:
            raise SvrIndisponivel("Resposta do SVR sem o campo temValorAReceber")

        masked = mask_cpf(cpf_digits)
        logger.info("[SvrPublic] consulta cpf=%s tem_valor=%s", masked, data["temValorAReceber"])
        return SvrResultado(
            tem_valor_a_receber=bool(data["temValorAReceber"]),
            consultado_em_nome_de=masked,
        )
