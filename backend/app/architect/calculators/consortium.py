"""
app/architect/calculators/consortium.py - Calculadora de Consórcio (Monte Carlo)

Feature: F3 - Nexa Architect
Version: 1.0.0

Responsabilidade:
Simular o comportamento de um grupo de consórcio para estimar:
1. Probabilidade de contemplação mensal (sorteio + lance).
2. Custo total esperado (considerando inflação da carta e taxas).
3. Prazo médio de contemplação.

Metodologia:
Utiliza Simulação de Monte Carlo para modelar os sorteios e a distribuição
de lances do grupo, gerando cenários probablisticos.
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
import random
import numpy as np
from app.architect.utils.formatters import format_currency, format_percentage

@dataclass
class ConsortiumResult:
    """
    Resultado da simulação de consórcio.
    """
    contemplation_month_expected: int
    contemplation_probability: Dict[str, float]  # ex: {"6m": 0.1, "12m": 0.3}
    total_cost: float
    monthly_payment: float
    admin_fee_total: float
    reserve_fund_total: float
    bid_amount_needed: float  # Lance estimado necessário
    scenarios: int  # Número de cenários simulados
    
    def to_dict(self) -> Dict:
        return asdict(self)


def calculate_consortium_metrics(
    letter_value: float,
    months: int,
    admin_rate: float,
    reserve_fund_rate: float = 0.0,
    bid_strategy: str = "fixed",  # 'fixed' (embutido) ou 'free' (recurso próprio)
    bid_amount: float = 0.0,
    num_simulations: int = 2000
) -> ConsortiumResult:
    """
    Simula um cenário de consórcio para estimar custos e prazos.
    
    Args:
        letter_value: Valor da carta de crédito (R$)
        months: Prazo do grupo (meses)
        admin_rate: Taxa de administração total (%) (ex: 0.15 para 15%)
        reserve_fund_rate: Fundo de reserva total (%)
        bid_strategy: 'fixed' (lance embutido) ou 'free' (lance livre)
        bid_amount: Valor disponível para lance (se bid_strategy='free')
        num_simulations: Número de iterações de Monte Carlo
        
    Returns:
        ConsortiumResult com estatísticas agregadas.
    """
    
    # 1. Cálculos Determinísticos (Custos Fixos)
    total_rate = admin_rate + reserve_fund_rate
    total_cost_nominal = letter_value * (1 + total_rate)
    monthly_payment = total_cost_nominal / months
    
    admin_fee_total = letter_value * admin_rate
    reserve_fund_total = letter_value * reserve_fund_rate
    
    # 2. Simulação de Monte Carlo para Contemplação
    # Premissas do modelo simplificado:
    # - Grupo com 200 participantes (padrão de mercado)
    # - 1 contemplado por sorteio, 1 por lance livre, 1 por lance fixo (se houver) por mês
    # - Distribuição de lances segue uma Log-Normal (maioria lances baixos, alguns altos)
    
    contemplation_months = []
    
    # Ajuste do lance efetivo
    effective_bid = bid_amount
    if bid_strategy == "fixed":
        # Lance embutido reduz a carta, mas usa % da própria carta
        # Geralmente 20-30%
        effective_bid = letter_value * 0.25 
    
    bid_percentage = effective_bid / letter_value
    
    for _ in range(num_simulations):
        simulated_month = _simulate_single_run(
            months=months,
            user_bid_ratio=bid_percentage,
            group_size=200
        )
        contemplation_months.append(simulated_month)
        
    # 3. Estatísticas
    contemplation_months = np.array(contemplation_months)
    expected_month = int(np.median(contemplation_months))
    
    # Probabilidades acumuladas
    prob_6m = np.sum(contemplation_months <= 6) / num_simulations
    prob_12m = np.sum(contemplation_months <= 12) / num_simulations
    prob_24m = np.sum(contemplation_months <= 24) / num_simulations
    prob_half = np.sum(contemplation_months <= (months // 2)) / num_simulations
    
    probabilities = {
        "6m": round(float(prob_6m), 4),
        "12m": round(float(prob_12m), 4),
        "24m": round(float(prob_24m), 4),
        "half_term": round(float(prob_half), 4)
    }
    
    return ConsortiumResult(
        contemplation_month_expected=expected_month,
        contemplation_probability=probabilities,
        total_cost=round(total_cost_nominal, 2),
        monthly_payment=round(monthly_payment, 2),
        admin_fee_total=round(admin_fee_total, 2),
        reserve_fund_total=round(reserve_fund_total, 2),
        bid_amount_needed=round(effective_bid, 2),
        scenarios=num_simulations
    )


def _simulate_single_run(months: int, user_bid_ratio: float, group_size: int) -> int:
    """
    Executa uma única simulação da trajetória do usuário no grupo.
    
    Retorna: Mês da contemplação (1 a months)
    """
    participants = group_size
    contemplated = 0
    
    # Média e desvio padrão históricos aproximados de lances (em %)
    # Lances tendem a ser mais altos no início e caem com o tempo
    base_bid_mean = 0.40  # 40% média inicial
    base_bid_std = 0.10
    
    for month in range(1, months + 1):
        if participants <= 0:
            return month
            
        # 1. Sorteio
        # Probabilidade simples: 1 chance em (total - contemplados)
        if random.random() < (1 / participants):
            return month
        
        participants -= 1 # Alguém foi sorteado (não o usuário)
        
        # 2. Lances
        # Gerar lances competitivos do mês
        # Decaimento linear da média de lances ao longo do tempo
        decay_factor = 1 - (month / months)
        current_mean = base_bid_mean * decay_factor
        
        # Simular o maior lance do mês (vencedor)
        winning_bid = np.random.normal(current_mean, base_bid_std)
        winning_bid = max(0.0, min(1.0, winning_bid)) # Clip entre 0% e 100%
        
        # Se usuário ofertou lance
        if user_bid_ratio > 0:
            # Se lance do usuário > lance vencedor simulado do grupo
            if user_bid_ratio >= winning_bid:
                return month
        
        participants -= 1 # Alguém venceu no lance
        
    return months # Caso não contemplado, recebe no final


__all__ = ["calculate_consortium_metrics", "ConsortiumResult"]
