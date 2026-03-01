#app/cashflow/engine.py
"""
Cashflow Engine

Orquestra:
- projeção de fluxo (30 dias)
- safe-to-spend
- risco financeiro
"""

from datetime import date

from app.cashflow.projector import CashflowProjector
from app.cashflow.safe_to_spend import SafeToSpendCalculator
from app.cashflow.burn_rate import BurnRateAnalyzer


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

    def analyze(
        self,
        transactions_df,
        shadow_invoices_df,
        reference_date: date | None = None,
        include_daily_data: bool = True,
        monthly_income: float | None = None,
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

        projection_df = self.projector.project(
            transactions_df=transactions_df,
            shadow_invoices_df=shadow_invoices_df
        )

        starting_balance = float(
            transactions_df.sort("transaction_date").tail(1)["balance"][0]
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

        return {
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