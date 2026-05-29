"""
app/architect/simulators/action_plan_builder.py - Gerador de plano de ação

Extraído de StrategyEngine para separar a lógica de construção
do plano de ação do orquestrador de simulação.
"""

from typing import Dict, Any, List

from app.architect.models import ActionStep, AssetType, SimulationRequest, StrategyType
from app.architect.utils.formatters import format_currency


def generate_action_plan(
    strategy: StrategyType,
    scenario: Dict[str, Any],
    req: SimulationRequest,
) -> List[ActionStep]:
    """Gera passos práticos baseados na estratégia escolhida."""
    steps: List[ActionStep] = []

    if strategy == StrategyType.FINANCING_RENTAL:
        steps.append(ActionStep(
            step=1,
            action=f"Reunir documentação para financiamento de {req.asset_type.value.lower()} com plano de aluguel",
            is_critical=True,
        ))
        if req.down_payment > 0:
            steps.append(ActionStep(
                step=2,
                action=f"Separar entrada de {format_currency(req.down_payment)}",
                amount=req.down_payment,
                is_critical=True,
            ))
        gross = scenario["monthly_payment"]
        rental = scenario["monthly_rental_income"]
        net = scenario["monthly_net_cost"]
        coverage_pct = rental / gross * 100 if gross > 0 else 0
        if scenario["is_self_sustaining"]:
            steps.append(ActionStep(
                step=len(steps) + 1,
                action=(
                    f"Financiar e imediatamente colocar o imóvel para alugar — "
                    f"aluguel de {format_currency(rental)}/mês cobre 100% da parcela de "
                    f"{format_currency(gross)}/mês. Imóvel se paga sozinho."
                ),
                amount=gross,
            ))
        else:
            steps.append(ActionStep(
                step=len(steps) + 1,
                action=(
                    f"Financiar e colocar o imóvel para alugar por {format_currency(rental)}/mês — "
                    f"cobre {coverage_pct:.0f}% da parcela. "
                    f"Seu desembolso real: {format_currency(net)}/mês"
                ),
                amount=net,
            ))
        steps.append(ActionStep(
            step=len(steps) + 1,
            action=(
                f"Custo líquido real da aquisição após {scenario['months']} meses de aluguel: "
                f"{format_currency(scenario['net_acquisition_cost'])}"
            ),
        ))

    elif strategy == StrategyType.CONSORTIUM_SELIC_RENTAL:
        selic_m = scenario.get("monthly_selic_contribution", 0.0)
        rental = scenario["monthly_rental_income"]
        gross = scenario["monthly_payment"]
        net = scenario["monthly_net_cost"]
        steps.append(ActionStep(
            step=1,
            action="Aderir ao consórcio e investir a entrada disponível na SELIC enquanto aguarda contemplação",
            is_critical=True,
        ))
        if req.down_payment > 0:
            steps.append(ActionStep(
                step=2,
                action=(
                    f"Aplicar {format_currency(req.down_payment)} em Tesouro Selic — "
                    f"rende aprox. {format_currency(selic_m)}/mês para complementar o aluguel"
                ),
                amount=req.down_payment,
                is_critical=True,
            ))
        if scenario["is_self_sustaining"]:
            steps.append(ActionStep(
                step=len(steps) + 1,
                action=(
                    f"Aluguel ({format_currency(rental)}/mês) + SELIC ({format_currency(selic_m)}/mês) "
                    f"cobrem 100% das parcelas do consórcio ({format_currency(gross)}/mês) — "
                    f"operação AUTO-SUSTENTÁVEL sem desembolso mensal"
                ),
                amount=gross,
            ))
        else:
            steps.append(ActionStep(
                step=len(steps) + 1,
                action=(
                    f"Aluguel ({format_currency(rental)}/mês) + SELIC ({format_currency(selic_m)}/mês) "
                    f"cobrem parcialmente as parcelas ({format_currency(gross)}/mês). "
                    f"Desembolso real: {format_currency(net)}/mês"
                ),
                amount=net,
            ))
        steps.append(ActionStep(
            step=len(steps) + 1,
            action=f"Aguardar contemplação no consórcio (média esperada: {scenario['months']} meses) e usar a carta para comprar o imóvel",
        ))

    elif strategy == StrategyType.FINANCING:
        steps.append(
            ActionStep(
                step=1,
                action=f"Reunir documentação para financiamento de {req.asset_type.value.lower()}",
                is_critical=True,
            )
        )
        if req.down_payment > 0:
            steps.append(
                ActionStep(
                    step=2,
                    action=f"Separar entrada de {format_currency(req.down_payment)}",
                    amount=req.down_payment,
                    is_critical=True,
                )
            )
        steps.append(
            ActionStep(
                step=len(steps) + 1,
                action=f"Pagar parcelas mensais de aprox. {format_currency(scenario['monthly_payment'])}",
                amount=scenario["monthly_payment"],
            )
        )
        if req.asset_type == AssetType.IMOVEL and req.expected_rental_income:
            rental = req.expected_rental_income
            payment = scenario["monthly_payment"]
            coverage = rental / payment * 100 if payment > 0 else 0
            out_of_pocket = max(payment - rental, 0.0)
            if rental >= payment:
                rental_action = (
                    f"Alugar o imóvel por {format_currency(rental)}/mês — cobre 100% da parcela "
                    f"e gera {format_currency(rental - payment)}/mês de renda extra enquanto quita o financiamento"
                )
            else:
                rental_action = (
                    f"Alugar o imóvel por {format_currency(rental)}/mês — cobre {coverage:.0f}% da parcela. "
                    f"Seu custo real mensal cai para {format_currency(out_of_pocket)}"
                )
            steps.append(
                ActionStep(
                    step=len(steps) + 1,
                    action=rental_action,
                    amount=rental,
                )
            )

    elif strategy == StrategyType.CONSORTIUM:
        steps.append(
            ActionStep(
                step=1,
                action="Aderir a um grupo de consórcio em andamento",
                is_critical=True,
            )
        )
        if req.down_payment > 0:
            steps.append(
                ActionStep(
                    step=2,
                    action=f"Ofertar lance de {format_currency(req.down_payment)} para antecipar contemplação",
                    amount=req.down_payment,
                    is_critical=True,
                )
            )
        steps.append(
            ActionStep(
                step=len(steps) + 1,
                action=f"Aguardar contemplação (média esperada: {scenario['months']} meses)",
            )
        )
        if req.asset_type == AssetType.IMOVEL and req.expected_rental_income:
            rental = req.expected_rental_income
            payment = scenario["monthly_payment"]
            coverage = rental / payment * 100 if payment > 0 else 0
            out_of_pocket = max(payment - rental, 0.0)
            if rental >= payment:
                rental_action = (
                    f"Após contemplação, colocar o imóvel para alugar por "
                    f"{format_currency(rental)}/mês — o aluguel cobre 100% da parcela "
                    f"e ainda gera {format_currency(rental - payment)}/mês de renda extra"
                )
            else:
                rental_action = (
                    f"Após contemplação, colocar o imóvel para alugar por "
                    f"{format_currency(rental)}/mês — cobre {coverage:.0f}% da parcela. "
                    f"Seu desembolso real cai para {format_currency(out_of_pocket)}/mês"
                )
            steps.append(
                ActionStep(
                    step=len(steps) + 1,
                    action=rental_action,
                    amount=rental,
                )
            )

    else:  # SAVE_INVEST
        steps.append(
            ActionStep(
                step=1,
                action="Abrir conta em corretora de taxa zero para investimentos",
                is_critical=True,
            )
        )
        steps.append(
            ActionStep(
                step=2,
                action=f"Configurar aplicação automática mensal de {format_currency(scenario['monthly_payment'])} em CDB 100% CDI",
                amount=scenario["monthly_payment"],
                is_critical=True,
            )
        )
        months_label = scenario.get("months", req.financing_months)
        fv_real    = scenario.get("fv_real")
        fv_nominal = scenario.get("fv_nominal")
        if fv_real and fv_nominal and abs(fv_real - fv_nominal) > 500:
            inflation_note = (
                f" (Em poder de compra de hoje: {format_currency(fv_real)} — "
                f"a inflação corroi {format_currency(fv_nominal - fv_real)} do valor nominal.)"
            )
        else:
            inflation_note = ""
        steps.append(
            ActionStep(
                step=3,
                action=f"Resgatar valor total em {months_label} meses para compra à vista{inflation_note}",
            )
        )

    return steps
