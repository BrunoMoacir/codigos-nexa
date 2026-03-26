"""
app/cashflow/safe_to_spend.py - Calculadora de Safe-to-Spend DEFINITIVA

RESPONSABILIDADE:
    Calcula quanto o usuário pode gastar com segurança sem comprometer
    obrigações futuras

INTEGRAÇÃO:
    - Usa projeção de cashflow (CashflowProjector)
    - Aplica buffer de segurança (15% padrão)
    - Considera Shadow Invoices

MUDANÇAS v2.0:
    ✅ Compatível com novo CashflowProjector
    ✅ Usa coluna "expenses" (renomeada de "shadow_amount")
    ✅ Mantém SafeToSpendResult (dataclass)
    ✅ Mantém toda lógica de cálculo

USAGE:
    calculator = SafeToSpendCalculator(safety_buffer_pct=0.15)
    result = calculator.calculate(
        projection_df=projection_df,
        horizon_days=30
    )
"""

import logging
import polars as pl
from dataclasses import dataclass
from typing import Literal


logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TYPES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


@dataclass
class SafeToSpendResult:
    """
    Resultado do cálculo de safe-to-spend.
    
    Attributes:
        current_balance: Saldo atual
        min_projected_balance: Menor saldo projetado no período
        total_shadow_invoices: Impacto total das shadow invoices
        safety_buffer: Buffer de segurança aplicado
        safe_to_spend_total: Valor total que pode gastar
        safe_to_spend_daily: Valor médio diário que pode gastar
        days: Período considerado
        risk_level: LOW/MEDIUM/HIGH/CRITICAL
    
    Example:
        >>> result = SafeToSpendResult(
        ...     current_balance=5000.0,
        ...     min_projected_balance=3500.0,
        ...     total_shadow_invoices=-1200.0,
        ...     safety_buffer=180.0,
        ...     safe_to_spend_total=1320.0,
        ...     safe_to_spend_daily=44.0,
        ...     days=30,
        ...     risk_level="LOW"
        ... )
    """
    
    current_balance: float
    min_projected_balance: float
    total_shadow_invoices: float
    safety_buffer: float
    safe_to_spend_total: float
    safe_to_spend_daily: float
    days: int
    risk_level: RiskLevel
    
    def to_dict(self) -> dict:
        """Converte para dict (útil para JSON)."""
        return {
            "current_balance": self.current_balance,
            "min_projected_balance": self.min_projected_balance,
            "total_shadow_invoices": self.total_shadow_invoices,
            "safety_buffer": self.safety_buffer,
            "safe_to_spend_total": self.safe_to_spend_total,
            "safe_to_spend_daily": self.safe_to_spend_daily,
            "days": self.days,
            "risk_level": self.risk_level
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SAFE TO SPEND CALCULATOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SafeToSpendCalculator:
    """
    Calcula safe-to-spend considerando projeção de cashflow.
    
    Fórmula:
        safe_to_spend = min_balance_projetado - buffer_segurança
    
    Buffer de Segurança:
        - Percentual sobre obrigações futuras (padrão: 15%)
        - Mínimo absoluto (padrão: R$ 200)
    
    Example:
        >>> calculator = SafeToSpendCalculator(safety_buffer_pct=0.15)
        >>> 
        >>> result = calculator.calculate(
        ...     projection_df=projection_df,
        ...     horizon_days=30
        ... )
        >>> 
        >>> print(f"Você pode gastar: R$ {result.safe_to_spend_daily:.2f}/dia")
        Você pode gastar: R$ 44.00/dia
    """
    
    def __init__(
        self,
        safety_buffer_pct: float = 0.15,
        min_buffer_absolute: float = 200.0
    ):
        """
        Inicializa calculadora.
        
        Args:
            safety_buffer_pct: Percentual de buffer (padrão: 15% = 0.15)
            min_buffer_absolute: Buffer mínimo absoluto (padrão: R$ 200)
        """
        self.safety_buffer_pct = safety_buffer_pct
        self.min_buffer_absolute = min_buffer_absolute
        self.logger = logging.getLogger(__name__)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PUBLIC API
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def calculate(
        self,
        projection_df: pl.DataFrame,
        horizon_days: int = 30
    ) -> SafeToSpendResult:
        """
        Calcula safe-to-spend baseado na projeção.
        
        Args:
            projection_df: DataFrame retornado por CashflowProjector.project()
                Colunas obrigatórias:
                - projected_balance (float)
                - expenses (float) - ✅ ATUALIZADO (antes: shadow_amount)
            horizon_days: Período considerado (dias)
        
        Returns:
            SafeToSpendResult com cálculo completo
        
        Raises:
            ValueError: Se DataFrame vazio ou sem colunas necessárias
        
        Example:
            >>> result = calculator.calculate(projection_df, 30)
            >>> 
            >>> if result.risk_level == "HIGH":
            ...     print("⚠️ ATENÇÃO: Risco alto de saldo negativo!")
        """
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # VALIDAÇÕES
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        if projection_df.is_empty():
            raise ValueError("DataFrame de projeção está vazio")
        
        # ✅ ATUALIZADO: Verifica coluna "expenses" (não mais "shadow_amount")
        required = {"projected_balance", "expenses"}
        if not required.issubset(projection_df.columns):
            missing = required - set(projection_df.columns)
            raise ValueError(f"Colunas faltando: {missing}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 1: Extrair métricas da projeção
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        current_balance = float(projection_df["projected_balance"][0])
        min_projected_balance = float(projection_df["projected_balance"].min())
        
        # ✅ ATUALIZADO: Usa coluna "expenses" (não mais "shadow_amount")
        total_shadow_invoices = float(projection_df["expenses"].sum())
        
        self.logger.debug(
            f"Saldo atual: R$ {current_balance:,.2f}, "
            f"Mínimo projetado: R$ {min_projected_balance:,.2f}"
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 2: Calcular buffer de segurança
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Buffer percentual sobre obrigações futuras
        buffer_pct = abs(total_shadow_invoices) * self.safety_buffer_pct
        
        # Garantir buffer mínimo absoluto
        safety_buffer = max(buffer_pct, self.min_buffer_absolute)
        
        self.logger.debug(
            f"Buffer calculado: R$ {safety_buffer:,.2f} "
            f"({self.safety_buffer_pct:.1%} de R$ {abs(total_shadow_invoices):,.2f})"
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 3: Calcular safe-to-spend
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Fórmula: safe = min_balance_projetado - buffer
        safe_to_spend_total = min_projected_balance - safety_buffer
        
        # Garantir que não seja negativo
        safe_to_spend_total = max(0.0, safe_to_spend_total)
        
        # Média diária
        safe_to_spend_daily = (
            safe_to_spend_total / horizon_days if horizon_days > 0 else 0.0
        )
        
        self.logger.info(
            f"Safe-to-spend: R$ {safe_to_spend_total:,.2f} total "
            f"(R$ {safe_to_spend_daily:,.2f}/dia)"
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 4: Classificar risco
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        risk_level = self._classify_risk(
            safe_to_spend_total,
            min_projected_balance
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 5: Retornar resultado
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        return SafeToSpendResult(
            current_balance=round(current_balance, 2),
            min_projected_balance=round(min_projected_balance, 2),
            total_shadow_invoices=round(total_shadow_invoices, 2),
            safety_buffer=round(safety_buffer, 2),
            safe_to_spend_total=round(safe_to_spend_total, 2),
            safe_to_spend_daily=round(safe_to_spend_daily, 2),
            days=horizon_days,
            risk_level=risk_level
        )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PRIVATE HELPERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _classify_risk(
        self,
        safe_to_spend: float,
        min_projected_balance: float
    ) -> RiskLevel:
        """
        Classifica risco financeiro.
        
        Critérios:
            CRITICAL: Safe-to-spend ≤ 0 OU saldo projetado negativo
            HIGH: Safe-to-spend < 300
            MEDIUM: Safe-to-spend < 1000
            LOW: Safe-to-spend ≥ 1000
        
        Args:
            safe_to_spend: Valor seguro para gastar
            min_projected_balance: Menor saldo projetado
        
        Returns:
            RiskLevel
        """
        # Saldo negativo = crítico
        if min_projected_balance < 0:
            return "CRITICAL"
        
        # Safe-to-spend baixo ou zero
        if safe_to_spend <= 0:
            return "CRITICAL"
        elif safe_to_spend < 300:
            return "HIGH"
        elif safe_to_spend < 1000:
            return "MEDIUM"
        else:
            return "LOW"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER FUNCTION (Convenience)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def calculate_safe_to_spend(
    projection_df: pl.DataFrame,
    horizon_days: int = 30,
    safety_buffer_pct: float = 0.15
) -> SafeToSpendResult:
    """
    Função helper que encapsula SafeToSpendCalculator.
    
    Útil para imports diretos:
        from app.cashflow.safe_to_spend import calculate_safe_to_spend
    
    Args:
        projection_df: DataFrame com projeção de cashflow
        horizon_days: Período em dias
        safety_buffer_pct: Percentual de buffer (0.15 = 15%)
    
    Returns:
        SafeToSpendResult
    
    Example:
        >>> result = calculate_safe_to_spend(projection_df, 30)
        >>> print(result.safe_to_spend_daily)
        44.0
    """
    calculator = SafeToSpendCalculator(safety_buffer_pct=safety_buffer_pct)
    return calculator.calculate(projection_df, horizon_days)