# app/optimizer/validators/input_validator.py
# InputValidator — valida OptimizationRequest com regras de negócio
# Passo 2.4 — Funcionalidade 2: Nexa Optimizer

from __future__ import annotations

from app.optimizer.models import OptimizationRequest


class InputValidator:
    """
    Valida regras de negócio do OptimizationRequest.

    Regras:
        R1  user_id não vazio
        R2  safe_to_spend >= 0 se fornecido
        R3  monthly_income > 0 se fornecido
        R4  pelo menos um de safe_to_spend / monthly_income deve ser informado

    Levanta ValueError com mensagem descritiva na primeira regra violada.
    """

    def validate(self, request: OptimizationRequest) -> None:
        """
        Valida o request. Levanta ValueError na primeira regra violada.

        Args:
            request: OptimizationRequest a ser validado.

        Raises:
            ValueError: mensagem indicando qual regra foi violada.
        """
        # R1 — user_id obrigatório
        if not request.user_id or not request.user_id.strip():
            raise ValueError("user_id é obrigatório")

        # R2 — safe_to_spend não pode ser negativo
        if request.safe_to_spend is not None and request.safe_to_spend < 0:
            raise ValueError("safe_to_spend não pode ser negativo")

        # R3 — monthly_income deve ser positivo se fornecido
        if request.monthly_income is not None and request.monthly_income <= 0:
            raise ValueError("renda mensal deve ser positiva")

        # R4 — pelo menos um dos dois deve ser informado
        if request.safe_to_spend is None and request.monthly_income is None:
            raise ValueError("informe safe_to_spend ou monthly_income")
