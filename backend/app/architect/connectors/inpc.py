"""
app/architect/connectors/inpc.py — Conector INPC (D5 correção monetária)

INPC (Índice Nacional de Preços ao Consumidor) — produzido pelo IBGE.
Série SGS 188: variação MENSAL do INPC (%).

Diferença do IPCA:
  IPCA — cobre famílias com renda de 1 a 40 salários mínimos.
  INPC — cobre famílias com renda de 1 a 5 salários mínimos (mais adequado
         para correção de dívidas contra consumidores de menor renda).

Usado em D5 (EvidenceBuilder) como alternativa ao IPCA para correção monetária.
O PDF V2 (seção 4.1) orienta criar INPCConnector dedicado em vez de usar IPCA como proxy.

API:
    SGS BACEN — série 188 (variação mensal %)
    URL: https://api.bcb.gov.br/dados/serie/bcdata.sgs.188/dados/ultimos/1?formato=json
    Público, sem autenticação.

Fallback: 4.80% a.a. (INPC histórico 2025/2026).
"""

import logging
from typing import Dict

import httpx

from app.architect.connectors.base import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)

_FALLBACK_INPC_MONTHLY: float = 0.004   # 0.40% a.m. (~4.8% a.a.)
_INPC_SERIES = 188


class INPCConnector(BaseConnector):
    """
    Conector para a variação MENSAL do INPC (SGS série 188).

    Retorna a variação percentual do último mês disponível.
    Para correção monetária acumulada, use evidence_builder._fetch_monthly_rates(188, ...).

    Taxas retornadas:
        inpc_monthly (float): variação mensal em decimal (ex: 0.0065 para 0.65%)

    Cache: 6h (divulgação mensal pelo IBGE).
    """

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("cache_ttl_seconds", 21600)  # 6h
        super().__init__(**kwargs)

    def fetch_rates(self) -> Dict[str, float]:
        """
        Busca a variação mensal do INPC na API SGS do BACEN.

        Returns:
            {"inpc_monthly": float}  — ex: {"inpc_monthly": 0.0065} = 0.65% a.m.

        Raises:
            ConnectorError: Se a resposta estiver vazia ou mal-formada.
        """
        url = (
            f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{_INPC_SERIES}"
            "/dados/ultimos/1?formato=json"
        )
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(url)
            resp.raise_for_status()

        data = resp.json()
        if not data or not isinstance(data, list) or "valor" not in data[0]:
            raise ConnectorError(f"Resposta inesperada SGS série {_INPC_SERIES}: {data}")

        pct = float(data[0]["valor"])   # ex: 0.65
        monthly = round(pct / 100, 6)  # ex: 0.0065

        logger.info("[INPCConnector] INPC mensal: %.4f%% (série %d)", pct, _INPC_SERIES)
        return {"inpc_monthly": monthly}

    def get_fallback_rates(self) -> Dict[str, float]:
        return {"inpc_monthly": _FALLBACK_INPC_MONTHLY}

    def get_inpc_monthly(self) -> float:
        """Variação mensal do INPC em decimal (ex: 0.0065 = 0.65% a.m.)."""
        return self.get_rates()["inpc_monthly"]


__all__ = ["INPCConnector"]
