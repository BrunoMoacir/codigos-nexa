"""
app/etl/profiles.py - Análise de Perfil Financeiro do Usuário

RESPONSABILIDADE:
    Analisa padrões de gastos e cria perfil financeiro

PERFIS:
    - CONSERVADOR: Taxa poupança ≥ 20%
    - EQUILIBRADO: Taxa poupança 10-20%
    - GASTADOR: Taxa poupança < 10%

USAGE:
    analyzer = UserProfileAnalyzer()
    profile = analyzer.analyze(df)
    print(profile.profile_type)  # "EQUILIBRADO"
"""

import logging
import polars as pl
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TYPES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ProfileType = Literal["CONSERVADOR", "EQUILIBRADO", "GASTADOR"]
TrendType = Literal["CRESCENTE", "ESTÁVEL", "DECRESCENTE"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATACLASS: RESULTADO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class UserProfile:
    """
    Perfil financeiro do usuário.
    
    Attributes:
        profile_type: CONSERVADOR/EQUILIBRADO/GASTADOR
        total_income: Receita total do período
        total_expenses: Despesa total do período
        monthly_avg_expenses: Média mensal de gastos
        top_categories: Top 3 categorias de gasto
        savings_rate: Taxa de poupança (%)
        financial_health_score: Score 0-100
        trend: Tendência dos gastos
    
    Example:
        >>> profile = UserProfile(
        ...     profile_type="EQUILIBRADO",
        ...     total_income=5000.0,
        ...     total_expenses=3500.0,
        ...     monthly_avg_expenses=3500.0,
        ...     top_categories=["Alimentação", "Transporte"],
        ...     savings_rate=30.0,
        ...     financial_health_score=85,
        ...     trend="ESTÁVEL"
        ... )
    """
    
    profile_type: ProfileType
    total_income: float
    total_expenses: float
    monthly_avg_expenses: float
    top_categories: list[str]
    savings_rate: float
    financial_health_score: int
    trend: TrendType
    
    def to_dict(self) -> dict:
        """Converte para dict (útil para JSON)."""
        return {
            "profile_type": self.profile_type,
            "total_income": self.total_income,
            "total_expenses": self.total_expenses,
            "monthly_avg_expenses": self.monthly_avg_expenses,
            "top_categories": self.top_categories,
            "savings_rate": self.savings_rate,
            "financial_health_score": self.financial_health_score,
            "trend": self.trend
        }
"""
PARTE 2: Classe UserProfileAnalyzer
"""

class UserProfileAnalyzer:
    """
    Analisador de perfil financeiro.
    
    Recebe DataFrame com transações e calcula perfil completo.
    
    Example:
        >>> analyzer = UserProfileAnalyzer()
        >>> profile = analyzer.analyze(df)
        >>> print(profile.profile_type)
        'EQUILIBRADO'
    """
    
    def __init__(self):
        """Inicializa o analisador."""
        self.logger = logging.getLogger(__name__)
    
    def analyze(self, df: pl.DataFrame) -> UserProfile:
        """
        Analisa DataFrame e retorna perfil completo.
        
        Args:
            df: DataFrame com transações
                Colunas necessárias:
                - amount (float)
                - transaction_date (datetime)
                - predicted_category (str) - opcional
        
        Returns:
            UserProfile com todas as métricas calculadas
        
        Example:
            >>> df = pl.DataFrame({
            ...     "amount": [-100, -50, 200, -30],
            ...     "transaction_date": [...],
            ...     "predicted_category": ["Alimentação", "Transporte", ...]
            ... })
            >>> profile = analyzer.analyze(df)
        """
        # Validação: DataFrame vazio
        if df.is_empty():
            self.logger.warning("DataFrame vazio. Retornando perfil padrão.")
            return self._get_empty_profile()
        
        # Validação: Coluna amount obrigatória
        if "amount" not in df.columns:
            self.logger.error("Coluna 'amount' não encontrada no DataFrame")
            return self._get_empty_profile()
        
        self.logger.info(f"Analisando perfil com {df.height} transações")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # CALCULAR MÉTRICAS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # 1. Receitas e Despesas
        total_income = self._calculate_income(df)
        total_expenses = self._calculate_expenses(df)
        
        self.logger.debug(f"Receita: R$ {total_income:.2f}")
        self.logger.debug(f"Despesa: R$ {total_expenses:.2f}")
        
        # 2. Média mensal
        monthly_avg = self._calculate_monthly_avg(df, total_expenses)
        
        # 3. Top categorias
        top_categories = self._get_top_categories(df)
        
        # 4. Taxa de poupança
        savings_rate = self._calculate_savings_rate(total_income, total_expenses)
        
        # 5. Tendência
        trend = self._calculate_trend(df)
        
        # 6. Health score
        health_score = self._calculate_health_score(
            savings_rate, 
            total_expenses, 
            total_income
        )
        
        # 7. Tipo de perfil
        profile_type = self._determine_profile_type(savings_rate, total_expenses)
        
        self.logger.info(
            f"Perfil calculado: {profile_type} "
            f"(poupança: {savings_rate:.1f}%, score: {health_score})"
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # CRIAR PERFIL
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        return UserProfile(
            profile_type=profile_type,
            total_income=total_income,
            total_expenses=total_expenses,
            monthly_avg_expenses=monthly_avg,
            top_categories=top_categories,
            savings_rate=savings_rate,
            financial_health_score=health_score,
            trend=trend
        )
    """
    PARTE 3: Métodos de Cálculo (privados)
    """

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CÁLCULO 1: RECEITA
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _calculate_income(self, df: pl.DataFrame) -> float:
        """
        Calcula receita total (amount > 0).
        
        Args:
            df: DataFrame com coluna 'amount'
        
        Returns:
            Soma de todos os valores positivos
        """
        income_df = df.filter(pl.col("amount") > 0)
        total = income_df["amount"].sum()
        return float(total) if total is not None else 0.0
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CÁLCULO 2: DESPESA
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _calculate_expenses(self, df: pl.DataFrame) -> float:
        """
        Calcula despesa total (amount < 0).
        
        Args:
            df: DataFrame com coluna 'amount'
        
        Returns:
            Soma absoluta de todos os valores negativos
        """
        expenses_df = df.filter(pl.col("amount") < 0)
        total = expenses_df["amount"].sum()
        return float(abs(total)) if total is not None else 0.0
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CÁLCULO 3: MÉDIA MENSAL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _calculate_monthly_avg(
        self, 
        df: pl.DataFrame, 
        total_expenses: float
    ) -> float:
        """
        Calcula média mensal de gastos.
        
        Args:
            df: DataFrame com coluna 'transaction_date'
            total_expenses: Despesa total (já calculada)
        
        Returns:
            Total dividido pelo número de meses únicos
        """
        if "transaction_date" not in df.columns or df.height == 0:
            return 0.0
        
        # Contar meses únicos
        unique_months = df.select([
            pl.col("transaction_date").dt.month().alias("month"),
            pl.col("transaction_date").dt.year().alias("year")
        ]).unique().height
        
        if unique_months == 0:
            return total_expenses
        
        return total_expenses / unique_months
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CÁLCULO 4: TOP CATEGORIAS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _get_top_categories(self, df: pl.DataFrame, top_n: int = 3) -> list[str]:
        """
        Retorna top N categorias por volume de gasto.
        
        Args:
            df: DataFrame com colunas 'predicted_category' e 'amount'
            top_n: Quantas categorias retornar (padrão: 3)
        
        Returns:
            Lista com nomes das categorias ordenadas por gasto
        """
        # Validação: colunas necessárias
        if "predicted_category" not in df.columns or "amount" not in df.columns:
            return []
        
        # Agrupar por categoria (apenas despesas)
        category_totals = df.filter(pl.col("amount") < 0).group_by(
            "predicted_category"
        ).agg(
            pl.col("amount").abs().sum().alias("total")
        ).sort("total", descending=True).head(top_n)
        
        return category_totals["predicted_category"].to_list()
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CÁLCULO 5: TAXA DE POUPANÇA
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _calculate_savings_rate(self, income: float, expenses: float) -> float:
        """
        Calcula taxa de poupança (%).
        
        Fórmula: (Receita - Despesa) / Receita × 100
        
        Args:
            income: Receita total
            expenses: Despesa total
        
        Returns:
            Percentual de poupança (pode ser negativo se gastar mais que ganha)
        """
        if income == 0:
            return 0.0
        
        savings = income - expenses
        return (savings / income) * 100
    """
    PARTE 4: Cálculos Avançados
    """

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CÁLCULO 6: TENDÊNCIA
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _calculate_trend(self, df: pl.DataFrame) -> TrendType:
        """
        Calcula tendência de gastos (CRESCENTE/ESTÁVEL/DECRESCENTE).
        
        Compara média dos últimos 30 registros vs 30 registros anteriores.
        
        Args:
            df: DataFrame com colunas 'transaction_date' e 'amount'
        
        Returns:
            CRESCENTE: Gastos aumentando (>10%)
            DECRESCENTE: Gastos diminuindo (<-10%)
            ESTÁVEL: Variação entre -10% e +10%
        """
        # Validação
        if "transaction_date" not in df.columns or "amount" not in df.columns:
            return "ESTÁVEL"
        
        if df.height < 10:
            return "ESTÁVEL"  # Poucos dados
        
        # Ordenar por data (mais recente primeiro)
        df_sorted = df.sort("transaction_date", descending=True)
        
        # Últimos 30 registros (período recente)
        recent = df_sorted.head(30).filter(pl.col("amount") < 0)
        
        # 30 registros anteriores (período antigo)
        older = df_sorted.slice(30, 30).filter(pl.col("amount") < 0)
        
        # Validação: precisa ter dados nos dois períodos
        if recent.height == 0 or older.height == 0:
            return "ESTÁVEL"
        
        # Calcular médias
        recent_avg = float(abs(recent["amount"].mean() or 0))
        older_avg = float(abs(older["amount"].mean() or 0))
        
        # Comparar (threshold: 10%)
        if recent_avg > older_avg * 1.1:
            return "CRESCENTE"  # Gastos aumentaram >10%
        elif recent_avg < older_avg * 0.9:
            return "DECRESCENTE"  # Gastos diminuíram >10%
        else:
            return "ESTÁVEL"  # Variação < 10%
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CÁLCULO 7: HEALTH SCORE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _calculate_health_score(
        self,
        savings_rate: float,
        expenses: float,
        income: float
    ) -> int:
        """
        Calcula score de saúde financeira (0-100).
        
        Fatores:
            - Taxa de poupança (até 50 pontos)
            - Balanço positivo (até 30 pontos)
            - Proporção despesa/renda (até 20 pontos)
        
        Args:
            savings_rate: Taxa de poupança (%)
            expenses: Despesa total
            income: Receita total
        
        Returns:
            Score entre 0 e 100
        """
        score = 0
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # FATOR 1: Taxa de poupança (50 pontos)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if savings_rate >= 30:
            score += 50  # Excelente
        elif savings_rate >= 20:
            score += 40  # Muito bom
        elif savings_rate >= 10:
            score += 30  # Bom
        elif savings_rate >= 0:
            score += 20  # Regular
        # Se savings_rate < 0, não ganha pontos
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # FATOR 2: Renda > Despesas (30 pontos)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if income > expenses:
            score += 30  # Balanço positivo
        elif income == expenses:
            score += 15  # Neutro
        # Se income < expenses, não ganha pontos
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # FATOR 3: Proporção despesa/renda (20 pontos)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if income > 0:
            expense_ratio = expenses / income
            
            if expense_ratio < 0.5:
                score += 20  # Gasta <50% da renda
            elif expense_ratio < 0.7:
                score += 15  # Gasta 50-70%
            elif expense_ratio < 0.9:
                score += 10  # Gasta 70-90%
            # Se gasta >90%, não ganha pontos
        
        # Garantir que score não ultrapassa 100
        return min(score, 100)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CÁLCULO 8: TIPO DE PERFIL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _determine_profile_type(
        self,
        savings_rate: float,
        expenses: float
    ) -> ProfileType:
        """
        Determina tipo de perfil baseado na taxa de poupança.
        
        Critérios:
            - CONSERVADOR: Poupança ≥ 20%
            - EQUILIBRADO: Poupança 10-20%
            - GASTADOR: Poupança < 10%
        
        Args:
            savings_rate: Taxa de poupança (%)
            expenses: Despesa total (não usado atualmente)
        
        Returns:
            CONSERVADOR | EQUILIBRADO | GASTADOR
        """
        if savings_rate >= 20:
            return "CONSERVADOR"
        elif savings_rate >= 10:
            return "EQUILIBRADO"
        else:
            return "GASTADOR"
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HELPER: PERFIL VAZIO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _get_empty_profile(self) -> UserProfile:
        """
        Retorna perfil padrão para DataFrame vazio.
        
        Returns:
            UserProfile com valores zerados
        """
        return UserProfile(
            profile_type="EQUILIBRADO",
            total_income=0.0,
            total_expenses=0.0,
            monthly_avg_expenses=0.0,
            top_categories=[],
            savings_rate=0.0,
            financial_health_score=50,  # Neutro
            trend="ESTÁVEL"
        )