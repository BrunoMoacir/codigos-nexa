"""
app/agent/financial_agent.py

Motor central de inteligência financeira da Nexa.

Responsabilidades:
- Executar o pipeline financeiro completo do usuário:
    ETL → Recorrência → Shadow Invoices → Perfil → Cashflow → Safe-to-Spend

- Produzir uma resposta unificada, pronta para consumo pela API / dashboard.

Este módulo representa o "cérebro" da plataforma.
"""

from typing import Dict, Any

from app.analysis.recurring_detector import RecurringDetector
from app.analysis.shadow_invoice_detector import ShadowInvoiceDetector
from app.analysis.user_profile_analyzer import UserProfileAnalyzer

from app.cashflow.projector import CashflowProjector
from app.cashflow.safe_to_spend import SafeToSpendEngine

from app.etl.runner import run_full_etl_pipeline



class FinancialAgent:
    """
    Orquestrador financeiro principal.

    Este agente executa TODA a inteligência financeira:
        - Carrega dados bancários
        - Processa ETL
        - Detecta recorrência
        - Detecta shadow invoices
        - Analisa perfil financeiro
        - Projeta fluxo de caixa futuro
        - Calcula Safe-to-Spend

    Ele transforma dados bancários brutos em inteligência financeira acionável.
    """

    def __init__(self):
        # Inicializa os motores de análise
        self.recurring_detector = RecurringDetector()
        self.shadow_invoice_detector = ShadowInvoiceDetector()
        self.user_profile_analyzer = UserProfileAnalyzer()
        self.cashflow_projector = CashflowProjector()
        self.safe_to_spend_engine = SafeToSpendEngine()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # MÉTODO PRINCIPAL — EXECUTA O PIPELINE COMPLETO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def run(self, user_id: str) -> Dict[str, Any]:
        """
        Executa o pipeline financeiro completo para um usuário.

        Args:
            user_id (str): Identificador único do usuário.

        Returns:
            Dict com:
                - perfil financeiro
                - projeção de saldo
                - shadow invoices
                - safe_to_spend
                - risco financeiro
        """

        # ==========================================================
        # STEP 1 — Executar ETL completo
        # ==========================================================
        etl_result = run_full_etl_pipeline(user_id=user_id)

        transactions = etl_result["transactions"]
        balances = etl_result.get("balances", {})

        # ==========================================================
        # STEP 2 — Detectar recorrências
        # ==========================================================
        recurring_result = self.recurring_detector.detect(transactions)

        # ==========================================================
        # STEP 3 — Detectar shadow invoices (obrigações futuras)
        # ==========================================================
        shadow_invoices = self.shadow_invoice_detector.detect(
            recurring_transactions=recurring_result["recurring"],
            installment_transactions=recurring_result["installments"]
        )

        # ==========================================================
        # STEP 4 — Analisar perfil financeiro do usuário
        # ==========================================================
        user_profile = self.user_profile_analyzer.analyze(transactions)

        # ==========================================================
        # STEP 5 — Projetar fluxo de caixa futuro
        # ==========================================================
        forecast = self.cashflow_projector.project(
            current_balance=balances.get("current_balance", 0.0),
            recurring_expenses=shadow_invoices["monthly_commitment"],
            horizon_days=30
        )

        # =========================================
