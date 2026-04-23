# app/optimizer/detectors/travel_detector.py
# TravelDetector — score de viagem e detecção de Airbnb/nômade digital

from __future__ import annotations

import logging

import polars as pl

logger = logging.getLogger(__name__)


class TravelDetector:
    """
    Calcula travel_frequency_score (0–100) e classifica o perfil de viajante.

    Fórmula (melhorias_analise_perfil.md §2.1):
        score = regularidade(0–40) + intensidade(0–40) + internacional(0–20)

        regularidade  = (meses_com_gasto_viagem / 12) × 40
        intensidade   = min(travel_spend_ratio × 200, 40)
        internacional = min(foreign_txn_count × 4, 20)

    Depende de T1.1: campos `is_travel_related` e `is_foreign` no DataFrame.
    """

    def calc_travel_score(
        self,
        df: pl.DataFrame,
        total_spend: float,
    ) -> dict:
        """
        Calcula o score de viagem sobre o DataFrame fornecido.

        Args:
            df: transactions_clean já enriquecido (T1.1).
            total_spend: total de despesas no período (R$). Usado para ratio.

        Returns:
            dict com travel_frequency_score, travel_profile e métricas auxiliares.
        """
        if total_spend <= 0 or df.is_empty():
            return self._zero_result()

        if "is_travel_related" not in df.columns:
            logger.warning("TravelDetector: campo is_travel_related ausente — rode T1.1 primeiro")
            return self._zero_result("SEM_DADOS")

        # Combina is_travel_related (MCC + keywords gerais) com merchant_category_l2
        # (VOO, HOTEL, LOCADORA, AIRBNB) para cobertura máxima.
        travel_filter = pl.col("is_travel_related") & (pl.col("amount") < 0)
        if "merchant_category_l2" in df.columns:
            _TRAVEL_L2 = {"VOO", "HOTEL", "LOCADORA", "AIRBNB"}
            l2_filter = (
                pl.col("merchant_category_l2").is_in(list(_TRAVEL_L2))
                & (pl.col("amount") < 0)
            )
            travel_filter = travel_filter | l2_filter

        travel_df = df.filter(travel_filter)

        if travel_df.is_empty():
            return self._zero_result()

        # Regularidade: meses distintos com pelo menos 1 gasto de viagem
        months_with_travel = (
            travel_df
            .with_columns(
                (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
            )
            .select("ym")
            .unique()
            .height
        )

        travel_spend = float(travel_df["amount"].sum()) * -1
        travel_spend_ratio = travel_spend / total_spend

        # Internacional: transações marcadas como estrangeiras
        foreign_count = 0
        if "is_foreign" in df.columns:
            foreign_count = df.filter(
                pl.col("is_foreign") & (pl.col("amount") < 0)
            ).height

        score = (
            (min(months_with_travel, 12) / 12) * 40
            + min(travel_spend_ratio * 200, 40)
            + min(foreign_count * 4, 20)
        )
        score = round(min(score, 100.0), 1)

        profile = self._classify(score)

        # Média mensal de gasto em viagem (normalizada pelos meses do df)
        total_months = max(
            df.with_columns(
                (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
            ).select("ym").unique().height,
            1,
        )

        return {
            "travel_frequency_score": score,
            "travel_profile": profile,
            "travel_spend_monthly": round(travel_spend / total_months, 2),
            "months_with_travel": months_with_travel,
            "foreign_txn_count": foreign_count,
        }

    def detect_airbnb_profile(self, df: pl.DataFrame) -> dict:
        """
        Detecta uso de Airbnb e sinal de nômade digital.

        Nômade digital: Airbnb regular (≥3 transações) + coworking no período.
        Depende de T1.1: merchant_category_l2.
        """
        if df.is_empty() or "description" not in df.columns:
            return {"is_airbnb_user": False, "airbnb_frequency": "NUNCA", "is_digital_nomad": False}

        airbnb_df = df.filter(
            pl.col("description").str.to_uppercase().str.contains("AIRBNB")
            & (pl.col("amount") < 0)
        )
        airbnb_count = len(airbnb_df)

        if airbnb_count == 0:
            return {"is_airbnb_user": False, "airbnb_frequency": "NUNCA", "is_digital_nomad": False}

        airbnb_frequency = "REGULAR" if airbnb_count >= 3 else "OCASIONAL"

        is_digital_nomad = False
        if airbnb_frequency == "REGULAR" and "merchant_category_l2" in df.columns:
            coworking_count = df.filter(
                pl.col("merchant_category_l2") == "COWORKING"
            ).height
            is_digital_nomad = coworking_count >= 2

        return {
            "is_airbnb_user": True,
            "airbnb_frequency": airbnb_frequency,
            "is_digital_nomad": is_digital_nomad,
            "airbnb_txn_count": airbnb_count,
        }

    # ── Helpers privados ─────────────────────────────────────────────────────

    @staticmethod
    def _classify(score: float) -> str:
        if score <= 30:
            return "OCASIONAL"
        if score <= 60:
            return "MODERADO"
        if score <= 80:
            return "FREQUENTE"
        return "INTENSO"

    @staticmethod
    def _zero_result(profile: str = "OCASIONAL") -> dict:
        return {
            "travel_frequency_score": 0.0,
            "travel_profile": profile,
            "travel_spend_monthly": 0.0,
            "months_with_travel": 0,
            "foreign_txn_count": 0,
        }
