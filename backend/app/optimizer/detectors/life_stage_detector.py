# app/optimizer/detectors/life_stage_detector.py
"""
LifeStageDetector — infere o estágio de vida do usuário a partir de sinais combinados.

Estágios detectados:
    FAMILIA_BEBE:        baby + farmácia + educação infantil → família com filho pequeno
    NOMADE_DIGITAL:      airbnb + coworking + viagens frequentes → nômade digital
    INVESTIDOR_PREMIUM:  corretora + renda alta + baixa dívida → investidor premium
    SOLTEIRO_URBANO:     delivery alto + pouco supermercado → solteiro/urbano

Cada estágio tem um score 0–1 calculado por combinação de sinais do UserProfile.
O estágio com maior score ≥ _PRIMARY_THRESHOLD é retornado como primário.
Abaixo do threshold, retorna NAO_IDENTIFICADO.

Opera exclusivamente sobre campos já derivados do UserProfile — não precisa de
acesso ao DataFrame de transações. Deve ser chamado DEPOIS de FamilyDetector,
TravelDetector, InvestorDetector e LifestyleClassifier.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from app.optimizer.constants import (
    LIFE_STAGE_FAMILIA_BEBE,
    LIFE_STAGE_NOMADE_DIGITAL,
    LIFE_STAGE_INVESTIDOR_PREMIUM,
    LIFE_STAGE_SOLTEIRO_URBANO,
    LIFE_STAGE_NAO_IDENTIFICADO,
    LIFE_STAGE_PRIMARY_THRESHOLD as _PRIMARY_THRESHOLD,
)

if TYPE_CHECKING:
    from app.optimizer.profiler import UserProfile

# Re-export para imports externos que já usam este módulo como fonte dos nomes
__all__ = [
    "LIFE_STAGE_FAMILIA_BEBE",
    "LIFE_STAGE_NOMADE_DIGITAL",
    "LIFE_STAGE_INVESTIDOR_PREMIUM",
    "LIFE_STAGE_SOLTEIRO_URBANO",
    "LIFE_STAGE_NAO_IDENTIFICADO",
    "LifeStageDetector",
    "refine_with_life_events",
]


class LifeStageDetector:
    """
    Classifica o UserProfile em um estágio de vida predominante usando combinação de sinais.

    Retorna:
        life_stage:           estágio primário (o de maior score ≥ 0.40)
        life_stage_confidence: score do estágio primário (0.0 quando NAO_IDENTIFICADO)
        life_stage_scores:    afinidade 0.0–1.0 por estágio para uso downstream
    """

    def detect(self, profile: "UserProfile") -> dict:
        scores = {
            LIFE_STAGE_FAMILIA_BEBE:       self._score_familia_bebe(profile),
            LIFE_STAGE_NOMADE_DIGITAL:     self._score_nomade_digital(profile),
            LIFE_STAGE_INVESTIDOR_PREMIUM: self._score_investidor_premium(profile),
            LIFE_STAGE_SOLTEIRO_URBANO:    self._score_solteiro_urbano(profile),
        }

        primary = max(scores, key=lambda k: scores[k])

        if scores[primary] < _PRIMARY_THRESHOLD:
            primary = LIFE_STAGE_NAO_IDENTIFICADO
            confidence = 0.0
        else:
            confidence = round(scores[primary], 3)

        return {
            "life_stage": primary,
            "life_stage_confidence": confidence,
            "life_stage_scores": {k: round(v, 3) for k, v in scores.items()},
        }

    # ─── Scorers ──────────────────────────────────────────────────────────────

    def _score_familia_bebe(self, profile: "UserProfile") -> float:
        """
        Família com filho pequeno: is_family_with_kids + farmácia + educação infantil.

        Sinal primário: FamilyDetector (is_family_with_kids + family_score).
        Reforços: gasto em farmácia (produtos de bebê) e educação (creche/escola).
        """
        if getattr(profile, "is_family_with_kids", False):
            family_s = getattr(profile, "family_score", 0.0)
            score = 0.45 + min(family_s / 100, 1.0) * 0.35
        else:
            score = 0.0

        pharmacy = profile.spend_by_category.get("farmacia", 0.0)
        if pharmacy > 200:
            score += 0.12
        elif pharmacy > 100:
            score += 0.06

        education = profile.spend_by_category.get("educacao", 0.0)
        if education > 200:
            score += 0.08
        elif education > 100:
            score += 0.04

        return min(score, 1.0)

    def _score_nomade_digital(self, profile: "UserProfile") -> float:
        """
        Nômade digital: Airbnb regular + viagens frequentes + ferramentas SaaS/coworking.

        Sinal primário: is_digital_nomad (já detectado pelo TravelDetector T2.5).
        Reforços: is_airbnb_user, travel_spend, subscription_burn, coworking spend.
        """
        if getattr(profile, "is_digital_nomad", False):
            return 0.85

        score = 0.0

        if getattr(profile, "is_airbnb_user", False):
            score += 0.30

        travel = getattr(profile, "travel_spend_monthly", 0.0)
        if travel > 800:
            score += 0.25
        elif travel > 400:
            score += 0.15
        elif travel > 200:
            score += 0.08

        # Subscription burn como proxy de trabalho remoto (SaaS, Adobe, Figma, etc.)
        subscriptions = getattr(profile, "subscription_burn_monthly", 0.0)
        if subscriptions > 150:
            score += 0.15
        elif subscriptions > 80:
            score += 0.08

        # Coworking: normalmente cai em "outros" (L2→L1), mas alguns bancos enviam L1 explícito
        coworking = profile.spend_by_category.get("coworking", 0.0)
        if coworking > 100:
            score += 0.20

        return min(score, 1.0)

    def _score_investidor_premium(self, profile: "UserProfile") -> float:
        """
        Investidor premium: corretora ativa + renda alta + baixo comprometimento de renda.

        Sinal primário: investor_type ATIVO ou DIVERSIFICADO (InvestorDetector).
        Reforços: renda mensal líquida > R$7k, committed_percentage baixo, savings_rate alto.

        Gate duro: sem atividade de corretora (investor_type="NONE") → score=0 independente
        da renda. Renda alta sem investir não é perfil de investidor premium.
        """
        investor_type = getattr(profile, "investor_type", "NONE")
        if investor_type == "NONE":
            return 0.0

        score = 0.0
        if investor_type in ("ATIVO", "DIVERSIFICADO"):
            score += 0.40
        elif investor_type == "CASUAL":
            score += 0.15

        monthly_income = 0.0
        ip = getattr(profile, "income_profile", None)
        if ip is not None and getattr(ip, "monthly_net_income", 0.0) > 0:
            monthly_income = ip.monthly_net_income
        else:
            monthly_income = getattr(profile, "estimated_monthly_income", 0.0)

        if monthly_income > 12_000:
            score += 0.30
        elif monthly_income > 7_000:
            score += 0.20
        elif monthly_income > 4_000:
            score += 0.10

        # Baixo comprometimento = baixa dívida recorrente
        committed = getattr(profile, "committed_percentage", 1.0)
        if committed < 0.20:
            score += 0.20
        elif committed < 0.35:
            score += 0.10

        savings_rate = getattr(profile, "savings_rate", 0.0)
        if savings_rate > 20:
            score += 0.10
        elif savings_rate > 10:
            score += 0.05

        return min(score, 1.0)

    def _score_solteiro_urbano(self, profile: "UserProfile") -> float:
        """
        Solteiro/urbano: delivery alto + pouco supermercado = come fora, vive solo.

        Sinais: delivery_monthly >> supermercado, subscription_burn, merchant_diversity.
        Usa category_trends._delivery quando disponível (mais preciso que L1 alimentacao).
        """
        score = 0.0

        # Ausência de sinal familiar reforça o perfil
        if not getattr(profile, "is_family_with_kids", False):
            score += 0.15

        # Delivery spend: category_trends._delivery é mais preciso (L2 separado de restaurante)
        trends = getattr(profile, "category_trends", {})
        delivery_monthly = trends.get("_delivery", {}).get("current_monthly", 0.0)
        if delivery_monthly == 0:
            delivery_monthly = profile.spend_by_category.get("delivery", 0.0)

        supermercado = profile.spend_by_category.get("supermercado", 0.0)

        if delivery_monthly > 300:
            score += 0.30
        elif delivery_monthly > 150:
            score += 0.20
        elif delivery_monthly > 80:
            score += 0.10

        # Delivery >> supermercado: come fora ou pede, não cozinha em casa
        if delivery_monthly > 0 and supermercado < delivery_monthly * 0.5:
            score += 0.20
        elif supermercado < 150 and not getattr(profile, "is_family_with_kids", False):
            score += 0.08

        # Alto streaming/apps → estilo de vida urbano digital
        subscriptions = getattr(profile, "subscription_burn_monthly", 0.0)
        if subscriptions > 100:
            score += 0.10
        elif subscriptions > 50:
            score += 0.05

        # Diversidade alta de merchants → sai bastante, pouco padrão doméstico
        merchant_div = getattr(profile, "merchant_diversity_score", 0.0)
        if merchant_div > 70:
            score += 0.10
        elif merchant_div > 50:
            score += 0.05

        return min(score, 1.0)


def refine_with_life_events(profile: "UserProfile", life_events: list[dict]) -> None:
    """
    Reforça FAMILIA_BEBE quando LifeEventsDetector detectou evento new_baby recente.

    Chamada em optimizer_service.py APÓS a execução do LifeEventsDetector, onde os
    eventos já foram calculados. O LifeStageDetector só tem acesso ao perfil derivado
    (sem transações brutas), então não consegue consumir o sinal de new_baby diretamente.
    Esta função fecha essa lacuna: se new_baby com confiança ≥ 0.60 for detectado,
    o estágio é promovido/reforçado para FAMILIA_BEBE.

    Modifica profile.life_stage, life_stage_confidence e life_stage_scores in-place.
    """
    new_baby = next(
        (e for e in life_events if e.get("event") == "new_baby" and e.get("confidence", 0.0) >= 0.60),
        None,
    )
    if new_baby is None:
        return

    baby_confidence = float(new_baby["confidence"])

    if profile.life_stage == LIFE_STAGE_FAMILIA_BEBE:
        # Já classificado: eleva a confiança com o reforço do evento
        profile.life_stage_confidence = round(min(profile.life_stage_confidence + 0.10, 1.0), 3)
    else:
        # Promove para FAMILIA_BEBE: new_baby é evidência forte que o detector de perfil
        # pode ter perdido por falta de histórico transacional suficiente
        profile.life_stage = LIFE_STAGE_FAMILIA_BEBE
        profile.life_stage_confidence = round(min(baby_confidence + 0.10, 0.95), 3)

    profile.life_stage_scores[LIFE_STAGE_FAMILIA_BEBE] = profile.life_stage_confidence
