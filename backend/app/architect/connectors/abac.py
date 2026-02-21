"""
app/architect/connectors/abac.py - Conector ABAC (Estatísticas de Consórcio)

Feature: F3 - Nexa Architect
Version: 2.0.0 (Fase 2)

Dados fornecidos:
    Estatísticas operacionais de grupos de consórcio por tipo de bem:
      - admin_rate:         Taxa de administração total (decimal, sobre a carta)
      - typical_months:     Prazo típico do grupo (meses)
      - typical_group_size: Tamanho médio do grupo (participantes)
      - reserve_fund_rate:  Fundo de reserva total (decimal)

Fonte:
    ABAC — Associação Brasileira de Administradoras de Consórcios.
    Publica relatórios mensais em PDF (abac.org.br).
    Não há API pública JSON, então este conector usa fallback hardcoded
    baseado nos boletins ABAC de fev/2026. Quando o fetch falha,
    o BaseConnector retorna get_fallback_rates() automaticamente.

Integração:
    AbacConnector é instanciado no ArchitectService. As estatísticas são
    injetadas em market_rates e usadas pelo StrategyEngine em
    _simulate_consortium(), substituindo valores hardcoded.

Uso:
    connector = AbacConnector()
    stats = connector.get_consortium_stats("VEICULO")
    # {"admin_rate": 0.17, "typical_months": 72, "typical_group_size": 200, ...}

    rate = connector.get_admin_rate("IMOVEL")  # 0.19
"""

import logging
from typing import Dict

import httpx

from app.architect.connectors.base import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)


