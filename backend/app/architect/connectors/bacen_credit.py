"""
app/architect/connectors/bacen_credit.py — Conector BACEN: Séries de Crédito

Séries SGS utilizadas:
  20714 — Taxa média de juros: crédito rotativo PF (% a.m.)
  20715 — Taxa máxima de juros: crédito rotativo PF (% a.m.)
  20706 — Taxa média de juros: cheque especial PF (% a.m.)
  25433 — Taxa média de juros: crédito consignado INSS (% a.m.)

Atenção: estas séries já vêm em % a.m. na API. O valor "15.67" significa
15,67% a.m. = decimal 0.1567. NÃO dividir por 12.

Uso:
    connector = BacenCreditConnector()
    rates = connector.get_rates()
    rotativo = rates["rotativo_monthly"]        # ex: 0.1567 (15.67% a.m.)
    cheque   = rates["cheque_especial_monthly"] # ex: 0.1080 (10.80% a.m.)
"""

import logging
from typing import Dict

import httpx

from app.architect.connectors.base import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)


class BacenCreditConnector(BaseConnector):
    """
    Conector para séries de crédito PF do SGS/BACEN.

    Fornece taxas reais de crédito rotativo e cheque especial — muito mais
    precisas do que a aproximação SELIC + spread usada anteriormente.
    Usadas como benchmark para detectar abuso em _detect_juros_rotativo()
    e _detect_cheque_especial() no NegotiationOpportunityDetector.

    Args:
        cache_ttl_seconds: padrão 21600 (6h) — séries de crédito mudam mensalmente.
    """

    _SGS_URL = (
        "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series}"
        "/dados/ultimos/1?formato=json"
    )

    _ROTATIVO_SERIES        = 20714   # crédito rotativo PF — taxa média (% a.m.)
    _ROTATIVO_MAX_SERIES    = 20715   # crédito rotativo PF — taxa máxima (% a.m.)
    _CHEQUE_ESPECIAL_SERIES = 20706   # cheque especial PF — taxa média (% a.m.)
    _CONSIGNADO_SERIES      = 25433   # crédito consignado INSS — taxa média (% a.m.)

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("cache_ttl_seconds", 21600)  # 6h — séries mudam mensalmente
        super().__init__(**kwargs)

    # ── Interface obrigatória ─────────────────────────────────────────────

    def fetch_rates(self) -> Dict[str, float]:
        """
        Busca as três séries de crédito PF na API SGS.

        Returns:
            {
                "rotativo_monthly":        float,  # ex: 0.1567 = 15.67% a.m.
                "rotativo_max_monthly":    float,
                "cheque_especial_monthly": float,
                "consignado_monthly":      float,  # ex: 0.0175 = 1.75% a.m.
            }

        Raises:
            ConnectorError: Se qualquer série estiver ausente ou malformada.
        """
        rates: Dict[str, float] = {}
        series_map = {
            self._ROTATIVO_SERIES:        "rotativo_monthly",
            self._ROTATIVO_MAX_SERIES:    "rotativo_max_monthly",
            self._CHEQUE_ESPECIAL_SERIES: "cheque_especial_monthly",
            self._CONSIGNADO_SERIES:      "consignado_monthly",
        }

        with httpx.Client(timeout=self.timeout) as client:
            for series_id, key in series_map.items():
                url = self._SGS_URL.format(series=series_id)
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()
                if not data or not isinstance(data, list) or "valor" not in data[0]:
                    raise ConnectorError(
                        f"Resposta inesperada da API BACEN (série {series_id}): {data}"
                    )
                # Série já vem em % a.m. — apenas divide por 100 para decimal
                rates[key] = round(float(data[0]["valor"]) / 100, 6)

        logger.info(
            "[BacenCreditConnector] rotativo=%.4f%% a.m. | cheque=%.4f%% a.m.",
            rates["rotativo_monthly"] * 100,
            rates["cheque_especial_monthly"] * 100,
        )
        return rates

    def get_fallback_rates(self) -> Dict[str, float]:
        """
        Valores de referência de abr/2026 (BACEN — SGS).
        Atualizar após cada divulgação mensal do BACEN.
        """
        return {
            "rotativo_monthly":        0.1567,   # 15.67% a.m. (mar/2026)
            "rotativo_max_monthly":    0.1770,   # 17.70% a.m.
            "cheque_especial_monthly": 0.1080,   # 10.80% a.m.
            "consignado_monthly":      0.0175,   #  1.75% a.m. (mar/2026)
        }

    # ── Convenience ──────────────────────────────────────────────────────

    def get_rotativo_monthly(self) -> float:
        """Taxa média do crédito rotativo PF em decimal (ex: 0.1567)."""
        return self.get_rates()["rotativo_monthly"]

    def get_cheque_especial_monthly(self) -> float:
        """Taxa média do cheque especial PF em decimal (ex: 0.1080)."""
        return self.get_rates()["cheque_especial_monthly"]

    def get_consignado_monthly(self) -> float:
        """Taxa média do crédito consignado INSS em decimal (ex: 0.0175)."""
        return self.get_rates()["consignado_monthly"]


__all__ = ["BacenCreditConnector"]
