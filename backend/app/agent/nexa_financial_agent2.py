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
        
        # ✅ CONVERTER SHADOW INVOICES para formato esperado pelo CashflowProjector
        # ShadowInvoiceDetector retorna: ["description", "avg_amount", "months", "occurrences"]
        # CashflowProjector espera: ["description", "amount", "next_due_date", ...]
        
        if shadow_invoices and len(shadow_invoices) > 0:
            from datetime import datetime, timedelta
            
            # Calcular next_due_date (assumir próximo mês após última transação)
            if "transaction_date" in df.columns:
                last_date = df["transaction_date"].max()
            else:
                last_date = datetime.now()
            
            # Adicionar 30 dias para próxima cobrança
            next_due = last_date + timedelta(days=30)
            
            # Converter para DataFrame e adicionar campos necessários
            shadow_df = pl.DataFrame(shadow_invoices)
            
            # Renomear avg_amount → amount
            if "avg_amount" in shadow_df.columns and "amount" not in shadow_df.columns:
                shadow_df = shadow_df.rename({"avg_amount": "amount"})
            
            # Adicionar next_due_date se não existir
            if "next_due_date" not in shadow_df.columns:
                shadow_df = shadow_df.with_columns(
                    pl.lit(next_due).alias("next_due_date")
                )
        else:
            shadow_df = pl.DataFrame()

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
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TESTE 1: Dados mínimos (não detecta recorrência - esperado)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    test_minimal = [
        {
            "transaction_id": "1",
            "amount": 5000.0,
            "date": datetime(2025, 1, 1),
            "description": "SALARIO",
            "type": "CREDIT",
            "balance": 5000.0
        },
        {
            "transaction_id": "2",
            "amount": -1500.0,
            "date": datetime(2025, 1, 5),
            "description": "ALUGUEL",
            "type": "DEBIT",
            "balance": 3500.0
        },
        {
            "transaction_id": "3",
            "amount": -49.90,
            "date": datetime(2025, 1, 10),
            "description": "NETFLIX",
            "type": "DEBIT",
            "balance": 3450.10
        }
    ]
    
    print("\n" + "="*80)
    print("🧪 TESTE 1: Dados Mínimos (3 transações, 1 mês)")
    print("="*80)
    
    agent = FinancialAgent()
    result = agent.run(test_minimal)
    
    print("\n✅ Resultado:")
    print(f"   • Profile: {result['profile']}")
    print(f"   • Recurring: {len(result['recurring'])} detectadas ← CORRETO (precisa ≥2 ocorrências)")
    print(f"   • Shadow Invoices: {len(result['shadow_invoices'])} ← CORRETO (sem padrão detectado)")
    print(f"   • Safe-to-spend: R$ {result['safe_to_spend']['safe_to_spend_daily']:.2f}/dia")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TESTE 2: Dados com recorrência real (DEVE detectar)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    test_recurring = [
        # Janeiro
        {"transaction_id": "1", "amount": 5000.0, "date": datetime(2025, 1, 1), "description": "SALARIO", "type": "CREDIT", "balance": 5000.0},
        {"transaction_id": "2", "amount": -1500.0, "date": datetime(2025, 1, 5), "description": "ALUGUEL", "type": "DEBIT", "balance": 3500.0},
        {"transaction_id": "3", "amount": -49.90, "date": datetime(2025, 1, 10), "description": "NETFLIX", "type": "DEBIT", "balance": 3450.10},
        {"transaction_id": "4", "amount": -21.90, "date": datetime(2025, 1, 15), "description": "SPOTIFY", "type": "DEBIT", "balance": 3428.20},
        
        # Fevereiro (mesmas assinaturas)
        {"transaction_id": "5", "amount": 5000.0, "date": datetime(2025, 2, 1), "description": "SALARIO", "type": "CREDIT", "balance": 8428.20},
        {"transaction_id": "6", "amount": -1500.0, "date": datetime(2025, 2, 5), "description": "ALUGUEL", "type": "DEBIT", "balance": 6928.20},
        {"transaction_id": "7", "amount": -49.90, "date": datetime(2025, 2, 10), "description": "NETFLIX", "type": "DEBIT", "balance": 6878.30},
        {"transaction_id": "8", "amount": -21.90, "date": datetime(2025, 2, 15), "description": "SPOTIFY", "type": "DEBIT", "balance": 6856.40},
        
        # Março (mesmas assinaturas)
        {"transaction_id": "9", "amount": 5000.0, "date": datetime(2025, 3, 1), "description": "SALARIO", "type": "CREDIT", "balance": 11856.40},
        {"transaction_id": "10", "amount": -1500.0, "date": datetime(2025, 3, 5), "description": "ALUGUEL", "type": "DEBIT", "balance": 10356.40},
        {"transaction_id": "11", "amount": -49.90, "date": datetime(2025, 3, 10), "description": "NETFLIX", "type": "DEBIT", "balance": 10306.50},
        {"transaction_id": "12", "amount": -21.90, "date": datetime(2025, 3, 15), "description": "SPOTIFY", "type": "DEBIT", "balance": 10284.60},
    ]
    
    print("\n" + "="*80)
    print("🧪 TESTE 2: Dados com Recorrência Real (12 transações, 3 meses)")
    print("="*80)
    
    agent2 = FinancialAgent()
    result2 = agent2.run(test_recurring)
    
    print("\n✅ Resultado:")
    print(f"   • Profile: {result2['profile']}")
    print(f"   • Recurring: {len(result2['recurring'])} detectadas ← DEVE SER ≥2 (Netflix + Spotify)")
    print(f"   • Shadow Invoices: {len(result2['shadow_invoices'])} ← DEVE SER ≥2")
    print(f"   • Safe-to-spend: R$ {result2['safe_to_spend']['safe_to_spend_daily']:.2f}/dia")
    
    if len(result2['recurring']) >= 2:
        print("\n🎉 SUCESSO! Recorrências detectadas:")
        for rec in result2['recurring']:
            print(f"   • {rec}")
    else:
        print("\n⚠️  ATENÇÃO: Esperava detectar Netflix e Spotify como recorrentes")
    
    print("\n" + "="*80)