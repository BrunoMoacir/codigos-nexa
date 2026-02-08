#app/cashflow/engine.py
"""
Cashflow Engine

Orquestra:
- projeção de fluxo (30 dias)
- safe-to-spend
- risco financeiro
"""

from app.cashflow.projector import CashflowProjector
from app.cashflow.safe_to_spend import SafeToSpendCalculator


class CashflowEngine:
    """
    Orquestrador de análise completa de cashflow.
    
    Integra:
        - CashflowProjector: Projeção de saldo futuro (30 dias)
        - SafeToSpendCalculator: Margem segura para gastos
    
    Example:
        >>> engine = CashflowEngine()
        >>> result = engine.analyze(transactions_df, shadow_df)
        >>> print(result["safe_to_spend"]["safe_to_spend_daily"])
    """

    def __init__(self):
        self.projector = CashflowProjector(horizon_days=30)
        self.safe_to_spend = SafeToSpendCalculator(safety_buffer_pct=0.15)

    def analyze(self, transactions_df, shadow_invoices_df):
        """
        Executa análise completa de cashflow.
        
        Args:
            transactions_df: DataFrame com transações
                Colunas obrigatórias: transaction_date, amount, balance
            
            shadow_invoices_df: DataFrame com shadow invoices
                Colunas obrigatórias: amount, next_due_date
        
        Returns:
            Dict com:
                - projection: Resumo da projeção + dados dia a dia
                - safe_to_spend: Cálculo de margem segura
                - risk_assessment: Avaliação de risco
        
        Example:
            >>> result = engine.analyze(df, shadow_df)
            >>> print(result["safe_to_spend"]["safe_to_spend_daily"])
            2007.35
        """

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 1️⃣ PROJEÇÃO DE SALDO FUTURO (30 dias)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        projection_df = self.projector.project(
            transactions_df=transactions_df,
            shadow_invoices_df=shadow_invoices_df
        )
        
        # Calcular saldo inicial para o resumo
        starting_balance = float(
            transactions_df.sort("transaction_date").tail(1)["balance"][0]
        )
        
        # Gerar resumo da projeção
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
        # 3️⃣ RETORNAR RESULTADO AGREGADO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        return {
            "projection": {
                "summary": projection_summary.to_dict(),
                "data": projection_df.to_dicts()  # Dados dia a dia
            },
            "safe_to_spend": sts_result.to_dict(),
            "risk_assessment": {
                "overall_risk": projection_summary.risk_level,
                "negative_day": projection_summary.negative_day,
                "worst_balance": projection_summary.worst_balance,
                "total_shadow_impact": projection_summary.total_shadow_impact
            }
        }