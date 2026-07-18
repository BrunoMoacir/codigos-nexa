"""
app/rights/connectors/serpro_restituicao.py — API Consulta Restituição (SERPRO)

Consulta REAL da restituição de IRPF apurada na última DIRPF, via API oficial
do SERPRO, mediante Autorização de Compartilhamento de Dados gerada pelo
PRÓPRIO contribuinte no Portal e-CAC (Sistema Compartilha Receita Federal).

Fluxo LGPD-nativo:
  1. Usuário autoriza o compartilhamento no e-CAC e recebe um token
  2. Usuário cola o token na Nexa
  3. Nexa consulta `GET /Consultar/{token}` e decripta os campos `valor`
     (RSA/ECB/PKCS1Padding com a chave privada do e-CNPJ do contratante)

Ambientes:
  Trial   : https://gateway.apiserpro.serpro.gov.br/consulta-restituicao-trial/v1
            Bearer fixo de demonstração (público na documentação do SERPRO)
  Produção: https://gateway.apiserpro.serpro.gov.br/consulta-restituicao/v1
            OAuth2 client_credentials (consumer key/secret do Loja SERPRO)

Códigos de retorno relevantes:
  200 → restituição encontrada (dados criptografados)
  404 → CPF sem restituição disponível no exercício atual
  403 → token de autorização expirado, já utilizado ou revogado
  401 → token de outra API/versão/contratante

Doc: https://apicenter.estaleiro.serpro.gov.br/documentacao/api-restituicao/
"""

from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass, field

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_GATEWAY = "https://gateway.apiserpro.serpro.gov.br"
_TRIAL_BASE = f"{_GATEWAY}/consulta-restituicao-trial/v1"
_PROD_BASE = f"{_GATEWAY}/consulta-restituicao/v1"
_TOKEN_URL = f"{_GATEWAY}/token"
# Chave pública de demonstração, publicada na própria documentação do SERPRO
_TRIAL_BEARER = "06aef429-a981-3ec5-a1f8-71d38d86481e"
_TIMEOUT = 20.0

_SITUACAO_DESCRICOES = {
    "01": "Restituição enviada para crédito",
    "02": "Em fila de restituição",
    "03": "Declaração em análise (malha)",
    "04": "Restituição devolvida ao Tesouro (reagendar no Portal BB)",
    "05": "Declaração retificada",
    "06": "Declaração cancelada",
    "07": "Restituição reagendada",
    "08": "Em processamento manual",
}


@dataclass
class RestituicaoResultado:
    encontrada: bool
    valor: float | None = None
    situacao_codigo: str | None = None
    situacao_descricao: str | None = None
    banco_codigo: str | None = None
    titular_cpf_mascarado: str | None = None
    aviso_legal: str | None = None
    campos_nao_decriptados: bool = False
    detalhe: str | None = None
    extras: dict = field(default_factory=dict)


class SerproNaoConfigurado(Exception):
    """Credenciais SERPRO ausentes — consulta real indisponível neste ambiente."""


class SerproTokenAutorizacaoInvalido(Exception):
    """Token de compartilhamento expirado, já utilizado, revogado ou de outra API."""


class SerproIndisponivel(Exception):
    """Gateway SERPRO fora do ar ou resposta inesperada."""


