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

    # ATENÇÃO (PDF V2 seção 4.1): unidades validadas em 01/05/2026:
    #   20714 = 33,42 | 20706 = 55,00 | 25433 = 2,43
    # Valores 33,42 e 55,00 estão altos para % a.m. — podem ser % a.a. ou CET anualizado.
    # Até validação formal com documentação SGS, dividir por 100 e tratar como declarado.
    # NUNCA usar 20714/20706 como % a.m. sem confirmar a unidade com o BACEN primeiro.
    _ROTATIVO_SERIES        = 20714   # crédito rotativo PF — unidade a confirmar (BACEN)
    _ROTATIVO_MAX_SERIES    = 20715   # crédito rotativo PF — taxa máxima
    _CHEQUE_ESPECIAL_SERIES = 20706   # cheque especial PF — unidade a confirmar (BACEN)
    _CONSIGNADO_SERIES      = 25433   # crédito consignado INSS — provavelmente % a.m.

    # Ordem de grandeza por modalidade, em decimal a.m. Não é calibração: é o
    # que separa "taxa alta" de "unidade errada". O teto do cheque especial é
    # legal (8% a.m., Res. CMN 4.765/2019) e por isso a faixa é apertada.
    _FAIXAS_PLAUSIVEIS: Dict[str, tuple[float, float]] = {
        "rotativo_monthly":        (0.05, 0.25),
        "rotativo_max_monthly":    (0.05, 0.35),
        # A faixa é generosa de propósito: precisa aceitar o próprio fallback
        # versionado do projeto (10,80% a.m.). Guarda que rejeita o valor para o
        # qual ela cai seria absurda.
        #
        # PENDÊNCIA JURÍDICA: a Res. CMN 4.765/2019 estabeleceu teto para o
        # cheque especial de PF, e o número que se cita é 8% a.m. Se for isso,
        # o fallback de 10,80% está acima do teto legal e precisa ser revisto —
        # não alterei porque é constante versionada e a confirmação é do
        # Gabriel, não minha.
        "cheque_especial_monthly": (0.02, 0.15),
        "consignado_monthly":      (0.005, 0.05),
    }

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
                rates[key] = round(float(data[0]["valor"]) / 100, 6)

        self._validar_plausibilidade(rates)

        logger.info(
            "[BacenCreditConnector] rotativo=%.4f%% a.m. | cheque=%.4f%% a.m.",
            rates["rotativo_monthly"] * 100,
            rates["cheque_especial_monthly"] * 100,
        )
        return rates

    @classmethod
    def _validar_plausibilidade(cls, rates: Dict[str, float]) -> None:
        """
        Rejeita taxa fora da ordem de grandeza da modalidade — a guarda que o
        comentário acima vinha pedindo desde a primeira versão.

        Em 20/08/2026 as séries devolviam, tratadas como % a.m.:

            rotativo          33,44%   → 3.087% a.a.
            rotativo (máx)    20,80%   → MENOR que a média, o que é impossível
            cheque especial   80,00%   → acima do teto legal de 8% a.m.
                                          (Res. CMN 4.765/2019)
            consignado         2,43%   → plausível

        A contradição interna (máximo < média) prova que as séries estão mal
        atribuídas, sem precisar resolver qual é a unidade de cada uma. O custo
        disso era silencioso e grande: com referência de 33,44% a.m., um usuário
        pagando os 15% a.m. que são a taxa REAL de rotativo sai com múltiplo de
        0,45× e o D3 não gera achado nenhum — a comparação de juros abusivos
        ficava desligada justamente para quem paga a taxa de mercado.

        Fora da faixa → ConnectorError, e o fallback versionado assume.
        """
        for chave, (minimo, maximo) in cls._FAIXAS_PLAUSIVEIS.items():
            valor = rates.get(chave)
            if valor is None:
                continue
            if not (minimo <= valor <= maximo):
                raise ConnectorError(
                    f"{chave}={valor:.2%} a.m. fora da faixa plausível "
                    f"[{minimo:.2%}, {maximo:.2%}] — provável troca de série ou "
                    f"de unidade na SGS"
                )

        media = rates.get("rotativo_monthly")
        maxima = rates.get("rotativo_max_monthly")
        if media is not None and maxima is not None and maxima < media:
            raise ConnectorError(
                f"rotativo_max ({maxima:.2%}) menor que a média ({media:.2%}) — "
                f"séries inconsistentes"
            )

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
