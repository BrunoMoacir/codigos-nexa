#app/core/safe_to_spend.py
from typing import Dict


def calculate_safe_to_spend(
    balance: float,
    projected_expenses: float,
    safety_margin: float = 0.15
) -> Dict:
    """
    Calcula quanto o usuário pode gastar com segurança.

    Fórmula:
      safe = (saldo - despesas futuras) * (1 - margem de segurança)
    """

    raw = balance - projected_expenses

    safe_value = raw * (1 - safety_margin)

    return {
        "current_balance": round(balance, 2),
        "projected_expenses": round(projected_expenses, 2),
        "safety_margin": safety_margin,
        "safe_to_spend": round(max(safe_value, 0), 2),
    }
