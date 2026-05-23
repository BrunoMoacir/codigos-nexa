"""
app/architect/validators/risk_scorer.py - Scoring multidimensional de tolerância a risco

Feature: F3 - Nexa Architect
Version: 2.1.0

Componentes implementados (5 de 6):
    C1 income_volatility:  income_profile.income_stability (1 − CV mensal da renda)
    C3 income_commitment:  1 − committed_pct (liberdade orçamentária residual)
    C4 reserve_depth:      surplus_acumulado / monthly_expenses / 6 (proxy de reserva)
    C5 savings_regularity: fração de meses com saldo líquido positivo
    C6 time_horizon_fit:   financing_months / prazo_máximo_para_o_tipo_de_bem

Componente ausente (sem API de portfólio):
    C2 investment_ratio:   portfólio variável / patrimônio total → None (peso zerado)

Agregação: média geométrica ponderada
    score = exp(Σ wᵢ × log(cᵢ))     [ao invés de Σ wᵢ × cᵢ]

    Propriedade crítica: um único componente próximo de zero derruba o score
    independente dos outros. committed_pct=95% com renda estável não compensa
    para MODERADO — é CONSERVADOR por definição.

Pesos por tipo de bem:
    IMOVEL  — income_volatility elevado (35 anos de compromisso)
    VEICULO — income_commitment elevado (ativo depreciativo, cash flow crítico)
    VIAGEM  — income_commitment + savings_regularity (crédito de consumo)
    REFORMA/OUTRO — balanceado (padrão)

Discretização (retrocompatibilidade com RiskProfile):
    score < 0.35 → CONSERVADOR
    score > 0.65 → AGRESSIVO
    meio         → MODERADO

Confidence:
    Indica o quanto o score pode ser confiado. Score 0.58 com 12 meses de
    dados reais é diferente de 0.58 baseado em 3 fallbacks.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.forecast.etl.income_profiler import IncomeProfile
    from app.forecast.etl.profiles import UserProfile

from app.architect.models import AssetType, RiskProfile, SimulationRequest

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONSTANTES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Prazo máximo por tipo de bem — espelho de input_validator._MAX_FINANCING_MONTHS
_MAX_MONTHS_BY_ASSET: dict[AssetType, int] = {
    AssetType.IMOVEL:  420,
    AssetType.VEICULO:  84,
    AssetType.REFORMA: 120,
    AssetType.VIAGEM:   60,
    AssetType.OUTRO:   120,
}

# Pesos por tipo de bem. Somam 1.0 incluindo C2 (investment_ratio), que
# quase sempre é None — o _compute_score renormaliza automaticamente ao removê-lo.
_WEIGHTS_BY_ASSET: dict[AssetType, dict[str, float]] = {
    AssetType.IMOVEL: {
        # 35 anos exige renda estável e reserva sólida acima de tudo
        "income_volatility":  0.30,
        "income_commitment":  0.18,
        "reserve_depth":      0.12,
        "savings_regularity": 0.15,
        "time_horizon_fit":   0.18,
        "investment_ratio":   0.07,
    },
    AssetType.VEICULO: {
        # Bem depreciativo: cash flow é o risco principal
        "income_volatility":  0.22,
        "income_commitment":  0.30,
        "reserve_depth":      0.10,
        "savings_regularity": 0.20,
        "time_horizon_fit":   0.10,
        "investment_ratio":   0.08,
    },
    AssetType.VIAGEM: {
        # Crédito de consumo: disciplina e folga mensal dominam
        "income_volatility":  0.18,
        "income_commitment":  0.32,
        "reserve_depth":      0.08,
        "savings_regularity": 0.28,
        "time_horizon_fit":   0.05,
        "investment_ratio":   0.09,
    },
    AssetType.REFORMA: {
        "income_volatility":  0.25,
        "income_commitment":  0.25,
        "reserve_depth":      0.10,
        "savings_regularity": 0.20,
        "time_horizon_fit":   0.12,
        "investment_ratio":   0.08,
    },
    AssetType.OUTRO: {
        "income_volatility":  0.25,
        "income_commitment":  0.25,
        "reserve_depth":      0.10,
        "savings_regularity": 0.20,
        "time_horizon_fit":   0.12,
        "investment_ratio":   0.08,
    },
}

# Limites para discretização em RiskProfile
_THRESHOLD_CONSERVATIVE: float = 0.35
_THRESHOLD_AGGRESSIVE:   float = 0.65

# Valor mínimo para log (evita log(0) = -inf nos componentes)
_LOG_FLOOR: float = 1e-4


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATACLASSES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class RiskComponents:
    """
    Vetor de componentes individuais do score de risco.

    Todos os valores em [0, 1] onde 1 = maior tolerância ao risco.
    None indica componente não computável (dados indisponíveis).
    Componentes None não entram na média — seus pesos são redistribuídos.
    """
    income_volatility:  float            # C1: 0=renda volátil, 1=estável
    income_commitment:  float            # C3: 0=tudo comprometido, 1=livre
    reserve_depth:      Optional[float]  # C4: 0=sem reserva, 1=≥6 meses cobertos
    savings_regularity: float            # C5: 0=nunca poupa, 1=poupa todo mês
    time_horizon_fit:   float            # C6: 0=prazo curto, 1=prazo longo
    investment_ratio:   Optional[float]  # C2: None se sem dados de portfólio


@dataclass
class RiskScore:
    """
    Resultado do scoring multidimensional de risco.

    Attributes:
        score:              Score contínuo [0-1] via média geométrica ponderada.
        profile:            RiskProfile discretizado (retrocompatibilidade API/DB).
        confidence:         Qualidade do score [0-1]. Baixa = muitos fallbacks.
        components:         Vetor com cada componente calculado.
        missing_components: Componentes com None (peso redistribuído para os demais).
        weights_used:       Pesos renormalizados efetivamente aplicados.
    """
    score:              float
    profile:            RiskProfile
    confidence:         float
    components:         RiskComponents
    missing_components: list[str]        = field(default_factory=list)
    weights_used:       dict[str, float] = field(default_factory=dict)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SCORER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class RiskScorer:
    """
    Scorer multidimensional de tolerância a risco financeiro.

    Ponto de entrada: RiskScorer.score() — estático, sem estado.

    Usa média geométrica ponderada em vez de aritmética:
        score = exp(Σ wᵢ × log(cᵢ))

    Isso garante que um componente crítico próximo de zero (ex: committed_pct=95%
    → C3=0.05) derrube o score drasticamente, independente dos outros componentes
    serem excelentes. Um usuário 95% comprometido não é MODERADO — é CONSERVADOR.

    Example:
        >>> rs = RiskScorer.score(request, income_profile, user_profile, df)
        >>> rs.score          # 0.4231
        >>> rs.profile        # RiskProfile.MODERADO
        >>> rs.confidence     # 0.72
        >>> rs.components.income_volatility   # 0.73
    """

    @staticmethod
    def score(
        request: SimulationRequest,
        income_profile: Optional["IncomeProfile"] = None,
        user_profile:   Optional["UserProfile"]   = None,
        transactions_df=None,
        committed_pct: float = 0.0,
        committed_available: bool = False,
        investment_ratio: Optional[float] = None,
        reserve_depth_override: Optional[float] = None,
    ) -> RiskScore:
        """
        Computa o score de tolerância ao risco.

        Args:
            request:                SimulationRequest (asset_type + financing_months para C6).
            income_profile:         IncomeProfile da F1 (income_stability para C1).
            user_profile:           UserProfile do UserProfileAnalyzer (C4 + fallback C1/C5).
            transactions_df:        DataFrame polars de transações (C5 preciso).
            committed_pct:          Fração da renda comprometida com obrigações fixas (C3).
            committed_available:    True quando committed_pct vem de dado real (não sentinel).
            investment_ratio:       Fração da carteira em renda variável (C2).
                                    None mantém o comportamento anterior (peso redistribuído).
            reserve_depth_override: C4 estimado externamente (ex: OF pipeline).
                                    Substitui _c4_reserve_depth(user_profile) quando não None.

        Returns:
            RiskScore com score, profile discretizado, confidence e componentes.
        """
        components = RiskScorer._build_components(
            request, income_profile, user_profile, transactions_df,
            committed_pct=committed_pct,
            committed_available=committed_available,
            investment_ratio=investment_ratio,
            reserve_depth_override=reserve_depth_override,
        )
        missing: list[str] = []
        score_val, weights = RiskScorer._compute_score(
            components, missing, request.asset_type
        )
        profile    = RiskScorer._discretize(score_val)
        confidence = RiskScorer._compute_confidence(
            income_profile, user_profile, transactions_df, missing
        )

        logger.debug(
            "RiskScorer | score=%.3f conf=%.2f profile=%s | "
            "C1=%.2f C3=%.2f C4=%s C5=%.2f C6=%.2f | asset=%s missing=%s",
            score_val, confidence, profile.value,
            components.income_volatility,
            components.income_commitment,
            f"{components.reserve_depth:.2f}" if components.reserve_depth is not None else "None",
            components.savings_regularity,
            components.time_horizon_fit,
            request.asset_type.value,
            missing,
        )

        return RiskScore(
            score=round(score_val, 4),
            profile=profile,
            confidence=round(confidence, 4),
            components=components,
            missing_components=missing,
            weights_used=weights,
        )

    # ── Construção dos componentes ───────────────────────────────────

    @staticmethod
    def _build_components(
        request: SimulationRequest,
        income_profile: Optional["IncomeProfile"],
        user_profile:   Optional["UserProfile"],
        transactions_df,
        committed_pct: float,
        committed_available: bool = False,
        investment_ratio: Optional[float] = None,
        reserve_depth_override: Optional[float] = None,
    ) -> RiskComponents:
        reserve_depth = (
            reserve_depth_override
            if reserve_depth_override is not None
            else RiskScorer._c4_reserve_depth(user_profile)
        )
        return RiskComponents(
            income_volatility  = RiskScorer._c1_income_volatility(income_profile, user_profile),
            income_commitment  = RiskScorer._c3_income_commitment(committed_pct, committed_available),
            reserve_depth      = reserve_depth,
            savings_regularity = RiskScorer._c5_savings_regularity(transactions_df, user_profile),
            time_horizon_fit   = RiskScorer._c6_time_horizon(request),
            investment_ratio   = investment_ratio,
        )

    @staticmethod
    def _c1_income_volatility(
        income_profile: Optional["IncomeProfile"],
        user_profile:   Optional["UserProfile"],
    ) -> float:
        """
        C1: Estabilidade da renda mensal [0-1]. 1=estável, 0=volátil.

        Fonte preferida: income_profile.income_stability = 1 − CV mensal.
        Fallback: 70% do resilience_score normalizado (proxy mais amplo).
        Default neutro: 0.50.
        """
        if income_profile is not None and income_profile.confidence >= 0.4:
            return float(income_profile.income_stability)
        if user_profile is not None:
            return min(user_profile.resilience_score / 100.0 * 0.7 + 0.15, 1.0)
        return 0.50

    @staticmethod
    def _c3_income_commitment(
        committed_pct: float,
        data_available: bool = False,
    ) -> float:
        """
        C3: Liberdade orçamentária [0-1]. 1=livre, 0=totalmente comprometido.

        Fórmula não-linear: exp(-3 × committed_pct). Penaliza comprometimento
        alto de forma desproporcional — reflete que cada % extra de renda comprometida
        reduz a margem de segurança de forma superlinear.

        Se data_available=False (dado ausente), retorna 0.5 neutro para não
        inflar nem penalizar o score por ausência de informação.
        """
        if not data_available:
            return 0.50

        clamped = max(0.0, min(1.0, committed_pct))
        return round(math.exp(-3.0 * clamped), 4)

    @staticmethod
    def _c4_reserve_depth(user_profile: Optional["UserProfile"]) -> Optional[float]:
        """
        C4: Profundidade de reserva de emergência [0-1].

        Proxy: surplus_acumulado_no_período / monthly_avg_expenses / 6.

        Interpretação: se o surplus do período cobre 6+ meses de despesas,
        o usuário demonstra capacidade de construção de reserva → C4 = 1.0.

        Limitação: mede o surplus do período observado, não o saldo atual de
        uma conta-reserva. Um usuário com reserva pré-existente mas sem transações
        recentes terá C4 = 0 incorretamente. Esse é o melhor proxy disponível
        sem dados de conta poupança.

        None quando user_profile é indisponível (C4 excluído da média).
        """
        if user_profile is None:
            return None

        surplus = user_profile.total_income - user_profile.total_expenses
        avg_expense = user_profile.monthly_avg_expenses

        if avg_expense <= 0:
            return None  # dados insuficientes para calcular

        if surplus <= 0:
            return 0.0  # gasto maior que renda → sem capacidade de reserva

        months_covered = surplus / avg_expense
        return round(min(months_covered / 6.0, 1.0), 4)

    @staticmethod
    def _c5_savings_regularity(
        transactions_df,
        user_profile: Optional["UserProfile"],
    ) -> float:
        """
        C5: Regularidade de poupança [0-1]. 1=poupa todo mês, 0=nunca.

        Fonte preferida: fração de meses com saldo líquido positivo no df.
        Fallback: mapeamento do savings_rate do UserProfile.
        Default neutro: 0.50.
        """
        if transactions_df is not None:
            try:
                return RiskScorer._savings_regularity_from_df(transactions_df)
            except Exception as exc:
                logger.debug("RiskScorer | C5 falhou no df: %s", exc)

        if user_profile is not None:
            sr = user_profile.savings_rate
            if sr >= 20:  return 0.85
            if sr >= 10:  return 0.65
            if sr >= 5:   return 0.45
            if sr >= 0:   return 0.30
            return 0.10

        return 0.50

    @staticmethod
    def _savings_regularity_from_df(df) -> float:
        """
        Calcula meses_com_saldo_positivo / total_meses a partir do DataFrame polars.

        Agrupa por ano-mês, soma todos os amounts, conta meses com saldo > 0.
        """
        import polars as pl

        col_date = next(
            (c for c in ("transaction_date", "date") if c in df.columns), None
        )
        if col_date is None or "amount" not in df.columns or df.is_empty():
            return 0.50

        monthly = (
            df.with_columns(
                (pl.col(col_date).dt.year() * 100 + pl.col(col_date).dt.month()).alias("ym")
            )
            .group_by("ym")
            .agg(pl.col("amount").sum().alias("net"))
        )

        total = monthly.height
        if total == 0:
            return 0.50

        positive = monthly.filter(pl.col("net") > 0).height
        return round(positive / total, 4)

    @staticmethod
    def _c6_time_horizon(request: SimulationRequest) -> float:
        """
        C6: Adequação do horizonte temporal [0-1].

        Prazo mais longo relativo ao máximo do tipo de bem = mais tempo para
        absorver volatilidade de retorno = maior tolerância ao risco de mercado.

        Nota: a média geométrica garante que C6 alto (horizonte longo) não compense
        outros componentes baixos. Um PJ instável num IMOVEL 420m tem C1=0.15,
        que derruba o score via geométrica independente de C6=1.0.
        """
        max_months = _MAX_MONTHS_BY_ASSET.get(request.asset_type, 120)
        return round(min(request.financing_months / max_months, 1.0), 4)

    # ── Score final, confidence e discretização ──────────────────────

    @staticmethod
    def _compute_score(
        components: RiskComponents,
        missing: list[str],
        asset_type: AssetType,
    ) -> tuple[float, dict[str, float]]:
        """
        Média geométrica ponderada com renormalização para componentes None.

        score = exp(Σ wᵢ × log(cᵢ))

        Propriedade central: um componente próximo de zero puxa o score para baixo
        de forma desproporcional, independente dos outros. Isso é intencional —
        reflete a natureza "o elo mais fraco quebra a corrente" do risco financeiro.

        Componentes None são excluídos e seus pesos redistribuídos proporcionalmente.
        """
        base_weights = _WEIGHTS_BY_ASSET.get(asset_type, _WEIGHTS_BY_ASSET[AssetType.OUTRO])

        values: dict[str, float] = {
            "income_volatility":  components.income_volatility,
            "income_commitment":  components.income_commitment,
            "savings_regularity": components.savings_regularity,
            "time_horizon_fit":   components.time_horizon_fit,
        }
        if components.reserve_depth is not None:
            values["reserve_depth"] = components.reserve_depth
        else:
            missing.append("reserve_depth")

        if components.investment_ratio is not None:
            values["investment_ratio"] = components.investment_ratio
        else:
            missing.append("investment_ratio")

        # Renormalizar pesos para os componentes presentes
        raw_weights = {k: base_weights[k] for k in values}
        total_w = sum(raw_weights.values())
        normalized = {k: v / total_w for k, v in raw_weights.items()}

        # Média geométrica ponderada: exp(Σ wᵢ × log(cᵢ))
        log_score = sum(
            normalized[k] * math.log(max(values[k], _LOG_FLOOR))
            for k in normalized
        )
        score = math.exp(log_score)
        return min(1.0, max(0.0, score)), normalized

    @staticmethod
    def _compute_confidence(
        income_profile: Optional["IncomeProfile"],
        user_profile:   Optional["UserProfile"],
        transactions_df,
        missing_components: list[str],
    ) -> float:
        """
        Calcula a confiança no score [0-1].

        Base: 0.40 — C5 via user_profile e C6 via request estão sempre disponíveis.
        +0.20 se income_profile com confidence ≥ 0.70 (C1 muito confiável)
        +0.10 se income_profile com confidence ≥ 0.40 (C1 parcialmente confiável)
        +0.15 se transactions_df cobre ≥ 6 meses (C5 confiável)
        +0.08 se transactions_df cobre 3–5 meses (C5 parcial)
        +0.04 se transactions_df cobre 1–2 meses (C5 fraco)
        +0.08 se user_profile disponível com dados reais (C4 + fallback C5)
        −0.07 por componente ausente (None) que usa peso redistribuído
        """
        conf = 0.40

        # C1 via income_profile
        if income_profile is not None:
            if income_profile.confidence >= 0.70:
                conf += 0.20
            elif income_profile.confidence >= 0.40:
                conf += 0.10

        # C5 via transactions_df
        if transactions_df is not None:
            n_months = RiskScorer._count_months(transactions_df)
            if n_months >= 6:
                conf += 0.15
            elif n_months >= 3:
                conf += 0.08
            elif n_months >= 1:
                conf += 0.04

        # C4 + fallback C1/C5 via user_profile
        if user_profile is not None and user_profile.total_income > 0:
            conf += 0.08

        # Penalizar por componentes ausentes
        conf -= len(missing_components) * 0.07

        return min(1.0, max(0.10, conf))

    @staticmethod
    def _count_months(df) -> int:
        """Conta meses distintos no DataFrame (para confidence de C5)."""
        try:
            import polars as pl
            col_date = next(
                (c for c in ("transaction_date", "date") if c in df.columns), None
            )
            if col_date is None:
                return 0
            return (
                df.select(
                    (pl.col(col_date).dt.year() * 100 + pl.col(col_date).dt.month()).alias("ym")
                )
                .unique()
                .height
            )
        except Exception:
            return 0

    @staticmethod
    def _discretize(score: float) -> RiskProfile:
        """Mapeia score contínuo para RiskProfile (retrocompatibilidade API/DB)."""
        if score < _THRESHOLD_CONSERVATIVE:
            return RiskProfile.CONSERVADOR
        if score > _THRESHOLD_AGGRESSIVE:
            return RiskProfile.AGRESSIVO
        return RiskProfile.MODERADO


__all__ = ["RiskScorer", "RiskScore", "RiskComponents"]
