"""
app/architect/simulators/strategy_engine.py - Motor de Decisão da F3

Feature: F3 - Nexa Architect
Version: 1.0.0

Responsabilidade:
    Orquestrar as simulações de Financiamento, Consórcio e Investimento,
    comparar os resultados (NPV, Liquidez, Prazo) e recomendar a melhor estratégia.

Logica de Decisão:
    1. Executa simulações paralelas para cada estratégia.
    2. Valida restrições (ex: parcela não pode exceder orçamento).
    3. Calcula NPV de cada fluxo para comparação justa.
    4. Seleciona a estratégia com menor custo financeiro (maior NPV, considerando que são saídas de caixa).
       Nota: Como são pagamentos, buscamos o NPV "menos negativo" (maior valor algébrico)
       ou o menor custo presente absoluto.
       Por convenção aqui: NPV negativo = custo a valor presente.
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
    CostScenario,
    NPVComparison,
    ConsortiumProbability,
    ActionStep,
    FinancingTerms,
    InvestmentTerms,
    RiskProfile
)
from app.architect.calculators import financing, investment, npv, consortium
from app.architect.utils.formatters import format_currency

logger = logging.getLogger(__name__)

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
        consortium_data: Optional[Dict[str, Any]] = None
    ) -> SimulationResponse:
        """
        Executa a simulação completa e retorna a recomendação.
        
        Args:
            request: Dados do usuário (target, entrada, orçamento, etc).
            market_rates: Taxas atuais (selic_annual, cdi_annual, best_cet_annual, etc).
            consortium_data: Dados históricos de consórcio (opcional).
            
        Returns:
            SimulationResponse com a melhor estratégia e detalhes.
        """
        logger.info(f"Iniciando simulação para user={request.user_id}, target={request.target_amount}")
        
        # 1. Preparar dados base
        principal = request.principal
        selic_monthly = (1 + market_rates.get("selic_annual", 0.10)) ** (1/12) - 1
        
        # 2. Simular Estratégias
        
        # A) Financiamento
        fin_result = self._simulate_financing(request, market_rates)
        
        # B) Poupar/Investir
        inv_result = self._simulate_investment(request, market_rates)
        
        # C) Consórcio (se habilitado)
        cons_result = None
        if request.include_consortium:
            cons_result = self._simulate_consortium(request, market_rates)
            
        # 3. Comparar NPVs
        # NPV de pagamentos é negativo (saída de caixa).
        # Queremos o que tem menor custo presente (maior valor algébrico).
        
        npv_fin = np.nan_to_num(fin_result["npv"])
        npv_inv = np.nan_to_num(inv_result["npv"])
        npv_cons = np.nan_to_num(cons_result["npv"]) if cons_result else -float('inf')
        
        # 4. Decisão preliminar baseada puramente financeiramente (NPV)
        # Ajuste por perfil de risco pode ocorrer aqui
        
        strategies = {
            StrategyType.FINANCING: npv_fin,
            StrategyType.SAVE_INVEST: npv_inv,
        }
        if cons_result:
            strategies[StrategyType.CONSORTIUM] = npv_cons
            
        # Ordenar estratégias da melhor (maior NPV) para a pior
        ranked_strategies = sorted(strategies.items(), key=lambda x: x[1], reverse=True)
        best_strategy = ranked_strategies[0][0]
        
        # 5. Validação de Restrições (Liquidez)
        # Se a melhor estratégia estourar o orçamento, tentamos a próxima
        final_strategy = best_strategy
        budget_limit = request.max_monthly_budget or float('inf')
        
        if best_strategy == StrategyType.FINANCING and fin_result["monthly_payment"] > budget_limit:
            # Financiamento caro demais, fallback
            final_strategy = StrategyType.SAVE_INVEST # Padrão seguro
            if cons_result and cons_result["monthly_payment"] <= budget_limit:
                # Verifica se consórcio é melhor que Investir (geralmente sim em prazo)
                if npv_cons > npv_inv:
                    final_strategy = StrategyType.CONSORTIUM
        
        elif best_strategy == StrategyType.CONSORTIUM and cons_result and cons_result["monthly_payment"] > budget_limit:
            final_strategy = StrategyType.SAVE_INVEST
            
        # 6. Montar Resposta
        
        # Escolher dados da estratégia vencedora para preencher campos principais
        if final_strategy == StrategyType.FINANCING:
            selected_scenario = fin_result
        elif final_strategy == StrategyType.CONSORTIUM and cons_result:
            selected_scenario = cons_result
        else:
            final_strategy = StrategyType.SAVE_INVEST
            selected_scenario = inv_result
            
        # Calcular impacto de liquidez
        # (Parcela / Orçamento). Se orçamento não definido, usa 0 (sem impacto medido aqui)
        # O Service deve preencher max_monthly_budget com safe_to_spend se não vier do request
        monthly_cost = selected_scenario["monthly_payment"]
        liquidity_base = request.max_monthly_budget or monthly_cost # Evita div/0
        liquidity_impact = -(monthly_cost / liquidity_base) if liquidity_base > 0 else 0.0
        
        # Action Plan
        action_plan = self._generate_action_plan(final_strategy, selected_scenario, request)
        
        return SimulationResponse(
            recommended_strategy=final_strategy,
            costs=CostScenario(
                min_cost=float(selected_scenario["min_cost"]),
                expected_cost=float(selected_scenario["expected_cost"]),
                max_cost=float(selected_scenario["max_cost"])
            ),
            npv=NPVComparison(
                financing=float(npv_fin),
                consortium=float(npv_cons) if cons_result else None,
                save_invest=float(npv_inv),
                discount_rate_used=selic_monthly
            ),
            consortium_probability=cons_result["probability"] if cons_result else None,
            liquidity_impact=round(liquidity_impact, 4),
            months_to_achieve=selected_scenario["months"],
            action_plan=action_plan,
            confidence_score=0.95, # Mock: Fatorar qualidade dos dados (F1) depois
            data_sources=["bacen", "anbima", "market_rates", "internal_models"]
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HELPERS DE SIMULAÇÃO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _simulate_financing(self, req: SimulationRequest, rates: Dict[str, float]) -> Dict[str, Any]:
        """Simula cenário de financiamento."""
        cet_annual = rates.get("best_cet_annual", 0.15)
        # Fallback se best_cet_annual não vier (usa avg do tipo de bem)
        if "best_cet_annual" not in rates:
            # Tenta pegar pelo asset_type, sem connector aqui o caller deve passar pronto
            # Assumimos que 'best_cet_annual' já vem resolvido do Service
            pass

        # Calcular PRICE (ou método escolhido)
        # OBS: financing.py tem calculate_price e calculate_sac
        # Vamos comparar ambos e pegar o melhor para o usuário (geralmente SAC é mais barato total, mas PRICE parcela inicial menor)
        # Se usuário pediu PRICE, calculamos PRICE.
        
        meth = req.amortization_method # PRICE ou SAC
        
        if meth == "SAC":
            sim = financing.calculate_sac(req.principal, cet_annual, req.financing_months)
        else:
            sim = financing.calculate_price(req.principal, cet_annual, req.financing_months)
            
        # Calcular NPV
        # Fluxo: +Principal (recebe bem agora) -Entrada -Parcelas...
        # Ou simplificado: Custo presente = Entrada + NPV(Parcelas)
        # Como queremos comparar custos, vamos calcular o valor presente dos PAGAMENTOS
        # e inverter o sinal para representar "custo" (valor negativo de patrimônio).
        
        selic_monthly = (1 + rates.get("selic_annual", 0.10)) ** (1/12) - 1
        
        # Fluxo de pagamentos (sinais negativos)
        # Mês 0: -Entrada
        # Mês 1..N: -Parcela
        
        cashflows = [-req.down_payment]
        for p in sim.schedule:
            cashflows.append(-p["payment"])
            
        npv_val = npv.calculate_npv(cashflows, selic_monthly)
        
        return {
            "type": "FINANCING",
            "monthly_payment": sim.monthly_payment,
            "total_cost": sim.total_cost,
            "min_cost": sim.total_cost, # Em financiamento fixo, variação é pequena
            "expected_cost": sim.total_cost,
            "max_cost": sim.total_cost * 1.05, # Margem risco
            "npv": npv_val,
            "months": 0, # Conquista imediata (0 meses de espera)
            "sim_obj": sim
        }

    def _simulate_investment(self, req: SimulationRequest, rates: Dict[str, float]) -> Dict[str, Any]:
        """Simula cenário de poupar (CDI)"""
        cdi_annual = rates.get("cdi_annual", 0.10)
        
        # Calcular quanto precisa guardar ou quanto tempo leva
        if req.max_monthly_budget:
            # Se tem limite de orçamento, calcula tempo
            monthly_dep = req.max_monthly_budget
            months = investment.calculate_months_needed(
                req.target_amount, monthly_dep, cdi_annual, req.down_payment
            )
            # Se months for None (não converge), definimos um teto
            if months is None:
                months = 120
        else:
            # Sem limite, define prazo igual ao financiamento para comparar
            months = req.financing_months
            monthly_dep = investment.calculate_pmt_needed(
                req.target_amount, cdi_annual, months, req.down_payment
            )
            
        # Calcular NPV
        # Fluxo: -Entrada (investida) -Aportes... +Resgate Final
        selic_monthly = (1 + rates.get("selic_annual", 0.10)) ** (1/12) - 1
        
        cashflows = [-req.down_payment]
        cashflows.extend([-monthly_dep] * months)
        # No final recebe o bem (valor +), mas como estamos comparando CUSTO de aquisição,
        # o benefício de ter o bem anula o custo de compra.
        # Para ser comparável com Financiamento (onde recebe bem no t=0), 
        # a estratégia de investimento tem o custo de NÃO ter o bem por N meses (custo de oportunidade de uso).
        # Mas simplificando para MVP: NPV(Saídas).
        # Financiamento: paga caro, recebe cedo.
        # Investimento: paga barato, recebe tarde.
        # Para comparar maçãs com maçãs:
        # NPV do Financiamento já desconta fluxos futuros.
        # NPV do Investimento: fluxos de saída apenas.
        # A diferença de "ter o bem" é subjetiva, mas financeiramente o VPL captura o valor do dinheiro.
        
        npv_val = npv.calculate_npv(cashflows, selic_monthly)
        
        return {
            "type": "SAVE_INVEST",
            "monthly_payment": monthly_dep,
            "min_cost": req.target_amount, # Custo nominal é só o valor do bem (juros trabalharam a favor)
            "expected_cost": req.target_amount, 
            "max_cost": req.target_amount, 
            "npv": npv_val, # Será menos negativo que financiamento (ótimo), mas tem o 'months' alto
            "months": months,
            "sim_obj": None
        }

    def _simulate_consortium(self, req: SimulationRequest, rates: Dict[str, float]) -> Dict[str, Any]:
        """Simula cenário de consórcio."""
        
        # Parâmetros padrão de mercado (TODO: vir do connector ABAC na fase 2)
        admin_rate = 0.16 # 16% taxa adm total
        months = 60 # Grupos típicos
        
        sim = consortium.calculate_consortium_metrics(
            letter_value=req.target_amount,
            months=months,
            admin_rate=admin_rate,
            reserve_fund_rate=0.02,
            bid_amount=req.down_payment # Usa a entrada como lance
        )
        
        # NPV
        selic_monthly = (1 + rates.get("selic_annual", 0.10)) ** (1/12) - 1
        
        # Fluxo médio esperado:
        # Paga parcelas por 'months'
        cashflows = [-sim.monthly_payment] * months
        # Se deu lance, desembolsa no mês da contemplação (esperado)
        expected_month = sim.contemplation_month_expected
        if expected_month < len(cashflows):
            cashflows[expected_month] -= req.down_payment # Lance sai do caixa
            
        npv_val = npv.calculate_npv(cashflows, selic_monthly)
        
        prob = ConsortiumProbability(
            win_12m=sim.contemplation_probability["12m"],
            win_24m=sim.contemplation_probability["24m"],
            win_36m=sim.contemplation_probability.get("36m", sim.contemplation_probability["half_term"]), # Adaptar keys
            expected_months=expected_month,
            with_lance=(req.down_payment > 0)
        )
        
        return {
            "type": "CONSORTIUM",
            "monthly_payment": sim.monthly_payment,
            "min_cost": sim.total_cost * 0.95, 
            "expected_cost": sim.total_cost,
            "max_cost": sim.total_cost * 1.10, # Reajuste carta
            "npv": npv_val,
            "months": expected_month, # Tempo de espera esperado
            "probability": prob,
            "sim_obj": sim
        }

    def _generate_action_plan(self, strategy: StrategyType, scenario: Dict, req: SimulationRequest) -> List[ActionStep]:
        """Gera passos práticos baseados na estratégia escolhida."""
        steps = []
        
        if strategy == StrategyType.FINANCING:
            steps.append(ActionStep(
                step=1, 
                action=f"Reunir documentação para financiamento {req.asset_type.value.lower()}", 
                is_critical=True
            ))
            steps.append(ActionStep(
                step=2, 
                action=f"Dar entrada de {format_currency(req.down_payment)}", 
                amount=req.down_payment,
                is_critical=True
            ))
            steps.append(ActionStep(
                step=3,
                action=f"Pagar parcelas mensais de aprox. {format_currency(scenario['monthly_payment'])}",
                amount=scenario['monthly_payment']
            ))
            
        elif strategy == StrategyType.CONSORTIUM:
            steps.append(ActionStep(
                step=1,
                action="Aderir a um grupo de consórcio em andamento (média 60 meses)",
                is_critical=True
            ))
            if req.down_payment > 0:
                steps.append(ActionStep(
                    step=2,
                    action=f"Ofertá lance de {format_currency(req.down_payment)} logo no primeiro mês",
                    amount=req.down_payment,
                    is_critical=True
                ))
            steps.append(ActionStep(
                step=3,
                action="Aguardar contemplação (média esperada: {} meses)".format(scenario['months']),
                is_critical=False
            ))
            
        else: # SAVE_INVEST
            steps.append(ActionStep(
                step=1,
                action="Abrir conta em corretora de taxa zero",
                is_critical=True
            ))
            steps.append(ActionStep(
                step=2,
                action=f"Configurar aplicação automática mensal de {format_currency(scenario['monthly_payment'])} em CDB 100% CDI",
                amount=scenario['monthly_payment'],
                is_critical=True
            ))
            steps.append(ActionStep(
                step=3,
                action=f"Resgatar valor total em {scenario['months']} meses para compra à vista",
                deadline=None # TODO: calc date
            ))
            
        return steps
