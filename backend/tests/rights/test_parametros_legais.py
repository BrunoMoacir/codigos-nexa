"""
Parâmetros legais do T3 — o teste que quebra quando o ano vira.

Os números deste módulo mudam por lei, quase sempre em janeiro. Espalhados
pelo código, apodrecem em silêncio e o produto continua dando orientação
errada com a mesma confiança de antes. Foi exatamente o que aconteceu:

  • `_ABONO_SALARIAL_TETO = 5 * 1412.0` → R$ 7.060, contra R$ 2.765,93 reais.
    Errado no multiplicador (nunca foram 5 salários mínimos, e sim 2) e na
    base (R$ 1.412 é o mínimo de 2024).
  • `28_559.70` → faixa anual de isenção do IRPF de 2024, quando desde 01/2026
    a isenção é de R$ 5.000/mês. Quem ganhava R$ 3.000/mês era informado de
    que estava "acima do limite de isenção".

Ambos ficaram parados até serem encontrados por auditoria, dois anos depois.
Um comentário dizendo "atualizar a cada ano" não impede isso; um teste
vermelho impede.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.rights import parametros_legais as p


class TestVigencia:

    def test_os_parametros_sao_do_ano_corrente(self):
        """
        Falha em 1º de janeiro. É o objetivo: a mensagem diz o que atualizar e
        onde, e a atualização leva minutos. O custo de esquecer é orientar mal
        sobre imposto e benefício social.
        """
        assert not p.parametros_vencidos(), p.AVISO_VENCIDO

    def test_a_guarda_detecta_o_ano_seguinte(self):
        assert p.parametros_vencidos(dt.date(p.ANO_VIGENCIA + 1, 1, 1)) is True
        assert p.parametros_vencidos(dt.date(p.ANO_VIGENCIA, 12, 31)) is False

    def test_todo_parametro_declara_a_fonte(self):
        for fonte in (p.SALARIO_MINIMO_FONTE, p.ABONO_FONTE, p.FGTS_FONTE, p.IRPF_FONTE):
            assert fonte and len(fonte) > 30, "parâmetro legal sem fonte declarada"


class TestOrdemDeGrandeza:
    """
    Não é calibração: é o que separa "número atualizado" de "número trocado".
    """

    def test_teto_do_abono_esta_entre_um_e_dois_salarios_minimos(self):
        """
        A regra convergiu de 2 salários mínimos para 1,5 e segue corrigida
        pelo INPC. Um teto de 5 mínimos, como havia, cai fora por larga
        margem.
        """
        assert p.SALARIO_MINIMO < p.ABONO_TETO_REMUNERACAO_MENSAL < 2 * p.SALARIO_MINIMO

    def test_isencao_do_ir_e_mensal_e_nao_anual(self):
        """
        `28_559.70` era um valor ANUAL comparado contra renda anual. Trocar a
        unidade aqui divide o limiar por 12 e acusa quase todo mundo.
        """
        assert 1_000 < p.IRPF_ISENCAO_MENSAL < 20_000
        assert p.irpf_isencao_anual() == pytest.approx(p.IRPF_ISENCAO_MENSAL * 12)

    def test_faixa_de_reducao_gradual_fica_acima_da_isencao(self):
        assert p.IRPF_REDUCAO_GRADUAL_ATE_MENSAL > p.IRPF_ISENCAO_MENSAL

    def test_aliquota_do_fgts_e_oito_por_cento(self):
        assert p.FGTS_ALIQUOTA_MENSAL == 0.08

    def test_salario_minimo_na_ordem_de_grandeza_de_hoje(self):
        assert 1_000 < p.SALARIO_MINIMO < 5_000


class TestRequisitosDoAbono:

    def test_os_requisitos_nao_verificaveis_estao_declarados(self):
        """
        Existem para serem MOSTRADOS. São o que separa "você tem direito" — que
        a Nexa não pode afirmar — de "confira estes pontos", que pode.
        """
        texto = " ".join(p.ABONO_REQUISITOS_NAO_VERIFICAVEIS).lower()
        assert "5 anos" in texto
        assert "30 dias" in texto
        assert "rais" in texto or "esocial" in texto
