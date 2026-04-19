# app/optimizer/validators/liquidity_checker.py
# LiquidityChecker — classifica o risco da anuidade para o caixa do usuário
# Camada 3 — Motor Anti-Falsos-Positivos (Card Optimizer v2.1)

from app.optimizer.models import LiquidityRisk


class LiquidityChecker:
    """
    Classifica o impacto de liquidez da anuidade de um cartão.

    liquidity_impact = (annuity_effective / 12) / safe_to_spend
    Representa a fração da margem mensal que a parcela da anuidade consumiria.

    Faixas (arquitetura v2.1 — thresholds mais conservadores):
        < 0.05 → SAFE     (anuidade < 5% da margem — sem impacto relevante)
        < 0.10 → WARNING  (5–10% da margem — observar)
        < 0.20 → HIGH     (10–20% da margem — impacto significativo)
        ≥ 0.20 → CRITICAL (≥ 20% da margem — anuidade compromete liquidez)

    Correspondência com penalidades no ranking:
        SAFE:     × 1.00 (sem desconto)
        WARNING:  × 0.90 (−10%)
        HIGH:     × 0.60 (−40%)
        CRITICAL: × 0.20 (−80%)
    """

    def check(self, liquidity_impact: float) -> LiquidityRisk:
        if liquidity_impact < 0.05:
            return LiquidityRisk.SAFE
        elif liquidity_impact < 0.10:
            return LiquidityRisk.WARNING
        elif liquidity_impact < 0.20:
            return LiquidityRisk.HIGH
        else:
            return LiquidityRisk.CRITICAL
