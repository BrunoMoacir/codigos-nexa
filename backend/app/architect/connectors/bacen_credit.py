"""
app/architect/connectors/bacen_credit.py — Conector BACEN: Séries de Crédito

TODAS as séries usadas aqui pertencem à família "Taxa média MENSAL de juros",
cujo nome oficial no catálogo do BACEN já declara a unidade. Isso não é
detalhe de estilo: é o que encerra a dúvida de unidade que este arquivo
carregou desde a primeira versão.

Séries SGS (nome oficial, catálogo de dados abertos do BACEN):
  25477 — Taxa média mensal … recursos livres — PF — Cartão de crédito rotativo
  25478 — Taxa média mensal … recursos livres — PF — Cartão de crédito parcelado
  25463 — Taxa média mensal … recursos livres — PF — Cheque especial
  25464 — Taxa média mensal … recursos livres — PF — Crédito pessoal não consignado
  25468 — Taxa média mensal … recursos livres — PF — Crédito pessoal consignado INSS

O que havia antes, e por que estava errado (verificado em 22/08/2026 contra
https://dadosabertos.bcb.gov.br/api/3/action/package_search):

    código  usado aqui como              nome oficial da série
    ------  --------------------------   ----------------------------------------
    20714   rotativo PF (% a.m.)         Taxa média de juros das operações de
                                         crédito — TOTAL (SFN inteiro: PF+PJ,
                                         livres+direcionados), em % a.a.
    20715   rotativo máximo PF (% a.m.)  Taxa média — Pessoas JURÍDICAS — Total,
                                         em % a.a.
    20706   cheque especial PF (% a.m.)  CONCESSÕES de crédito direcionado PF —
                                         BNDES. Não é taxa: é R$ milhões.
    25433   consignado INSS (% a.m.)     Taxa média mensal — TOTAL (SFN inteiro)

Nenhum dos quatro media o que o código dizia que media. Os sintomas eram
visíveis sem consultar o catálogo:

  • a "taxa máxima" (20,80) saía MENOR que a "média" (33,44) — impossível;
    eram, respectivamente, a média de PJ e a média do SFN inteiro, ambas a.a.;
  • o "cheque especial" oscilava 32 → 772 → 55 entre meses, porque era um
    volume de concessões, não uma taxa;
  • 20714 e 25433 são a MESMA série em unidades diferentes: em 20 meses
    seguidos, (1 + 25433/100)^12 − 1 == 20714/100 dentro do arredondamento.

Custo em produção: com 33,44% a.m. de referência, quem pagava os ~15% a.m. que
são a taxa real do rotativo saía com múltiplo 0,45× e o D3 não gerava achado
nenhum. E com 10,80% a.m. de cheque especial no fallback, quem pagava o teto
legal (8% a.m.) saía com 0,77× — também sem achado, embora esteja no limite do
que a lei permite cobrar.

Uso:
    connector = BacenCreditConnector()
    rates = connector.get_rates()
    rotativo = rates["rotativo_monthly"]        # ex: 0.1513 (15,13% a.m.)
    cheque   = rates["cheque_especial_monthly"] # ex: 0.0756 ( 7,56% a.m.)
"""

import logging
from typing import Dict

import httpx

from app.architect.connectors.base import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)


# Res. CMN 4.765/2019, art. 2º — vigente desde 06/01/2020: os juros do cheque
# especial de pessoa natural e MEI estão limitados a 8% ao mês (≈151,8% a.a.).
# A mesma resolução autoriza tarifa de 0,25% sobre a parcela do limite que
# exceder R$ 500,00 (art. 3º).
#
# Confirmado também pelo próprio dado: no Olinda taxaJuros v2 de 03/08/2026 há
# um aglomerado de IFs em 8,26–8,28% a.m. (Banco do Brasil, Santander, Inter,
# C6, BTG…). Não é coincidência — é 1,08^(31/30) − 1 = 8,2774%, o teto de 8%
# a.m. convertido para um mês de 31 dias. Os grandes bancos cobram exatamente
# o teto.
TETO_CHEQUE_ESPECIAL_MENSAL = 0.08
TETO_CHEQUE_ESPECIAL_BASE_LEGAL = (
    "Res. CMN 4.765/2019, art. 2º — juros do cheque especial de pessoa natural "
    "e MEI limitados a 8% ao mês (vigente desde 06/01/2020)."
)


