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
    CompoundStrategyLeg,
    EfficiencyAnalysis,
    MacroSimulationResult,
    StrategyMacroStats,
    TimingScenario,
)
from app.architect.calculators import financing as fin_calc
from app.architect.calculators import investment as inv_calc
from app.architect.calculators import npv as npv_calc
from app.architect.calculators import consortium as cons_calc
from app.architect.connectors.consortium_rate_provider import ConsortiumRateProvider
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


def _pick_ssd_winner(
    ssd_matrix: Dict[str, Dict[str, str]],
    candidates: Dict["StrategyType", float],
) -> tuple[Optional["StrategyType"], Optional[str]]:
    """
    Retorna a estratégia que domina todas as outras em SSD, e o texto da garantia.

    Dominância SSD garante preferibilidade para qualquer agente avesso a risco,
    independente do grau de aversão — mais forte que comparar NPV mediano:
    captura a forma completa da distribuição, não apenas o ponto central.

    Returns:
        (winner, guarantee_text) quando existe um dominador único.
        (None, None) quando o resultado é inconclusivo.
    """
    name_to_type = {s.value: s for s in candidates}
    for name, rel_map in ssd_matrix.items():
        if name not in name_to_type:
            continue
        others = [k for k in candidates if k.value != name]
        if not others:
            continue
        if all(rel_map.get(o.value) == "dominates" for o in others):
            labels = " e ".join(o.value for o in others)
            guarantee = (
                f"{name} domina {labels} em dominância estocástica de segunda ordem "
                f"— preferível para qualquer agente avesso a risco, "
                f"independente do grau de aversão."
            )
            return name_to_type[name], guarantee
    return None, None


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

        selic_annual  = market_rates.get("selic_annual", 0.1475)
        selic_monthly = (1 + selic_annual) ** (1 / 12) - 1
        cdi_annual    = market_rates.get("cdi_annual", 0.1465)

        # Custo de oportunidade: prioridade → rendimento_real_atual do Open Finance
        # (retorno que o usuário JÁ consegue, dado real) → fallback: taxa estimada
        # por perfil de risco sobre o CDI de mercado.
        of = request.open_finance_features
        if of is not None and of.rendimento_real_atual is not None:
            disc_rate_annual = of.rendimento_real_atual
        else:
            disc_rate_annual = self._get_investment_rate(cdi_annual, request.risk_profile, request.risk_score)
        disc_rate_monthly = (1 + disc_rate_annual) ** (1 / 12) - 1
        market_rates      = {**market_rates, "disc_rate_monthly": disc_rate_monthly}

        # ── 1. Simular Estratégias ──────────────────────────────────
        fin_result = self._simulate_financing(request, market_rates)
        inv_result = self._simulate_investment(request, market_rates)

        cons_result: Optional[Dict[str, Any]] = None
        if request.include_consortium:
            cons_result = self._simulate_consortium(request, market_rates)

        # ── 1.5. Estratégias compostas (apenas imóvel com renda de aluguel) ──
        has_rental = (
            request.asset_type == AssetType.IMOVEL
            and request.expected_rental_income is not None
            and request.expected_rental_income > 0
        )
        comp4_result: Optional[Dict[str, Any]] = None
        comp5_result: Optional[Dict[str, Any]] = None
        if has_rental:
            comp4_result = self._simulate_financing_rental(request, market_rates, fin_result)
            if cons_result:
                comp5_result = self._simulate_consortium_selic_rental(
                    request, market_rates, cons_result
                )

        # ── 1.7. Simulação macroeconômica (VAR-1) antecipada para SSD ────
        # Rodamos antes da comparação para que a dominância estocástica
        # possa influenciar a escolha, em vez de apenas enriquecer o output.
        macro_sim = self._run_macro_simulation(
            request=request,
            market_rates=market_rates,
            fin_result=fin_result,
            inv_result=inv_result,
            cons_result=cons_result,
        )

        # ── 2. Comparar NPVs ────────────────────────────────────────
        npv_fin = _safe_float(fin_result["npv"])
        npv_inv = _safe_float(inv_result["npv"])
        npv_cons = _safe_float(cons_result["npv"]) if cons_result else None

        # ── 2.5. Custo de oportunidade do aluguel perdido (SAVE_INVEST) ──
        #
        # Quando o usuário informa expected_rental_income, comparar Poupar/Investir
        # com estratégias compostas sem ajuste é injusto: ao esperar N meses acumulando,
        # o usuário abre mão de N × aluguel/mês que poderia estar recebendo.
        #
        # Ajuste: o NPV do SAVE_INVEST usado na COMPARAÇÃO é penalizado pelo
        # valor presente do fluxo de aluguel perdido durante a acumulação.
        # O valor bruto (sem penalidade) ainda vai para NPVComparison.save_invest
        # para transparência.
        #
        # Fórmula: PV_aluguel_perdido = rental × [(1 − (1+r)^(−n)) / r]
        #          npv_inv_adj = npv_inv − PV_aluguel_perdido
        foregone_rental_pv = 0.0
        if has_rental:
            inv_months = inv_result["months"]
            rental = request.expected_rental_income
            if selic_monthly > 0:
                foregone_rental_pv = rental * (1 - (1 + selic_monthly) ** (-inv_months)) / selic_monthly
            else:
                foregone_rental_pv = rental * inv_months
        npv_inv_for_comparison = npv_inv - foregone_rental_pv

        # ── 2.8. Break-even rate: CET onde FINANCING == SAVE_INVEST ────
        break_even_cet = self._find_break_even_cet(request, market_rates, npv_inv)

        # ── 3. Decisão: maior NPV = menor custo presente ────────────
        strategies: Dict[StrategyType, float] = {
            StrategyType.FINANCING: npv_fin,
            StrategyType.SAVE_INVEST: npv_inv_for_comparison,
        }
        if cons_result and npv_cons is not None:
            strategies[StrategyType.CONSORTIUM] = npv_cons
        if comp4_result:
            strategies[StrategyType.FINANCING_RENTAL] = _safe_float(comp4_result["npv"])
        if comp5_result:
            strategies[StrategyType.CONSORTIUM_SELIC_RENTAL] = _safe_float(comp5_result["npv"])

        ranked = sorted(strategies.items(), key=lambda x: x[1], reverse=True)
        best_strategy = ranked[0][0]

        # ── 3.2. SSD override: dominância estocástica supera NPV mediano ──
        # Quando macro_sim disponível, verifica se alguma estratégia domina
        # todas as outras em segunda ordem — garantia válida para qualquer
        # agente avesso a risco, independente do grau de aversão.
        ssd_winner:    Optional[StrategyType] = None
        ssd_guarantee: Optional[str]         = None
        if macro_sim is not None and macro_sim.ssd_matrix:
            ssd_winner, ssd_guarantee = _pick_ssd_winner(macro_sim.ssd_matrix, strategies)
            if ssd_winner is not None:
                logger.info(
                    "SSD override: %s → %s | %s",
                    best_strategy.value,
                    ssd_winner.value,
                    ssd_guarantee,
                )
                best_strategy = ssd_winner

        # ── 3.5. Ajuste por perfil de risco ─────────────────────────
        best_strategy, profile_warnings = self._apply_risk_profile_adjustment(
            request, best_strategy, strategies
        )

        # ── 3.6. Conflito SSD × perfil de risco ─────────────────────
        # Se o ajuste de perfil reverteu a escolha do SSD, a garantia matemática
        # já não vale para a estratégia efetivamente recomendada. Registra o
        # conflito em warnings e zera ssd_guarantee para evitar output enganoso.
        if ssd_winner is not None and best_strategy != ssd_winner:
            profile_warnings.append(
                f"Nota: {ssd_winner.value} domina matematicamente em dominância "
                f"estocástica de 2ª ordem, mas foi substituído por {best_strategy.value} "
                f"pelo perfil de risco do usuário — garantia SSD descartada em favor "
                f"da adequação ao perfil."
            )
            ssd_guarantee = None

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

        elif (
            best_strategy == StrategyType.FINANCING_RENTAL
            and comp4_result
            and comp4_result["monthly_net_cost"] > budget_limit
        ):
            final_strategy = StrategyType.SAVE_INVEST

        elif (
            best_strategy == StrategyType.CONSORTIUM_SELIC_RENTAL
            and comp5_result
            and comp5_result["monthly_net_cost"] > budget_limit
        ):
            final_strategy = StrategyType.SAVE_INVEST

        # ── 5. Montar resposta ────────────────────────────────────────
        if final_strategy == StrategyType.FINANCING_RENTAL and comp4_result:
            selected = comp4_result
        elif final_strategy == StrategyType.CONSORTIUM_SELIC_RENTAL and comp5_result:
            selected = comp5_result
        elif final_strategy == StrategyType.FINANCING:
            selected = fin_result
        elif final_strategy == StrategyType.CONSORTIUM and cons_result:
            selected = cons_result
        else:
            final_strategy = StrategyType.SAVE_INVEST
            selected = inv_result

        # Liquidez — usa custo líquido para estratégias compostas
        if final_strategy in (StrategyType.FINANCING_RENTAL, StrategyType.CONSORTIUM_SELIC_RENTAL):
            monthly_cost_for_liquidity = selected.get("monthly_net_cost", selected["monthly_payment"])
        else:
            monthly_cost_for_liquidity = selected["monthly_payment"]

        liquidity_base = request.max_monthly_budget or monthly_cost_for_liquidity
        liquidity_impact = (
            -(monthly_cost_for_liquidity / liquidity_base) if liquidity_base > 0 else 0.0
        )

        # Meses — financial é imediato; compound consortium usa duração total para rental plan
        months = max(1, selected.get("full_months", selected["months"]))

        # ── 4.5. Avisos contextuais ──────────────────────────────────
        vehicle_warn = self._vehicle_depreciation_warning(request, final_strategy)
        if vehicle_warn:
            profile_warnings.append(vehicle_warn)

        # Aviso quando custo de oportunidade de aluguel é significativo
        if has_rental and foregone_rental_pv > 10_000:
            fmt = format_currency
            inv_months = inv_result["months"]
            profile_warnings.append(
                f"Custo de oportunidade incluído na comparação: aguardar {inv_months} meses "
                f"para comprar à vista significa abrir mão de {fmt(foregone_rental_pv)} "
                f"em aluguel (valor presente). As estratégias compostas já incluem essa renda."
            )

        # ── 4.6. Custos de transação (ITBI, cartório, registro) ─────────
        transaction_costs_applied: Optional[float] = None
        if request.asset_type == AssetType.IMOVEL:
            tc_pct = request.transaction_costs_pct if request.transaction_costs_pct is not None else 0.04
            if tc_pct > 0:
                transaction_costs_applied = round(request.target_amount * tc_pct, 2)
                # Somado ao custo das estratégias que envolvem aquisição imediata ou contrato
                for result in [fin_result, cons_result, comp4_result, comp5_result]:
                    if result is not None:
                        result["expected_cost"] = float(result["expected_cost"]) + transaction_costs_applied
                        result["max_cost"] = float(result["max_cost"]) + transaction_costs_applied
                profile_warnings.append(
                    f"Custos de transação de R$ {transaction_costs_applied:,.0f} "
                    f"({tc_pct:.1%} do valor) incluídos no custo total "
                    "(ITBI, cartório, registro)."
                )

        # Action Plan
        action_plan = self._generate_action_plan(
            final_strategy, selected, request
        )

        # ── 4.7. Alavancagem otimizada (LeverageOptimizer) ──────────────
        leverage_analysis: Optional[dict] = None
        if has_rental:
            try:
                from app.architect.calculators.leverage_optimizer import LeverageOptimizer
                selic_annual = market_rates.get("selic_annual", 0.1475)
                admin_rate = market_rates.get("consortium_admin_rate", 0.18)
                lev_result = LeverageOptimizer().find_optimal(
                    asset_value=request.target_amount,
                    monthly_rent=request.expected_rental_income,
                    selic_annual=selic_annual,
                    admin_rate=admin_rate,
                    consortium_months=request.financing_months,
                )
                leverage_analysis = {
                    "is_viable": lev_result.is_viable,
                    "recommendation": lev_result.recommendation,
                    "rejection_reason": lev_result.rejection_reason,
                    "optimal_multiplier": lev_result.optimal_multiplier,
                    "optimal_letter_value": lev_result.optimal_letter_value,
                    "final_patrimony": lev_result.final_patrimony,
                    "rent_yield_annual": round(lev_result.rent_yield_annual, 4),
                }
                if lev_result.is_viable and lev_result.optimal:
                    leverage_analysis["monthly_payment"] = round(lev_result.optimal.monthly_payment, 2)
                    leverage_analysis["is_self_sustaining"] = lev_result.optimal.is_self_sustaining
                    leverage_analysis["total_coverage_pct"] = round(lev_result.optimal.total_coverage_pct, 2)
            except Exception as exc:
                logger.warning("StrategyEngine | LeverageOptimizer falhou: %s", exc)

        # Plano de alavancagem por aluguel (apenas imóvel com renda informada)
        rental_leverage_plan: Optional[RentalLeveragePlan] = None
        if has_rental:
            rental_leverage_plan = self._compute_rental_leverage_plan(
                monthly_rental_income=request.expected_rental_income,
                monthly_payment=selected["monthly_payment"],  # parcela bruta
                total_cost=float(selected["expected_cost"]),
                months=months,
            )

        # Estratégias compostas — lista detalhada para comparação
        compound_strategies_list = None
        if has_rental:
            legs = []
            for result in [comp4_result, comp5_result]:
                if result is None:
                    continue
                leg_months = max(1, result.get("full_months", result["months"]))
                legs.append(CompoundStrategyLeg(
                    strategy_type=StrategyType(result["type"]),
                    monthly_gross_payment=round(result["monthly_payment"], 2),
                    monthly_rental_income=round(result["monthly_rental_income"], 2),
                    monthly_selic_contribution=round(result.get("monthly_selic_contribution", 0.0), 2),
                    monthly_net_cost=round(result["monthly_net_cost"], 2),
                    total_gross_cost=round(result["expected_cost"], 2),
                    total_rental_income=round(result["total_rental_income"], 2),
                    net_acquisition_cost=round(result["net_acquisition_cost"], 2),
                    npv=round(result["npv"], 2),
                    months=leg_months,
                    is_self_sustaining=result["is_self_sustaining"],
                    narrative=result["narrative"],
                ))
            compound_strategies_list = legs if legs else None

        # months_to_achieve: para compound consortium usa contemplação esperada, não duração total
        months_to_achieve = max(1, selected["months"])

        # ── 4.8. Custos de manutenção periódica (IMOVEL / VEICULO) ────────
        maintenance_cost_annual: Optional[float] = None
        if request.asset_type in (AssetType.IMOVEL, AssetType.VEICULO):
            if request.asset_type == AssetType.IMOVEL:
                maintenance_cost_annual = round(request.target_amount * 0.01, 2)
            else:
                maintenance_cost_annual = 1000.0

            # Financiamento: posse começa agora, duração = financing_months
            fin_maint = self._compute_maintenance_cost(
                request.asset_type, request.target_amount, request.financing_months
            )
            if fin_maint > 0:
                fin_result["expected_cost"] += fin_maint
                fin_result["max_cost"] += fin_maint

            # Consórcio: posse estimada a partir da contemplação; usa duração total do grupo
            cons_maint = 0.0
            if cons_result:
                cons_maint = self._compute_maintenance_cost(
                    request.asset_type, request.target_amount, cons_result["months"]
                )
                if cons_maint > 0:
                    cons_result["expected_cost"] += cons_maint
                    cons_result["max_cost"] += cons_maint

            # Estratégias compostas herdam manutenção da estratégia base correspondente
            if comp4_result and fin_maint > 0:
                comp4_result["expected_cost"] += fin_maint
                comp4_result["max_cost"] += fin_maint
            if comp5_result and cons_maint > 0:
                comp5_result["expected_cost"] += cons_maint
                comp5_result["max_cost"] += cons_maint

            asset_label = "imóvel" if request.asset_type == AssetType.IMOVEL else "veículo"
            profile_warnings.append(
                f"Custo de manutenção estimado para o {asset_label}: "
                f"R$ {maintenance_cost_annual:,.0f}/ano "
                f"(incluído no custo total das estratégias de aquisição)."
            )

        # ── 4.9. Estratégia eficiente (segunda recomendação) ──────────────
        all_results: Dict[StrategyType, Dict[str, Any]] = {
            StrategyType.FINANCING: fin_result,
            StrategyType.SAVE_INVEST: inv_result,
        }
        if cons_result:
            all_results[StrategyType.CONSORTIUM] = cons_result
        if comp4_result:
            all_results[StrategyType.FINANCING_RENTAL] = comp4_result
        if comp5_result:
            all_results[StrategyType.CONSORTIUM_SELIC_RENTAL] = comp5_result

        efficient_strategy = self._pick_efficient_strategy(
            request, all_results, final_strategy
        )

        data_sources = ["bacen", "anbima", "market_rates", "internal_models"]
        if leverage_analysis:
            data_sources.append("leverage_optimizer")

        if macro_sim is not None:
            data_sources.append("macro_var1")

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
                discount_rate_used=disc_rate_monthly,
                financing_rental=float(comp4_result["npv"]) if comp4_result else None,
                consortium_selic_rental=float(comp5_result["npv"]) if comp5_result else None,
                break_even_cet=break_even_cet,
            ),
            consortium_probability=(
                cons_result["probability"] if cons_result else None
            ),
            liquidity_impact=round(float(liquidity_impact), 4),
            months_to_achieve=months_to_achieve,
            action_plan=action_plan,
            confidence_score=request.risk_score_confidence or 0.75,
            data_sources=data_sources,
            rental_leverage_plan=rental_leverage_plan,
            compound_strategies=compound_strategies_list,
            leverage_analysis=leverage_analysis,
            transaction_costs_applied=transaction_costs_applied,
            maintenance_cost_annual=maintenance_cost_annual,
            efficient_strategy=efficient_strategy,
            macro_simulation=macro_sim,
            ssd_guarantee=ssd_guarantee,
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
        selic_monthly = (1 + rates.get("selic_annual", 0.1475)) ** (1 / 12) - 1
        disc_monthly = rates.get("disc_rate_monthly", selic_monthly)

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

        npv_val = npv_calc.calculate_npv(cashflows, disc_monthly)

        return {
            "type": "FINANCING",
            "monthly_payment": sim.monthly_payment,
            "total_cost": sim.total_cost,
            "min_cost": sim.total_cost,
            "expected_cost": sim.total_cost,
            "max_cost": round(sim.total_cost * 1.05, 2),
            "npv": npv_val,
            "months": 1,  # Aquisição imediata (ge=1 no model)
            "cashflows": cashflows,  # Preservado para estratégias compostas
        }

    @staticmethod
    def _get_investment_rate(
        cdi_annual: float,
        risk_profile: RiskProfile,
        risk_score: Optional[float] = None,
    ) -> float:
        """
        Retorna taxa de retorno esperada de investimentos por perfil de risco.

        Quando risk_score está disponível, interpola continuamente entre o
        retorno conservador (CDI líquido) e o arrojado (min(CDI×1.60, 18%)),
        eliminando os saltos discretos entre perfis.

        Sem risk_score (score=None): fallback para mapeamento por enum.

        Critérios do fallback por enum:
          CONSERVADOR → CDI × 0.85 (IR 15%): renda fixa pós-fixada
          MODERADO    → CDI × 0.85 × 1.10:   crédito privado / FII
          AGRESSIVO   → min(CDI × 1.60, 18%): exposição a renda variável
        """
        cdi_net = cdi_annual * 0.85  # IR 15% (prazo ≥ 720 dias)
        aggressive_rate = min(cdi_annual * 1.60, 0.18)

        if risk_score is not None:
            # Interpolação linear: score=0 → cdi_net; score=1 → aggressive_rate
            return cdi_net + (aggressive_rate - cdi_net) * risk_score

        # Fallback: mapeamento discreto por enum
        if risk_profile == RiskProfile.CONSERVADOR:
            return cdi_net
        elif risk_profile == RiskProfile.MODERADO:
            return cdi_net * 1.10
        else:  # AGRESSIVO
            return aggressive_rate

    def _pick_efficient_strategy(
        self,
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

        # Estratégias de aquisição real (excluir SAVE_INVEST — ele não "adquire" o bem)
        # A eficiência compara alternativas que entregam o bem, não a opção de esperar.
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

        # Excluir estratégias com parcela > 120% do orçamento (inviáveis na prática)
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

            # Dimensão 1: perda de capital (40%)
            total_out = request.down_payment + total_cost
            capital_loss_raw = max(0.0, (total_out - target) / target)
            score_capital = 1.0 - min(capital_loss_raw, 1.0)

            # Dimensão 2: velocidade de posse (35%)
            score_speed = 1.0 - (months - 1) / max(max_months - 1, 1)
            score_speed = max(0.0, score_speed)

            # Dimensão 3: impacto no orçamento (25%)
            if budget > 0:
                budget_ratio = monthly / budget
            else:
                budget_ratio = 0.5  # neutro sem info de orçamento
            score_budget = 1.0 - min(budget_ratio, 1.0)

            score = round(0.40 * score_capital + 0.35 * score_speed + 0.25 * score_budget, 4)
            scored.append((score, stype, result))

        if not scored:
            return None

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_type, best_result = scored[0]

        # Só retorna se difere da recomendação financeira
        if best_type == financial_winner:
            return None

        target = request.target_amount
        total_cost = float(best_result.get("expected_cost", target))
        monthly = float(best_result.get("monthly_payment", 0.0))
        months = max(1, best_result.get("months", 1))
        # Capital loss = dinheiro total pago (entrada + parcelas) - valor do bem
        total_out_of_pocket = request.down_payment + total_cost
        capital_loss_pct = round(max(0.0, (total_out_of_pocket - target) / target) * 100, 1)
        budget_commitment_pct = round((monthly / budget * 100) if budget > 0 else 0.0, 1)

        # ── Readiness: limiares interpolados pelo risk_score (ou fallback por enum) ──
        rp = request.risk_profile
        rs = request.risk_score
        if rs is not None:
            # Interpolação linear contínua entre extremos conservador (rs=0) e arrojado (rs=1).
            # Elimina o salto discreto CONSERVADOR→MODERADO→AGRESSIVO.
            ready_budget = 25.0 + rs * 25.0   # 25% (rs=0) → 50% (rs=1)
            warn_budget  = 40.0 + rs * 35.0   # 40%        → 75%
            ready_loss   = 50.0 + rs * 50.0   # 50%        → 100%
            warn_loss    = 80.0 + rs * 70.0   # 80%        → 150%
            profile_label = f"score {rs:.2f}"
        else:
            if rp == RiskProfile.CONSERVADOR:
                ready_budget, warn_budget = 25.0, 40.0
                ready_loss, warn_loss = 50.0, 80.0
            elif rp == RiskProfile.AGRESSIVO:
                ready_budget, warn_budget = 50.0, 75.0
                ready_loss, warn_loss = 100.0, 150.0
            else:  # MODERADO
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

        # Prefixo de timing
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

    @staticmethod
    def _compute_maintenance_cost(
        asset_type: AssetType, target_amount: float, months: int
    ) -> float:
        """
        Custo total de manutenção ao longo do período de posse (R$).

        IMOVEL  → 1% do valor do imóvel por ano (reparos, pequenos consertos).
        VEICULO → R$ 1.000/ano (revisões, pneus, imprevistos).
        Outros  → 0.
        """
        if asset_type == AssetType.IMOVEL:
            annual = target_amount * 0.01
        elif asset_type == AssetType.VEICULO:
            annual = 1000.0
        else:
            return 0.0
        return round(annual * (months / 12), 2)

    def _find_break_even_cet(
        self, req: SimulationRequest, rates: Dict[str, float], npv_inv: float
    ) -> Optional[float]:
        """
        Encontra por busca binária o CET anual onde FINANCING == SAVE_INVEST em NPV.

        Abaixo desse ponto: financiar é mais barato.
        Acima: poupar/investir é mais vantajoso.

        Returns:
            CET de equilíbrio (decimal, ex: 0.132 = 13,2% a.a.), ou None se falhar.
        """
        # Verificar se o crossover existe no intervalo [0.1%, 200%]
        try:
            rates_lo = dict(rates); rates_lo["best_cet_annual"] = 0.001
            rates_hi = dict(rates); rates_hi["best_cet_annual"] = 2.0
            npv_lo = self._simulate_financing(req, rates_lo)["npv"]
            npv_hi = self._simulate_financing(req, rates_hi)["npv"]
        except Exception:
            return None

        # Se financing nunca supera investing no intervalo, não há crossover relevante
        if npv_lo < npv_inv and npv_hi < npv_inv:
            return None  # SAVE_INVEST sempre melhor

        lo, hi = 0.001, 2.0
        for _ in range(60):
            mid = (lo + hi) / 2
            test_rates = dict(rates)
            test_rates["best_cet_annual"] = mid
            try:
                npv_mid = self._simulate_financing(req, test_rates)["npv"]
            except Exception:
                return None
            if npv_mid >= npv_inv:
                lo = mid  # financing ainda melhor ou igual; CET pode subir
            else:
                hi = mid  # financing pior; CET deve cair
            if hi - lo < 1e-5:
                break
        return round((lo + hi) / 2, 4)

    def _simulate_investment(
        self, req: SimulationRequest, rates: Dict[str, float]
    ) -> Dict[str, Any]:
        """Simula cenário de poupar/investir — M3.1: inclui FV real e benchmark por perfil."""
        cdi_annual    = rates.get("cdi_annual",    0.1465)
        ipca_annual   = rates.get("ipca_annual",   0.045)   # M3.1

        # Benchmark: prioridade → rendimento real do Open Finance (taxa real do usuário)
        # → fallback: estimativa por perfil sobre CDI de mercado.
        of = req.open_finance_features
        if of is not None and of.rendimento_real_atual is not None:
            investment_rate = of.rendimento_real_atual
        else:
            investment_rate = self._get_investment_rate(
                cdi_annual, req.risk_profile, req.risk_score
            )
        selic_monthly = (1 + rates.get("selic_annual", 0.1475)) ** (1 / 12) - 1
        disc_monthly = rates.get("disc_rate_monthly", selic_monthly)

        if req.max_monthly_budget:
            monthly_dep = req.max_monthly_budget
            months = inv_calc.calculate_months_needed(
                req.target_amount,
                monthly_dep,
                investment_rate,
                req.down_payment,
            )
            if months is None:
                months = 120
        else:
            months = req.financing_months
            monthly_dep = inv_calc.calculate_pmt_needed(
                req.target_amount,
                investment_rate,
                months,
                req.down_payment,
            )

        # Fluxo: -Entrada -Aportes mensais
        cashflows = [-req.down_payment]
        cashflows.extend([-monthly_dep] * months)

        npv_val = npv_calc.calculate_npv(cashflows, disc_monthly)

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
            "fv_nominal":       round(fv_nominal, 2),
            "fv_real":          round(fv_real, 2),
            "ipca_annual":      ipca_annual,
            # Benchmark de retorno usado (varia por perfil de risco)
            "investment_rate":  round(investment_rate, 4),
        }

    def _simulate_consortium(
        self, req: SimulationRequest, rates: Dict[str, float]
    ) -> Dict[str, Any]:
        """Simula cenário de consórcio via Monte Carlo.

        Usa parâmetros reais produzidos pelo ConsortiumRateProvider:
        - AbacConnector: admin_rate, months, group_size, reserve_fund_rate
        - IPCAConnector: annual_adjustment_rate (IPCA ou INCC≈IPCA×1.5 p/ imóvel)

        Todos os campos lêem do dict `rates` via .get() com fallback seguro,
        garantindo retrocompatibilidade com fixtures de teste que não incluem
        as chaves novas.
        """
        selic_monthly = (1 + rates.get("selic_annual", 0.1475)) ** (1 / 12) - 1
        disc_monthly = rates.get("disc_rate_monthly", selic_monthly)

        # Parâmetros do grupo — injetados pelo ConsortiumRateProvider via ArchitectService
        admin_rate            = rates.get("consortium_admin_rate",             0.17)
        cons_months           = int(rates.get("consortium_months",             72))
        reserve_fund_rate     = rates.get("consortium_reserve_fund_rate",      0.02)
        group_size            = int(rates.get("consortium_group_size",         100))
        contemplated_per_m    = int(rates.get("consortium_contemplated_per_month", 2))
        annual_adj_rate       = rates.get("consortium_annual_adjustment_rate", 0.045)

        # Mapeamento de tipo de bem: AssetType enum → formato consortium.py
        calc_asset_type = ConsortiumRateProvider.map_asset_type(req.asset_type.value)

        sim = cons_calc.calculate_consortium_metrics(
            letter_value=req.target_amount,
            months=cons_months,
            admin_rate=admin_rate,
            reserve_fund_rate=reserve_fund_rate,
            bid_amount=req.down_payment,
            asset_type=calc_asset_type,
            annual_adjustment_rate=annual_adj_rate,
            group_size=group_size,
            contemplated_per_month=contemplated_per_m,
        )

        # Fluxo: -Parcelas por N meses
        cashflows = [-sim.monthly_payment] * cons_months
        expected_month = sim.contemplation_month_expected

        # Lance no mês esperado de contemplação
        if expected_month < len(cashflows) and req.down_payment > 0:
            cashflows[expected_month] -= req.down_payment

        npv_val = npv_calc.calculate_npv(cashflows, disc_monthly)

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

    def _simulate_financing_rental(
        self,
        req: SimulationRequest,
        rates: Dict[str, float],
        fin_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Estratégia 4 — Financiamento + aluguel do imóvel.

        O cashflow de cada mês é reduzido pela renda de aluguel.
        NPV reflete o custo real líquido da aquisição.
        is_self_sustaining = True quando aluguel >= parcela bruta.
        """
        rental = req.expected_rental_income  # já garantido > 0 pelo gate has_rental
        selic_monthly = (1 + rates.get("selic_annual", 0.1475)) ** (1 / 12) - 1
        disc_monthly = rates.get("disc_rate_monthly", selic_monthly)
        gross_cashflows = fin_result["cashflows"]  # [-entrada, -p1, -p2, ...]
        months = req.financing_months

        # Cashflows líquidos: entrada inalterada; parcelas reduzidas pelo aluguel
        net_cashflows = [gross_cashflows[0]]
        for cf in gross_cashflows[1:]:
            net_cashflows.append(cf + rental)  # cf < 0; rental > 0 → reduz custo

        npv_val = npv_calc.calculate_npv(net_cashflows, disc_monthly)

        gross_payment = fin_result["monthly_payment"]
        net_monthly = max(gross_payment - rental, 0.0)
        total_rental = round(rental * months, 2)
        net_acquisition = round(fin_result["expected_cost"] - total_rental, 2)
        is_self_sustaining = rental >= gross_payment

        fmt = format_currency
        if is_self_sustaining:
            surplus = rental - gross_payment
            narrative = (
                f"O aluguel de {fmt(rental)}/mês cobre 100% da parcela de "
                f"{fmt(gross_payment)}/mês — o imóvel se paga sozinho e ainda "
                f"gera {fmt(surplus)}/mês de renda extra."
            )
        else:
            coverage_pct = rental / gross_payment * 100 if gross_payment > 0 else 0
            narrative = (
                f"O aluguel de {fmt(rental)}/mês cobre {coverage_pct:.0f}% da parcela "
                f"de {fmt(gross_payment)}/mês. Seu desembolso real cai para "
                f"{fmt(net_monthly)}/mês ao longo de {months} meses."
            )

        return {
            "type": "FINANCING_RENTAL",
            "monthly_payment": gross_payment,
            "monthly_net_cost": net_monthly,
            "monthly_rental_income": rental,
            "monthly_selic_contribution": 0.0,
            "min_cost": fin_result["min_cost"],
            "expected_cost": fin_result["expected_cost"],
            "max_cost": fin_result["max_cost"],
            "npv": npv_val,
            "months": months,
            "is_self_sustaining": is_self_sustaining,
            "total_rental_income": total_rental,
            "net_acquisition_cost": net_acquisition,
            "narrative": narrative,
        }

    def _simulate_consortium_selic_rental(
        self,
        req: SimulationRequest,
        rates: Dict[str, float],
        cons_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Estratégia 5 — Consórcio + entrada investida na SELIC + aluguel.

        Lógica mês a mês:
        1. Rendimento SELIC sobre o saldo investido (inicia com req.down_payment)
        2. + Aluguel recebido
        3. - Parcela do consórcio (com reajuste anual)
        4. = Saldo líquido reinvestido (ou aporte do bolso se negativo)

        is_self_sustaining = True se o saldo nunca fica negativo.
        """
        rental = req.expected_rental_income
        selic_annual = rates.get("selic_annual", 0.1475)
        selic_monthly = (1 + selic_annual) ** (1 / 12) - 1
        disc_monthly = rates.get("disc_rate_monthly", selic_monthly)

        cons_months = int(rates.get("consortium_months", 72))
        admin_rate = rates.get("consortium_admin_rate", 0.17)
        reserve_fund_rate = rates.get("consortium_reserve_fund_rate", 0.02)
        annual_adj_rate = rates.get("consortium_annual_adjustment_rate", 0.045)
        adj_monthly = (1 + annual_adj_rate) ** (1 / 12) - 1
        total_rate = admin_rate + reserve_fund_rate

        invested = req.down_payment  # entrada investida na SELIC desde o início
        current_letter = req.target_amount  # carta sem alavancagem

        net_cashflows: list = []  # fluxo líquido mês a mês (positivo = excedente)
        total_paid = 0.0
        total_rent = 0.0
        total_selic = 0.0
        months_negative = 0

        for month in range(1, cons_months + 1):
            if month > 1 and annual_adj_rate > 0:
                current_letter *= (1 + adj_monthly)

            payment = current_letter * (1 + total_rate) / cons_months
            selic_income = max(invested, 0) * selic_monthly
            net = rental + selic_income - payment

            invested += net
            total_paid += payment
            total_rent += rental
            total_selic += selic_income

            if invested < 0:
                months_negative += 1

            net_cashflows.append(net)

        # NPV: mês 0 = saída da entrada (investida mas comprometida); meses 1..N = fluxos líquidos
        npv_cashflows = [-req.down_payment] + net_cashflows
        npv_val = npv_calc.calculate_npv(npv_cashflows, disc_monthly)

        is_self_sustaining = months_negative == 0

        # Métricas do mês 1 (para narrativa)
        gross_payment_m1 = round(req.target_amount * (1 + total_rate) / cons_months, 2)
        selic_m1 = round(req.down_payment * selic_monthly, 2)
        monthly_net_cost = max(gross_payment_m1 - rental - selic_m1, 0.0)
        total_rental_income = round(rental * cons_months, 2)
        net_acquisition_cost = round(max(total_paid - total_rental_income - total_selic, 0), 2)

        fmt = format_currency
        if is_self_sustaining:
            narrative = (
                f"Operação auto-sustentável: aluguel ({fmt(rental)}/mês) + "
                f"SELIC sobre entrada ({fmt(selic_m1)}/mês) cobrem as parcelas "
                f"({fmt(gross_payment_m1)}/mês) durante todos os {cons_months} meses. "
                f"Imóvel quitado sem desembolso mensal."
            )
        else:
            narrative = (
                f"Aluguel ({fmt(rental)}/mês) + SELIC sobre entrada ({fmt(selic_m1)}/mês) "
                f"cobrem parcialmente as parcelas ({fmt(gross_payment_m1)}/mês). "
                f"Desembolso real estimado: {fmt(monthly_net_cost)}/mês "
                f"({months_negative} meses com déficit de {cons_months} no total)."
            )

        return {
            "type": "CONSORTIUM_SELIC_RENTAL",
            "monthly_payment": gross_payment_m1,
            "monthly_net_cost": monthly_net_cost,
            "monthly_rental_income": rental,
            "monthly_selic_contribution": selic_m1,
            "min_cost": cons_result["min_cost"],
            "expected_cost": cons_result["expected_cost"],
            "max_cost": cons_result["max_cost"],
            "npv": npv_val,
            "months": cons_result["months"],        # contemplação esperada
            "full_months": cons_months,             # duração total do grupo
            "is_self_sustaining": is_self_sustaining,
            "total_rental_income": total_rental_income,
            "net_acquisition_cost": net_acquisition_cost,
            "months_negative": months_negative,
            "narrative": narrative,
            "probability": cons_result["probability"],
        }

    def _generate_action_plan(
        self,
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

        # Consórcio: só bloquear para perfis muito conservadores (rs < 0.25).
        # Entre 0.25 e 0.35 (conservador moderado), consórcio é aceito — sem juros bancários.
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
                abs_diff = abs(npv_inv) - abs(npv_cons)   # positivo = consórcio mais barato
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

        # Veículo + conservador → nunca financia (bem depreciativo)
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

        # Outros bens: requer vantagem mínima de NPV sobre SAVE_INVEST.
        # Com risk_score: limiar suavizado entre 25% (score=0) e 15% (score=0.35).
        # Sem risk_score: limiar fixo de 20% (comportamento legado).
        if npv_inv == float("-inf"):
            return best_strategy, warnings

        if rs is not None:
            # score=0 → exige 25%; score=0.35 → exige ~15%; interpolação linear
            min_advantage_pct = 0.25 - rs * (0.10 / 0.35)
        else:
            min_advantage_pct = 0.20

        abs_diff = abs(npv_inv) - abs(npv_fin)   # positivo = financing mais barato
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

    def _run_macro_simulation(
        self,
        request: SimulationRequest,
        market_rates: Dict[str, float],
        fin_result: Dict[str, Any],
        inv_result: Dict[str, Any],
        cons_result: Optional[Dict[str, Any]],
        n_sims: int = 2000,
    ) -> Optional[MacroSimulationResult]:
        """
        Executa a simulação de cenários macroeconômicos correlacionados (VAR-1).

        Gera n_sims trajetórias de (Selic, IPCA, valorização) com correlações
        históricas e calcula a distribuição de NPV de cada estratégia base.

        Returns MacroSimulationResult ou None se a simulação falhar.
        """
        try:
            from app.architect.simulators.macro_scenario import run_macro_simulation

            selic_annual = market_rates.get("selic_annual", 0.1475)
            cdi_annual   = market_rates.get("cdi_annual", 0.1465)

            # invest_factor: razão entre retorno real do usuário e Selic — garante
            # consistência entre a simulação macro e _simulate_investment.
            disc_rate_annual = self._get_investment_rate(
                cdi_annual, request.risk_profile, request.risk_score
            )
            invest_factor = disc_rate_annual / selic_annual if selic_annual > 0 else 0.85

            consortium_months: Optional[int] = None
            consortium_admin_reserve: float  = 0.19
            consortium_expected: Optional[int] = None
            if cons_result is not None:
                consortium_months  = int(market_rates.get("consortium_months", 72))
                admin_rate         = market_rates.get("consortium_admin_rate", 0.17)
                reserve_rate       = market_rates.get("consortium_reserve_fund_rate", 0.02)
                consortium_admin_reserve = admin_rate + reserve_rate
                prob = cons_result.get("probability")
                if prob is not None:
                    consortium_expected = int(prob.expected_months)

            distributions, prob_best, ssd_matrix = run_macro_simulation(
                n_sims                            = n_sims,
                initial_selic_annual              = selic_annual,
                financing_cashflows               = fin_result.get("cashflows"),
                financing_months                  = request.financing_months,
                save_monthly                      = float(inv_result["monthly_payment"]),
                target_amount                     = request.target_amount,
                down_payment                      = request.down_payment,
                consortium_months                 = consortium_months,
                consortium_admin_reserve          = consortium_admin_reserve,
                consortium_expected_contemplation = consortium_expected,
                invest_factor                     = invest_factor,
                seed                              = None,
            )

            return MacroSimulationResult(
                n_simulations = n_sims,
                distributions = {
                    k: StrategyMacroStats(
                        npv_p10 = round(v.npv_p10, 2),
                        npv_p50 = round(v.npv_p50, 2),
                        npv_p90 = round(v.npv_p90, 2),
                        cvar_95 = round(v.cvar_95, 2),
                    )
                    for k, v in distributions.items()
                },
                prob_best  = prob_best,
                ssd_matrix = ssd_matrix,
            )

        except Exception as exc:
            logger.warning("StrategyEngine | macro_simulation falhou: %s", exc)
            return None

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

        selic_monthly = (1 + market_rates.get("selic_annual", 0.1475)) ** (1 / 12) - 1
        disc_monthly  = market_rates.get("disc_rate_monthly", selic_monthly)
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
            npv_val = npv_calc.calculate_npv(all_cashflows, disc_monthly)

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

