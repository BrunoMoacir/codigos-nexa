"""
FamilyDetector — detecta perfil de pai/mãe com filhos pequenos.
"""

from __future__ import annotations
import re
from typing import TYPE_CHECKING

import polars as pl

from app.optimizer.detectors.evidence_scorer import compute_false_positive_risk
from app.core.formatacao import brl

if TYPE_CHECKING:
    from app.optimizer.detectors.personal_baseline import PersonalBaseline

_SCHOOL_KEYWORDS = ["ESCOLA", "COLEGIO", "CRECHE", "MATERNAL", "ENSINO INFANTIL"]
_BABY_PRODUCT_KEYWORDS = ["FRALDA", "PAMPERS", "HUGGIES", "CHICCO", "FISHER PRICE"]
_PEDIATRIC_KEYWORDS = ["PEDIATR", "INFANTIL CLINICA", "PLANO SAUDE CRIANCA", "PLANO FAMILIAR"]
_KIDS_CLOTHING_KEYWORDS = ["RENNER KIDS", "HERING KIDS", "CARTER", "POSTHAUS", "ZARA KIDS"]
_ENTERTAINMENT_KIDS_KEYWORDS = ["MUNDO BITA", "MAGIC CITY", "HOPI HARI", "PARQUE", "BRINQUEDOTECA"]

# Padrões pré-compilados com re.escape para evitar interpretação de metacaracteres
# (ex: "FISHER PRICE" e outros nomes com espaços/pontos são literais, não regex).
_P_SCHOOL        = re.compile("|".join(re.escape(k) for k in _SCHOOL_KEYWORDS),        re.IGNORECASE)
_P_BABY          = re.compile("|".join(re.escape(k) for k in _BABY_PRODUCT_KEYWORDS),  re.IGNORECASE)
_P_PEDIATRIC     = re.compile("|".join(re.escape(k) for k in _PEDIATRIC_KEYWORDS),     re.IGNORECASE)
_P_KIDS_CLOTHING = re.compile("|".join(re.escape(k) for k in _KIDS_CLOTHING_KEYWORDS), re.IGNORECASE)
_P_KIDS_ENTERT   = re.compile("|".join(re.escape(k) for k in _ENTERTAINMENT_KIDS_KEYWORDS), re.IGNORECASE)


def _match_count(expenses: pl.DataFrame, pattern: re.Pattern) -> int:
    if expenses.is_empty():
        return 0
    return expenses.filter(
        pl.col("description").str.to_uppercase().str.contains(pattern.pattern)
    ).height


def _match_spend(expenses: pl.DataFrame, pattern: re.Pattern) -> float:
    if expenses.is_empty():
        return 0.0
    filtered = expenses.filter(
        pl.col("description").str.to_uppercase().str.contains(pattern.pattern)
    )
    return float(filtered["amount"].sum()) * -1 if not filtered.is_empty() else 0.0


