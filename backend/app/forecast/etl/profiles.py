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

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Optional

import polars as pl

if TYPE_CHECKING:
    from app.forecast.etl.income_profiler import IncomeProfile

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TYPES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ProfileType = Literal["CONSERVADOR", "EQUILIBRADO", "GASTADOR"]
TrendType = Literal["CRESCENTE", "ESTÁVEL", "DECRESCENTE"]

# Sub-classificação comportamental — 5 tiers que cortam transversalmente os 3 perfis
# Combina savings_rate + trend para granularidade maior que apenas GASTADOR/EQUILIBRADO.
#
#   CRITICO:      deficit (savings < 0) ou 0–5% com gastos crescendo → situação urgente
#   RISCO:        0–5% estável ou 5–15% crescendo → alerta, sem margem de erro
#   MODERADO:     5–15% estável → comportamento mediano, melhorável
#   BOAS_PRATICAS: 15–25% estável ou decrescendo → disciplina financeira sólida
#   SOLIDO:       ≥ 25% com tendência não-crescente → excelente saúde financeira
BehaviorTier = Literal["CRITICO", "RISCO", "MODERADO", "BOAS_PRATICAS", "SOLIDO"]


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
    # Renda mensal líquida usada para os ratios (filtrada via IncomeProfiler).
    # None quando IncomeProfile não foi fornecido ou confidence < 0.5 —
    # nesse caso savings_rate e health_score foram calculados com total_income bruto.
    income_net_monthly: Optional[float] = field(default=None)

    # ── Campos enriquecidos (v2) ──────────────────────────────────────────────
    # Todos opcionais com defaults para manter retrocompatibilidade.

    # Sub-classificação comportamental (5 tiers) — mais granular que profile_type.
    # Combina savings_rate + trend. Usar em profile_context e architect.
    behavior_tier: BehaviorTier = field(default="MODERADO")

    # Score de resiliência financeira (0–100) — substitui financial_health_score
    # como métrica de saúde quando disponível (inclui trend, committed_pct,
    # income_stability — vs os 3 fatores do financial_health_score original).
    # financial_health_score mantido para retrocompatibilidade (banco de dados).
    resilience_score: int = field(default=0)

    # Perfil de risco inferido automaticamente das transações: conservador/moderado/agressivo.
    # Usado pelo Architect (F3) em vez do mapeamento manual GASTADOR→MODERADO.
    # "agressivo" só é atribuído quando savings ≥ 25% + resilience ≥ 70 + estável.
    risk_appetite_inferred: str = field(default="moderado")

    def to_dict(self) -> dict:
        """Converte para dict (útil para JSON)."""
        d = {
            "profile_type": self.profile_type,
            "total_income": self.total_income,
            "total_expenses": self.total_expenses,
            "monthly_avg_expenses": self.monthly_avg_expenses,
            "top_categories": self.top_categories,
            "savings_rate": self.savings_rate,
            "financial_health_score": self.financial_health_score,
            "trend": self.trend,
            "behavior_tier": self.behavior_tier,
            "resilience_score": self.resilience_score,
            "risk_appetite_inferred": self.risk_appetite_inferred,
        }
        if self.income_net_monthly is not None:
            d["income_net_monthly"] = self.income_net_monthly
        return d


