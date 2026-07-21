"""
app/optimizer/detectors/lifestyle_features.py — Vetor de features do
classificador ML de clusters de estilo de vida.

FONTE ÚNICA: o script de treino (scripts/train_lifestyle_classifier.py) e a
inferência (ml_lifestyle_classifier.py) importam DAQUI — se as features
mudarem, treino e inferência mudam juntos (versão em FEATURES_VERSION;
o modelo carrega a versão com que foi treinado e recusa mismatch).

Todas as features são deriváveis do UserProfile e normalizadas para escalas
comparáveis (0–1 na maioria), espelhando os sinais que as regras do
LifestyleClassifier usam — o modelo é destilado das regras (professor) e
aprende fronteiras suaves + interações entre sinais.
"""

from __future__ import annotations

from app.optimizer.profiler import UserProfile

FEATURES_VERSION = "1.0"

FEATURE_NAMES: list[str] = [
    "travel_freq",            # travel_frequency_score / 100
    "intl_spend_norm",        # min(international_spend_monthly / 500, 1)
    "travel_intense",         # 1 se travel_profile FREQUENTE/INTENSO
    "digital_nomad",          # is_digital_nomad (1/0)
    "airbnb_user",            # is_airbnb_user (1/0)
    "foodie_score",           # foodie_score / 100
    "food_share",             # gasto alimentacao / gasto total (cap 1)
    "investor_level",         # NONE=0, CASUAL=0.5, ATIVO/DIVERSIFICADO=1
    "savings_rate_norm",      # savings_rate% clip(-50..50) / 50  → -1..1
    "edu_health_share",       # (saude+educacao) / gasto total (cap 1)
    "family_with_kids",       # is_family_with_kids (1/0)
    "family_score",           # family_score / 100
    "clt_pattern",            # income_pattern == CLT (1/0)
    "pj_mixed_pattern",       # income_pattern PJ/MIXED (1/0)
    "spending_stability",     # 0–1
    "subscription_burn",      # min(subscription_burn_monthly / 200, 1)
    "pix_ratio",              # 1 - credit_spend_ratio (proxy de débito/PIX)
    "merchant_diversity",     # merchant_diversity_score / 80 (cap 1)
    "committed_pct",          # committed_percentage (0–1)
    "fss_signal",             # SAUDAVEL=0, ATENCAO=0.33, ALERTA=0.66, CRITICO=1
    "is_likely_mei",          # 1/0
]

_FSS_MAP = {"SAUDAVEL": 0.0, "ATENCAO": 0.33, "ALERTA": 0.66, "CRITICO": 1.0}
_INVESTOR_MAP = {"NONE": 0.0, "CASUAL": 0.5, "ATIVO": 1.0, "DIVERSIFICADO": 1.0}


def extract_features(p: UserProfile) -> list[float]:
    """UserProfile → vetor de features na ordem de FEATURE_NAMES."""
    total = p.monthly_avg_spend if p.monthly_avg_spend > 0 else 1.0
    food_share = min(p.spend_by_category.get("alimentacao", 0.0) / total, 1.0)
    edu_health_share = min(
        (p.spend_by_category.get("saude", 0.0) + p.spend_by_category.get("educacao", 0.0))
        / total,
        1.0,
    )
    income_pattern = (
        p.income_profile.income_pattern if p.income_profile is not None else ""
    )

    return [
        min(p.travel_frequency_score / 100.0, 1.0),
        min(p.international_spend_monthly / 500.0, 1.0),
        1.0 if p.travel_profile in ("FREQUENTE", "INTENSO") else 0.0,
        1.0 if getattr(p, "is_digital_nomad", False) else 0.0,
        1.0 if getattr(p, "is_airbnb_user", False) else 0.0,
        min(p.foodie_score / 100.0, 1.0),
        food_share,
        _INVESTOR_MAP.get(p.investor_type, 0.0),
        max(min(p.savings_rate, 50.0), -50.0) / 50.0,
        edu_health_share,
        1.0 if getattr(p, "is_family_with_kids", False) else 0.0,
        min(getattr(p, "family_score", 0.0) / 100.0, 1.0),
        1.0 if income_pattern == "CLT" else 0.0,
        1.0 if income_pattern in ("PJ", "MIXED") else 0.0,
        max(min(p.spending_stability, 1.0), 0.0),
        min(p.subscription_burn_monthly / 200.0, 1.0),
        max(min(1.0 - p.credit_spend_ratio, 1.0), 0.0),
        min(p.merchant_diversity_score / 80.0, 1.0),
        max(min(p.committed_percentage, 1.0), 0.0),
        _FSS_MAP.get(getattr(p, "fss_level", "SAUDAVEL"), 0.0),
        1.0 if p.is_likely_mei else 0.0,
    ]


__all__ = ["extract_features", "FEATURE_NAMES", "FEATURES_VERSION"]