class FamilyDetector:
    """
    Detecta perfil de pai/mãe com filhos pequenos.

    family_score (0–100), is_family_with_kids (bool).
    Threshold: family_score >= 40 → is_family_with_kids = True.
    """

    def detect_family_profile(
        self,
        df: pl.DataFrame,
        baseline: "PersonalBaseline | None" = None,
    ) -> dict:
        """
        Args:
            df:       transactions_clean já enriquecido (janela 90 dias).
            baseline: PersonalBaseline do usuário (90–540 dias). Quando fornecido,
                      os thresholds de gasto são adaptados ao histórico pessoal:
                      categorias sem histórico recebem gate reduzido (novo sinal = mais forte);
                      categorias já estabelecidas exigem spike maior para disparar.
        """
        if df.is_empty() or "description" not in df.columns:
            return {
                "is_family_with_kids": False, "family_score": 0.0, "family_signals": [],
                "confidence": 0.0, "supporting_signals": [], "missing_signals": ["escola", "produtos_bebe", "pediatria", "roupas_infantis", "entretenimento_infantil"], "false_positive_risk": "high",
            }

        score = 0.0
        signals: list[str] = []
        missing: list[str] = []

        expenses = df.filter(pl.col("amount") < 0)

        # Normalização mensal para comparação contra baseline (R$/mês).
        # Quando baseline ausente, compara totais brutos do período (comportamento original).
        use_baseline = baseline is not None and baseline.has_data()
        if use_baseline:
            coverage_months = max(
                df.with_columns(
                    (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
                ).select("ym").unique().height,
                1,
            )
            # Thresholds mensais adaptados ao histórico pessoal.
            # "educacao": tuition/creche → spike_ratio 1.5× (mensalidade sobe gradualmente)
            # "farmacia": proxy para produtos bebê → spike_ratio 2.0× (compra concentrada)
            # "vestuario": roupas infantis → spike_ratio 1.5×
            thr_school   = baseline.adjusted_threshold("educacao",  default=67.0,  spike_ratio=1.5)
            thr_baby     = baseline.adjusted_threshold("farmacia",  default=33.0,  spike_ratio=2.0)
            thr_clothing = baseline.adjusted_threshold("vestuario", default=33.0,  spike_ratio=1.5)
        else:
            coverage_months = 1
            # Thresholds originais: comparação no total do período (não mensal).
            thr_school, thr_baby, thr_clothing = 200.0, 100.0, 100.0

        def _monthly(spend: float) -> float:
            return spend / coverage_months if use_baseline else spend

        school_spend = _match_spend(expenses, _P_SCHOOL)
        if _monthly(school_spend) > thr_school:
            score += 30
            signals.append(f"school_spend={brl(school_spend, 0)}")
            if use_baseline:
                ratio = baseline.deviation_ratio("educacao", school_spend / coverage_months)
                if ratio != float("inf"):
                    signals.append(f"school_vs_baseline={ratio:.1f}x")
                elif school_spend > 0:
                    signals.append("school_categoria_nova")
        else:
            missing.append("escola")

        baby_spend = _match_spend(expenses, _P_BABY)
        if _monthly(baby_spend) > thr_baby:
            score += 25
            signals.append(f"baby_products={brl(baby_spend, 0)}")
            if use_baseline:
                ratio = baseline.deviation_ratio("farmacia", baby_spend / coverage_months)
                if ratio != float("inf"):
                    signals.append(f"baby_vs_baseline={ratio:.1f}x")
                elif baby_spend > 0:
                    signals.append("baby_categoria_nova")
        else:
            missing.append("produtos_bebe")

        pediatric_count = _match_count(expenses, _P_PEDIATRIC)
        if pediatric_count >= 2:
            score += 20
            signals.append(f"pediatric_visits={pediatric_count}")
        else:
            missing.append("pediatria")

        kids_clothing = _match_spend(expenses, _P_KIDS_CLOTHING)
        if _monthly(kids_clothing) > thr_clothing:
            score += 15
            signals.append(f"kids_clothing={brl(kids_clothing, 0)}")
            if use_baseline:
                ratio = baseline.deviation_ratio("vestuario", kids_clothing / coverage_months)
                if ratio != float("inf"):
                    signals.append(f"clothing_vs_baseline={ratio:.1f}x")
        else:
            missing.append("roupas_infantis")

        kids_entertainment = _match_count(expenses, _P_KIDS_ENTERT)
        if kids_entertainment >= 2:
            score += 10
            signals.append(f"kids_entertainment={kids_entertainment}")
        else:
            missing.append("entretenimento_infantil")

        family_score = round(min(score, 100.0), 1)
        confidence = round(family_score / 100, 4)

        return {
            "is_family_with_kids": family_score >= 40,
            "family_score": family_score,
            "family_signals": signals,
            "confidence": confidence,
            "supporting_signals": signals,
            "missing_signals": missing,
            "false_positive_risk": compute_false_positive_risk(confidence),
        }
