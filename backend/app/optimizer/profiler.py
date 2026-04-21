# app/optimizer/profiler.py
# ConsumptionProfiler — analisa transações reais e monta perfil de consumo
# Passo 2.2 — Funcionalidade 2: Nexa Optimizer

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

import polars as pl

from app.forecast.etl.income_profiler import IncomeProfile, IncomeProfiler

# TODO: migrar para structlog (dependência já declarada em pyproject.toml)
# quando o projeto configurar o handler global, substituir por:
#   import structlog; logger = structlog.get_logger(__name__)
logger = logging.getLogger(__name__)

# Janela de análise: últimos 90 dias
_WINDOW_DAYS = 90

# Categorias consideradas "viagem" para travel_spend_monthly
_TRAVEL_CATEGORIES = {"Lazer", "Transporte"}

# Padrões regex que indicam gasto internacional.
# Palavras ambíguas usam word boundaries (\b) para evitar falsos positivos:
#   \biof\b  → não captura "biofarmácia"
#   \beuro\b → não captura "europeu"
_INTERNATIONAL_PATTERN = (
    r"usd|eur\b|gbp|dollar|dolar|\beuro\b|\biof\b"
    r"|exterior|internacional|international|foreign|abroad"
)


@dataclass
class UserProfile:
    """Perfil de consumo do usuário derivado das transações reais dos últimos 90 dias."""

    monthly_avg_spend: float = 0.0
    committed_percentage: float = 0.0
    spend_by_category: dict = field(default_factory=dict)
    spend_by_source: dict = field(default_factory=dict)
    international_spend_monthly: float = 0.0
    travel_spend_monthly: float = 0.0
    estimated_monthly_income: float = 0.0   # legado: soma bruta de créditos
    data_coverage_months: int = 0
    spending_stability: float = 0.0
    # CV puro (std/mean) — usado pelo ConfidenceScorer com thresholds por faixa (v2.1)
    # ≤ 0.15 → sem penalidade; 0.15–0.35 → ×0.90; 0.35–0.60 → ×0.75; > 0.60 → ×0.60
    spend_stability_cv: float = 0.0
    income_profile: Optional[IncomeProfile] = None  # renda filtrada e classificada (M1.x)
    # Fração do gasto total que já transita por crédito (0.0–1.0).
    # Floor de 0.5: usuários 100% débito transfeririam ao menos metade para um novo cartão.
    credit_spend_ratio: float = 1.0


