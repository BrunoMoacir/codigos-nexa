"""
app/cashflow/burn_rate.py - Analisador de Velocidade de Gasto (Burn Rate)

RESPONSABILIDADE:
    Detecta quando o usuário está gastando mais rápido do que o esperado,
    comparando o ritmo atual com a média histórica por categoria.

CONCEITO:
    Burn Rate Ratio = (% do budget gasto até hoje) / (% esperado linearmente)

    Exemplo: dia 15 de 30 → expected = 50%.
        Se já gastou 70% do budget → ratio = 1.4 → alerta WARNING.

INTEGRAÇÃO:
    CashflowEngine.analyze() inclui 'burn_rate' no resultado.
    O agente usa proativamente: "Cuidado com alimentação — ritmo 40% acima do normal."

USAGE:
    analyzer = BurnRateAnalyzer()
    report = analyzer.analyze(transactions_df)

    if report.alert_level != "OK":
        print(f"⚠️ {report.alert_level}: {report.burn_rate_ratio:.1f}x acima do esperado")
"""

import calendar
import logging
import polars as pl
from dataclasses import dataclass
from datetime import date
from typing import Literal

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONSTANTES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

AlertLevel = Literal["OK", "ATTENTION", "WARNING", "CRITICAL"]

# Alertas não são emitidos nos primeiros dias do mês: projeção linear
# com day=1 ou 2 produz ratio artificialmente alto para qualquer gasto.
_MIN_ALERT_DAY = 3

# Categoria alertada quando seu ritmo excede 20% acima do esperado
_CATEGORY_PACE_THRESHOLD = 1.20

# Thresholds do alerta geral (burn_rate_ratio)
_ATTENTION_RATIO = 1.10
_WARNING_RATIO   = 1.30
_CRITICAL_RATIO  = 1.50

# Thresholds de alerta baseados em projeção mensal como % da renda (MI.5)
# Projeção = (gasto_até_hoje / dia_atual) × dias_no_mês / renda_mensal
_INCOME_ATTENTION_RATIO = 0.75   # Projetado gastar 75% da renda → ATTENTION
_INCOME_WARNING_RATIO   = 0.90   # Projetado gastar 90% da renda → WARNING
_INCOME_CRITICAL_RATIO  = 1.00   # Projetado gastar ≥ 100% da renda → CRITICAL

# Ordem de severidade para escalar entre alertas
_ALERT_ORDER: dict[str, int] = {"OK": 0, "ATTENTION": 1, "WARNING": 2, "CRITICAL": 3}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATACLASSES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class CategoryBurnRate:
    """
    Burn rate de uma categoria com gasto acima do ritmo esperado.

    Attributes:
        category: Nome da categoria (ex: "alimentacao")
        spent_so_far: Total gasto no mês até hoje (R$)
        monthly_budget: Média histórica mensal — usado como orçamento implícito
        pct_consumed: % do budget já consumido (ex: 0.72 = 72%)
        projected_total: Extrapolação linear do gasto até o fim do mês
        overshoot: Quanto vai ultrapassar o budget (0.0 se dentro do limite)

    Example:
        >>> cat = CategoryBurnRate(
        ...     category="alimentacao",
        ...     spent_so_far=720.0,
        ...     monthly_budget=1000.0,
        ...     pct_consumed=0.72,
        ...     projected_total=1440.0,
        ...     overshoot=440.0,
        ... )
        >>> cat.overshoot
        440.0
    """
    category: str
    spent_so_far: float
    monthly_budget: float
    pct_consumed: float
    projected_total: float
    overshoot: float

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "spent_so_far": self.spent_so_far,
            "monthly_budget": self.monthly_budget,
            "pct_consumed": self.pct_consumed,
            "projected_total": self.projected_total,
            "overshoot": self.overshoot,
        }


