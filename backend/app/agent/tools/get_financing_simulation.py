# app/agent/tools/get_financing_simulation.py
"""
Tool: get_financing_simulation
Simula estratégias de aquisição de um bem: Financiamento vs. Poupança/Investimento vs. Consórcio.
Inclui custo total, NPV, impacto de liquidez, plano de ação e bônus de pontos no cartão (M3.3).

Use SEMPRE que o usuário perguntar sobre:
- Comprar um imóvel, carro, reforma ou qualquer bem de alto valor
- Financiamento bancário: parcelas, juros, prazo
- Se vale mais a pena financiar, poupar ou fazer consórcio
- Simulações de conquistas financeiras (F3 — Nexa Architect)
"""
from langchain_core.tools import tool
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def _build_request(
    user_id: str,
    target_amount: float,
    down_payment: float,
    max_monthly_budget: Optional[float],
    asset_type: str,
    financing_months: int,
    risk_profile: str,
    expected_rental_income: Optional[float],
):
    """Monta o SimulationRequest com os enums corretos."""
    from app.architect.models import SimulationRequest, AssetType, RiskProfile

    asset_map = {
        "IMOVEL": AssetType.IMOVEL,
        "VEICULO": AssetType.VEICULO,
        "REFORMA": AssetType.REFORMA,
        "VIAGEM": AssetType.VIAGEM,
    }
    asset_enum = asset_map.get(asset_type.upper(), AssetType.OUTRO)

    risk_map = {
        "conservador": RiskProfile.CONSERVADOR,
        "agressivo":   RiskProfile.AGRESSIVO,
    }
    risk_enum = risk_map.get(risk_profile.lower(), RiskProfile.MODERADO)

    req_kwargs = dict(
        user_id=user_id,
        target_amount=target_amount,
        down_payment=down_payment,
        max_monthly_budget=max_monthly_budget,
        asset_type=asset_enum,
        financing_months=financing_months,
        risk_profile=risk_enum,
        include_consortium=True,
    )
    if expected_rental_income and expected_rental_income > 0 and asset_enum == AssetType.IMOVEL:
        req_kwargs["expected_rental_income"] = expected_rental_income

    return SimulationRequest(**req_kwargs)


def _fetch_user_safe_to_spend(user_id: str) -> Optional[float]:
    """Busca o safe_to_spend real do usuário via pipeline F1. Retorna None se indisponível."""
    try:
        from app.runner import get_runner
        result = get_runner().run_from_db(user_id=user_id, horizon_days=30)
        if result and result.get("status") == "success":
            sts = result["projections"].get("safe_to_spend")
            if sts:
                return sts.safe_to_spend_total
    except Exception as err:
        logger.debug("[Tool] F1 indisponivel para get_financing_simulation: %s", err)
    return None


