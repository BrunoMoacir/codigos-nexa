"""
app/architect/simulators/sensitivity_analyzer.py - Análise de Sensibilidade

Feature: F3 - Nexa Architect
Version: 3.0.0 (Fase 3)

Responsabilidade:
    Analisar como variações nas variáveis-chave afetam o NPV de cada estratégia.
    Identifica qual parâmetro mais impacta a recomendação final e qual é o
    perfil de risco da simulação base.

Variáveis analisadas:
    - interest_rate: CET do financiamento ±2 p.p. (9 pontos)
    - months:        Prazo do financiamento ±6 meses (7 pontos)
    - down_payment:  Valor da entrada ±10% do original (9 pontos)
    - cdi_rate:      Taxa CDI (impacta rendimento do investimento) ±2 p.p. (9 pontos)

Decisões de design:
    - Sem chamadas de rede/banco — trabalha com os dados já coletados pelo
      ArchitectService (request + market_rates + baseline_response).
    - Reutiliza os mesmos calculadores do StrategyEngine para garantir
      consistência matemática.
    - Usa apenas stdlib (math, logging, dataclasses, datetime) — sem numpy.

Uso:
    from app.architect.simulators.sensitivity_analyzer import SensitivityAnalyzer

    analyzer = SensitivityAnalyzer()
    report = analyzer.analyze(request, market_rates, baseline_response)
    print(report.most_sensitive_variable)
    print(report.to_dict())
"""

import math
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any

from app.architect.models import SimulationRequest, SimulationResponse, StrategyType
from app.architect.calculators import financing as fin_calc
from app.architect.calculators import investment as inv_calc
from app.architect.calculators import npv as npv_calc
from app.architect.calculators import consortium as cons_calc

logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> float:
    """Converte para float, descartando NaN e infinito."""
    if value is None:
        return 0.0
    try:
        fval = float(value)
        if math.isnan(fval) or math.isinf(fval):
            return 0.0
        return fval
    except (TypeError, ValueError):
        return 0.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MODELOS DE RESULTADO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class SensitivityPoint:
    """
    NPV de cada estratégia para um valor específico de uma variável.

    Representa um único ponto na curva de sensibilidade:
    "o que acontece com o NPV quando esta variável vale X?"

    Attributes:
        delta:          Variação aplicada à variável base.
                        Ex: +0.02 = +2 p.p. para taxas, +6 para meses.
        param_value:    Valor absoluto do parâmetro neste ponto.
        npv_financing:  NPV do financiamento neste cenário.
        npv_invest:     NPV do investimento neste cenário.
        npv_consortium: NPV do consórcio (None se include_consortium=False).
        recommended:    Estratégia vencedora neste ponto (maior NPV).
    """

    delta: float
    param_value: float
    npv_financing: float
    npv_invest: float
    npv_consortium: Optional[float]
    recommended: str  # StrategyType.value


@dataclass
class VariableSensitivity:
    """
    Análise completa de sensibilidade de uma variável.

    Attributes:
        variable:       Identificador da variável ("interest_rate", "months", etc.)
        description:    Descrição legível para exibição.
        unit:           Unidade ("p.p.", "meses", "R$").
        base_value:     Valor original usado na simulação base.
        points:         Lista de pontos na curva (do mínimo ao máximo delta).
        npv_range:      Amplitude do NPV vencedor ao longo da curva (max - min).
                        Quanto maior, mais sensível é esta variável.
        elasticity:     Variação do NPV vencedor por unidade de delta.
                        Ex: R$ 5.000 de variação por 1 p.p. de taxa.
        strategy_flips: Quantas vezes a estratégia vencedora muda entre pontos
                        consecutivos. 0 = recomendação estável.
    """

    variable: str
    description: str
    unit: str
    base_value: float
    points: List[SensitivityPoint]
    npv_range: float
    elasticity: float
    strategy_flips: int


