"""
app/optimizer/miles_valuator.py
M2.3 — Motor de Valoração de Milhas em Tempo Real

Carrega data/cards/miles_valuation.json e fornece taxas de conversão
dinâmicas por programa de fidelidade e cenário de resgate.

Cenários:
    pessimistic  → resgate em produtos / cashback (menor valor)
    expected     → transferência para companhia aérea parceira (valor médio)
    optimistic   → promoção de transferência com bônus (maior valor)

Uso:
    valuator = get_valuator()
    rate = valuator.get_rate("livelo", "expected")  # R$ 16.0 / 1.000 pts
    value = valuator.compute_points_value(2.0, 3600.0, "livelo", "expected")  # R$ 115.20
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_VALUATION_FILE = (
    Path(__file__).parent.parent.parent / "data" / "cards" / "miles_valuation.json"
)

# Mapeia os nomes de cenário usados no simulador para as chaves do JSON
_SCENARIO_KEY: dict[str, str] = {
    "min": "pessimistic_per_1000",
    "pessimistic": "pessimistic_per_1000",
    "expected": "expected_per_1000",
    "max": "optimistic_per_1000",
    "optimistic": "optimistic_per_1000",
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

        Args:
            program: chave do programa (ex: "livelo", "smiles", "atomos")
            scenario: "pessimistic" | "expected" | "optimistic" (aceita também "min"/"max")

        Returns:
            Taxa em R$/1.000 pts, ou None se programa não encontrado.
        """
        self._ensure_loaded()
        prog = self._table.get(program.lower())
        if not prog:
            return None
        key = _SCENARIO_KEY.get(scenario, "expected_per_1000")
        value = prog.get(key)
        return float(value) if value is not None else None

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
        return f"{label} — R$ {rate:.0f}/mil pontos"


# ── Singleton ────────────────────────────────────────────────────────────────
_valuator: MilesValuator | None = None


def get_valuator() -> MilesValuator:
    """Retorna instância singleton do MilesValuator."""
    global _valuator
    if _valuator is None:
        _valuator = MilesValuator()
    return _valuator
