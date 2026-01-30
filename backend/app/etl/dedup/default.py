import polars as pl
from app.etl.dedup.base import DedupPolicy


class DefaultDedupPolicy(DedupPolicy):
    """
    Deduplicação semântica padrão:
    Usa dedup_hash previamente calculado.
    """

    def apply(self, df: pl.DataFrame) -> tuple[pl.DataFrame, int]:
        before = df.height
        df = df.unique(subset=["dedup_hash"], keep="first")
        removed = before - df.height
        return df, removed
