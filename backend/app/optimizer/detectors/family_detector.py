"""
FamilyDetector — detecta perfil de pai/mãe com filhos pequenos.
"""

from __future__ import annotations
import re
import polars as pl

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

    def detect_family_profile(self, df: pl.DataFrame) -> dict:
        if df.is_empty() or "description" not in df.columns:
            return {"is_family_with_kids": False, "family_score": 0.0, "family_signals": []}

        score = 0.0
        signals = []

        expenses = df.filter(pl.col("amount") < 0)

        school_spend = _match_spend(expenses, _P_SCHOOL)
        if school_spend > 200:
            score += 30
            signals.append(f"school_spend=R${school_spend:.0f}")

        baby_spend = _match_spend(expenses, _P_BABY)
        if baby_spend > 100:
            score += 25
            signals.append(f"baby_products=R${baby_spend:.0f}")

        pediatric_count = _match_count(expenses, _P_PEDIATRIC)
        if pediatric_count >= 2:
            score += 20
            signals.append(f"pediatric_visits={pediatric_count}")

        kids_clothing = _match_spend(expenses, _P_KIDS_CLOTHING)
        if kids_clothing > 100:
            score += 15
            signals.append(f"kids_clothing=R${kids_clothing:.0f}")

        kids_entertainment = _match_count(expenses, _P_KIDS_ENTERT)
        if kids_entertainment >= 2:
            score += 10
            signals.append(f"kids_entertainment={kids_entertainment}")

        family_score = round(min(score, 100.0), 1)

        return {
            "is_family_with_kids": family_score >= 40,
            "family_score": family_score,
            "family_signals": signals,
        }
