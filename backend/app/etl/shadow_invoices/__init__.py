"""
Shadow Invoices module

Exposição controlada da API pública:
- Runner
- Detectores internos ficam encapsulados
"""

from .runner import run_shadow_invoice_detection

__all__ = [
    "run_shadow_invoice_detection",
]
