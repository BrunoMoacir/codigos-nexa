"""
app/opportunities/calculators/issuer_risk.py

V2 (docs/OPP.md §8.2) — tier de risco do emissor e bucket de liquidez.

Só o que o IRPFCalculator não cobre: classificação qualitativa de risco
por instituição (curada, não é rating de agência) e a penalidade de yield
usada pelo scorecard por banco para o ranking ajustado a risco.

O tier é conservador por padrão: instituição desconhecida → tier 3.
"""

from __future__ import annotations

_ISSUER_RISK_TIER: dict[str, int] = {
    # Tier 1 — bancões sistêmicos
    "Itaú": 1,
    "Bradesco": 1,
    "Banco do Brasil": 1,
    "Santander": 1,
    "Caixa Econômica": 1,
    # Tier 2 — digitais/plataformas consolidadas
    "BTG Pactual": 2,
    "Nubank": 2,
    "Banco Inter": 2,
    "C6 Bank": 2,
    "XP Investimentos": 2,
    # Tier 3 — médios/pequenos
    "Banco Pan": 3,
    "Sofisa Direto": 3,
    "Sicoob": 3,
    "PagBank": 3,
    "PicPay": 3,
}

# Penalidade anual (decimal) aplicada ao yield no ranking ajustado a risco.
_RISK_PENALTY: dict[int, float] = {1: 0.0, 2: 0.005, 3: 0.015}


def issuer_tier(bank_name: str) -> int:
    """Tier de risco do emissor. Desconhecido → 3 (conservador)."""
    return _ISSUER_RISK_TIER.get(bank_name, 3)


def risk_penalty(tier: int) -> float:
    """Penalidade anual (decimal) sobre o yield para o tier informado."""
    return _RISK_PENALTY.get(tier, _RISK_PENALTY[3])


def liquidity_bucket(liquidity_days: int, liquidity: str) -> str:
    """Bucket de liquidez para o 'melhor banco por bucket' do scorecard."""
    if liquidity == "daily" or liquidity_days <= 1:
        return "diaria"
    return "ate_12m" if liquidity_days <= 365 else "longo_prazo"


__all__ = ["issuer_tier", "risk_penalty", "liquidity_bucket"]
