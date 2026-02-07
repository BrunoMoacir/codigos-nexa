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

import sys
from pathlib import Path

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURAR PYTHON PATH
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Adiciona o diretório 'backend' ao PYTHONPATH

current_file = Path(__file__).resolve()
# nexa_financial_agent.py está em: backend/app/agent/
# Precisamos subir 3 níveis: agent → app → backend
backend_dir = current_file.parent.parent.parent

if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
    print(f"✅ Python path configurado: {backend_dir}\n")

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

        # Converter para DataFrame Polars
        df = pl.DataFrame(transactions)
        
        # ✅ IMPORTANTE: CashflowProjector espera 'transaction_date', mas análise usa 'date'
        # Renomear coluna se necessário
        if "date" in df.columns and "transaction_date" not in df.columns:
            df = df.rename({"date": "transaction_date"})
        
        # Converter shadow invoices para DataFrame Polars
        shadow_df = pl.DataFrame(shadow_invoices) if shadow_invoices else pl.DataFrame()

        projection_df = self.cashflow_projector.project(
            transactions_df=df,
            shadow_invoices_df=shadow_df
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BLOCO DE TESTE (somente quando executado diretamente)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    from datetime import datetime
    
    print("🧪 Testando FinancialAgent...")
    
    # Transações de teste
    # IMPORTANTE: Usar 'date' (não 'transaction_date') porque o código interno usa 'date'
    test_transactions = [
        {
            "transaction_id": "1",
            "amount": 5000.0,
            "date": datetime(2025, 1, 1),  # ✅ datetime object
            "description": "SALARIO",
            "type": "CREDIT",
            "balance": 5000.0
        },
        {
            "transaction_id": "2",
            "amount": -1500.0,
            "date": datetime(2025, 1, 5),  # ✅ datetime object
            "description": "ALUGUEL",
            "type": "DEBIT",
            "balance": 3500.0
        },
        {
            "transaction_id": "3",
            "amount": -49.90,
            "date": datetime(2025, 1, 10),  # ✅ datetime object
            "description": "NETFLIX",
            "type": "DEBIT",
            "balance": 3450.10
        }
    ]
    
    agent = FinancialAgent()
    result = agent.run(test_transactions)
    
    print("\n✅ Resultado:")
    print(f"   • Profile: {result['profile']}")
    print(f"   • Recurring: {len(result['recurring'])} detectadas")
    print(f"   • Shadow Invoices: {len(result['shadow_invoices'])}")
    print(f"   • Safe-to-spend: {result['safe_to_spend']}")