class ConsumptionProfiler:
    """
    Analisa o histórico de transações (F1) e monta o UserProfile.

    Regras principais:
    - Usa os últimos 90 dias de transactions_clean
    - Exclui transações context_type == "PJ" do consumo pessoal
    - Considera shadow_invoice_events para committed_percentage
    - data_coverage_months < 2 sinaliza dados insuficientes (penaliza confidence nos cartões)
    """

    def build(
        self,
        transactions_df: pl.DataFrame,
        shadow_invoices_df: pl.DataFrame | None = None,
        safe_to_spend: float | None = None,
        reference_date: date | None = None,
    ) -> UserProfile:
        """
        Constrói um UserProfile a partir dos DataFrames de entrada.

        Args:
            transactions_df: DataFrame com schema transactions_clean da F1.
            shadow_invoices_df: DataFrame de shadow invoices da F1 (opcional).
            safe_to_spend: margem diária disponível (não usada no perfil, aceita para interface).
            reference_date: data de referência para a janela de 90 dias (default=hoje).

        Returns:
            UserProfile com todos os campos calculados.
        """
        if transactions_df is None or transactions_df.is_empty():
            logger.warning("ConsumptionProfiler: DataFrame vazio — retornando perfil zerado")
            return UserProfile()

        ref = reference_date or date.today()
        cutoff = ref - timedelta(days=_WINDOW_DAYS)

        df = self._prepare_df(transactions_df, cutoff)

        if df.is_empty():
            logger.warning("ConsumptionProfiler: sem transações nos últimos 90 dias")
            return UserProfile()

        # Enriquecimento de features comportamentais (T1.1 — User Intelligence Fase 1)
        from app.optimizer.feature_store import TransactionFeatureEnricher
        df = TransactionFeatureEnricher().enrich(df)

        data_coverage_months = self._coverage_months(df)
        monthly_totals = self._monthly_expense_totals(df)
        monthly_avg_spend = float(monthly_totals.mean()) if len(monthly_totals) > 0 else 0.0
        spending_stability, spend_stability_cv = self._spending_stability(monthly_totals)

        spend_by_category = self._spend_by_category(df, data_coverage_months)
        spend_by_source = self._spend_by_source(df, data_coverage_months)
        international_spend_monthly = self._international_spend(df, data_coverage_months)
        travel_spend_monthly = self._travel_spend(df, data_coverage_months)
        estimated_monthly_income = self._monthly_income(df)
        committed_percentage = self._committed_percentage(shadow_invoices_df, monthly_avg_spend)
        credit_spend_ratio = self._credit_spend_ratio(spend_by_source)

        # Renda filtrada e classificada (IncomeProfiler opera sobre o df já recortado)
        income_profile = IncomeProfiler().build(df)

        profile = UserProfile(
            monthly_avg_spend=round(monthly_avg_spend, 2),
            committed_percentage=round(committed_percentage, 4),
            spend_by_category=spend_by_category,
            spend_by_source=spend_by_source,
            international_spend_monthly=round(international_spend_monthly, 2),
            travel_spend_monthly=round(travel_spend_monthly, 2),
            estimated_monthly_income=round(estimated_monthly_income, 2),
            data_coverage_months=data_coverage_months,
            spending_stability=round(spending_stability, 4),
            spend_stability_cv=round(spend_stability_cv, 4),
            income_profile=income_profile,
            credit_spend_ratio=round(credit_spend_ratio, 4),
        )

        logger.info(
            f"ConsumptionProfiler: avg_spend={profile.monthly_avg_spend:.2f}, "
            f"income_net={income_profile.monthly_net_income:.2f} "
            f"(raw={profile.estimated_monthly_income:.2f}, "
            f"pattern={income_profile.income_pattern}, "
            f"conf={income_profile.confidence:.2f}), "
            f"coverage={profile.data_coverage_months}m, "
            f"stability={profile.spending_stability:.2f}"
        )

        return profile

    # ─── Helpers privados ─────────────────────────────────────────────────────

    def _prepare_df(self, df: pl.DataFrame, cutoff: date) -> pl.DataFrame:
        """Filtra janela de 90 dias e exclui transações PJ."""
        if df["date"].dtype != pl.Date:
            df = df.with_columns(pl.col("date").cast(pl.Date))

        df = df.filter(pl.col("date") >= cutoff)

        if "context_type" in df.columns:
            df = df.filter(
                pl.col("context_type").is_null() | (pl.col("context_type") != "PJ")
            )

        return df

    def _coverage_months(self, df: pl.DataFrame) -> int:
        """Conta meses distintos no histórico filtrado."""
        months = (
            df.select(
                (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
            )
            .unique()
            .height
        )
        return months

    def _monthly_expense_totals(self, df: pl.DataFrame) -> pl.Series:
        """Soma de despesas (amount < 0) por mês. Retorna Series de valores positivos."""
        expenses = df.filter(pl.col("amount") < 0)
        if expenses.is_empty():
            return pl.Series("monthly", [], dtype=pl.Float64)

        monthly = (
            expenses
            .with_columns(
                (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
            )
            .group_by("ym")
            .agg(pl.col("amount").sum().alias("total"))
            .with_columns(pl.col("total").abs())
            .get_column("total")
        )
        return monthly

    def _spending_stability(self, monthly_totals: pl.Series) -> tuple[float, float]:
        """
        Calcula estabilidade do gasto mensal e coeficiente de variação bruto.

        Returns:
            (spending_stability, spend_stability_cv)
            spending_stability: 0.0–1.0, onde 1.0 = muito estável (= 1 − CV)
            spend_stability_cv: CV puro (std/mean), usado pelo ConfidenceScorer
        """
        if len(monthly_totals) < 2:
            return 0.5, 0.5

        mean = monthly_totals.mean()
        if mean == 0:
            return 0.0, 1.0

        std = monthly_totals.std(ddof=0)
        cv = float(std) / float(mean)
        stability = max(round(1.0 - min(cv, 1.0), 4), 0.0)
        return stability, round(min(cv, 1.0), 4)

    def _spend_by_category(self, df: pl.DataFrame, coverage_months: int) -> dict:
        """Gasto médio mensal por categoria (apenas despesas)."""
        if "category" not in df.columns:
            return {}

        expenses = df.filter(pl.col("amount") < 0)
        if expenses.is_empty():
            return {}

        months = max(coverage_months, 1)

        result = (
            expenses
            .group_by("category")
            .agg(pl.col("amount").sum().abs().alias("total"))
            .with_columns((pl.col("total") / months).alias("monthly_avg"))
        )

        return {
            row["category"]: round(row["monthly_avg"], 2)
            for row in result.to_dicts()
            if row["category"] is not None
        }

    def _spend_by_source(self, df: pl.DataFrame, coverage_months: int) -> dict:
        """
        Gasto médio mensal por fonte de pagamento.

        Convenção baseada no transaction_type:
        - "DEBIT" → débito (conta corrente / PIX / boleto)
        - qualquer outro → crédito (cartão de crédito)
        """
        if "transaction_type" not in df.columns:
            return {}

        expenses = df.filter(pl.col("amount") < 0)
        if expenses.is_empty():
            return {}

        months = max(coverage_months, 1)

        result = (
            expenses
            .with_columns(
                pl.when(pl.col("transaction_type").str.to_uppercase() == "DEBIT")
                .then(pl.lit("debit"))
                .otherwise(pl.lit("credit"))
                .alias("source")
            )
            .group_by("source")
            .agg(pl.col("amount").sum().abs().alias("total"))
            .with_columns((pl.col("total") / months).alias("monthly_avg"))
        )

        return {
            row["source"]: round(row["monthly_avg"], 2)
            for row in result.to_dicts()
        }

    def _international_spend(self, df: pl.DataFrame, coverage_months: int) -> float:
        """Estimativa de gasto internacional mensal (detecção por keywords na descrição)."""
        if "description" not in df.columns:
            return 0.0

        expenses = df.filter(pl.col("amount") < 0)
        if expenses.is_empty():
            return 0.0

        intl = expenses.filter(
            pl.col("description").str.to_lowercase().str.contains(_INTERNATIONAL_PATTERN)
        )

        if intl.is_empty():
            return 0.0

        total = float(intl.get_column("amount").sum()) * -1
        return round(total / max(coverage_months, 1), 2)

    def _travel_spend(self, df: pl.DataFrame, coverage_months: int) -> float:
        """Gasto médio mensal nas categorias de viagem (Lazer + Transporte)."""
        if "category" not in df.columns:
            return 0.0

        travel = df.filter(
            (pl.col("amount") < 0) & pl.col("category").is_in(list(_TRAVEL_CATEGORIES))
        )

        if travel.is_empty():
            return 0.0

        total = float(travel.get_column("amount").sum()) * -1
        return round(total / max(coverage_months, 1), 2)

    def _monthly_income(self, df: pl.DataFrame) -> float:
        """Estima renda mensal a partir de entradas positivas (salário, transferências recebidas)."""
        credits = df.filter(pl.col("amount") > 0)
        if credits.is_empty():
            return 0.0

        monthly = (
            credits
            .with_columns(
                (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
            )
            .group_by("ym")
            .agg(pl.col("amount").sum().alias("total"))
            .get_column("total")
        )

        return round(float(monthly.mean()), 2) if len(monthly) > 0 else 0.0

    def _committed_percentage(
        self,
        shadow_invoices_df: pl.DataFrame | None,
        monthly_avg_spend: float,
    ) -> float:
        """
        Percentual do gasto mensal já comprometido com parcelas e assinaturas.

        Contrato da interface:
            shadow_invoices_df deve ser o output de run_shadow_invoice_detection(),
            onde cada linha representa UMA obrigação mensal detectada (um padrão
            recorrente, não cada ocorrência histórica). Portanto, a soma dos amounts
            já representa o total mensal comprometido — não há necessidade de
            normalizar por número de meses.

            Se o chamador passar um DataFrame com múltiplas ocorrências históricas
            da mesma obrigação, o percentual será inflado proporcionalmente.
        """
        if shadow_invoices_df is None or shadow_invoices_df.is_empty():
            return 0.0

        if monthly_avg_spend <= 0:
            return 1.0

        if "amount" not in shadow_invoices_df.columns:
            return 0.0

        total_committed = float(shadow_invoices_df.get_column("amount").sum()) * -1
        total_committed = max(total_committed, 0.0)

        return min(round(total_committed / monthly_avg_spend, 4), 1.0)

    def _credit_spend_ratio(self, spend_by_source: dict) -> float:
        """
        Fração do gasto total que já transita por crédito.

        Usuários com alto uso de débito têm retorno de cartão de crédito superestimado
        se usarmos monthly_avg_spend bruto. Este ratio corrige isso.

        Floor de 0.10: usuário predominantemente débito pode não querer crédito —
        assumir 50% causava superestimação de 5-10x para usuários PIX-only.
        Floor mínimo de 10% evita retorno=0 para usuários sem histórico de crédito,
        preservando recomendações básicas sem inflar resultados.
        """
        credit = spend_by_source.get("credit", 0.0)
        debit = spend_by_source.get("debit", 0.0)
        total = credit + debit
        if total <= 0:
            return 1.0
        raw_ratio = credit / total
        return max(raw_ratio, 0.10)
