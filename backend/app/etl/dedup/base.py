from abc import ABC, abstractmethod
import polars as pl


class DedupPolicy(ABC):
    """
    Contrato para políticas de deduplicação.
    """

    @abstractmethod
    def apply(self, df: pl.DataFrame) -> tuple[pl.DataFrame, int]:
        """
        Retorna:
        - DataFrame deduplicado
        - quantidade de duplicatas removidas
        """
        ...
