#app/cashflow/engine.py
"""
Cashflow Engine

Orquestra:
- projeção de fluxo (30 dias)
- safe-to-spend
- risco financeiro
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Optional

from app.forecast.cashflow.projector import CashflowProjector
from app.forecast.cashflow.safe_to_spend import SafeToSpendCalculator
from app.forecast.cashflow.burn_rate import BurnRateAnalyzer
from app.budget.budget_advisor import BudgetAdvisor

if TYPE_CHECKING:
    from app.forecast.etl.income_profiler import IncomeProfile

_INCOME_CONFIDENCE_THRESHOLD = 0.5


class CashflowEngine:
    """
    Orquestrador de análise completa de cashflow.

    Integra:
        - CashflowProjector: Projeção de saldo futuro (30 dias)
        - SafeToSpendCalculator: Margem segura para gastos
        - BurnRateAnalyzer: Velocidade de gasto do mês corrente

    Example:
        >>> engine = CashflowEngine()
        >>> result = engine.analyze(transactions_df, shadow_df)
        >>> print(result["safe_to_spend"]["safe_to_spend_daily"])
    """

    def __init__(self):
        self.projector = CashflowProjector(horizon_days=30)
        self.safe_to_spend = SafeToSpendCalculator(safety_buffer_pct=0.15)
        self.burn_rate = BurnRateAnalyzer()
        self.budget_advisor = BudgetAdvisor()  # M1.3

    def analyze(
        self,
        transactions_df,
        shadow_invoices_df,
        reference_date: date | None = None,
        include_daily_data: bool = True,
        monthly_income: float | None = None,
        income_profile: Optional["IncomeProfile"] = None,
    ):
        """
        Executa análise completa de cashflow.

        Args:
            transactions_df: DataFrame com transações.
                Colunas obrigatórias: transaction_date, amount, balance.
                Deve conter ao menos uma linha — use guard no chamador se necessário.
            shadow_invoices_df: DataFrame com shadow invoices.
                Colunas obrigatórias: amount, next_due_date.
            reference_date: Data de referência para burn rate e projeções.
                Padrão: date.today(). Passar explicitamente em backtesting ou
                simulações históricas para manter todos os calculadores alinhados.
            include_daily_data: Se True (padrão), inclui projection["data"] com os
                dados dia a dia. Passe False para respostas compactas quando o
                consumidor só precisa do resumo (evita payload grande em horizon alto).

        Returns:
            Dict com:
                - projection: Resumo da projeção + dados dia a dia (se include_daily_data)
                - safe_to_spend: Cálculo de margem segura
                - risk_assessment: Avaliação de risco (campos críticos expostos no topo)
                - burn_rate: Velocidade de gasto do mês corrente

        Raises:
            ValueError: Se transactions_df estiver vazio (sem saldo inicial disponível).

        Example:
            >>> result = engine.analyze(df, shadow_df)
            >>> print(result["safe_to_spend"]["safe_to_spend_daily"])
            2007.35
        """

        # MI.5: fallback — extrai monthly_income do income_profile quando não declarado
        if monthly_income is None and income_profile is not None:
            if income_profile.confidence >= _INCOME_CONFIDENCE_THRESHOLD:
                monthly_income = income_profile.monthly_net_income

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # GUARD: DataFrame vazio — .tail(1)["balance"][0] lançaria IndexError
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        if transactions_df.is_empty():
            raise ValueError(
                "transactions_df está vazio — não é possível calcular saldo inicial."
            )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 1️⃣ PROJEÇÃO DE SALDO FUTURO (30 dias)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # reference_date propagado: sem ele a projeção ancorava na última
        # transação e o burn rate em hoje — dois calculadores olhando para
        # datas diferentes no mesmo relatório.
        # Saldo resolvido ANTES e repassado: projector e resumo precisam
        # partir do mesmo número, senão a projeção diz uma coisa e o
        # cabeçalho do relatório outra.
        starting_balance = self._starting_balance(transactions_df)

        projection_df = self.projector.project(
            transactions_df=transactions_df,
            shadow_invoices_df=shadow_invoices_df,
            current_balance=starting_balance,
            reference_date=reference_date,
        )

        projection_summary = self.projector.get_summary(
            projection_df=projection_df,
            starting_balance=starting_balance
        )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 2️⃣ CÁLCULO SAFE-TO-SPEND
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        sts_result = self.safe_to_spend.calculate(
            projection_df=projection_df,
            horizon_days=30
        )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 3️⃣ BURN RATE — velocidade de gasto do mês corrente
        # reference_date propagado para manter alinhamento com projeção
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        burn_rate_result = self.burn_rate.analyze(
            transactions_df=transactions_df,
            current_date=reference_date,     # None → date.today() dentro do analyzer
            monthly_income=monthly_income,   # None → income_ratio omitido do relatório
        )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 4️⃣ RETORNAR RESULTADO AGREGADO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # projection["data"] pode ser grande em horizon alto — omitível via flag
        projection_daily = projection_df.to_dicts() if include_daily_data else []

        result = {
            "projection": {
                "summary": projection_summary.to_dict(),
                "data": projection_daily,
            },
            "safe_to_spend": sts_result.to_dict(),
            "risk_assessment": {
                "overall_risk": projection_summary.risk_level,
                "negative_day": projection_summary.negative_day,
                "worst_balance": projection_summary.worst_balance,
                "total_shadow_impact": projection_summary.total_shadow_impact
            },
            "burn_rate": burn_rate_result.to_dict()
        }

        # M1.3 — Orçamento inteligente: incluído quando renda mensal está disponível
        if monthly_income and monthly_income > 0:
            try:
                budget_result = self.budget_advisor.suggest(
                    transactions_df=transactions_df,
                    monthly_income=monthly_income,
                )
                result["budget_advice"] = budget_result.to_dict()
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "BudgetAdvisor falhou — omitindo 'budget_advice': %s", exc
                )

        return result

    @staticmethod
    def _starting_balance(transactions_df) -> float:
        """
        Saldo da última transação, tolerante a lacuna.

        `float(tail(1)["balance"][0])` estourava TypeError quando a última
        linha vinha sem saldo — o que acontece em conta de cartão, onde a
        Pluggy não manda balance. Procura para trás o último saldo conhecido
        antes de desistir.
        """
        if "balance" not in transactions_df.columns:
            raise ValueError(
                "transactions_df não possui coluna 'balance' — impossível ancorar a projeção."
            )

        saldos = transactions_df.sort("transaction_date")["balance"].to_list()
        for saldo in reversed(saldos):
            if saldo is not None:
                return float(saldo)

        raise ValueError(
            "Nenhuma transação com saldo conhecido — informe current_balance "
            "ou sincronize uma conta que exponha saldo."
        )
