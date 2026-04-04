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

# Tiers de comportamento que merecem tratamento especial na recomendação
_CRITICAL_TIERS = {"CRITICO", "RISCO"}

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
    behavior_tier: str = "MODERADO",
    resilience_score: Optional[int] = None,
) -> float:
    """
    Retorna score 0.0–1.0 de pressão financeira.
    Quanto maior, mais conservadora deve ser a recomendação.

    Componentes base:
      savings_rate      → até 0.40
      trend de gastos   → até 0.20
      committed_pct     → até 0.25
      safe_to_spend     → até 0.15
      saúde financeira  → até 0.10 (resilience_score ou health_score)

    Componente adicional (v2):
      behavior_tier     → até 0.30 (CRITICO/RISCO amplificam a pressão)

    O behavior_tier é somado ao score base pois captura a combinação
    savings_rate + trend de forma mais precisa — um GASTADOR em deficit
    (CRITICO) deve receber pressão máxima mesmo que os outros indicadores
    não tenham dados completos.
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

    # Saúde financeira (até 0.10) — usa resilience_score se disponível (mais preciso)
    # resilience_score: 6 fatores (0–100) | health_score: 3 fatores (0–100)
    hs = resilience_score if resilience_score is not None else health_score
    if hs < 25:
        score += 0.10
    elif hs < 45:
        score += 0.05

    # Behavior tier (até 0.30) — amplifica pressão para situações críticas (v2)
    # CRITICO = deficit ou quase-deficit com tendência piorando
    # RISCO   = margem muito estreita sem déficit ainda
    # BOAS_PRATICAS/SOLIDO não adicionam (não há bonus negativo — score não penaliza quem vai bem)
    if behavior_tier == "CRITICO":
        score += 0.30
    elif behavior_tier == "RISCO":
        score += 0.15

    return min(1.0, score)


def apply_profile_fit(
    options: list[PaymentOption],
    pressure_score: float,
    profile_type: str,
    category: str,
    installments: int,
    safe_to_spend_ratio: float,
    committed_pct: float,
    behavior_tier: str = "MODERADO",
) -> list[PaymentOption]:
    """
    Aplica profile_fit a cada opção com base no pressure_score, perfil e behavior_tier.

    Regras por pressure_score:
      < 0.2  → todas OK, custo de oportunidade decide
      0.2–0.4 → FINANCIAMENTO → CAUTELA
      0.4–0.6 → FINANCIAMENTO → CAUTELA; parcelado longo → OK
      > 0.6   → FINANCIAMENTO → EVITAR; parcelado > 6x → CAUTELA

    Regras adicionais por profile_type:
      CONSERVADOR: sem CDC em compras discricionárias; sem parcelado > 6x se ratio < 0.15
      GASTADOR:    CDC como CAUTELA por padrão

    Regras adicionais por behavior_tier (v2 — mais precisas que profile_type):
      CRITICO: FINANCIAMENTO sempre EVITAR; parcelado > 3x → CAUTELA;
               PIX/AVISTA = IDEAL (preservar caixa é prioridade máxima)
      RISCO:   FINANCIAMENTO sempre CAUTELA (independente do pressure_score);
               parcelado > 6x → CAUTELA
    """
    is_discretionary = category.lower() in _DISCRETIONARY_CATEGORIES
    updated: list[PaymentOption] = []

    for opt in options:
        fit: str = "OK"

        if opt.method == PaymentMethod.FINANCIAMENTO:
            # behavior_tier tem precedência — captura déficit que pressure_score
            # pode subestimar quando dados de committed_pct estão incompletos
            if behavior_tier == "CRITICO":
                fit = "EVITAR"
            elif pressure_score > 0.6:
                fit = "EVITAR"
            elif behavior_tier == "RISCO":
                fit = "CAUTELA"
            elif pressure_score > 0.2:
                fit = "CAUTELA"
            elif profile_type == "CONSERVADOR" and is_discretionary:
                fit = "CAUTELA"
            elif profile_type == "GASTADOR":
                fit = "CAUTELA"

        elif opt.method == PaymentMethod.CARTAO_PARCELADO:
            n = opt.installments or installments
            if behavior_tier == "CRITICO" and n > 3:
                fit = "CAUTELA"
            elif behavior_tier == "RISCO" and n > 6:
                fit = "CAUTELA"
            elif pressure_score > 0.6 and n > 6:
                fit = "CAUTELA"
            elif profile_type == "CONSERVADOR" and n > 6 and safe_to_spend_ratio < 0.15:
                fit = "CAUTELA"

        elif opt.method in (PaymentMethod.PIX_AVISTA, PaymentMethod.CARTAO_AVISTA):
            # CRITICO/RISCO: à vista é sempre o melhor caminho (sem novas dívidas)
            if behavior_tier in _CRITICAL_TIERS or pressure_score > 0.6:
                fit = "IDEAL"

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
    behavior_tier: str = "MODERADO",
    resilience_score: Optional[int] = None,
) -> ProfileContext:
    """
    Calcula pressure_score e monta o resumo de perfil para o reasoning.

    Parâmetros v2:
        behavior_tier:    tier de comportamento (CRITICO/RISCO/MODERADO/BOAS_PRATICAS/SOLIDO)
        resilience_score: score de resiliência (0–100) — mais preciso que health_score
    """
    safe_to_spend_ratio = safe_to_spend / monthly_income if monthly_income > 0 else 0.0

    score = compute_pressure_score(
        savings_rate=savings_rate,
        trend=trend,
        health_score=health_score,
        committed_pct=committed_pct,
        safe_to_spend_ratio=safe_to_spend_ratio,
        behavior_tier=behavior_tier,
        resilience_score=resilience_score,
    )

    # Sumário contextualizado — usa behavior_tier para mensagens mais precisas
    tier_label = {
        "CRITICO":       "crítico",
        "RISCO":         "em risco",
        "MODERADO":      "moderado",
        "BOAS_PRATICAS": "sólido",
        "SOLIDO":        "excelente",
    }.get(behavior_tier, profile_type.lower())

    if behavior_tier == "CRITICO":
        if savings_rate < 0:
            summary = (
                f"Situação {tier_label}: você está gastando mais do que ganha "
                f"({abs(savings_rate):.0f}% de déficit). Evite qualquer nova dívida."
            )
        else:
            summary = (
                f"Situação {tier_label}: margem de poupança muito baixa ({savings_rate:.0f}%) "
                f"com gastos crescendo. Evite parcelamentos e financiamentos."
            )
    elif behavior_tier == "RISCO":
        summary = (
            f"Perfil {tier_label}: poupança de {savings_rate:.0f}% com pouca margem de segurança"
            + (f" — {committed_pct:.0%} da renda comprometida" if committed_pct > 0.5 else "")
            + ". Prefira opções sem juros."
        )
    elif score < 0.2:
        summary = f"Perfil {tier_label}: situação financeira confortável."
    elif score < 0.4:
        summary = f"Perfil {tier_label}: leve pressão financeira — prefira opções sem juros."
    elif score < 0.6:
        summary = (
            f"Perfil {tier_label}: pressão moderada "
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
