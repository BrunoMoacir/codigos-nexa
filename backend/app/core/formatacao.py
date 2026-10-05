"""
app/core/formatacao.py — Números em português do Brasil.

Os textos que o backend monta (cards do feed, alertas, metas, defesa, roteiro
do negociador, retorno das ferramentas do agente) formatavam dinheiro com
`f"R$ {valor:,.2f}"`, que é o padrão americano: "R$ 16,622.86". Para quem lê
em pt-BR — e para o LLM, que relê o texto da ferramenta — isso é dezesseis
reais e sessenta e dois centavos, não dezesseis mil.
"""

from __future__ import annotations


def _agrupar(valor: float, casas: int) -> str:
    texto = f"{abs(valor):,.{casas}f}"  # 1,234.56 (en-US)
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def brl(valor, casas: int = 2) -> str:
    """R$ 1.234,56 — negativo como -R$ 1.234,56 (convenção do Intl pt-BR)."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return "R$ —"
    negativo = round(v, casas) < 0
    return f"{'-' if negativo else ''}R$ {_agrupar(v, casas)}"


def numero(valor, casas: int = 0) -> str:
    """1.234 ou 1.234,5 — separador de milhar ponto, decimal vírgula."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return "—"
    negativo = round(v, casas) < 0
    return f"{'-' if negativo else ''}{_agrupar(v, casas)}"


__all__ = ["brl", "numero"]