def _format_output(response, target_amount: float, asset_type: str, down_payment: float) -> str:
    """Formata a SimulationResponse como texto para o LLM."""
    from app.architect.models import StrategyType

    strategy_labels = {
        StrategyType.FINANCING:               "Financiamento Bancário",
        StrategyType.SAVE_INVEST:             "Poupar e Investir",
        StrategyType.CONSORTIUM:              "Consórcio",
        StrategyType.FINANCING_RENTAL:        "Financiamento + Aluguel",
        StrategyType.CONSORTIUM_SELIC_RENTAL: "Consórcio + SELIC + Aluguel",
    }
    recommended = strategy_labels.get(response.recommended_strategy, response.recommended_strategy)

    lines = [
        f"Simulacao de Aquisicao — R$ {target_amount:,.0f} ({asset_type})",
        f"Estrategia Recomendada: {recommended}",
        f"Confianca da Analise: {response.confidence_score:.0%}",
        "-" * 40,
    ]

    npv = response.npv
    lines.append("Custos Comparados (NPV — valor presente):")
    lines.append(f"  Financiamento: R$ {npv.financing:,.0f}")
    lines.append(f"  Poupar/Investir: R$ {npv.save_invest:,.0f}")
    if npv.consortium is not None:
        lines.append(f"  Consorcio: R$ {npv.consortium:,.0f}")
    if npv.financing_rental is not None:
        lines.append(f"  Financiamento+Aluguel (Estrategia 4): R$ {npv.financing_rental:,.0f}")
    if npv.consortium_selic_rental is not None:
        lines.append(f"  Consorcio+SELIC+Aluguel (Estrategia 5): R$ {npv.consortium_selic_rental:,.0f}")
    lines.append(
        f"  Custo esperado da estrategia recomendada: R$ {response.costs.expected_cost:,.0f} "
        f"(min: R$ {response.costs.min_cost:,.0f} / max: R$ {response.costs.max_cost:,.0f})"
    )
    lines.append("")

    lines.append(f"Prazo para aquisicao: {response.months_to_achieve} meses")
    if response.liquidity_impact != 0.0:
        pct = abs(response.liquidity_impact) * 100
        lines.append(f"Impacto de liquidez: {pct:.0f}% do seu orcamento mensal disponivel")
    lines.append("")

    if response.card_optimization_bonus:
        b = response.card_optimization_bonus
        lines.append("Bonus de Pontos (M3.3):")
        lines.append(f"  {b.narrative}")
        lines.append(f"  Retorno mensal estimado: R$ {b.monthly_bonus_brl:,.2f}")
        lines.append(f"  Retorno total no prazo: R$ {b.total_bonus_brl:,.2f}")
        lines.append(f"  Reducao efetiva de custo: {b.effective_cost_reduction_pct:.1f}%")
        lines.append("")

    if response.rental_leverage_plan:
        r = response.rental_leverage_plan
        lines.append("Plano de Alavancagem por Aluguel:")
        lines.append(f"  {r.narrative}")
        lines.append(f"  Aluguel estimado: R$ {r.monthly_rental_income:,.0f}/mes")
        lines.append(f"  Parcela da estrategia: R$ {r.monthly_payment:,.0f}/mes")
        lines.append(f"  Cobertura do aluguel: {r.rental_coverage_pct:.0f}% da parcela")
        if r.is_self_sustaining:
            lines.append(f"  O imovel se paga sozinho — sobram R$ {abs(r.monthly_out_of_pocket):,.0f}/mes")
        else:
            lines.append(f"  Seu desembolso real: R$ {r.monthly_out_of_pocket:,.0f}/mes")
        lines.append(f"  Custo liquido real da aquisicao: R$ {r.net_acquisition_cost:,.0f}")
        lines.append("")

    if response.compound_strategies:
        lines.append("=" * 40)
        lines.append("ESTRATEGIAS DE COMPRA IMEDIATA COM ALUGUEL")
        lines.append("(O imovel trabalha por voce enquanto voce paga)")
        lines.append("=" * 40)
        for leg in response.compound_strategies:
            label = strategy_labels.get(leg.strategy_type, leg.strategy_type.value)
            lines.append(f"")
            lines.append(f"[{label}]")
            lines.append(f"Como funciona:")

            if leg.strategy_type.value == "FINANCING_RENTAL":
                lines.append(
                    f"  1. Voce financia o imovel AGORA (parcela: R$ {leg.monthly_gross_payment:,.0f}/mes)"
                )
                lines.append(
                    f"  2. Coloca o imovel para alugar (renda: R$ {leg.monthly_rental_income:,.0f}/mes)"
                )
                coverage = (
                    leg.monthly_rental_income / leg.monthly_gross_payment * 100
                    if leg.monthly_gross_payment > 0 else 0
                )
                lines.append(
                    f"  3. O aluguel cobre {coverage:.0f}% da parcela — voce paga apenas "
                    f"R$ {leg.monthly_net_cost:,.0f}/mes do bolso"
                )
            elif leg.strategy_type.value == "CONSORTIUM_SELIC_RENTAL":
                lines.append(
                    f"  1. Voce entra no consorcio (parcela: R$ {leg.monthly_gross_payment:,.0f}/mes)"
                )
                lines.append(
                    f"  2. Investe a entrada (R$ {down_payment:,.0f}) na SELIC"
                    f" — rende R$ {leg.monthly_selic_contribution:,.0f}/mes"
                )
                lines.append(
                    f"  3. O aluguel (R$ {leg.monthly_rental_income:,.0f}/mes)"
                    f" + SELIC (R$ {leg.monthly_selic_contribution:,.0f}/mes)"
                    f" = R$ {leg.monthly_rental_income + leg.monthly_selic_contribution:,.0f}/mes para pagar a parcela"
                )
                if leg.monthly_net_cost == 0:
                    lines.append(
                        "  4. RESULTADO: zero desembolso do bolso no inicio — operacao quase auto-sustentavel"
                    )
                else:
                    lines.append(f"  4. Desembolso real estimado: R$ {leg.monthly_net_cost:,.0f}/mes")

            lines.append(f"")
            if leg.is_self_sustaining:
                lines.append(f"  STATUS: AUTO-SUSTENTAVEL — o imovel se paga sozinho")
            else:
                lines.append(f"  STATUS: Desembolso mensal do bolso: R$ {leg.monthly_net_cost:,.0f}/mes")
            lines.append(f"  Custo total de aquisicao (bruto): R$ {leg.total_gross_cost:,.0f}")
            lines.append(f"  Total de aluguel recebido no periodo: R$ {leg.total_rental_income:,.0f}")
            lines.append(f"  Custo LIQUIDO real (o que voce realmente paga): R$ {leg.net_acquisition_cost:,.0f}")
            lines.append(f"  NPV (valor presente do custo): R$ {leg.npv:,.0f}")
        lines.append("")
        lines.append(
            "NOTA: O custo de oportunidade do aluguel perdido ja foi incluido na "
            "comparacao com Poupar/Investir. Aguardar anos acumulando significa "
            "abrir mao de meses/anos de renda de aluguel."
        )
        lines.append("")

    if response.action_plan:
        lines.append("Plano de Acao:")
        for s in response.action_plan[:6]:
            deadline_str = f" — ate {s.deadline}" if s.deadline else ""
            lines.append(f"  {s.step}. {s.action}{deadline_str}")
        lines.append("")

    if response.warnings:
        lines.append("Avisos:")
        for w in response.warnings[:4]:
            lines.append(f"  - {w}")

    return "\n".join(lines)


