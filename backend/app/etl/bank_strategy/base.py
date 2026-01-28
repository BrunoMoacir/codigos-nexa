# app/etl/bank_strategy/base.py

from abc import ABC, abstractmethod
from typing import Any
import polars as pl

from app.schemas.enums import BankTier, DataStatus


class BankStrategy(ABC):
    """
    Contrato base para estratégias por banco.

    Cada banco (Nubank, Itaú, Inter, etc.) deve:
    - Declarar seu tier de confiabilidade
    - Aplicar normalizações específicas
    - Avaliar a qualidade dos dados recebidos
    """

    bank_id: str
    tier: BankTier

    def __init__(self, bank_id: str):
        self.bank_id = bank_id

    @abstractmethod
    def normalize(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Normalizações específicas do banco.
        Ex:
        - Ajustar description
        - Corrigir sinais de amount
        - Padronizar status
        """
        pass

    @abstractmethod
    def evaluate_quality(self, df: pl.DataFrame) -> DataStatus:
        """
        Avalia a confiabilidade geral dos dados do banco.
        Retorna TRUSTED | DEGRADED | UNTRUSTED
        """
        pass
