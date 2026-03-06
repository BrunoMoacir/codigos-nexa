"""
app/architect/simulators/strategy_engine.py - Motor de Decisão da F3

Feature: F3 - Nexa Architect
Version: 1.0.0

Responsabilidade:
    Orquestrar as simulações de Financiamento, Consórcio e Investimento,
    comparar os resultados (NPV, Liquidez, Prazo) e recomendar a melhor estratégia.

Logica de Decisão:
    1. Executa simulações para cada estratégia.
    2. Valida restrições (ex: parcela não pode exceder orçamento).
    3. Calcula NPV de cada fluxo para comparação justa.
    4. Seleciona a estratégia com menor custo financeiro (maior NPV).
       Nota: Como são pagamentos, NPV negativo = custo a valor presente.
       Melhor estratégia = Maior NPV (mais próximo de zero).
"""

from typing import Dict, List, Optional, Any
from datetime import date
import logging
import math

from app.architect.models import (
    SimulationRequest,
    SimulationResponse,
    StrategyType,
    AssetType,
    RiskProfile,
    CostScenario,
    NPVComparison,
    ConsortiumProbability,
    ActionStep,
    RentalLeveragePlan,
    TimingScenario,
)
from app.architect.calculators import financing as fin_calc
from app.architect.calculators import investment as inv_calc
from app.architect.calculators import npv as npv_calc
from app.architect.calculators import consortium as cons_calc
from app.architect.connectors.ipca import deflate as ipca_deflate
from app.architect.utils.formatters import format_currency

logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> float:
    """Converte valor para float, tratando NaN e None."""
    if value is None:
        return 0.0
    fval = float(value)
    if math.isnan(fval) or math.isinf(fval):
        return 0.0
    return fval


