"""
As regras tributárias de investimento — brackets, compensação de perda e
come-cotas.

Dos 105 testes que a área tinha, 13 protegiam dois módulos que nenhum router,
service ou tool importava (`app/fiscal/services/tax_radar.py` e
`app/fiscal/services/tax_loss_harvesting.py`) e 38 cobriam o calendário. Não
havia um único teste para o `TaxLossHarvester` vivo, para o `ZeroTaxMode`, para
o `InvestmentProfiler` nem para o cálculo do DAS.

**Sexta variante do vício da suíte:** manter testes verdes sobre código que
ninguém chama. A suíte reportava "tax loss harvesting testado" e o que rodava
em produção nunca tinha sido exercitado.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.tax.models import InvestmentPosition
from app.tax.parametros_fiscais import (
    ALIQUOTA_BOLSA,
    ALIQUOTA_FII,
    ISENCAO_BOLSA_ALIENACOES_MES,
    aliquota_de_ganho,
    aliquota_regressiva,
    classe_de_compensacao,
    proximo_come_cotas,
    proximo_degrau,
)
from app.tax.services.tax_loss_harvesting import TaxLossHarvester
from app.tax.services.zero_tax_mode import ZeroTaxMode

HOJE = dt.date.today()


def _pos(**kw) -> InvestmentPosition:
    base = dict(
        bank_name="XP", product_name="Produto", product_type="CDB",
        amount=100_000.0, current_balance=100_000.0, annual_rate_pct=13.0,
        holding_months=12, is_exempt=False, unrealized_gain=0.0,
        estimated_ir=0.0, has_come_cotas=False,
    )
    base.update(kw)
    return InvestmentPosition(**base)


def _com_ganho(dias: int, ganho: float, **kw) -> InvestmentPosition:
    return _pos(
        application_date=HOJE - dt.timedelta(days=dias),
        current_balance=100_000.0 + ganho,
        unrealized_gain=ganho,
        estimated_ir=round(ganho * aliquota_regressiva(dias), 2),
        **kw,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# A tabela regressiva e o próximo degrau
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestTabelaRegressiva:

    @pytest.mark.parametrize("dias,esperado", [
        (1, 0.225), (180, 0.225), (181, 0.200), (360, 0.200),
        (361, 0.175), (720, 0.175), (721, 0.150), (5_000, 0.150),
    ])
    def test_aliquota_por_prazo(self, dias, esperado):
        """Lei 11.033/2004, art. 1º — "até 180 dias" inclui o dia 180."""
        assert aliquota_regressiva(dias) == esperado

    @pytest.mark.parametrize("dias,faltam,nova", [
        (1, 180, 0.200),
        (90, 91, 0.200),
        (180, 1, 0.200),      # falta UM dia, não seis meses
        (181, 180, 0.175),
        (359, 2, 0.175),
        (719, 2, 0.150),
        (720, 1, 0.150),
    ])
    def test_proximo_degrau(self, dias, faltam, nova):
        """
        A versão anterior, em meses, devolvia a faixa em que a posição JÁ
        estava. Aos 180 dias mandava esperar mais 6 MESES quando falta 1 dia.
        """
        assert proximo_degrau(dias) == (faltam, nova)

    def test_na_menor_faixa_nao_ha_degrau(self):
        assert proximo_degrau(721) is None
        assert proximo_degrau(10_000) is None


class TestAliquotaPorClasseDeAtivo:
    """
    Tudo passava por `calc_ir_on_cdb`, ou seja, pela tabela regressiva de renda
    fixa — inclusive ação e FII, que têm alíquota linear.
    """

    def test_acao_e_quinze_por_cento_em_qualquer_prazo(self):
        for dias in (30, 200, 800):
            assert aliquota_de_ganho("ACAO", dias) == ALIQUOTA_BOLSA
        assert aliquota_de_ganho("ACAO", 90) != aliquota_regressiva(90)

    def test_fii_e_vinte_por_cento(self):
        assert aliquota_de_ganho("FII", 90) == ALIQUOTA_FII

    def test_renda_fixa_e_fundo_seguem_a_regressiva(self):
        assert aliquota_de_ganho("CDB", 90) == 0.225
        assert aliquota_de_ganho("FUNDO_MM", 800) == 0.150


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Hold longer
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestHoldLonger:

    @pytest.fixture
    def harvester(self):
        return TaxLossHarvester()

    @pytest.mark.parametrize("dias", [30, 90, 175, 180, 181, 300, 340, 359, 700, 719])
    def test_dispara_em_toda_a_faixa(self, harvester, dias):
        """
        Varredura de 1 a 29 meses na versão anterior: só `holding_months == 6`
        passava. Todo caso útil — faltando um ou dois meses para o degrau —
        era descartado.
        """
        pos = _com_ganho(dias, 10_000.0)
        achados = [
            o for o in harvester.find_opportunities([pos])
            if o.opportunity_type == "hold_longer"
        ]
        assert achados, f"nenhuma oportunidade com {dias} dias de aplicação"

    def test_aos_180_dias_a_espera_e_de_um_dia(self, harvester):
        """Era "Não resgatar nas próximas 24 semanas"."""
        o = [x for x in harvester.find_opportunities([_com_ganho(180, 10_000.0)])
             if x.opportunity_type == "hold_longer"][0]
        assert "Amanhã" in o.description
        assert "1 dia" in o.action_deadline

    def test_a_economia_vem_da_diferenca_de_aliquota(self, harvester):
        ganho = 10_000.0
        o = [x for x in harvester.find_opportunities([_com_ganho(175, ganho)])
             if x.opportunity_type == "hold_longer"][0]
        assert o.estimated_tax_saving_brl == pytest.approx(ganho * (0.225 - 0.200))

    def test_acima_da_menor_faixa_nao_ha_o_que_esperar(self, harvester):
        assert not [
            o for o in harvester.find_opportunities([_com_ganho(800, 10_000.0)])
            if o.opportunity_type == "hold_longer"
        ]

    def test_acao_e_fii_nao_tem_degrau_de_prazo(self, harvester):
        """15% e 20% são lineares — não existe bracket a aguardar."""
        for tipo in ("ACAO", "FII"):
            pos = _com_ganho(90, 20_000.0, product_type=tipo)
            assert not [
                o for o in harvester.find_opportunities([pos])
                if o.opportunity_type == "hold_longer"
            ], tipo

    def test_sem_data_de_aplicacao_a_confianca_cai(self, harvester):
        """
        `holding_months` vem de aritmética de mês-calendário e erra até ~15
        dias. Dizer "faltam 3 dias" em cima disso seria precisão inventada.
        """
        pos = _pos(holding_months=5, unrealized_gain=10_000.0,
                   current_balance=110_000.0, estimated_ir=2_250.0)
        o = [x for x in harvester.find_opportunities([pos])
             if x.opportunity_type == "hold_longer"][0]
        assert o.confidence == "medium"
        assert "cerca de" in o.description

        exato = [x for x in harvester.find_opportunities([_com_ganho(150, 10_000.0)])
                 if x.opportunity_type == "hold_longer"][0]
        assert exato.confidence == "high"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Harvest loss — só onde a lei permite compensar
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCompensacaoDePerda:

    @pytest.fixture
    def harvester(self):
        return TaxLossHarvester()

    def _harvest(self, harvester, carteira):
        return [o for o in harvester.find_opportunities(carteira)
                if o.opportunity_type == "harvest_loss"]

    @pytest.mark.parametrize("tipo", ["CDB", "TESOURO", "DEBENTURE", "LF"])
    def test_renda_fixa_nao_compensa(self, harvester, tipo):
        """
        O IR da renda fixa é retido na fonte sobre o rendimento de CADA
        operação: a perda de um papel não abate o ganho de outro. A versão
        anterior recomendava resgatar realizando prejuízo por um benefício que
        não existe nessa classe — dano real e irreversível.
        """
        carteira = [
            _pos(product_type=tipo, product_name="Perda",
                 current_balance=44_000.0, amount=50_000.0, unrealized_gain=-6_000.0),
            _com_ganho(400, 12_000.0, product_type=tipo, product_name="Ganho"),
        ]
        assert self._harvest(harvester, carteira) == []

    def test_bolsa_compensa(self, harvester):
        """
        Ficava muda aqui: sem taxa anual contratada — que a Pluggy não informa
        para renda variável — o `estimated_ir` era zero e o detector saía.
        """
        carteira = [
            _pos(product_type="ACAO", product_name="MGLU3", amount=40_000.0,
                 current_balance=25_000.0, unrealized_gain=-15_000.0),
            _pos(product_type="ACAO", product_name="PETR4", amount=60_000.0,
                 current_balance=90_000.0, unrealized_gain=30_000.0,
                 estimated_ir=30_000.0 * ALIQUOTA_BOLSA),
        ]
        achados = self._harvest(harvester, carteira)
        assert len(achados) == 1
        # Perda de 15k cobre metade do ganho de 30k → metade do IR de 4.500.
        assert achados[0].estimated_tax_saving_brl == pytest.approx(2_250.0)

    def test_fii_nao_compensa_com_acao(self, harvester):
        """FII é categoria separada: perda de FII só abate ganho de FII."""
        carteira = [
            _pos(product_type="FII", product_name="HGLG11", amount=40_000.0,
                 current_balance=30_000.0, unrealized_gain=-10_000.0),
            _pos(product_type="ACAO", product_name="PETR4", amount=60_000.0,
                 current_balance=90_000.0, unrealized_gain=30_000.0,
                 estimated_ir=4_500.0),
        ]
        assert self._harvest(harvester, carteira) == []

    def test_fundos_so_da_mesma_administradora(self, harvester):
        def fundos(banco_do_ganho: str):
            return [
                _pos(product_type="FUNDO_MM", bank_name="XP", product_name="F1",
                     amount=40_000.0, current_balance=30_000.0, unrealized_gain=-10_000.0),
                _pos(product_type="FUNDO_MM", bank_name=banco_do_ganho, product_name="F2",
                     amount=60_000.0, current_balance=90_000.0,
                     unrealized_gain=30_000.0, estimated_ir=4_500.0),
            ]
        assert self._harvest(harvester, fundos("BTG")) == []
        assert self._harvest(harvester, fundos("XP")) != []

    def test_ganho_dentro_da_isencao_de_bolsa_nao_gera_colheita(self, harvester):
        """
        Realizar prejuízo para compensar um ganho ISENTO é perda pura. A
        isenção é de R$ 20.000 em alienações no mês (Lei 11.033/2004, art. 3º).
        """
        carteira = [
            _pos(product_type="ACAO", product_name="MGLU3", amount=9_000.0,
                 current_balance=4_000.0, unrealized_gain=-5_000.0),
            _pos(product_type="ACAO", product_name="PETR4", amount=8_000.0,
                 current_balance=15_000.0, unrealized_gain=7_000.0,
                 estimated_ir=1_050.0),
        ]
        assert sum(p.current_balance for p in carteira[1:]) < ISENCAO_BOLSA_ALIENACOES_MES
        assert self._harvest(harvester, carteira) == []

    def test_a_economia_usa_o_IR_real_de_cada_posicao(self, harvester):
        """
        Era "alíquota do prazo MÉDIO das posições com ganho" — aproximação que
        erra quando a carteira tem prazos dispersos. Agora a economia é a
        fração do ganho coberta pela perda vezes o IR efetivamente apurado.
        """
        carteira = [
            _pos(product_type="FUNDO_MM", bank_name="XP", product_name="Perda",
                 amount=20_000.0, current_balance=15_000.0, unrealized_gain=-5_000.0),
            _com_ganho(100, 10_000.0, product_type="FUNDO_MM", bank_name="XP",
                       product_name="Curto"),     # 22,5%
            _com_ganho(800, 10_000.0, product_type="FUNDO_MM", bank_name="XP",
                       product_name="Longo"),     # 15,0%
        ]
        ir_total = 10_000 * 0.225 + 10_000 * 0.150
        esperado = ir_total * (5_000 / 20_000)
        assert self._harvest(harvester, carteira)[0].estimated_tax_saving_brl == pytest.approx(
            esperado, abs=0.02
        )

    def test_classe_de_compensacao_declarada(self):
        assert classe_de_compensacao("CDB") is None
        assert classe_de_compensacao("ACAO") == "bolsa"
        assert classe_de_compensacao("FII") == "fii"
        assert classe_de_compensacao("FUNDO_RF") == "fundo"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Come-cotas
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestComeCotas:

    @pytest.mark.parametrize("mes,esperado", [
        (1, "maio"), (4, "maio"), (5, "maio"),
        (6, "novembro"), (8, "novembro"), (10, "novembro"), (11, "novembro"),
        (12, "maio"),
    ])
    def test_mes_da_proxima_incidencia(self, mes, esperado):
        """
        O rótulo saía de `meses_restantes <= 5`, e de junho a outubro a
        distância até novembro é ≤ 5 — então SETE dos doze meses do ano
        diziam "maio".
        """
        _data, nome = proximo_come_cotas(dt.date(2026, mes, 15))
        assert nome == esperado

    def test_a_data_e_uma_data_de_verdade(self):
        """A string impressa para maio era `"31/{ano}"`, sem mês."""
        data, _ = proximo_come_cotas(dt.date(2026, 2, 10))
        assert (data.day, data.month, data.year) == (31, 5, 2026)
        data, _ = proximo_come_cotas(dt.date(2026, 7, 10))
        assert (data.day, data.month, data.year) == (30, 11, 2026)

    def test_em_dezembro_vira_o_ano(self):
        data, nome = proximo_come_cotas(dt.date(2026, 12, 20))
        assert data.year == 2027 and nome == "maio"

    def test_a_data_aparece_formatada_na_recomendacao(self):
        pos = _pos(product_type="FUNDO_MM", has_come_cotas=True,
                   current_balance=215_000.0, unrealized_gain=15_000.0,
                   estimated_ir=2_625.0)
        achados = [o for o in ZeroTaxMode().find_opportunities([pos], 0.1465)
                   if o.opportunity_type == "avoid_come_cotas"]
        assert achados
        data, _ = proximo_come_cotas(dt.date.today())
        assert data.strftime("%d/%m/%Y") in achados[0].action_deadline

    def test_o_beneficio_e_diferimento_e_nao_economia(self):
        """
        O IR do come-cotas volta no resgate. Chamar de "economia de imposto" e
        somar no total superestima o benefício.
        """
        pos = _pos(product_type="FUNDO_MM", has_come_cotas=True,
                   current_balance=215_000.0, unrealized_gain=15_000.0,
                   estimated_ir=2_625.0)
        o = [x for x in ZeroTaxMode().find_opportunities([pos], 0.1465)
             if x.opportunity_type == "avoid_come_cotas"][0]
        assert o.benefit_kind == "deferral"
        assert "não elimina esse imposto" in o.description
