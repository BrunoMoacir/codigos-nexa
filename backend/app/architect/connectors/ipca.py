"""
app/architect/connectors/ipca.py — Conector IPCA (M3.1)

Feature: F3 - Nexa Architect / M3.1 — Ajuste por Inflação

Responsabilidade:
    Busca o IPCA acumulado em 12 meses (série SGS 13522 do BCB) para ajustar
    projeções de investimento ao poder de compra real.

API:
    Sistema SGS - Gerenciador de Séries Temporais do BCB
    URL: https://api.bcb.gov.br/dados/serie/bcdata.sgs.13522/dados/ultimos/1?formato=json
    Série 13522: IPCA — variação ACUMULADA EM 12 MESES (%)
    (a série 433 é a variação MENSAL — ver comentário em _IPCA_SERIES)
    Pública, sem autenticação.

Fallback:
    4.50% a.a. — meta de inflação do CMN para 2026.
    Atualizar trimestralmente se necessário.

Uso:
    >>> connector = IPCAConnector()
    >>> ipca = connector.get_ipca()   # ex: 0.0487
    >>> print(f"IPCA: {ipca:.2%}")
    IPCA: 4.87%
"""

import logging
from typing import Dict

import httpx

from app.architect.connectors.base import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)

# Meta de inflação do CMN para 2026 — usado como fallback
_FALLBACK_IPCA_ANNUAL: float = 0.045   # 4.5% a.a.


class IPCAConnector(BaseConnector):
    """
    Conector para o IPCA acumulado em 12 meses (SGS série 13522).

    Busca o valor mais recente disponível na API do Banco Central.
    O IPCA é divulgado mensalmente pelo IBGE e reflete a inflação
    acumulada nos últimos 12 meses.

    Taxas retornadas:
        ipca_annual (float): IPCA acumulado 12 meses em decimal
                             Ex: 0.0487 para 4.87% a.a.

    Args:
        cache_ttl_seconds:          TTL do cache — padrão 6h (IPCA muda mensalmente).
        timeout_seconds:            Timeout do request HTTP. Padrão: 5s.
        fallback_cache_ttl_seconds: TTL do fallback. Padrão: 300s (5 min).

    Example:
        >>> connector = IPCAConnector()
        >>> ipca = connector.get_ipca()
        >>> fv_real = fv_nominal / (1 + ipca) ** (months / 12)
    """

    _SGS_BASE_URL = (
        "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series}"
        "/dados/ultimos/1?formato=json"
    )
    # Série 13522: IPCA — variação ACUMULADA EM 12 MESES (%), que é o que
    # este conector promete devolver e o que todo consumidor assume.
    #
    # Estava usando a série 433, que é a variação MENSAL — e o próprio código
    # tinha a nota dizendo isso. O valor cru era devolvido como `ipca_annual`:
    # em 01/07/2026 a 433 dava 0,07 e a 13522 dava 4,44. Ou seja, a inflação
    # anual entrava no sistema como 0,07% em vez de 4,44%, ~60x menor.
    #
    # O maior estrago era no consórcio: o reajuste da carta (INCC ≈ IPCA×1,5)
    # virava 0,105% a.a. em vez de ~7%, e uma carta de R$300k em 180 meses
    # saía por R$ 365k em vez de R$ 627k — 71% de custo a menos numa decisão
    # de 15 anos.
    _IPCA_SERIES = 13522
    # Série mensal, mantida para quem precisa da variação do mês (não é o
    # que get_ipca() devolve).
    _IPCA_MONTHLY_SERIES = 433
    _CACHE_TTL   = 6 * 3600     # 6 horas (divulgação mensal)

    # Guarda de plausibilidade: IPCA anual fora desta faixa é sinal de erro de
    # unidade ou de série trocada, não de economia brasileira exótica. O
    # menor IPCA 12m da série histórica foi ~1,9% (2017) e o maior no período
    # pós-Real ~12,5% (2002/2021) — a faixa abaixo é folgada nos dois lados.
    _IPCA_MIN_PLAUSIVEL = 0.005   # 0,5% a.a.
    _IPCA_MAX_PLAUSIVEL = 0.40    # 40% a.a.

    def __init__(self, **kwargs):
        kwargs.setdefault("cache_ttl_seconds", self._CACHE_TTL)
        super().__init__(**kwargs)

    # ── Interface obrigatória ─────────────────────────────────────────────

    def fetch_rates(self) -> Dict[str, float]:
        """
        Busca o IPCA acumulado em 12 meses na API SGS do BACEN.

        Returns:
            {"ipca_annual": float}
            Ex: {"ipca_annual": 0.0487}

        Raises:
            ConnectorError: Se a resposta estiver vazia ou mal-formada.
        """
        url = self._SGS_BASE_URL.format(series=self._IPCA_SERIES)

        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url)
            response.raise_for_status()

        data = response.json()

        if not data or not isinstance(data, list) or "valor" not in data[0]:
            raise ConnectorError(
                f"Resposta inesperada da API BACEN "
                f"(série {self._IPCA_SERIES}): {data}"
            )

        ipca_pct    = float(data[0]["valor"])   # ex: 4.87 (percentual)
        ipca_annual = ipca_pct / 100            # ex: 0.0487 (decimal)

        # Rejeitar valor implausível em vez de propagar: é exatamente assim
        # que a variação mensal passava por anual sem ninguém perceber. Com a
        # exceção, o multi-layer fallback cai na fonte secundária (IBGE) ou
        # na taxa fixa versionada — as duas corretas.
        if not (self._IPCA_MIN_PLAUSIVEL <= ipca_annual <= self._IPCA_MAX_PLAUSIVEL):
            raise ConnectorError(
                f"IPCA anual implausível ({ipca_pct}%) na série "
                f"{self._IPCA_SERIES} — provável troca de série ou de unidade"
            )

        logger.info("[IPCAConnector] IPCA 12m: %.2f%%", ipca_pct)
        return {"ipca_annual": ipca_annual}

    def fetch_rates_secondary(self) -> Dict[str, float]:
        """
        Fonte secundária: IBGE SIDRA API — produtor original do IPCA.

        Usa o agregado 7060, variável 2266 (variação acumulada nos últimos
        12 meses, %). Independente da infraestrutura do BCB.

        URL: https://servicodados.ibge.gov.br/api/v3/agregados/7060/
                  periodos/-1/variaveis/2266?localidades=N1[1]
        """
        url = (
            "https://servicodados.ibge.gov.br/api/v3/agregados/7060"
            "/periodos/-1/variaveis/2266?localidades=N1[1]"
        )
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url)
            response.raise_for_status()

        data = response.json()
        try:
            series_dict: dict = (
                data[0]["resultados"][0]["series"][0]["serie"]
            )
            latest_value = list(series_dict.values())[-1]
            ipca_annual = float(latest_value) / 100.0
        except (IndexError, KeyError, ValueError, TypeError) as exc:
            raise ConnectorError(f"IBGE SIDRA: resposta inesperada — {exc}") from exc

        logger.info("[IPCAConnector] IPCA 12m via IBGE: %.2f%%", ipca_annual * 100)
        return {"ipca_annual": round(ipca_annual, 6)}

    def get_fallback_rates(self) -> Dict[str, float]:
        """
        Retorna meta de inflação do CMN como fallback.

        Referência: Meta CMN 2026 = 3.0% (central) com tolerância até 4.5%.
        Usamos 4.5% como estimativa conservadora.

        Returns:
            {"ipca_annual": 0.045}
        """
        logger.warning(
            "[IPCAConnector] Usando fallback IPCA: %.1f%%",
            _FALLBACK_IPCA_ANNUAL * 100,
        )
        return {"ipca_annual": _FALLBACK_IPCA_ANNUAL}

    # ── Convenience methods ──────────────────────────────────────────────

    def get_ipca(self) -> float:
        """
        Retorna o IPCA acumulado em 12 meses em decimal.

        Returns:
            float: ex. 0.0487 para 4.87% a.a.
        """
        return self.get_rates()["ipca_annual"]


