# app/etl/cashflow/models.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class CashflowProjectionPoint:
    date: datetime
    projected_balance: float
    risk_flag: Optional[str] = None  # e.g. "NEGATIVE_BALANCE"
