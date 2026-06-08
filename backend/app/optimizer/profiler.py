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
_TRAVEL_CATEGORIES = {"Lazer", "Transporte", "lazer", "transporte", "viagem"}

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

    # ── Campos de Inteligência Comportamental (Fase 1) ────────────────────────
    # Todos com default para compatibilidade retroativa

    travel_frequency_score: float = 0.0          # 0–100 (TravelDetector)
    travel_profile: str = "OCASIONAL"            # OCASIONAL | MODERADO | FREQUENTE | INTENSO
    foodie_score: float = 0.0                    # 0–100 (FoodieDetector)
    foodie_profile: str = "BASICO"               # BASICO | APRECIADOR | GOURMET | ENTUSIASTA

    # savings_rate: FONTE = profiles.py::UserProfileAnalyzer.savings_rate (já calculado com
    # income_profile filtrado, behavior_tier e resilience_score de 6 fatores).
    # NÃO recalcular aqui — ler de UserProfileAnalyzer(df, income_profile).savings_rate
    # Valor em % (ex: 22.5 = 22.5%). profiles.py usa porcentagem, não fração.
    savings_rate: float = 0.0

    investor_type: str = "NONE"                  # NONE | CASUAL | ATIVO | DIVERSIFICADO
    is_likely_mei: bool = False                  # sinal de microempreendedor
    lifestyle_cluster: str = "NAO_CLASSIFICADO"  # ver T1.7
    cluster_scores: dict = field(default_factory=dict)  # afinidade 0–1 por cluster (T1.7)
    # Clusters além do primário com score ≥ 0.30 — ex: ["FAMILIA_ESTRUTURADA", "INVESTIDOR_CAUTELOSO"]
    secondary_clusters: list = field(default_factory=list)
    merchant_diversity_score: float = 0.0        # 0–100: diversidade de merchants únicos

    # subscription_burn_monthly: R$/mês em assinaturas de streaming (STREAMING L2).
    # DISTINTO de committed_percentage: committed_pct cobre TODAS as obrigações recorrentes
    # (shadow_invoices = parcelas + assinaturas), normalizado pelo gasto mensal total.
    # subscription_burn_monthly é apenas streaming (Netflix, Spotify, etc.), em R$/mês absoluto.
    subscription_burn_monthly: float = 0.0

    # ── Campos de Inteligência Comportamental (Fase 2) ────────────────────────

    # resilience_score: lido de UserProfileAnalyzer (profiles.py).
    # Repassado ao FSSCalculator para evitar recalcular savings_rate, tendência e committed_pct.
    resilience_score: float = 0.0             # 0–100, maior = mais resiliente (profiles.py)

    fss: float = 0.0                          # Financial Stress Score 0–100 (FSSCalculator)
    fss_level: str = "SAUDAVEL"               # SAUDAVEL | ATENCAO | ALERTA | CRITICO

    is_airbnb_user: bool = False               # T2.5: usa Airbnb (TravelDetector)
    is_digital_nomad: bool = False             # T2.5: Airbnb regular + coworking

    is_family_with_kids: bool = False          # T2.3: detector de família com filhos
    family_score: float = 0.0                  # 0–100 (FamilyDetector)

    peak_spend_day_of_month: Optional[int] = None   # T2.7: dia do mês com pico de gasto
    best_notification_day: int = 5                  # T2.7: melhor dia para notificar

    # True quando monthly_avg_spend foi estimado por renda (sem transações reais).
    # Usado pelo CardSimulator para capar confidence_score em 0.50 e pelo
    # OptimizerService para emitir warning no relatório.
    spend_is_estimated: bool = False

    # ── Campos de Tendência (TrendDetector) ───────────────────────────────────
    # Dict categoria → {direction, ratio, baseline_monthly, current_monthly}.
    # Direções: SUBINDO | ESTAVEL | CAINDO | REEMERGINDO | DESAPARECENDO
    # Chaves especiais: "_income" (renda), "_credit" (crédito), "_debit" (débito/PIX).
    # Vazio quando não há dados históricos suficientes (< 2 meses de baseline).
    category_trends: dict = field(default_factory=dict)

    # ── Campos de Estágio de Vida (LifeStageDetector) ────────────────────────
    # Estágio de vida inferido por combinação de sinais comportamentais.
    # Valores: FAMILIA_BEBE | NOMADE_DIGITAL | INVESTIDOR_PREMIUM | SOLTEIRO_URBANO | NAO_IDENTIFICADO
    life_stage: str = "NAO_IDENTIFICADO"
    life_stage_confidence: float = 0.0              # score do estágio primário (0.0–1.0)
    life_stage_scores: dict = field(default_factory=dict)  # afinidade por estágio


