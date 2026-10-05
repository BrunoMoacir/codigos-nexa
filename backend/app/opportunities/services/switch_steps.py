"""
app/opportunities/services/switch_steps.py

OPP.5 (docs/ROADMAP.md) — Recomendação de troca com passos práticos.

Gera a lista de passos concretos para o usuário executar a migração do
dinheiro parado para um produto recomendado. Puramente apresentacional:
não faz I/O, não calcula rentabilidade — recebe os atributos do produto
já avaliado pelo BankComparator e devolve texto acionável em PT-BR.

A Nexa não executa a troca nem intermedia a aplicação — os passos são
orientação prática, sempre acompanhados do disclaimer regulatório
(ver DISCLAIMER em app/opportunities/services/opportunity_engine.py).
"""

from __future__ import annotations
from app.core.formatacao import brl

_FGC_LIMIT_BRL = 250_000.0

# Prazo (em dias) da tabela regressiva que zera a diferença de alíquota —
# usado só para avisar sobre resgate antecipado em produtos tributados.
_IR_BEST_RATE_DAYS = 720


def build_switch_steps(
    bank_name: str,
    product_type: str,
    liquidity_days: int,
    min_amount: float,
    is_exempt: bool,
    fgc_covered: bool,
    amount: float | None = None,
) -> list[str]:
    """
    Monta os passos práticos para migrar dinheiro parado para o produto.

    Args:
        bank_name:      Instituição emissora (ex: "Nubank", "Tesouro Direto").
        product_type:   "CDB" | "LCI" | "LCA" | "TESOURO_SELIC".
        liquidity_days: Prazo de liquidez em dias (1 = diária).
        min_amount:     Aplicação mínima (R$).
        is_exempt:      True para LCI/LCA (isentos de IR).
        fgc_covered:    True quando o produto tem garantia FGC.
        amount:         Valor que o usuário pretende aplicar (opcional,
                        usado para alertar sobre o teto do FGC).

    Returns:
        Lista ordenada de passos em PT-BR.
    """
    steps: list[str] = []

    if product_type == "TESOURO_SELIC":
        steps.append(
            "Abra conta em uma corretora ou banco habilitado no Tesouro Direto "
            "(a maioria não cobra taxa de administração para Tesouro)."
        )
        steps.append("Transfira o valor via PIX para a conta da corretora — cai na hora.")
        steps.append(
            "No app ou site, busque por 'Tesouro Selic' e aplique o valor desejado "
            "(aplicação mínima em torno de R$ 150)."
        )
        steps.append(
            "Guarde: a custódia B3 de 0,20% a.a. só incide sobre o que exceder "
            "R$ 10.000, e o resgate cai na conta em 1 dia útil (D+1)."
        )
        return steps

    steps.append(
        f"Abra (ou acesse) sua conta no {bank_name} — abertura é gratuita e 100% digital "
        "na maioria das instituições."
    )
    steps.append(
        f"Transfira o valor via PIX da sua conta atual para o {bank_name} — sem custo e imediato."
    )

    apply_step = f"No app do {bank_name}, acesse a área de investimentos e aplique no {product_type}"
    if min_amount > 1:
        apply_step += f" (aplicação mínima: {brl(min_amount)})"
    steps.append(apply_step + ".")

    if liquidity_days <= 1:
        steps.append(
            "Liquidez diária: você pode resgatar a qualquer momento e o dinheiro "
            "volta para a conta no mesmo dia ou em 1 dia útil."
        )
    else:
        steps.append(
            f"Atenção ao prazo: o resgate só ocorre no vencimento (~{liquidity_days} dias). "
            "Aplique apenas o valor que você não vai precisar nesse período."
        )

    if is_exempt:
        steps.append(
            f"{product_type} é isento de IR para pessoa física — o rendimento exibido já é o líquido."
        )
    else:
        steps.append(
            "O IR é regressivo e retido na fonte no resgate: quanto mais tempo aplicado, "
            f"menor a alíquota (mínima de 15% após {_IR_BEST_RATE_DAYS} dias)."
        )

    if fgc_covered:
        fgc_step = (
            f"O valor é garantido pelo FGC até {brl(_FGC_LIMIT_BRL, 0)} por CPF por instituição."
        )
        if amount is not None and amount > _FGC_LIMIT_BRL:
            fgc_step += (
                " Seu valor excede esse teto — considere dividir entre mais de uma instituição."
            )
        steps.append(fgc_step)

    return steps


__all__ = ["build_switch_steps"]