@dataclass
class SensitivityReport:
    """
    Relatório completo de análise de sensibilidade.

    Attributes:
        variables:               Análise de cada variável testada, ordenadas por
                                 impacto decrescente (mais sensível primeiro).
        most_sensitive_variable: Identificador da variável com maior npv_range.
        strategy_stability:      Fração de pontos (0–1) onde a estratégia não muda.
                                 1.0 = completamente estável, 0.0 = sempre muda.
        risk_profile:            "baixo" | "moderado" | "alto" — baseado em flips
                                 e elasticidade média.
        baseline_strategy:       Estratégia recomendada na simulação base (referência).
        generated_at:            Timestamp de geração.
    """

    variables: List[VariableSensitivity]
    most_sensitive_variable: str
    strategy_stability: float
    risk_profile: str
    baseline_strategy: str
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        """Serializa para dict (uso em API responses e logs)."""
        return {
            "variables": [
                {
                    "variable": v.variable,
                    "description": v.description,
                    "unit": v.unit,
                    "base_value": v.base_value,
                    "npv_range": round(v.npv_range, 2),
                    "elasticity": round(v.elasticity, 4),
                    "strategy_flips": v.strategy_flips,
                    "points": [
                        {
                            "delta": round(p.delta, 4),
                            "param_value": round(p.param_value, 4),
                            "npv_financing": round(p.npv_financing, 2),
                            "npv_invest": round(p.npv_invest, 2),
                            "npv_consortium": (
                                round(p.npv_consortium, 2)
                                if p.npv_consortium is not None
                                else None
                            ),
                            "recommended": p.recommended,
                        }
                        for p in v.points
                    ],
                }
                for v in self.variables
            ],
            "most_sensitive_variable": self.most_sensitive_variable,
            "strategy_stability": round(self.strategy_stability, 4),
            "risk_profile": self.risk_profile,
            "baseline_strategy": self.baseline_strategy,
            "generated_at": self.generated_at.isoformat(),
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ANALISADOR PRINCIPAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class SensitivityAnalyzer:
    """
    Analisa como variações nas variáveis-chave afetam o NPV de cada estratégia.

    Não faz chamadas de rede/banco. Recebe os dados já coletados pelo
    ArchitectService e recalcula as estratégias localmente para cada variação.

    Variáveis e faixas:
        interest_rate → CET do financiamento: ±2 p.p. (9 pontos, step 0.5 p.p.)
        months        → Prazo do financiamento: ±6 meses (7 pontos, step 2)
        down_payment  → Entrada: ±10% do valor base (9 pontos, step 2.5%)
        cdi_rate      → Taxa CDI: ±2 p.p. (9 pontos, step 0.5 p.p.)

    Usage:
        analyzer = SensitivityAnalyzer()
        report = analyzer.analyze(request, market_rates, baseline_response)
        print(report.most_sensitive_variable)   # ex: "interest_rate"
        print(report.risk_profile)              # ex: "moderado"
    """

    # (delta_min, delta_max, n_steps)
    _RANGES: Dict[str, tuple] = {
        "interest_rate": (-0.02, 0.02, 9),
        "months":        (-6.0,  6.0,  7),
        "down_payment":  (-0.10, 0.10, 9),
        "cdi_rate":      (-0.02, 0.02, 9),
    }

    _DESCRIPTIONS: Dict[str, str] = {
        "interest_rate": "Taxa de Juros do Financiamento (CET)",
        "months":        "Prazo do Financiamento",
        "down_payment":  "Valor da Entrada",
        "cdi_rate":      "Taxa CDI (Rendimento do Investimento)",
    }

    _UNITS: Dict[str, str] = {
        "interest_rate": "p.p.",
        "months":        "meses",
        "down_payment":  "R$",
        "cdi_rate":      "p.p.",
    }

    def analyze(
        self,
        request: SimulationRequest,
        market_rates: Dict[str, float],
        baseline_response: SimulationResponse,
    ) -> SensitivityReport:
        """
        Executa análise de sensibilidade completa para as 4 variáveis-chave.

        Args:
            request:           Parâmetros originais da simulação base.
            market_rates:      Taxas de mercado usadas na simulação base.
            baseline_response: Resultado da simulação base (ponto de referência).

        Returns:
            SensitivityReport com análise de todas as variáveis, ordenadas por
            impacto decrescente.
        """
        logger.info(
            "Iniciando análise de sensibilidade: user=%s, target=%.2f",
            request.user_id,
            request.target_amount,
        )

        selic_monthly = (1 + market_rates.get("selic_annual", 0.1075)) ** (1 / 12) - 1
        baseline_strategy = baseline_response.recommended_strategy.value

        variables = [
            self._analyze_interest_rate(request, market_rates, selic_monthly),
            self._analyze_months(request, market_rates, selic_monthly),
            self._analyze_down_payment(request, market_rates, selic_monthly),
            self._analyze_cdi_rate(request, market_rates, selic_monthly),
        ]

        # Ordena por impacto decrescente (maior npv_range = mais sensível)
        variables.sort(key=lambda v: v.npv_range, reverse=True)

        most_sensitive = variables[0].variable

        # Estabilidade: fração de pontos onde a estratégia não muda
        total_points = sum(len(v.points) for v in variables)
        stable_points = sum(
            sum(1 for p in v.points if p.recommended == baseline_strategy)
            for v in variables
        )
        strategy_stability = stable_points / total_points if total_points > 0 else 1.0

        # Perfil de risco baseado em flips e elasticidade
        total_flips = sum(v.strategy_flips for v in variables)
        avg_elasticity = sum(v.elasticity for v in variables) / len(variables)
        risk_profile = _compute_risk_profile(total_flips, avg_elasticity)

        logger.info(
            "Sensibilidade concluída: variável_crítica=%s, estabilidade=%.2f, risco=%s",
            most_sensitive,
            strategy_stability,
            risk_profile,
        )

        return SensitivityReport(
            variables=variables,
            most_sensitive_variable=most_sensitive,
            strategy_stability=strategy_stability,
            risk_profile=risk_profile,
            baseline_strategy=baseline_strategy,
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ANÁLISE POR VARIÁVEL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _analyze_interest_rate(
        self,
        request: SimulationRequest,
        market_rates: Dict[str, float],
        selic_monthly: float,
    ) -> VariableSensitivity:
        """Varia o CET do financiamento em ±2 p.p. e mede impacto no NPV."""
        base_cet = market_rates.get("best_cet_annual", 0.15)
        d_min, d_max, n = self._RANGES["interest_rate"]
        points = []

        for delta in _linspace(d_min, d_max, n):
            cet = max(0.001, base_cet + delta)
            npv_fin = self._npv_financing(request, cet, request.financing_months, selic_monthly)
            npv_inv = self._npv_investment(request, market_rates, selic_monthly)
            npv_cons = (
                self._npv_consortium(request, market_rates, selic_monthly)
                if request.include_consortium
                else None
            )
            points.append(SensitivityPoint(
                delta=round(delta, 4),
                param_value=round(cet, 4),
                npv_financing=round(npv_fin, 2),
                npv_invest=round(npv_inv, 2),
                npv_consortium=round(npv_cons, 2) if npv_cons is not None else None,
                recommended=_pick_strategy(npv_fin, npv_inv, npv_cons),
            ))

        return _build_sensitivity("interest_rate", self._DESCRIPTIONS, self._UNITS, base_cet, points)

    def _analyze_months(
        self,
        request: SimulationRequest,
        market_rates: Dict[str, float],
        selic_monthly: float,
    ) -> VariableSensitivity:
        """Varia o prazo do financiamento em ±6 meses."""
        base_months = request.financing_months
        cet = market_rates.get("best_cet_annual", 0.15)
        d_min, d_max, n = self._RANGES["months"]
        points = []

        for delta in _linspace(d_min, d_max, n):
            months = max(6, int(base_months + round(delta)))
            npv_fin = self._npv_financing(request, cet, months, selic_monthly)
            npv_inv = self._npv_investment(request, market_rates, selic_monthly)
            npv_cons = (
                self._npv_consortium(request, market_rates, selic_monthly)
                if request.include_consortium
                else None
            )
            points.append(SensitivityPoint(
                delta=float(delta),
                param_value=float(months),
                npv_financing=round(npv_fin, 2),
                npv_invest=round(npv_inv, 2),
                npv_consortium=round(npv_cons, 2) if npv_cons is not None else None,
                recommended=_pick_strategy(npv_fin, npv_inv, npv_cons),
            ))

        return _build_sensitivity("months", self._DESCRIPTIONS, self._UNITS, float(base_months), points)

    def _analyze_down_payment(
        self,
        request: SimulationRequest,
        market_rates: Dict[str, float],
        selic_monthly: float,
    ) -> VariableSensitivity:
        """
        Varia a entrada em ±10% do valor original.

        Quando down_payment base for zero, usa ±10% de target_amount como referência
        para que haja variação significativa nos pontos.
        """
        base_dp = request.down_payment
        reference = base_dp if base_dp > 0 else request.target_amount
        d_min, d_max, n = self._RANGES["down_payment"]
        points = []

        for frac in _linspace(d_min, d_max, n):
            dp = max(0.0, base_dp + reference * frac)
            dp = min(dp, request.target_amount * 0.9)  # limite: 90% do target
            principal = max(1.0, request.target_amount - dp)

            npv_fin = self._npv_financing_custom(
                request, market_rates, selic_monthly, dp, principal
            )
            npv_inv = self._npv_investment_custom(request, market_rates, selic_monthly, dp)
            npv_cons = (
                self._npv_consortium_custom(request, market_rates, selic_monthly, dp)
                if request.include_consortium
                else None
            )
            points.append(SensitivityPoint(
                delta=round(frac, 4),
                param_value=round(dp, 2),
                npv_financing=round(npv_fin, 2),
                npv_invest=round(npv_inv, 2),
                npv_consortium=round(npv_cons, 2) if npv_cons is not None else None,
                recommended=_pick_strategy(npv_fin, npv_inv, npv_cons),
            ))

        return _build_sensitivity("down_payment", self._DESCRIPTIONS, self._UNITS, base_dp, points)

    def _analyze_cdi_rate(
        self,
        request: SimulationRequest,
        market_rates: Dict[str, float],
        selic_monthly: float,
    ) -> VariableSensitivity:
        """Varia o CDI em ±2 p.p. — impacta o NPV do investimento."""
        base_cdi = market_rates.get("cdi_annual", 0.1025)
        cet = market_rates.get("best_cet_annual", 0.15)
        d_min, d_max, n = self._RANGES["cdi_rate"]
        points = []

        for delta in _linspace(d_min, d_max, n):
            cdi = max(0.001, base_cdi + delta)
            rates_variant = {**market_rates, "cdi_annual": cdi}

            npv_fin = self._npv_financing(request, cet, request.financing_months, selic_monthly)
            npv_inv = self._npv_investment(request, rates_variant, selic_monthly)
            npv_cons = (
                self._npv_consortium(request, market_rates, selic_monthly)
                if request.include_consortium
                else None
            )
            points.append(SensitivityPoint(
                delta=round(delta, 4),
                param_value=round(cdi, 4),
                npv_financing=round(npv_fin, 2),
                npv_invest=round(npv_inv, 2),
                npv_consortium=round(npv_cons, 2) if npv_cons is not None else None,
                recommended=_pick_strategy(npv_fin, npv_inv, npv_cons),
            ))

        return _build_sensitivity("cdi_rate", self._DESCRIPTIONS, self._UNITS, base_cdi, points)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CÁLCULOS DE NPV (mirrors do StrategyEngine, parametrizados)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _npv_financing(
        self,
        request: SimulationRequest,
        cet_annual: float,
        months: int,
        selic_monthly: float,
    ) -> float:
        try:
            if request.amortization_method.value == "SAC":
                sim = fin_calc.calculate_sac(request.principal, cet_annual, months)
            else:
                sim = fin_calc.calculate_price(request.principal, cet_annual, months)
            cashflows = [-request.down_payment] + [-row["payment"] for row in sim.schedule]
            return _safe_float(npv_calc.calculate_npv(cashflows, selic_monthly))
        except Exception:
            return 0.0

    def _npv_financing_custom(
        self,
        request: SimulationRequest,
        market_rates: Dict[str, float],
        selic_monthly: float,
        down_payment: float,
        principal: float,
    ) -> float:
        cet = market_rates.get("best_cet_annual", 0.15)
        try:
            if request.amortization_method.value == "SAC":
                sim = fin_calc.calculate_sac(principal, cet, request.financing_months)
            else:
                sim = fin_calc.calculate_price(principal, cet, request.financing_months)
            cashflows = [-down_payment] + [-row["payment"] for row in sim.schedule]
            return _safe_float(npv_calc.calculate_npv(cashflows, selic_monthly))
        except Exception:
            return 0.0

    def _npv_investment(
        self,
        request: SimulationRequest,
        market_rates: Dict[str, float],
        selic_monthly: float,
    ) -> float:
        return self._npv_investment_custom(request, market_rates, selic_monthly, request.down_payment)

    def _npv_investment_custom(
        self,
        request: SimulationRequest,
        market_rates: Dict[str, float],
        selic_monthly: float,
        down_payment: float,
    ) -> float:
        try:
            cdi_annual = market_rates.get("cdi_annual", 0.1025)
            if request.max_monthly_budget:
                monthly_dep = request.max_monthly_budget
                months = inv_calc.calculate_months_needed(
                    request.target_amount, monthly_dep, cdi_annual, down_payment
                )
                if months is None:
                    months = 120
            else:
                months = request.financing_months
                monthly_dep = inv_calc.calculate_pmt_needed(
                    request.target_amount, cdi_annual, months, down_payment
                )
            cashflows = [-down_payment] + [-monthly_dep] * months
            return _safe_float(npv_calc.calculate_npv(cashflows, selic_monthly))
        except Exception:
            return 0.0

    def _npv_consortium(
        self,
        request: SimulationRequest,
        market_rates: Dict[str, float],
        selic_monthly: float,
    ) -> Optional[float]:
        return self._npv_consortium_custom(request, market_rates, selic_monthly, request.down_payment)

    def _npv_consortium_custom(
        self,
        request: SimulationRequest,
        market_rates: Dict[str, float],
        selic_monthly: float,
        bid_amount: float,
    ) -> Optional[float]:
        try:
            admin_rate = market_rates.get("consortium_admin_rate", 0.17)
            cons_months = int(market_rates.get("consortium_months", 72))
            reserve_fund_rate = market_rates.get("consortium_reserve_fund_rate", 0.02)

            sim = cons_calc.calculate_consortium_metrics(
                letter_value=request.target_amount,
                months=cons_months,
                admin_rate=admin_rate,
                reserve_fund_rate=reserve_fund_rate,
                bid_amount=bid_amount,
            )
            cashflows = [-sim.monthly_payment] * cons_months
            expected_month = sim.contemplation_month_expected
            if expected_month < len(cashflows) and bid_amount > 0:
                cashflows[expected_month] -= bid_amount

            return _safe_float(npv_calc.calculate_npv(cashflows, selic_monthly))
        except Exception:
            return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS PUROS (sem estado)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _linspace(start: float, stop: float, n: int) -> List[float]:
    """Equivalente a numpy.linspace usando apenas stdlib."""
    if n <= 1:
        return [start]
    step = (stop - start) / (n - 1)
    return [start + step * i for i in range(n)]


def _pick_strategy(
    npv_fin: float,
    npv_inv: float,
    npv_cons: Optional[float],
) -> str:
    """Retorna o StrategyType.value com maior NPV (menor custo presente)."""
    candidates: Dict[str, float] = {
        StrategyType.FINANCING.value:   npv_fin,
        StrategyType.SAVE_INVEST.value: npv_inv,
    }
    if npv_cons is not None:
        candidates[StrategyType.CONSORTIUM.value] = npv_cons
    return max(candidates, key=lambda k: candidates[k])


def _build_sensitivity(
    variable: str,
    descriptions: Dict[str, str],
    units: Dict[str, str],
    base_value: float,
    points: List[SensitivityPoint],
) -> VariableSensitivity:
    """
    Computa métricas agregadas (npv_range, elasticity, strategy_flips)
    a partir da lista de pontos de sensibilidade.
    """
    # NPV range: amplitude entre o maior e menor NPV vencedor
    winner_npvs: List[float] = []
    for p in points:
        candidates = {
            "FINANCING":   p.npv_financing,
            "SAVE_INVEST": p.npv_invest,
        }
        if p.npv_consortium is not None:
            candidates["CONSORTIUM"] = p.npv_consortium
        winner_npvs.append(max(candidates.values()))

    npv_range = max(winner_npvs) - min(winner_npvs) if winner_npvs else 0.0

    # Elasticidade: variação total do NPV vencedor / variação total do delta
    max_delta = max((abs(p.delta) for p in points), default=0.0)
    elasticity = npv_range / max_delta if max_delta > 0 else 0.0

    # Flips: mudanças de estratégia entre pontos consecutivos
    strategy_flips = sum(
        1 for i in range(1, len(points))
        if points[i].recommended != points[i - 1].recommended
    )

    return VariableSensitivity(
        variable=variable,
        description=descriptions[variable],
        unit=units[variable],
        base_value=base_value,
        points=points,
        npv_range=round(npv_range, 2),
        elasticity=round(elasticity, 4),
        strategy_flips=strategy_flips,
    )


def _compute_risk_profile(total_flips: int, avg_elasticity: float) -> str:
    """
    Classifica o perfil de risco da simulação base com base em:
        - total_flips:      quantas vezes a estratégia muda ao variar os parâmetros
        - avg_elasticity:   variação média do NPV vencedor por unidade de delta

    Retorna:
        "baixo"    → recomendação estável e pouco sensível a variações
        "moderado" → alguma sensibilidade, mas sem mudanças frequentes
        "alto"     → recomendação muda com frequência ou NPV muito volátil
    """
    # Elasticidade é em R$/unidade de delta (ex: R$/p.p. ou R$/mês).
    # Limiares calibrados para simulações típicas de R$50k–R$1M.
    if total_flips == 0 and avg_elasticity < 200_000:
        return "baixo"
    if total_flips <= 2 and avg_elasticity < 1_000_000:
        return "moderado"
    return "alto"


__all__ = [
    "SensitivityAnalyzer",
    "SensitivityReport",
    "VariableSensitivity",
    "SensitivityPoint",
]
