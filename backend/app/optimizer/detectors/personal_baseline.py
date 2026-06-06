"""
PersonalBaseline — baseline de gasto pessoal por categoria.

Substitui thresholds fixos nos detectores por comparação contra o
próprio histórico do usuário (janela 90–540 dias antes do período recente).

Exemplo:
    Farmácia baseline: R$80/mês  →  comportamento normal
    Farmácia recente:  R$650/mês →  deviation_ratio = 8.1×  →  evento de saúde

Uso nos detectores (via adjusted_threshold):
    threshold = baseline.adjusted_threshold('educacao', default=200.0)
    # Baseline R$0    → 100.0  (novo comportamento: gate reduzido a 50%)
    # Baseline R$150  → 225.0  (hábito moderado: gate proporcional ao histórico)
    # Baseline R$400  → 600.0  (já estabelecido: precisa spike maior para disparar)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import polars as pl


@dataclass(frozen=True)
class PersonalBaseline:
    """Baseline de gasto pessoal mensal por categoria, derivado do histórico pré-recente."""

    category_monthly_avg: dict[str, float]
    total_monthly_avg: float
    data_months: int

    def monthly_avg(self, category: str) -> float:
        """Gasto médio mensal na categoria. 0.0 se sem histórico."""
        return self.category_monthly_avg.get(category, 0.0)

    def deviation_ratio(self, category: str, recent_monthly: float) -> float:
        """
        Razão gasto_recente / baseline_mensal.

        Returns:
            float: razão (1.0 = inalterado, 3.0 = triplo do normal).
            inf:   sem histórico na categoria — qualquer gasto é comportamento novo.
        """
        baseline = self.monthly_avg(category)
        if baseline <= 0:
            return float("inf")
        return recent_monthly / baseline

    def adjusted_threshold(
        self,
        category: str,
        default: float,
        spike_ratio: float = 1.5,
        floor_ratio: float = 0.5,
    ) -> float:
        """
        Threshold adaptado ao histórico do usuário na categoria.

        Sem histórico na categoria: gate reduzido (comportamento novo = sinal mais forte).
        Com histórico estabelecido: gate proporcional ao baseline + spike_ratio para evitar
        falso positivo em comportamentos já habituais.

        Args:
            category:    chave em category_monthly_avg (ex: "educacao", "farmacia").
            default:     threshold mensal de referência (em R$/mês).
            spike_ratio: múltiplo do baseline necessário para disparar (default 1.5×).
            floor_ratio: fração mínima do default quando sem histórico (default 0.5).

        Returns:
            Threshold em R$/mês adaptado ao perfil do usuário.

        Exemplos com default=100:
            baseline=0   → 100 × 0.5 = 50    (novo sinal: gate reduzido)
            baseline=80  → max(80×1.5, 50) = 120  (hábito moderado)
            baseline=300 → max(300×1.5, 50) = 450  (já estabelecido: spike necessário)
        """
        baseline = self.monthly_avg(category)
        if baseline <= 0:
            return default * floor_ratio
        return max(baseline * spike_ratio, default * floor_ratio)

    def has_data(self) -> bool:
        """True quando há ao menos 2 meses de histórico para baseline confiável."""
        return self.data_months >= 2


def compute_personal_baseline(
    df: pl.DataFrame,
    reference_date: date | None = None,
    window_days: int = 540,
    recent_days: int = 90,
) -> PersonalBaseline:
    """
    Computa baseline pessoal a partir do histórico pré-janela-recente.

    Usa [reference_date − window_days, reference_date − recent_days) para excluir
    o período atual dos detectores e evitar que o comportamento em análise contamine
    o próprio baseline de comparação.

    Args:
        df:             DataFrame completo de transações (histórico + recente).
                        Deve conter colunas: date, amount.
                        Usa category_canonical quando disponível; fallback para category.
        reference_date: data de referência (default = hoje).
        window_days:    janela histórica máxima em dias (default 540 ≈ 18 meses).
        recent_days:    dias recentes excluídos do baseline (default 90 = janela do profiler).

    Returns:
        PersonalBaseline com category_monthly_avg em R$/mês.
        Retorna PersonalBaseline vazio (data_months=0) quando sem histórico suficiente.
    """
    _empty = PersonalBaseline(category_monthly_avg={}, total_monthly_avg=0.0, data_months=0)

    if df is None or df.is_empty() or "date" not in df.columns:
        return _empty

    ref = reference_date or date.today()
    cutoff_start = ref - timedelta(days=window_days)
    cutoff_end = ref - timedelta(days=recent_days)

    if df["date"].dtype != pl.Date:
        df = df.with_columns(pl.col("date").cast(pl.Date))

    hist = df.filter(
        (pl.col("date") >= cutoff_start)
        & (pl.col("date") < cutoff_end)
        & (pl.col("amount") < 0)
    )

    if "context_type" in hist.columns:
        hist = hist.filter(
            pl.col("context_type").is_null() | (pl.col("context_type") != "PJ")
        )

    if hist.is_empty():
        return _empty

    data_months = (
        hist.with_columns(
            (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
        )
        .select("ym")
        .unique()
        .height
    )

    if data_months == 0:
        return _empty

    total_monthly_avg = float(hist["amount"].sum()) * -1 / data_months

    cat_col = "category_canonical" if "category_canonical" in hist.columns else "category"
    category_monthly_avg: dict[str, float] = {}

    if cat_col in hist.columns:
        cat_avgs = (
            hist.group_by(cat_col)
            .agg(pl.col("amount").sum().abs().alias("total"))
            .with_columns((pl.col("total") / data_months).alias("monthly_avg"))
        )
        category_monthly_avg = {
            row[cat_col]: round(row["monthly_avg"], 2)
            for row in cat_avgs.to_dicts()
            if row[cat_col] is not None
        }

    return PersonalBaseline(
        category_monthly_avg=category_monthly_avg,
        total_monthly_avg=round(total_monthly_avg, 2),
        data_months=data_months,
    )