class AbacConnector(BaseConnector):
    """
    Conector de estatísticas de consórcio baseado em dados da ABAC.

    Fornece taxas de administração e parâmetros operacionais de grupos de
    consórcio por tipo de bem, usados em `_simulate_consortium` do StrategyEngine.

    Taxas de fallback (boletim ABAC fev/2026):
        IMOVEL:  admin=19%, prazo=180 meses (15 anos), grupo=150 cotas
        VEICULO: admin=17%, prazo=72  meses (6 anos),  grupo=200 cotas
        REFORMA: admin=18%, prazo=60  meses (5 anos),  grupo=100 cotas
        VIAGEM:  admin=18%, prazo=48  meses (4 anos),  grupo=80  cotas
        OUTRO:   admin=18%, prazo=60  meses (5 anos),  grupo=100 cotas

    Obs: admin_rate é o custo total sobre o prazo do grupo (não a.a.).
    Ex: 17% em 72 meses ≈ 2.83% a.a. de taxa administrativa.

    Args:
        cache_ttl_seconds:          TTL após fetch bem-sucedido. Padrão: 86400 (24h).
                                    Dados ABAC são publicados mensalmente.
        timeout_seconds:            Timeout HTTP. Padrão: 8s.
        fallback_cache_ttl_seconds: TTL do fallback. Padrão: 3600 (1h).

    Example:
        >>> connector = AbacConnector()
        >>> stats = connector.get_consortium_stats("VEICULO")
        >>> stats["admin_rate"]      # 0.17
        >>> stats["typical_months"]  # 72
    """

    _ABAC_BASE_URL = "https://api.abac.org.br/v1/stats/consortium"
    _DEFAULT_CACHE_TTL = 86_400  # 24 horas — dados mudam mensalmente

    def __init__(
        self,
        cache_ttl_seconds: int = _DEFAULT_CACHE_TTL,
        timeout_seconds: float = 8.0,
        fallback_cache_ttl_seconds: int = 3_600,
    ) -> None:
        super().__init__(
            cache_ttl_seconds=cache_ttl_seconds,
            timeout_seconds=timeout_seconds,
            fallback_cache_ttl_seconds=fallback_cache_ttl_seconds,
        )

    # ── Interface obrigatória ─────────────────────────────────────────────

    def fetch_rates(self) -> Dict[str, float]:
        """
        Tenta buscar estatísticas de consórcio da ABAC.

        A ABAC não possui API pública JSON; este método tentará o endpoint
        e falhará graciosamente — BaseConnector então usa get_fallback_rates().

        Raises:
            ConnectorError: Se a resposta for inesperada ou o endpoint falhar.
            httpx.HTTPError: Se o request HTTP falhar.
        """
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(self._ABAC_BASE_URL)
                response.raise_for_status()
            data = response.json()
            return self._parse_abac_response(data)
        except Exception as exc:
            raise ConnectorError(
                f"ABAC API indisponível ({exc}) — usando dados de referência fev/2026"
            ) from exc

    def get_fallback_rates(self) -> Dict[str, float]:
        """
        Estatísticas de consórcio hardcoded (boletim ABAC fev/2026).

        Formato das chaves: "consortium_{ASSET_TYPE}_{campo}"
        Campos: admin_rate, months, group_size, reserve_fund_rate.

        Returns:
            Dict plano com todas as estatísticas por tipo de bem.
        """
        return {
            # ── IMÓVEL ─────────────────────────────────────────────────
            # Prazo: 120–200 meses; admin: 17–22%; grupo: 50–200 cotas
            "consortium_IMOVEL_admin_rate":        0.19,
            "consortium_IMOVEL_months":            180.0,
            "consortium_IMOVEL_group_size":        150.0,
            "consortium_IMOVEL_reserve_fund_rate": 0.02,

            # ── VEÍCULO ────────────────────────────────────────────────
            # Prazo: 48–84 meses; admin: 15–18%; grupo: 100–300 cotas
            "consortium_VEICULO_admin_rate":        0.17,
            "consortium_VEICULO_months":            72.0,
            "consortium_VEICULO_group_size":        200.0,
            "consortium_VEICULO_reserve_fund_rate": 0.02,

            # ── REFORMA ────────────────────────────────────────────────
            # Prazo: 36–60 meses; admin: 16–20%; grupo: 50–150 cotas
            "consortium_REFORMA_admin_rate":        0.18,
            "consortium_REFORMA_months":            60.0,
            "consortium_REFORMA_group_size":        100.0,
            "consortium_REFORMA_reserve_fund_rate": 0.02,

            # ── VIAGEM ─────────────────────────────────────────────────
            # Prazo: 24–48 meses; admin: 16–20%; grupo: 50–100 cotas
            "consortium_VIAGEM_admin_rate":        0.18,
            "consortium_VIAGEM_months":            48.0,
            "consortium_VIAGEM_group_size":        80.0,
            "consortium_VIAGEM_reserve_fund_rate": 0.02,

            # ── OUTRO ──────────────────────────────────────────────────
            "consortium_OUTRO_admin_rate":        0.18,
            "consortium_OUTRO_months":            60.0,
            "consortium_OUTRO_group_size":        100.0,
            "consortium_OUTRO_reserve_fund_rate": 0.02,
        }

    # ── Convenience methods ───────────────────────────────────────────────

    def get_admin_rate(self, asset_type: str) -> float:
        """
        Retorna a taxa de administração total para o tipo de bem.

        Args:
            asset_type: "IMOVEL", "VEICULO", "REFORMA", "VIAGEM" ou "OUTRO".

        Returns:
            Taxa de administração em decimal (ex: 0.17 para 17%).
            Fallback para VEICULO (0.17) se asset_type desconhecido.

        Example:
            >>> connector.get_admin_rate("IMOVEL")
            0.19
        """
        rates = self.get_rates()
        key = f"consortium_{asset_type.upper()}_admin_rate"
        return rates.get(key, rates["consortium_VEICULO_admin_rate"])

    def get_consortium_stats(self, asset_type: str) -> Dict:
        """
        Retorna todas as estatísticas de consórcio para um tipo de bem.

        Args:
            asset_type: "IMOVEL", "VEICULO", "REFORMA", "VIAGEM" ou "OUTRO".

        Returns:
            Dict com:
                admin_rate (float):         Taxa de administração total (decimal)
                typical_months (int):       Prazo típico do grupo
                typical_group_size (int):   Tamanho médio do grupo
                reserve_fund_rate (float):  Fundo de reserva (decimal)

        Example:
            >>> stats = connector.get_consortium_stats("VEICULO")
            >>> stats["admin_rate"]       # 0.17
            >>> stats["typical_months"]   # 72
        """
        rates = self.get_rates()
        prefix = f"consortium_{asset_type.upper()}_"

        # Fallback para VEICULO se asset_type não reconhecido
        if f"{prefix}admin_rate" not in rates:
            logger.warning(
                "AbacConnector: asset_type '%s' desconhecido — usando VEICULO como fallback",
                asset_type,
            )
            prefix = "consortium_VEICULO_"

        return {
            "admin_rate":         rates[f"{prefix}admin_rate"],
            "typical_months":     int(rates[f"{prefix}months"]),
            "typical_group_size": int(rates[f"{prefix}group_size"]),
            "reserve_fund_rate":  rates[f"{prefix}reserve_fund_rate"],
        }

    # ── Helper de parse ───────────────────────────────────────────────────

    @staticmethod
    def _parse_abac_response(data: dict) -> Dict[str, float]:
        """
        Parseia resposta JSON da API ABAC (caso seja implementada no futuro).

        Estrutura JSON esperada:
            {
                "VEICULO": {"admin_rate": 17.0, "months": 72, "group_size": 200, ...},
                "IMOVEL":  {"admin_rate": 19.0, ...},
                ...
            }
        admin_rate e reserve_fund_rate em percentual (17.0 = 17%).

        Raises:
            ConnectorError: Se o formato for inesperado.
        """
        if not isinstance(data, dict):
            raise ConnectorError(f"ABAC: resposta inesperada (não é dict): {data!r}")

        result = {}
        for asset_type, stats in data.items():
            if not isinstance(stats, dict):
                continue
            prefix = f"consortium_{asset_type.upper()}_"
            try:
                result[f"{prefix}admin_rate"]        = float(stats["admin_rate"]) / 100
                result[f"{prefix}months"]            = float(stats.get("months", 60))
                result[f"{prefix}group_size"]        = float(stats.get("group_size", 100))
                result[f"{prefix}reserve_fund_rate"] = float(stats.get("reserve_fund_rate", 2.0)) / 100
            except (KeyError, ValueError, TypeError) as exc:
                raise ConnectorError(
                    f"ABAC: erro ao parsear '{asset_type}': {exc}"
                ) from exc

        if not result:
            raise ConnectorError("ABAC: resposta vazia ou sem dados utilizáveis.")

        return result


__all__ = ["AbacConnector"]
