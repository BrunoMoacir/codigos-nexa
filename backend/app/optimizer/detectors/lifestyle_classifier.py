# app/optimizer/detectors/lifestyle_classifier.py

from __future__ import annotations
from app.optimizer.profiler import UserProfile


CLUSTER_EXPLORER_GLOBAL    = "EXPLORADOR_GLOBAL"
CLUSTER_URBAN_FOODIE       = "URBANO_FOODIE"
CLUSTER_INVESTOR           = "INVESTIDOR_CAUTELOSO"
CLUSTER_FAMILY             = "FAMILIA_ESTRUTURADA"
CLUSTER_DIGITAL_NATIVE     = "DIGITAL_NATIVO"
CLUSTER_FINANCIAL_STRESS   = "ESTRESSE_FINANCEIRO"
CLUSTER_MICROEMPREENDEDOR  = "MICROEMPREENDEDOR"
CLUSTER_UNCLASSIFIED       = "NAO_CLASSIFICADO"


class LifestyleClassifier:
    """
    Classifica o UserProfile em um dos clusters de estilo de vida.

    Fase 1: regras determinísticas baseadas em scores dos detectors.
    Fase 3: substituir por modelo ML (HDBSCAN ou K-Means treinado).

    Retorna o cluster primário (string) e um dict de scores de afinidade
    para todos os clusters (0.0–1.0) para uso futuro.
    """

    def classify(self, profile: UserProfile) -> dict:
        scores = {
            CLUSTER_EXPLORER_GLOBAL:   self._score_explorer(profile),
            CLUSTER_URBAN_FOODIE:      self._score_foodie(profile),
            CLUSTER_INVESTOR:          self._score_investor(profile),
            CLUSTER_FAMILY:            self._score_family(profile),
            CLUSTER_DIGITAL_NATIVE:    self._score_digital_native(profile),
            CLUSTER_FINANCIAL_STRESS:  self._score_financial_stress(profile),
            CLUSTER_MICROEMPREENDEDOR: self._score_mei(profile),
        }

        primary = max(scores, key=lambda k: scores[k])

        # Threshold mínimo — se nenhum cluster tem afinidade > 0.35, não classificar
        if scores[primary] < 0.35:
            primary = CLUSTER_UNCLASSIFIED

        return {
            "lifestyle_cluster": primary,
            "cluster_scores": {k: round(v, 3) for k, v in scores.items()},
        }

    def _score_explorer(self, p: UserProfile) -> float:
        score = 0.0
        score += min(p.travel_frequency_score / 100, 1.0) * 0.50
        score += min(p.international_spend_monthly / 500, 1.0) * 0.30
        score += (1.0 if p.travel_profile in ("FREQUENTE", "INTENSO") else 0.0) * 0.20
        return score

    def _score_foodie(self, p: UserProfile) -> float:
        score = 0.0
        score += min(p.foodie_score / 100, 1.0) * 0.60
        food_spend = p.spend_by_category.get("Alimentação", 0) + p.spend_by_category.get("alimentacao", 0)
        pct_food = food_spend / p.monthly_avg_spend if p.monthly_avg_spend > 0 else 0
        score += min(pct_food * 2, 1.0) * 0.40
        return score

    def _score_investor(self, p: UserProfile) -> float:
        score = 0.0
        score += (1.0 if p.investor_type in ("ATIVO", "DIVERSIFICADO") else
                  0.5 if p.investor_type == "CASUAL" else 0.0) * 0.50
        score += min(p.savings_rate * 2, 1.0) * 0.50
        return score

    def _score_family(self, p: UserProfile) -> float:
        edu_health = (
            p.spend_by_category.get("Saúde", 0)
            + p.spend_by_category.get("Educação", 0)
        )
        edu_health_pct = edu_health / p.monthly_avg_spend if p.monthly_avg_spend > 0 else 0
        score = min(edu_health_pct * 3, 0.6)

        if p.income_profile and p.income_profile.income_pattern == "CLT":
            score += 0.2
        if p.spending_stability > 0.7:
            score += 0.2
        return score

    def _score_digital_native(self, p: UserProfile) -> float:
        score = 0.0
        score += min(p.subscription_burn_monthly / 200, 1.0) * 0.40
        pix_proxy = 1.0 - p.credit_spend_ratio
        score += min(pix_proxy * 1.5, 1.0) * 0.30
        score += min(p.merchant_diversity_score / 80, 1.0) * 0.30
        return score

    def _score_financial_stress(self, p: UserProfile) -> float:
        score = 0.0
        if p.savings_rate < -0.05:
            score += 0.4
        if p.committed_percentage > 0.6:
            score += 0.3
        if p.spending_stability < 0.3:
            score += 0.3
        return score

    def _score_mei(self, p: UserProfile) -> float:
        if p.is_likely_mei:
            return 0.8
        if p.income_profile and p.income_profile.income_pattern in ("PJ", "MIXED"):
            return 0.5
        return 0.0