# ── PARTE 2: Classe UserProfileAnalyzer ──────────────────────────────────────

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
    
    def analyze(
        self,
        df: pl.DataFrame,
        income_profile: Optional["IncomeProfile"] = None,
        committed_pct: float = 0.0,
    ) -> UserProfile:
        """
        Analisa DataFrame e retorna perfil completo.

        Args:
            df: DataFrame com transações.
                Colunas necessárias: amount (float), transaction_date (datetime).
                Coluna opcional: predicted_category (str).
            income_profile: IncomeProfile do IncomeProfiler (opcional).
                Se fornecido e confidence ≥ 0.5, usa monthly_net_income como
                referência de renda para savings_rate e health_score, eliminando
                a inflação causada por transferências e estornos.
                Quando None ou confidence < 0.5, usa a soma bruta de créditos.
            committed_pct: Percentual da renda comprometida com obrigações fixas
                (parcelas + assinaturas), vindo do ConsumptionProfiler. Usado no
                resilience_score. Default 0.0 (sem dados).

        Returns:
            UserProfile com todas as métricas calculadas.

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

        self.logger.info("Analisando perfil com %s transações", df.height)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # CALCULAR MÉTRICAS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # 1. Receitas e Despesas
        total_income = self._calculate_income(df)
        total_expenses = self._calculate_expenses(df)

        self.logger.debug("Receita bruta: R$ %.2f", total_income)
        self.logger.debug("Despesa: R$ %.2f", total_expenses)

        # 2. Renda de referência para ratios (filtrada vs bruta)
        income_for_ratios, income_net_monthly = self._resolve_income_reference(
            df, total_income, income_profile
        )

        # 3. Média mensal
        monthly_avg = self._calculate_monthly_avg(df, total_expenses)

        # 4. Top categorias
        top_categories = self._get_top_categories(df)

        # 5. Taxa de poupança (usando renda de referência)
        savings_rate = self._calculate_savings_rate(income_for_ratios, total_expenses)

        # 6. Tendência
        trend = self._calculate_trend(df)

        # 7. Health score (usando renda de referência)
        health_score = self._calculate_health_score(
            savings_rate,
            total_expenses,
            income_for_ratios,
        )

        # 8. Tipo de perfil
        profile_type = self._determine_profile_type(savings_rate)

        # ── v2: campos enriquecidos ──────────────────────────────────

        # 9. Behavior tier — 5 níveis combinando savings_rate + trend
        behavior_tier = self._calculate_behavior_tier(savings_rate, trend)

        # 10. Resilience score — 6 fatores (vs 3 do financial_health_score)
        resilience_score = self._calculate_resilience_score(
            savings_rate=savings_rate,
            income=income_for_ratios,
            expenses=total_expenses,
            trend=trend,
            committed_pct=committed_pct,
            income_profile=income_profile,
        )

        # 11. Risk appetite inferido — conservador/moderado/agressivo
        risk_appetite_inferred = self._infer_risk_appetite(
            behavior_tier=behavior_tier,
            resilience_score=resilience_score,
            trend=trend,
        )

        self.logger.info(
            f"Perfil calculado: {profile_type} | tier={behavior_tier} | "
            f"savings={savings_rate:.1f}% | health={health_score} | "
            f"resilience={resilience_score} | risk={risk_appetite_inferred} | "
            f"renda_ref={'filtrada' if income_net_monthly else 'bruta'}"
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
            trend=trend,
            income_net_monthly=income_net_monthly,
            behavior_tier=behavior_tier,
            resilience_score=resilience_score,
            risk_appetite_inferred=risk_appetite_inferred,
        )

    # ── PARTE 3: Métodos de Cálculo (privados) ───────────────────────────────

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # RENDA DE REFERÊNCIA
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _resolve_income_reference(
        self,
        df: pl.DataFrame,
        total_income_raw: float,
        income_profile: Optional["IncomeProfile"],
    ) -> tuple[float, Optional[float]]:
        """
        Retorna a renda de referência para ratios e savings_rate.

        Hierarquia:
            1. income_profile.monthly_net_income × n_meses (se confidence ≥ 0.5)
            2. total_income_raw (soma bruta — fallback)

        Returns:
            (income_for_ratios, income_net_monthly)
            income_net_monthly: valor mensal filtrado se usado, None se fallback bruto.
        """
        _CONFIDENCE_THRESHOLD = 0.5

        if (
            income_profile is not None
            and income_profile.confidence >= _CONFIDENCE_THRESHOLD
            and income_profile.monthly_net_income > 0
        ):
            n_months = self._count_months(df)
            period_net = income_profile.monthly_net_income * max(n_months, 1)
            self.logger.debug(
                f"Usando renda filtrada: R$ {income_profile.monthly_net_income:.0f}/mês "
                f"× {n_months}m = R$ {period_net:.0f} "
                f"(conf={income_profile.confidence:.2f}, padrão={income_profile.income_pattern})"
            )
            return period_net, income_profile.monthly_net_income

        return total_income_raw, None

    def _count_months(self, df: pl.DataFrame) -> int:
        """Conta meses distintos no DataFrame (usando transaction_date ou date)."""
        col = next(
            (c for c in ("transaction_date", "date") if c in df.columns), None
        )
        if col is None:
            return 1
        return (
            df.select(
                (pl.col(col).dt.year() * 100 + pl.col(col).dt.month()).alias("ym")
            )
            .unique()
            .height
        ) or 1

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

    # ── PARTE 4: Cálculos Avançados ──────────────────────────────────────────

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CÁLCULO 6: TENDÊNCIA
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _calculate_trend(self, df: pl.DataFrame) -> TrendType:
        """
        Calcula tendência de gastos (CRESCENTE/ESTÁVEL/DECRESCENTE).

        Compara o total de despesas do mês mais recente contra a média dos
        meses anteriores. Requer ao menos 2 meses distintos de dados.

        Args:
            df: DataFrame com colunas 'transaction_date' e 'amount'.

        Returns:
            CRESCENTE: Mês atual gasta >10% acima da média histórica.
            DECRESCENTE: Mês atual gasta >10% abaixo da média histórica.
            ESTÁVEL: Variação dentro de ±10%.
        """
        col = next(
            (c for c in ("transaction_date", "date") if c in df.columns), None
        )
        if col is None or "amount" not in df.columns:
            return "ESTÁVEL"

        expenses = df.filter(pl.col("amount") < 0)
        if expenses.is_empty():
            return "ESTÁVEL"

        # Total de despesas por mês (ym = ano×100 + mês → ordenação natural)
        monthly = (
            expenses
            .with_columns(
                (pl.col(col).dt.year() * 100 + pl.col(col).dt.month()).alias("ym")
            )
            .group_by("ym")
            .agg(pl.col("amount").sum().abs().alias("total"))
            .sort("ym")
        )

        if monthly.height < 2:
            return "ESTÁVEL"  # dados de apenas 1 mês — tendência indefinida

        # Mês mais recente vs média dos meses anteriores
        recent_total = float(monthly[-1]["total"][0])
        older_avg    = float(monthly[:-1]["total"].mean() or 0)

        if older_avg == 0:
            return "ESTÁVEL"

        if recent_total > older_avg * 1.1:
            return "CRESCENTE"
        elif recent_total < older_avg * 0.9:
            return "DECRESCENTE"
        else:
            return "ESTÁVEL"
    
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
        if savings_rate >= 25:
            score += 50
        elif savings_rate >= 15:
            score += 45
        elif savings_rate >= 10:
            score += 40
        elif savings_rate >= 5:
            score += 30
        elif savings_rate >= 0:
            score += 20
        # Se savings_rate < 0, não ganha pontos
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # FATOR 2: Renda > Despesas (30 pontos)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if income > expenses:
            score += 30  # Balanço positivo
        elif abs(income - expenses) / max(income, 1) < 0.02:
            score += 20  # praticamente neutro
        elif income >= expenses * 0.95:
            score += 10  # quase equilibrado
        # Se income < expenses, não ganha pontos
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # FATOR 3: Proporção despesa/renda (20 pontos)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if income > 0:
            expense_ratio = expenses / income
            
            if expense_ratio < 0.6:
                score += 20  # Gasta <60% da renda
            elif expense_ratio < 0.75:
                score += 15  # Gasta 60-75%
            elif expense_ratio < 0.85:
                score += 10  # Gasta 75-85%
            elif expense_ratio < 0.95:
                score += 7   # Gasta 85-95%
            elif expense_ratio < 1.0:
                score += 5   # Gasta 95-100%
            # Se gasta ≥100% da renda, não ganha pontos
        
        # Garantir que score não ultrapassa 100
        return min(100,max(0,score))
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CÁLCULO 8: TIPO DE PERFIL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _determine_profile_type(self, savings_rate: float) -> ProfileType:
        """
        Determina tipo de perfil baseado na taxa de poupança.

        Critérios:
            - CONSERVADOR: Poupança ≥ 20%
            - EQUILIBRADO: Poupança 10-20%
            - GASTADOR: Poupança < 10%

        Args:
            savings_rate: Taxa de poupança (%).

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
    # CÁLCULO 9: BEHAVIOR TIER (v2)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _calculate_behavior_tier(savings_rate: float, trend: TrendType) -> BehaviorTier:
        """
        Sub-classifica o comportamento financeiro em 5 tiers.

        Combina savings_rate (magnitude do problema) com trend (direção),
        resultando em granularidade maior que GASTADOR/EQUILIBRADO/CONSERVADOR.

        Tier matrix:
          savings < 0            → CRITICO  (gastando mais do que ganha)
          0–5% + crescente       → CRITICO  (déficit iminente)
          0–5% + estável/queda   → RISCO    (sem margem de segurança)
          5–15% + crescente      → RISCO    (deterioração em curso)
          5–15% + estável/queda  → MODERADO (mediano, melhorável)
          15–25% + crescente     → MODERADO (boa poupança mas tendência ruim)
          15–25% + estável/queda → BOAS_PRATICAS
          ≥ 25%                  → SOLIDO
        """
        if savings_rate < 0:
            return "CRITICO"
        if savings_rate < 5:
            return "CRITICO" if trend == "CRESCENTE" else "RISCO"
        if savings_rate < 15:
            return "RISCO" if trend == "CRESCENTE" else "MODERADO"
        if savings_rate < 25:
            return "MODERADO" if trend == "CRESCENTE" else "BOAS_PRATICAS"
        return "SOLIDO"

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CÁLCULO 10: RESILIENCE SCORE (v2)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _calculate_resilience_score(
        savings_rate: float,
        income: float,
        expenses: float,
        trend: TrendType,
        committed_pct: float = 0.0,
        income_profile: Optional["IncomeProfile"] = None,
    ) -> int:
        """
        Score de resiliência financeira (0–100) com 6 fatores.

        Mais abrangente que financial_health_score (3 fatores):
          1. Taxa de poupança       (25 pts) — capacidade de acumulação
          2. Equilíbrio renda/gasto (20 pts) — balanço do período
          3. Proporção gasto/renda  (15 pts) — margem de segurança
          4. Tendência dos gastos   (20 pts) — direção (CRESCENTE penaliza fortemente)
          5. Obrigações comprometidas (10 pts) — liberdade de manobra futura
          6. Estabilidade da renda  (10 pts) — predictibilidade do fluxo de entrada

        financial_health_score mantido para retrocompatibilidade com banco de dados.
        Este score substitui health_score como entrada no pressure_score.
        """
        score = 0

        # ── Fator 1: Taxa de poupança (25 pts) ───────────────────────
        if savings_rate >= 20:
            score += 25
        elif savings_rate >= 10:
            score += 20
        elif savings_rate >= 5:
            score += 12
        elif savings_rate >= 0:
            score += 5
        # < 0 → 0 pts (deficit)

        # ── Fator 2: Equilíbrio renda/gasto (20 pts) ─────────────────
        if income > 0 and expenses > 0:
            if income >= expenses * 1.05:
                score += 20  # renda cobre gastos com folga ≥ 5%
            elif income >= expenses:
                score += 15  # balanço positivo
            elif abs(income - expenses) / income < 0.02:
                score += 8   # quase neutro (±2%)
            elif income >= expenses * 0.95:
                score += 3   # leve deficit

        # ── Fator 3: Proporção despesa/renda (15 pts) ────────────────
        if income > 0:
            ratio = expenses / income
            if ratio < 0.60:
                score += 15
            elif ratio < 0.75:
                score += 12
            elif ratio < 0.85:
                score += 8
            elif ratio < 0.95:
                score += 4
            # ≥ 0.95 ou > renda → 0 pts

        # ── Fator 4: Tendência dos gastos (20 pts) ───────────────────
        if trend == "DECRESCENTE":
            score += 20   # melhorando — bonus máximo
        elif trend == "ESTÁVEL":
            score += 15   # estável — sólido
        # CRESCENTE → 0 pts (gastos crescendo = piora iminente)

        # ── Fator 5: Obrigações comprometidas (10 pts) ────────────────
        # committed_pct: % do gasto mensal já comprometido com parcelas/assinaturas
        if committed_pct < 0.30:
            score += 10
        elif committed_pct < 0.50:
            score += 7
        elif committed_pct < 0.70:
            score += 4
        elif committed_pct < 0.90:
            score += 1
        # ≥ 0.90 → 0 pts (quase tudo comprometido)

        # ── Fator 6: Estabilidade da renda (10 pts) ───────────────────
        # Usa income_profile.income_stability (0.0–1.0) se disponível.
        # CLT fixo → ~0.9 | PJ variável → ~0.3 | UNKNOWN → 0.5 (neutro)
        if income_profile is not None and income_profile.confidence >= 0.4:
            stability = income_profile.income_stability
        else:
            stability = 0.5  # neutro sem dados
        score += round(stability * 10)

        return min(100, max(0, score))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CÁLCULO 11: RISK APPETITE INFERIDO (v2)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _infer_risk_appetite(
        behavior_tier: BehaviorTier,
        resilience_score: int,
        trend: TrendType,
    ) -> str:
        """
        Infere o apetite a risco (conservador/moderado/agressivo) das transações.

        Substitui o mapeamento manual do ArchitectService:
          CONSERVADOR → CONSERVADOR
          EQUILIBRADO → MODERADO
          GASTADOR    → MODERADO  ← lossy: GASTADOR com -30% = GASTADOR com 9%

        Nova lógica multi-dimensional:
          agressivo:   SOLIDO + resilience ≥ 70 + tendência não-crescente
                       (usuário tem ampla margem, histórico robusto, sem deterioração)
          conservador: CRITICO ou RISCO, ou resilience < 35
                       (usuário em situação de pressão — não deve assumir riscos)
          moderado:    todo o resto (BOAS_PRATICAS sem qualidade agressiva, ou MODERADO)

        Nota: "agressivo" só é atribuído automaticamente quando há evidência forte.
        O usuário sempre pode declarar um perfil diferente na request.
        """
        # Pré-condições para agressivo: situação excelente em todos os eixos
        if (
            behavior_tier == "SOLIDO"
            and resilience_score >= 70
            and trend != "CRESCENTE"
        ):
            return "agressivo"

        # Pré-condições para conservador: situação de pressão ou fragilidade
        if behavior_tier in ("CRITICO", "RISCO") or resilience_score < 35:
            return "conservador"

        return "moderado"

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
            financial_health_score=0,
            trend="ESTÁVEL",
            behavior_tier="MODERADO",
            resilience_score=0,
            risk_appetite_inferred="moderado",
        )