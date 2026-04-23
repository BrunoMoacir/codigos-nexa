"""
FSSCalculator — Financial Stress Score (0–100, onde 100 = máximo estresse).

Complementa (não duplica) o resilience_score de profiles.py.
Componentes exclusivos do FSS: rotativo do cartão, cheque especial, queda abrupta de renda.
"""

from __future__ import annotations
import re
import polars as pl

# Pré-compilado para evitar re-join a cada chamada de _calc_overdraft_usage
_OVERDRAFT_PATTERN = re.compile(
    r"CHEQUE ESPECIAL|LIMITE ESPECIAL|IOF ESPECIAL|JUROS ESPECIAL",
    re.IGNORECASE,
)


class FSSCalculator:
    """
    Financial Stress Score — índice 0–100 (100 = máximo estresse).

    Quando resilience_score disponível: usa como base (evita recalcular savings_rate,
    tendência e committed_pct) e adiciona apenas sinais exclusivos do FSS.
    """

    def calc_fss(
        self,
        profile,
        txns_90d: pl.DataFrame,
        income_3m_avg: float | None = None,
        income_12m_avg: float | None = None,
        resilience_score: int | None = None,
    ) -> dict:
        score = 0.0
        signals = []

        if resilience_score is not None:
            base_stress = max(0, (100 - resilience_score) * 0.50)
            score += base_stress
            if resilience_score < 35:
                signals.append(f"low_resilience={resilience_score}")
        else:
            savings_pct = getattr(profile, "savings_rate", 0.0)
            if savings_pct < -5:
                score += 15
                signals.append(f"negative_savings_rate={savings_pct:.1f}%")
            elif savings_pct < 5:
                score += 7
                signals.append("low_savings_rate")

            future_commitment = profile.committed_percentage
            if future_commitment > 0.4:
                score += min((future_commitment - 0.4) * 100, 20)
                signals.append(f"future_commitment={future_commitment:.1%}")

        # Rotativo do cartão — EXCLUSIVO FSS
        if profile.committed_percentage > 0.5 and profile.credit_spend_ratio > 0.7:
            revolving_score = min((profile.committed_percentage - 0.5) * 60, 30)
            score += revolving_score
            signals.append(f"likely_revolving={profile.committed_percentage:.1%}")

        # Cheque especial — EXCLUSIVO FSS
        overdraft_score = self._calc_overdraft_usage(txns_90d)
        score += overdraft_score * 25
        if overdraft_score > 0.1:
            signals.append(f"overdraft_usage={overdraft_score:.1%}")

        # Queda abrupta de renda — EXCLUSIVO FSS
        # income_3m_avg pode ser 0.0 (renda caiu para zero = maior sinal de estresse);
        # `if income_3m_avg` bloquearia esse caso, então usa `is not None`.
        if income_3m_avg is not None and income_12m_avg is not None and income_12m_avg > 0:
            income_drop = (income_3m_avg - income_12m_avg) / income_12m_avg
            if income_drop < -0.15:
                score += 20
                signals.append(f"income_drop={income_drop:.1%}")

        fss = round(min(score, 100.0), 1)

        if fss <= 20:
            level = "SAUDAVEL"
        elif fss <= 40:
            level = "ATENCAO"
        elif fss <= 65:
            level = "ALERTA"
        else:
            level = "CRITICO"

        return {
            "fss": fss,
            "fss_level": level,
            "fss_signals": signals,
        }

    def _calc_overdraft_usage(self, df: pl.DataFrame) -> float:
        """Estima uso de cheque especial por keywords na descrição (0.0–1.0)."""
        if df.is_empty() or "description" not in df.columns:
            return 0.0

        overdraft_months = (
            df.filter(pl.col("description").str.to_uppercase().str.contains(_OVERDRAFT_PATTERN.pattern))
            .with_columns(
                (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
            )
            .select("ym")
            .unique()
            .height
        )

        total_months = (
            df.with_columns(
                (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
            )
            .select("ym")
            .unique()
            .height
        )

        return overdraft_months / total_months if total_months > 0 else 0.0
