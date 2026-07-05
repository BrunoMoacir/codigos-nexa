"""
app/opportunities/services/idle_money_detector.py

Calcula dinheiro parado, protegido por reserva de emergência quando um
UserProfile é informado (Ticket OPP1-B — docs/OPP1_DINHEIRO_PARADO_PLANO.md).

Fonte do saldo (Opção B do plano, entregue em 2026-07-05):
  1. REAL_BALANCE   — saldo real de conta corrente (account_balances,
                      persistido no sync do Pluggy; frescor de 7 dias).
  2. CASHFLOW_PROXY — fallback: soma cumulativa das transações conhecidas
                      (comportamento original), quando não há saldo fresco.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import polars as pl
    from app.optimizer.profiler import UserProfile

IdleSource = Literal["REAL_BALANCE", "CASHFLOW_PROXY"]

logger = logging.getLogger(__name__)

# Meses de despesa protegidos como reserva de emergência, por fss_level do
# ConsumptionProfiler. Maior para perfis mais frágeis: aqui é uma margem de
# segurança a NUNCA sugerir investir, não uma meta de poupança (não confundir
# com app/goals/profile_advisor.py::_EMERGENCY_MONTHS_BY_FSS, que responde a
# uma pergunta diferente — ver plano, seção 3). Valores não validados com
# produto/jurídico — ver plano, seção 8 (Riscos).
_RESERVE_MONTHS_BY_FSS: dict[str, int] = {
    "SAUDAVEL": 6,
    "ATENCAO": 6,
    "ALERTA": 9,
    "CRITICO": 9,
}
_DEFAULT_RESERVE_MONTHS = 6  # fss_level desconhecido/ausente → tratar como saudável


@dataclass
class IdleMoneyResult:
    # Valor final, já líquido de reserva — usado pelo ranking de produtos.
    idle_amount: float

    # Saldo bruto, sem proteção de reserva. Com idle_source=REAL_BALANCE é o
    # saldo real de conta corrente (account_balances); com CASHFLOW_PROXY é a
    # soma cumulativa das transações conhecidas (mesma heurística de
    # app/forecast/router.py::fetch_user_transactions — "current_balance").
    gross_idle_amount: float = 0.0

    # Reserva protegida que NÃO deve virar oportunidade de investimento.
    emergency_reserve: float = 0.0
    reserve_months_applied: int = 0   # 0 quando nenhum UserProfile foi informado

    avg_income_3m: float = 0.0
    avg_expenses_3m: float = 0.0
    months_analyzed: int = 0
    has_sufficient_data: bool = False   # False quando < 2 meses de histórico

    # Origem do saldo bruto (Opção B do plano OPP.1)
    idle_source: IdleSource = "CASHFLOW_PROXY"
    balance_captured_at: Optional[datetime] = None   # só com REAL_BALANCE


class IdleMoneyDetector:
    """
    Detecta saldo ocioso estimado, protegido por reserva de emergência.

    gross_idle_amount = soma cumulativa das transações do usuário (proxy de saldo)
    emergency_reserve  = reserve_months_applied × avg_expenses_3m (só com UserProfile)
    idle_amount        = max(0, gross_idle_amount − emergency_reserve)
    """

    _MIN_MONTHS = 2

    def detect(
        self,
        user_id: str,
        transactions_df: "pl.DataFrame | None" = None,
        user_profile: "UserProfile | None" = None,
    ) -> IdleMoneyResult:
        """
        Calcula idle money para um usuário.

        transactions_df: quando fornecido (ex.: pelo OpportunityEngine, que já
            buscou o DataFrame para montar o UserProfile), evita nova consulta.
            Quando omitido, busca via app.core.db.queries — comportamento
            idêntico ao anterior ao Ticket OPP1-B.
        user_profile: quando fornecido, a reserva de emergência (baseada em
            fss_level) é subtraída do saldo estimado antes de retornar.
        """
        if transactions_df is None:
            try:
                from app.core.db.queries import get_transactions_for_user
                transactions_df = get_transactions_for_user(user_id)
            except Exception as exc:
                logger.error("[IdleMoneyDetector] get_transactions user=%s: %s", user_id, exc)
                return self._empty_result()

        if transactions_df.is_empty():
            return self._empty_result()

        real_balance = self._fetch_real_checking_balance(user_id)
        return self._calculate(
            transactions_df, user_profile=user_profile, real_balance=real_balance
        )

    @staticmethod
    def _fetch_real_checking_balance(user_id: str):
        """Saldo real de conta corrente (account_balances, frescor de 7 dias).
        None → cai no proxy de fluxo de caixa. Falha aberta."""
        try:
            from app.core.db.balances import get_latest_balance
            return get_latest_balance(user_id, "CHECKING")
        except Exception as exc:
            logger.debug("[IdleMoneyDetector] real_balance user=%s: %s", user_id, exc)
            return None

    def _calculate(
        self,
        df,
        user_profile: "UserProfile | None" = None,
        real_balance=None,
    ) -> IdleMoneyResult:
        try:
            import polars as pl

            date_col = "transaction_date" if "transaction_date" in df.columns else "date"
            today = date.today()

            # Saldo bruto: real quando persistido e fresco (Opção B do plano);
            # senão, proxy = soma cumulativa de TODAS as transações conhecidas
            # (não só a janela de 3 meses abaixo) — ver docstring do result.
            if real_balance is not None and real_balance.balance is not None:
                gross_idle_amount = max(0.0, round(float(real_balance.balance), 2))
                idle_source: IdleSource = "REAL_BALANCE"
                balance_captured_at = real_balance.captured_at
            else:
                estimated_balance = float(df["amount"].sum()) if df.height > 0 else 0.0
                gross_idle_amount = max(0.0, round(estimated_balance, 2))
                idle_source = "CASHFLOW_PROXY"
                balance_captured_at = None

            # Janela: 3 meses completos anteriores ao mês atual — usada para
            # avg_income/avg_expenses (contexto) e para dimensionar a reserva.
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

            reserve_months = 0
            emergency_reserve = 0.0
            if user_profile is not None:
                fss_level = getattr(user_profile, "fss_level", None)
                reserve_months = _RESERVE_MONTHS_BY_FSS.get(fss_level, _DEFAULT_RESERVE_MONTHS)
                emergency_reserve = round(reserve_months * avg_expenses, 2)

            idle_amount = max(0.0, round(gross_idle_amount - emergency_reserve, 2))

            return IdleMoneyResult(
                idle_amount=idle_amount,
                gross_idle_amount=gross_idle_amount,
                emergency_reserve=emergency_reserve,
                reserve_months_applied=reserve_months,
                avg_income_3m=avg_income,
                avg_expenses_3m=avg_expenses,
                months_analyzed=months,
                has_sufficient_data=months >= self._MIN_MONTHS,
                idle_source=idle_source,
                balance_captured_at=balance_captured_at,
            )
        except Exception as exc:
            logger.error("[IdleMoneyDetector] _calculate: %s", exc)
            return self._empty_result()

    @staticmethod
    def _empty_result() -> IdleMoneyResult:
        return IdleMoneyResult(
            idle_amount=0.0,
            gross_idle_amount=0.0,
            emergency_reserve=0.0,
            reserve_months_applied=0,
            avg_income_3m=0.0,
            avg_expenses_3m=0.0,
            months_analyzed=0,
            has_sufficient_data=False,
        )
