"""
Nexa Financial Agent - Cérebro financeiro da Nexa

Orquestra todos os motores financeiros:
    - Recorrência
    - Shadow invoices
    - Perfil financeiro
    - Projeção de fluxo de caixa
    - Safe-to-spend

Objetivo:
    Gerar diagnóstico financeiro completo e acionável.
"""

from typing import Dict, List
import polars as pl

from app.analysis.recurring_detector import RecurringDetector
from app.analysis.shadow_invoice_detector import ShadowInvoiceDetector
from app.analysis.user_profile_analyzer import UserProfileAnalyzer

from app.cashflow.projector import CashflowProjector
from app.cashflow.safe_to_spend import SafeToSpendCalculator


class FinancialAgent:
    """
    Agente financeiro principal da Nexa.
    """

    def __init__(self):
        self.recurring_detector = RecurringDetector()
        self.shadow_invoice_detector = ShadowInvoiceDetector()
        self.user_profile_analyzer = UserProfileAnalyzer()

        self.cashflow_projector = CashflowProjector()
        self.safe_to_spend_calculator = SafeToSpendCalculator()

    def run(self, transactions: List[Dict]) -> Dict:
        """
        Executa pipeline financeiro completo.

        Args:
            transactions: Lista de transações normalizadas.

        Returns:
            Diagnóstico financeiro completo.
        """

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 1 — Perfil Financeiro
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        profile = self.user_profile_analyzer.analyze(transactions)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 2 — Recorrências
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        recurring = self.recurring_detector.run(transactions)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 3 — Shadow Invoices
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        shadow_invoices = self.shadow_invoice_detector.run(transactions)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 4 — Projeção de Cashflow
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        df = pl.DataFrame(transactions)

        projection_df = self.cashflow_projector.project(
            transactions_df=df
        )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 5 — Safe To Spend
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        safe_to_spend = self.safe_to_spend_calculator.calculate(
            projection_df=projection_df,
            horizon_days=30
        )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # RESULTADO FINAL
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        return {
            "profile": profile,
            "recurring": recurring,
            "shadow_invoices": shadow_invoices,
            "cashflow_projection": projection_df.to_dicts(),
            "safe_to_spend": safe_to_spend.to_dict()
        }
