# app/optimizer/detectors/mei_detector.py
# MEIDetector — detecta padrão de microempreendedor em conta PF

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from app.forecast.etl.income_profiler import IncomeProfile

logger = logging.getLogger(__name__)

# Threshold mínimo de gasto em ferramentas B2B para sinalizar atividade empresarial
_B2B_SPEND_THRESHOLD = 50.0
# Quantidade mínima de recebimentos de CNPJs distintos para sinalizar múltiplos clientes
_MIN_CNPJ_PAYERS = 3
# income_stability abaixo deste valor indica renda irregular (sinal PJ/MEI)
_INSTABILITY_THRESHOLD = 0.45


class MEIDetector:
    """
    Detecta padrão de microempreendedor (MEI/PJ disfarçado) em conta PF.

    Combina 4 sinais independentes — 2 ou mais confirmam o padrão:
        1. income_pattern PJ/MIXED já detectado pelo IncomeProfiler
        2. Gastos em ferramentas B2B (is_b2b do T1.1)
        3. Recebimentos de múltiplos CNPJs (campo payer_document_type do Open Finance)
        4. Renda instável (income_stability < 0.45)

    Depende de T1.1: campo is_b2b.
    """

    def detect_mei_pattern(
        self,
        df: pl.DataFrame,
        income_profile: IncomeProfile | None,
    ) -> dict:
        """
        Args:
            df: transactions_clean já enriquecido (T1.1).
            income_profile: saída do IncomeProfiler (pode ser None).

        Returns:
            dict com is_likely_mei, mei_confidence (0.0–1.0) e mei_signals.
        """
        if df.is_empty():
            return self._zero_result()

        signals: list[str] = []
        coverage_months = max(
            df.with_columns(
                (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
            ).select("ym").unique().height,
            1,
        )

        # ── Sinal 1: IncomeProfiler já classificou como PJ ou MIXED ──────────
        if income_profile and income_profile.income_pattern.value in ("PJ", "MIXED"):
            signals.append("income_pattern_pj")

        # ── Sinal 2: gastos em ferramentas B2B ───────────────────────────────
        b2b_spend_monthly = 0.0
        if "is_b2b" in df.columns:
            b2b_df = df.filter(pl.col("is_b2b") & (pl.col("amount") < 0))
            b2b_total = float(b2b_df["amount"].sum()) * -1 if not b2b_df.is_empty() else 0.0
            b2b_spend_monthly = b2b_total / coverage_months
            if b2b_total > _B2B_SPEND_THRESHOLD:
                signals.append("b2b_tools")
        else:
            logger.debug("MEIDetector: is_b2b ausente — rode T1.1 primeiro")

        # ── Sinal 3: recebimentos de múltiplos CNPJs ─────────────────────────
        # payer_document_type é campo opcional do Open Finance (nem sempre presente)
        pj_credits = 0
        if "payer_document_type" in df.columns:
            pj_credits = df.filter(
                (pl.col("amount") > 0)
                & (pl.col("payer_document_type").str.to_uppercase() == "CNPJ")
            ).height
            if pj_credits >= _MIN_CNPJ_PAYERS:
                signals.append("multiple_cnpj_payers")

        # ── Sinal 4: renda instável (PJ/freela tem CV alto) ──────────────────
        # income_stability: 0.0–1.0 — CLT estável → ~0.9, PJ variável → ~0.3
        if income_profile and income_profile.income_stability < _INSTABILITY_THRESHOLD:
            signals.append("unstable_income")

        is_likely_mei = len(signals) >= 2
        confidence = round(min(len(signals) / 4, 1.0), 2)

        return {
            "is_likely_mei": is_likely_mei,
            "mei_confidence": confidence,
            "mei_signals": signals,
            "b2b_spend_monthly": round(b2b_spend_monthly, 2),
            "pj_credit_count": pj_credits,
        }

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _zero_result() -> dict:
        return {
            "is_likely_mei": False,
            "mei_confidence": 0.0,
            "mei_signals": [],
            "b2b_spend_monthly": 0.0,
            "pj_credit_count": 0,
        }
