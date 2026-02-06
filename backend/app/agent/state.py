"backend/app/agent/state.py"
from typing import TypedDict
import polars as pl

class FinancialState(TypedDict):
    transactions: pl.DataFrame
    recurring: pl.DataFrame
    forecast: pl.DataFrame
    safe_to_spend: dict
    explanation: str