# ── Funções utilitárias de ajuste por inflação ──────────────────────────────

def deflate(
    nominal_value: float,
    ipca_annual: float,
    years: float,
) -> float:
    """
    Converte um valor futuro nominal para valor real (poder de compra de hoje).

    Fórmula:
        valor_real = valor_nominal / (1 + ipca_annual) ^ anos

    Args:
        nominal_value: Valor futuro em R$ nominais.
        ipca_annual:   Taxa de inflação anual em decimal (ex: 0.045).
        years:         Número de anos no futuro (ex: 5 ou months/12).

    Returns:
        float: Valor em R$ de poder de compra atual.

    Example:
        >>> deflate(180_000, 0.045, 5)
        145_916.3...  # R$145k de hoje equivalem a R$180k em 5 anos c/ 4.5% IPCA
    """
    if years <= 0 or ipca_annual < 0:
        return nominal_value
    return nominal_value / ((1 + ipca_annual) ** years)


def real_return(
    nominal_rate: float,
    ipca_annual: float,
) -> float:
    """
    Calcula a taxa real de retorno (Fisher equation).

    Taxa real = (1 + nominal) / (1 + inflação) - 1

    Args:
        nominal_rate: Taxa nominal anual em decimal (ex: 0.1325 para SELIC).
        ipca_annual:  Taxa de inflação anual em decimal (ex: 0.045).

    Returns:
        float: Taxa de retorno real anual em decimal.

    Example:
        >>> real_return(0.1325, 0.045)
        0.0837...  # ~8.4% a.a. real
    """
    return (1 + nominal_rate) / (1 + ipca_annual) - 1


__all__ = ["IPCAConnector", "deflate", "real_return"]
