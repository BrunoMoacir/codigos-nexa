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
        from app.architect.models import (
            SimulationRequest, AssetType, RiskProfile, StrategyType,
        )
        from app.architect.services.architect_service import ArchitectService

        # Mapear asset_type string para enum
        asset_map = {
            "IMOVEL": AssetType.IMOVEL,
            "VEICULO": AssetType.VEICULO,
            "REFORMA": AssetType.REFORMA,
            "VIAGEM": AssetType.VIAGEM,
        }
        asset_enum = asset_map.get(asset_type.upper(), AssetType.OUTRO)

        risk_map = {
            "conservador": RiskProfile.CONSERVADOR,
            "agressivo": RiskProfile.AGRESSIVO,
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

        request = SimulationRequest(**req_kwargs)

        # Tentar buscar safe_to_spend da F1 para melhorar o cálculo de liquidez
        safe_to_spend_value: Optional[float] = None
        try:
            from app.runner import NexaRunner
            runner = NexaRunner(mode="dev")
            result = runner.run(horizon_days=30)
            if result.get("status") == "success":
                sts = result["projections"].get("safe_to_spend")
                if sts:
                    safe_to_spend_value = sts.safe_to_spend_total
        except Exception as f1_err:
            logger.debug("[Tool] F1 indisponivel para get_financing_simulation: %s", f1_err)
            # LiquidityValidator usara max_monthly_budget como fallback

        service = ArchitectService()
        response = service.simulate(request, safe_to_spend=safe_to_spend_value)

        # Formatar saída para o LLM
        strategy_labels = {
            StrategyType.FINANCING:   "Financiamento Bancário",
            StrategyType.SAVE_INVEST: "Poupar e Investir",
            StrategyType.CONSORTIUM:  "Consórcio",
        }
        recommended = strategy_labels.get(response.recommended_strategy, response.recommended_strategy)

        lines = [
            f"Simulacao de Aquisicao — R$ {target_amount:,.0f} ({asset_type})",
            f"Estrategia Recomendada: {recommended}",
            f"Confianca da Analise: {response.confidence_score:.0%}",
            "-" * 40,
        ]

        # Custos comparados via NPVComparison (custo de cada estratégia em valor presente)
        npv = response.npv
        lines.append("Custos Comparados (NPV — valor presente):")
        lines.append(f"  Financiamento: R$ {npv.financing:,.0f}")
        lines.append(f"  Poupar/Investir: R$ {npv.save_invest:,.0f}")
        if npv.consortium is not None:
            lines.append(f"  Consorcio: R$ {npv.consortium:,.0f}")
        lines.append(
            f"  Custo esperado da estrategia recomendada: R$ {response.costs.expected_cost:,.0f} "
            f"(min: R$ {response.costs.min_cost:,.0f} / max: R$ {response.costs.max_cost:,.0f})"
        )
        lines.append("")

        # Prazo e impacto de liquidez
        lines.append(f"Prazo para aquisicao: {response.months_to_achieve} meses")
        # liquidity_impact é float: fração do safe_to_spend consumida (ex: -0.22 = 22%)
        if response.liquidity_impact != 0.0:
            pct = abs(response.liquidity_impact) * 100
            lines.append(f"Impacto de liquidez: {pct:.0f}% do seu orcamento mensal disponivel")
        lines.append("")

        # Bônus de pontos no cartão (M3.3) — só para financiamento
        if response.card_optimization_bonus:
            b = response.card_optimization_bonus
            lines.append("Bonus de Pontos (M3.3):")
            lines.append(f"  {b.narrative}")
            lines.append(f"  Retorno mensal estimado: R$ {b.monthly_bonus_brl:,.2f}")
            lines.append(f"  Retorno total no prazo: R$ {b.total_bonus_brl:,.2f}")
            lines.append(f"  Reducao efetiva de custo: {b.effective_cost_reduction_pct:.1f}%")
            lines.append("")

        # Plano de alavancagem por aluguel (IMOVEL com expected_rental_income)
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

        # Plano de ação — ActionStep tem: step (int), action (str), deadline (date|None)
        if response.action_plan:
            lines.append("Plano de Acao:")
            for s in response.action_plan[:6]:
                deadline_str = f" — ate {s.deadline}" if s.deadline else ""
                lines.append(f"  {s.step}. {s.action}{deadline_str}")
            lines.append("")

        # Avisos
        if response.warnings:
            lines.append("Avisos:")
            for w in response.warnings[:4]:
                lines.append(f"  - {w}")

        return "\n".join(lines)

    except ValueError as ve:
        return f"Dados insuficientes para simular: {ve}"
    except Exception as e:
        logger.error("[Tool] get_financing_simulation erro: %s", e, exc_info=True)
        return (
            "Nao foi possivel executar a simulacao agora. "
            "Verifique os dados informados (valor do bem, entrada, prazo) e tente novamente."
        )
