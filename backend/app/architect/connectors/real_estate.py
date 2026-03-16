"""
app/architect/connectors/real_estate.py - Conector de Dados Imobiliários (FipeZAP/IBGE)

Feature: F3 - Nexa Architect (F3.5 — Leverage Strategy)
Version: 1.0.0

Responsabilidade:
    Fornecer preço médio/m² e aluguel médio/m² por cidade e bairro,
    permitindo que o agente calcule automaticamente asset_value e monthly_rent
    quando o usuário informa apenas "70m² no Buritis em BH".

Fontes de dados:
    Primária:  FipeZAP (fipezap.zapimoveis.com.br) — índice imobiliário mensal
               Não há API pública JSON estável; tentativa via scraping será
               realizada, com degradação graciosa para o fallback.
    Secundária: IBGE / PNAD — preços regionais de habitação

Fallback:
    Base hardcoded com ~60 cidades/bairros, extraída dos relatórios mensais
    FipeZAP fev/2026. Atualizar trimestralmente.

Integração:
    - Instanciado pelo LeverageOptimizer via get_leverage_simulation tool
    - Permite que o agente resolva "70m² no Buritis" → asset_value=525.000,
      monthly_rent=1.750 automaticamente antes de chamar o otimizador.

Uso:
    connector = RealEstateDataConnector()
    data = connector.get_location_data("belo horizonte", "buritis")
    # {"price_sqm": 7500.0, "rent_sqm": 25.0, "source": "fipezap_fallback",
    #  "city_normalized": "belo_horizonte", "neighborhood_normalized": "buritis"}

    # Calcular asset_value e monthly_rent para 70m²:
    asset_value  = data["price_sqm"] * 70  # R$ 525.000
    monthly_rent = data["rent_sqm"]  * 70  # R$ 1.750
"""

import logging
import unicodedata
from typing import Dict, Optional

import httpx

from app.architect.connectors.base import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)


