"""
app/purchase/profile_context.py — Contexto de Perfil para Recomendação de Compra

Calcula o pressure_score (0.0–1.0) com base no perfil financeiro do usuário
e aplica profile_fit a cada PaymentOption.

Inputs reutilizados (não cria nada novo):
  - UserProfile (financeiro)  → forecast/etl/profiles.py
  - ConsumptionProfiler       → optimizer/profiler.py
  - safe_to_spend_ratio       → safe_to_spend / monthly_income

O score NÃO bloqueia opções — apenas muda profile_fit e o texto do reasoning.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.purchase.models import PaymentMethod, PaymentOption

# Categorias tipicamente discricionárias (não essenciais)
_DISCRETIONARY_CATEGORIES = {
    "lazer", "vestuário", "roupas", "eletrônicos", "eletronicos",
    "viagem", "restaurante", "beleza", "games", "entretenimento",
}


@dataclass
class ProfileContext:
    """Resultado do cálculo de contexto de perfil para uma compra."""
    pressure_score: float                   # 0.0 (sem pressão) → 1.0 (máxima pressão)
    profile_type: str                       # CONSERVADOR / EQUILIBRADO / GASTADOR
    summary: str                            # texto curto para o reasoning


def compute_pressure_score(
    savings_rate: float,
    trend: str,
    health_score: int,
    committed_pct: float,
    safe_to_spend_ratio: float,
) -> float:
    """
    Retorna score 0.0–1.0 de pressão financeira.
    Quanto maior, mais conservadora deve ser a recomendação.

    Componentes:
      savings_rate    → até 0.40
      trend de gastos → até 0.20
      committed_pct   → até 0.25
      safe_to_spend   → até 0.15
      health_score    → até 0.10 (score composto 0–100 do UserProfileAnalyzer)
    """
    score = 0.0

    # Savings rate (até 0.40)
    if savings_rate < 0:
        score += 0.40
    elif savings_rate < 5:
        score += 0.30
    elif savings_rate < 10:
        score += 0.20
    elif savings_rate < 20:
        score += 0.05

    # Tendência de gastos (até 0.20)
    if trend == "CRESCENTE":
        score += 0.20

    # Comprometimento da renda (até 0.25)
    if committed_pct > 0.90:
        score += 0.25
    elif committed_pct > 0.80:
        score += 0.15
    elif committed_pct > 0.70:
        score += 0.05

    # Safe-to-spend vs renda (até 0.15)
    if safe_to_spend_ratio < 0.05:
        score += 0.15
    elif safe_to_spend_ratio < 0.15:
        score += 0.08

    # Saúde financeira composta (até 0.10)
    # health_score é o score 0–100 do UserProfileAnalyzer — captura deterioração
    # que os outros componentes ainda não refletem (ex: score caindo mas savings_rate ok)
    if health_score < 30:
        score += 0.10
    elif health_score < 50:
        score += 0.05

    return min(1.0, score)


def apply_profile_fit(
    options: list[PaymentOption],
    pressure_score: float,
    profile_type: str,
    category: str,
    installments: int,
    safe_to_spend_ratio: float,
    committed_pct: float,
) -> list[PaymentOption]:
    """
    Aplica profile_fit a cada opção com base no pressure_score e perfil.

    Regras:
      pressure < 0.2  → todas OK, custo de oportunidade decide
      0.2–0.4         → FINANCIAMENTO → CAUTELA
      0.4–0.6         → FINANCIAMENTO → CAUTELA; parcelado longo → OK
      > 0.6           → FINANCIAMENTO → EVITAR; parcelado > 6x → CAUTELA

    Regras adicionais por perfil:
      CONSERVADOR: sem CDC em compras discricionárias; sem parcelado > 6x se ratio < 0.15
      GASTADOR:    CDC só se não houver alternativa acessível (tratado como pressure alta)
    """
    is_discretionary = category.lower() in _DISCRETIONARY_CATEGORIES
    updated: list[PaymentOption] = []

    for opt in options:
        fit: str = "OK"

        if opt.method == PaymentMethod.FINANCIAMENTO:
            if pressure_score > 0.6:
                fit = "EVITAR"
            elif pressure_score > 0.2:
                fit = "CAUTELA"
            elif profile_type == "CONSERVADOR" and is_discretionary:
                fit = "CAUTELA"
            elif profile_type == "GASTADOR":
                fit = "CAUTELA"

        elif opt.method == PaymentMethod.CARTAO_PARCELADO:
            n = opt.installments or installments
            if pressure_score > 0.6 and n > 6:
                fit = "CAUTELA"
            elif profile_type == "CONSERVADOR" and n > 6 and safe_to_spend_ratio < 0.15:
                fit = "CAUTELA"

        elif opt.method in (PaymentMethod.PIX_AVISTA, PaymentMethod.CARTAO_AVISTA):
            if pressure_score > 0.6:
                fit = "IDEAL"   # preserva caixa no curto prazo

        updated.append(opt.model_copy(update={"profile_fit": fit}))

    return updated


def build_profile_context(
    profile_type: str,
    savings_rate: float,
    trend: str,
    health_score: int,
    committed_pct: float,
    monthly_income: float,
    safe_to_spend: float,
) -> ProfileContext:
    """
    Calcula pressure_score e monta o resumo de perfil para o reasoning.
    """
    safe_to_spend_ratio = safe_to_spend / monthly_income if monthly_income > 0 else 0.0

    score = compute_pressure_score(
        savings_rate=savings_rate,
        trend=trend,
        health_score=health_score,
        committed_pct=committed_pct,
        safe_to_spend_ratio=safe_to_spend_ratio,
    )

    if score < 0.2:
        summary = f"Perfil {profile_type.lower()}: situação financeira confortável."
    elif score < 0.4:
        summary = f"Perfil {profile_type.lower()}: leve pressão financeira — prefira opções sem juros."
    elif score < 0.6:
        summary = (
            f"Perfil {profile_type.lower()}: pressão moderada "
            f"({committed_pct:.0%} da renda comprometida) — evite financiamento."
        )
    else:
        parts = []
        if savings_rate < 5:
            parts.append(f"taxa de poupança de {savings_rate:.0f}%")
        if committed_pct > 0.80:
            parts.append(f"{committed_pct:.0%} da renda comprometida")
        if trend == "CRESCENTE":
            parts.append("gastos em tendência crescente")
        detail = "; ".join(parts) if parts else "múltiplos indicadores de pressão"
        summary = f"Atenção: {detail}. Priorize preservar caixa."

    return ProfileContext(
        pressure_score=round(score, 2),
        profile_type=profile_type,
        summary=summary,
    )
