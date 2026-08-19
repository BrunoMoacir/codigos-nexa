"""
app/architect/connectors/consortium_rate_provider.py

Feature: F3 - Nexa Architect
Version: 1.0.0

Responsabilidade:
    Provider de parâmetros de entrada para calculate_consortium_metrics().
    Combina AbacConnector (grupo + taxas) e IPCAConnector (reajuste) em um
    objeto de parâmetros coeso, seguindo o mesmo padrão de injeção de
    dependência dos demais conectores da F3.

Fontes:
    AbacConnector  → admin_rate, months, group_size, reserve_fund_rate
    IPCAConnector  → annual_adjustment_rate
                     Para IMÓVEL: INCC ≈ IPCA × 1.5 (até ConnectorINCC existir)
                     Para demais: IPCA direto

Integração:
    1. ArchitectService._fetch_market_rates() chama
       ConsortiumRateProvider.get_consortium_rates(asset_type) e faz merge
       no dict de taxas usando o prefixo "consortium_".

    2. StrategyEngine._simulate_consortium() lê as chaves do dict e as repassa
       para calculate_consortium_metrics() do consortium.py v2.

Mapeamento de tipos de bem:
    ABAC (uppercase)  →  consortium.py (lowercase)
    ──────────────────────────────────────────────
    IMOVEL            →  property
    VEICULO           →  vehicle
    REFORMA           →  service
    VIAGEM            →  service
    OUTRO             →  other

Nota sobre INCC:
    O INCC (Índice Nacional de Custo da Construção) não tem API pública JSON.
    Historicamente, INCC ≈ 1,5× IPCA. Usamos:
        adj_rate_imovel = min(INCC_FALLBACK, ipca × INCC_IPCA_FACTOR)
    onde INCC_FALLBACK = 7% e INCC_IPCA_FACTOR = 1.5.
    Quando uma fonte de INCC real estiver disponível, substituir aqui.
"""

import logging
import math
from dataclasses import dataclass, asdict
from typing import Dict, Optional

from app.architect.connectors.abac import AbacConnector
from app.architect.connectors.ipca import IPCAConnector

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Constantes de ajuste
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# INCC histórico médio (2015-2025) — fallback enquanto não há conector real
_INCC_FALLBACK = 0.070       # 7,0% a.a.

# INCC corre ~50% acima do IPCA historicamente
_INCC_IPCA_FACTOR = 1.5

# Tipos de bem cujo reajuste usa INCC (construção civil)
_INCC_ASSET_TYPES = frozenset({"IMOVEL", "property"})

