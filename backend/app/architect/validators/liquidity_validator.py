"""
app/architect/validators/liquidity_validator.py - Validador de liquidez mensal

Feature: F3 - Nexa Architect
Version: 1.0.0

Responsabilidade:
    Calcular e classificar o impacto de liquidez de um compromisso mensal
    sobre a capacidade financeira real do usuário.

    O `liquidity_impact` é a fração do safe_to_spend que o compromisso consome.
    Valor negativo por convenção (é uma saída): -0.30 = 30% do disponível comprometido.

Fonte de dados:
    safe_to_spend: Vem da F1 (Core Engine). É o valor que o usuário pode gastar
                   com segurança no mês sem comprometer reserva de emergência.
    Fallback:      Se F1 não estiver disponível, usa max_monthly_budget do request
                   como proxy conservador.

Thresholds de risco (baseados em boas práticas de finanças pessoais):
    Até 25%   → Verde  (SAFE)     — confortável, sem alerta
    26–40%    → Amarelo (WARNING) — atenção, dentro do aceitável
    41–70%    → Laranja (HIGH)    — risco elevado, comprometimento significativo
    Acima 70% → Vermelho (CRITICAL) — insustentável para maioria dos perfis

Usage:
    from app.architect.validators.liquidity_validator import LiquidityValidator

    result = LiquidityValidator.calculate(
        monthly_payment=2500.0,
        safe_to_spend=8000.0,      # da F1; None se indisponível
        max_monthly_budget=3000.0, # do request; usado como fallback
    )
    print(result.impact)          # ex: -0.3125
    print(result.risk_level)      # "WARNING"
    print(result.warnings)        # lista de strings
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENUMS E CONSTANTES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class RiskLevel(str, Enum):
    """Nível de risco de liquidez."""
    SAFE     = "SAFE"      # até 25%
    WARNING  = "WARNING"   # 26–40%
    HIGH     = "HIGH"      # 41–70%
    CRITICAL = "CRITICAL"  # acima de 70%


# Thresholds de comprometimento do safe_to_spend (em fração)
_THRESHOLD_WARNING  = 0.25
_THRESHOLD_HIGH     = 0.40
_THRESHOLD_CRITICAL = 0.70


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULTADO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class LiquidityResult:
    """
    Resultado do cálculo de impacto de liquidez.

    Attributes:
        impact:             Fração do disponível comprometida, negativa por convenção.
                            Ex: -0.30 = 30% do safe_to_spend consumido.
        risk_level:         Classificação de risco (SAFE/WARNING/HIGH/CRITICAL).
        is_sustainable:     False se risk_level == CRITICAL (insustentável).
        reference_used:     "safe_to_spend" ou "max_monthly_budget" (qual base foi usada).
        reference_value:    O valor em R$ usado como denominador.
        monthly_payment:    A parcela mensal avaliada (R$).
        warnings:           Alertas não-bloqueantes gerados pelo cálculo.
    """
    impact: float
    risk_level: RiskLevel
    is_sustainable: bool
    reference_used: str
    reference_value: float
    monthly_payment: float
    warnings: list[str] = field(default_factory=list)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# VALIDADOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class LiquidityValidator:
    """
    Calcula e classifica o impacto de liquidez de um compromisso mensal.

    Ponto de entrada: `LiquidityValidator.calculate()`.

    Hierarquia de referência (qual valor usar como base):
        1. safe_to_spend da F1 (mais preciso — reflete receita real)
        2. max_monthly_budget do request (fallback quando F1 indisponível)
        3. Se nenhum disponível: impacto não calculável → retorna 0.0 com aviso

    Example:
        >>> result = LiquidityValidator.calculate(
        ...     monthly_payment=3000.0,
        ...     safe_to_spend=10000.0,
        ... )
        >>> result.impact          # -0.30
        >>> result.risk_level      # RiskLevel.HIGH
        >>> result.is_sustainable  # True
    """

    @staticmethod
    def calculate(
        monthly_payment: float,
        safe_to_spend: Optional[float] = None,
        max_monthly_budget: Optional[float] = None,
    ) -> LiquidityResult:
        """
        Calcula o impacto de liquidez e classifica o nível de risco.

        Args:
            monthly_payment:    Compromisso mensal da estratégia (R$).
            safe_to_spend:      Disponível mensal calculado pela F1 (R$).
                                Preferido como base de cálculo.
            max_monthly_budget: Budget declarado pelo usuário (R$).
                                Usado como fallback se safe_to_spend for None.

        Returns:
            LiquidityResult com impacto, nível de risco e avisos.
        """
        if monthly_payment < 0:
            raise ValueError("monthly_payment não pode ser negativo.")

        # ── Escolher base de referência ─────────────────────────────
        reference_value, reference_used = LiquidityValidator._pick_reference(
            safe_to_spend, max_monthly_budget, monthly_payment
        )

        warnings: list[str] = []

        # ── Avisar quando usamos fallback ───────────────────────────
        if reference_used == "max_monthly_budget":
            warnings.append(
                "safe_to_spend da F1 não disponível. "
                "Impacto de liquidez calculado com max_monthly_budget (estimativa conservadora)."
            )
        elif reference_used == "monthly_payment":
            warnings.append(
                "Sem referência de liquidez (safe_to_spend e max_monthly_budget ausentes). "
                "Impacto de liquidez não calculável; retornado como 0."
            )
            return LiquidityResult(
                impact=0.0,
                risk_level=RiskLevel.SAFE,
                is_sustainable=True,
                reference_used=reference_used,
                reference_value=reference_value,
                monthly_payment=monthly_payment,
                warnings=warnings,
            )

        # ── Calcular impacto ─────────────────────────────────────────
        ratio = monthly_payment / reference_value
        impact = -round(ratio, 4)   # negativo por convenção

        # ── Classificar risco ────────────────────────────────────────
        risk_level = LiquidityValidator._classify(ratio)

        # ── Gerar avisos específicos ─────────────────────────────────
        LiquidityValidator._add_risk_warnings(
            ratio, risk_level, monthly_payment, reference_value, warnings
        )

        # ── Verificar se excede o budget declarado ───────────────────
        if (
            reference_used == "safe_to_spend"
            and max_monthly_budget is not None
            and monthly_payment > max_monthly_budget
        ):
            warnings.append(
                f"Parcela mensal (R$ {monthly_payment:,.2f}) excede o "
                f"max_monthly_budget declarado (R$ {max_monthly_budget:,.2f})."
            )

        return LiquidityResult(
            impact=impact,
            risk_level=risk_level,
            is_sustainable=(risk_level != RiskLevel.CRITICAL),
            reference_used=reference_used,
            reference_value=reference_value,
            monthly_payment=monthly_payment,
            warnings=warnings,
        )

    # ── Helpers privados ─────────────────────────────────────────────

    @staticmethod
    def _pick_reference(
        safe_to_spend: Optional[float],
        max_monthly_budget: Optional[float],
        monthly_payment: float,
    ) -> tuple[float, str]:
        """
        Escolhe qual valor usar como denominador do cálculo.

        Prioridade: safe_to_spend > max_monthly_budget > monthly_payment.
        O último é um fallback de emergência que produz sempre -1.0 e aviso.
        """
        if safe_to_spend is not None and safe_to_spend > 0:
            return safe_to_spend, "safe_to_spend"
        if max_monthly_budget is not None and max_monthly_budget > 0:
            return max_monthly_budget, "max_monthly_budget"
        # Sem referência: usamos a própria parcela para não dividir por zero
        return monthly_payment if monthly_payment > 0 else 1.0, "monthly_payment"

    @staticmethod
    def _classify(ratio: float) -> RiskLevel:
        """
        Mapeia o ratio de comprometimento para o nível de risco.

        Args:
            ratio: monthly_payment / reference (positivo).

        Returns:
            RiskLevel correspondente.
        """
        if ratio <= _THRESHOLD_WARNING:
            return RiskLevel.SAFE
        if ratio <= _THRESHOLD_HIGH:
            return RiskLevel.WARNING
        if ratio <= _THRESHOLD_CRITICAL:
            return RiskLevel.HIGH
        return RiskLevel.CRITICAL

    @staticmethod
    def _add_risk_warnings(
        ratio: float,
        risk_level: RiskLevel,
        monthly_payment: float,
        reference_value: float,
        warnings: list[str],
    ) -> None:
        """Adiciona avisos textuais baseados no nível de risco."""
        pct = ratio * 100

        if risk_level == RiskLevel.WARNING:
            warnings.append(
                f"Comprometimento moderado: a estratégia consome {pct:.1f}% "
                f"do disponível mensal. Fique atento às despesas variáveis."
            )
        elif risk_level == RiskLevel.HIGH:
            warnings.append(
                f"Comprometimento elevado: {pct:.1f}% do disponível mensal. "
                "Recomenda-se revisar o orçamento antes de assumir este compromisso."
            )
        elif risk_level == RiskLevel.CRITICAL:
            warnings.append(
                f"Comprometimento crítico: {pct:.1f}% do disponível mensal. "
                "Esta estratégia pode inviabilizar despesas essenciais. "
                "Considere aumentar o prazo, reduzir o valor alvo ou poupar antes."
            )


__all__ = ["LiquidityValidator", "LiquidityResult", "RiskLevel"]
