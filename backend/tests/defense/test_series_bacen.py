"""
As séries de referência do D3 — quem as publica, o que medem, em que unidade.

Este arquivo existe porque o `bacen_credit.py` carregou por meses um comentário
que dizia, em letras maiúsculas, "NUNCA usar 20714/20706 como % a.m. sem
confirmar a unidade com o BACEN primeiro" — e o código usava assim mesmo. Um
aviso não é uma guarda. Um teste é.

O que se descobriu ao finalmente confirmar, em 22/08/2026, contra o catálogo de
dados abertos do BACEN:

    código  usado como                   nome oficial
    ------  --------------------------   -----------------------------------------
    20714   rotativo PF (% a.m.)         Taxa média de juros das operações de
                                         crédito — TOTAL (SFN inteiro), % a.a.
    20715   rotativo máximo PF           Taxa média — Pessoas JURÍDICAS — Total
    20706   cheque especial PF           CONCESSÕES de crédito direcionado PF —
                                         BNDES. Não é taxa: é R$ milhões.
    25433   consignado INSS              Taxa média mensal — TOTAL (SFN inteiro)

A unidade não era o único problema — a identidade também estava errada nas
quatro. A correção troca a família inteira pela "Taxa média MENSAL de juros …
Pessoas físicas", em que a unidade e o público estão escritos no nome da série.

Os testes de catálogo abaixo são a única forma de a próxima pessoa saber que
os códigos continuam certos: eles perguntam ao BACEN, não a mim.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

import pytest

from app.architect.connectors.bacen_credit import (
    TETO_CHEQUE_ESPECIAL_BASE_LEGAL,
    TETO_CHEQUE_ESPECIAL_MENSAL,
    BacenCreditConnector,
)
from app.architect.connectors.base import ConnectorError
from app.architect.connectors.olinda_interest_rate import (
    _MODALIDADES_PF,
    OlindaInterestRateConnector,
)

_TIMEOUT = 30


def _get_json(url: str):
    """Busca JSON ou pula o teste — a rede é do BACEN, não nossa."""
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as resp:
            return json.load(resp)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        pytest.skip(f"BACEN inacessível: {exc}")


def _norm(s: str) -> str:
    return " ".join((s or "").split()).lower()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# O catálogo do BACEN confirma cada série (rede)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture(scope="module")
def titulos_oficiais() -> dict[int, str]:
    """Título publicado pelo BACEN para cada código que o conector usa."""
    out = {}
    for codigo in BacenCreditConnector.SERIES:
        url = BacenCreditConnector.CATALOGO_URL + "?" + urllib.parse.urlencode(
            {"q": f"name:{codigo}-*", "rows": 1}
        )
        resultados = _get_json(url)["result"]["results"]
        out[codigo] = resultados[0]["title"] if resultados else ""
    return out


class TestOCatalogoDoBacenConfirmaCadaSerie:

    @pytest.mark.parametrize("codigo", sorted(BacenCreditConnector.SERIES))
    def test_titulo_oficial_bate_com_o_que_o_codigo_afirma(self, codigo, titulos_oficiais):
        _chave, esperado = BacenCreditConnector.SERIES[codigo]
        assert _norm(titulos_oficiais[codigo]) == _norm(esperado), (
            f"série {codigo}: o BACEN publica «{titulos_oficiais[codigo]}», "
            f"o conector afirma «{esperado}»"
        )

    @pytest.mark.parametrize("codigo", sorted(BacenCreditConnector.SERIES))
    def test_a_unidade_esta_no_nome_da_serie(self, codigo, titulos_oficiais):
        """
        O ponto inteiro da correção: a família "Taxa média MENSAL" declara a
        unidade no próprio título. Com 20714 ("Taxa média de juros … Total",
        em % a.a.) esta asserção falha, que é como o defeito teria aparecido
        no dia um.
        """
        assert "taxa média mensal" in _norm(titulos_oficiais[codigo])

    @pytest.mark.parametrize("codigo", sorted(BacenCreditConnector.SERIES))
    def test_a_serie_e_de_pessoa_fisica(self, codigo, titulos_oficiais):
        """
        20714 e 25433 eram do SFN inteiro (PF+PJ, livres+direcionados) e 20715
        era só de pessoas JURÍDICAS. Comparar a taxa de um consumidor com a
        média que inclui capital de giro e BNDES não mede nada.
        """
        assert "pessoas físicas" in _norm(titulos_oficiais[codigo])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# O valor vivo bate com a modalidade (rede)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture(scope="module")
def taxas_vivas() -> dict[str, float]:
    """
    Taxas vivas do BACEN, ou pula — mesma regra do `_get_json` acima.

    A fixture propagava a exceção, então uma indisponibilidade do BACEN
    (visto: HTTP 502) virava suíte vermelha por algo que não é do projeto.
    O que estes testes verificam é a PLAUSIBILIDADE do valor publicado; sem
    valor publicado não há o que verificar.
    """
    try:
        return BacenCreditConnector(timeout_seconds=_TIMEOUT).fetch_rates()
    except Exception as exc:
        pytest.skip(f"BACEN inacessível: {type(exc).__name__}: {str(exc)[:120]}")


class TestOValorPublicadoHojeEPlausivel:

    def test_cada_modalidade_na_propria_ordem_de_grandeza(self, taxas_vivas):
        BacenCreditConnector._validar_plausibilidade(taxas_vivas)

    def test_rotativo_e_a_modalidade_mais_cara(self, taxas_vivas):
        assert taxas_vivas["rotativo_monthly"] == max(taxas_vivas.values())

    def test_cheque_especial_publicado_respeita_o_teto_legal(self, taxas_vivas):
        """
        A média de uma modalidade com teto de 8% a.m. tem que caber abaixo
        dele com folga. A série antiga devolvia 80% a.m.
        """
        assert taxas_vivas["cheque_especial_monthly"] <= TETO_CHEQUE_ESPECIAL_MENSAL


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# A guarda de plausibilidade (offline)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestAGuardaDePlausibilidade:

    def test_o_fallback_versionado_passa_na_propria_guarda(self):
        """
        Guarda que rejeita o valor para o qual o sistema cai é inútil — e a
        recíproca também vale: se o fallback não passa na guarda, é o fallback
        que está errado. Foi assim que os 10,80% a.m. de cheque especial, acima
        do teto legal, apareceram.
        """
        BacenCreditConnector._validar_plausibilidade(
            BacenCreditConnector().get_fallback_rates()
        )

    def test_a_serie_antiga_e_rejeitada(self):
        """Os números que 20714/20715/20706/25433 devolviam em 20/08/2026."""
        with pytest.raises(ConnectorError):
            BacenCreditConnector._validar_plausibilidade({
                "rotativo_monthly":        0.3344,   # era a média do SFN, em % a.a.
                "cheque_especial_monthly": 0.80,     # era volume de concessões
                "consignado_monthly":      0.0243,
            })

    def test_serie_em_percent_ao_ano_lida_como_ao_mes_e_rejeitada(self):
        """15,13% a.m. é o rotativo; 442% a.a. é o MESMO número na outra unidade."""
        with pytest.raises(ConnectorError):
            BacenCreditConnector._validar_plausibilidade({"rotativo_monthly": 4.4244})

    @pytest.mark.parametrize(
        "rates",
        [
            # consignado acima do cheque especial — cada um dentro da PRÓPRIA
            # faixa, então só a ordem entre produtos denuncia.
            {"consignado_monthly": 0.045, "cheque_especial_monthly": 0.020,
             "rotativo_monthly": 0.150},
            # cheque especial acima do rotativo, idem.
            {"consignado_monthly": 0.018, "cheque_especial_monthly": 0.095,
             "rotativo_monthly": 0.085},
        ],
        ids=["consignado>cheque", "cheque>rotativo"],
    )
    def test_ordem_entre_produtos_pega_o_que_a_faixa_deixa_passar(self, rates):
        """
        Cada valor, isolado, cabe na faixa da sua própria modalidade — a
        checagem de faixa aprova os três. O que não pode passar é a ordem:
        consignado tem desconto em folha (menor risco) e não pode custar mais
        que cheque especial, que por sua vez não pode custar mais que o
        rotativo, que é a dívida sem garantia mais cara do mercado.

        Sem esta segunda checagem, uma troca de códigos entre modalidades
        entraria em produção sem sintoma.
        """
        for chave, valor in rates.items():
            minimo, maximo = BacenCreditConnector._FAIXAS_PLAUSIVEIS[chave]
            assert minimo <= valor <= maximo, f"{chave} nem cabe na faixa: cenário inválido"

        with pytest.raises(ConnectorError, match="trocadas entre modalidades"):
            BacenCreditConnector._validar_plausibilidade(rates)

    def test_valores_corretos_passam(self):
        BacenCreditConnector._validar_plausibilidade({
            "rotativo_monthly":        0.1513,
            "parcelado_monthly":       0.0932,
            "cheque_especial_monthly": 0.0756,
            "pessoal_monthly":         0.0708,
            "consignado_monthly":      0.0183,
        })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# O teto legal do cheque especial (offline)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 1,08^(31/30) − 1: o teto de 8% a.m. convertido para um mês de 31 dias. É
# onde os grandes bancos se aglomeram no Olinda de 03/08/2026 — Banco do
# Brasil 8,24, Santander 8,27, Inter 8,26, C6 8,27, BTG 8,21. Não é "perto do
# teto" por acaso: é o teto.
_TAXA_NO_TETO = 0.0828


class TestTetoLegalDoChequeEspecial:

    def test_o_teto_e_oito_por_cento_ao_mes(self):
        assert TETO_CHEQUE_ESPECIAL_MENSAL == 0.08
        assert "4.765/2019" in TETO_CHEQUE_ESPECIAL_BASE_LEGAL

    def test_o_fallback_do_projeto_nao_pode_estar_acima_do_teto(self):
        """
        A pendência que ficou aberta na rodada anterior. O fallback era 10,80%
        a.m. — 35% acima do que a norma do CMN permite cobrar. Usar isso como
        "média de mercado" é dizer ao usuário que o teto legal é barato.
        """
        cheque = BacenCreditConnector().get_fallback_rates()["cheque_especial_monthly"]
        assert cheque <= TETO_CHEQUE_ESPECIAL_MENSAL, (
            f"fallback de {cheque:.2%} a.m. está acima do teto legal de "
            f"{TETO_CHEQUE_ESPECIAL_MENSAL:.0%} a.m."
        )

    def test_a_faixa_de_plausibilidade_conhece_o_teto(self):
        _min, maximo = BacenCreditConnector._FAIXAS_PLAUSIVEIS["cheque_especial_monthly"]
        assert maximo <= 1.5 * TETO_CHEQUE_ESPECIAL_MENSAL, (
            "a média de uma modalidade com teto legal não pode ter faixa aberta "
            "muito acima do teto — foi assim que 80% a.m. passou"
        )

    def test_quem_paga_o_teto_legal_deixou_de_ser_invisivel(self):
        """
        O custo real de errar a referência, em termos do usuário.

        Com 10,80% a.m. de referência, quem paga exatamente o teto legal
        (8,28% a.m., que é o que Banco do Brasil, Santander, Inter, C6 e BTG
        cobram) sai com múltiplo 0,77× — abaixo da média, nenhum achado. O
        D3 ficava desligado justamente para a população que paga o máximo que
        a lei permite.
        """
        from app.defense.services.abusive_interest_detector import _classify

        referencia_errada = 0.1080
        referencia_certa = BacenCreditConnector().get_fallback_rates()[
            "cheque_especial_monthly"
        ]

        assert _classify(_TAXA_NO_TETO, referencia_errada) is None
        assert _classify(_TAXA_NO_TETO, referencia_certa) is not None

    def test_o_dossie_do_D3_cita_o_teto_no_cheque_especial(self):
        from app.defense.services.abusive_interest_detector import _LEGAL_BASIS

        assert "4.765/2019" in _LEGAL_BASIS
        assert "8% ao mês" in _LEGAL_BASIS


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Olinda: as modalidades de crédito voltaram a existir
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture(scope="module")
def olinda() -> OlindaInterestRateConnector:
    return OlindaInterestRateConnector(timeout_seconds=_TIMEOUT)


class TestOlindaTrazCredito:

    def test_a_FONTE_devolve_rotativo_e_cheque_especial(self, olinda):
        """
        O conector consultava `TaxasJurosMensalPorMes`, que só publica
        financiamento imobiliário. `get_market_averages()` devolvia
        {"imovel": …} — e como não era vazio, ninguém percebia. O D6 lia
        `market.get("rotativo")` → None → `continue`, e nunca gerava achado
        de portabilidade para nenhuma modalidade de crédito.

        A asserção é sobre `fetch_rates()`, não sobre `get_market_averages()`:
        a segunda passa pelo `get_rates()` do BaseConnector, que substitui a
        fonte morta pelo fallback versionado e devolve um dicionário completo.
        Testar a fonte pela porta que tem fallback é não testar a fonte — é o
        mesmo erro que deixou este defeito vivo.
        """
        vivas = olinda.fetch_rates()
        for chave in ("rotativo", "cheque_especial", "consignado", "pessoal"):
            assert chave in vivas, f"{chave} ausente na FONTE: {sorted(vivas)}"
            assert vivas[chave] > 0

    def test_a_media_e_de_um_corte_transversal_e_nao_temporal(self, olinda):
        """
        A ConsultaUnificada devolve várias semanas de apuração de uma vez. Sem
        cortar pelo período mais recente, a mesma IF entra repetida e a "média
        entre bancos" vira média temporal disfarçada.
        """
        linhas = olinda._fetch_diario()
        assert len({r["InicioPeriodo"] for r in linhas}) == 1
        rotativo = [r for r in linhas if r["codigoModalidade"] == "204101"
                    and r["codigoSegmento"] == "1"]
        nomes = [r["InstituicaoFinanceira"] for r in rotativo]
        assert len(nomes) == len(set(nomes)), "IF repetida no mesmo corte"

    def test_os_codigos_de_modalidade_existem_no_catalogo_do_bacen(self, olinda):
        url = (
            "https://olinda.bcb.gov.br/olinda/servico/taxaJuros/versao/v2/odata/"
            "ParametrosConsulta?$format=json&$top=500"
        )
        catalogo = {
            (r["codigoSegmento"], r["codigoModalidade"]): r["modalidade"]
            for r in _get_json(url)["value"]
        }
        for chave, codigo in _MODALIDADES_PF.items():
            assert ("1", codigo) in catalogo, (
                f"{chave}: código {codigo} não existe como modalidade PF"
            )

    def test_a_taxa_maxima_vem_da_distribuicao_real(self, olinda):
        """
        O SGS não publica máximo nenhum. `rotativo_max` vinha de 20715, que é a
        média de pessoas JURÍDICAS — e era essa a razão de o "máximo" (20,80)
        sair abaixo da "média" (33,44).
        """
        dist = olinda.get_rate_distribution("rotativo")
        assert dist is not None
        assert dist["max"] >= dist["mediana"] >= dist["min"]
        assert dist["n_ifs"] >= 10

    def test_a_referencia_do_D3_tem_maximo_acima_da_media(self):
        from app.defense.services.abusive_interest_detector import AbusiveInterestDetector

        m = AbusiveInterestDetector()._get_market_rates()
        assert m["rotativo_max_monthly"] >= m["rotativo_monthly"]


class TestOlindaSemCampoFantasma:
    """
    `get_best_rate` filtrava por `NumeroDeContratos >= 100`. Esse campo não
    existe na taxaJuros v2 — `int(None or 0)` = 0, sempre menor que 100. Todo
    candidato era descartado e a função devolvia None em toda chamada, o que
    fazia o D6 cair em `best_rate or market_avg` e prometer portabilidade para
    a própria média.
    """

    _LINHAS = [
        {"InicioPeriodo": "2026-08-03", "codigoSegmento": "1",
         "codigoModalidade": "221101", "InstituicaoFinanceira": "BCO A",
         "TaxaJurosAoMes": 0.00, "TaxaJurosAoAno": 0.0},
        *[
            {"InicioPeriodo": "2026-08-03", "codigoSegmento": "1",
             "codigoModalidade": "221101", "InstituicaoFinanceira": f"BCO {i}",
             "TaxaJurosAoMes": float(taxa), "TaxaJurosAoAno": 0.0}
            for i, taxa in enumerate([1.9, 2.4, 3.1, 4.0, 5.2, 6.8, 9.0, 12.0, 19.0])
        ],
    ]

    @pytest.fixture
    def conector(self, monkeypatch):
        linhas = self._LINHAS
        monkeypatch.setattr(
            OlindaInterestRateConnector, "_fetch_diario", lambda self: linhas
        )
        return OlindaInterestRateConnector()

    def test_best_rate_devolve_taxa_e_nao_None(self, conector):
        assert conector.get_best_rate("pessoal") is not None

    def test_best_rate_ignora_a_taxa_de_zero(self, conector):
        """
        0,00% a.m. existe na apuração (carteira residual, operação subsidiada)
        e não é oferta contratável. Prometer portabilidade para ela seria
        enganoso.
        """
        assert conector.get_best_rate("pessoal") > 0

    def test_best_rate_e_menor_que_a_mediana(self, conector):
        dist = conector.get_rate_distribution("pessoal")
        assert conector.get_best_rate("pessoal") < dist["mediana"]

    def test_modalidade_desconhecida_nao_explode(self, conector):
        assert conector.get_best_rate("cripto") is None
        assert conector.get_rate_distribution("cripto") is None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Uma tabela só para o mesmo número
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestAReferenciaDoD6:
    """
    O D6 lê as médias no vocabulário do Olinda (`rotativo`, `pessoal`), não no
    do SGS (`rotativo_monthly`).

    Duas coisas erradas apontando para o mesmo lado, e é preciso ser exato
    sobre qual delas doía:

    • A que RODAVA: com o Olinda no endpoint errado, `get_market_averages()`
      devolvia só {"imovel": …}. O D6 fazia `market.get(modality)` → None →
      `continue`. Nenhum achado de portabilidade, para nenhum empréstimo.
    • A que estava ARMADA e não chegou a rodar: `pessoal` valia 3,20% a.m. na
      tabela de fallback do Olinda e 3,20% de novo, hardcoded, no segundo
      nível do próprio D6. A média real é 7,08% a.m. (SGS 25464). Com o limiar
      de 1,20×, essa referência acusaria a partir de 3,84% a.m. — abaixo da
      própria média de mercado. Assim que a primeira fosse consertada sem a
      segunda, o detector sairia de "não acha nada" para "acusa quem paga
      barato".
    """

    @pytest.fixture
    def referencia(self, monkeypatch):
        """
        Rede desligada de propósito: o que se testa aqui é o caminho que roda
        quando as APIs do BACEN estão fora — que era justamente onde estavam os
        3,20%.
        """
        from app.architect.connectors.bacen_credit import BacenCreditConnector
        from app.architect.connectors.olinda_interest_rate import (
            OlindaInterestRateConnector,
        )
        from app.defense.services.portability_detector import PortabilityDetector

        for classe in (BacenCreditConnector, OlindaInterestRateConnector):
            monkeypatch.setattr(
                classe, "fetch_rates",
                lambda self: (_ for _ in ()).throw(RuntimeError("offline")),
            )
        monkeypatch.setattr(
            OlindaInterestRateConnector, "get_rate_distribution", lambda self, m: None
        )
        return PortabilityDetector._get_market_rates()

    def test_traduz_o_vocabulario_do_sgs_para_o_do_D6(self, referencia):
        for chave in ("rotativo", "cheque_especial", "consignado", "pessoal"):
            assert chave in referencia, f"{chave} ausente: {sorted(referencia)}"

    def test_quem_paga_abaixo_do_mercado_nao_recebe_ordem_de_portabilidade(
        self, referencia
    ):
        """
        5% a.m. em crédito pessoal está ABAIXO da média (7,08% a.m.) — não pode
        virar recomendação de portabilidade. Com a referência de 3,20% que
        estava armada nas duas tabelas, viraria: 5 / 3,20 = 1,56×, acima do
        limiar de 1,20×.
        """
        from app.defense.services.portability_detector import _THRESHOLD_INSTITUTION

        assert 0.05 / referencia["pessoal"] < _THRESHOLD_INSTITUTION
        assert 0.05 / 0.0320 >= _THRESHOLD_INSTITUTION  # a referência armada

    def test_a_referencia_de_pessoal_e_a_do_bacen(self, referencia):
        """
        A asserção que pega as duas tabelas de 3,20%: o valor tem que estar na
        ordem de grandeza do que o BACEN publica para crédito pessoal não
        consignado, não na metade dela.
        """
        assert referencia["pessoal"] == pytest.approx(0.0708, abs=0.02)


class TestAFerramentaDoAgenteNaoTemTabelaPropria:
    """
    A tool do agente mantinha a própria tabela de fallback. Ela envelheceu
    separada: o detector já tinha sido corrigido e a tool continuava
    imprimindo "Cheque Especial (média mercado): 10.80% a.m." — acima do teto
    legal, na tela do usuário.
    """

    def test_a_tool_le_a_referencia_do_detector(self, monkeypatch):
        from app.agent.tools import detect_abusive_interest as tool
        from app.defense.services.abusive_interest_detector import AbusiveInterestDetector

        monkeypatch.setattr(
            AbusiveInterestDetector,
            "_get_market_rates",
            staticmethod(lambda: {
                "rotativo_monthly": 0.1111,
                "rotativo_max_monthly": 0.2222,
                "cheque_especial_monthly": 0.0333,
            }),
        )
        r = tool._get_market_rates()
        assert r["rotativo_pct"] == pytest.approx(11.11)
        assert r["cheque_pct"] == pytest.approx(3.33)

    def test_a_tool_mostra_o_teto_legal(self, monkeypatch):
        from app.agent.tools import detect_abusive_interest as tool

        assert tool._get_market_rates()["cheque_teto_pct"] == pytest.approx(8.0)
