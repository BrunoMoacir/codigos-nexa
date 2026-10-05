"""
Os quatro verificadores de direitos — e a regra de que varredura não promete
dinheiro.

Não havia teste nenhum para `FgtsChecker`, `PisPasepChecker`,
`IrRestituicaoChecker` e `SvrBacenClient`. `total_estimated_recoverable` — o
campo que dá nome à funcionalidade — não tinha asserção em lugar algum. O
único teste que batia no endpoint (`test_overview_anota_capacidades`) rodava
com um usuário sem transações e afirmava só os rótulos `capability`, então
nunca chegava perto do caminho de estimativa.

É a quinta variante do mesmo vício da suíte: exercitar o endpoint e afirmar só
o metadado, nunca o número que a funcionalidade existe para produzir. Aqui
todo valor esperado vem do CENÁRIO, nunca da saída do próprio verificador.

O que se via antes, num usuário de R$ 6.000/mês com salário e IRRF normais:

    TOTAL 'RECUPERÁVEL' ANUNCIADO: R$ 13.712,00
      fgts            2400.0  medium
      pis_pasep       1412.0  medium
      ir_restituicao  9900.0  medium

Nenhuma das três parcelas era dinheiro a receber: depósito de FGTS de emprego
ATIVO, um "abono" que era constante para qualquer renda, e o IRRF RETIDO.
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import polars as pl
import pytest

from app.rights.parametros_legais import (
    ABONO_TETO_REMUNERACAO_MENSAL,
    FGTS_ALIQUOTA_MENSAL,
    IRPF_ISENCAO_MENSAL,
    SALARIO_MINIMO,
    abono_proporcional,
)
from app.rights.services.contexto_transacional import ContextoTransacional
from app.rights.services.fgts_checker import FgtsChecker
from app.rights.services.ir_restituicao_checker import IrRestituicaoChecker
from app.rights.services.pis_pasep_checker import PisPasepChecker
from app.rights.services.svr_bacen_client import SvrBacenClient


def _primeiro_dia(meses_atras: int) -> dt.date:
    d = dt.date.today().replace(day=1)
    for _ in range(meses_atras):
        d = (d - dt.timedelta(days=1)).replace(day=1)
    return d


def _ctx(linhas: list[dict]) -> ContextoTransacional:
    with patch(
        "app.core.db.queries.get_transactions_for_user",
        return_value=pl.DataFrame(linhas),
    ):
        return ContextoTransacional.carregar("u")


def _salario(meses: int, valor: float, desc: str = "SALARIO EMPRESA") -> list[dict]:
    return [
        {"transaction_date": _primeiro_dia(i).replace(day=5),
         "amount": valor, "description": desc}
        for i in range(1, meses + 1)
    ]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# A regra central: varredura automática não promete dinheiro
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestVarreduraNaoPrometeDinheiro:
    """
    `app/fiscal/rights_monitor` já seguia esta regra e
    `tests/fiscal/test_rights_monitor.py` já a exigia. `GET /rights/{user_id}`,
    que é a porta de entrada, seguia a política oposta. Agora vale uma só.
    """

    @pytest.fixture
    def resposta(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.core.security import require_owner
        from app.rights.router import limiter, router

        limiter.enabled = False
        linhas = []
        for i in range(1, 13):
            linhas += [
                {"transaction_date": _primeiro_dia(i).replace(day=5),
                 "amount": 6000.0, "description": "SALARIO EMPRESA XYZ"},
                {"transaction_date": _primeiro_dia(i).replace(day=5),
                 "amount": -900.0, "description": "IRRF SOBRE SALARIO"},
            ]
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[require_owner] = lambda user_id: "u"
        with patch(
            "app.core.db.queries.get_transactions_for_user",
            return_value=pl.DataFrame(linhas),
        ):
            return TestClient(app).get("/rights/u").json()

    def test_total_recuperavel_e_zero(self, resposta):
        """Era R$ 13.712,00 para exatamente este extrato."""
        assert resposta["total_estimated_recoverable"] == 0.0

    def test_nenhuma_heuristica_preenche_estimated_amount(self, resposta):
        for direito in resposta["rights"]:
            assert direito["estimated_amount"] is None, (
                f"{direito['category']} preencheu estimated_amount por heurística"
            )

    def test_o_sinal_existe_e_diz_o_que_mede(self, resposta):
        """
        A heurística não sumiu — mudou de campo e ganhou rótulo. Saber que há
        R$ 10.800 de IRRF no ano muda a prioridade de olhar a restituição.
        """
        sinais = {d["category"]: d["sinal"] for d in resposta["rights"] if d["sinal"]}
        assert "fgts" in sinais and "ir_restituicao" in sinais

        ir = sinais["ir_restituicao"]
        assert ir["valor"] == pytest.approx(12 * 900.0)
        assert ir["nao_e_valor_a_receber"] is True
        assert "não é o valor da restituição" in ir["rotulo"]

        fgts = sinais["fgts"]
        assert "não é saldo" in fgts["rotulo"]
        assert fgts["base"], "todo sinal declara como foi obtido"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ContextoTransacional — mês é mês, não linha
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestRendaMensalEDeVerdadeMensal:

    def test_renda_mensal_soma_o_mes_e_promedia_entre_meses(self):
        """
        `income["amount"].mean()` era a média de CADA CRÉDITO. Aqui a renda de
        quem recebe R$ 12.000 em um crédito e a de quem recebe o mesmo em
        vários têm que dar o mesmo número.
        """
        um = _salario(12, 12_000.0)
        varios = [
            {"transaction_date": _primeiro_dia(i).replace(day=d),
             "amount": 4_000.0, "description": "SALARIO"}
            for i in range(1, 13) for d in (5, 15, 25)
        ]
        assert _ctx(um).renda_mensal_media == pytest.approx(12_000.0)
        assert _ctx(varios).renda_mensal_media == pytest.approx(12_000.0)

    def test_pix_pequenos_nao_derrubam_a_renda_media(self):
        """
        O caso que quebrava o teto do abono: R$ 12.000/mês de salário mais 60
        Pix de R$ 50 davam "renda média R$ 1.901,41/mês".
        """
        linhas = _salario(12, 12_000.0) + [
            {"transaction_date": _primeiro_dia(1 + i % 11).replace(day=10),
             "amount": 50.0, "description": "PIX RECEBIDO"}
            for i in range(60)
        ]
        assert _ctx(linhas).renda_mensal_media > 12_000.0

    def test_meses_sao_meses_distintos_nao_linhas(self):
        seis_meses_dois_creditos = [
            {"transaction_date": _primeiro_dia(i).replace(day=d),
             "amount": 2_000.0, "description": "SALARIO"}
            for i in range(1, 7) for d in (5, 20)
        ]
        ctx = _ctx(seis_meses_dois_creditos)
        assert ctx.meses_com_salario == 6

    def test_mes_corrente_parcial_fica_de_fora(self):
        """
        Sem limite superior, o mês corrente pela metade dilui a média e o
        número muda ao longo do mês — o mesmo defeito já corrigido no Radar de
        Oportunidades.
        """
        completos = _salario(3, 5_000.0)
        com_parcial = completos + [
            {"transaction_date": dt.date.today().replace(day=1),
             "amount": 1_200.0, "description": "SALARIO ADIANTADO"}
        ]
        assert _ctx(com_parcial).meses_com_salario == 3
        assert _ctx(com_parcial).renda_mensal_media == pytest.approx(5_000.0)

    def test_sem_dado_e_diferente_de_zero(self):
        vazio = ContextoTransacional()
        assert vazio.disponivel is False
        assert vazio.renda_mensal_media is None
        assert vazio.salario_mensal_medio is None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FGTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestFgts:

    def test_o_sinal_nao_depende_de_como_o_patrao_parcela(self):
        """
        Mesma renda de R$ 4.000/mês por 6 meses. Antes: R$ 1.600 para quem
        recebia de uma vez e R$ 960 para quem recebia adiantamento + salário.
        """
        uma_vez = _salario(6, 4_000.0)
        parcelado = [
            {"transaction_date": _primeiro_dia(i).replace(day=20),
             "amount": 2_000.0, "description": "ADIANTAMENTO SALARIAL"}
            for i in range(1, 7)
        ] + [
            {"transaction_date": _primeiro_dia(i).replace(day=5),
             "amount": 2_000.0, "description": "SALARIO"}
            for i in range(1, 7)
        ]
        esperado = 4_000.0 * FGTS_ALIQUOTA_MENSAL * 6   # do CENÁRIO, não da saída

        a = FgtsChecker().check("u", _ctx(uma_vez)).sinal
        b = FgtsChecker().check("u", _ctx(parcelado)).sinal
        assert a.valor == pytest.approx(esperado)
        assert b.valor == pytest.approx(esperado)

    def test_o_aviso_diz_que_nao_e_saldo_nem_sacavel(self):
        r = FgtsChecker().check("u", _ctx(_salario(6, 4_000.0)))
        assert r.estimated_amount is None
        assert "não é saldo" in r.warning
        assert "hipóteses previstas em lei" in r.warning

    def test_sem_padrao_salarial_nao_inventa_sinal(self):
        linhas = [
            {"transaction_date": _primeiro_dia(i).replace(day=5),
             "amount": 3_000.0, "description": "TRANSFERENCIA RECEBIDA"}
            for i in range(1, 7)
        ]
        r = FgtsChecker().check("u", _ctx(linhas))
        assert r.sinal is None
        assert "não significa que não haja FGTS" in r.relevance_reason


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PIS/PASEP — abono salarial
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestAbonoSalarial:

    def test_o_teto_e_o_da_lei_e_nao_cinco_salarios_minimos(self):
        """
        `5 * 1412.0` = R$ 7.060. O critério nunca foi 5 salários mínimos, e
        sim 2 — e desde 2026 é um valor corrigido pelo INPC, desvinculado do
        mínimo. Quem ganhava R$ 6.000/mês era declarado elegível.
        """
        assert ABONO_TETO_REMUNERACAO_MENSAL < 5 * SALARIO_MINIMO
        r = PisPasepChecker().check("u", _ctx(_salario(12, 6_000.0)))
        assert r.sinal is None
        assert "acima do teto" in r.relevance_reason

    def test_quem_cabe_no_teto_recebe_o_valor_proporcional(self):
        r = PisPasepChecker().check("u", _ctx(_salario(12, 2_000.0)))
        assert r.sinal.valor == pytest.approx(SALARIO_MINIMO)

    @pytest.mark.parametrize("meses", [3, 6, 9])
    def test_o_abono_e_proporcional_e_nao_constante(self, meses):
        """
        `_estimate_abono` fixava `months_worked = 12`: os dois ramos devolviam
        o salário mínimo cheio para qualquer renda e qualquer histórico.
        """
        r = PisPasepChecker().check("u", _ctx(_salario(meses, 2_000.0)))
        assert r.sinal.valor == pytest.approx(round(SALARIO_MINIMO * meses / 12, 2))
        assert r.sinal.valor < SALARIO_MINIMO

    def test_o_valor_do_abono_e_proporcional_na_funcao_pura(self):
        assert abono_proporcional(0) == 0.0
        assert abono_proporcional(6) == pytest.approx(SALARIO_MINIMO / 2, abs=0.01)
        assert abono_proporcional(12) == pytest.approx(SALARIO_MINIMO)
        assert abono_proporcional(99) == pytest.approx(SALARIO_MINIMO), "limitado a 12/12"

    def test_declara_os_requisitos_que_a_nexa_nao_verifica(self):
        """
        Caber no teto de renda é UM dos quatro requisitos. Os outros dependem
        da RAIS/eSocial e do tempo de inscrição no PIS — dados que a Nexa não
        tem e sobre os quais não pode afirmar nada.
        """
        r = PisPasepChecker().check("u", _ctx(_salario(12, 2_000.0)))
        assert "SE você cumprir" in r.sinal.rotulo
        assert "5 anos" in r.sinal.base
        assert "30 dias" in r.sinal.base
        assert "RAIS" in r.sinal.base


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Restituição de IR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestIrrf:

    def test_restituicao_ja_recebida_nao_conta_como_retencao(self):
        """
        `abs(sum)` misturava os sinais: seis retenções de R$ 500 mais uma
        restituição JÁ RECEBIDA de R$ 4.000 davam "R$ 1.000 de IRRF retido" —
        dinheiro que o usuário já tinha na conta, contado como a receber.
        """
        linhas = [
            {"transaction_date": _primeiro_dia(i).replace(day=5),
             "amount": -500.0, "description": "IRRF SALARIO"}
            for i in range(1, 7)
        ] + [
            {"transaction_date": _primeiro_dia(2).replace(day=10),
             "amount": 4_000.0, "description": "RESTITUICAO IRRF RECEBIDA"}
        ]
        r = IrRestituicaoChecker().check("u", _ctx(linhas))
        assert r.sinal.valor == pytest.approx(6 * 500.0)

    @pytest.mark.parametrize("descricao", [
        "IMPOSTO DE RENDA RETIDO NA FONTE",
        "IMPOSTO RENDA RETIDO",
        "IRRF SOBRE SALARIO",
        "IR RETIDO FONTE",
    ])
    def test_reconhece_como_o_extrato_escreve(self, descricao):
        """
        `IMPOSTO DE RENDA RETIDO NA FONTE` — a forma mais literal — não casava.
        A regex inline em produção era mais pobre que a `_IR_KEYWORDS`
        compilada e nunca usada logo acima dela.
        """
        linhas = [{"transaction_date": _primeiro_dia(1).replace(day=5),
                   "amount": -500.0, "description": descricao}]
        assert IrRestituicaoChecker().check("u", _ctx(linhas)).sinal is not None

    def test_quem_e_isento_nao_e_informado_de_que_esta_acima_da_faixa(self):
        """
        `28_559.70` era a faixa ANUAL de 2024. Desde 01/2026 a isenção é de
        R$ 5.000/mês: quem ganha R$ 3.000/mês recebia "acima do limite de
        isenção, provável IR retido na fonte" com R$ 2.700 estimados.
        """
        assert 3_000.0 < IRPF_ISENCAO_MENSAL
        r = IrRestituicaoChecker().check("u", _ctx(_salario(12, 3_000.0)))
        assert r.sinal is None
        assert "acima da faixa de isenção" not in r.relevance_reason
        assert "dentro da faixa de isenção" in r.relevance_reason

    def test_acima_da_faixa_sem_irrf_no_extrato_avisa_sem_estimar(self):
        r = IrRestituicaoChecker().check("u", _ctx(_salario(12, 9_000.0)))
        assert r.sinal is None
        assert "acima da faixa de isenção" in r.relevance_reason

    def test_o_aviso_separa_retido_de_restituivel(self):
        linhas = [{"transaction_date": _primeiro_dia(i).replace(day=5),
                   "amount": -800.0, "description": "IRRF"} for i in range(1, 7)]
        r = IrRestituicaoChecker().check("u", _ctx(linhas))
        assert "não o que você tem a receber" in r.warning
        assert "pode ser zero" in r.warning


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SVR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestSvr:

    def test_nunca_produz_valor(self):
        """
        A consulta pública do SVR responde `temValorAReceber: bool` e nada
        mais — o montante exige login GOV.BR. Qualquer número aqui seria
        inventado.
        """
        r = SvrBacenClient().check("u", _ctx(_salario(6, 4_000.0)))
        assert r.estimated_amount is None
        assert r.sinal is None

    def test_nao_afirma_estatistica_sem_fonte(self):
        """Havia 'a mediana ... é de aproximadamente R$ 150' na descrição."""
        r = SvrBacenClient().check("u", _ctx([]))
        assert "mediana" not in r.description.lower()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# A tool do agente lê os verificadores
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestToolDoAgente:
    """
    Era um bloco de texto fixo: as mesmas quatro seções para todo mundo, sem
    nunca chamar os verificadores. Terceira implementação paralela da mesma
    funcionalidade, com uma terceira política.
    """

    def _rodar(self, linhas):
        from app.agent.tools.get_forgotten_rights import get_forgotten_rights

        with patch(
            "app.core.db.queries.get_transactions_for_user",
            return_value=pl.DataFrame(linhas),
        ), patch(
            "app.agent.tools.get_forgotten_rights._get_total_negotiation_gain",
            return_value=0.0,
        ):
            return get_forgotten_rights.invoke({"user_id": "u"})

    def test_o_texto_muda_com_o_extrato(self):
        com_salario = self._rodar(_salario(6, 4_000.0))
        sem_salario = self._rodar([
            {"transaction_date": _primeiro_dia(i).replace(day=5),
             "amount": 100.0, "description": "TRANSFERENCIA"}
            for i in range(1, 7)
        ])
        assert com_salario != sem_salario
        from app.core.formatacao import brl
        assert brl(4_000.0 * FGTS_ALIQUOTA_MENSAL * 6) in com_salario

    def test_nunca_imprime_total_a_receber(self):
        texto = self._rodar(_salario(12, 2_000.0))
        assert "total recuperável" not in texto.lower()
        assert "NÃO é valor a receber" in texto

    def test_mostra_que_a_consulta_do_SVR_e_real(self):
        """
        Com `capability` fixo em "guided", a tool escondia do usuário a única
        parte da funcionalidade que consulta de verdade.
        """
        texto = self._rodar(_salario(6, 4_000.0))
        assert "CONSULTA REAL NA NEXA" in texto
