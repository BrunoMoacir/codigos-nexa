# app/optimizer/detectors/investor_detector.py
# InvestorDetector — tipo de investidor e métricas de aporte

from __future__ import annotations

import logging

import polars as pl

logger = logging.getLogger(__name__)

# Keywords de proventos recebidos — indica carteira de investimentos ativa
_INCOME_INVESTMENT_PATTERN = (
    r"DIVIDENDO|JCP|PROVENTO|RENDIMENTO CDB|RENDIMENTO LCI|RENDIMENTO LCA|REND\. FII"
)


class InvestorDetector:
    """
    Detecta perfil de investidor com base em transferências para corretoras
    e recebimento de proventos.

    investor_type:
        NONE          — sem sinais de investimento
        CASUAL        — 1–3 aportes no período, sem dividendos
        ATIVO         — ≥4 aportes ou dividendos recebidos
        DIVERSIFICADO — aportes em ≥2 corretoras distintas OU dividendos + aportes

    NOTA sobre savings_rate:
        Não calculado aqui. profiles.py::UserProfileAnalyzer já produz savings_rate
        completo (com IncomeProfiler filtrado + behavior_tier + resilience_score).
        O ConsumptionProfiler.build() deve ler de lá — ver T1.6.

    Depende de T1.1: campo is_broker_txn.
    """

    def calc_investor_profile(self, df: pl.DataFrame) -> dict:
        """
        Args:
            df: transactions_clean já enriquecido (T1.1).

        Returns:
            dict com investor_type, investment_transfers_monthly,
            has_dividends e broker_diversity.
        """
        if df.is_empty():
            return self._zero_result()

        coverage_months = max(
            df.with_columns(
                (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
            ).select("ym").unique().height,
            1,
        )

        # ── Aportes em corretoras ─────────────────────────────────────────────
        broker_txn_count = 0
        investment_transfers_monthly = 0.0
        broker_diversity = 0

        if "is_broker_txn" in df.columns:
            broker_df = df.filter(
                pl.col("is_broker_txn") & (pl.col("amount") < 0)
            )
            broker_txn_count = len(broker_df)

            if broker_txn_count > 0:
                investment_transfers_monthly = (
                    float(broker_df["amount"].sum()) * -1 / coverage_months
                )
                if "merchant_id" in broker_df.columns:
                    broker_diversity = broker_df["merchant_id"].n_unique()
                elif "merchant_normalized" in broker_df.columns:
                    broker_diversity = broker_df["merchant_normalized"].n_unique()
                elif "description" in broker_df.columns:
                    broker_diversity = broker_df["description"].n_unique()
        elif "description" in df.columns:
            logger.debug("InvestorDetector: is_broker_txn ausente — rode T1.1 primeiro")

        # ── Dividendos e proventos recebidos ─────────────────────────────────
        has_dividends = False
        if "description" in df.columns:
            has_dividends = (
                df.filter(
                    (pl.col("amount") > 0)
                    & pl.col("description").str.to_uppercase().str.contains(
                        _INCOME_INVESTMENT_PATTERN
                    )
                ).height > 0
            )

        # ── Classificação ─────────────────────────────────────────────────────
        if broker_txn_count == 0 and not has_dividends:
            investor_type = "NONE"
        elif broker_diversity >= 2 or (has_dividends and broker_txn_count > 0):
            investor_type = "DIVERSIFICADO"
        elif broker_txn_count >= 4 or has_dividends:
            investor_type = "ATIVO"
        else:
            investor_type = "CASUAL"

        return {
            "investor_type": investor_type,
            "investment_transfers_monthly": round(investment_transfers_monthly, 2),
            "broker_txn_count": broker_txn_count,
            "has_dividends": has_dividends,
            "broker_diversity": broker_diversity,
        }

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _zero_result() -> dict:
        return {
            "investor_type": "NONE",
            "investment_transfers_monthly": 0.0,
            "broker_txn_count": 0,
            "has_dividends": False,
            "broker_diversity": 0,
        }
