"""
app/architect/connectors/market_rates.py - CETs de mercado por tipo de bem

Feature: F3 - Nexa Architect
Version: 1.0.0

Dados fornecidos (Fase 1):
    cet_{ASSET_TYPE}_min (float): CET mínimo encontrado no mercado
    cet_{ASSET_TYPE}_avg (float): CET médio de mercado
    cet_{ASSET_TYPE}_max (float): CET máximo de mercado
    Ex: cet_VEICULO_min, cet_IMOVEL_avg, ...

Fonte (Fase 1 — MVP):
    Arquivo JSON local: data/architect/market_rates.json
    Dados mock baseados em médias de mercado (fev/2026).
    Sem chamada HTTP — leitura em disco com cache em memória.

Fonte (Fase 2 — TODO):
    APIs públicas de simulação dos bancos:
    - Itaú:    https://www.itau.com.br/emprestimos-financiamentos/
    - Bradesco: https://banco.bradesco/html/classic/produtos-servicos/
    - CAIXA:   https://www.caixa.gov.br/
    - BCB Open Finance: https://openfinance.bcb.gov.br/

Tipos de bem suportados (AssetType):
    IMOVEL, VEICULO, REFORMA, VIAGEM, OUTRO
"""

import json
import logging
from pathlib import Path
from typing import Dict

from app.architect.connectors.base import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)

# Caminho absoluto para o arquivo de dados
_DATA_FILE = Path(__file__).resolve().parents[3] / "data" / "architect" / "market_rates.json"


