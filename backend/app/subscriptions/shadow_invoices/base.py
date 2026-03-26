# app/etl/shadow_invoices/base.py

import polars as pl
from abc import ABC, abstractmethod


class ShadowInvoiceDetector(ABC):
    """
    Classe base para qualquer detector de obrigações futuras.
    """

    @abstractmethod
    def detect(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Recebe DataFrame de transações normalizadas
        Retorna DataFrame de shadow invoices
        """
        pass
