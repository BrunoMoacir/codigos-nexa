"""
app/forecast/cashflow/invoice_horizon.py — Pressão da Fatura Atual

Calcula o risco de colocar mais uma compra no cartão considerando:
  - Quantos dias faltam para a fatura fechar
  - Quanto já está comprometido no ciclo atual (transações de crédito)
  - Parcelas em andamento (shadow invoices INSTALLMENT)
  - Assinaturas do próximo mês (shadow invoices SUBSCRIPTION)

Fonte dos tipos de shadow invoice: forecast/schemas_shadow_invoice.py
  → Apenas "SUBSCRIPTION" e "INSTALLMENT" existem (não existe "CARTAO")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal, Optional

import polars as pl

logger = logging.getLogger(__name__)

InvoicePressure = Literal["SAFE", "MODERATE", "HEAVY", "CRITICAL"]

# Fallback de dias para fechar a fatura quando não há histórico suficiente
_DEFAULT_DAYS_TO_CLOSE = 15


@dataclass
class InvoiceHorizon:
    days_to_close: int                      # dias até fechar a fatura atual
    current_cycle_committed: float          # soma das transações de crédito no ciclo atual
    installments_in_flight: float           # parcelas INSTALLMENT do próximo ciclo
    subscriptions_monthly: float            # assinaturas SUBSCRIPTION do próximo mês
    monthly_income: float                   # renda mensal de referência
    invoice_pressure: InvoicePressure       # classificação de pressão

    @property
    def total_committed(self) -> float:
        return (
            self.current_cycle_committed
            + self.installments_in_flight
            + self.subscriptions_monthly
        )

    def to_dict(self) -> dict:
        return {
            "days_to_close": self.days_to_close,
            "current_cycle_committed": round(self.current_cycle_committed, 2),
            "installments_in_flight": round(self.installments_in_flight, 2),
            "subscriptions_monthly": round(self.subscriptions_monthly, 2),
            "total_committed": round(self.total_committed, 2),
            "monthly_income": round(self.monthly_income, 2),
            "invoice_pressure": self.invoice_pressure,
        }


def classify_invoice_pressure(
    current_cycle_committed: float,
    installments_in_flight: float,
    subscriptions_monthly: float,
    monthly_income: float,
    days_to_close: int,
) -> InvoicePressure:
    """
    Classifica a pressão de fatura em SAFE / MODERATE / HEAVY / CRITICAL.

    Critérios (em ordem de prioridade):
      CRITICAL: fatura fecha em ≤ 3 dias (qualquer cartão é arriscado)
      CRITICAL: compromisso > 80% da renda E fatura fecha em ≤ 10 dias
      HEAVY:    compromisso > 60% da renda E fatura fecha em ≤ 10 dias
      MODERATE: compromisso > 50% da renda OU fatura fecha em ≤ 7 dias
      SAFE:     demais casos
    """
    if days_to_close <= 3:
        return "CRITICAL"

    total = current_cycle_committed + installments_in_flight + subscriptions_monthly
    ratio = total / monthly_income if monthly_income > 0 else 1.0

    if ratio > 0.80 and days_to_close <= 10:
        return "CRITICAL"
    elif ratio > 0.60 and days_to_close <= 10:
        return "HEAVY"
    elif ratio > 0.50 or days_to_close <= 7:
        return "MODERATE"
    else:
        return "SAFE"


def _detect_days_to_close(transactions_df: pl.DataFrame, today: date) -> int:
    """
    Infere o dia de fechamento da fatura a partir do histórico de crédito.

    Estratégia: identifica o dia do mês em que o saldo de crédito "zera"
    (nova fatura começa) nas últimas 3–6 ocorrências. Fallback: 15 dias.
    """
    if transactions_df.is_empty():
        return _DEFAULT_DAYS_TO_CLOSE

    credit_cols = {"date", "amount", "payment_method"}
    ausentes = credit_cols - set(transactions_df.columns)
    if ausentes:
        # `payment_method` NUNCA existe no pipeline: não está no schema
        # Pluggy, nem no ETL, nem em transactions_clean. Ou seja, este
        # detector jamais inferiu nada — a classificação de pressão de
        # fatura roda 100% sobre a constante de fallback.
        #
        # O silêncio era o problema: o número parecia calculado. Enquanto
        # não houver fonte de meio de pagamento (o caminho natural é o tipo
        # da conta, que o snapshot de saldos já conhece), o aviso deixa
        # explícito que o valor é suposição, não medição.
        logger.warning(
            "[InvoiceHorizon] Sem %s — dia de fechamento NÃO inferido, "
            "usando fallback de %s dias",
            sorted(ausentes), _DEFAULT_DAYS_TO_CLOSE,
        )
        return _DEFAULT_DAYS_TO_CLOSE

    try:
        credit = transactions_df.filter(
            (pl.col("payment_method").str.to_lowercase().str.contains("crédito|credito|credit"))
            & (pl.col("amount") < 0)
        )
        if credit.is_empty():
            return _DEFAULT_DAYS_TO_CLOSE

        # Agrupa gastos por dia do mês e detecta onde há queda brusca (início de ciclo)
        credit = credit.with_columns(
            pl.col("date").cast(pl.Date).dt.day().alias("day_of_month")
        )
        daily = (
            credit.group_by("day_of_month")
            .agg(pl.col("amount").sum().alias("total"))
            .sort("day_of_month")
        )

        # Usa o dia com maior acúmulo como proxy do fechamento
        close_day = int(daily.sort("total").select("day_of_month").row(0)[0])
        close_day = max(1, min(close_day, 28))

        current_day = today.day
        if close_day > current_day:
            days_to_close = close_day - current_day
        else:
            # Já passou neste mês — próximo fechamento no mês seguinte
            next_close = today.replace(day=close_day) + timedelta(days=32)
            next_close = next_close.replace(day=close_day)
            days_to_close = (next_close - today).days

        return max(1, days_to_close)

    except Exception as exc:
        logger.debug("InvoiceHorizon | erro ao detectar dia de fechamento: %s", exc)
        return _DEFAULT_DAYS_TO_CLOSE


def build_invoice_horizon(
    transactions_df: pl.DataFrame,
    shadow_invoices: list,
    monthly_income: float,
    today: Optional[date] = None,
) -> InvoiceHorizon:
    """
    Constrói o InvoiceHorizon para o ciclo atual.

    Args:
        transactions_df: DataFrame de transações do usuário (polars)
        shadow_invoices: lista de ShadowInvoiceResponse (schemas_shadow_invoice.py)
        monthly_income:  renda mensal líquida estimada (IncomeProfiler)
        today:           data de referência (default: date.today())
    """
    today = today or date.today()

    days_to_close = _detect_days_to_close(transactions_df, today)

    # ── Comprometido no ciclo atual ──────────────────────────────────
    current_cycle_committed = 0.0
    if not transactions_df.is_empty() and "date" in transactions_df.columns:
        try:
            # Data de início do ciclo atual (aproximação: hoje − (30 − days_to_close))
            cycle_start = today - timedelta(days=max(0, 30 - days_to_close))
            credit_this_cycle = transactions_df.filter(
                (pl.col("date").cast(pl.Date) >= cycle_start)
                & (pl.col("amount") < 0)
                & (
                    pl.col("payment_method").str.to_lowercase()
                    .str.contains("crédito|credito|credit")
                    if "payment_method" in transactions_df.columns
                    else pl.lit(True)
                )
            )
            current_cycle_committed = abs(float(credit_this_cycle["amount"].sum()))
        except Exception as exc:
            logger.debug("InvoiceHorizon | erro ao calcular ciclo atual: %s", exc)

    # ── Shadow invoices: INSTALLMENT e SUBSCRIPTION ─────────────────
    installments_in_flight = 0.0
    subscriptions_monthly = 0.0

    next_cycle_end = today + timedelta(days=30)

    for inv in shadow_invoices:
        try:
            due: date = (
                inv.next_due_date.date()
                if isinstance(inv.next_due_date, datetime)
                else inv.next_due_date
            )
            amount = abs(float(inv.amount))

            if inv.type == "INSTALLMENT" and today <= due <= next_cycle_end:
                installments_in_flight += amount
            elif inv.type == "SUBSCRIPTION" and today <= due <= next_cycle_end:
                subscriptions_monthly += amount
        except Exception as exc:
            logger.debug("InvoiceHorizon | shadow invoice ignorada: %s", exc)

    pressure = classify_invoice_pressure(
        current_cycle_committed=current_cycle_committed,
        installments_in_flight=installments_in_flight,
        subscriptions_monthly=subscriptions_monthly,
        monthly_income=monthly_income,
        days_to_close=days_to_close,
    )

    return InvoiceHorizon(
        days_to_close=days_to_close,
        current_cycle_committed=round(current_cycle_committed, 2),
        installments_in_flight=round(installments_in_flight, 2),
        subscriptions_monthly=round(subscriptions_monthly, 2),
        monthly_income=round(monthly_income, 2),
        invoice_pressure=pressure,
    )
