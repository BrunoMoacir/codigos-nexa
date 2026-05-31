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
    BreakevenDistribution,
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
from app.architect.simulators.action_plan_builder import generate_action_plan
from app.architect.simulators.cost_adjuster import compute_maintenance_cost
from app.architect.simulators.strategy_selector import (
    apply_risk_profile_adjustment,
    pick_efficient_strategy,
)
from app.architect.utils.formatters import format_currency

logger = logging.getLogger(__name__)

# Mapeamento AssetType → tipo aceito pelos calculadores de financiamento/consórcio.
# Necessário para seguro correto (MIP+DFI para property, auto para vehicle).
_CALC_ASSET_MAP: Dict[AssetType, str] = {
    AssetType.IMOVEL:  "property",
    AssetType.VEICULO: "vehicle",
    AssetType.REFORMA: "other",
    AssetType.VIAGEM:  "other",
    AssetType.OUTRO:   "other",
}

# IOF para financiamento imobiliário residencial (SFH) é 0% — Decreto 6.306/2007.
# Outros tipos seguem a alíquota padrão (IOF_FIXO_RATE em financing.py).
_IOF_RATE_BY_ASSET: Dict[AssetType, float] = {
    AssetType.IMOVEL:  0.0,                   # SFH: isento
    AssetType.VEICULO: fin_calc.IOF_FIXO_RATE,
    AssetType.REFORMA: fin_calc.IOF_FIXO_RATE,
    AssetType.VIAGEM:  fin_calc.IOF_FIXO_RATE,
    AssetType.OUTRO:   fin_calc.IOF_FIXO_RATE,
}


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