class StrategyEngine:
    """
    Motor central de decisão do Nexa Architect.

    Não faz chamadas de rede/banco. Recebe todos os dados necessários
    (request do usuário + taxas de mercado) e processa a matemática pura.
    """

    def simulate(
        self,
        request: SimulationRequest,
        market_rates: Dict[str, float],
    ) -> SimulationResponse:
        """
        Executa a simulação completa e retorna a recomendação.

        Args:
            request: Dados do usuário (target, entrada, orçamento, etc).
            market_rates: Taxas atuais {selic_annual, cdi_annual, best_cet_annual}.

        Returns:
            SimulationResponse com a melhor estratégia e detalhes.
        """
        logger.info(
            "Iniciando simulação para user=%s, target=%s",
            request.user_id,
            request.target_amount,
        )

        selic_annual = market_rates.get("selic_annual", 0.1075)
        selic_monthly = (1 + selic_annual) ** (1 / 12) - 1

        # ── 1. Simular Estratégias ──────────────────────────────────
        fin_result = self._simulate_financing(request, market_rates)
        inv_result = self._simulate_investment(request, market_rates)

        cons_result: Optional[Dict[str, Any]] = None
        if request.include_consortium:
            cons_result = self._simulate_consortium(request, market_rates)

        # ── 2. Comparar NPVs ────────────────────────────────────────
        npv_fin = _safe_float(fin_result["npv"])
        npv_inv = _safe_float(inv_result["npv"])
        npv_cons = _safe_float(cons_result["npv"]) if cons_result else None

        # ── 3. Decisão: maior NPV = menor custo presente ────────────
        strategies: Dict[StrategyType, float] = {
            StrategyType.FINANCING: npv_fin,
            StrategyType.SAVE_INVEST: npv_inv,
        }
        if cons_result and npv_cons is not None:
            strategies[StrategyType.CONSORTIUM] = npv_cons

        ranked = sorted(strategies.items(), key=lambda x: x[1], reverse=True)
        best_strategy = ranked[0][0]

        # ── 3.5. Ajuste por perfil de risco ─────────────────────────
        best_strategy, profile_warnings = self._apply_risk_profile_adjustment(
            request, best_strategy, strategies
        )

        # ── 4. Validação de Restrições (Liquidez) ────────────────────
        budget_limit = request.max_monthly_budget or float("inf")
        final_strategy = best_strategy

        if (
            best_strategy == StrategyType.FINANCING
            and fin_result["monthly_payment"] > budget_limit
        ):
            final_strategy = StrategyType.SAVE_INVEST
            if (
                cons_result
                and cons_result["monthly_payment"] <= budget_limit
                and npv_cons is not None
                and npv_cons > npv_inv
            ):
                final_strategy = StrategyType.CONSORTIUM

        elif (
            best_strategy == StrategyType.CONSORTIUM
            and cons_result
            and cons_result["monthly_payment"] > budget_limit
        ):
            final_strategy = StrategyType.SAVE_INVEST

        # ── 5. Montar resposta ────────────────────────────────────────
        if final_strategy == StrategyType.FINANCING:
            selected = fin_result
        elif final_strategy == StrategyType.CONSORTIUM and cons_result:
            selected = cons_result
        else:
            final_strategy = StrategyType.SAVE_INVEST
            selected = inv_result

        # Liquidez
        monthly_cost = selected["monthly_payment"]
        liquidity_base = request.max_monthly_budget or monthly_cost
        liquidity_impact = (
            -(monthly_cost / liquidity_base) if liquidity_base > 0 else 0.0
        )

        # Meses - financiamento é imediato, mas mínimo 1 pelo model
        months = max(1, selected["months"])

        # ── 4.5. Aviso de depreciação para veículo ───────────────────
        vehicle_warn = self._vehicle_depreciation_warning(request, final_strategy)
        if vehicle_warn:
            profile_warnings.append(vehicle_warn)

        # Action Plan
        action_plan = self._generate_action_plan(
            final_strategy, selected, request
        )

        # Plano de alavancagem por aluguel (apenas imóvel com renda informada)
        rental_leverage_plan: Optional[RentalLeveragePlan] = None
        if (
            request.asset_type == AssetType.IMOVEL
            and request.expected_rental_income is not None
            and request.expected_rental_income > 0
        ):
            rental_leverage_plan = self._compute_rental_leverage_plan(
                monthly_rental_income=request.expected_rental_income,
                monthly_payment=monthly_cost,
                total_cost=float(selected["expected_cost"]),
                months=months,
            )

        return SimulationResponse(
            recommended_strategy=final_strategy,
            costs=CostScenario(
                min_cost=float(selected["min_cost"]),
                expected_cost=float(selected["expected_cost"]),
                max_cost=float(selected["max_cost"]),
            ),
            npv=NPVComparison(
                financing=float(npv_fin),
                consortium=float(npv_cons) if npv_cons is not None else None,
                save_invest=float(npv_inv),
                discount_rate_used=selic_monthly,
            ),
            consortium_probability=(
                cons_result["probability"] if cons_result else None
            ),
            liquidity_impact=round(float(liquidity_impact), 4),
            months_to_achieve=months,
            action_plan=action_plan,
            confidence_score=0.85,
            data_sources=["bacen", "anbima", "market_rates", "internal_models"],
            rental_leverage_plan=rental_leverage_plan,
            warnings=profile_warnings,
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HELPERS DE SIMULAÇÃO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _simulate_financing(
        self, req: SimulationRequest, rates: Dict[str, float]
    ) -> Dict[str, Any]:
        """Simula cenário de financiamento (PRICE ou SAC)."""
        cet_annual = rates.get("best_cet_annual", 0.15)
        selic_monthly = (1 + rates.get("selic_annual", 0.1075)) ** (1 / 12) - 1

        # Calcular pelo método escolhido
        if req.amortization_method.value == "SAC":
            sim = fin_calc.calculate_sac(
                req.principal, cet_annual, req.financing_months
            )
        else:
            sim = fin_calc.calculate_price(
                req.principal, cet_annual, req.financing_months
            )

        # Fluxo de caixa: -Entrada no mês 0, -Parcelas nos meses 1..N
        cashflows = [-req.down_payment]
        for row in sim.schedule:
            cashflows.append(-row["payment"])

        npv_val = npv_calc.calculate_npv(cashflows, selic_monthly)

        return {
            "type": "FINANCING",
            "monthly_payment": sim.monthly_payment,
            "total_cost": sim.total_cost,
            "min_cost": sim.total_cost,
            "expected_cost": sim.total_cost,
            "max_cost": round(sim.total_cost * 1.05, 2),
            "npv": npv_val,
            "months": 1,  # Aquisição imediata (ge=1 no model)
        }

    def _simulate_investment(
        self, req: SimulationRequest, rates: Dict[str, float]
    ) -> Dict[str, Any]:
        """Simula cenário de poupar/investir (CDI) — M3.1: inclui FV real."""
        cdi_annual    = rates.get("cdi_annual",    0.1025)
        selic_monthly = (1 + rates.get("selic_annual", 0.1075)) ** (1 / 12) - 1
        ipca_annual   = rates.get("ipca_annual",   0.045)   # M3.1

        if req.max_monthly_budget:
            monthly_dep = req.max_monthly_budget
            months = inv_calc.calculate_months_needed(
                req.target_amount,
                monthly_dep,
                cdi_annual,
                req.down_payment,
            )
            if months is None:
                months = 120
        else:
            months = req.financing_months
            monthly_dep = inv_calc.calculate_pmt_needed(
                req.target_amount,
                cdi_annual,
                months,
                req.down_payment,
            )

        # Fluxo: -Entrada -Aportes mensais
        cashflows = [-req.down_payment]
        cashflows.extend([-monthly_dep] * months)

        npv_val = npv_calc.calculate_npv(cashflows, selic_monthly)

        # M3.1 — Valor futuro nominal vs. real (poder de compra de hoje)
        fv_nominal = req.target_amount
        fv_real    = ipca_deflate(fv_nominal, ipca_annual, years=months / 12)

        return {
            "type": "SAVE_INVEST",
            "monthly_payment": round(monthly_dep, 2),
            "min_cost": req.target_amount,
            "expected_cost": req.target_amount,
            "max_cost": req.target_amount,
            "npv": npv_val,
            "months": months,
            # M3.1 extras:
            "fv_nominal":    round(fv_nominal, 2),
            "fv_real":       round(fv_real, 2),
            "ipca_annual":   ipca_annual,
        }

    def _simulate_consortium(
        self, req: SimulationRequest, rates: Dict[str, float]
    ) -> Dict[str, Any]:
        """Simula cenário de consórcio via Monte Carlo.

        Usa taxas reais da ABAC (injetadas pelo ArchitectService via market_rates
        desde a Fase 2). Mantém fallbacks para retrocompatibilidade com Fase 1.
        """
        selic_monthly = (1 + rates.get("selic_annual", 0.1075)) ** (1 / 12) - 1

        # Taxas ABAC (Fase 2) — fallback para valores de referência de mercado
        admin_rate        = rates.get("consortium_admin_rate",        0.17)
        cons_months       = int(rates.get("consortium_months",        72))
        reserve_fund_rate = rates.get("consortium_reserve_fund_rate", 0.02)

        sim = cons_calc.calculate_consortium_metrics(
            letter_value=req.target_amount,
            months=cons_months,
            admin_rate=admin_rate,
            reserve_fund_rate=reserve_fund_rate,
            bid_amount=req.down_payment,
        )

        # Fluxo: -Parcelas por N meses
        cashflows = [-sim.monthly_payment] * cons_months
        expected_month = sim.contemplation_month_expected

        # Lance no mês esperado de contemplação
        if expected_month < len(cashflows) and req.down_payment > 0:
            cashflows[expected_month] -= req.down_payment

        npv_val = npv_calc.calculate_npv(cashflows, selic_monthly)

        # Montar ConsortiumProbability
        prob_dict = sim.contemplation_probability
        prob = ConsortiumProbability(
            win_12m=prob_dict.get("12m", 0.0),
            win_24m=prob_dict.get("24m", 0.0),
            win_36m=prob_dict.get("36m", prob_dict.get("half_term", 0.0)),
            expected_months=max(1, expected_month),
            with_lance=(req.down_payment > 0),
        )

        return {
            "type": "CONSORTIUM",
            "monthly_payment": sim.monthly_payment,
            "min_cost": round(sim.total_cost * 0.95, 2),
            "expected_cost": sim.total_cost,
            "max_cost": round(sim.total_cost * 1.10, 2),
            "npv": npv_val,
            "months": max(1, expected_month),
            "probability": prob,
        }

    def _generate_action_plan(
        self,
        strategy: StrategyType,
        scenario: Dict[str, Any],
        req: SimulationRequest,
    ) -> List[ActionStep]:
        """Gera passos práticos baseados na estratégia escolhida."""
        steps: List[ActionStep] = []

        if strategy == StrategyType.FINANCING:
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
            # M3.1 — Adiciona nota sobre poder de compra real se disponível
            months_label = scenario.get("months", req.financing_months)
            fv_real   = scenario.get("fv_real")
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

    @staticmethod
    def _apply_risk_profile_adjustment(
        request: SimulationRequest,
        best_strategy: StrategyType,
        strategies: Dict[StrategyType, float],
    ) -> tuple[StrategyType, list[str]]:
        """
        Ajusta a estratégia recomendada com base no perfil de risco declarado.

        Regras:
        - CONSERVADOR:
            · Veículo (ativo depreciativo): nunca recomenda FINANCING —
              substitui por CONSORTIUM (se disponível e melhor NPV) ou SAVE_INVEST.
            · Outros bens: só mantém FINANCING se a vantagem de NPV sobre
              SAVE_INVEST for >= 20%; abaixo disso prefere SAVE_INVEST.
        - MODERADO: sem ajuste — NPV puro decide.
        - AGRESSIVO: sem ajuste — NPV puro decide (aceita risco maior).

        Returns:
            (estratégia_ajustada, lista_de_warnings)
        """
        if request.risk_profile != RiskProfile.CONSERVADOR:
            return best_strategy, []

        if best_strategy != StrategyType.FINANCING:
            return best_strategy, []

        warnings: list[str] = []
        npv_fin = strategies.get(StrategyType.FINANCING, 0.0)
        npv_inv = strategies.get(StrategyType.SAVE_INVEST, float("-inf"))
        npv_cons = strategies.get(StrategyType.CONSORTIUM)

        # Veículo + conservador → nunca financia (bem depreciativo)
        if request.asset_type == AssetType.VEICULO:
            if npv_cons is not None and npv_cons > npv_inv:
                adjusted = StrategyType.CONSORTIUM
                reason = "consórcio (sem juros bancários)"
            else:
                adjusted = StrategyType.SAVE_INVEST
                reason = "Poupar/Investir (sem endividamento)"
            warnings.append(
                f"Perfil conservador: financiamento de veículo evitado "
                f"(bem depreciativo — perde ~15-20% ao ano). Recomendado: {reason}."
            )
            return adjusted, warnings

        # Outros bens: substitui se vantagem do financiamento for < 20%
        if npv_inv == float("-inf"):
            return best_strategy, warnings

        # NPVs são negativos (custos). Financing é melhor quando mais próximo de 0.
        abs_diff = abs(npv_inv) - abs(npv_fin)   # positivo = financing mais barato
        ref = abs(npv_inv) if npv_inv != 0 else 1.0
        advantage_pct = abs_diff / ref

        if advantage_pct < 0.20:
            warnings.append(
                f"Perfil conservador: vantagem do financiamento sobre Poupar/Investir "
                f"é de apenas {advantage_pct:.0%} — preferindo Poupar/Investir "
                "para evitar endividamento."
            )
            return StrategyType.SAVE_INVEST, warnings

        return best_strategy, warnings

    @staticmethod
    def _vehicle_depreciation_warning(
        request: SimulationRequest,
        final_strategy: StrategyType,
    ) -> Optional[str]:
        """
        Gera aviso de risco de depreciação para financiamento longo de veículo.

        Um veículo perde ~15-20% de valor por ano. Com entrada baixa e prazo longo,
        o saldo devedor pode superar o valor de mercado do bem nos primeiros anos
        ('ficar de cabeça pra baixo').

        Retorna a string de aviso ou None se não aplicável.
        """
        if request.asset_type != AssetType.VEICULO:
            return None
        if final_strategy != StrategyType.FINANCING:
            return None
        if request.financing_months <= 36:
            return None

        down_pct = request.down_payment / request.target_amount if request.target_amount > 0 else 0.0

        if down_pct < 0.20 and request.financing_months > 48:
            return (
                f"Atenção: financiamento de veículo por {request.financing_months} meses "
                f"com entrada de apenas {down_pct:.0%} — o carro pode valer menos que o saldo "
                "devedor nos primeiros 2-3 anos. Considere aumentar a entrada ou reduzir o prazo."
            )
        elif request.financing_months > 48:
            return (
                f"Veículo financiado em {request.financing_months} meses: "
                f"veículos depreciam ~15-20% ao ano. Com entrada de {down_pct:.0%}, "
                "verifique se o prazo não ultrapassa a vida útil econômica do bem."
            )
        return None

    @staticmethod
    def _compute_rental_leverage_plan(
        monthly_rental_income: float,
        monthly_payment: float,
        total_cost: float,
        months: int,
    ) -> RentalLeveragePlan:
        """
        Calcula o plano de alavancagem por aluguel para imóveis.

        Determina quanto o aluguel estimado cobre das parcelas e qual o
        custo líquido real da aquisição após descontar a renda de aluguel.

        Args:
            monthly_rental_income: Renda mensal estimada de aluguel (R$).
            monthly_payment:       Parcela mensal da estratégia (R$).
            total_cost:            Custo total da estratégia (R$).
            months:                Prazo total em meses.

        Returns:
            RentalLeveragePlan com todos os indicadores calculados.
        """
        rental_coverage_pct = round(
            (monthly_rental_income / monthly_payment * 100) if monthly_payment > 0 else 0.0, 1
        )
        monthly_out_of_pocket = round(monthly_payment - monthly_rental_income, 2)
        total_rental_income = round(monthly_rental_income * months, 2)
        net_acquisition_cost = round(total_cost - total_rental_income, 2)
        is_self_sustaining = monthly_rental_income >= monthly_payment
        months_covered = months if is_self_sustaining else 0

        fmt = format_currency
        if is_self_sustaining:
            surplus = round(monthly_rental_income - monthly_payment, 2)
            narrative = (
                f"O aluguel estimado de {fmt(monthly_rental_income)}/mês cobre 100% da parcela "
                f"de {fmt(monthly_payment)}/mês — o imóvel se paga sozinho. "
                f"Você ainda tem {fmt(surplus)}/mês de renda extra. "
                f"Ao longo de {months} meses, o aluguel gera {fmt(total_rental_income)}, "
                f"reduzindo seu custo real de aquisição para {fmt(max(net_acquisition_cost, 0.0))}."
            )
        elif rental_coverage_pct >= 50:
            narrative = (
                f"O aluguel estimado de {fmt(monthly_rental_income)}/mês cobre "
                f"{rental_coverage_pct:.1f}% da parcela de {fmt(monthly_payment)}/mês. "
                f"Seu desembolso real mensal será apenas {fmt(monthly_out_of_pocket)}. "
                f"Ao longo de {months} meses, o aluguel contribui com {fmt(total_rental_income)}, "
                f"reduzindo o custo efetivo da aquisição para {fmt(net_acquisition_cost)}."
            )
        else:
            narrative = (
                f"O aluguel estimado de {fmt(monthly_rental_income)}/mês cobre "
                f"{rental_coverage_pct:.1f}% da parcela de {fmt(monthly_payment)}/mês. "
                f"Ainda há um desembolso mensal de {fmt(monthly_out_of_pocket)}. "
                f"Mesmo assim, ao longo de {months} meses o aluguel economiza "
                f"{fmt(total_rental_income)}, baixando o custo total para {fmt(net_acquisition_cost)}."
            )

        return RentalLeveragePlan(
            monthly_rental_income=round(monthly_rental_income, 2),
            monthly_payment=round(monthly_payment, 2),
            rental_coverage_pct=rental_coverage_pct,
            monthly_out_of_pocket=monthly_out_of_pocket,
            total_rental_income=total_rental_income,
            net_acquisition_cost=net_acquisition_cost,
            is_self_sustaining=is_self_sustaining,
            months_covered=months_covered,
            narrative=narrative,
        )

    def simulate_timing_scenarios(
        self,
        request: SimulationRequest,
        market_rates: Dict[str, float],
        monthly_savings: float,
        scenarios: list = None,
    ) -> list:
        """
        M3.4 — Simula múltiplos timings: comprar agora vs esperar W meses.

        Para cada janela de espera (wait_months), calcula:
            - Entrada acumulada = original + mensal × meses
            - Principal reduzido = target - nova entrada
            - Simulação de financiamento com o novo principal
            - NPV incluindo custo de oportunidade da espera
            - Economia vs comprar agora (NPV)
            - Texto comparativo em linguagem natural

        Args:
            request:         Dados do usuário.
            market_rates:    Taxas de mercado (SELIC, CDI, CET, IPCA).
            monthly_savings: Quanto o usuário pode poupar / mês (R$).
            scenarios:       Lista de meses de espera. Padrão: [0, 3, 6, 12].

        Returns:
            Lista de TimingScenario ordenada pelo wait_months crescente.
        """
        if scenarios is None:
            scenarios = [0, 3, 6, 12]

        selic_monthly = (1 + market_rates.get("selic_annual", 0.1325)) ** (1 / 12) - 1
        cet_annual    = market_rates.get("best_cet_annual", 0.20)
        ipca_annual   = market_rates.get("ipca_annual", 0.045)

        results = []
        base_npv: float | None = None

        for wait in sorted(set(scenarios)):
            # ── 1. Calcular entrada acumulada após espera ──────────────
            new_down = request.down_payment + monthly_savings * wait
            new_down = min(new_down, request.target_amount * 0.95)  # teto: 95%
            new_principal = request.target_amount - new_down

            # ── 2. Simular financiamento com novo principal ────────────
            sim = fin_calc.calculate_price(new_principal, cet_annual, request.financing_months)

            # Fluxo NPV: custo de oportunidade da espera + financiamento
            opp_cashflows  = [-monthly_savings] * wait
            fin_cashflows  = [-new_down] + [-row["payment"] for row in sim.schedule]
            all_cashflows  = opp_cashflows + fin_cashflows
            npv_val = npv_calc.calculate_npv(all_cashflows, selic_monthly)

            # ── 3. Base (comprar agora) para comparação ────────────────
            if base_npv is None:
                base_npv = npv_val
            saving_vs_now = npv_val - base_npv

            # ── 4. Nota de inflação ────────────────────────────────────
            fv_real = (
                request.target_amount / ((1 + ipca_annual) ** (wait / 12))
                if wait > 0 else request.target_amount
            )

            # ── 5. Texto comparativo ───────────────────────────────────
            fmt = format_currency
            if wait == 0:
                text = (
                    f"Comprar agora: parcela de {fmt(sim.monthly_payment)}/mês "
                    f"por {request.financing_months} meses. "
                    f"Custo total: {fmt(sim.total_cost)}."
                )
            else:
                eco_text = (
                    f"Economia de {fmt(saving_vs_now)} (VPL)"
                    if saving_vs_now > 0
                    else f"Custo adicional de {fmt(-saving_vs_now)} vs comprar agora"
                )
                inflation_note = ""
                if abs(fv_real - request.target_amount) > 500:
                    inflation_note = (
                        f" (Em poder de compra atual: {fmt(fv_real)} — "
                        f"inflação de {ipca_annual:.1%} a.a.)"
                    )
                text = (
                    f"Esperar {wait} meses poupando {fmt(monthly_savings)}/mês: "
                    f"entrada de {fmt(new_down)} → "
                    f"parcela de {fmt(sim.monthly_payment)}/mês "
                    f"por {request.financing_months} meses. "
                    f"{eco_text}.{inflation_note}"
                )

            results.append(TimingScenario(
                wait_months=wait,
                accumulated_down_payment=round(new_down, 2),
                new_principal=round(new_principal, 2),
                recommended_strategy=StrategyType.FINANCING,
                total_cost_expected=round(sim.total_cost, 2),
                total_cost_npv=round(npv_val, 2),
                monthly_payment=round(sim.monthly_payment, 2),
                saving_vs_now=round(saving_vs_now, 2),
                comparison_text=text,
            ))

        return results

