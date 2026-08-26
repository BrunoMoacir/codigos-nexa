"""
app/core/login_throttle.py — bloqueio de credential stuffing POR CONTA.

O rate limit do login é 10/min **por IP**. Isso segura força bruta de uma
origem só e não segura nada de um atacante distribuído: mil IPs testando dez
senhas por minuto na mesma conta passam inteiros por baixo do limite, e cada
requisição parece perfeitamente normal.

Este módulo conta falhas por CONTA (identificada pelo e-mail submetido) e
bloqueia a conta por uma janela curta ao estourar o limite.

Duas decisões que importam:

**O bloqueio não pode virar oráculo de existência.** A contagem é pela string
que o cliente enviou, exista a conta ou não, e a resposta é a mesma nos dois
casos. Se só contas reais bloqueassem, o próprio bloqueio responderia "esse
e-mail existe" — que é exatamente o que o hash fictício de senha em
`security.py` foi feito para evitar.

**O e-mail nunca vira chave em claro no Redis.** Vai o SHA-256: quem lê o Redis
não colhe uma lista de e-mails de usuários.

Fail-open quando o Redis está fora, igual à blacklist de token: derrubar todo
login porque o cache caiu é pior que perder o bloqueio por conta, que é uma
segunda camada — a primeira (limite por IP) continua de pé.
"""

from __future__ import annotations

import hashlib
import logging

logger = logging.getLogger(__name__)

_PREFIXO = "nexa:login_fail:"

# 8 tentativas em 15 min. Um humano que errou a senha tenta 3 ou 4 vezes e vai
# para o "esqueci minha senha"; oito é folgado para o usuário e apertado para
# quem está varrendo uma lista de senhas vazadas.
MAX_TENTATIVAS = 8
JANELA_SEGUNDOS = 900


def _chave(email: str) -> str:
    normalizado = (email or "").strip().lower()
    return _PREFIXO + hashlib.sha256(normalizado.encode()).hexdigest()


def esta_bloqueada(email: str) -> bool:
    """A conta estourou o limite de falhas na janela?"""
    from app.core.cache import get_redis

    cliente = get_redis()
    if cliente is None:
        return False  # fail-open declarado — ver docstring do módulo
    try:
        return int(cliente.get(_chave(email)) or 0) >= MAX_TENTATIVAS
    except Exception as exc:
        logger.warning("[LoginThrottle] leitura falhou: %s", exc)
        return False


def registrar_falha(email: str) -> int:
    """
    Soma uma falha e devolve o total na janela (0 se não deu para contar).

    O TTL é fixado na PRIMEIRA falha e não é renovado nas seguintes: a janela é
    de 15 min desde o primeiro erro, não 15 min desde o último. Renovar a cada
    tentativa deixaria um atacante manter a conta bloqueada para sempre — o
    bloqueio viraria negação de serviço contra o dono.
    """
    from app.core.cache import get_redis

    cliente = get_redis()
    if cliente is None:
        return 0
    try:
        chave = _chave(email)
        total = cliente.incr(chave)
        if total == 1:
            cliente.expire(chave, JANELA_SEGUNDOS)
        return int(total)
    except Exception as exc:
        logger.warning("[LoginThrottle] contagem falhou: %s", exc)
        return 0


def limpar(email: str) -> None:
    """Zera o contador — chamado no login bem-sucedido."""
    from app.core.cache import get_redis

    cliente = get_redis()
    if cliente is None:
        return
    try:
        cliente.delete(_chave(email))
    except Exception as exc:
        logger.debug("[LoginThrottle] limpeza falhou: %s", exc)


__all__ = [
    "MAX_TENTATIVAS",
    "JANELA_SEGUNDOS",
    "esta_bloqueada",
    "registrar_falha",
    "limpar",
]
