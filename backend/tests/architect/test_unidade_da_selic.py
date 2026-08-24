"""
A unidade da SELIC na fonte secundária.

Origem: um teste da suíte falhava de vez em quando —
`test_o_ponto_de_virada_do_desconto_e_exato`, no conselho de compra. O relatório
carregava a prova: `cdi_rate_used=0.0078`. Uma SELIC de 0,78% ao ano.

O que acontecia: a série primária (SGS 432) dava `ReadTimeout`, a cadeia de
fallback do `BaseConnector` seguia para a fonte secundária, e a fonte secundária
era a série 4390 — comentada no código como "SELIC over anualizada (% a.a.)".
A 4390 é "Selic acumulada no mês", em % AO MÊS. Consulta de 24/08/2026:

    série   nome                                          valor    unidade
    -----   -------------------------------------------   ------   -------
    432     Taxa SELIC meta                                14.00    % a.a.
    4189    Selic acumulada no mês ANUALIZADA base 252     13.95    % a.a.
    4390    Selic acumulada no mês                          0.78    % a.m.
    11/12   Selic/CDI diária                             0.05166   % a.d.

O `/100` transformava 0,78 em 0,0078 e entregava isso como taxa anual, dezoito
vezes menor que a real. Com o dinheiro praticamente sem valor no tempo, o VPL
de adiar pagamento colapsa: no conselho de compra o ganho de parcelar caía de
R$ 213 para cerca de R$ 10 e a recomendação virava de "parcele" para "pague à
vista". O mesmo número alimenta o Architect (desconto de VPL), o comparador de
Tesouro, poupança vs CDI e o motor de oportunidades.

A cadeia de fallback protegia contra a fonte ficar FORA DO AR. Não protegia
contra a fonte responder com o número errado.

Os testes que existiam alimentavam a série 4390 com "14.75" e "10.50" — valores
que a 4390 nunca produziu — e conferiam só a divisão por 100. Verdes para
sempre, defeito intacto.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.architect.connectors.bacen import BacenConnector
from app.architect.connectors.base import ConnectorError

_TIMEOUT = 30
_SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{s}/dados/ultimos/1?formato=json"


def _valor_sgs(serie: int) -> float:
    """Último valor da série ou pula o teste — a rede é do BACEN, não nossa."""
    try:
        with urllib.request.urlopen(_SGS.format(s=serie), timeout=_TIMEOUT) as resp:
            dados = json.load(resp)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        pytest.skip(f"BACEN inacessível: {exc}")
    return float(dados[0]["valor"])


def _conector() -> BacenConnector:
    c = BacenConnector()
    c.invalidate_cache()
    return c


def _resposta(valor: str) -> MagicMock:
    m = MagicMock()
    m.json.return_value = [{"data": "01/08/2026", "valor": valor}]
    m.raise_for_status = MagicMock()
    return m


# ── 1. A série secundária mede a mesma coisa que a primária ─────────────────

class TestUnidadeDaSerieSecundaria:
    """
    Perguntar ao BACEN, não a mim. É a única forma de a próxima pessoa saber
    que o código continua certo.
    """

    def test_a_secundaria_e_a_4189(self):
        assert BacenConnector._SELIC_EFETIVA_SERIES == 4189

    def test_a_secundaria_concorda_com_a_primaria_ao_vivo(self):
        """
        4189 é a meta realizada e anualizada: acompanha a 432 de perto. A 4390
        estaria uma ordem de grandeza abaixo.
        """
        meta = _valor_sgs(BacenConnector._SELIC_META_SERIES)
        efetiva = _valor_sgs(BacenConnector._SELIC_EFETIVA_SERIES)
        assert abs(meta - efetiva) < 3.0, (
            f"432={meta} e {BacenConnector._SELIC_EFETIVA_SERIES}={efetiva} — "
            f"não medem a mesma coisa na mesma unidade"
        )

    def test_a_4390_nao_serve_e_a_banda_prova(self):
        """
        Trava a razão da troca: a 4390 lida como decimal anual é recusada pela
        guarda. Se alguém devolver a 4390 para cá, este teste cai.
        """
        mensal = _valor_sgs(4390)
        with pytest.raises(ConnectorError):
            BacenConnector._validar_selic_anual(mensal / 100, origem="SGS 4390")

    def test_o_valor_vivo_da_secundaria_passa_pela_guarda(self):
        efetiva = _valor_sgs(BacenConnector._SELIC_EFETIVA_SERIES)
        assert BacenConnector._validar_selic_anual(efetiva / 100, origem="teste")


# ── 2. A banda de plausibilidade ────────────────────────────────────────────

class TestBandaDePlausibilidade:

    @pytest.mark.parametrize("taxa", [0.02, 0.05, 0.1075, 0.1475, 0.45, 0.50])
    def test_selic_real_passa(self, taxa):
        assert BacenConnector._validar_selic_anual(taxa, origem="teste") == taxa

    @pytest.mark.parametrize("taxa,unidade", [
        (0.0078, "4390 em ago/26 (% a.m.)"),
        (0.0122, "4390 em jul/26 (% a.m.)"),
        (0.0005166, "série 11/12 (% a.d.)"),
        (0.0, "resposta zerada"),
        (14.0, "esqueceram de dividir por 100"),
        (-0.05, "negativo"),
    ])
    def test_o_que_nao_e_selic_e_recusado(self, taxa, unidade):
        with pytest.raises(ConnectorError, match="implausível"):
            BacenConnector._validar_selic_anual(taxa, origem=unidade)

    def test_a_fronteira_do_mensal_e_onde_o_comentario_diz(self):
        """
        O piso de 2% pega uma leitura mensal enquanto a SELIC anual estiver
        abaixo de ~26,8% a.a. — e o comentário no código afirma isso. Se o piso
        mudar sem o comentário, este teste cai.
        """
        anual_de_virada = 1.02 ** 12 - 1
        assert anual_de_virada == pytest.approx(0.2682, abs=1e-4)

        # Logo abaixo da virada: o mensal é recusado.
        mensal = (1 + anual_de_virada * 0.99) ** (1 / 12) - 1
        with pytest.raises(ConnectorError):
            BacenConnector._validar_selic_anual(mensal, origem="mensal")

        # Acima dela o mensal entra na banda — limitação declarada, não bug.
        mensal_alto = (1 + 0.35) ** (1 / 12) - 1
        assert BacenConnector._validar_selic_anual(mensal_alto, origem="mensal")


# ── 3. A cadeia inteira, sob resposta errada (não sob ausência) ─────────────

class TestCadeiaComRespostaErrada:
    """
    O nível 3 existia para quando ninguém responde. O caso que quebrava era
    outro: alguém responde, com o número errado.
    """

    def test_secundaria_com_valor_mensal_cai_para_o_hardcoded(self):
        c = _conector()
        with patch("httpx.Client") as cls:
            cls.return_value.__enter__.return_value.get.side_effect = [
                httpx.ConnectError("timeout na 432"),
                _resposta("0.78"),          # o que a 4390 devolveria
            ]
            taxas = c.get_rates()
        assert taxas["selic_annual"] == pytest.approx(0.1475)

    def test_primaria_com_valor_absurdo_cai_para_a_secundaria(self):
        c = _conector()
        with patch("httpx.Client") as cls:
            cls.return_value.__enter__.return_value.get.side_effect = [
                _resposta("0.05166"),       # a 432 devolvendo taxa diária
                _resposta("13.95"),         # a 4189, sã
            ]
            taxas = c.get_rates()
        assert taxas["selic_annual"] == pytest.approx(0.1395)

    def test_secundaria_sa_e_servida(self):
        c = _conector()
        with patch("httpx.Client") as cls:
            cls.return_value.__enter__.return_value.get.side_effect = [
                httpx.ConnectError("timeout na 432"),
                _resposta("13.95"),
            ]
            assert c.get_rates()["selic_annual"] == pytest.approx(0.1395)

    @pytest.mark.parametrize("primaria,secundaria", [
        ("0.78", "0.78"),
        ("0.05166", "0.0012"),
        ("1400", "1395"),
    ])
    def test_nenhum_caminho_entrega_taxa_fora_da_banda(self, primaria, secundaria):
        c = _conector()
        with patch("httpx.Client") as cls:
            cls.return_value.__enter__.return_value.get.side_effect = [
                _resposta(primaria), _resposta(secundaria),
            ]
            selic = c.get_rates()["selic_annual"]
        assert BacenConnector._SELIC_MIN_PLAUSIVEL <= selic <= BacenConnector._SELIC_MAX_PLAUSIVEL


# ── 4. A consequência que apareceu no conselho de compra ───────────────────

class TestConsequenciaNoVPL:
    """
    Por que 0,0078 não é um detalhe de conector: é a taxa que traz os quatro
    meios de pagamento ao mesmo instante. Sem valor do dinheiro no tempo, adiar
    pagamento não vale nada e o ranking inverte.
    """

    def test_o_ganho_de_parcelar_colapsa_com_a_taxa_errada(self):
        from app.purchase.opportunity_cost import _cdi_net_monthly

        def vpl(r):
            return sum((3_000.0 / 12) / (1 + r) ** k for k in range(1, 13))

        certa = 3_000.0 - vpl(_cdi_net_monthly(0.14, 12))
        errada = 3_000.0 - vpl(_cdi_net_monthly(0.0078, 12))

        # R$ 164,47 contra R$ 9,72 — dezessete vezes. (Os R$ 213,22 que
        # apareceram no relatório do teste que falhou somam a esse ganho os
        # R$ 48,75 de cashback.)
        assert certa == pytest.approx(164.47, abs=0.5)
        assert errada == pytest.approx(9.72, abs=0.5)
        assert certa / errada > 15

    def test_com_a_taxa_errada_o_pix_vence_ate_sem_desconto_real(self):
        """
        Desconto de 2% (R$ 2.940 num item de R$ 3.000): com a SELIC certa o
        cartão parcelado ganha com folga; com 0,78% a.a. o PIX passa na frente.
        """
        from app.purchase.opportunity_cost import _cdi_net_monthly

        def net_parcelado(cdi, reward=48.75):
            r = _cdi_net_monthly(cdi, 12)
            return sum((3_000.0 / 12) / (1 + r) ** k for k in range(1, 13)) - reward

        assert net_parcelado(0.14) < 2_940.0
        assert net_parcelado(0.0078) > 2_940.0
