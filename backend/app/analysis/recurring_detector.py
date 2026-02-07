"""
RecurringDetector

Wrapper simples em cima do motor real de recorrência:
app.core.recurrence.detect_recurring
"""

import polars as pl
from app.core.recurrence import detect_recurring


class RecurringDetector:
    """
    Detector de transações recorrentes (assinaturas e parcelamentos).

    Essa classe apenas encapsula o motor principal de recorrência
    já existente no core.
    """

    def run(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Detecta recorrência nas transações.

        Args:
            df: DataFrame com transações normalizadas

        Returns:
            DataFrame com colunas:
              - is_recurring
              - is_installment
              - confidence
        """
        return detect_recurring(df)