class SerproRestituicaoConnector:
    """
    Cliente da API Consulta Restituição. `transport` é injetável para testes.

    Configuração (Settings):
      SERPRO_RESTITUICAO_TRIAL       — usa ambiente trial com bearer de demo
      SERPRO_CONSUMER_KEY / _SECRET  — credenciais de produção (Loja SERPRO)
      SERPRO_RESTITUICAO_PRIVATE_KEY_B64 — chave privada RSA (DER PKCS#8 em
        base64, formato do arquivo `chave-privada` do e-CNPJ) p/ decriptação
    """

    def __init__(self, transport: httpx.BaseTransport | None = None):
        self._transport = transport
        self._token_cache: tuple[str, float] | None = None  # (token, expira_em)

    # ── configuração ────────────────────────────────────────────────────

    @property
    def trial(self) -> bool:
        return bool(getattr(settings, "SERPRO_RESTITUICAO_TRIAL", False))

    @property
    def is_configured(self) -> bool:
        if self.trial:
            return True
        return bool(
            getattr(settings, "SERPRO_CONSUMER_KEY", "")
            and getattr(settings, "SERPRO_CONSUMER_SECRET", "")
        )

    @property
    def _base_url(self) -> str:
        return _TRIAL_BASE if self.trial else _PROD_BASE

    # ── autenticação ────────────────────────────────────────────────────

    def _bearer(self) -> str:
        if self.trial:
            return _TRIAL_BEARER
        if not self.is_configured:
            raise SerproNaoConfigurado(
                "SERPRO_CONSUMER_KEY/SECRET não configurados — contrate a API "
                "Consulta Restituição na Loja SERPRO e defina as variáveis."
            )
        if self._token_cache and self._token_cache[1] > time.monotonic():
            return self._token_cache[0]

        creds = f"{settings.SERPRO_CONSUMER_KEY}:{settings.SERPRO_CONSUMER_SECRET}"
        basic = base64.b64encode(creds.encode()).decode()
        try:
            with httpx.Client(timeout=_TIMEOUT, transport=self._transport) as client:
                resp = client.post(
                    _TOKEN_URL,
                    data={"grant_type": "client_credentials"},
                    headers={"Authorization": f"Basic {basic}"},
                )
        except httpx.HTTPError as exc:
            raise SerproIndisponivel(f"Falha de rede no token SERPRO: {exc}") from exc
        if resp.status_code != 200:
            raise SerproIndisponivel(f"Token SERPRO retornou HTTP {resp.status_code}")

        payload = resp.json()
        token = payload.get("access_token")
        expires_in = int(payload.get("expires_in", 300))
        if not token:
            raise SerproIndisponivel("Token SERPRO sem access_token")
        # margem de 30s para não usar token à beira de expirar
        self._token_cache = (token, time.monotonic() + max(expires_in - 30, 30))
        return token

    # ── decriptação ─────────────────────────────────────────────────────

    def _private_key(self):
        """Carrega a chave RSA (DER PKCS#8 base64) uma única vez; None se ausente."""
        key_b64 = getattr(settings, "SERPRO_RESTITUICAO_PRIVATE_KEY_B64", "") or ""
        if not key_b64.strip():
            return None
        try:
            from cryptography.hazmat.primitives import serialization

            der = base64.b64decode(key_b64.strip())
            return serialization.load_der_private_key(der, password=None)
        except Exception as exc:
            logger.error("[SerproRestituicao] chave privada inválida: %s", exc)
            return None

    def _decrypt(self, key, valor_b64: str) -> str | None:
        try:
            from cryptography.hazmat.primitives.asymmetric import padding

            ciphertext = base64.b64decode(valor_b64)
            return key.decrypt(ciphertext, padding.PKCS1v15()).decode("utf-8")
        except Exception as exc:
            logger.warning("[SerproRestituicao] falha ao decriptar campo: %s", exc)
            return None

    # ── consulta ────────────────────────────────────────────────────────

    def consultar(self, token_compartilhamento: str) -> RestituicaoResultado:
        """
        Consulta a restituição usando o token de Autorização de
        Compartilhamento de Dados gerado pelo titular no e-CAC.
        """
        token_compartilhamento = token_compartilhamento.strip()
        if not token_compartilhamento:
            raise SerproTokenAutorizacaoInvalido("Token de compartilhamento vazio")

        bearer = self._bearer()
        try:
            with httpx.Client(
                base_url=self._base_url,
                timeout=_TIMEOUT,
                headers={"Authorization": f"Bearer {bearer}"},
                transport=self._transport,
            ) as client:
                resp = client.get(f"/Consultar/{token_compartilhamento}")
        except httpx.HTTPError as exc:
            raise SerproIndisponivel(f"Falha de rede na consulta SERPRO: {exc}") from exc

        if resp.status_code == 404:
            return RestituicaoResultado(
                encontrada=False,
                detalhe="O CPF não possui restituição disponível no exercício atual.",
            )
        if resp.status_code in (401, 403):
            raise SerproTokenAutorizacaoInvalido(
                "Token de autorização expirado, já utilizado, revogado ou de outra API. "
                "Gere um novo no Portal e-CAC (Compartilha Receita Federal)."
            )
        if resp.status_code == 429:
            raise SerproIndisponivel(
                "Limite de requisições do gateway SERPRO atingido — aguarde alguns "
                "segundos e tente novamente."
            )
        if resp.status_code != 200:
            raise SerproIndisponivel(f"SERPRO retornou HTTP {resp.status_code}")

        payload = resp.json()
        titular = str(payload.get("autorizacao", {}).get("titular", ""))
        resultado = RestituicaoResultado(
            encontrada=True,
            titular_cpf_mascarado=(f"***.{titular[3:6]}.***-**" if len(titular) == 11 else None),
            aviso_legal=payload.get("autorizacao", {}).get("avisoLegal"),
        )

        key = self._private_key()
        if key is None:
            resultado.campos_nao_decriptados = True
            resultado.detalhe = (
                "Restituição encontrada, mas SERPRO_RESTITUICAO_PRIVATE_KEY_B64 não está "
                "configurada — os campos retornam criptografados pelo SERPRO."
            )
            return resultado

        for dado in payload.get("dados", []):
            codigo = str(dado.get("codigo", ""))
            texto = self._decrypt(key, dado.get("valor", ""))
            if texto is None:
                resultado.campos_nao_decriptados = True
                continue
            if codigo == "1":  # Valor da Restituição
                try:
                    resultado.valor = float(texto.replace(".", "").replace(",", "."))
                except ValueError:
                    resultado.extras["valor_bruto"] = texto
            elif codigo == "2":  # Código da Situação
                resultado.situacao_codigo = texto.strip()
                resultado.situacao_descricao = _SITUACAO_DESCRICOES.get(texto.strip())
            elif codigo == "3":  # Descrição da Situação (fonte oficial prevalece)
                resultado.situacao_descricao = texto.strip()
            elif codigo == "4":  # Banco indicado
                resultado.banco_codigo = texto.strip()
            else:
                resultado.extras[dado.get("texto", codigo)] = texto

        logger.info(
            "[SerproRestituicao] consulta ok titular=%s encontrada=%s situacao=%s",
            resultado.titular_cpf_mascarado, resultado.encontrada, resultado.situacao_codigo,
        )
        return resultado
