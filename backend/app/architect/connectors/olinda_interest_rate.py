"""
app/architect/connectors/olinda_interest_rate.py — Conector Olinda taxaJuros v2

Taxas de juros POR INSTITUIÇÃO FINANCEIRA. É o que o SGS não dá: o SGS publica
a média da população, o Olinda publica a linha de cada IF — necessário para o
D3 ("o SEU banco cobra X, o mercado cobra Y") e para o D6 (portabilidade).

Vantagem estrutural sobre o SGS: os campos se chamam `TaxaJurosAoMes` e
`TaxaJurosAoAno`. Não existe dúvida de unidade — ela está no nome do campo.

Endpoints (v2):
  ConsultaUnificada          — todas as modalidades diárias, com codigoModalidade
                               e codigoSegmento resolvidos. É o que este conector usa.
  TaxasJurosMensalPorMes     — só as modalidades de tipo "M" (financiamento
                               imobiliário). Não serve para rotativo/cheque especial.
  ParametrosConsulta         — catálogo de (segmento, modalidade, tipo).

O conector chamava `TaxasJurosMensalPorMes` para TODAS as modalidades. Esse
endpoint só devolve financiamento imobiliário — verificado em 22/08/2026:
40 linhas em 2026-06, todas "Financiamento imobiliário". Consequências que
ninguém via, porque a função devolvia um dicionário não-vazio e portanto
"funcionava":

  • `get_market_averages()` devolvia só {"imovel": …}. O D6 lia
    `market.get("rotativo")` → None → `continue`: o detector de portabilidade
    NUNCA gerava achado para rotativo, cheque especial, consignado ou pessoal.
  • o D3 tentava o Olinda primeiro, recebia esse dicionário, considerava
    sucesso e nunca chegava ao BACEN.

E `get_best_rate()` filtrava por `NumeroDeContratos >= min_contracts`. Esse
campo não existe na v2 (os campos são InicioPeriodo, FimPeriodo,
codigoSegmento, Segmento, codigoModalidade, Modalidade, Posicao,
InstituicaoFinanceira, TaxaJurosAoMes, TaxaJurosAoAno, cnpj8). `int(None or 0)`
= 0, sempre menor que 100 → todo candidato era descartado e a função devolvia
None em toda chamada.

A seleção por nome de modalidade também saiu: comparar substrings de
"Cartão de crédito - rotativo total - Prefixado" é frágil e foi o que permitiu
o alias "Conta garantida" (produto de PJ) entrar em `cheque_especial`. Agora a
chave é `codigoModalidade` + `codigoSegmento`, que são códigos estáveis do
BACEN.

Cache: 24h.
Sem autenticação necessária.
"""

from __future__ import annotations

import logging
import statistics
from datetime import date
from typing import Optional

import httpx

from app.architect.connectors.base import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)

_BASE = "https://olinda.bcb.gov.br/olinda/servico/taxaJuros/versao/v2/odata"

# Segmento 1 = Pessoa Física, 2 = Pessoa Jurídica (ParametrosConsulta).
_SEGMENTO_PF = "1"

# chave interna Nexa → codigoModalidade do BACEN (segmento PF, apuração diária).
# Códigos conferidos contra ParametrosConsulta em 22/08/2026.
_MODALIDADES_PF = {
    "rotativo":        "204101",   # Cartão de crédito - rotativo total
    "parcelado":       "215101",   # Cartão de crédito - parcelado
    "cheque_especial": "216101",   # Cheque especial
    "consignado":      "218101",   # Crédito pessoal consignado INSS
    "pessoal":         "221101",   # Crédito pessoal não consignado
    "veiculo":         "401101",   # Aquisição de veículos
}

# Financiamento imobiliário é apurado por MÊS (tipoModalidade "M") e por isso
# não aparece na ConsultaUnificada diária — vem do endpoint mensal, que é o
# único que o serve (códigos 903101/903201/903203 e 905*).
_NOME_IMOVEL = "financiamento imobiliário"

