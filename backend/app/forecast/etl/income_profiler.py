"""
app/etl/income_profiler.py - Estimativa de Renda Mensal Real (M1.x)

PROBLEMA RESOLVIDO:
    ConsumptionProfiler._monthly_income() soma todos os créditos sem filtro,
    inflando a renda em 2-3× para usuários com múltiplos bancos:
        - Transferência Nubank → Inter aparece como "renda" no Inter
        - Estornos, cashback, rendimentos de investimento contam como renda
    Resultado: elegibilidade de cartões errada, burn rate sem referência real,
    anomalias com thresholds inadequados.

O QUE ESTE MÓDULO FAZ:
    1. Exclui créditos por keywords de não-renda (estornos, transferências, rendimentos)
    2. Exclui round-trips: crédito que "desfaz" um débito recente (transferência interna)
    3. Classifica o padrão: CLT (salário fixo) | PJ (variável) | MIXED | UNKNOWN
    4. Calcula estabilidade e confiança da estimativa

INTEGRAÇÃO:
    - ConsumptionProfiler.build() chama IncomeProfiler e armazena em UserProfile.income_profile
    - OptimizerService usa income_profile.monthly_net_income para elegibilidade (card.min_income)
    - BurnRateAnalyzer usa como referência de budget total quando disponível
    - Se confidence < 0.5, os consumidores devem usar fallback ou pedir renda ao usuário

LIMITAÇÕES CONHECIDAS:
    - Round-trip cross-bank (Nubank → Inter) não é detectável com dados de um único banco.
      A exclusão por keywords "PIX TRANSF", "TED ENVIO" mitiga parcialmente.
    - Proxy de payer = primeiros 30 chars da descrição. Payers com nomes longos similares
      podem ser tratados como o mesmo payer.
    - `join_asof` no round-trip detection compara cada crédito com o débito mais recente
      na janela — não verifica TODOS os débitos no período (aceitável para MVP).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum

import polars as pl
from app.core.formatacao import brl

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONSTANTES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Keywords que indicam que o crédito NÃO é renda do trabalho
_EXCLUSION_PATTERN = (
    r"estorno|devoluc|reembolso|cashback|rendimento|juros cred"
    r"|resgate|aplicac|cdb |lci |lca |fundo |ted envio|pix envio"
    r"|tarifa|anuidade|taxa admin|saque|transferencia propria"
)

# Keywords que indicam salário CLT com alta confiança
_SALARY_PATTERN = (
    r"salario|salário|folha|holerite|pagamento sal|vale sal"
    r"|remuneracao|remuneração|rh |recursos humanos|pgto sal"
    r"|vencimento|proventos"
)

# Keywords que indicam renda PJ / freelance
_PJ_PATTERN = (
    r"nota fiscal|nf |prestac|prestação|servicos prest|serviços prest"
    r"|honorario|honorário|autonomo|autônomo|mei |pj "
)

# Janela para round-trip: crédito que "desfaz" débito recente → transferência interna
_ROUNDTRIP_WINDOW_DAYS: int = 5
_ROUNDTRIP_TOLERANCE: float = 0.02  # 2% de tolerância no valor

# Coeficiente de variação máximo para considerar renda "estável" (CLT)
_STABLE_CV_THRESHOLD: float = 0.15

# Desvio máximo do dia de pagamento para detectar cadência de salário (dias)
_SALARY_DAY_TOLERANCE: int = 5

# Mínimo de meses para calcular estabilidade confiável
_MIN_MONTHS: int = 2

# Número mínimo de payers distintos para sinalizar PJ
_PJ_MIN_PAYERS: int = 3


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENUMS & TIPOS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class IncomePattern(str, Enum):
    CLT     = "CLT"      # Salário fixo mensal de empregador único
    PJ      = "PJ"       # Renda variável, múltiplos pagadores
    MIXED   = "MIXED"    # CLT + renda PJ complementar (ex: salário + freela)
    UNKNOWN = "UNKNOWN"  # Dados insuficientes ou padrão não identificado


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATACLASS DE RESULTADO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class IncomeProfile:
    """
    Estimativa de renda mensal real do usuário.

    Attributes:
        monthly_net_income: Renda líquida estimada (R$/mês). Campo principal
            a ser usado pelos módulos consumidores. Exclui transferências,
            estornos e rendimentos de investimento.
        income_pattern: CLT | PJ | MIXED | UNKNOWN
        income_stability: 0.0–1.0. CLT bem detectado → ~0.9. PJ variável → ~0.3.
        confidence: 0.0–1.0. Indica confiança na estimativa.
            ≥ 0.7 → usar diretamente para eligibilidade de cartão.
            0.4–0.7 → usar com cautela.
            < 0.4 → preferir renda declarada pelo usuário.
        salary_monthly: Componente CLT detectada (R$/mês).
        freelance_monthly: Componente PJ detectada (R$/mês).
        raw_monthly_credits: Total bruto de créditos antes das exclusões.
        excluded_monthly: Valor médio excluído por mês (transferências/estornos).
        detection_signals: Lista de sinais que guiaram a classificação.

    Example:
        >>> profile.monthly_net_income
        8500.0
        >>> profile.income_pattern
        <IncomePattern.CLT: 'CLT'>
        >>> profile.confidence
        0.85
    """
    monthly_net_income: float
    income_pattern: IncomePattern
    income_stability: float
    confidence: float
    salary_monthly: float
    freelance_monthly: float
    raw_monthly_credits: float
    excluded_monthly: float
    detection_signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "monthly_net_income": self.monthly_net_income,
            "income_pattern": self.income_pattern,
            "income_stability": self.income_stability,
            "confidence": self.confidence,
            "salary_monthly": self.salary_monthly,
            "freelance_monthly": self.freelance_monthly,
            "raw_monthly_credits": self.raw_monthly_credits,
            "excluded_monthly": self.excluded_monthly,
            "detection_signals": self.detection_signals,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROFILER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class IncomeProfiler:
    """
    Estima a renda mensal real filtrando créditos que não são renda do trabalho.

    Recebe o DataFrame completo (débitos + créditos) porque a detecção de
    round-trips requer comparar créditos contra débitos recentes.

    Example:
        >>> profiler = IncomeProfiler()
        >>> income = profiler.build(transactions_df)
        >>> print(f"R$ {income.monthly_net_income:,.0f}/mês ({income.income_pattern})")
        R$ 8.500/mês (CLT)
        >>> if income.confidence < 0.5:
        ...     # pedir renda ao usuário
    """

    def build(self, transactions_df: pl.DataFrame) -> IncomeProfile:
        """
        Constrói o IncomeProfile a partir do DataFrame completo de transações.

        Args:
            transactions_df: DataFrame com schema transactions_clean da F1.
                Deve conter: date (Date), amount (Float64), description (Utf8).
                Pode conter tanto créditos (amount > 0) quanto débitos (amount < 0).

        Returns:
            IncomeProfile com todos os campos calculados.
            Se dados insuficientes, retorna _empty() com UNKNOWN e confidence=0.
        """
        if transactions_df is None or transactions_df.is_empty():
            return _empty()

        # O DataFrame do ETL (pré-persistência) chama a coluna de
        # transaction_date; o rename para 'date' só acontece em
        # save_transactions_clean. Sem este alias, todo usuário sincronizado
        # pela rota da Pluggy caía em _empty() com renda 0.
        if "date" not in transactions_df.columns and "transaction_date" in transactions_df.columns:
            transactions_df = transactions_df.rename({"transaction_date": "date"})

        required = {"date", "amount"}
        if not required.issubset(transactions_df.columns):
            logger.warning("IncomeProfiler: colunas 'date' ou 'amount' ausentes")
            return _empty()

        df = transactions_df.with_columns(pl.col("date").cast(pl.Date))

        credits_raw = df.filter(pl.col("amount") > 0)
        debits      = df.filter(pl.col("amount") < 0)

        if credits_raw.is_empty():
            return _empty()

        signals: list[str] = []

        # ── 1. Excluir créditos por keywords de não-renda ─────────────────
        credits = self._exclude_by_keywords(credits_raw, signals)

        # ── 2. Excluir round-trips (transferências internas) ───────────────
        credits = self._exclude_roundtrips(credits, debits, signals)

        if credits.is_empty():
            return _empty()

        # ── 3. Calcular médias mensais ────────────────────────────────────
        n_months    = _coverage_months(df)
        months      = max(n_months, 1)
        raw_monthly = round(float(credits_raw["amount"].sum()) / months, 2)
        net_monthly = round(float(credits["amount"].sum()) / months, 2)
        excluded    = round(raw_monthly - net_monthly, 2)

        # ── 4. Classificar padrão de renda ────────────────────────────────
        pattern, salary_monthly, freelance_monthly, has_keyword = self._classify_pattern(
            credits, months, signals
        )

        # ── 5. Estabilidade e confiança ───────────────────────────────────
        stability  = self._income_stability(credits, n_months)
        confidence = self._income_confidence(pattern, n_months, has_keyword, stability)

        logger.info(
            f"IncomeProfiler: net={net_monthly:.0f}/mês, pattern={pattern}, "
            f"stability={stability:.2f}, confidence={confidence:.2f}, "
            f"excluded={excluded:.0f}/mês ({len(signals)} sinais)"
        )

        return IncomeProfile(
            monthly_net_income=net_monthly,
            income_pattern=pattern,
            income_stability=stability,
            confidence=confidence,
            salary_monthly=round(salary_monthly, 2),
            freelance_monthly=round(freelance_monthly, 2),
            raw_monthly_credits=raw_monthly,
            excluded_monthly=excluded,
            detection_signals=signals,
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PRIVATE HELPERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _exclude_by_keywords(
        credits: pl.DataFrame,
        signals: list[str],
    ) -> pl.DataFrame:
        """Exclui créditos cuja descrição corresponde a entradas que não são renda."""
        if "description" not in credits.columns:
            return credits

        before   = credits.height
        filtered = credits.filter(
            ~pl.col("description").str.to_lowercase().str.contains(_EXCLUSION_PATTERN)
        )
        n_excluded = before - filtered.height
        if n_excluded > 0:
            signals.append(
                f"{n_excluded} créditos excluídos por keywords "
                f"(estornos / transferências / rendimentos)"
            )
        return filtered

    @staticmethod
    def _exclude_roundtrips(
        credits: pl.DataFrame,
        debits: pl.DataFrame,
        signals: list[str],
    ) -> pl.DataFrame:
        """
        Exclui créditos que parecem ser round-trips de transferência interna.

        Para cada crédito, procura o débito mais recente nos últimos
        _ROUNDTRIP_WINDOW_DAYS dias com valor similar (±_ROUNDTRIP_TOLERANCE).
        Se encontrado, o crédito é considerado transferência própria e removido.

        Usa join_asof (vectorizado) em vez de loop Python.

        Limitação: verifica apenas o débito mais recente na janela — não
        todos os débitos no período (join_asof backward strategy).
        Para MVP, é suficiente: transferências internas geralmente ocorrem
        em sequência próxima no extrato.
        """
        if debits.is_empty():
            return credits

        # Preparar debits: converter para datetime (join_asof exige) + valor absoluto
        debits_prep = (
            debits
            .with_columns([
                pl.col("date").cast(pl.Date).cast(pl.Datetime).alias("date"),
                pl.col("amount").abs().alias("_debit_abs"),
            ])
            .sort("date")
            .select(["date", "_debit_abs"])
        )

        credits_prep = (
            credits
            .with_columns(
                pl.col("date").cast(pl.Date).cast(pl.Datetime).alias("date")
            )
            .sort("date")
        )

        # join_asof: associa cada crédito ao débito mais recente ≤ N dias antes
        joined = credits_prep.join_asof(
            debits_prep,
            on="date",
            strategy="backward",
            tolerance=timedelta(days=_ROUNDTRIP_WINDOW_DAYS),
        )

        # Identificar round-trips: crédito ≈ débito (±2%)
        is_roundtrip = (
            pl.col("_debit_abs").is_not_null()
            & (
                (pl.col("amount") - pl.col("_debit_abs")).abs()
                / pl.col("_debit_abs").clip(lower_bound=0.01)
                <= _ROUNDTRIP_TOLERANCE
            )
        )

        n_excluded = joined.filter(is_roundtrip).height
        if n_excluded > 0:
            signals.append(
                f"{n_excluded} créditos removidos por suspeita de "
                f"round-trip (transferência interna)"
            )

        # Restaurar date para pl.Date e dropar coluna auxiliar
        result = (
            joined
            .filter(~is_roundtrip)
            .drop("_debit_abs")
            .with_columns(pl.col("date").cast(pl.Date))
        )
        return result

    @staticmethod
    def _classify_pattern(
        credits: pl.DataFrame,
        months: int,
        signals: list[str],
    ) -> tuple[IncomePattern, float, float, bool]:
        """
        Determina o padrão de renda e decomposição CLT/PJ.

        Returns:
            (pattern, salary_monthly, freelance_monthly, has_keyword)
            has_keyword: True se CLT ou PJ foram confirmados por keyword explícita
                (confiança maior). False se detectados apenas por cadência/payers.
        """
        has_desc = "description" in credits.columns
        total_monthly = float(credits["amount"].sum()) / months

        # ── Detectar CLT por keywords ──────────────────────────────────────
        salary_credits = pl.DataFrame()
        if has_desc:
            salary_credits = credits.filter(
                pl.col("description").str.to_lowercase().str.contains(_SALARY_PATTERN)
            )
        has_salary_kw = not salary_credits.is_empty()

        # ── Detectar CLT por cadência (mesmo valor, mesmo dia ±5) ──────────
        has_salary_cadence = _detect_salary_cadence(credits)

        # ── Detectar PJ por keywords ───────────────────────────────────────
        pj_credits = pl.DataFrame()
        if has_desc:
            pj_credits = credits.filter(
                pl.col("description").str.to_lowercase().str.contains(_PJ_PATTERN)
            )
        has_pj_kw = not pj_credits.is_empty()

        # ── Detectar PJ por diversidade de payers ─────────────────────────
        distinct_payers = 1
        if has_desc:
            distinct_payers = (
                credits
                .select(
                    pl.col("description").str.to_lowercase().str.strip_chars()
                    .str.slice(0, 30).alias("payer")
                )
                .get_column("payer")
                .n_unique()
            )
        has_many_payers = distinct_payers >= _PJ_MIN_PAYERS

        # ── Calcular componentes mensais ───────────────────────────────────
        salary_monthly    = float(salary_credits["amount"].sum()) / months if has_salary_kw else 0.0
        freelance_monthly = float(pj_credits["amount"].sum()) / months if has_pj_kw else 0.0

        # ── Classificar ───────────────────────────────────────────────────
        is_clt = has_salary_kw or has_salary_cadence
        is_pj  = has_pj_kw or has_many_payers

        if is_clt and is_pj:
            pattern = IncomePattern.MIXED
            signals.append(
                f"MIXED: salário CLT (~{brl(salary_monthly, 0)}/mês) "
                f"+ renda PJ (~{brl(freelance_monthly, 0)}/mês)"
            )
        elif is_clt:
            pattern = IncomePattern.CLT
            source  = "keyword de salário" if has_salary_kw else "cadência regular de crédito"
            # Limitação MVP: quando CLT é detectado apenas por cadência (sem keyword),
            # usamos total_monthly como proxy do salário. Se o usuário tiver créditos
            # PJ não detectados no mesmo período, salary_monthly ficará superestimado.
            # Mitigação: has_keyword=False reduz confidence para 0.55, sinaliza incerteza.
            salary_monthly = salary_monthly if has_salary_kw else total_monthly
            signals.append(
                f"CLT detectado via {source} "
                f"(~{brl(salary_monthly, 0)}/mês)"
            )
        elif is_pj:
            pattern = IncomePattern.PJ
            source  = "keyword PJ" if has_pj_kw else f"{distinct_payers} payers distintos"
            freelance_monthly = freelance_monthly if has_pj_kw else total_monthly
            signals.append(
                f"PJ detectado via {source}"
            )
        else:
            pattern = IncomePattern.UNKNOWN
            signals.append("Padrão de renda não identificado — dados ambíguos ou insuficientes")

        has_keyword = has_salary_kw or has_pj_kw
        return pattern, salary_monthly, freelance_monthly, has_keyword

    @staticmethod
    def _income_stability(credits: pl.DataFrame, n_months: int) -> float:
        """
        Estabilidade da renda mensal: 1 − CV, limitada a [0, 1].
        Com < 2 meses retorna 0.3 (conservador).
        """
        if n_months < _MIN_MONTHS:
            return 0.3

        monthly = (
            credits
            .with_columns(
                (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
            )
            .group_by("ym")
            .agg(pl.col("amount").sum().alias("total"))
            .get_column("total")
        )

        if len(monthly) < 2:
            return 0.3

        mean = float(monthly.mean() or 0)
        if mean <= 0:
            return 0.0

        cv = float(monthly.std(ddof=0) or 0) / mean
        return round(max(0.0, 1.0 - min(cv, 1.0)), 4)

    @staticmethod
    def _income_confidence(
        pattern: IncomePattern,
        n_months: int,
        has_keyword: bool,
        stability: float,
    ) -> float:
        """
        Confiança na estimativa de renda (0.0–1.0).

        Args:
            has_keyword: True se CLT/PJ foram confirmados por keyword explícita
                (ex: "salario", "nota fiscal"). False se detectados apenas por
                cadência de crédito ou diversidade de payers.

        Base por padrão:
            UNKNOWN          → 0.25
            CLT/PJ via cadência (sem keyword) → 0.55
            CLT/PJ via keyword explícita       → 0.85
            MIXED (tem ambos)                  → 0.80

        Penalidades:
            < 2 meses de dados → × 0.5
            Estabilidade < 0.5 → × 0.8 (renda errática, difícil estimar)
        """
        if pattern == IncomePattern.UNKNOWN:
            base = 0.25
        elif pattern == IncomePattern.MIXED:
            base = 0.80
        elif has_keyword:
            base = 0.85
        else:
            base = 0.55  # cadência detectada, sem keyword

        if n_months < _MIN_MONTHS:
            base *= 0.5
        if stability < 0.5:
            base *= 0.8

        return round(min(base, 1.0), 4)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS PUROS (fora da classe para testabilidade isolada)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _detect_salary_cadence(credits: pl.DataFrame) -> bool:
    """
    Retorna True se houver um crédito recorrente com valor estável e dia fixo.

    Heurística: em cada mês, pega o maior crédito (provável salário).
    Se o CV desses valores for < _STABLE_CV_THRESHOLD e o desvio padrão do
    dia de pagamento for < _SALARY_DAY_TOLERANCE → cadência de CLT detectada.

    Requer ao menos _MIN_MONTHS meses de dados.
    """
    if "date" not in credits.columns or credits.is_empty():
        return False

    monthly_max = (
        credits
        .with_columns([
            pl.col("date").cast(pl.Date),
            (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym"),
            pl.col("date").dt.day().alias("day"),
        ])
        .group_by("ym")
        .agg([
            pl.col("amount").max().alias("max_amount"),
            # Dia do maior crédito do mês: sort_by dentro do agg
            pl.col("day").sort_by("amount", descending=True).first().alias("pay_day"),
        ])
        .sort("ym")
    )

    if monthly_max.height < _MIN_MONTHS:
        return False

    amounts = monthly_max.get_column("max_amount")
    mean    = float(amounts.mean() or 0)
    if mean <= 0:
        return False

    # ddof=1 intencional (amostral): com 2-3 meses, infla o desvio → mais
    # conservador na detecção de CLT. Preferível rejeitar uma cadência legítima
    # do que confirmar CLT em dados insuficientes. _income_stability usa ddof=0
    # (populacional) porque é descritivo, não decisório.
    cv = float(amounts.std(ddof=1) or 0) / mean
    if cv >= _STABLE_CV_THRESHOLD:
        return False  # valor do crédito varia muito

    day_std = float(monthly_max.get_column("pay_day").cast(pl.Float64).std(ddof=1) or 0)
    if day_std > _SALARY_DAY_TOLERANCE:
        return False  # dia de pagamento varia muito

    return True


def _coverage_months(df: pl.DataFrame) -> int:
    """Conta meses distintos no DataFrame."""
    return (
        df.select(
            (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
        )
        .unique()
        .height
    )


def _empty() -> IncomeProfile:
    """Retorna perfil neutro quando dados são insuficientes."""
    return IncomeProfile(
        monthly_net_income=0.0,
        income_pattern=IncomePattern.UNKNOWN,
        income_stability=0.0,
        confidence=0.0,
        salary_monthly=0.0,
        freelance_monthly=0.0,
        raw_monthly_credits=0.0,
        excluded_monthly=0.0,
        detection_signals=["Dados insuficientes para estimar renda"],
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER FUNCTION (convenience)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_income_profile(transactions_df: pl.DataFrame) -> IncomeProfile:
    """
    Wrapper de conveniência para IncomeProfiler.build().

    Example:
        >>> income = build_income_profile(transactions_df)
        >>> if income.confidence >= 0.5:
        ...     annual_income = income.monthly_net_income * 12
    """
    return IncomeProfiler().build(transactions_df)


__all__ = [
    "IncomeProfiler",
    "IncomeProfile",
    "IncomePattern",
    "build_income_profile",
]
