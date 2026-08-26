"""
app/core/observabilidade.py — captura de erro de produção.

O `sentry-sdk` estava no ambiente e **nunca era inicializado**. O audit
registrava eventos de negócio (login, reset, export LGPD), mas uma exceção em
produção não alertava ninguém — a doc de segurança listava isso como
recomendado antes da beta.

Ligar telemetria num produto que processa extrato bancário exige cuidado
específico, e as três decisões abaixo são o que separa observabilidade de
vazamento:

  * **`send_default_pii=False`** — sem isso o SDK anexa corpo de requisição,
    cookies e cabeçalhos. Aqui isso seria enviar transação bancária para um
    terceiro.
  * **Scrub explícito** dos campos que este produto conhece (token, senha,
    CPF, e-mail) além do padrão do SDK, e do prefixo `[user_id=...]` que o
    agente injeta nas mensagens.
  * **Desligado por padrão** — sem `SENTRY_DSN` nada é inicializado e nada
    sai da máquina. Não há "modo de teste" que envia por acidente.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Campos cujo VALOR nunca pode sair daqui, além do que o SDK já filtra.
_CAMPOS_SENSIVEIS = (
    "password", "senha", "new_password", "token", "access_token",
    "refresh_token", "authorization", "secret", "api_key", "cpf",
    "hashed_password", "token_hash", "email",
)

_PREFIXO_AGENTE = re.compile(r"\[\s*user_id\s*=[^\]]*\]", re.IGNORECASE)


def _limpar(evento, _hint):
    """
    Remove valor sensível antes do envio. Roda em TODO evento.

    Falha aberta de propósito: um erro aqui não pode impedir o envio de um
    alerta — mas também não pode deixar passar o dado. Por isso a limpeza é
    feita numa cópia e, se algo estourar, o evento inteiro é descartado.
    """
    try:
        def _varrer(no):
            if isinstance(no, dict):
                return {
                    chave: ("[removido]"
                            if any(s in str(chave).lower() for s in _CAMPOS_SENSIVEIS)
                            else _varrer(valor))
                    for chave, valor in no.items()
                }
            if isinstance(no, list):
                return [_varrer(item) for item in no]
            if isinstance(no, str):
                return _PREFIXO_AGENTE.sub("[user_id=removido]", no)
            return no

        return _varrer(evento)
    except Exception:
        return None  # na dúvida, não envia


def iniciar_observabilidade() -> bool:
    """
    Inicializa o Sentry se houver DSN. Devolve se ficou ligado.

    Nunca levanta: falha de telemetria não pode derrubar o boot da API.
    """
    from app.core.config import settings

    dsn = (settings.SENTRY_DSN or "").strip()
    if not dsn:
        logger.info("[Observabilidade] SENTRY_DSN não definido — captura desligada.")
        return False

    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=dsn,
            environment=settings.APP_ENV,
            # Extrato bancário não vai para telemetria de terceiro.
            send_default_pii=False,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            before_send=_limpar,
        )
        logger.info("[Observabilidade] Sentry ativo (env=%s).", settings.APP_ENV)
        return True
    except Exception as exc:
        logger.error("[Observabilidade] Sentry não pôde ser inicializado: %s", exc)
        return False


__all__ = ["iniciar_observabilidade"]