# A ConsultaUnificada não aceita $filter (a v2 devolve 400 em qualquer
# expressão). Vem ordenada por (modalidade, segmento) com o período mais
# recente à frente de cada grupo: em 22/08/2026 as 801 primeiras linhas eram
# exatamente o período 2026-08-03 inteiro. 1.500 dá folga de quase 2×, e ainda
# assim o payload com $select fica em ~300 KB.
_TOP_DIARIO = 1500
_CAMPOS = (
    "InicioPeriodo,codigoSegmento,codigoModalidade,Modalidade,"
    "InstituicaoFinanceira,cnpj8,TaxaJurosAoMes,TaxaJurosAoAno"
)

# Percentil usado como "melhor taxa praticada". Não é o mínimo: em 03/08/2026 o
# menor rotativo PF publicado era 0,20% a.m. e o menor crédito pessoal era
# 0,00% — números que existem na apuração (carteira residual, operação
# subsidiada) mas não são oferta que o usuário consegue contratar. Prometer
# portabilidade para uma taxa dessas seria enganoso.
_PERCENTIL_MELHOR_TAXA = 10

# Fallback: SGS jun/2026 (BacenCreditConnector) em % a.m.
_FALLBACK_MARKET = {
    "rotativo":        15.13,
    "parcelado":        9.32,
    "cheque_especial":  7.56,
    "pessoal":          7.08,
    "consignado":       1.83,
}


