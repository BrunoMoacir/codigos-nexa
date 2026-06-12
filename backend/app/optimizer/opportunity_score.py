# app/optimizer/opportunity_score.py
# OpportunityScoreCalculator — dinheiro recuperável real, ajustado por confiança
#
# opportunity_score (R$/ano) =
#     net_gain_expected
#     × profile_confidence   (confiança do perfil, 0–1)
#     × pattern_stability    (estabilidade do padrão de gasto, 0–1)
#     × spending_recurrence  (recorrência do gasto nas categorias, 0–1)
#     × card_eligibility     (elegibilidade do cartão, 0–1)
#
# Resultado em R$/ano: quanto o usuário pode recuperar de fato, não apenas no papel.

from __future__ import annotations

from app.optimizer.models import CardSimulationResult
from app.optimizer.profiler import UserProfile

# Peso da confiança do simulador vs. confiança da renda no fator profile_confidence.
# 60/40 porque o simulador já incorpora cobertura de dados, estabilidade e categoria;
# a renda contribui com a dimensão de capacidade de pagamento da anuidade.
_SIM_CONF_WEIGHT = 0.60
_INCOME_CONF_WEIGHT = 0.40

# Crédito parcial para categorias CAINDO: o gasto ainda existe, mas encolhendo.
_DECLINING_CREDIT = 0.40


def compute_opportunity_score(
    result: CardSimulationResult,
    profile: UserProfile,
) -> tuple[float, dict]:
    """
    Calcula o score de oportunidade financeira real para um cartão.

    Retorna (opportunity_score, breakdown_dict).
    - opportunity_score: R$/ano recuperável ajustado pelos quatro fatores (0 se ganho ≤ 0).
    - breakdown_dict: fatores intermediários para explicabilidade e auditoria.
    """
    if result.net_gain_expected <= 0:
        return 0.0, {
            "net_gain_expected": result.net_gain_expected,
            "profile_confidence": 0.0,
            "pattern_stability": 0.0,
            "spending_recurrence": 0.0,
            "card_eligibility": result.eligibility_score,
            "opportunity_score": 0.0,
        }

    # ── Fator 1: confiança do perfil ─────────────────────────────────────────
    # Combina a confiança do simulador (cobertura, estabilidade, categoria) com
    # a confiança da renda (capacidade real de pagar a anuidade).
    sim_conf = result.confidence_score
    income_conf = (
        profile.income_profile.confidence
        if profile.income_profile is not None
        else 0.5
    )
    profile_confidence = _SIM_CONF_WEIGHT * sim_conf + _INCOME_CONF_WEIGHT * income_conf

    # ── Fator 2: estabilidade do padrão ──────────────────────────────────────
    # spending_stability (0–1) mede consistência mês a mês via coeficiente de variação.
    pattern_stability = profile.spending_stability

    # ── Fator 3: recorrência do gasto ─────────────────────────────────────────
    # Proporção do gasto mensal que está em categorias estáveis ou crescentes.
    # Categorias desaparecendo (DESAPARECENDO) não contribuem — o gasto pode não existir
    # quando o cartão chegar. Categorias em queda recebem crédito parcial.
    trends = getattr(profile, "category_trends", {})
    if not trends:
        spending_recurrence = profile.spending_stability
    else:
        total_spend = 0.0
        stable_spend = 0.0
        for cat, data in trends.items():
            if cat.startswith("_"):
                continue  # pula _income, _credit, _debit, _pix, _delivery
            current = data.get("current_monthly", 0.0)
            direction = data.get("direction", "ESTAVEL")
            total_spend += current
            if direction in ("ESTAVEL", "SUBINDO", "REEMERGINDO"):
                stable_spend += current
            elif direction == "CAINDO":
                stable_spend += current * _DECLINING_CREDIT

        if total_spend > 0:
            spending_recurrence = min(stable_spend / total_spend, 1.0)
        else:
            spending_recurrence = profile.spending_stability

    # ── Fator 4: elegibilidade do cartão ─────────────────────────────────────
    card_eligibility = result.eligibility_score

    # ── Score final ──────────────────────────────────────────────────────────
    score = (
        result.net_gain_expected
        * profile_confidence
        * pattern_stability
        * spending_recurrence
        * card_eligibility
    )
    score = max(score, 0.0)

    breakdown = {
        "net_gain_expected": round(result.net_gain_expected, 2),
        "profile_confidence": round(profile_confidence, 3),
        "pattern_stability": round(pattern_stability, 3),
        "spending_recurrence": round(spending_recurrence, 3),
        "card_eligibility": round(card_eligibility, 3),
        "opportunity_score": round(score, 2),
    }

    return round(score, 2), breakdown
