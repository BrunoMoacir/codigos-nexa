"""
app/architect/calculators/leverage_optimizer.py - Otimizador de Alavancagem Patrimonial

Feature: F3 - Nexa Architect (F3.5 — Leverage Strategy)
Version: 1.0.0

Responsabilidade:
    Encontrar a MELHOR estratégia de alavancagem via consórcio para um imóvel,
    testando múltiplos multiplicadores e cenários de mercado. Ou recomendar
    que o usuário NÃO use alavancagem quando nenhum cenário fecha a conta.

Estratégia de alavancagem:
    1. Usuário entra num consórcio com carta de valor MAIOR que o imóvel desejado
    2. Quando contemplado, compra o imóvel e investe o surplus (carta - imóvel)
    3. Aluga o imóvel — renda de aluguel + rendimento do surplus pagam as parcelas
    4. Se a conta fecha: imóvel quitado + sobra investida ao final = patrimônio grátis

    Quando NÃO funciona:
    - Aluguel da região muito baixo (yield < 0.3%/mês do imóvel)
    - SELIC muito baixa (rendimento do surplus não compensa)
    - Taxa admin do consórcio muito alta (parcelas pesadas)
    - Multiplicador muito alto (surplus rende, mas parcela é gigante)

Abordagem:
    Em vez de assumir 2x, o otimizador testa multiplicadores de 1.2x a 3.0x
    em steps de 0.1x e encontra o ponto ótimo que maximiza o patrimônio final
    sem que o saldo investido fique negativo em nenhum mês (restrição de caixa).

    Se NENHUM multiplicador fecha a conta sem aporte extra do bolso, o módulo
    retorna a melhor alternativa parcial (com menor aporte mensal necessário)
    E uma recomendação clara de "alavancagem não viável neste cenário".

Integração:
    - Consome: consortium.py (parcelas), investment.py (rendimento SELIC)
    - Alimentado por: ConsortiumRateProvider (taxas reais), FipeZAP (aluguel)
    - Chamado por: StrategyEngine como 4ª estratégia (LEVERAGE_CONSORTIUM)
    - Exposto via: tool do agente get_leverage_simulation

Uso:
    optimizer = LeverageOptimizer()
    result = optimizer.find_optimal(
        asset_value=300000,
        monthly_rent=1800,
        selic_annual=0.1475,
        admin_rate=0.18,
        consortium_months=180,
    )
    if result.is_viable:
        print(f"Carta ideal: {result.optimal_letter_value}")
        print(f"Patrimônio final: {result.final_patrimony}")
    else:
        print(f"Alavancagem inviável: {result.rejection_reason}")
"""

import math
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULTADO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class MonthlySnapshot:
    """Estado financeiro em um mês específico da simulação."""
    month: int
    invested_balance: float       # Saldo aplicado na SELIC
    selic_income: float           # Rendimento SELIC do mês
    rent_income: float            # Aluguel recebido
    consortium_payment: float     # Parcela do consórcio
    net_cashflow: float           # Entradas - Saídas do mês
    out_of_pocket: float          # Quanto saiu do bolso (0 se auto-sustentável)
    cumulative_out_of_pocket: float  # Total que saiu do bolso até agora


@dataclass
class ScenarioResult:
    """Resultado de um cenário específico (um multiplicador)."""
    multiplier: float
    letter_value: float
    surplus_invested: float
    monthly_payment: float

    # Fluxo mensal
    monthly_rent_income: float
    monthly_selic_income_initial: float  # Rendimento SELIC do mês 1
    monthly_net_initial: float           # Saldo líquido no mês 1

    # Resultado final
    final_invested_balance: float
    final_patrimony: float          # imóvel + saldo investido
    total_paid_consortium: float
    total_rent_received: float
    total_selic_earned: float
    total_out_of_pocket: float      # Total que saiu do bolso do usuário
    real_cost: float                # Custo real = total pago - total recebido

    # Viabilidade
    is_self_sustaining: bool        # Nunca precisou de aporte do bolso
    min_balance_month: int          # Mês em que o saldo investido foi mais baixo
    min_balance_value: float        # Valor mais baixo do saldo investido
    months_negative: int            # Quantos meses o saldo ficou negativo
    max_monthly_deficit: float      # Maior déficit mensal (se houver)

    # Cobertura
    rent_coverage_pct: float        # Aluguel / Parcela (%)
    total_coverage_pct: float       # (Aluguel + SELIC inicial) / Parcela (%)


