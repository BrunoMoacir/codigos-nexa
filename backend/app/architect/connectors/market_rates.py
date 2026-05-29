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

import httpx

from app.architect.connectors.base import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)

# Caminho para o JSON local usado como fallback secundário
_DATA_FILE = Path(__file__).resolve().parents[3] / "data" / "architect" / "market_rates.json"

# API pública do Banco Central do Brasil (SGS — Sistema Gerenciador de Séries)
# Endpoint: GET /dados/serie/bcdata.sgs.{serie}/dados/ultimos/1?formato=json
# Retorna: [{"data": "dd/mm/aaaa", "valor": "12.34"}]  (taxa em % a.a.)
_BCB_BASE = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados/ultimos/1"

# Mapeamento: série BCB → tipo de bem
# Fontes:
#   25497 — SFH (financiamento habitacional taxas de mercado, % a.a.)
#   25501 — Veículos com recursos livres, % a.a.
#   20722 — Crédito pessoal não consignado, % a.a. (base para REFORMA/VIAGEM/OUTRO)
_BCB_SERIES: Dict[str, int] = {
    "IMOVEL":  25497,
    "VEICULO": 25501,
    "REFORMA": 20722,
    "VIAGEM":  20722,
    "OUTRO":   20722,
}

# Spreads aplicados sobre a média BCB para derivar cenários min/max.
# min = média * (1 - SPREAD_MIN)  → perfil prime, melhor banco
# max = média * (1 + SPREAD_MAX)  → perfil padrão, banco de varejo
_SPREAD_MIN: Dict[str, float] = {
    "IMOVEL":  0.03,
    "VEICULO": 0.10,
    "REFORMA": 0.15,
    "VIAGEM":  0.15,
    "OUTRO":   0.12,
}
_SPREAD_MAX: Dict[str, float] = {
    "IMOVEL":  0.07,
    "VEICULO": 0.25,
    "REFORMA": 0.45,
    "VIAGEM":  0.45,
    "OUTRO":   0.40,
}


