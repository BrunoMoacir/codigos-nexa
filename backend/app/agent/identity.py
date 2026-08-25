"""
app/agent/identity.py — o user_id das ferramentas vem do token, não do LLM.

O que faltava: **nenhuma das 31 ferramentas recebia o usuário autenticado.**
`user_id` era um argumento que o modelo preenchia, e cada tool consultava o
banco por ele sem checagem de posse. Verificado antes da correção:

    get_bank_cost_analysis(user_id="demo-ana")
      → "Total pago em tarifas: R$ 174,50 | Projeção anual: R$ 348,96"

As defesas que existiam protegem o transporte, não o argumento:

  camada 1  `chat_request.user_id != current_user` → 403   (o user_id da REQUISIÇÃO)
  camada 2  regex apaga `[user_id=...]` do corpo da mensagem (o TEXTO)
  camada 3  o system prompt manda ignorar outros user_ids   (o MODELO)

Para o vetor "o modelo chama a ferramenta com outro id", as camadas 1 e 2 não
se aplicam — sobrava só a 3, que é comportamental. Este módulo fecha isso com
uma barreira determinística: o `user_id` de toda tool é SOBRESCRITO pelo
usuário autenticado da requisição.

Sem identidade estabelecida a ferramenta não roda. Falhar fechado: uma tool que
consulta dados sem saber de quem é o pior resultado possível.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator, Optional

from langchain_core.tools import StructuredTool

logger = logging.getLogger(__name__)

_USUARIO_AUTENTICADO: ContextVar[Optional[str]] = ContextVar(
    "nexa_usuario_autenticado", default=None
)

_SEM_IDENTIDADE = (
    "FALHA DE IDENTIDADE: a sessão não tem usuário autenticado, então nenhuma "
    "consulta a dados pessoais pode ser feita. Informe ao usuário que a sessão "
    "precisa ser reiniciada — não tente outra ferramenta."
)


def usuario_autenticado() -> Optional[str]:
    """User_id da requisição em curso, ou None fora de uma requisição."""
    return _USUARIO_AUTENTICADO.get()


@contextmanager
def usuario_da_requisicao(user_id: str) -> Iterator[None]:
    """
    Fixa o usuário autenticado enquanto durar o bloco.

    Precisa envolver a chamada ao agente DENTRO da thread que a executa: o
    `run_in_executor` do asyncio não copia o contexto por conta própria.
    """
    token = _USUARIO_AUTENTICADO.set(user_id)
    try:
        yield
    finally:
        _USUARIO_AUTENTICADO.reset(token)


def _vincular(nome: str, func: Callable) -> Callable:
    """Envolve a função da tool sobrescrevendo `user_id` pelo autenticado."""

    def vinculada(*args: Any, **kwargs: Any) -> Any:
        dono = usuario_autenticado()
        if dono is None:
            logger.error("[Agent] %s chamada sem usuário autenticado no contexto.", nome)
            return _SEM_IDENTIDADE

        pedido = kwargs.get("user_id")
        if pedido is not None and pedido != dono:
            # Não é erro do usuário: ou o modelo alucinou o id, ou alguém
            # conseguiu instruí-lo a pedir dados de outra conta. Os dois casos
            # interessam a quem opera o sistema.
            logger.warning(
                "[Agent] %s pediu user_id=%r; sobrescrito pelo autenticado %r.",
                nome, pedido, dono,
            )
        kwargs["user_id"] = dono
        return func(*args, **kwargs)

    vinculada.__name__ = getattr(func, "__name__", nome)
    vinculada.__doc__ = func.__doc__
    return vinculada


def vincular_ao_usuario(tool: Any) -> StructuredTool:
    """
    Cópia da tool cujo `user_id` sempre vem do contexto autenticado.

    Preserva `name`, `description` e `args_schema` — é o que o grafo usa para
    rotear e o que `scripts/run_agent_evals.py` reaproveita ao trocar os corpos
    por fixtures. O registro `AGENT_TOOLS` continua com as tools cruas; a
    vinculação acontece no build do agente, que é onde existe requisição.
    """
    func = getattr(tool, "func", None)
    if func is None:  # tools async ou de outro tipo: melhor falhar no build
        raise TypeError(f"{getattr(tool, 'name', tool)!r} não expõe .func para vincular")

    return StructuredTool.from_function(
        func=_vincular(tool.name, func),
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
    )


__all__ = [
    "usuario_autenticado",
    "usuario_da_requisicao",
    "vincular_ao_usuario",
]
