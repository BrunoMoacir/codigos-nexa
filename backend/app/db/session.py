import duckdb
import polars as pl


def get_duckdb_df(user_id: str) -> pl.DataFrame:
    con = duckdb.connect("finance.duckdb", read_only=True)

    try:
        df = con.execute("""
            SELECT *
            FROM transactions
            WHERE user_id = ?
        """, [user_id]).pl()

        return df

    finally:
        con.close()