class MarketRatesConnector(BaseConnector):
    """
    Conector de CETs (Custo Efetivo Total) por tipo de bem.

    Busca taxas médias de mercado na API pública do BCB (SGS) e deriva
    cenários min/avg/max com spreads calibrados por tipo de ativo.
    Fallback automático para valores hardcoded quando a API falha.

    Taxas retornadas:
        cet_{ASSET_TYPE}_min  — melhor CET esperado (perfil prime)
        cet_{ASSET_TYPE}_avg  — CET médio de mercado (dado BCB)
        cet_{ASSET_TYPE}_max  — pior CET esperado (varejo padrão)

    Args:
        cache_ttl_seconds:          TTL do cache após fetch bem-sucedido.
                                    Padrão: 86400 (24h) — CETs variam pouco.
        timeout_seconds:            Timeout HTTP por série BCB. Padrão: 5s.
        fallback_cache_ttl_seconds: TTL do cache quando fetch falha.
                                    Padrão: 300 (5 min).

    Example:
        >>> connector = MarketRatesConnector()
        >>> cet = connector.get_best_cet("VEICULO")
        >>> print(f"Melhor CET veículo: {cet:.2%}")
    """

    _VALID_ASSET_TYPES = {"IMOVEL", "VEICULO", "REFORMA", "VIAGEM", "OUTRO"}

    def __init__(
        self,
        cache_ttl_seconds: int = 86400,
        timeout_seconds: int = 5,
        fallback_cache_ttl_seconds: int = 300,
    ) -> None:
        super().__init__(
            cache_ttl_seconds=cache_ttl_seconds,
            timeout_seconds=timeout_seconds,
            fallback_cache_ttl_seconds=fallback_cache_ttl_seconds,
        )

    # ── Interface obrigatória ─────────────────────────────────────────────

    def fetch_rates(self) -> Dict[str, float]:
        """
        Busca taxas médias na API pública do BCB (SGS) e deriva min/avg/max.

        Faz uma request por série única necessária (deduplicadas por asset_type).
        Se qualquer série falhar, levanta ConnectorError e o BaseConnector
        usa get_fallback_rates() automaticamente.

        Returns:
            Dict no formato {"cet_IMOVEL_min": 0.143, "cet_IMOVEL_avg": 0.148, ...}

        Raises:
            ConnectorError: Se qualquer série não responder ou retornar dado inválido.
        """
        # Busca apenas séries únicas (REFORMA/VIAGEM/OUTRO compartilham 20722)
        unique_series = {serie: asset for asset, serie in _BCB_SERIES.items()}
        avg_by_serie: Dict[int, float] = {}

        for serie_id in unique_series:
            url = _BCB_BASE.format(serie=serie_id)
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.get(url, params={"formato": "json"})
                resp.raise_for_status()
                data = resp.json()
                if not data or "valor" not in data[0]:
                    raise ConnectorError(f"BCB série {serie_id}: resposta inesperada {data}")
                # Séries BCB 25497/25501/20722 retornam % a.m. (ex: "1.12" = 1.12%/mês).
                # Valores < 5% são mensais — converter para taxa anual equivalente.
                rate = float(data[0]["valor"]) / 100.0
                if rate < 0.05:
                    rate = (1 + rate) ** 12 - 1
                avg_by_serie[serie_id] = rate
                logger.debug("BCB série %d: %.4f a.a.", serie_id, avg_by_serie[serie_id])
            except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
                raise ConnectorError(
                    f"Falha ao buscar BCB série {serie_id}: {exc}"
                ) from exc

        rates: Dict[str, float] = {}
        for asset_type in self._VALID_ASSET_TYPES:
            serie_id = _BCB_SERIES[asset_type]
            avg = avg_by_serie[serie_id]
            spread_min = _SPREAD_MIN[asset_type]
            spread_max = _SPREAD_MAX[asset_type]
            rates[f"cet_{asset_type}_avg"] = round(avg, 4)
            rates[f"cet_{asset_type}_min"] = round(avg * (1 - spread_min), 4)
            rates[f"cet_{asset_type}_max"] = round(avg * (1 + spread_max), 4)

        # Validar invariante: CET imóvel (garantia real) < CET veículo (bem depreciativo).
        # Se violado, a série BCB retornou produto subsidiado atípico — usar fonte secundária.
        if rates.get("cet_IMOVEL_min", 0) >= rates.get("cet_VEICULO_min", 1):
            raise ConnectorError(
                f"Invariante econômica violada: CET imóvel ({rates['cet_IMOVEL_min']:.4f}) "
                f">= CET veículo ({rates['cet_VEICULO_min']:.4f}). Série BCB inconsistente."
            )

        logger.info(
            "MarketRatesConnector: taxas atualizadas via BCB — IMOVEL avg=%.2f%% VEICULO avg=%.2f%%",
            rates["cet_IMOVEL_avg"] * 100,
            rates["cet_VEICULO_avg"] * 100,
        )
        return rates

    def fetch_rates_secondary(self) -> Dict[str, float]:
        """
        Fonte secundária: deriva CETs a partir da SELIC atual + spreads calibrados.

        Quando o BCB SGS falha, usa a SELIC do BacenConnector (que tem sua própria
        cadeia de fallback) como âncora, aplicando spreads históricos por tipo de ativo.
        Isso produz valores dinâmicos mesmo offline, ao invés dos hardcoded.

        Spreads sobre SELIC (médias históricas 2022-2026):
            IMOVEL:  SELIC + 2-4 p.p. (SFH/SFI)
            VEICULO: SELIC + 5-15 p.p. (CDC)
            REFORMA: SELIC + 10-30 p.p. (crédito pessoal)
            VIAGEM:  SELIC + 15-37 p.p. (crédito pessoal)
            OUTRO:   SELIC + 10-33 p.p. (crédito pessoal)
        """
        from app.architect.connectors.bacen import BacenConnector
        selic = BacenConnector(
            cache_ttl_seconds=self.cache_ttl,
            timeout_seconds=self.timeout,
            fallback_cache_ttl_seconds=self.fallback_cache_ttl,
        ).get_selic()

        # spreads adicionados à SELIC: (min_add, avg_add, max_add) em p.p.
        spreads = {
            "IMOVEL":  (0.020, 0.030, 0.045),
            "VEICULO": (0.050, 0.080, 0.145),
            "REFORMA": (0.100, 0.190, 0.310),
            "VIAGEM":  (0.150, 0.225, 0.380),
            "OUTRO":   (0.100, 0.200, 0.330),
        }

        rates: Dict[str, float] = {}
        for asset_type, (sp_min, sp_avg, sp_max) in spreads.items():
            rates[f"cet_{asset_type}_min"] = round(selic + sp_min, 4)
            rates[f"cet_{asset_type}_avg"] = round(selic + sp_avg, 4)
            rates[f"cet_{asset_type}_max"] = round(selic + sp_max, 4)

        logger.info(
            "[MarketRatesConnector] CETs derivados da SELIC %.2f%% — IMOVEL avg=%.2f%% VEICULO avg=%.2f%%",
            selic * 100,
            rates["cet_IMOVEL_avg"] * 100,
            rates["cet_VEICULO_avg"] * 100,
        )
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
            # Imóvel — SFH/SFI (CAIXA, BB, Itaú, Bradesco) — SELIC 14.75% + spread mínimo 15bps
            "cet_IMOVEL_min": 0.1490,
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