def _calc_merchant_diversity(df: pl.DataFrame) -> float:
    """Score 0–100: quanto mais merchants únicos, mais diversificado."""
    expenses = df.filter(pl.col("amount") < 0)
    if expenses.is_empty():
        return 0.0
    if "merchant_id" in expenses.columns:
        merch_col = "merchant_id"
    elif "merchant_normalized" in expenses.columns:
        merch_col = "merchant_normalized"
    elif "description" in expenses.columns:
        merch_col = "description"
    else:
        return 0.0
    return round(min(expenses[merch_col].n_unique(), 100), 1)


def _calc_subscription_burn(df: pl.DataFrame, coverage_months: int) -> float:
    """R$/mês em assinaturas de streaming (STREAMING L2)."""
    if "merchant_category_l2" not in df.columns:
        return 0.0
    streaming_df = df.filter(
        pl.col("merchant_category_l2").is_in({"STREAMING"}) & (pl.col("amount") < 0)
    )
    if streaming_df.is_empty():
        return 0.0
    total = float(streaming_df["amount"].sum()) * -1
    return round(total / max(coverage_months, 1), 2)


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

        # Baseline pessoal computado ANTES do corte de 90 dias.
        # Usa [90–540 dias atrás] como janela histórica — exclui o período atual para
        # evitar que o comportamento em análise contamine a própria referência.
        # Quando transactions_df só contém 90 dias, baseline.has_data() = False e
        # os detectores degradam graciosamente para thresholds fixos originais.
        from app.optimizer.detectors.personal_baseline import compute_personal_baseline
        personal_baseline = compute_personal_baseline(transactions_df, reference_date=ref)

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

        # Detectors comportamentais (T1.6)
        from app.optimizer.detectors.travel_detector import TravelDetector
        from app.optimizer.detectors.foodie_detector import FoodieDetector
        from app.optimizer.detectors.investor_detector import InvestorDetector
        from app.optimizer.detectors.mei_detector import MEIDetector

        # total_spend_period: gasto total no período coberto (90d, ~3m).
        # Nomeado anteriormente total_spend_12m por engano — não é anualizado.
        total_spend_period = monthly_avg_spend * data_coverage_months

        travel_detector = TravelDetector()
        travel_result = travel_detector.calc_travel_score(df, total_spend_period, baseline=personal_baseline)
        foodie_result = FoodieDetector().calc_foodie_score(df, monthly_avg_spend, baseline=personal_baseline)
        investor_result = InvestorDetector().calc_investor_profile(df)
        mei_result = MEIDetector().detect_mei_pattern(df, income_profile)
        merchant_diversity = _calc_merchant_diversity(df)
        subscription_burn = _calc_subscription_burn(df, data_coverage_months)

        # savings_rate: LIDO de UserProfileAnalyzer — não recalcular.
        from app.forecast.etl.profiles import UserProfileAnalyzer as _UPA
        _etl_profile = _UPA().analyze(df, income_profile, committed_percentage)
        savings_rate_pct = _etl_profile.savings_rate
        resilience_score = _etl_profile.resilience_score

        # travel_spend_monthly: TravelDetector usa is_travel_related (T1.1) — mais preciso
        # que _travel_spend() que só olha categorias L1 (Lazer + Transporte).
        # Usa o valor do detector se positivo; fallback para categoria L1 caso contrário.
        detector_travel_spend = travel_result.get("travel_spend_monthly", 0.0)
        effective_travel_spend = detector_travel_spend if detector_travel_spend > 0 else travel_spend_monthly

        profile = UserProfile(
            monthly_avg_spend=round(monthly_avg_spend, 2),
            committed_percentage=round(committed_percentage, 4),
            spend_by_category=spend_by_category,
            spend_by_source=spend_by_source,
            international_spend_monthly=round(international_spend_monthly, 2),
            travel_spend_monthly=round(effective_travel_spend, 2),
            estimated_monthly_income=round(estimated_monthly_income, 2),
            data_coverage_months=data_coverage_months,
            spending_stability=round(spending_stability, 4),
            spend_stability_cv=round(spend_stability_cv, 4),
            income_profile=income_profile,
            credit_spend_ratio=round(credit_spend_ratio, 4),
            travel_frequency_score=travel_result["travel_frequency_score"],
            travel_profile=travel_result["travel_profile"],
            foodie_score=foodie_result["foodie_score"],
            foodie_profile=foodie_result["foodie_profile"],
            savings_rate=savings_rate_pct,
            resilience_score=round(float(resilience_score), 1),
            investor_type=investor_result["investor_type"],
            is_likely_mei=mei_result["is_likely_mei"],
            merchant_diversity_score=merchant_diversity,
            subscription_burn_monthly=subscription_burn,
        )

        # Detectors Fase 2 que alimentam o LifestyleClassifier — devem rodar ANTES dele.

        # T2.3 — FamilyDetector (opera sobre o df enriquecido, janela 90 dias)
        from app.optimizer.detectors.family_detector import FamilyDetector
        family_result = FamilyDetector().detect_family_profile(df, baseline=personal_baseline)
        profile.is_family_with_kids = family_result["is_family_with_kids"]
        profile.family_score = family_result["family_score"]

        # T2.5 — Airbnb / Nômade Digital (reutiliza instância já criada acima)
        airbnb_result = travel_detector.detect_airbnb_profile(df)
        profile.is_airbnb_user = airbnb_result["is_airbnb_user"]
        profile.is_digital_nomad = airbnb_result["is_digital_nomad"]

        # T2.7 — Temporal Intelligence
        from app.optimizer.detectors.temporal_detector import TemporalDetector
        temporal_result = TemporalDetector().analyze(df)
        profile.peak_spend_day_of_month = temporal_result["peak_spend_day_of_month"]
        profile.best_notification_day = temporal_result["best_notification_day"]

        # Clustering de estilo de vida (T1.7) — usa family_score e is_airbnb_user acima
        from app.optimizer.detectors.lifestyle_classifier import LifestyleClassifier
        cluster_result = LifestyleClassifier().classify(profile)
        profile.lifestyle_cluster = cluster_result["lifestyle_cluster"]
        profile.secondary_clusters = cluster_result.get("secondary_clusters", [])
        profile.cluster_scores = cluster_result["cluster_scores"]

        # Detecção de tendência por categoria, renda e fonte de pagamento.
        # Usa transactions_df (histórico completo) para comparar baseline vs período recente.
        from app.optimizer.detectors.trend_detector import TrendDetector
        profile.category_trends = TrendDetector().detect(
            df=transactions_df,
            current_spend_by_category=spend_by_category,
            current_spend_by_source=spend_by_source,
            current_monthly_income=estimated_monthly_income,
            personal_baseline=personal_baseline,
            reference_date=ref,
            enriched_recent_df=df,   # df já enriquecido (90 dias) — habilita _pix e _delivery
        )

        # Estágio de vida (LifeStageDetector) — deve rodar DEPOIS de TrendDetector pois
        # usa category_trends._delivery para detectar SOLTEIRO_URBANO com mais precisão.
        from app.optimizer.detectors.life_stage_detector import LifeStageDetector
        life_stage_result = LifeStageDetector().detect(profile)
        profile.life_stage = life_stage_result["life_stage"]
        profile.life_stage_confidence = life_stage_result["life_stage_confidence"]
        profile.life_stage_scores = life_stage_result["life_stage_scores"]

        logger.info(
            f"ConsumptionProfiler: avg_spend={profile.monthly_avg_spend:.2f}, "
            f"income_net={income_profile.monthly_net_income:.2f} "
            f"(raw={profile.estimated_monthly_income:.2f}, "
            f"pattern={income_profile.income_pattern}, "
            f"conf={income_profile.confidence:.2f}), "
            f"coverage={profile.data_coverage_months}m, "
            f"stability={profile.spending_stability:.2f}, "
            f"cluster={profile.lifestyle_cluster}, "
            f"life_stage={profile.life_stage}({profile.life_stage_confidence:.2f})"
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
        """
        Gasto médio mensal por categoria (apenas despesas).

        Usa category_canonical (lowercase sem acento) quando disponível — garante que
        as chaves do dict coincidam com os cashback_categories em knowledge_cards.json
        ("alimentacao", "supermercado", "farmacia"...) e eliminam o dual-lookup
        "Alimentação" + "alimentacao" dos detectors.
        Fallback para raw `category` quando category_canonical não existe.
        """
        cat_col = "category_canonical" if "category_canonical" in df.columns else "category"
        if cat_col not in df.columns:
            return {}

        expenses = df.filter(pl.col("amount") < 0)
        if expenses.is_empty():
            return {}

        months = max(coverage_months, 1)

        result = (
            expenses
            .group_by(cat_col)
            .agg(pl.col("amount").sum().abs().alias("total"))
            .with_columns((pl.col("total") / months).alias("monthly_avg"))
        )

        return {
            row[cat_col]: round(row["monthly_avg"], 2)
            for row in result.to_dicts()
            if row[cat_col] is not None and row[cat_col] != "outros"
        }

    def _spend_by_source(self, df: pl.DataFrame, coverage_months: int) -> dict:
        """
        Gasto médio mensal por fonte de pagamento.

        Convenção baseada no transaction_type:
        - "DEBIT" → débito (conta corrente / PIX / boleto)
        - null/None → "unknown" (excluído do cálculo de credit_spend_ratio)
        - qualquer outro string não-nulo → crédito (cartão de crédito)

        Null é tratado como "unknown" e NÃO como crédito. Classificá-lo como
        crédito inflava credit_spend_ratio para usuários PIX-only cujo banco
        não preenche transaction_type, superestimando spend_annual em até 10×.
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
                pl.when(pl.col("transaction_type").is_null())
                .then(pl.lit("unknown"))
                .when(pl.col("transaction_type").str.to_uppercase() == "DEBIT")
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
        """Gasto médio mensal nas categorias de viagem (lazer + transporte + viagem).

        Usa category_canonical quando disponível para cobrir bancos que enviam
        "Lazer", "lazer" ou "viagem" sem normalização prévia.
        """
        cat_col = "category_canonical" if "category_canonical" in df.columns else "category"
        if cat_col not in df.columns:
            return 0.0

        travel = df.filter(
            (pl.col("amount") < 0) & pl.col(cat_col).is_in(list(_TRAVEL_CATEGORIES))
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

        Quando total=0 mas há transações "unknown" (transaction_type=None), o usuário
        é provavelmente PIX/débito — usa o floor (0.10) ao invés de 1.0 (default anterior).
        """
        credit = spend_by_source.get("credit", 0.0)
        debit = spend_by_source.get("debit", 0.0)
        total = credit + debit
        if total <= 0:
            has_unknown = spend_by_source.get("unknown", 0.0) > 0
            return 0.10 if has_unknown else 1.0
        raw_ratio = credit / total
        return max(raw_ratio, 0.10)