def _get_investment_rate(
    cdi_annual: float,
    risk_profile: Optional[RiskProfile],
    risk_score: Optional[float] = None,
) -> float:
    """
    Retorna taxa de retorno esperada de investimentos por perfil de risco.

    Quando risk_score está disponível, interpola continuamente entre o
    retorno conservador (CDI líquido) e o arrojado (min(CDI×1.60, 18%)),
    eliminando os saltos discretos entre perfis.

    Sem risk_score (score=None): fallback para mapeamento por enum.

      CONSERVADOR → CDI × 0.85 (IR 15%): renda fixa pós-fixada
      MODERADO    → CDI × 0.85 × 1.10:   crédito privado / FII
      AGRESSIVO   → min(CDI × 1.60, 18%): exposição a renda variável
      None        → tratado como MODERADO
    """
    cdi_net = cdi_annual * 0.85  # IR 15% (prazo ≥ 720 dias)
    aggressive_rate = min(cdi_annual * 1.60, 0.18)

    if risk_score is not None:
        return cdi_net + (aggressive_rate - cdi_net) * risk_score

    if risk_profile == RiskProfile.CONSERVADOR:
        return cdi_net
    if risk_profile == RiskProfile.AGRESSIVO:
        return aggressive_rate
    return cdi_net * 1.10  # MODERADO (e None)


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
            disc_rate_annual = _get_investment_rate(cdi_annual, request.risk_profile, request.risk_score)
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

        # ── 1.6. Custos de aquisição/posse antes da decisão ─────────────
        # Esses custos afetam o ranking financeiro; aplicá-los só no output
        # deixava recommended_strategy e NPVComparison inconsistentes.
        ownership_warnings: list[str] = []
        transaction_costs_applied: Optional[float] = None
        maintenance_cost_annual: Optional[float] = None

        def _add_cost_to_result(result: Optional[Dict[str, Any]], cost: float) -> None:
            if result is None or cost <= 0:
                return
            result["expected_cost"] = float(result["expected_cost"]) + cost
            result["max_cost"] = float(result["max_cost"]) + cost
            result["npv"] = _safe_float(result.get("npv")) - cost

        if request.asset_type == AssetType.IMOVEL:
            tc_pct = request.transaction_costs_pct if request.transaction_costs_pct is not None else 0.04
            if tc_pct > 0:
                transaction_costs_applied = round(request.target_amount * tc_pct, 2)
                for result in [fin_result, cons_result, comp4_result, comp5_result]:
                    _add_cost_to_result(result, transaction_costs_applied)
                ownership_warnings.append(
                    f"Custos de transação de R$ {transaction_costs_applied:,.0f} "
                    f"({tc_pct:.1%} do valor) incluídos no custo total "
                    "(ITBI, cartório, registro)."
                )

        if request.asset_type in (AssetType.IMOVEL, AssetType.VEICULO):
            if request.asset_type == AssetType.IMOVEL:
                maintenance_cost_annual = round(request.target_amount * 0.01, 2)
            else:
                maintenance_cost_annual = 1000.0

            fin_maint = compute_maintenance_cost(
                request.asset_type, request.target_amount, request.financing_months
            )
            _add_cost_to_result(fin_result, fin_maint)
            _add_cost_to_result(comp4_result, fin_maint)

            cons_maint = 0.0
            if cons_result:
                cons_maint = compute_maintenance_cost(
                    request.asset_type, request.target_amount, cons_result["months"]
                )
                _add_cost_to_result(cons_result, cons_maint)
                _add_cost_to_result(comp5_result, cons_maint)

            asset_label = "imóvel" if request.asset_type == AssetType.IMOVEL else "veículo"
            ownership_warnings.append(
                f"Custo de manutenção estimado para o {asset_label}: "
                f"R$ {maintenance_cost_annual:,.0f}/ano "
                f"(incluído no custo total das estratégias de aquisição)."
            )

        # ── 1.7. Simulação macroeconômica (VAR-1) antecipada para SSD ────
        # Rodamos antes da comparação para que a dominância estocástica
        # possa influenciar a escolha, em vez de apenas enriquecer o output.
        macro_sim = None
        if request.include_macro:
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
        breakeven_dist = (
            self._compute_breakeven_surface(request, market_rates)
            if request.include_breakeven_distribution
            else None
        )

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
        best_strategy, profile_warnings = apply_risk_profile_adjustment(
            request, best_strategy, strategies
        )
        profile_warnings.extend(ownership_warnings)

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

        # Action Plan
        action_plan = generate_action_plan(
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

        efficient_strategy = pick_efficient_strategy(
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
                breakeven_distribution=breakeven_dist,
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

        calc_asset = _CALC_ASSET_MAP.get(req.asset_type, "other")
        iof_rate   = _IOF_RATE_BY_ASSET.get(req.asset_type, fin_calc.IOF_FIXO_RATE)

        if req.amortization_method.value == "SAC":
            sim = fin_calc.calculate_sac(
                req.principal, cet_annual, req.financing_months,
                iof_rate=iof_rate, asset_type=calc_asset,
            )
        else:
            sim = fin_calc.calculate_price(
                req.principal, cet_annual, req.financing_months,
                iof_rate=iof_rate, asset_type=calc_asset,
            )

        # IOF pago no ato do contrato (t=0); para IMOVEL SFH é 0.
        # Seguro mensal (MIP/DFI para imóvel, auto para veículo) entra no fluxo
        # descontado — é custo obrigatório e afeta a comparação NPV com SAVE_INVEST.
        cashflows = [-(req.down_payment + sim.total_iof)]
        for row in sim.schedule:
            cashflows.append(-(row["payment"] + row.get("insurance", 0.0)))

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

    def _compute_breakeven_surface(
        self,
        request: SimulationRequest,
        market_rates: Dict[str, float],
        n_simulations: int = 5_000,
        seed: Optional[int] = None,
    ) -> Optional[BreakevenDistribution]:
        """
        Distribuição probabilística do CET de break-even sob incerteza macroeconômica.

        Amostra N cenários de (selic, ipca) com correlação histórica, calcula o
        retorno real do SAVE_INVEST por perfil e encontra via bisecção vetorizada
        o CET onde NPV(FINANCING) = NPV(SAVE_INVEST).

        Chave analítica (PRICE, sem orçamento máximo):
          pva cancela → break-even ocorre quando pmt_fin(cet*) = pmt_inv(inv_real_s)

        O break-even em CET > 0 exige retornos reais negativos (IPCA supera CDI×perfil).
        Isso acontece em cenários de alta inflação amostrados via normal bivariada —
        com ~2-3% dos cenários tipicamente solventes em ambientes de juros altos.
        Quando solventes são < 10% do total, retorna None.

        Não suporta SAC nem max_monthly_budget (ambos retornam None).
        """
        try:
            import numpy as np
        except ImportError:
            return None

        if request.amortization_method.value == "SAC":
            return None

        principal = _safe_float(request.principal)
        if principal <= 0:
            return None

        N   = int(request.financing_months)
        dp  = float(request.down_payment)
        tgt = float(request.target_amount)

        current_selic = float(market_rates.get("selic_annual", 0.1475))
        current_cdi   = float(market_rates.get("cdi_annual",   0.1465))
        current_cet   = float(market_rates.get("best_cet_annual", 0.15))
        current_ipca  = float(market_rates.get("ipca_annual", 0.045))

        # ── 1. Amostrar cenários (selic, ipca) com correlação histórica ─────
        # σ_selic=2.5 p.p., σ_ipca=2.0 p.p., corr=0.40 (BCB 2015-2025)
        rng   = np.random.default_rng(seed)
        s_sel, s_ipc, corr = 0.025, 0.020, 0.40
        cov   = np.array([[s_sel**2, corr*s_sel*s_ipc], [corr*s_sel*s_ipc, s_ipc**2]])
        L     = np.linalg.cholesky(cov)
        z     = rng.standard_normal((n_simulations, 2))
        draws = np.array([current_selic, current_ipca]) + z @ L.T

        selic_s = np.clip(draws[:, 0], 0.02, 0.50)
        ipca_s  = np.clip(draws[:, 1], 0.01, 0.40)

        # CDI mantém spread histórico fixo em relação à SELIC
        spread = max(0.0, current_selic - current_cdi)
        cdi_s  = np.maximum(selic_s - spread, 0.01)

        # ── 2. Retorno REAL do investimento por perfil (vetorizado) ─────────
        # Break-even existe quando retorno real < 0 (IPCA > CDI×perfil).
        # Com retorno real negativo, pmt_inv > P/N → pmt_fin(cet*) tem solução positiva.
        cdi_net    = cdi_s * 0.85
        aggressive = np.minimum(cdi_s * 1.60, 0.18)
        rs = request.risk_score
        rp = request.risk_profile
        if rs is not None:
            inv_nom_s = cdi_net + (aggressive - cdi_net) * float(rs)
        elif rp == RiskProfile.AGRESSIVO:
            inv_nom_s = aggressive
        elif rp == RiskProfile.CONSERVADOR:
            inv_nom_s = cdi_net
        else:  # MODERADO
            inv_nom_s = cdi_net * 1.10

        # Retorno real deflacionado pelo IPCA do cenário
        inv_real_s = (1.0 + inv_nom_s) / (1.0 + ipca_s) - 1.0

        # ── 3. PMT do SAVE_INVEST no retorno real de cada cenário ───────────
        inv_m   = (1.0 + inv_real_s) ** (1.0 / 12.0) - 1.0  # mensal (n_sims,)
        fv_dp_s = dp * (1.0 + inv_m) ** N
        growth  = (1.0 + inv_m) ** N - 1.0

        safe_m = np.where(np.abs(growth) > 1e-10, inv_m,   1e-10)
        safe_g = np.where(np.abs(growth) > 1e-10, growth, float(N))
        pmt_inv = np.where(
            np.abs(growth) > 1e-10,
            (tgt - fv_dp_s) * safe_m / safe_g,
            (tgt - dp) / max(N, 1),
        )

        # ── 4. prob_financing_wins: direto, sem precisar do break-even ──────
        # Financiar vence quando a parcela atual < aporte mensal necessário para poupar
        cet_m_cur = (1.0 + current_cet) ** (1.0 / 12.0) - 1.0
        if cet_m_cur > 1e-10:
            q_cur = (1.0 + cet_m_cur) ** (-N)
            pmt_fin_cur = principal * cet_m_cur / (1.0 - q_cur)
        else:
            pmt_fin_cur = principal / N

        prob = float(np.mean(pmt_fin_cur < pmt_inv))

        # ── 5. Solvabilidade: break-even em CET>0 existe apenas quando ──────
        # pmt_inv > P/N (retorno real negativo → investimento piora vs. sem juros)
        pmt_fin_floor = principal / N
        solvable      = pmt_inv > pmt_fin_floor
        n_solvable    = int(np.sum(solvable))

        if n_solvable < int(n_simulations * 0.10):
            return None  # sem cenários com break-even positivo (SAVE_INVEST domina)

        pmt_target = pmt_inv[solvable]

        # ── 6. Bisecção vetorizada: pmt_fin(cet*) = pmt_target ──────────────
        lo = np.full(n_solvable, 0.0001 / 12.0)
        hi = np.full(n_solvable, 2.0    / 12.0)

        for _ in range(32):  # 32 iterações → precisão < 1e-8 no CET mensal
            mid = (lo + hi) / 2.0
            q   = (1.0 + mid) ** (-N)
            pmt_mid = principal * mid / (1.0 - q)
            hi = np.where(pmt_mid > pmt_target, mid, hi)
            lo = np.where(pmt_mid > pmt_target, lo,  mid)

        cet_m_star = (lo + hi) / 2.0
        be_cet     = (1.0 + cet_m_star) ** 12 - 1.0  # anualizar

        return BreakevenDistribution(
            cet_p10=round(float(np.percentile(be_cet, 10)), 4),
            cet_p50=round(float(np.percentile(be_cet, 50)), 4),
            cet_p90=round(float(np.percentile(be_cet, 90)), 4),
            prob_financing_wins=round(prob, 4),
            n_simulations=n_solvable,
        )

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
            investment_rate = _get_investment_rate(
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

        # Fluxo: -Entrada -Aportes mensais [-Aluguel mensal durante acumulação]
        # current_monthly_rent: custo real de quem poupa para comprar enquanto ainda aluga.
        # O aluguel é corrigido pelo IPCA mês a mês para não subestimar o NPV em horizontes longos.
        rent_monthly = req.current_monthly_rent or 0.0
        ipca_monthly = (1.0 + ipca_annual) ** (1.0 / 12) - 1.0
        cashflows = [-req.down_payment]
        for m in range(1, months + 1):
            rent_m = rent_monthly * (1.0 + ipca_monthly) ** m
            cashflows.append(-(monthly_dep + rent_m))

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
        # Parâmetros do MC de consórcio — injetados pelo CalibrationPipeline quando disponíveis
        bid_mean_initial      = rates.get("bid_mean_initial", 0.35)
        bid_std               = rates.get("bid_std",          0.12)

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
            bid_mean_initial=bid_mean_initial,
            bid_std=bid_std,
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
            disc_rate_annual = _get_investment_rate(
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

            # current_monthly_rent somado ao depósito mensal: quem poupa ainda paga
            # aluguel durante a acumulação — esse custo deve entrar na distribuição SSD
            # para comparação justa contra FINANCING (que substitui o aluguel).
            rent_for_macro = request.current_monthly_rent or 0.0
            distributions, prob_best, ssd_matrix = run_macro_simulation(
                n_sims                            = n_sims,
                initial_selic_annual              = selic_annual,
                financing_cashflows               = fin_result.get("cashflows"),
                financing_months                  = request.financing_months,
                save_monthly                      = float(inv_result["monthly_payment"]) + rent_for_macro,
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
            sim = fin_calc.calculate_price(
                new_principal, cet_annual, request.financing_months,
                iof_rate=_IOF_RATE_BY_ASSET.get(request.asset_type, fin_calc.IOF_FIXO_RATE),
                asset_type=_CALC_ASSET_MAP.get(request.asset_type, "other"),
            )

            # Fluxo NPV: custo de oportunidade da espera + financiamento
            opp_cashflows  = [-monthly_savings] * wait
            fin_cashflows  = [-(new_down + sim.total_iof)] + [
                -(row["payment"] + row.get("insurance", 0.0)) for row in sim.schedule
            ]
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
