"""
app/architect/connectors/anbima.py - Conector ANBIMA (CDI/DI)

Feature: F3 - Nexa Architect
Version: 1.0.0

Dados fornecidos (Fase 1):
    cdi_annual (float): Taxa CDI anual em decimal
                        Ex: 13.15% a.a. → 0.1315

Fonte (Fase 1 — MVP):
    BCB SGS série 12: CDI over acumulado no mês, anualizado
    URL: https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados/ultimos/1?formato=json
    Pública, sem autenticação.

    O CDI é publicado diariamente pela B3 e reproduzido pelo BCB.
    Para Phase 1, usar BCB evita a necessidade de OAuth2 com ANBIMA.

Fonte (Fase 2 — TODO):
    ANBIMA Developer API (requer registro e OAuth2):
    https://developers.anbima.com.br
    Fornece além do CDI: curva DI, taxa de referência, spreads de debêntures.

Relação CDI × SELIC:
    CDI ≈ SELIC - 0.10% a.a. (convenção histórica do mercado brasileiro).
    Ex: SELIC 13.25% → CDI ~13.15%
"""

import logging
from typing import Dict

import httpx

from app.architect.connectors.base import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)


class AnbimaConnector(BaseConnector):
    """
    Conector para a taxa CDI (Certificado de Depósito Interbancário).

    O CDI é o principal benchmark de renda fixa brasileiro, usado nas
    simulações como taxa de retorno da estratégia Poupar/Investir (C).

    Fase 1: dados via BCB SGS série 12 (público, sem auth).
    Fase 2 (TODO): migrar para ANBIMA Developer API com OAuth2.

    Taxas retornadas:
        cdi_annual (float): Taxa CDI anual em decimal
                            Ex: 0.1315 para 13.15% a.a.

    Args:
        cache_ttl_seconds:          TTL do cache após fetch bem-sucedido.
                                    Padrão: 3600 (1 hora). O CDI muda diariamente
                                    mas varia poucos bps por dia — 1h é suficiente.
        timeout_seconds:            Timeout do request HTTP. Padrão: 5s.
        fallback_cache_ttl_seconds: TTL do cache quando a API falha.
                                    Padrão: 60s (retry em 1 minuto).

    Example:
        >>> connector = AnbimaConnector()
        >>> cdi = connector.get_cdi()
        >>> print(f"CDI: {cdi:.2%}")
        CDI: 13.15%
        >>> monthly_rate = (1 + cdi) ** (1/12) - 1
    """

    _SGS_BASE_URL = (
        "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series}"
        "/dados/ultimos/1?formato=json"
    )
    _CDI_SERIES = 12  # CDI over acumulado no mês, anualizado — % a.a.

    # ── Interface obrigatória ─────────────────────────────────────────────

    def fetch_rates(self) -> Dict[str, float]:
        """
        Busca a taxa CDI mais recente via BCB SGS série 12.

        Usa self.timeout para o request HTTP.

        Returns:
            {"cdi_annual": float}
            Ex: {"cdi_annual": 0.1315}

        Raises:
            ConnectorError: Se a resposta estiver vazia ou mal-formada.
            httpx.HTTPError: Se o request HTTP falhar (capturado por get_rates()).
        """
        url = self._SGS_BASE_URL.format(series=self._CDI_SERIES)

        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url)
            response.raise_for_status()

        data = response.json()

        if not data or not isinstance(data, list) or "valor" not in data[0]:
            raise ConnectorError(
                f"Resposta inesperada da API BCB "
                f"(série {self._CDI_SERIES}): {data}"
            )

        cdi_pct = float(data[0]["valor"])   # ex: 13.15 (percentual)
        cdi_annual = cdi_pct / 100          # ex: 0.1315 (decimal)

        return {"cdi_annual": cdi_annual}

    def get_fallback_rates(self) -> Dict[str, float]:
        """
        Retorna CDI hardcoded como fallback quando a API falha.

        Referência: CDI em abr/2026 ≈ 14.65% a.a. (SELIC 14.75% - 0.10%).
        Atualizar trimestralmente ou sempre que a SELIC mudar mais de 0.50%.

        Returns:
            {"cdi_annual": 0.1465}
        """
        return {"cdi_annual": 0.1465}

    # ── Convenience methods ───────────────────────────────────────────────

    def get_cdi(self) -> float:
        """
        Retorna a taxa CDI anual em decimal.

        Shorthand para get_rates()["cdi_annual"].
        Aplica cache e fallback automaticamente via BaseConnector.

        Returns:
            Taxa CDI anual em decimal (ex: 0.1315 para 13.15% a.a.)

        Example:
            >>> connector = AnbimaConnector()
            >>> cdi = connector.get_cdi()              # 0.1315
            >>> monthly = (1 + cdi) ** (1/12) - 1     # 0.01034...
        """
        return self.get_rates()["cdi_annual"]


__all__ = ["AnbimaConnector"]
