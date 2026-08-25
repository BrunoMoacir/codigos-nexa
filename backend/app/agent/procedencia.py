"""
app/agent/procedencia.py — toda resposta de ferramenta diz de onde veio.

O agente tinha 31 ferramentas devolvendo prosa livre, e o modelo precisava
ADIVINHAR pelo texto se aquilo era medição, estimativa ou degradação. A regra 7
do system prompt manda admitir falha e não inventar número, mas não havia como
o modelo distinguir:

    "Tarifas identificadas: R$ 174,50"          ← medido, 6 meses de extrato
    "Tarifas identificadas: R$ 0,00"            ← medido, sem tarifas
    "Tarifas identificadas: R$ 0,00"            ← o detector não rodou

As três frases são iguais para quem só lê texto. A terceira vira "seu banco não
cobra tarifas", que é falso.

Uma ferramenta já resolvia isso, e resolvia bem: `get_card_optimization` emite
`[META] confidence_score_melhor_cartao` e `[META] dados_insuficientes`, e o
prompt tem regra de escalonamento em cima disso — abaixo de 0,50 o agente chama
o especialista. Este módulo generaliza esse padrão para todas as ferramentas,
num formato único:

    [NEXA] confianca=0.83 | cobertura=6 meses | fontes=transactions_clean,income_profiler

Curto de propósito: entra em todo resultado de ferramenta, em toda mensagem, e
token custa. Só o que muda a resposta.
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# Abaixo disto o agente não pode afirmar o número como se fosse medido — ver as
# regras de procedência no system prompt. É o mesmo limiar que o fluxo de
# cartões já usava para escalar ao especialista, agora valendo para todas.
LIMIAR_CONFIANCA_BAIXA = 0.50

_MARCADOR = "[NEXA]"


def _fmt_confianca(valor: Optional[float]) -> Optional[str]:
    if valor is None:
        return None
    return f"confianca={max(0.0, min(1.0, float(valor))):.2f}"


def _fmt_cobertura(meses: Optional[float]) -> Optional[str]:
    if meses is None:
        return None
    if meses <= 0:
        return "cobertura=sem historico"
    if meses < 1:
        return f"cobertura={int(round(meses * 30))} dias"
    return f"cobertura={meses:.0f} meses" if meses >= 2 else "cobertura=1 mes"


def com_procedencia(
    texto: str,
    *,
    fontes: Optional[Iterable[str]] = None,
    confianca: Optional[float] = None,
    cobertura_meses: Optional[float] = None,
    degradado: Optional[str] = None,
) -> str:
    """
    Anexa a linha de procedência ao resultado de uma ferramenta.

    Args:
        texto:           o resultado como o usuário final o veria.
        fontes:          integrações que REALMENTE responderam nesta chamada.
                         É o marcador que expôs as quatro integrações mortas do
                         F7 — uma fonte que some da lista é uma fonte que caiu.
        confianca:       0.0–1.0. Omitir quando não há como estimar; inventar
                         um 0.9 é pior que não informar.
        cobertura_meses: meses de extrato que sustentam o número.
        degradado:       motivo curto quando a resposta saiu de um caminho de
                         fallback. Presente = o agente NÃO pode apresentar o
                         número como medição.

    Returns:
        O texto com uma linha `[NEXA] ...` ao final. Sem nenhum campo
        preenchido, devolve o texto intacto — linha vazia não informa nada.
    """
    campos: list[str] = []

    conf = _fmt_confianca(confianca)
    if conf:
        campos.append(conf)

    cob = _fmt_cobertura(cobertura_meses)
    if cob:
        campos.append(cob)

    nomes = [f for f in (fontes or []) if f]
    if nomes:
        campos.append("fontes=" + ",".join(dict.fromkeys(nomes)))

    if degradado:
        campos.append(f"degradado={degradado}")

    if not campos:
        return texto

    return f"{texto.rstrip()}\n\n{_MARCADOR} " + " | ".join(campos)


def degradada(texto: str, motivo: str, *, fontes: Optional[Iterable[str]] = None) -> str:
    """
    Atalho para o caminho de fallback: confiança zero e motivo declarado.

    Usar sempre que a ferramenta devolver um resultado que NÃO veio do caminho
    principal — inclusive quando o texto parece completo.
    """
    return com_procedencia(texto, fontes=fontes, confianca=0.0, degradado=motivo)


def ler_procedencia(resultado: str) -> dict:
    """
    Faz o caminho inverso — usado em teste e em análise de conversa.

    Returns:
        `{"confianca": float|None, "cobertura": str|None, "fontes": [str],
          "degradado": str|None}`; dicionário vazio se não houver linha.
    """
    for linha in reversed(resultado.splitlines()):
        if not linha.startswith(_MARCADOR):
            continue
        dados: dict = {"confianca": None, "cobertura": None, "fontes": [], "degradado": None}
        for parte in linha[len(_MARCADOR):].split("|"):
            parte = parte.strip()
            if parte.startswith("confianca="):
                try:
                    dados["confianca"] = float(parte.split("=", 1)[1])
                except ValueError:
                    pass
            elif parte.startswith("cobertura="):
                dados["cobertura"] = parte.split("=", 1)[1]
            elif parte.startswith("fontes="):
                dados["fontes"] = [f for f in parte.split("=", 1)[1].split(",") if f]
            elif parte.startswith("degradado="):
                dados["degradado"] = parte.split("=", 1)[1]
        return dados
    return {}


__all__ = [
    "LIMIAR_CONFIANCA_BAIXA",
    "com_procedencia",
    "degradada",
    "ler_procedencia",
]
