#app/etl/bank_strategy/dedup/default.py
import polars as pl
from app.forecast.etl.dedup.base import DedupPolicy


class DefaultDedupPolicy(DedupPolicy):
    """
    Deduplicação semântica padrão:
    Usa dedup_hash previamente calculado.
    """

    def apply(self, df: pl.DataFrame) -> tuple[pl.DataFrame, int]:
        if "dedup_hash" not in df.columns:
            return df, 0

        before = df.height
        # maintain_order=True: sem isso o Polars pode reordenar as linhas e
        # tornar a saída do ETL não-determinística entre execuções.
        df = df.unique(subset=["dedup_hash"], keep="first", maintain_order=True)
        removed = before - df.height
        return df, removed
