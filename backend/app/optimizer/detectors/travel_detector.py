# app/optimizer/detectors/travel_detector.py
# TravelDetector — score de viagem e detecção de Airbnb/nômade digital

from __future__ import annotations

import logging

import polars as pl

from app.optimizer.detectors.evidence_scorer import compute_false_positive_risk

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

        # Hierarquia de detecção de viagem:
        # 1. merchant_category_l1 == "viagem" — canônico, derivado do L2
        # 2. merchant_category_l2 IN (VOO, HOTEL...) — subcategoria explícita
        # 3. is_travel_related — flag MCC + keyword booleano
        travel_filter = pl.lit(False) & (pl.col("amount") < 0)  # seed vazio

        if "merchant_category_l1" in df.columns:
            travel_filter = travel_filter | (
                (pl.col("merchant_category_l1") == "viagem") & (pl.col("amount") < 0)
            )

        if "merchant_category_l2" in df.columns:
            _TRAVEL_L2 = {"VOO", "HOTEL", "LOCADORA", "AIRBNB"}
            travel_filter = travel_filter | (
                pl.col("merchant_category_l2").is_in(list(_TRAVEL_L2))
                & (pl.col("amount") < 0)
            )

        # Fallback: is_travel_related (MCC + keyword)
        travel_filter = travel_filter | (pl.col("is_travel_related") & (pl.col("amount") < 0))

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

        regularidade_pts  = (min(months_with_travel, 12) / 12) * 40
        intensidade_pts   = min(travel_spend_ratio * 200, 40)
        internacional_pts = min(foreign_count * 4, 20)

        score = regularidade_pts + intensidade_pts + internacional_pts
        score = round(min(score, 100.0), 1)

        profile = self._classify(score)
        confidence = round(score / 100, 4)

        supporting_signals: list[str] = []
        if regularidade_pts > 0:
            supporting_signals.append(f"meses_com_viagem={months_with_travel}")
        if intensidade_pts > 0:
            supporting_signals.append(f"proporcao_gasto_viagem={travel_spend_ratio:.1%}")
        if foreign_count > 0:
            supporting_signals.append(f"transacoes_internacionais={foreign_count}")

        missing_signals: list[str] = []
        if months_with_travel < 3:
            missing_signals.append("regularidade_viagens_baixa")
        if travel_spend_ratio < 0.05:
            missing_signals.append("proporcao_gasto_viagem_baixa")
        if foreign_count == 0:
            missing_signals.append("sem_transacoes_internacionais")

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
            "confidence": confidence,
            "supporting_signals": supporting_signals,
            "missing_signals": missing_signals,
            "false_positive_risk": compute_false_positive_risk(confidence),
        }

    def detect_airbnb_profile(self, df: pl.DataFrame) -> dict:
        """
        Detecta uso de Airbnb e sinal de nômade digital.

        Nômade digital: Airbnb regular (≥3 transações) + coworking no período.
        Depende de T1.1: merchant_category_l2.
        """
        if df.is_empty() or "description" not in df.columns:
            return {
                "is_airbnb_user": False, "airbnb_frequency": "NUNCA", "is_digital_nomad": False,
                "confidence": 0.0, "supporting_signals": [], "missing_signals": ["sem_transacoes_airbnb"], "false_positive_risk": "high",
            }

        airbnb_df = df.filter(
            pl.col("description").str.to_uppercase().str.contains("AIRBNB")
            & (pl.col("amount") < 0)
        )
        airbnb_count = len(airbnb_df)

        if airbnb_count == 0:
            return {
                "is_airbnb_user": False, "airbnb_frequency": "NUNCA", "is_digital_nomad": False,
                "confidence": 0.0, "supporting_signals": [], "missing_signals": ["sem_transacoes_airbnb"], "false_positive_risk": "high",
            }

        airbnb_frequency = "REGULAR" if airbnb_count >= 3 else "OCASIONAL"

        is_digital_nomad = False
        coworking_count = 0
        if airbnb_frequency == "REGULAR" and "merchant_category_l2" in df.columns:
            coworking_count = df.filter(
                pl.col("merchant_category_l2") == "COWORKING"
            ).height
            is_digital_nomad = coworking_count >= 2

        if is_digital_nomad:
            confidence = 0.88
        elif airbnb_frequency == "REGULAR":
            confidence = 0.72
        else:
            confidence = 0.50

        supporting_signals: list[str] = [f"airbnb_txns={airbnb_count}"]
        if is_digital_nomad:
            supporting_signals.append(f"coworking_txns={coworking_count}")

        missing_signals: list[str] = []
        if airbnb_frequency != "REGULAR":
            missing_signals.append("airbnb_uso_insuficiente")
        if not is_digital_nomad:
            missing_signals.append("sem_coworking")

        return {
            "is_airbnb_user": True,
            "airbnb_frequency": airbnb_frequency,
            "is_digital_nomad": is_digital_nomad,
            "airbnb_txn_count": airbnb_count,
            "confidence": confidence,
            "supporting_signals": supporting_signals,
            "missing_signals": missing_signals,
            "false_positive_risk": compute_false_positive_risk(confidence),
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
            "confidence": 0.0,
            "supporting_signals": [],
            "missing_signals": ["regularidade_viagens_baixa", "proporcao_gasto_viagem_baixa", "sem_transacoes_internacionais"],
            "false_positive_risk": "high",
        }