class OlindaInterestRateConnector(BaseConnector):
    """
    Conector para taxaJuros v2 do Olinda BACEN.

    Uso:
        c = OlindaInterestRateConnector()
        rates = c.get_market_averages()                       # % a.m. decimal
        rate  = c.get_rate_by_institution("Itaú", "rotativo")
        best  = c.get_best_rate("pessoal")
        dist  = c.get_rate_distribution("rotativo")           # min/p10/mediana/max
    """

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("cache_ttl_seconds", 86400)  # 24h
        super().__init__(**kwargs)

    def fetch_rates(self) -> dict:
        """Interface BaseConnector — médias de mercado por modalidade (decimal a.m.)."""
        rows = self._fetch_diario()
        medias = {}
        for chave in _MODALIDADES_PF:
            taxas = self._taxas(rows, chave)
            if taxas:
                medias[chave] = round(statistics.fmean(taxas) / 100, 6)
        if not medias:
            raise ConnectorError("Olinda taxaJuros: nenhuma modalidade PF no retorno")
        # Imobiliário vem de outro endpoint; sua ausência não invalida o resto.
        medias.update(self.get_imovel_averages())
        return medias

    def get_fallback_rates(self) -> dict:
        return {k: v / 100 for k, v in _FALLBACK_MARKET.items()}

    # ── API pública ───────────────────────────────────────────────────

    def get_market_averages(self, mes: Optional[str] = None) -> dict[str, float]:
        """
        Taxa média de mercado por modalidade em decimal (% a.m.), como média
        simples entre as IFs que publicaram no período.

        Atenção ao usar isto como "a taxa média BACEN" de um documento: a
        média que o Tema 27/STJ referencia é a da série SGS, ponderada pelo
        volume das concessões. Esta é a média simples entre instituições — o
        Olinda não publica volume. Para o benchmark citado juridicamente, use
        o `BacenCreditConnector`; use esta aqui para comparar bancos entre si.
        """
        try:
            return self.get_rates()
        except Exception as exc:  # pragma: no cover — get_rates já trata
            logger.warning("[OlindaIR] get_market_averages fallback: %s", exc)
            return self.get_fallback_rates()

    def get_rate_by_institution(
        self,
        institution_name: str,
        modality: str,
        mes: Optional[str] = None,
    ) -> Optional[float]:
        """
        Taxa em % a.m. (decimal) de uma IF específica numa modalidade.
        Retorna None se a IF não publicou nessa modalidade.
        """
        try:
            rows = self._fetch_diario()
            taxas = [
                float(r["TaxaJurosAoMes"])
                for r in self._linhas(rows, modality)
                if self._name_match(r.get("InstituicaoFinanceira", ""), institution_name)
                and r.get("TaxaJurosAoMes") is not None
            ]
            return round(statistics.fmean(taxas) / 100, 6) if taxas else None
        except Exception as exc:
            logger.debug("[OlindaIR] get_rate_by_institution: %s", exc)
            return None

    def get_best_rate(self, modality: str, mes: Optional[str] = None) -> Optional[float]:
        """
        Melhor taxa realisticamente praticada na modalidade (% a.m. decimal).

        É o percentil 10 das taxas publicadas, não o mínimo — ver
        `_PERCENTIL_MELHOR_TAXA`. Usada pelo D6 como alvo de portabilidade, e
        portanto precisa ser uma taxa que o usuário consiga contratar.
        """
        try:
            taxas = sorted(t for t in self._taxas(self._fetch_diario(), modality) if t > 0)
            if not taxas:
                return None
            idx = max(0, round((_PERCENTIL_MELHOR_TAXA / 100) * (len(taxas) - 1)))
            return round(taxas[idx] / 100, 6)
        except Exception as exc:
            logger.debug("[OlindaIR] get_best_rate: %s", exc)
            return None

    def get_rate_distribution(self, modality: str) -> Optional[dict]:
        """
        Distribuição das taxas entre IFs na modalidade, em decimal a.m.

        É daqui que sai a "taxa máxima de mercado". O SGS não publica máximo
        nenhum — a série que o projeto usava como `rotativo_max` era a média
        de PESSOAS JURÍDICAS, o que explicava o absurdo de o "máximo" sair
        abaixo da "média".
        """
        try:
            taxas = sorted(t for t in self._taxas(self._fetch_diario(), modality) if t > 0)
            if not taxas:
                return None
            idx = max(0, round((_PERCENTIL_MELHOR_TAXA / 100) * (len(taxas) - 1)))
            return {
                "min":     round(taxas[0] / 100, 6),
                "p10":     round(taxas[idx] / 100, 6),
                "mediana": round(statistics.median(taxas) / 100, 6),
                "media":   round(statistics.fmean(taxas) / 100, 6),
                "max":     round(taxas[-1] / 100, 6),
                "n_ifs":   len(taxas),
            }
        except Exception as exc:
            logger.debug("[OlindaIR] get_rate_distribution: %s", exc)
            return None

    def get_institution_ranking(
        self,
        modality: str,
        mes: Optional[str] = None,
    ) -> list[dict]:
        """
        Ranking de IFs por taxa (menor → maior) numa modalidade.
        Usado pelo D6 para sugerir banco alvo de portabilidade.
        """
        try:
            resultado = []
            for r in self._linhas(self._fetch_diario(), modality):
                if r.get("TaxaJurosAoMes") is None:
                    continue
                resultado.append({
                    "institution": r.get("InstituicaoFinanceira", ""),
                    "cnpj8":       r.get("cnpj8", ""),
                    "rate_month":  round(float(r["TaxaJurosAoMes"]) / 100, 6),
                    "rate_year":   round(float(r.get("TaxaJurosAoAno") or 0) / 100, 6),
                })
            resultado.sort(key=lambda x: x["rate_month"])
            return resultado
        except Exception as exc:
            logger.debug("[OlindaIR] get_institution_ranking: %s", exc)
            return []

    def get_imovel_averages(self, mes: Optional[str] = None) -> dict[str, float]:
        """
        Financiamento imobiliário PF (decimal a.m.), do endpoint mensal — a
        única modalidade que a apuração diária não cobre.
        """
        # A apuração mensal sai com ~45 dias de atraso: em 22/08/2026 o mês
        # mais recente publicado era 2026-06. Pedir só o mês corrente devolvia
        # vazio quase sempre — e vazio aqui é `imovel` ausente, que no D6 vira
        # `continue` e nenhum achado de portabilidade imobiliária.
        candidatos = [mes] if mes else self._meses_recentes(3)
        rows: list[dict] = []
        for candidato in candidatos:
            try:
                rows = self._fetch_mensal(candidato)
                break
            except Exception as exc:
                logger.debug("[OlindaIR] mensal %s: %s", candidato, exc)
        if not rows:
            return {}
        # O endpoint mensal não devolve codigoModalidade (a entidade
        # TaxaJurosMensal não tem o campo), então aqui a seleção é por nome
        # mesmo — mas é seguro: esse endpoint só serve imobiliário.
        taxas = [
            float(r["TaxaJurosAoMes"])
            for r in rows
            if r.get("TaxaJurosAoMes") is not None
            and _NOME_IMOVEL in (r.get("Modalidade") or "").lower()
        ]
        return {"imovel": round(statistics.fmean(taxas) / 100, 6)} if taxas else {}

    # ── Internos ──────────────────────────────────────────────────────

    @staticmethod
    def _linhas(rows: list[dict], modality: str) -> list[dict]:
        """Linhas PF da modalidade, selecionadas por código — não por nome."""
        codigo = _MODALIDADES_PF.get(modality)
        if codigo is None:
            return []
        return [
            r for r in rows
            if r.get("codigoModalidade") == codigo
            and r.get("codigoSegmento") == _SEGMENTO_PF
        ]

    @classmethod
    def _taxas(cls, rows: list[dict], modality: str) -> list[float]:
        return [
            float(r["TaxaJurosAoMes"])
            for r in cls._linhas(rows, modality)
            if r.get("TaxaJurosAoMes") is not None
        ]

    def _fetch_diario(self) -> list[dict]:
        """
        ConsultaUnificada, apenas o período de apuração mais recente.

        O corte pelo período máximo presente na resposta é obrigatório: sem
        ele, a mesma IF entra várias vezes (uma por semana de apuração) e a
        média vira média temporal disfarçada de corte transversal.
        """
        cache_key = "olinda_diario"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        params = {"$format": "json", "$top": _TOP_DIARIO, "$select": _CAMPOS}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(f"{_BASE}/ConsultaUnificada", params=params)
            resp.raise_for_status()
            rows = resp.json().get("value", [])

        if not rows:
            raise ConnectorError("Olinda taxaJuros: ConsultaUnificada sem dados")

        ultimo = max(r["InicioPeriodo"] for r in rows if r.get("InicioPeriodo"))
        recentes = [r for r in rows if r.get("InicioPeriodo") == ultimo]
        logger.info(
            "[OlindaIR] %d IFs no período %s (de %d linhas)",
            len(recentes), ultimo, len(rows),
        )
        self._set_cache(cache_key, recentes)
        return recentes

    def _fetch_mensal(self, mes: str) -> list[dict]:
        url = (
            f"{_BASE}/TaxasJurosMensalPorMes"
            f"?$filter=anoMes eq '{mes}'&$format=json&$top=5000"
        )
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(url)
            resp.raise_for_status()
            rows = resp.json().get("value", [])
        if not rows:
            raise ConnectorError(f"Olinda taxaJuros: sem dados mensais para {mes}")
        return rows

    @staticmethod
    def _meses_recentes(quantos: int) -> list[str]:
        """Mês corrente e anteriores, do mais novo para o mais antigo."""
        d = date.today()
        y, m = d.year, d.month
        saida = []
        for _ in range(quantos):
            saida.append(f"{y}-{m:02d}")
            m -= 1
            if m == 0:
                y, m = y - 1, 12
        return saida

    @classmethod
    def _current_month(cls) -> str:
        return cls._meses_recentes(1)[0]

    @staticmethod
    def _name_match(olinda_name: str, search: str) -> bool:
        return search.lower() in olinda_name.lower()


__all__ = ["OlindaInterestRateConnector"]
