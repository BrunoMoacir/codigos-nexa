# app/core/explain.py

def explain_safe_to_spend(result: dict) -> str:
    """
    Gera explicação humana para o Safe-to-Spend.
    """

    daily = result.get("safe_to_spend_daily", 0)
    total = result.get("safe_to_spend_total", 0)
    min_balance = result.get("min_projected_balance", 0)
    buffer = result.get("buffer", 0)
    days = result.get("days", 30)

    if daily <= 0:
        return (
            "⚠️ No momento, não há margem segura para novos gastos. "
            "Suas despesas projetadas comprometem totalmente o saldo disponível."
        )

    explanation = (
        f"Você pode gastar até R$ {daily:,.2f} por dia com segurança "
        f"nos próximos {days} dias.\n\n"
        f"Mesmo no pior cenário, seu saldo não cai abaixo de "
        f"R$ {min_balance:,.2f}, mantendo um buffer de segurança "
        f"de R$ {buffer:,.2f}."
    )

    return explanation