@tool
def get_financing_simulation(
    user_id: str,
    target_amount: float,
    down_payment: float = 0.0,
    max_monthly_budget: Optional[float] = None,
    asset_type: str = "OUTRO",
    financing_months: int = 48,
    risk_profile: str = "moderado",
    expected_rental_income: Optional[float] = None,
) -> str:
    """
    Simula e compara 3 estratégias para adquirir um bem de alto valor:
    Financiamento bancário, Poupança/Investimento e Consórcio.

    Retorna custos totais, NPV (valor presente líquido), impacto de liquidez mensal,
    estratégia recomendada, plano de ação e — se financiamento — o bônus estimado
    de pontos ao pagar as parcelas no melhor cartão premium do mercado (M3.3).

    Para imóveis, se o usuário mencionar que pretende alugar o imóvel após adquiri-lo,
    use expected_rental_income para calcular o plano de alavancagem por aluguel:
    quanto o aluguel cobre das parcelas e qual o custo líquido real da aquisição.

    Use esta ferramenta quando o usuário perguntar sobre:
    - Comprar imóvel, carro, reforma, viagem ou qualquer bem de alto valor
    - Se vale a pena financiar vs. poupar vs. fazer consórcio
    - Simulação de parcelas, juros totais e custo efetivo
    - Quanto vai pagar a mais no financiamento vs. poupar sozinho
    - Se pode comprar um apartamento, alugar e usar o aluguel para pagar as parcelas

    Args:
        user_id: ID do usuário (obrigatório).
        target_amount: Valor total do bem em R$ (obrigatório).
        down_payment: Valor de entrada disponível em R$ (padrão: 0).
        max_monthly_budget: Orçamento mensal máximo para parcelas em R$ (opcional).
        asset_type: Tipo de bem — IMOVEL, VEICULO, REFORMA, VIAGEM ou OUTRO (padrão: OUTRO).
        financing_months: Prazo do financiamento em meses (padrão: 48).
        risk_profile: Perfil de risco — conservador, moderado ou agressivo (padrão: moderado).
        expected_rental_income: Renda mensal estimada de aluguel em R$ (opcional, só para IMOVEL).
            Ativa o plano de alavancagem: calcula se o aluguel cobre as parcelas.
    """
    logger.info(
        "[Tool] get_financing_simulation user=%s target=R$%.0f asset=%s meses=%d",
        user_id, target_amount, asset_type, financing_months,
    )
    try:
        from app.architect.services.architect_service import ArchitectService

        request = _build_request(
            user_id, target_amount, down_payment, max_monthly_budget,
            asset_type, financing_months, risk_profile, expected_rental_income,
        )
        safe_to_spend_value = _fetch_user_safe_to_spend(user_id)

        response = ArchitectService().simulate(request, safe_to_spend=safe_to_spend_value)
        return _format_output(response, target_amount, asset_type, down_payment)

    except ValueError as ve:
        return f"Dados insuficientes para simular: {ve}"
    except Exception as e:
        logger.error("[Tool] get_financing_simulation erro: %s", e, exc_info=True)
        return (
            "Nao foi possivel executar a simulacao agora. "
            "Verifique os dados informados (valor do bem, entrada, prazo) e tente novamente."
        )