class MarketRatesConnector(BaseConnector):
    """
    Conector de CETs (Custo Efetivo Total) por tipo de bem.

    Fase 1: lê dados de um arquivo JSON local com mock de mercado.
    Fase 2 (TODO): busca CETs reais via APIs de simulação dos bancos.

    Taxas retornadas (uma entrada por asset_type × cenário):
        cet_{ASSET_TYPE}_min (float): Melhor CET disponível no mercado
        cet_{ASSET_TYPE}_avg (float): CET médio de mercado
        cet_{ASSET_TYPE}_max (float): Pior CET do mercado

    O method `get_best_cet(asset_type)` é o principal ponto de entrada
    para os calculators — retorna o `cet_min` do tipo solicitado.

    Args:
        cache_ttl_seconds:          TTL do cache. Padrão: 86400 (24h).
                                    CETs de mercado variam pouco no dia a dia.
        timeout_seconds:            Não usado em Fase 1 (sem HTTP). Reservado
                                    para Fase 2.
        fallback_cache_ttl_seconds: TTL do cache quando fetch falha.
                                    Padrão: 300 (5 min).
        data_file:                  Caminho para o JSON. Padrão: detectado
                                    automaticamente via __file__.

    Example:
        >>> connector = MarketRatesConnector()
        >>> cet = connector.get_best_cet("VEICULO")
        >>> print(f"Melhor CET veículo: {cet:.2%}")
        Melhor CET veículo: 16.20%
    """

    # Assets suportados — espelha AssetType de models.py (sem importar o enum
    # para evitar dependência circular entre connector e models).
    _VALID_ASSET_TYPES = {"IMOVEL", "VEICULO", "REFORMA", "VIAGEM", "OUTRO"}

    def __init__(
        self,
        cache_ttl_seconds: int = 86400,
        timeout_seconds: int = 5,
        fallback_cache_ttl_seconds: int = 300,
        data_file: Path = _DATA_FILE,
    ) -> None:
        super().__init__(
            cache_ttl_seconds=cache_ttl_seconds,
            timeout_seconds=timeout_seconds,
            fallback_cache_ttl_seconds=fallback_cache_ttl_seconds,
        )
        self._data_file = data_file

    # ── Interface obrigatória ─────────────────────────────────────────────

    def fetch_rates(self) -> Dict[str, float]:
        """
        Lê CETs do arquivo JSON local e retorna como dict plano.

        Returns:
            Dict com entradas no formato "cet_{ASSET_TYPE}_{cenario}":
            {
                "cet_IMOVEL_min": 0.1475,
                "cet_IMOVEL_avg": 0.1525,
                "cet_IMOVEL_max": 0.1625,
                "cet_VEICULO_min": 0.1620,
                ...
            }

        Raises:
            ConnectorError: Se o arquivo não existir, for JSON inválido
                            ou não tiver a chave "rates".
        """
        if not self._data_file.exists():
            raise ConnectorError(
                f"Arquivo de taxas de mercado não encontrado: {self._data_file}"
            )

        try:
            raw = json.loads(self._data_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConnectorError(
                f"JSON inválido em {self._data_file}: {exc}"
            ) from exc

        if "rates" not in raw or not isinstance(raw["rates"], dict):
            raise ConnectorError(
                f"Estrutura inesperada no arquivo {self._data_file}: chave 'rates' ausente."
            )

        rates: Dict[str, float] = {}
        for asset_type, data in raw["rates"].items():
            for scenario in ("min", "avg", "max"):
                key = f"cet_{asset_type}_{scenario}"
                value = data.get(f"cet_{scenario}")
                if value is None:
                    raise ConnectorError(
                        f"Campo ausente no JSON: rates.{asset_type}.cet_{scenario}"
                    )
                rates[key] = float(value)

        return rates

    def get_fallback_rates(self) -> Dict[str, float]:
        """
        Retorna CETs hardcoded como fallback quando o arquivo JSON falha.

        Referência: médias de mercado em fev/2026.
        Atualizar trimestralmente ou sempre que o arquivo JSON for atualizado.

        Returns:
            Dict plano com cet_{ASSET_TYPE}_{min|avg|max}
        """
        return {
            # Imóvel — SFH/SFI (CAIXA, BB, Itaú, Bradesco) — SELIC 13.25% + spread 150-300bps
            "cet_IMOVEL_min": 0.1475,
            "cet_IMOVEL_avg": 0.1525,
            "cet_IMOVEL_max": 0.1625,
            # Veículo — CDC, consórcio, leasing
            "cet_VEICULO_min": 0.1620,
            "cet_VEICULO_avg": 0.1950,
            "cet_VEICULO_max": 0.2450,
            # Reforma — crédito pessoal e CDC
            "cet_REFORMA_min": 0.2200,
            "cet_REFORMA_avg": 0.3100,
            "cet_REFORMA_max": 0.4500,
            # Viagem — cartão parcelado e crédito pessoal
            "cet_VIAGEM_min": 0.2800,
            "cet_VIAGEM_avg": 0.3600,
            "cet_VIAGEM_max": 0.5200,
            # Outro — crédito pessoal geral
            "cet_OUTRO_min": 0.2400,
            "cet_OUTRO_avg": 0.3200,
            "cet_OUTRO_max": 0.4800,
        }

    # ── Convenience methods ───────────────────────────────────────────────

    def get_best_cet(self, asset_type: str) -> float:
        """
        Retorna o melhor CET disponível (mínimo de mercado) para o tipo de bem.

        Principal ponto de entrada para os calculators de financiamento.

        Args:
            asset_type: Tipo de bem. Um de: IMOVEL, VEICULO, REFORMA, VIAGEM, OUTRO.
                        Case-insensitive.

        Returns:
            CET mínimo anual em decimal (ex: 0.1620 para 16.20% a.a.)

        Raises:
            ValueError: Se asset_type não for um dos valores suportados.

        Example:
            >>> connector = MarketRatesConnector()
            >>> cet = connector.get_best_cet("VEICULO")  # 0.1620
            >>> cet = connector.get_best_cet("IMOVEL")   # 0.1475
        """
        asset_upper = asset_type.upper()
        if asset_upper not in self._VALID_ASSET_TYPES:
            raise ValueError(
                f"asset_type inválido: '{asset_type}'. "
                f"Valores aceitos: {sorted(self._VALID_ASSET_TYPES)}"
            )
        return self.get_rates()[f"cet_{asset_upper}_min"]

    def get_avg_cet(self, asset_type: str) -> float:
        """
        Retorna o CET médio de mercado para o tipo de bem.

        Usado para cenários conservadores onde o usuário não necessariamente
        consegue as melhores condições.

        Args:
            asset_type: Tipo de bem (case-insensitive).

        Returns:
            CET médio anual em decimal (ex: 0.1950 para 19.50% a.a.)
        """
        asset_upper = asset_type.upper()
        if asset_upper not in self._VALID_ASSET_TYPES:
            raise ValueError(
                f"asset_type inválido: '{asset_type}'. "
                f"Valores aceitos: {sorted(self._VALID_ASSET_TYPES)}"
            )
        return self.get_rates()[f"cet_{asset_upper}_avg"]


__all__ = ["MarketRatesConnector"]
