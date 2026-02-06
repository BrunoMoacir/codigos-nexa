#app/domain/forecast_engine
from datetime import date, timedelta
from typing import Dict, List


class ForecastEngine:
    """
    Motor de projeção financeira.

    Responsável por simular o saldo futuro do usuário
    considerando gastos variáveis médios, despesas fixas,
    assinaturas e parcelamentos.

    Este componente é o núcleo do sistema de alertas
    de risco financeiro.
    """

    def project_balance(
        self,
        current_balance: float,
        daily_variable_spend: float,
        fixed_expenses: float,
        subscriptions: float,
        installments: float,
        days: int = 30
    ) -> Dict:
        """
        Simula o saldo dia a dia para um determinado horizonte.

        Args:
            current_balance (float): Saldo atual do usuário.
            daily_variable_spend (float): Gasto médio diário variável.
            fixed_expenses (float): Total mensal de despesas fixas.
            subscriptions (float): Total mensal de assinaturas.
            installments (float): Total mensal de parcelamentos.
            days (int): Quantidade de dias da simulação.

        Returns:
            Dict contendo:
                - projection: lista com saldo por dia
                - negative_day: dia em que o saldo fica negativo (ou None)
                - worst_balance: menor saldo atingido
                - risk_level: LOW | MEDIUM | HIGH
        """

        # -------------------------------------------------------------
        # 1) Converter despesas mensais em custo diário fixo
        # -------------------------------------------------------------
        daily_fixed_cost = (fixed_expenses + subscriptions + installments) / 30

        # -------------------------------------------------------------
        # 2) Inicializar variáveis da simulação
        # -------------------------------------------------------------
        balance = current_balance
        projection: List[Dict] = []
        negative_day = None
        worst_balance = balance

        # -------------------------------------------------------------
        # 3) Simulação dia a dia
        # -------------------------------------------------------------
        for day in range(1, days + 1):

            # Deduz o gasto variável médio + custo fixo diário
            balance -= (daily_variable_spend + daily_fixed_cost)

            # Armazena o saldo projetado
            projection.append({
                "day": day,
                "balance": round(balance, 2)
            })

            # Atualiza o pior saldo observado
            if balance < worst_balance:
                worst_balance = balance

            # Registra o primeiro dia em que o saldo ficou negativo
            if balance < 0 and negative_day is None:
                negative_day = day

        # -------------------------------------------------------------
        # 4) Classificação de risco financeiro
        # -------------------------------------------------------------
        risk_level = self._classify_risk(
            negative_day=negative_day,
            worst_balance=worst_balance
        )

        # -------------------------------------------------------------
        # 5) Retorno estruturado para API / dashboards
        # -------------------------------------------------------------
        return {
            "projection": projection,
            "negative_day": negative_day,
            "worst_balance": round(worst_balance, 2),
            "risk_level": risk_level
        }

    # =================================================================

    def _classify_risk(self, negative_day: int | None, worst_balance: float) -> str:
        """
        Classifica o risco financeiro com base na projeção.

        Critérios:
            - HIGH: saldo fica negativo em até 7 dias
            - MEDIUM: saldo fica negativo entre 8 e 30 dias
            - LOW: saldo nunca fica negativo

        Args:
            negative_day (int | None): Dia da primeira quebra de saldo.
            worst_balance (float): Menor saldo observado.

        Returns:
            str: LOW | MEDIUM | HIGH
        """

        if negative_day is None:
            return "LOW"

        if negative_day <= 7:
            return "HIGH"

        return "MEDIUM"