@dataclass
class LeverageResult:
    """Resultado completo do otimizador de alavancagem."""

    # Decisão principal
    is_viable: bool                 # Existe pelo menos 1 cenário auto-sustentável?
    recommendation: str             # Texto em linguagem natural
    rejection_reason: Optional[str] # Se não viável, por quê

    # Cenário ótimo (melhor patrimônio final entre os viáveis)
    optimal: Optional[ScenarioResult]
    optimal_multiplier: Optional[float]
    optimal_letter_value: Optional[float]
    final_patrimony: Optional[float]

    # Melhor cenário parcial (menor aporte do bolso, se nenhum for viável)
    best_partial: Optional[ScenarioResult]

    # Todos os cenários testados (para visualização)
    all_scenarios: List[ScenarioResult]

    # Inputs usados (para reprodutibilidade)
    asset_value: float
    monthly_rent: float
    selic_annual: float
    admin_rate: float
    consortium_months: int

    # Métricas de referência
    rent_yield_monthly: float       # Aluguel / Valor do imóvel (mensal)
    rent_yield_annual: float        # Aluguel / Valor do imóvel (anual)

    def to_dict(self) -> Dict:
        return asdict(self)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OTIMIZADOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class LeverageOptimizer:
    """
    Encontra a estratégia ótima de alavancagem via consórcio.

    Testa multiplicadores de 1.2x a 3.0x e seleciona o que maximiza
    patrimônio final sem o saldo investido ficar negativo.

    Se nenhum cenário é auto-sustentável, retorna o melhor parcial
    (menor aporte do bolso) com recomendação clara de inviabilidade.
    """

    # Range de multiplicadores a testar
    MULT_MIN = 1.2
    MULT_MAX = 3.0
    MULT_STEP = 0.1

    # Thresholds de viabilidade
    MIN_RENT_YIELD_MONTHLY = 0.003   # 0.3%/mês — abaixo disso, aluguel muito baixo
    MIN_SURPLUS_RATIO = 0.15         # Surplus deve ser >= 15% da carta
    MAX_DEFICIT_MONTHS_PCT = 0.10    # Máx 10% dos meses em déficit (margem de segurança)

    def find_optimal(
        self,
        asset_value: float,
        monthly_rent: float,
        selic_annual: float,
        admin_rate: float,
        consortium_months: int,
        reserve_fund_rate: float = 0.02,
        annual_adjustment_rate: float = 0.0,
        multipliers: Optional[List[float]] = None,
    ) -> LeverageResult:
        """
        Testa múltiplos cenários e encontra a alavancagem ótima.

        Args:
            asset_value:             Valor do imóvel desejado (R$)
            monthly_rent:            Aluguel mensal estimado da região (R$)
            selic_annual:            Taxa SELIC anual (decimal, ex: 0.1325)
            admin_rate:              Taxa de administração do consórcio (decimal)
            consortium_months:       Prazo do grupo (meses)
            reserve_fund_rate:       Fundo de reserva (decimal)
            annual_adjustment_rate:  Reajuste anual da carta (0 = sem reajuste)
            multipliers:             Lista personalizada de multiplicadores.
                                     None = testa de 1.2x a 3.0x em steps de 0.1x.

        Returns:
            LeverageResult com decisão, cenário ótimo e todos os cenários testados.
        """
        if asset_value <= 0:
            raise ValueError("Valor do imóvel deve ser positivo")
        if monthly_rent < 0:
            raise ValueError("Aluguel não pode ser negativo")
        if selic_annual <= -1:
            raise ValueError("SELIC inválida")
        if consortium_months <= 0:
            raise ValueError("Prazo deve ser positivo")

        # Métricas de referência
        rent_yield_m = monthly_rent / asset_value if asset_value > 0 else 0
        rent_yield_a = rent_yield_m * 12

        # Multiplicadores a testar
        if multipliers is None:
            mult_count = int((self.MULT_MAX - self.MULT_MIN) / self.MULT_STEP) + 1
            mults = [round(self.MULT_MIN + i * self.MULT_STEP, 1) for i in range(mult_count)]
        else:
            mults = sorted(multipliers)

        # Simular cada cenário
        all_scenarios: List[ScenarioResult] = []
        viable_scenarios: List[ScenarioResult] = []
        best_partial: Optional[ScenarioResult] = None

        for mult in mults:
            scenario = self._simulate_scenario(
                asset_value=asset_value,
                multiplier=mult,
                monthly_rent=monthly_rent,
                selic_annual=selic_annual,
                admin_rate=admin_rate,
                reserve_fund_rate=reserve_fund_rate,
                consortium_months=consortium_months,
                annual_adjustment_rate=annual_adjustment_rate,
            )
            all_scenarios.append(scenario)

            if scenario.is_self_sustaining:
                viable_scenarios.append(scenario)
            else:
                if best_partial is None or scenario.total_out_of_pocket < best_partial.total_out_of_pocket:
                    best_partial = scenario

        # Selecionar ótimo entre os viáveis (maior patrimônio final)
        optimal: Optional[ScenarioResult] = None
        if viable_scenarios:
            optimal = max(viable_scenarios, key=lambda s: s.final_patrimony)

        # Montar resultado
        is_viable = optimal is not None

        if is_viable:
            recommendation = self._build_recommendation_viable(optimal, asset_value, consortium_months)
            rejection = None
        else:
            recommendation, rejection = self._build_recommendation_not_viable(
                asset_value, monthly_rent, rent_yield_m, selic_annual,
                admin_rate, best_partial
            )

        return LeverageResult(
            is_viable=is_viable,
            recommendation=recommendation,
            rejection_reason=rejection,
            optimal=optimal,
            optimal_multiplier=optimal.multiplier if optimal else None,
            optimal_letter_value=optimal.letter_value if optimal else None,
            final_patrimony=optimal.final_patrimony if optimal else None,
            best_partial=best_partial if not is_viable else None,
            all_scenarios=all_scenarios,
            asset_value=asset_value,
            monthly_rent=monthly_rent,
            selic_annual=selic_annual,
            admin_rate=admin_rate,
            consortium_months=consortium_months,
            rent_yield_monthly=round(rent_yield_m, 6),
            rent_yield_annual=round(rent_yield_a, 4),
        )

    def _simulate_scenario(
        self,
        asset_value: float,
        multiplier: float,
        monthly_rent: float,
        selic_annual: float,
        admin_rate: float,
        reserve_fund_rate: float,
        consortium_months: int,
        annual_adjustment_rate: float,
    ) -> ScenarioResult:
        """
        Simula um cenário completo de alavancagem para um multiplicador.

        Fluxo mês a mês:
        1. Rendimento SELIC sobre o saldo investido
        2. + Aluguel recebido
        3. - Parcela do consórcio (com reajuste se houver)
        4. = Saldo líquido → reinvestido (ou aporte do bolso se negativo)
        """
        letter_value = asset_value * multiplier
        surplus = letter_value - asset_value

        total_rate = admin_rate + reserve_fund_rate
        selic_monthly = (1 + selic_annual) ** (1 / 12) - 1
        adj_monthly = (1 + annual_adjustment_rate) ** (1 / 12) - 1

        # Simular mês a mês
        invested = surplus
        current_letter = letter_value
        total_paid = 0.0
        total_rent = 0.0
        total_selic = 0.0
        total_oop = 0.0
        min_balance = surplus
        min_balance_month = 0
        months_negative = 0
        max_deficit = 0.0

        for month in range(1, consortium_months + 1):
            # Reajuste da carta (a partir do mês 2)
            if month > 1 and annual_adjustment_rate > 0:
                current_letter *= (1 + adj_monthly)

            # Parcela do mês
            payment = current_letter * (1 + total_rate) / consortium_months

            # Rendimento SELIC do saldo (só se positivo)
            selic_income = max(invested, 0) * selic_monthly

            # Fluxo do mês
            net = monthly_rent + selic_income - payment

            # Atualizar saldo
            invested += net
            total_paid += payment
            total_rent += monthly_rent
            total_selic += selic_income

            # Aporte do bolso se saldo ficou negativo
            if invested < 0:
                oop = -invested  # quanto precisou aportar
                total_oop += oop
                # Na prática, o usuário aportaria e o saldo volta a 0
                # Mas mantemos negativo para detectar inviabilidade real
                months_negative += 1
                if -net > max_deficit:
                    max_deficit = -net

            # Tracking de mínimo
            if invested < min_balance:
                min_balance = invested
                min_balance_month = month

        # Resultado do cenário
        final_balance = invested
        final_patrimony = asset_value + max(final_balance, 0)

        # Métricas de cobertura (mês 1)
        payment_m1 = letter_value * (1 + total_rate) / consortium_months
        selic_m1 = surplus * selic_monthly
        rent_coverage = (monthly_rent / payment_m1 * 100) if payment_m1 > 0 else 0
        total_coverage = ((monthly_rent + selic_m1) / payment_m1 * 100) if payment_m1 > 0 else 0

        is_self_sustaining = min_balance >= 0

        return ScenarioResult(
            multiplier=round(multiplier, 1),
            letter_value=round(letter_value, 2),
            surplus_invested=round(surplus, 2),
            monthly_payment=round(payment_m1, 2),
            monthly_rent_income=round(monthly_rent, 2),
            monthly_selic_income_initial=round(selic_m1, 2),
            monthly_net_initial=round(monthly_rent + selic_m1 - payment_m1, 2),
            final_invested_balance=round(final_balance, 2),
            final_patrimony=round(final_patrimony, 2),
            total_paid_consortium=round(total_paid, 2),
            total_rent_received=round(total_rent, 2),
            total_selic_earned=round(total_selic, 2),
            total_out_of_pocket=round(total_oop, 2),
            real_cost=round(max(total_paid - total_rent - total_selic, 0), 2),
            is_self_sustaining=is_self_sustaining,
            min_balance_month=min_balance_month,
            min_balance_value=round(min_balance, 2),
            months_negative=months_negative,
            max_monthly_deficit=round(max_deficit, 2),
            rent_coverage_pct=round(rent_coverage, 1),
            total_coverage_pct=round(total_coverage, 1),
        )

    # ── Geração de recomendações ──────────────────────────────────

    @staticmethod
    def _build_recommendation_viable(
        optimal: ScenarioResult,
        asset_value: float,
        months: int,
    ) -> str:
        fmt = lambda v: f"R$ {v:,.0f}".replace(",", ".")
        return (
            f"Alavancagem viável. Carta ideal: {fmt(optimal.letter_value)} "
            f"({optimal.multiplier}x o valor do imóvel de {fmt(asset_value)}). "
            f"Você investe {fmt(optimal.surplus_invested)} na SELIC e o rendimento "
            f"({fmt(optimal.monthly_selic_income_initial)}/mês) + aluguel "
            f"({fmt(optimal.monthly_rent_income)}/mês) cobrem "
            f"{optimal.total_coverage_pct:.0f}% da parcela de "
            f"{fmt(optimal.monthly_payment)}/mês. "
            f"A operação se paga sozinha. Ao final de {months} meses: "
            f"imóvel quitado + {fmt(max(optimal.final_invested_balance, 0))} investidos = "
            f"patrimônio de {fmt(optimal.final_patrimony)} sem desembolso mensal."
        )

    @staticmethod
    def _build_recommendation_not_viable(
        asset_value: float,
        monthly_rent: float,
        rent_yield_m: float,
        selic_annual: float,
        admin_rate: float,
        best_partial: Optional[ScenarioResult],
    ) -> tuple:
        fmt = lambda v: f"R$ {v:,.0f}".replace(",", ".")

        reasons = []
        if rent_yield_m < 0.003:
            reasons.append(
                f"o aluguel ({fmt(monthly_rent)}/mês) representa apenas "
                f"{rent_yield_m*100:.2f}% do valor do imóvel — muito baixo "
                f"para cobrir parcelas de consórcio"
            )
        if selic_annual < 0.08:
            reasons.append(
                f"a SELIC está em {selic_annual*100:.1f}% a.a., rendimento "
                f"insuficiente para complementar o aluguel"
            )
        if admin_rate > 0.20:
            reasons.append(
                f"a taxa de administração do consórcio ({admin_rate*100:.0f}%) "
                f"é alta, elevando as parcelas"
            )
        if not reasons:
            reasons.append("a combinação de aluguel + rendimento não cobre as parcelas em nenhum multiplicador")

        rejection = "; ".join(reasons) + "."

        if best_partial:
            recommendation = (
                f"Alavancagem NÃO viável para este imóvel — {rejection} "
                f"O melhor cenário parcial ({best_partial.multiplier}x) exigiria "
                f"{fmt(best_partial.max_monthly_deficit)}/mês do seu bolso. "
                f"Recomendação: considere financiamento direto, consórcio simples (1x), "
                f"ou busque imóvel com aluguel maior (yield > 0.5%/mês do valor)."
            )
        else:
            recommendation = (
                f"Alavancagem NÃO viável para este imóvel — {rejection} "
                f"Recomendação: consórcio simples (1x) ou financiamento direto."
            )

        return recommendation, rejection


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FUNÇÕES AUXILIARES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def quick_viability_check(
    asset_value: float,
    monthly_rent: float,
    selic_annual: float,
    admin_rate: float,
    consortium_months: int,
) -> Dict:
    """
    Verificação rápida de viabilidade SEM rodar o otimizador completo.

    Útil para o agente fazer uma triagem antes de rodar a simulação pesada.
    Calcula se a conta fecha para multiplicador 2.0x (cenário médio).

    Returns:
        Dict com likely_viable (bool), coverage_pct, reason (str).
    """
    if asset_value <= 0 or monthly_rent <= 0:
        return {"likely_viable": False, "coverage_pct": 0, "reason": "Dados inválidos"}

    letter = asset_value * 2.0
    surplus = letter - asset_value  # = asset_value
    total_rate = admin_rate + 0.02
    payment = letter * (1 + total_rate) / consortium_months
    selic_m = (1 + selic_annual) ** (1/12) - 1
    selic_income = surplus * selic_m
    total_income = monthly_rent + selic_income
    coverage = total_income / payment * 100 if payment > 0 else 0

    if coverage >= 100:
        return {"likely_viable": True, "coverage_pct": round(coverage, 1),
                "reason": "Aluguel + SELIC cobrem 100% da parcela no cenário 2x"}
    elif coverage >= 80:
        return {"likely_viable": True, "coverage_pct": round(coverage, 1),
                "reason": f"Cobertura de {coverage:.0f}% — viável com multiplicador menor"}
    else:
        return {"likely_viable": False, "coverage_pct": round(coverage, 1),
                "reason": f"Cobertura de apenas {coverage:.0f}% — provavelmente inviável"}


__all__ = [
    "LeverageOptimizer",
    "LeverageResult",
    "ScenarioResult",
    "MonthlySnapshot",
    "quick_viability_check",
]