class BacenCreditConnector(BaseConnector):
    """
    Conector para séries de crédito PF do SGS/BACEN.

    Fornece taxas médias reais por modalidade — benchmark do D3 (juros
    abusivos), do D6 (portabilidade) e do NegotiationOpportunityDetector.

    Args:
        cache_ttl_seconds: padrão 21600 (6h) — séries de crédito mudam mensalmente.
    """

    _SGS_URL = (
        "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series}"
        "/dados/ultimos/1?formato=json"
    )

    # Catálogo oficial: código → (chave interna, trecho obrigatório do título
    # publicado pelo BACEN). O trecho é a prova de identidade E de unidade —
    # "Taxa média mensal" está no nome. `tests/defense/test_series_bacen.py`
    # confronta este dicionário com o catálogo de dados abertos do BACEN, que é
    # o único jeito de a próxima pessoa saber que os códigos continuam certos.
    SERIES: Dict[int, tuple[str, str]] = {
        25477: (
            "rotativo_monthly",
            "Taxa média mensal de juros das operações de crédito com recursos "
            "livres - Pessoas físicas - Cartão de crédito rotativo",
        ),
        25478: (
            "parcelado_monthly",
            "Taxa média mensal de juros das operações de crédito com recursos "
            "livres - Pessoas físicas - Cartão de crédito parcelado",
        ),
        25463: (
            "cheque_especial_monthly",
            "Taxa média mensal de juros das operações de crédito com recursos "
            "livres - Pessoas físicas - Cheque especial",
        ),
        25464: (
            "pessoal_monthly",
            "Taxa média mensal de juros das operações de crédito com recursos "
            "livres - Pessoas físicas - Crédito pessoal não consignado",
        ),
        25468: (
            "consignado_monthly",
            "Taxa média mensal de juros das operações de crédito com recursos "
            "livres - Pessoas físicas - Crédito pessoal consignado para "
            "aposentados e pensionistas do INSS",
        ),
    }

    # Endpoint do catálogo de dados abertos do BACEN (CKAN). Não é chamado em
    # produção — é a autoridade que o teste de contrato consulta.
    CATALOGO_URL = "https://dadosabertos.bcb.gov.br/api/3/action/package_search"

    # Ordem de grandeza por modalidade, em decimal a.m. Não é calibração: é o
    # que separa "taxa alta" de "série trocada". Os limites vêm do dado medido
    # em jun/2026 com folga, e o do cheque especial vem da lei — a média de uma
    # modalidade com teto de 8% a.m. não pode estar em 10%, muito menos em 80%.
    _FAIXAS_PLAUSIVEIS: Dict[str, tuple[float, float]] = {
        "rotativo_monthly":        (0.08, 0.30),   # medido: 15,13%
        "parcelado_monthly":       (0.02, 0.20),   # medido:  9,32%
        "cheque_especial_monthly": (0.01, 0.10),   # medido:  7,56% | teto legal 8%
        "pessoal_monthly":         (0.01, 0.15),   # medido:  7,08%
        "consignado_monthly":      (0.005, 0.05),  # medido:  1,83%
    }

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("cache_ttl_seconds", 21600)  # 6h — séries mudam mensalmente
        super().__init__(**kwargs)

    # ── Interface obrigatória ─────────────────────────────────────────────

    def fetch_rates(self) -> Dict[str, float]:
        """
        Busca as séries de crédito PF na API SGS.

        Returns:
            {
                "rotativo_monthly":        float,  # ex: 0.1513 = 15,13% a.m.
                "parcelado_monthly":       float,
                "cheque_especial_monthly": float,
                "pessoal_monthly":         float,
                "consignado_monthly":      float,  # ex: 0.0183 = 1,83% a.m.
            }

        Raises:
            ConnectorError: se alguma série vier ausente, malformada ou fora da
                ordem de grandeza da modalidade.
        """
        rates: Dict[str, float] = {}

        with httpx.Client(timeout=self.timeout) as client:
            for series_id, (key, _titulo) in self.SERIES.items():
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
            "[BacenCreditConnector] rotativo=%.2f%% | cheque=%.2f%% | consignado=%.2f%% (a.m.)",
            rates["rotativo_monthly"] * 100,
            rates["cheque_especial_monthly"] * 100,
            rates["consignado_monthly"] * 100,
        )
        return rates

    @classmethod
    def _validar_plausibilidade(cls, rates: Dict[str, float]) -> None:
        """
        Rejeita taxa fora da ordem de grandeza da modalidade e ordem de produto
        invertida — a guarda que o comentário do arquivo vinha pedindo desde a
        primeira versão, e que teria apontado as quatro séries trocadas.

        Duas checagens:

        1. Faixa por modalidade (`_FAIXAS_PLAUSIVEIS`). Pega troca de unidade
           (% a.a. lida como % a.m.) e série que nem é taxa.

        2. Ordem entre produtos: consignado < cheque especial < rotativo. É
           invariante da estrutura do crédito no Brasil — consignado tem
           desconto em folha (menor risco), rotativo é dívida sem garantia com
           a maior inadimplência do mercado. Uma troca de códigos entre
           modalidades pode passar pelas faixas e não passa por aqui.

        Fora do esperado → ConnectorError, e o fallback versionado assume.
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

        ordem = [
            ("consignado_monthly", "cheque_especial_monthly"),
            ("cheque_especial_monthly", "rotativo_monthly"),
        ]
        for menor, maior in ordem:
            a, b = rates.get(menor), rates.get(maior)
            if a is None or b is None:
                continue
            if a >= b:
                raise ConnectorError(
                    f"{menor} ({a:.2%} a.m.) não pode ser >= {maior} ({b:.2%} a.m.) "
                    f"— séries trocadas entre modalidades"
                )

    def get_fallback_rates(self) -> Dict[str, float]:
        """
        Valores de jun/2026 (BACEN — SGS, família "Taxa média mensal").
        Atualizar após cada divulgação mensal do BACEN.
        """
        return {
            "rotativo_monthly":        0.1513,   # 15,13% a.m. — SGS 25477
            "parcelado_monthly":       0.0932,   #  9,32% a.m. — SGS 25478
            "cheque_especial_monthly": 0.0756,   #  7,56% a.m. — SGS 25463
            "pessoal_monthly":         0.0708,   #  7,08% a.m. — SGS 25464
            "consignado_monthly":      0.0183,   #  1,83% a.m. — SGS 25468
        }

    # ── Convenience ──────────────────────────────────────────────────────

    def get_rotativo_monthly(self) -> float:
        """Taxa média do crédito rotativo PF em decimal (ex: 0.1513)."""
        return self.get_rates()["rotativo_monthly"]

    def get_cheque_especial_monthly(self) -> float:
        """Taxa média do cheque especial PF em decimal (ex: 0.0756)."""
        return self.get_rates()["cheque_especial_monthly"]

    def get_consignado_monthly(self) -> float:
        """Taxa média do crédito consignado INSS em decimal (ex: 0.0183)."""
        return self.get_rates()["consignado_monthly"]


__all__ = [
    "BacenCreditConnector",
    "TETO_CHEQUE_ESPECIAL_MENSAL",
    "TETO_CHEQUE_ESPECIAL_BASE_LEGAL",
]
