"""
app/architect/simulators/strategy_selector.py - Seleção e ajuste de estratégia

Extraído de StrategyEngine para separar o ranking de estratégias e os
ajustes de perfil de risco do orquestrador de simulação.
"""

from typing import Dict, Any, Optional

from app.architect.models import (
    AssetType,
    EfficiencyAnalysis,
    RiskProfile,
    SimulationRequest,
    StrategyType,
)
from app.architect.utils.formatters import format_currency


def pick_efficient_strategy(
    request: SimulationRequest,
    results: Dict[StrategyType, Dict[str, Any]],
    financial_winner: StrategyType,
) -> Optional[EfficiencyAnalysis]:
    """
    Seleciona a estratégia com melhor equilíbrio custo × velocidade × orçamento.

    Score (0.0–1.0):
      40% → capital_loss: extra pago além do valor do bem (juros/taxas)
      35% → speed: meses até a posse
      25% → budget: parcela / orçamento mensal

    Retorna None quando a estratégia eficiente coincide com financial_winner.
    """
    if not results:
        return None

    budget = request.max_monthly_budget or 0.0

    acquisition_types = {
        StrategyType.FINANCING,
        StrategyType.CONSORTIUM,
        StrategyType.FINANCING_RENTAL,
        StrategyType.CONSORTIUM_SELIC_RENTAL,
    }
    candidates = {
        stype: r for stype, r in results.items()
        if stype in acquisition_types
    }

    if not candidates:
        return None

    if budget > 0:
        candidates = {
            stype: r for stype, r in candidates.items()
            if float(r.get("monthly_payment", 0.0)) <= budget * 1.20
        }

    if not candidates:
        return None

    all_months = [max(1, r.get("months", 1)) for r in candidates.values()]
    max_months = max(all_months)

    scored: list[tuple[float, StrategyType, Dict[str, Any]]] = []
    for stype, result in candidates.items():
        target = request.target_amount
        total_cost = float(result.get("expected_cost", target))
        monthly = float(result.get("monthly_payment", 0.0))
        months = max(1, result.get("months", 1))

        total_out = request.down_payment + total_cost
        capital_loss_raw = max(0.0, (total_out - target) / target)
        score_capital = 1.0 - min(capital_loss_raw, 1.0)

        score_speed = 1.0 - (months - 1) / max(max_months - 1, 1)
        score_speed = max(0.0, score_speed)

        if budget > 0:
            budget_ratio = monthly / budget
        else:
            budget_ratio = 0.5
        score_budget = 1.0 - min(budget_ratio, 1.0)

        score = round(0.40 * score_capital + 0.35 * score_speed + 0.25 * score_budget, 4)
        scored.append((score, stype, result))

    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_type, best_result = scored[0]

    if best_type == financial_winner:
        return None

    target = request.target_amount
    total_cost = float(best_result.get("expected_cost", target))
    monthly = float(best_result.get("monthly_payment", 0.0))
    months = max(1, best_result.get("months", 1))
    total_out_of_pocket = request.down_payment + total_cost
    capital_loss_pct = round(max(0.0, (total_out_of_pocket - target) / target) * 100, 1)
    budget_commitment_pct = round((monthly / budget * 100) if budget > 0 else 0.0, 1)

    rp = request.risk_profile
    rs = request.risk_score
    if rs is not None:
        ready_budget = 25.0 + rs * 25.0
        warn_budget  = 40.0 + rs * 35.0
        ready_loss   = 50.0 + rs * 50.0
        warn_loss    = 80.0 + rs * 70.0
        profile_label = f"score {rs:.2f}"
    else:
        if rp == RiskProfile.CONSERVADOR:
            ready_budget, warn_budget = 25.0, 40.0
            ready_loss, warn_loss = 50.0, 80.0
        elif rp == RiskProfile.AGRESSIVO:
            ready_budget, warn_budget = 50.0, 75.0
            ready_loss, warn_loss = 100.0, 150.0
        else:
            ready_budget, warn_budget = 35.0, 60.0
            ready_loss, warn_loss = 80.0, 120.0
        profile_label = rp.value

    if budget_commitment_pct > warn_budget or capital_loss_pct > warn_loss:
        readiness_flag = "AGUARDAR"
    elif budget_commitment_pct > ready_budget or capital_loss_pct > ready_loss:
        readiness_flag = "ATENCAO"
    else:
        readiness_flag = "PRONTO"

    fmt = format_currency
    strategy_labels = {
        StrategyType.FINANCING:               "Financiamento",
        StrategyType.CONSORTIUM:              "Consórcio",
        StrategyType.SAVE_INVEST:             "Poupar e Investir",
        StrategyType.FINANCING_RENTAL:        "Financiamento + Aluguel",
        StrategyType.CONSORTIUM_SELIC_RENTAL: "Consórcio + SELIC + Aluguel",
    }
    fin_label = strategy_labels.get(financial_winner, str(financial_winner))
    eff_label = strategy_labels.get(best_type, str(best_type))

    if readiness_flag == "AGUARDAR":
        timing_prefix = (
            f"Ainda não é a hora ideal: a parcela de {fmt(monthly)}/mês representa "
            f"{budget_commitment_pct:.0f}% do seu orçamento"
            + (f" e o custo extra é de {capital_loss_pct:.0f}%" if capital_loss_pct > warn_loss else "")
            + f" — acima do confortável para o perfil {profile_label}. "
            f"Considere aumentar a entrada ou aguardar mais capacidade de poupança. "
        )
    elif readiness_flag == "ATENCAO":
        timing_prefix = (
            f"Viável, mas exige disciplina: parcela de {fmt(monthly)}/mês "
            f"({budget_commitment_pct:.0f}% do orçamento). "
        )
    else:
        timing_prefix = ""

    if best_type == StrategyType.CONSORTIUM:
        body = (
            f"O {eff_label} equilibra custo e tempo: {capital_loss_pct:.0f}% de custo extra "
            f"(taxa de administração), posse em ~{months} meses. "
            f"Melhor que o {fin_label} em perda de capital."
        )
    elif best_type == StrategyType.FINANCING:
        body = (
            f"O {eff_label} entrega o bem imediatamente ({capital_loss_pct:.0f}% de juros). "
            f"Escolha quando tempo importa mais que custo total."
        )
    elif best_type in (StrategyType.FINANCING_RENTAL, StrategyType.CONSORTIUM_SELIC_RENTAL):
        body = (
            f"O {eff_label} usa o aluguel para reduzir o desembolso real: "
            f"posse em ~{months} meses, {capital_loss_pct:.0f}% de custo líquido extra."
        )
    else:
        body = (
            f"O {eff_label} oferece o melhor equilíbrio entre perda de capital "
            f"({capital_loss_pct:.0f}%), prazo ({months} meses) e parcela ({fmt(monthly)}/mês)."
        )

    rationale = (timing_prefix + body).strip()

    return EfficiencyAnalysis(
        strategy_type=best_type,
        efficiency_score=best_score,
        capital_loss_pct=capital_loss_pct,
        months_to_acquire=months,
        budget_commitment_pct=budget_commitment_pct,
        monthly_payment=round(monthly, 2),
        total_cost=round(total_cost, 2),
        readiness_flag=readiness_flag,
        rationale=rationale,
    )


