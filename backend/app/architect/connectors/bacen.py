"""
app/architect/connectors/bacen.py - Conector BACEN (Banco Central do Brasil)

Feature: F3 - Nexa Architect
Version: 1.1.0

Dados fornecidos:
    selic_annual (float): Taxa SELIC meta anual em decimal
                          Ex: 13.25% a.a. → 0.1325
    tr_monthly (float):   Taxa Referencial (TR) mensal em decimal (OPP4-A)
                          Ex: 0.0000 quando a TR está zerada (comum desde ~2017)

API:
    Sistema SGS - Gerenciador de Séries Temporais do BCB
    URL: https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series}/dados/ultimos/1?formato=json
    Série 432: Taxa SELIC meta - valor nominal anual em %
    Série 226: Taxa Referencial (TR) - valor mensal em %
    Pública, sem autenticação.

Nota sobre acoplamento SELIC/TR (OPP4-A): fetch_rates() busca as duas séries numa
única chamada, seguindo o mesmo padrão de múltiplas séries já usado em
BacenCreditConnector. Consequência aceita: uma falha pontual na série de TR
também aciona o fallback de SELIC (raro — a série de TR quase nunca falha
isoladamente — e o cache de fallback dura só fallback_cache_ttl_seconds,
60s por padrão). get_tr_monthly() usa .get() defensivo porque
fetch_rates_secondary() (fonte alternativa só de SELIC, série 4390) não inclui TR.

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
    nas simulações de NPV e como referência de custo de oportunidade, e a
    Taxa Referencial — TR (série 226), usada na fórmula oficial de
    rendimento da poupança (OPP4-A/B).

    A SELIC só muda nas reuniões do COPOM (~a cada 45 dias) e a TR muda
    mensalmente, então o cache de 1 hora padrão é mais que suficiente para o MVP.

    Taxas retornadas:
        selic_annual (float): Taxa SELIC meta anual em decimal
                              Ex: 0.1325 para 13.25% a.a.
        tr_monthly (float):   Taxa Referencial mensal em decimal
                              Ex: 0.0 quando a TR está zerada

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
    _SELIC_META_SERIES   = 432   # Taxa SELIC meta — % nominal anual
    _SELIC_EFETIVA_SERIES = 4390  # SELIC over anualizada (% a.a.) — fonte secundária
    _TR_SERIES = 226              # Taxa Referencial (TR) — % mensal (OPP4-A)

    # TR tem ficado em 0% na quase totalidade dos meses desde ~2017 (SELIC baixa
    # no período). Fallback conservador — atualizar se a TR voltar a ser positiva
    # de forma sustentada. Referência: consulta SGS 226 em 2026-07-04.
    _TR_FALLBACK_MONTHLY = 0.0

    # ── Interface obrigatória ─────────────────────────────────────────────

    def fetch_rates(self) -> Dict[str, float]:
        """
        Busca SELIC meta (série 432) e TR (série 226) mais recentes na API SGS.

        Usa self.timeout para cada request HTTP. As duas séries são buscadas
        na mesma chamada (ver nota de acoplamento no docstring do módulo).

        Returns:
            {"selic_annual": float, "tr_monthly": float}
            Ex: {"selic_annual": 0.1325, "tr_monthly": 0.0}

        Raises:
            ConnectorError: Se qualquer resposta estiver vazia ou mal-formada.
            httpx.HTTPError: Se algum request HTTP falhar (capturado por get_rates()).
        """
        rates: Dict[str, float] = {}

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
        rates["selic_annual"] = float(data[0]["valor"]) / 100   # ex: 13.25 → 0.1325

        url_tr = self._SGS_BASE_URL.format(series=self._TR_SERIES)
        with httpx.Client(timeout=self.timeout) as client:
            response_tr = client.get(url_tr)
            response_tr.raise_for_status()
        data_tr = response_tr.json()
        if not data_tr or not isinstance(data_tr, list) or "valor" not in data_tr[0]:
            raise ConnectorError(
                f"Resposta inesperada da API BACEN (série {self._TR_SERIES}): {data_tr}"
            )
        rates["tr_monthly"] = round(float(data_tr[0]["valor"]) / 100, 6)  # ex: 0.00 → 0.0

        return rates

    def fetch_rates_secondary(self) -> Dict[str, float]:
        """
        Fonte secundária: SGS série 4390 (SELIC over anualizada).

        Usa a mesma infraestrutura BCB mas série diferente — cobre falhas
        de série específica sem depender de um provedor externo.
        """
        url = self._SGS_BASE_URL.format(series=self._SELIC_EFETIVA_SERIES)
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url)
            response.raise_for_status()
        data = response.json()
        if not data or not isinstance(data, list) or "valor" not in data[0]:
            raise ConnectorError(f"BCB série {self._SELIC_EFETIVA_SERIES}: resposta inesperada {data}")
        selic_annual = float(data[0]["valor"]) / 100
        logger.info("[BacenConnector] SELIC (série 4390): %.4f a.a.", selic_annual)
        return {"selic_annual": selic_annual}

    def get_fallback_rates(self) -> Dict[str, float]:
        """
        Retorna SELIC e TR hardcoded como fallback quando a API do BACEN falha.

        Referência: SELIC meta em abr/2026 = 14.75% a.a. (COPOM mar/2026).
        Atualizar após cada reunião do COPOM ou, no mínimo, trimestralmente.
        TR: ver _TR_FALLBACK_MONTHLY.

        Returns:
            {"selic_annual": 0.1475, "tr_monthly": 0.0}
        """
        return {"selic_annual": 0.1475, "tr_monthly": self._TR_FALLBACK_MONTHLY}

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

    def get_tr_monthly(self) -> float:
        """
        Retorna a Taxa Referencial (TR) mensal em decimal (OPP4-A).

        Usa .get() com fallback defensivo em vez de indexação direta: se
        get_rates() serviu o resultado via fetch_rates_secondary() (fonte
        alternativa de SELIC, série 4390), essa fonte não inclui TR — nesse
        caso específico, retorna _TR_FALLBACK_MONTHLY em vez de KeyError.

        Returns:
            Taxa Referencial mensal em decimal (ex: 0.0 quando a TR está zerada)

        Example:
            >>> connector = BacenConnector()
            >>> tr = connector.get_tr_monthly()   # 0.0
        """
        return self.get_rates().get("tr_monthly", self._TR_FALLBACK_MONTHLY)


__all__ = ["BacenConnector"]
