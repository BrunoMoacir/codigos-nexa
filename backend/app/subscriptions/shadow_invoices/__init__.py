# app/etl/shadow_invoices/__init__.py
"""
Shadow Invoices - Detecção de Obrigações Futuras

RESPONSABILIDADE:
    Detecta assinaturas e parcelamentos que gerarão despesas futuras.

COMPONENTES:
    - SubscriptionDetector: Detecta assinaturas recorrentes (Netflix, Spotify, etc)
    - InstallmentDetector: Detecta parcelamentos (01/12, 02/12, etc)
    - runner: Orquestra os detectores

USAGE:
    from app.subscriptions.shadow_invoices import run_shadow_invoice_detection
    
    shadow_df = run_shadow_invoice_detection(transactions_df)
"""

# Importar função principal do runner
from .runner import run_shadow_invoice_detection

# Exportar apenas a função principal
__all__ = ["run_shadow_invoice_detection"]