# Contemplados/mês mínimo e máximo para derivação segura
_CONTEMPLATED_MIN = 2
_CONTEMPLATED_MAX = 5


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Mapeamento de tipos (ABAC → consortium.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_ABAC_TO_CALC_ASSET_TYPE: Dict[str, str] = {
    "IMOVEL":  "property",
    "VEICULO": "vehicle",
    "REFORMA": "service",
    "VIAGEM":  "service",
    "OUTRO":   "other",
}


@dataclass
class ConsortiumSimParams:
    """
    Parâmetros completos para uma chamada de calculate_consortium_metrics().

    Produzidos pelo ConsortiumRateProvider a partir de AbacConnector + IPCAConnector.
    Também exportáveis como dict plano para merge no rates dict do ArchitectService.

    Attributes:
        admin_rate:               Taxa de administração total (ex: 0.17)
        months:                   Prazo típico do grupo
        reserve_fund_rate:        Fundo de reserva (ex: 0.02)
        group_size:               Tamanho do grupo
        contemplated_per_month:   Contemplados por assembleia (sorteio + lances)
        annual_adjustment_rate:   Reajuste anual da carta (IPCA ou INCC)
        calc_asset_type:          Tipo no formato do consortium.py (vehicle, property…)
        ipca_annual:              IPCA bruto (para uso externo como referência)
        using_incc_approximation: True se o reajuste foi estimado via INCC≈IPCA×1.5
    """
    admin_rate: float
    months: int
    reserve_fund_rate: float
    group_size: int
    contemplated_per_month: int
    annual_adjustment_rate: float
    calc_asset_type: str
    ipca_annual: float
    using_incc_approximation: bool

    def to_rates_dict(self) -> Dict[str, float]:
        """
        Exporta os campos numéricos no formato flat "consortium_" para merge
        no rates dict do ArchitectService.

        O campo `calc_asset_type` (string) não é incluído — é acessado diretamente
        pelo StrategyEngine via `ConsortiumRateProvider.map_asset_type()`.

        Returns:
            Dict pronto para update(rates_dict).
        """
        return {
            "consortium_admin_rate":             self.admin_rate,
            "consortium_months":                 float(self.months),
            "consortium_reserve_fund_rate":      self.reserve_fund_rate,
            "consortium_group_size":             float(self.group_size),
            "consortium_contemplated_per_month": float(self.contemplated_per_month),
            "consortium_annual_adjustment_rate": self.annual_adjustment_rate,
        }


class ConsortiumRateProvider:
    """
    Provider de parâmetros de consórcio para o calculator Monte Carlo.

    Combina AbacConnector e IPCAConnector para produzir um ConsortiumSimParams
    completo, derivando `contemplated_per_month` e `annual_adjustment_rate`
    de forma automática.

    Não herda de BaseConnector pois não é uma fonte de dados única — agrega
    dois conectores distintos. Segue o mesmo padrão de injeção de dependência.

    Args:
        abac: AbacConnector injetável (para testes e mocks).
        ipca: IPCAConnector injetável (para testes e mocks).

    Example:
        >>> provider = ConsortiumRateProvider()
        >>> params = provider.get_params("VEICULO")
        >>> params.group_size
        200
        >>> params.annual_adjustment_rate  # IPCA real do BCB
        0.0487
        >>> rates_update = params.to_rates_dict()
        >>> market_rates.update(rates_update)

    Integration:
        # ArchitectService._fetch_market_rates():
        params = self._consortium_provider.get_params(asset_type)
        rates.update(params.to_rates_dict())

        # StrategyEngine._simulate_consortium() — via cost_basis, que lê as
        # taxas por rate()/rate_int() e não por .get() com default literal:
        sim = cost_basis.simular_consorcio(req, rates, req.down_payment)
    """

    def __init__(
        self,
        abac: Optional[AbacConnector] = None,
        ipca: Optional[IPCAConnector] = None,
    ) -> None:
        self._abac = abac or AbacConnector()
        self._ipca = ipca or IPCAConnector()

    # ── Interface principal ───────────────────────────────────────────────

    def get_params(self, asset_type: str) -> ConsortiumSimParams:
        """
        Retorna os parâmetros completos para o calculator de consórcio.

        Derivações automáticas:
            contemplated_per_month:   max(2, min(5, round(group_size / months)))
                Garante pelo menos 2 contemplados/mês (1 sorteio + 1 lance) e
                no máximo 5 para grupos com alta densidade de contemplação.

            annual_adjustment_rate:
                - IMÓVEL: min(INCC_FALLBACK=7%, ipca × 1.5)
                  INCC historicamente corre ~50% acima do IPCA.
                - Demais: IPCA direto do BCB via IPCAConnector.

        Args:
            asset_type: Tipo de bem no formato ABAC (IMOVEL, VEICULO, etc.)
                        ou formato consortium.py (property, vehicle, etc.).
                        Case-insensitive. Desconhecidos mapeiam para "OUTRO".

        Returns:
            ConsortiumSimParams com todos os parâmetros prontos para uso.

        Note:
            Se qualquer conector falhar, o BaseConnector de cada um
            retorna fallback automaticamente — este método nunca lança exceção
            de conectividade.

        Example:
            >>> p = ConsortiumRateProvider().get_params("VEICULO")
            >>> p.group_size, p.months, p.admin_rate
            (200, 72, 0.17)
        """
        abac_type = self._normalize_abac_type(asset_type)
        stats = self._abac.get_consortium_stats(abac_type)
        ipca_annual = self._ipca.get_ipca()

        group_size = int(stats["typical_group_size"])
        months = int(stats["typical_months"])

        # Contemplados/mês: derivado do ritmo de esvaziamento do grupo
        # Um grupo de 200 em 72 meses → 2,77 → round → 3/mês
        # Um grupo de 150 em 180 meses → 0,83 → max → 2/mês (piso)
        contemplated = max(
            _CONTEMPLATED_MIN,
            min(_CONTEMPLATED_MAX, round(group_size / months)),
        )

        # Reajuste anual
        is_property = abac_type in _INCC_ASSET_TYPES
        if is_property:
            incc_estimated = min(_INCC_FALLBACK, ipca_annual * _INCC_IPCA_FACTOR)
            annual_adj = incc_estimated
            using_incc = True
            logger.debug(
                "[ConsortiumRateProvider] IMOVEL: INCC≈%.2f%% "
                "(IPCA=%.2f%% × %.1f, cap=%.0f%%)",
                annual_adj * 100,
                ipca_annual * 100,
                _INCC_IPCA_FACTOR,
                _INCC_FALLBACK * 100,
            )
        else:
            annual_adj = ipca_annual
            using_incc = False
            logger.debug(
                "[ConsortiumRateProvider] %s: reajuste=IPCA=%.2f%%",
                abac_type,
                ipca_annual * 100,
            )

        return ConsortiumSimParams(
            admin_rate=stats["admin_rate"],
            months=months,
            reserve_fund_rate=stats["reserve_fund_rate"],
            group_size=group_size,
            contemplated_per_month=contemplated,
            annual_adjustment_rate=annual_adj,
            calc_asset_type=self.map_asset_type(abac_type),
            ipca_annual=ipca_annual,
            using_incc_approximation=using_incc,
        )

    def get_fallback_params(self, asset_type: str) -> ConsortiumSimParams:
        """
        Retorna parâmetros de fallback hardcoded sem chamar conectores.

        Usado quando get_params() falha inesperadamente e o caller precisa
        de um fallback de último recurso além dos já embutidos nos conectores.

        Args:
            asset_type: Tipo de bem (ABAC ou calculator format).

        Returns:
            ConsortiumSimParams com valores conservadores de referência (fev/2026).
        """
        abac_type = self._normalize_abac_type(asset_type)
        # Reutiliza fallback do AbacConnector (já testado e mantido)
        fb_rates = self._abac.get_fallback_rates()
        prefix = f"consortium_{abac_type}_"
        if f"{prefix}admin_rate" not in fb_rates:
            prefix = "consortium_VEICULO_"

        group_size = int(fb_rates[f"{prefix}group_size"])
        months = int(fb_rates[f"{prefix}months"])
        contemplated = max(_CONTEMPLATED_MIN, min(_CONTEMPLATED_MAX, round(group_size / months)))
        is_property = abac_type in _INCC_ASSET_TYPES

        return ConsortiumSimParams(
            admin_rate=fb_rates[f"{prefix}admin_rate"],
            months=months,
            reserve_fund_rate=fb_rates[f"{prefix}reserve_fund_rate"],
            group_size=group_size,
            contemplated_per_month=contemplated,
            annual_adjustment_rate=_INCC_FALLBACK if is_property else 0.045,
            calc_asset_type=self.map_asset_type(abac_type),
            ipca_annual=0.045,
            using_incc_approximation=is_property,
        )

    # ── Utilitários estáticos ────────────────────────────────────────────

    @staticmethod
    def map_asset_type(asset_type: str) -> str:
        """
        Mapeia tipo de bem do formato ABAC para o formato consortium.py.

        Args:
            asset_type: Tipo de bem no formato ABAC uppercase.
                        Ex: "IMOVEL", "VEICULO", "REFORMA", "VIAGEM", "OUTRO".
                        Case-insensitive. Desconhecidos retornam "other".

        Returns:
            Tipo no formato consortium.py: "property", "vehicle", "service", "other".

        Note:
            Este método espera o formato ABAC (ex: "VEICULO"), não o formato
            do calculator (ex: "vehicle"). Em StrategyEngine, use com
            req.asset_type.value que já é o formato ABAC.

        Example:
            >>> ConsortiumRateProvider.map_asset_type("IMOVEL")
            'property'
            >>> ConsortiumRateProvider.map_asset_type("VEICULO")
            'vehicle'
            >>> ConsortiumRateProvider.map_asset_type("UNKNOWN")
            'other'
        """
        normalized = asset_type.upper()
        return _ABAC_TO_CALC_ASSET_TYPE.get(normalized, "other")

    # ── Helpers privados ─────────────────────────────────────────────────

    @staticmethod
    def _normalize_abac_type(asset_type: str) -> str:
        """
        Normaliza asset_type para o formato ABAC uppercase.

        Aceita tanto formato ABAC ("VEICULO") quanto calculator ("vehicle").
        Tipos desconhecidos mapeiam para "OUTRO".
        """
        upper = asset_type.upper()
        if upper in _ABAC_TO_CALC_ASSET_TYPE:
            return upper
        # Talvez seja o formato calculator — tentar mapeamento reverso
        _REVERSE = {v.upper(): k for k, v in _ABAC_TO_CALC_ASSET_TYPE.items()}
        return _REVERSE.get(upper, "OUTRO")


__all__ = ["ConsortiumRateProvider", "ConsortiumSimParams"]
