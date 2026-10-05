"""
app/optimizer/miles_valuator.py
M2.3 + PointValuationEngine — Motor de Valoração de Milhas (Card Optimizer v2.1)

Carrega data/cards/miles_valuation.json e fornece taxas de conversão
dinâmicas por programa de fidelidade e cenário de resgate.

Cenários:
    pessimistic  → resgate em produtos / cashback (P25 do mercado)
    expected     → transferência para companhia aérea parceira (P50)
    optimistic   → promoção de transferência com bônus (P75)

POINT_VALUE_DISTRIBUTIONS: distribuição de mercado por programa (R$/ponto).
    Fonte: MaxMilhas + PassagensImperdíveis (atualização mensal).
    Scores de ranking usam P25 (conservador). Display ao usuário usa P50.
    Intervalo P25–P75 é mostrado quando otimista/pessimista divergem > 50%.

Uso:
    valuator = get_valuator()
    rate = valuator.get_rate("livelo", "expected")           # R$ 16.0 / 1.000 pts
    p25  = valuator.get_conservative_rate("livelo")          # P25 em R$/1.000 pts
    value = valuator.compute_points_value(2.0, 3600.0, "livelo", "expected")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from app.core.formatacao import brl

logger = logging.getLogger(__name__)

_VALUATION_FILE = (
    Path(__file__).parent.parent.parent / "data" / "cards" / "miles_valuation.json"
)

# Mapeia os nomes de cenário usados no simulador para as chaves do JSON
_SCENARIO_KEY: dict[str, str] = {
    "conservative": "pessimistic_per_1000",
    "min": "pessimistic_per_1000",
    "pessimistic": "pessimistic_per_1000",
    "expected": "expected_per_1000",
    "max": "optimistic_per_1000",
    "optimistic": "optimistic_per_1000",
}

# Distribuição de mercado por programa — (P25, P50, P75) em R$/ponto
# Fonte: miles_valuation.json (pessimistic/expected/optimistic_per_1000 ÷ 1000)
# Programas sem entrada no JSON usam estimativas de mercado (latam_pass, itau_multiplus, etc.)
# P25 → usado para scoring/ranking (conservador)
# P50 → mostrado ao usuário como "valor esperado"
# P75 → mostrado como "cenário otimista" quando otimista/pessimista divergem > 50%
POINT_VALUE_DISTRIBUTIONS: dict[str, tuple[float, float, float]] = {
    # Sincronizados com miles_valuation.json (Mar/2026)
    "smiles":          (0.012, 0.022, 0.040),
    "livelo":          (0.008, 0.016, 0.028),
    "nu_pontos":       (0.008, 0.014, 0.022),
    "atomos":          (0.007, 0.014, 0.024),
    # Estimativas de mercado (programas não cobertos pelo JSON)
    "latam_pass":      (0.013, 0.021, 0.035),
    "itau_multiplus":  (0.013, 0.017, 0.023),
    "xp_pontos":       (0.020, 0.025, 0.032),
    "membership_amex": (0.017, 0.022, 0.030),
    "esfera":          (0.013, 0.018, 0.025),
    "stix":            (0.012, 0.018, 0.025),
}


class MilesValuator:
    """
    Retorna o valor em R$ por 1.000 pontos/milhas de acordo com o
    programa de fidelidade e o cenário de resgate do usuário.

    Se o programa não estiver na tabela ou o arquivo não existir, os
    métodos retornam None/0.0 — o caller deve usar points_conversion_rate
    fixo do CardRecord como fallback.
    """

    def __init__(self) -> None:
        self._table: dict[str, dict] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        try:
            with open(_VALUATION_FILE, encoding="utf-8") as f:
                self._table = json.load(f)
            self._loaded = True
            logger.debug("miles_valuation.json carregado (%d programas)", len(self._table))
        except FileNotFoundError:
            logger.warning("miles_valuation.json não encontrado — usando rates fixos")
            self._loaded = True
        except Exception as exc:
            logger.error("Erro ao carregar miles_valuation.json: %s", exc)
            self._loaded = True

    def get_rate(self, program: str, scenario: str) -> float | None:
        """
        Retorna R$ por 1.000 pontos para o programa e cenário dados.

        Prioriza POINT_VALUE_DISTRIBUTIONS (P25/P50/P75) quando o programa está na
        tabela estática. Cai no JSON como fallback para programas não mapeados.

        Args:
            program: chave do programa (ex: "livelo", "smiles", "atomos")
            scenario: "pessimistic" | "expected" | "optimistic" (aceita "min"/"max")

        Returns:
            Taxa em R$/1.000 pts, ou None se programa não encontrado.
        """
        key = program.lower()
        dist = POINT_VALUE_DISTRIBUTIONS.get(key)
        if dist is not None:
            # "conservative" compartilha o P25 com "min", mas os dois NÃO são
            # a mesma coisa a jusante: "min" é o piso do intervalo exibido
            # (P25 + gasto −20%), "conservative" é o gasto ESPERADO valorizado
            # a P25 — o número que o ranking ordena.
            if scenario in ("min", "pessimistic", "conservative"):
                return dist[0] * 1000  # P25 em R$/1.000 pts
            elif scenario in ("max", "optimistic"):
                return dist[2] * 1000  # P75
            else:
                return dist[1] * 1000  # P50 (expected)

        # Fallback: JSON com pessimistic/expected/optimistic
        self._ensure_loaded()
        prog = self._table.get(key)
        if not prog:
            return None
        json_key = _SCENARIO_KEY.get(scenario, "expected_per_1000")
        value = prog.get(json_key)
        return float(value) if value is not None else None

    def get_conservative_rate(self, program: str) -> float | None:
        """
        Retorna a taxa P25 (conservadora) para o programa em R$/1.000 pts.

        É o princípio 1 da arquitetura — 'point values usam P25 do mercado,
        não média' — e vale para ORDENAR, não para exibir: o usuário vê o
        P50 em net_gain_expected e a banda em net_gain_min/max, enquanto o
        ranking compara cartões pelo net_gain_conservative do simulador,
        que chega aqui pelo cenário "conservative".

        Cashback não passa por esta função (R$1 vale R$1); milha passa,
        porque a banda P25–P75 chega a 3x. Ordenar os dois pelo ponto médio
        da milha inclinaria o ranking para cartão de pontos.
        """
        key = program.lower()
        dist = POINT_VALUE_DISTRIBUTIONS.get(key)
        if dist is not None:
            return dist[0] * 1000  # P25 → R$/1.000 pts

        # Fallback: usa pessimistic do JSON
        return self.get_rate(program, "pessimistic")

    def get_interval(self, program: str) -> tuple[float, float, float] | None:
        """
        Retorna (P25, P50, P75) em R$/1.000 pts para display ao usuário.

        O intervalo P25–P75 é exibido ao usuário quando P75/P25 ≥ 1.5 (banda larga).
        """
        key = program.lower()
        dist = POINT_VALUE_DISTRIBUTIONS.get(key)
        if dist is not None:
            return dist[0] * 1000, dist[1] * 1000, dist[2] * 1000
        return None

    def get_partners(self, program: str) -> list[str]:
        """Retorna lista de parceiros de transferência do programa."""
        self._ensure_loaded()
        return list(self._table.get(program.lower(), {}).get("transfer_partners", []))

    def is_known(self, program: str) -> bool:
        """Verifica se o programa está na tabela de valoração."""
        self._ensure_loaded()
        return program.lower() in self._table

    def compute_points_value(
        self,
        points_per_brl: float,
        spend: float,
        program: str,
        scenario: str,
    ) -> float:
        """
        Calcula o valor monetário dos pontos acumulados em um determinado gasto.

        Args:
            points_per_brl: pontos acumulados por R$ gasto
            spend: gasto total (R$)
            program: programa de fidelidade do cartão
            scenario: cenário de resgate ("pessimistic"/"expected"/"optimistic")

        Returns:
            Valor em R$ dos pontos. 0.0 se programa desconhecido.
        """
        rate = self.get_rate(program, scenario)
        if rate is None:
            return 0.0
        points = spend * points_per_brl
        return (points / 1000.0) * rate

    def describe_scenario(self, program: str, scenario: str) -> str:
        """
        Gera texto descritivo para o LLM sobre o cenário de valoração.

        Exemplo: "resgate esperado via transferência para LATAM Pass ou Azul (R$ 16/mil pts)"
        """
        self._ensure_loaded()
        rate = self.get_rate(program, scenario)
        if rate is None:
            return ""
        partners = self.get_partners(program)
        partner_text = " ou ".join(partners[:2]) if partners else program
        labels = {
            "pessimistic": "resgate pessimista (produtos/cashback)",
            "min": "resgate pessimista (produtos/cashback)",
            "expected": f"resgate esperado via transferência para {partner_text}",
            "optimistic": "resgate otimista (promoção de bônus de transferência)",
            "max": "resgate otimista (promoção de bônus de transferência)",
        }
        label = labels.get(scenario, scenario)
        return f"{label} — {brl(rate, 0)}/mil pontos"


# ── Singleton ────────────────────────────────────────────────────────────────
_valuator: MilesValuator | None = None


def get_valuator() -> MilesValuator:
    """Retorna instância singleton do MilesValuator."""
    global _valuator
    if _valuator is None:
        _valuator = MilesValuator()
    return _valuator