@dataclass
class BurnRateReport:
    """
    Relatório de velocidade de gasto do mês corrente.

    Attributes:
        current_day: Dia atual do mês (ex: 15)
        days_in_month: Total de dias no mês (ex: 31)
        overall_burn_rate: % do budget histórico já gasto (ex: 0.72)
        expected_burn_rate: % esperado linearmente = day / days_in_month (ex: 0.48)
        burn_rate_ratio: overall / expected — >1.0 = acima do ritmo (ex: 1.5)
        total_spent_month: Total gasto no mês até hoje (R$)
        total_budget: Budget estimado = soma das médias históricas por categoria (R$)
        projected_overshoot: Quanto vai ultrapassar o budget total ao fim do mês (R$)
        categories_over_pace: Categorias com ritmo >20% acima do esperado
        alert_level: OK | ATTENTION | WARNING | CRITICAL
        income_monthly: Renda mensal do usuário (R$), se disponível via IncomeProfiler.
            Quando presente, permite interpretar gastos como % da renda real.
        income_ratio: total_spent_month / income_monthly. None se renda não disponível.
            Ex: 0.45 = o usuário gastou 45% da renda no mês até hoje.

    Example:
        >>> report.alert_level
        'WARNING'
        >>> report.income_ratio
        0.45   # 45% da renda gasta até o dia 15
    """
    current_day: int
    days_in_month: int
    overall_burn_rate: float
    expected_burn_rate: float
    burn_rate_ratio: float
    total_spent_month: float
    total_budget: float
    projected_overshoot: float
    categories_over_pace: list[CategoryBurnRate]
    alert_level: AlertLevel
    income_monthly: float = 0.0           # 0.0 quando renda não disponível
    income_ratio: float | None = None     # None quando renda não disponível

    def to_dict(self) -> dict:
        return {
            "current_day": self.current_day,
            "days_in_month": self.days_in_month,
            "overall_burn_rate": self.overall_burn_rate,
            "expected_burn_rate": self.expected_burn_rate,
            "burn_rate_ratio": self.burn_rate_ratio,
            "total_spent_month": self.total_spent_month,
            "total_budget": self.total_budget,
            "projected_overshoot": self.projected_overshoot,
            "categories_over_pace": [c.to_dict() for c in self.categories_over_pace],
            "alert_level": self.alert_level,
            "income_monthly": self.income_monthly,
            "income_ratio": self.income_ratio,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ANALYZER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _max_alert_level(a: AlertLevel, b: AlertLevel) -> AlertLevel:
    """Retorna o nível de alerta mais severo entre dois (MI.5)."""
    return a if _ALERT_ORDER.get(a, 0) >= _ALERT_ORDER.get(b, 0) else b


class BurnRateAnalyzer:
    """
    Analisa a velocidade de gasto do mês corrente vs. histórico.

    Fluxo:
        1. Separa transações do mês corrente vs. N meses anteriores (histórico)
        2. Calcula budget implícito por categoria = média mensal do histórico
        3. Compara ritmo atual com ritmo esperado linear
        4. Identifica categorias fora do ritmo (>20% acima) — vetorizado em Polars
        5. Projeta overshoot ao fim do mês

    Apenas despesas (amount < 0) são consideradas.

    Alertas são suprimidos nos primeiros _MIN_ALERT_DAY dias do mês — a projeção
    linear no dia 1 ou 2 é inerentemente instável e geraria falsos positivos.

    Args:
        history_months: Meses de histórico para calcular o budget implícito.
            Padrão: 3. Aumente para 6 em contextos com mais dados históricos.

    Example:
        >>> analyzer = BurnRateAnalyzer()
        >>> report = analyzer.analyze(transactions_df)
        >>>
        >>> if report.alert_level != "OK":
        ...     worst = report.categories_over_pace[0]
        ...     print(f"{worst.category}: vai ultrapassar R$ {worst.overshoot:.0f}")
        alimentacao: vai ultrapassar R$ 380
    """

    def __init__(self, history_months: int = 3):
        self.logger = logging.getLogger(__name__)
        self._history_months = history_months

    def analyze(
        self,
        transactions_df: pl.DataFrame,
        current_date: date | None = None,
        monthly_income: float | None = None,
    ) -> BurnRateReport:
        """
        Analisa burn rate do mês corrente.

        Args:
            transactions_df: DataFrame com transações do usuário.
                Colunas obrigatórias:
                    - transaction_date (Datetime ou Date)
                    - amount (Float) — negativos = despesa
                    - category (Str)
            current_date: Data de referência. Padrão: date.today().
            monthly_income: Renda mensal do usuário (R$), preferencialmente
                obtida via IncomeProfiler. Quando fornecida, o relatório inclui
                income_ratio = total_spent / income, contextualizando os gastos
                em relação à renda real (não apenas ao histórico de gastos).

        Returns:
            BurnRateReport com análise completa e alert_level.

        Example:
            >>> report = analyzer.analyze(df, current_date=date(2026, 3, 15), monthly_income=8500.0)
            >>> report.income_ratio
            0.38   # 38% da renda gasta até o dia 15
        """
        if current_date is None:
            current_date = date.today()

        if transactions_df.is_empty():
            return self._empty_report(current_date)

        required = {"transaction_date", "amount", "category"}
        missing = required - set(transactions_df.columns)
        if missing:
            self.logger.warning("Colunas faltando: %s. Retornando relatório vazio.", missing)
            return self._empty_report(current_date)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # PREPARAR DataFrame
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        df = transactions_df
        if df.schema.get("transaction_date") != pl.Datetime:
            df = df.with_columns(pl.col("transaction_date").cast(pl.Datetime))

        # Garantir que 'category' seja sempre String (evita SchemaError com DB vazio / null-typed)
        if "category" in df.columns and df.schema.get("category") == pl.Null:
            df = df.with_columns(pl.col("category").cast(pl.Utf8))


        # Coluna year-month como string para uso com is_in() — mais idiomático
        # e eficiente do que construir máscaras booleanas aninhadas via loop.
        df = df.with_columns([
            pl.col("transaction_date").dt.year().alias("_year"),
            pl.col("transaction_date").dt.month().alias("_month"),
            (
                pl.col("transaction_date").dt.year().cast(pl.Utf8)
                + "-"
                + pl.col("transaction_date").dt.month().cast(pl.Utf8)
            ).alias("_ym"),
        ])

        # Apenas despesas
        df_expenses = df.filter(pl.col("amount") < 0)
        if df_expenses.is_empty():
            return self._empty_report(current_date)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # VARIÁVEIS DO MÊS CORRENTE
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        year  = current_date.year
        month = current_date.month
        day   = current_date.day
        days_in_month      = calendar.monthrange(year, month)[1]
        expected_burn_rate = day / days_in_month

        current_ym = f"{year}-{month}"

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # GASTOS DO MÊS CORRENTE (por categoria)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        df_current = df_expenses.filter(pl.col("_ym") == current_ym)

        if df_current.is_empty():
            spent_by_category = pl.DataFrame(
                {"category": pl.Series([], dtype=pl.Utf8),
                 "spent":    pl.Series([], dtype=pl.Float64)}
            )
        else:
            spent_by_category = (
                df_current
                .group_by("category")
                .agg(pl.col("amount").abs().sum().alias("spent"))
            )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # BUDGET IMPLÍCITO — média dos últimos N meses (excluindo atual)
        # is_in() sobre coluna _ym: evita máscaras aninhadas via loop.
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        history_months = self._previous_months(year, month, self._history_months)
        history_ym_set = {f"{y}-{m}" for y, m in history_months}

        df_history = df_expenses.filter(pl.col("_ym").is_in(history_ym_set))

        if df_history.is_empty():
            # Sem histórico: usa gasto do mês corrente como budget de referência.
            # Ratio = overall / expected nunca diverge → sem alertas.
            budget_by_category = spent_by_category.rename({"spent": "budget"})
        else:
            budget_by_category = (
                df_history
                .group_by(["category", "_ym"])
                .agg(pl.col("amount").abs().sum().alias("monthly_total"))
                .group_by("category")
                .agg(pl.col("monthly_total").mean().alias("budget"))
            )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # MERGE E CÁLCULOS GLOBAIS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        merged = (
            budget_by_category
            .join(spent_by_category, on="category", how="left")
            .with_columns(pl.col("spent").fill_null(0.0))
        )

        total_budget = float(merged["budget"].sum())
        total_spent  = float(merged["spent"].sum())

        if total_budget == 0:
            return self._empty_report(current_date)

        overall_burn_rate = total_spent / total_budget
        burn_rate_ratio   = (
            overall_burn_rate / expected_burn_rate if expected_burn_rate > 0 else 0.0
        )

        projected_month_total = (total_spent / day) * days_in_month if day > 0 else total_spent
        projected_overshoot   = max(0.0, projected_month_total - total_budget)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # CATEGORIAS FORA DO RITMO — cálculo totalmente vetorizado
        # iter_rows só ocorre na coleta final do resultado filtrado,
        # mantendo a lógica pesada dentro do plano de query do Polars.
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        pct_consumed_expr = pl.col("spent") / pl.col("budget")
        cat_ratio_expr = (
            pct_consumed_expr / expected_burn_rate
            if expected_burn_rate > 0
            else pl.lit(0.0)
        )
        projected_expr = (
            pl.col("spent") / day * days_in_month if day > 0 else pl.col("spent")
        )

        cat_analysis = (
            merged
            .filter(pl.col("budget") > 0)
            .with_columns([
                pct_consumed_expr.alias("pct_consumed"),
                cat_ratio_expr.alias("cat_ratio"),
                projected_expr.alias("projected_cat"),
            ])
            .with_columns([
                (pl.col("projected_cat") - pl.col("budget"))
                .clip(lower_bound=0.0)
                .alias("overshoot")
            ])
            .filter(pl.col("cat_ratio") >= _CATEGORY_PACE_THRESHOLD)
            .sort("overshoot", descending=True)  # pior primeiro, dentro do Polars
        )

        categories_over_pace: list[CategoryBurnRate] = [
            CategoryBurnRate(
                category=row["category"],
                spent_so_far=round(row["spent"], 2),
                monthly_budget=round(row["budget"], 2),
                pct_consumed=round(row["pct_consumed"], 3),
                projected_total=round(row["projected_cat"], 2),
                overshoot=round(row["overshoot"], 2),
            )
            for row in cat_analysis.iter_rows(named=True)
        ]

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ALERT LEVEL
        # Suprimido nos primeiros _MIN_ALERT_DAY dias: projeção linear
        # com day=1 ou 2 gera ratio instável para qualquer gasto não-zero.
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        if day < _MIN_ALERT_DAY:
            alert_level: AlertLevel = "OK"
        else:
            alert_level = self._classify_alert(burn_rate_ratio)

        income_ratio = (
            round(total_spent / monthly_income, 4)
            if monthly_income and monthly_income > 0
            else None
        )

        # MI.5 — escalada de alerta por % da renda real
        # Quando a renda mensal está disponível, calcula a projeção de gasto do
        # mês inteiro como % da renda. Permite detectar situações em que o usuário
        # gasta dentro do padrão histórico (burn_rate_ratio OK), mas está a caminho
        # de comprometer a maior parte da renda do mês.
        if monthly_income and monthly_income > 0 and day >= _MIN_ALERT_DAY:
            projected_month_total = (total_spent / day * days_in_month) if day > 0 else total_spent
            projected_income_ratio = projected_month_total / monthly_income
            income_alert = self._classify_income_alert(projected_income_ratio)
            alert_level = _max_alert_level(alert_level, income_alert)

        self.logger.info(
            f"Burn rate: {overall_burn_rate:.1%} gasto vs {expected_burn_rate:.1%} esperado "
            f"(ratio {burn_rate_ratio:.2f}) → {alert_level} | "
            f"{len(categories_over_pace)} categoria(s) fora do ritmo"
            + (f" | income_ratio={income_ratio:.1%}" if income_ratio is not None else "")
        )

        return BurnRateReport(
            current_day=day,
            days_in_month=days_in_month,
            overall_burn_rate=round(overall_burn_rate, 3),
            expected_burn_rate=round(expected_burn_rate, 3),
            burn_rate_ratio=round(burn_rate_ratio, 2),
            total_spent_month=round(total_spent, 2),
            total_budget=round(total_budget, 2),
            projected_overshoot=round(projected_overshoot, 2),
            categories_over_pace=categories_over_pace,
            alert_level=alert_level,
            income_monthly=round(monthly_income, 2) if monthly_income else 0.0,
            income_ratio=income_ratio,
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PRIVATE HELPERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _previous_months(year: int, month: int, n: int) -> list[tuple[int, int]]:
        """Retorna os N meses anteriores a (year, month) como lista de (ano, mês)."""
        result = []
        y, m = year, month
        for _ in range(n):
            m -= 1
            if m == 0:
                m = 12
                y -= 1
            result.append((y, m))
        return result

    def _classify_alert(self, burn_rate_ratio: float) -> AlertLevel:
        """
        Classifica nível de alerta pelo burn_rate_ratio.

        OK:        ratio < 1.10  — dentro do ritmo normal
        ATTENTION: 1.10 ≤ ratio < 1.30  — levemente acelerado
        WARNING:   1.30 ≤ ratio < 1.50  — claramente fora do ritmo
        CRITICAL:  ratio ≥ 1.50  — gasto muito acelerado
        """
        if burn_rate_ratio >= _CRITICAL_RATIO:
            return "CRITICAL"
        elif burn_rate_ratio >= _WARNING_RATIO:
            return "WARNING"
        elif burn_rate_ratio >= _ATTENTION_RATIO:
            return "ATTENTION"
        else:
            return "OK"

    @staticmethod
    def _classify_income_alert(projected_income_ratio: float) -> AlertLevel:
        """
        Classifica alerta com base na projeção de gasto mensal vs renda (MI.5).

        projected_income_ratio = (gasto_até_hoje / dia_atual × dias_no_mês) / renda_mensal

        OK:        projetado < 75% da renda
        ATTENTION: 75–90% da renda
        WARNING:   90–100% da renda
        CRITICAL:  ≥ 100% da renda — vai gastar mais do que ganha no mês
        """
        if projected_income_ratio >= _INCOME_CRITICAL_RATIO:
            return "CRITICAL"
        elif projected_income_ratio >= _INCOME_WARNING_RATIO:
            return "WARNING"
        elif projected_income_ratio >= _INCOME_ATTENTION_RATIO:
            return "ATTENTION"
        else:
            return "OK"

    def _empty_report(self, current_date: date) -> BurnRateReport:
        """Retorna relatório neutro quando não há dados suficientes."""
        days_in_month = calendar.monthrange(current_date.year, current_date.month)[1]
        return BurnRateReport(
            current_day=current_date.day,
            days_in_month=days_in_month,
            overall_burn_rate=0.0,
            expected_burn_rate=round(current_date.day / days_in_month, 3),
            burn_rate_ratio=0.0,
            total_spent_month=0.0,
            total_budget=0.0,
            projected_overshoot=0.0,
            categories_over_pace=[],
            alert_level="OK",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER FUNCTION (Convenience)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def analyze_burn_rate(
    transactions_df: pl.DataFrame,
    current_date: date | None = None,
    monthly_income: float | None = None,
) -> BurnRateReport:
    """
    Helper para uso direto sem instanciar BurnRateAnalyzer.

    Example:
        >>> from app.forecast.cashflow.burn_rate import analyze_burn_rate
        >>> report = analyze_burn_rate(df, monthly_income=5000.0)
        >>> report.alert_level
        'OK'
    """
    return BurnRateAnalyzer().analyze(transactions_df, current_date, monthly_income)


__all__ = [
    "BurnRateAnalyzer",
    "BurnRateReport",
    "CategoryBurnRate",
    "AlertLevel",
    "analyze_burn_rate",
]
