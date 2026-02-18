"""
app/architect/connectors/bacen.py - Conector BACEN (Banco Central do Brasil)

Feature: F3 - Nexa Architect
Version: 1.0.0

Dados fornecidos (Fase 1):
    selic_annual (float): Taxa SELIC meta anual em decimal
                          Ex: 13.25% a.a. → 0.1325

API:
    Sistema SGS - Gerenciador de Séries Temporais do BCB
    URL: https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series}/dados/ultimos/1?formato=json
    Série 432: Taxa SELIC meta - valor nominal anual em %
    Pública, sem autenticação.

Fase 2 (TODO):
    PTAX (câmbio USD/BRL) via ODATA:
    https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/...
"""

import logging
from typing import Dict

import httpx

from app.architect.connectors.base import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)


class BacenConnector(BaseConnector):
    """
    Conector para a API SGS do Banco Central do Brasil.

    Busca a Taxa SELIC meta (série 432), usada como taxa de desconto
    nas simulações de NPV e como referência de custo de oportunidade.

    A SELIC só muda nas reuniões do COPOM (~a cada 45 dias), então
    o cache de 1 hora padrão é mais que suficiente para o MVP.

    Taxas retornadas:
        selic_annual (float): Taxa SELIC meta anual em decimal
                              Ex: 0.1325 para 13.25% a.a.

    Args:
        cache_ttl_seconds:          TTL do cache após fetch bem-sucedido.
                                    Padrão: 3600 (1 hora).
        timeout_seconds:            Timeout do request HTTP. Padrão: 5s.
        fallback_cache_ttl_seconds: TTL do cache quando a API falha.
                                    Padrão: 60s (retry em 1 minuto).

    Example:
        >>> connector = BacenConnector()
        >>> selic = connector.get_selic()
        >>> print(f"SELIC: {selic:.2%}")
        SELIC: 13.25%
        >>> monthly_rate = (1 + selic) ** (1/12) - 1
    """

    _SGS_BASE_URL = (
        "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series}"
        "/dados/ultimos/1?formato=json"
    )
    _SELIC_META_SERIES = 432  # Taxa SELIC meta — % nominal anual

    # ── Interface obrigatória ─────────────────────────────────────────────

    def fetch_rates(self) -> Dict[str, float]:
        """
        Busca a Taxa SELIC meta mais recente na API SGS do BACEN.

        Usa self.timeout para o request HTTP.

        Returns:
            {"selic_annual": float}
            Ex: {"selic_annual": 0.1325}

        Raises:
            ConnectorError: Se a resposta estiver vazia ou mal-formada.
            httpx.HTTPError: Se o request HTTP falhar (capturado por get_rates()).
        """
        url = self._SGS_BASE_URL.format(series=self._SELIC_META_SERIES)

        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url)
            response.raise_for_status()

        data = response.json()

        if not data or not isinstance(data, list) or "valor" not in data[0]:
            raise ConnectorError(
                f"Resposta inesperada da API BACEN "
                f"(série {self._SELIC_META_SERIES}): {data}"
            )

        selic_pct = float(data[0]["valor"])   # ex: 13.25 (percentual)
        selic_annual = selic_pct / 100        # ex: 0.1325 (decimal)

        return {"selic_annual": selic_annual}

    def get_fallback_rates(self) -> Dict[str, float]:
        """
        Retorna SELIC hardcoded como fallback quando a API do BACEN falha.

        Referência: SELIC meta em fev/2026 = 13.25% a.a.
        Atualizar após cada reunião do COPOM ou, no mínimo, trimestralmente.

        Returns:
            {"selic_annual": 0.1325}
        """
        return {"selic_annual": 0.1325}

    # ── Convenience methods ───────────────────────────────────────────────

    def get_selic(self) -> float:
        """
        Retorna a Taxa SELIC meta anual em decimal.

        Shorthand para get_rates()["selic_annual"].
        Aplica cache e fallback automaticamente via BaseConnector.

        Returns:
            Taxa SELIC anual em decimal (ex: 0.1325 para 13.25% a.a.)

        Example:
            >>> connector = BacenConnector()
            >>> selic = connector.get_selic()          # 0.1325
            >>> monthly = (1 + selic) ** (1/12) - 1   # 0.01044...
        """
        return self.get_rates()["selic_annual"]


__all__ = ["BacenConnector"]
