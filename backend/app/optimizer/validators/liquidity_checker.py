# app/optimizer/validators/liquidity_checker.py
# LiquidityChecker — classifica o risco da anuidade para o caixa do usuário
# Passo 2.3 — Funcionalidade 2: Nexa Optimizer

from app.optimizer.models import LiquidityRisk


class LiquidityChecker:
    """
    Classifica o impacto de liquidez da anuidade de um cartão.

    liquidity_impact = (annuity_effective / 12) / safe_to_spend
    Representa a fração da margem mensal que a parcela da anuidade consumiria.

    Faixas:
        > 0.50 → CRITICAL  (anuidade compromete mais de 50% da margem)
        > 0.25 → HIGH      (mais de 25%)
        > 0.10 → WARNING   (mais de 10%)
        ≤ 0.10 → SAFE
    """

    def check(self, liquidity_impact: float) -> LiquidityRisk:
        if liquidity_impact > 0.50:
            return LiquidityRisk.CRITICAL
        elif liquidity_impact > 0.25:
            return LiquidityRisk.HIGH
        elif liquidity_impact > 0.10:
            return LiquidityRisk.WARNING
        else:
            return LiquidityRisk.SAFE
