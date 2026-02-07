#app/agent/shadow_invoice/detector.py
"""
Shadow Invoice Detector

Responsável por detectar despesas recorrentes que ainda não chegaram,
mas que devem impactar o saldo futuro do usuário.

Exemplo:
- Aluguel
- Financiamento
- Assinaturas
- Academia
"""

from typing import List, Dict


class ShadowInvoiceDetector:
    """
    Detecta cobranças futuras prováveis com base no histórico.
    """

    def __init__(self, confidence_threshold: float = 0.75):
        """
        Args:
            confidence_threshold: nível mínimo de confiança para assumir
                                  que uma cobrança é recorrente.
        """
        self.confidence_threshold = confidence_threshold

    def detect(self, recurring_expenses: List[Dict]) -> List[Dict]:
        """
        Filtra despesas recorrentes que ainda não ocorreram no ciclo atual.

        Args:
            recurring_expenses: lista produzida pelo RecurringDetector

        Returns:
            Lista de despesas futuras prováveis (shadow invoices)
        """
        shadow_invoices = []

        for expense in recurring_expenses:
            if expense.get("confidence", 0) >= self.confidence_threshold:
                shadow_invoices.append({
                    "name": expense["description"],
                    "amount": expense["amount"],
                    "due_day": expense.get("due_day"),
                    "confidence": expense["confidence"],
                })

        return shadow_invoices
