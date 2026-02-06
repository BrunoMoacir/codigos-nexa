"""
app/etl/shadow_invoices/runner.py - Orquestrador de Detecção

CORREÇÃO:
    ✅ SUBSCRIPTION roda ANTES (prioridade)
    ✅ INSTALLMENT roda DEPOIS (só se não for subscription)
"""

import polars as pl
from app.etl.shadow_invoices.subscription_detector import SubscriptionDetector
from app.etl.shadow_invoices.installment_detector import InstallmentDetector


def run_shadow_invoice_detection(df: pl.DataFrame) -> pl.DataFrame:
    """
    Detecta shadow invoices (obrigações futuras) em transações.
    
    Ordem de execução (PRIORIDADE):
        1. SubscriptionDetector (detecta assinaturas primeiro)
        2. InstallmentDetector (detecta parcelamentos que sobraram)
    
    Args:
        df: DataFrame com transações normalizadas
    
    Returns:
        DataFrame com shadow invoices detectadas
    
    Example:
        >>> result = run_shadow_invoice_detection(df)
        >>> print(result)
        ┌─────────────┬────────┬───────────────┬──────────┬────────────┐
        │ type        ┆ amount ┆ next_due_date ┆ metadata ┆ confidence │
        ├─────────────┼────────┼───────────────┼──────────┼────────────┤
        │ SUBSCRIPTION┆ -39.9  ┆ 2026-01-01    ┆ ...      ┆ 0.9        │
        │ INSTALLMENT ┆ -120.0 ┆ 2026-01-01    ┆ ...      ┆ 0.9        │
        └─────────────┴────────┴───────────────┴──────────┴────────────┘
    """
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ORDEM IMPORTA! SUBSCRIPTION TEM PRIORIDADE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    detectors = [
        SubscriptionDetector(),   # ✅ 1º: Detecta assinaturas
        InstallmentDetector(),    # ✅ 2º: Detecta parcelamentos
    ]
    
    results = []
    detected_descriptions = set()  # Evitar duplicatas
    
    for detector in detectors:
        # Filtrar transações já detectadas
        if detected_descriptions:
            df_filtered = df.filter(
                ~pl.col("description").is_in(list(detected_descriptions))
            )
        else:
            df_filtered = df
        
        # Detectar
        detected = detector.detect(df_filtered)
        
        if not detected.is_empty():
            results.append(detected)
            
            # Registrar descrições detectadas
            # (para não detectar novamente no próximo detector)
            descriptions = detected.select("metadata").to_series()
            for metadata in descriptions:
                detected_descriptions.add(metadata["description"])
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CONCATENAR RESULTADOS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if not results:
        return pl.DataFrame()
    
    return pl.concat(results, how="diagonal_relaxed")