def apply_risk_profile_adjustment(
    request: SimulationRequest,
    best_strategy: StrategyType,
    strategies: Dict[StrategyType, float],
) -> tuple[StrategyType, list[str]]:
    """
    Ajusta a estratégia recomendada com base no perfil/score de risco.

    Quando risk_score está disponível, usa limiares contínuos:
      - Perfil "conservador" (score < 0.35):
          · Veículo: evita FINANCING (bem depreciativo).
          · Outros: requer vantagem de NPV ≥ min_advantage_pct sobre SAVE_INVEST.
            min_advantage_pct = 25% × (1 − score/0.35) → suaviza a fronteira.
      - Perfil "moderado/arrojado" (score ≥ 0.35): sem ajuste, NPV decide.

    Sem risk_score: comportamento legado por enum CONSERVADOR/MODERADO/AGRESSIVO.
    """
    rs = request.risk_score
    is_conservative = (
        rs < 0.35 if rs is not None
        else request.risk_profile == RiskProfile.CONSERVADOR
    )

    if not is_conservative:
        return best_strategy, []

    if best_strategy not in (
        StrategyType.FINANCING,
        StrategyType.FINANCING_RENTAL,
        StrategyType.CONSORTIUM,
    ):
        return best_strategy, []

    warnings: list[str] = []
    npv_fin  = strategies.get(StrategyType.FINANCING, 0.0)
    npv_inv  = strategies.get(StrategyType.SAVE_INVEST, float("-inf"))
    npv_cons = strategies.get(StrategyType.CONSORTIUM)

    if best_strategy == StrategyType.CONSORTIUM:
        is_very_conservative = (
            rs < 0.25 if rs is not None
            else request.risk_profile == RiskProfile.CONSERVADOR
        )
        if (
            is_very_conservative
            and npv_cons is not None
            and npv_inv != float("-inf")
        ):
            abs_diff = abs(npv_inv) - abs(npv_cons)
            ref = abs(npv_inv) if npv_inv != 0 else 1.0
            advantage_pct = abs_diff / ref
            if advantage_pct < 0.10:
                profile_label = f"score={rs:.2f}" if rs is not None else request.risk_profile.value
                warnings.append(
                    f"Perfil muito conservador ({profile_label}): vantagem do consórcio "
                    f"sobre Poupar/Investir é de {advantage_pct:.0%} (mínimo: 10%) "
                    "— preferindo Poupar/Investir para evitar compromisso de longo prazo."
                )
                return StrategyType.SAVE_INVEST, warnings
        return best_strategy, warnings

    if request.asset_type == AssetType.VEICULO:
        if npv_cons is not None and npv_cons > npv_inv:
            adjusted = StrategyType.CONSORTIUM
            reason = "consórcio (sem juros bancários)"
        else:
            adjusted = StrategyType.SAVE_INVEST
            reason = "Poupar/Investir (sem endividamento)"
        profile_label = f"score={rs:.2f}" if rs is not None else request.risk_profile.value
        warnings.append(
            f"Perfil conservador ({profile_label}): financiamento de veículo evitado "
            f"(bem depreciativo — perde ~15-20% ao ano). Recomendado: {reason}."
        )
        return adjusted, warnings

    if npv_inv == float("-inf"):
        return best_strategy, warnings

    if rs is not None:
        min_advantage_pct = 0.25 - rs * (0.10 / 0.35)
    else:
        min_advantage_pct = 0.20

    abs_diff = abs(npv_inv) - abs(npv_fin)
    ref = abs(npv_inv) if npv_inv != 0 else 1.0
    advantage_pct = abs_diff / ref

    if advantage_pct < min_advantage_pct:
        profile_label = f"score={rs:.2f}" if rs is not None else request.risk_profile.value
        warnings.append(
            f"Perfil conservador ({profile_label}): vantagem do financiamento sobre "
            f"Poupar/Investir é de {advantage_pct:.0%} (mínimo: {min_advantage_pct:.0%}) "
            "— preferindo Poupar/Investir para evitar endividamento."
        )
        return StrategyType.SAVE_INVEST, warnings

    return best_strategy, warnings
