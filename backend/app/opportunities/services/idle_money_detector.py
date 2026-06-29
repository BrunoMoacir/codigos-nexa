"""
app/opportunities/services/idle_money_detector.py

Calcula dinheiro parado: avg_income_3m − avg_expenses_3m.
Usa histórico de transações do DuckDB.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

logger = logging.getLogger(__name__)


@dataclass
class IdleMoneyResult:
    idle_amount: float
    avg_income_3m: float
    avg_expenses_3m: float
    months_analyzed: int
    has_sufficient_data: bool   # False quando < 2 meses de histórico


class IdleMoneyDetector:
    """
    Detecta saldo ocioso estimado com base em renda e despesas médias.

    idle_amount = avg_income_3m − avg_expenses_3m

    O resultado representa o quanto o usuário tipicamente deixa parado
    no final de cada mês sem investir.
    """

    _MIN_MONTHS = 2

    def detect(self, user_id: str) -> IdleMoneyResult:
        """Calcula idle money para um usuário a partir de suas transações."""
        try:
            from app.core.db.queries import get_transactions_for_user
            df = get_transactions_for_user(user_id)
        except Exception as exc:
            logger.error("[IdleMoneyDetector] get_transactions user=%s: %s", user_id, exc)
            return IdleMoneyResult(
                idle_amount=0.0,
                avg_income_3m=0.0,
                avg_expenses_3m=0.0,
                months_analyzed=0,
                has_sufficient_data=False,
            )

        if df.is_empty():
            return IdleMoneyResult(
                idle_amount=0.0,
                avg_income_3m=0.0,
                avg_expenses_3m=0.0,
                months_analyzed=0,
                has_sufficient_data=False,
            )

        return self._calculate(df)

    def _calculate(self, df) -> IdleMoneyResult:
        try:
            import polars as pl

            date_col = "transaction_date" if "transaction_date" in df.columns else "date"
            today = date.today()

            # Janela: 3 meses completos anteriores ao mês atual
            cutoff = today.replace(day=1)
            for _ in range(3):
                cutoff = (cutoff - timedelta(days=1)).replace(day=1)

            df_recent = df.filter(pl.col(date_col) >= cutoff)
            if df_recent.is_empty():
                df_recent = df

            income_df = df_recent.filter(pl.col("amount") > 0)
            expenses_df = df_recent.filter(pl.col("amount") < 0)

            total_income = float(income_df["amount"].sum()) if income_df.height > 0 else 0.0
            total_expenses = abs(float(expenses_df["amount"].sum())) if expenses_df.height > 0 else 0.0

            months = max(1, (today.year - cutoff.year) * 12 + today.month - cutoff.month)
            avg_income = round(total_income / months, 2)
            avg_expenses = round(total_expenses / months, 2)
            idle = max(0.0, round(avg_income - avg_expenses, 2))

            return IdleMoneyResult(
                idle_amount=idle,
                avg_income_3m=avg_income,
                avg_expenses_3m=avg_expenses,
                months_analyzed=months,
                has_sufficient_data=months >= self._MIN_MONTHS,
            )
        except Exception as exc:
            logger.error("[IdleMoneyDetector] _calculate: %s", exc)
            return IdleMoneyResult(
                idle_amount=0.0,
                avg_income_3m=0.0,
                avg_expenses_3m=0.0,
                months_analyzed=0,
                has_sufficient_data=False,
            )