# ── Normalização de nomes ─────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """
    Remove acentos, converte para minúsculas e substitui espaços por underscores.

    "Belo Horizonte" → "belo_horizonte"
    "Itaim Bibi"     → "itaim_bibi"
    "São Paulo"      → "sao_paulo"
    """
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return ascii_str.lower().strip().replace(" ", "_").replace("-", "_")


# Aliases de cidade: abreviações e nomes populares → slug canônico
_CITY_ALIASES: Dict[str, str] = {
    # São Paulo
    "sp": "sao_paulo", "sampa": "sao_paulo",
    # Rio de Janeiro
    "rj": "rio_de_janeiro", "rio": "rio_de_janeiro",
    # Belo Horizonte
    "bh": "belo_horizonte", "bhz": "belo_horizonte",
    # Brasília / DF
    "df": "brasilia", "bsb": "brasilia", "distrito_federal": "brasilia",
    # Curitiba
    "cwb": "curitiba",
    # Porto Alegre
    "poa": "porto_alegre",
    # Florianópolis
    "floripa": "florianopolis",
    # Campinas
    "cps": "campinas",
    # Fortaleza
    "for": "fortaleza",
    # Salvador
    "ssa": "salvador",
    # Goiânia
    "gyn": "goiania",
    # Manaus
    "mao": "manaus",
    # Recife
    "rec": "recife",
}


class RealEstateDataConnector(BaseConnector):
    """
    Conector de preços imobiliários por cidade/bairro.

    Fornece preço médio/m² e aluguel médio/m² para localidades brasileiras,
    permitindo ao agente calcular automaticamente asset_value e monthly_rent
    a partir de "NxM² em [bairro], [cidade]".

    Taxas de fallback (FipeZAP fev/2026):
        Cobertura: São Paulo, Rio de Janeiro, Belo Horizonte, Brasília,
        Curitiba, Porto Alegre, Florianópolis, Campinas, Fortaleza,
        Salvador, Recife, Goiânia, Manaus — com ~60 bairros.

    Cache:
        TTL de 24h (dados mudam mensalmente). Chave: "RealEstateDataConnector".

    Args:
        cache_ttl_seconds:          Padrão: 86400 (24h).
        timeout_seconds:            Timeout HTTP. Padrão: 8s.
        fallback_cache_ttl_seconds: Padrão: 3600 (1h).

    Example:
        >>> connector = RealEstateDataConnector()
        >>> data = connector.get_location_data("bh", "buritis")
        >>> data["price_sqm"]    # 7500.0
        >>> data["rent_sqm"]     # 25.0
        >>> data["rent_yield_monthly"]  # 0.00333 (0.33%/mês)
    """

    _DEFAULT_CACHE_TTL = 86_400  # 24h — dados mudam mensalmente

    # URL placeholder — FipeZAP não tem API JSON pública estável.
    # Se futuramente disponibilizarem, substituir aqui.
    _FIPEZAP_API_URL = "https://fipezap.zapimoveis.com.br/api/v1/indices"

    def __init__(
        self,
        cache_ttl_seconds: int = _DEFAULT_CACHE_TTL,
        timeout_seconds: float = 8.0,
        fallback_cache_ttl_seconds: int = 3_600,
    ) -> None:
        super().__init__(
            cache_ttl_seconds=cache_ttl_seconds,
            timeout_seconds=int(timeout_seconds),
            fallback_cache_ttl_seconds=fallback_cache_ttl_seconds,
        )

    # ── Interface obrigatória ─────────────────────────────────────────────────

    def fetch_rates(self) -> Dict[str, float]:
        """
        Tenta buscar dados do FipeZAP.

        A FipeZAP não possui API JSON pública estável; este método tentará
        o endpoint e falhará graciosamente — BaseConnector usa fallback.

        Raises:
            ConnectorError: Se a resposta for inesperada ou o endpoint falhar.
        """
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(self._FIPEZAP_API_URL)
                response.raise_for_status()
            data = response.json()
            return self._parse_fipezap_response(data)
        except Exception as exc:
            raise ConnectorError(
                f"FipeZAP API indisponível ({exc}) — usando dados de referência fev/2026"
            ) from exc

    def get_fallback_rates(self) -> Dict[str, float]:
        """
        Base de preços imobiliários hardcoded (FipeZAP / ZapImóveis fev/2026).

        Formato das chaves: "{cidade}__{bairro}__price_sqm" e "{cidade}__{bairro}__rent_sqm"
        Valores: R$/m² (preço de venda e aluguel médio).

        Cobertura: ~60 localidades em 13 cidades.

        Returns:
            Dict plano com price_sqm e rent_sqm para cada localidade.
        """
        return {
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # SÃO PAULO — SP
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # Fonte: FipeZAP jan/2026 — índice de oferta
            "sao_paulo____price_sqm":            10_500.0,   # média SP
            "sao_paulo____rent_sqm":             40.0,

            "sao_paulo__itaim_bibi__price_sqm":  17_000.0,
            "sao_paulo__itaim_bibi__rent_sqm":   62.0,

            "sao_paulo__jardins__price_sqm":     18_500.0,
            "sao_paulo__jardins__rent_sqm":      67.0,

            "sao_paulo__vila_madalena__price_sqm": 13_200.0,
            "sao_paulo__vila_madalena__rent_sqm":  50.0,

            "sao_paulo__pinheiros__price_sqm":   13_800.0,
            "sao_paulo__pinheiros__rent_sqm":    53.0,

            "sao_paulo__moema__price_sqm":       14_500.0,
            "sao_paulo__moema__rent_sqm":        54.0,

            "sao_paulo__brooklin__price_sqm":    12_200.0,
            "sao_paulo__brooklin__rent_sqm":     46.0,

            "sao_paulo__vila_olimpia__price_sqm": 13_500.0,
            "sao_paulo__vila_olimpia__rent_sqm":  52.0,

            "sao_paulo__perdizes__price_sqm":    11_000.0,
            "sao_paulo__perdizes__rent_sqm":     42.0,

            "sao_paulo__lapa__price_sqm":        9_500.0,
            "sao_paulo__lapa__rent_sqm":         36.0,

            "sao_paulo__santana__price_sqm":     8_500.0,
            "sao_paulo__santana__rent_sqm":      33.0,

            "sao_paulo__tatuape__price_sqm":     8_800.0,
            "sao_paulo__tatuape__rent_sqm":      34.0,

            "sao_paulo__ibirapuera__price_sqm":  15_000.0,
            "sao_paulo__ibirapuera__rent_sqm":   56.0,

            "sao_paulo__consolacao__price_sqm":  11_500.0,
            "sao_paulo__consolacao__rent_sqm":   44.0,

            "sao_paulo__bela_vista__price_sqm":  10_000.0,
            "sao_paulo__bela_vista__rent_sqm":   38.0,

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # RIO DE JANEIRO — RJ
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            "rio_de_janeiro____price_sqm":          8_500.0,   # média RJ
            "rio_de_janeiro____rent_sqm":           32.0,

            "rio_de_janeiro__leblon__price_sqm":    19_500.0,
            "rio_de_janeiro__leblon__rent_sqm":     64.0,

            "rio_de_janeiro__ipanema__price_sqm":   17_500.0,
            "rio_de_janeiro__ipanema__rent_sqm":    57.0,

            "rio_de_janeiro__copacabana__price_sqm": 13_500.0,
            "rio_de_janeiro__copacabana__rent_sqm":  49.0,

            "rio_de_janeiro__botafogo__price_sqm":  12_500.0,
            "rio_de_janeiro__botafogo__rent_sqm":   46.0,

            "rio_de_janeiro__tijuca__price_sqm":    9_000.0,
            "rio_de_janeiro__tijuca__rent_sqm":     34.0,

            "rio_de_janeiro__barra_da_tijuca__price_sqm": 9_800.0,
            "rio_de_janeiro__barra_da_tijuca__rent_sqm":  36.0,

            "rio_de_janeiro__recreio_dos_bandeirantes__price_sqm": 8_200.0,
            "rio_de_janeiro__recreio_dos_bandeirantes__rent_sqm":  30.0,

            "rio_de_janeiro__flamengo__price_sqm":  11_500.0,
            "rio_de_janeiro__flamengo__rent_sqm":   43.0,

            "rio_de_janeiro__leme__price_sqm":      11_000.0,
            "rio_de_janeiro__leme__rent_sqm":       41.0,

            "rio_de_janeiro__catete__price_sqm":    8_000.0,
            "rio_de_janeiro__catete__rent_sqm":     30.0,

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # BELO HORIZONTE — MG
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            "belo_horizonte____price_sqm":          6_000.0,   # média BH
            "belo_horizonte____rent_sqm":           22.0,

            "belo_horizonte__buritis__price_sqm":   7_500.0,   # ← exemplo do usuário
            "belo_horizonte__buritis__rent_sqm":    25.0,

            "belo_horizonte__savassi__price_sqm":   9_500.0,
            "belo_horizonte__savassi__rent_sqm":    35.0,

            "belo_horizonte__lourdes__price_sqm":   9_000.0,
            "belo_horizonte__lourdes__rent_sqm":    33.0,

            "belo_horizonte__funcionarios__price_sqm": 8_500.0,
            "belo_horizonte__funcionarios__rent_sqm":  31.0,

            "belo_horizonte__pampulha__price_sqm":  6_500.0,
            "belo_horizonte__pampulha__rent_sqm":   24.0,

            "belo_horizonte__barreiro__price_sqm":  4_500.0,
            "belo_horizonte__barreiro__rent_sqm":   17.0,

            "belo_horizonte__centro__price_sqm":    4_200.0,
            "belo_horizonte__centro__rent_sqm":     16.0,

            "belo_horizonte__cidade_nova__price_sqm": 5_500.0,
            "belo_horizonte__cidade_nova__rent_sqm":  20.0,

            "belo_horizonte__sion__price_sqm":      8_000.0,
            "belo_horizonte__sion__rent_sqm":       29.0,

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # BRASÍLIA — DF
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            "brasilia____price_sqm":              7_500.0,   # média BSB
            "brasilia____rent_sqm":               29.0,

            "brasilia__asa_norte__price_sqm":     7_200.0,
            "brasilia__asa_norte__rent_sqm":      28.0,

            "brasilia__asa_sul__price_sqm":       8_800.0,
            "brasilia__asa_sul__rent_sqm":        33.0,

            "brasilia__lago_norte__price_sqm":    9_200.0,
            "brasilia__lago_norte__rent_sqm":     36.0,

            "brasilia__lago_sul__price_sqm":      10_500.0,
            "brasilia__lago_sul__rent_sqm":       40.0,

            "brasilia__sudoeste__price_sqm":      9_800.0,
            "brasilia__sudoeste__rent_sqm":       37.0,

            "brasilia__noroeste__price_sqm":      9_000.0,
            "brasilia__noroeste__rent_sqm":       34.0,

            "brasilia__aguas_claras__price_sqm":  6_500.0,
            "brasilia__aguas_claras__rent_sqm":   25.0,

            "brasilia__taguatinga__price_sqm":    4_500.0,
            "brasilia__taguatinga__rent_sqm":     18.0,

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # CURITIBA — PR
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            "curitiba____price_sqm":          6_500.0,
            "curitiba____rent_sqm":           25.0,

            "curitiba__batel__price_sqm":     9_200.0,
            "curitiba__batel__rent_sqm":      35.0,

            "curitiba__agua_verde__price_sqm": 7_800.0,
            "curitiba__agua_verde__rent_sqm":  30.0,

            "curitiba__cabral__price_sqm":    8_500.0,
            "curitiba__cabral__rent_sqm":     32.0,

            "curitiba__portao__price_sqm":    6_200.0,
            "curitiba__portao__rent_sqm":     24.0,

            "curitiba__campo_comprido__price_sqm": 5_800.0,
            "curitiba__campo_comprido__rent_sqm":  22.0,

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # PORTO ALEGRE — RS
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            "porto_alegre____price_sqm":              5_500.0,
            "porto_alegre____rent_sqm":               21.0,

            "porto_alegre__moinhos_de_vento__price_sqm": 8_800.0,
            "porto_alegre__moinhos_de_vento__rent_sqm":  34.0,

            "porto_alegre__bela_vista__price_sqm":    7_200.0,
            "porto_alegre__bela_vista__rent_sqm":     28.0,

            "porto_alegre__petrópolis__price_sqm":    7_500.0,
            "porto_alegre__petropolis__price_sqm":    7_500.0,
            "porto_alegre__petropolis__rent_sqm":     29.0,

            "porto_alegre__menino_deus__price_sqm":   5_800.0,
            "porto_alegre__menino_deus__rent_sqm":    22.0,

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # FLORIANÓPOLIS — SC
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            "florianopolis____price_sqm":         7_200.0,
            "florianopolis____rent_sqm":          29.0,

            "florianopolis__trindade__price_sqm": 7_800.0,
            "florianopolis__trindade__rent_sqm":  31.0,

            "florianopolis__centro__price_sqm":   9_000.0,
            "florianopolis__centro__rent_sqm":    36.0,

            "florianopolis__campeche__price_sqm": 6_500.0,
            "florianopolis__campeche__rent_sqm":  26.0,

            "florianopolis__ingleses__price_sqm": 5_800.0,
            "florianopolis__ingleses__rent_sqm":  23.0,

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # CAMPINAS — SP
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            "campinas____price_sqm":              6_200.0,
            "campinas____rent_sqm":               24.0,

            "campinas__cambuí__price_sqm":        8_500.0,
            "campinas__cambui__price_sqm":        8_500.0,
            "campinas__cambui__rent_sqm":         33.0,

            "campinas__nova_campinas__price_sqm": 7_800.0,
            "campinas__nova_campinas__rent_sqm":  30.0,

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # FORTALEZA — CE
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            "fortaleza____price_sqm":             5_800.0,
            "fortaleza____rent_sqm":              22.0,

            "fortaleza__meireles__price_sqm":     8_200.0,
            "fortaleza__meireles__rent_sqm":      32.0,

            "fortaleza__aldeota__price_sqm":      7_500.0,
            "fortaleza__aldeota__rent_sqm":       29.0,

            "fortaleza__cocó__price_sqm":         7_000.0,
            "fortaleza__coco__price_sqm":         7_000.0,
            "fortaleza__coco__rent_sqm":          27.0,

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # SALVADOR — BA
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            "salvador____price_sqm":              5_500.0,
            "salvador____rent_sqm":               21.0,

            "salvador__itaigara__price_sqm":      7_200.0,
            "salvador__itaigara__rent_sqm":       28.0,

            "salvador__ondina__price_sqm":        7_800.0,
            "salvador__ondina__rent_sqm":         30.0,

            "salvador__barra__price_sqm":         8_500.0,
            "salvador__barra__rent_sqm":          33.0,

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # RECIFE — PE
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            "recife____price_sqm":                5_800.0,
            "recife____rent_sqm":                 22.0,

            "recife__boa_viagem__price_sqm":      7_500.0,
            "recife__boa_viagem__rent_sqm":       29.0,

            "recife__pina__price_sqm":            7_000.0,
            "recife__pina__rent_sqm":             27.0,

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # GOIÂNIA — GO
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            "goiania____price_sqm":               5_200.0,
            "goiania____rent_sqm":               20.0,

            "goiania__setor_bueno__price_sqm":    7_000.0,
            "goiania__setor_bueno__rent_sqm":     27.0,

            "goiania__marista__price_sqm":        7_500.0,
            "goiania__marista__rent_sqm":         29.0,

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # MANAUS — AM
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            "manaus____price_sqm":                4_800.0,
            "manaus____rent_sqm":                19.0,

            "manaus__adrianopolis__price_sqm":    6_500.0,
            "manaus__adrianopolis__rent_sqm":     25.0,

            "manaus__ponta_negra__price_sqm":     6_000.0,
            "manaus__ponta_negra__rent_sqm":      23.0,
        }

    # ── Convenience methods ───────────────────────────────────────────────────

    def get_location_data(
        self,
        city: str,
        neighborhood: Optional[str] = None,
    ) -> Dict:
        """
        Retorna price_sqm e rent_sqm para uma localidade.

        Normaliza city e neighborhood automaticamente (remove acentos,
        lowercases, substitui espaços por underscores). Suporta aliases
        de cidade (ex: "BH" → "belo_horizonte", "SP" → "sao_paulo").

        Estratégia de busca (em ordem):
            1. Cidade + Bairro exatos
            2. Cidade (média) se bairro não encontrado
            3. Brasil (média nacional) se cidade não encontrada

        Args:
            city:         Nome da cidade ou alias (ex: "BH", "São Paulo", "RJ").
            neighborhood: Nome do bairro (ex: "Buritis", "Itaim Bibi"). Optional.

        Returns:
            Dict com:
                price_sqm (float):         Preço médio de venda/m² (R$)
                rent_sqm (float):          Aluguel médio/m² (R$)
                rent_yield_monthly (float): Aluguel/Preço mensal (decimal)
                rent_yield_annual (float):  Aluguel/Preço anual (decimal)
                city_normalized (str):     Slug da cidade usado
                neighborhood_normalized (str): Slug do bairro usado (ou "")
                source (str):              "fipezap_live" | "fipezap_fallback"
                fallback_level (str):      "neighborhood" | "city" | "national"

        Example:
            >>> connector.get_location_data("bh", "buritis")
            {"price_sqm": 7500.0, "rent_sqm": 25.0, "rent_yield_monthly": 0.003333,
             "city_normalized": "belo_horizonte", "neighborhood_normalized": "buritis", ...}

            >>> connector.get_location_data("sp", "itaim bibi")
            {"price_sqm": 17000.0, "rent_sqm": 62.0, ...}
        """
        rates = self.get_rates()
        source = "fipezap_live" if self.is_cache_warm else "fipezap_fallback"

        city_slug = _normalize(city)
        city_slug = _CITY_ALIASES.get(city_slug, city_slug)

        nbhd_slug = _normalize(neighborhood) if neighborhood else ""

        # 1. Buscar cidade + bairro
        price, rent, fallback_level = self._lookup(rates, city_slug, nbhd_slug)

        # Calcular yields
        rent_yield_m = rent / price if price > 0 else 0.0
        rent_yield_a = rent_yield_m * 12

        return {
            "price_sqm":              round(price, 2),
            "rent_sqm":               round(rent, 2),
            "rent_yield_monthly":     round(rent_yield_m, 6),
            "rent_yield_annual":      round(rent_yield_a, 4),
            "city_normalized":        city_slug,
            "neighborhood_normalized": nbhd_slug,
            "source":                 source,
            "fallback_level":         fallback_level,
        }

    def list_cities(self) -> list:
        """Retorna lista de cidades com dados disponíveis."""
        rates = self.get_rates()
        cities = set()
        for key in rates:
            parts = key.split("__")
            if len(parts) >= 2 and parts[0]:
                cities.add(parts[0])
        return sorted(cities)

    def list_neighborhoods(self, city: str) -> list:
        """Retorna lista de bairros com dados para uma cidade."""
        city_slug = _normalize(city)
        city_slug = _CITY_ALIASES.get(city_slug, city_slug)
        rates = self.get_rates()
        neighborhoods = set()
        prefix = f"{city_slug}__"
        for key in rates:
            if key.startswith(prefix) and key.endswith("__price_sqm"):
                parts = key.split("__")
                if len(parts) == 3 and parts[1]:
                    neighborhoods.add(parts[1])
        return sorted(neighborhoods)

    # ── Helpers privados ─────────────────────────────────────────────────────

    @staticmethod
    def _lookup(
        rates: Dict[str, float],
        city_slug: str,
        nbhd_slug: str,
    ) -> tuple:
        """
        Busca price_sqm e rent_sqm no dict de rates com fallback em cascata.

        Returns:
            (price_sqm, rent_sqm, fallback_level)
        """
        # 1. Bairro específico
        if nbhd_slug:
            p_key = f"{city_slug}__{nbhd_slug}__price_sqm"
            r_key = f"{city_slug}__{nbhd_slug}__rent_sqm"
            if p_key in rates and r_key in rates:
                return rates[p_key], rates[r_key], "neighborhood"

        # 2. Média da cidade (bairro vazio = "")
        p_key = f"{city_slug}____price_sqm"
        r_key = f"{city_slug}____rent_sqm"
        if p_key in rates and r_key in rates:
            return rates[p_key], rates[r_key], "city"

        # 3. Fallback nacional (média Brasil ~R$6.000/m², aluguel ~R$23/m²)
        logger.warning(
            "RealEstateDataConnector: cidade '%s' não encontrada — usando média nacional",
            city_slug,
        )
        return 6_000.0, 23.0, "national"

    @staticmethod
    def _parse_fipezap_response(data: dict) -> Dict[str, float]:
        """
        Parseia resposta JSON da API FipeZAP (caso seja disponibilizada).

        Estrutura JSON esperada (hipotética):
            {
                "indices": [
                    {
                        "cidade": "São Paulo",
                        "bairro": "Itaim Bibi",
                        "preco_m2": 17000.0,
                        "aluguel_m2": 62.0
                    },
                    ...
                ]
            }

        Raises:
            ConnectorError: Se o formato for inesperado.
        """
        if not isinstance(data, dict) or "indices" not in data:
            raise ConnectorError(f"FipeZAP: resposta inesperada: {str(data)[:200]}")

        result = {}
        for item in data["indices"]:
            try:
                city = _normalize(item["cidade"])
                nbhd = _normalize(item.get("bairro", ""))
                price = float(item["preco_m2"])
                rent = float(item["aluguel_m2"])
                key_prefix = f"{city}__{nbhd}"
                result[f"{key_prefix}__price_sqm"] = price
                result[f"{key_prefix}__rent_sqm"]  = rent
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("FipeZAP: erro ao parsear item %s: %s", item, exc)
                continue

        if not result:
            raise ConnectorError("FipeZAP: resposta vazia ou sem dados utilizáveis.")

        return result


__all__ = ["RealEstateDataConnector"]
