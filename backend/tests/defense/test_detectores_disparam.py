"""
Defesa do Consumidor — os detectores precisam DISPARAR.

Dos 8 testes que existiam para os detectores, seis afirmavam que eles devolvem
lista vazia (`test_db_vazio_retorna_lista_vazia`, `test_db_erro_retorna_lista_vazia`)
e os outros checavam formato do achado. **Nenhum afirmava que um detector
encontra algo num cenário que deveria acioná-lo.** Um detector que nunca acha
nada passava em todos os 61 testes da feature — e era exatamente o que
acontecia:

  • D1a, o caminho mais forte, exigia a coluna `bank_name`, que
    `get_transactions_for_user` não devolve. Guarda dura, retorno vazio: o
    caso de manual do Tema 972/STJ (empréstimo de R$ 15 mil seguido de seguro
    prestamista três dias depois) não gerava achado nenhum;
  • `_INTEREST_PATTERN` do D3 procurava `\\bjuro\\b` e `\\bencargo\\b` no
    SINGULAR — extrato escreve "JUROS", "ENCARGOS";
  • o teto de R$ 800 do SEGURO_PRESTAMISTA no F5 (introduzido por uma premissa
    errada de "prêmio mensal") descartava o prêmio de R$ 890 de um empréstimo
    de R$ 15 mil, que é justamente o sinal do D1.

Cada cenário aqui é um caso de manual, com o valor esperado vindo do cenário.
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import polars as pl
import pytest

from app.defense.services.abusive_interest_detector import (
    _INTEREST_PATTERN,
    AbusiveInterestDetector,
)
from app.defense.services.tied_sale_detector import TiedSaleDetector


def _com_extrato(linhas: list[dict]):
    return patch(
        "app.core.db.queries.get_transactions_for_user",
        return_value=pl.DataFrame(linhas),
    )


# ── D1 — venda casada ────────────────────────────────────────────────────────

class TestD1DisparaNoCasoDeManual:
    """
    Tema 972/STJ: seguro prestamista vinculado a crédito sem liberdade de
    escolha da seguradora. Empréstimo liberado, prêmio debitado dias depois,
    mesma conta.
    """

    _EMPRESTIMO = {
        "account_id": "acc1", "date": dt.date(2026, 6, 10), "amount": 15_000.0,
        "description": "LIBERACAO EMPRESTIMO PESSOAL",
    }
    _PRESTAMISTA = {
        "account_id": "acc1", "date": dt.date(2026, 6, 13), "amount": -890.0,
        "description": "SEGURO PRESTAMISTA CONTRATO 4471",
    }

    def test_dispara(self):
        with _com_extrato([self._EMPRESTIMO, self._PRESTAMISTA]):
            achados = TiedSaleDetector()._check_temporal_correlation("u")

        assert len(achados) == 1, "o caso de manual do Tema 972 não gerou achado"
        assert achados[0].severity == "high"
        assert achados[0].detector == "D1"

    def test_a_evidencia_registra_o_intervalo(self):
        with _com_extrato([self._EMPRESTIMO, self._PRESTAMISTA]):
            achado = TiedSaleDetector()._check_temporal_correlation("u")[0]

        assert any("3 dia(s)" in e for e in achado.evidence_points)
        assert any("15000.00" in e for e in achado.evidence_points)
        assert any("890.00" in e for e in achado.evidence_points)

    def test_continua_sendo_pre_indicio_e_nao_sentenca(self):
        """
        A postura do produto: indício não é sentença. O achado precisa dizer
        que exige confirmação, e a ação tem que COMEÇAR pedindo isso.
        """
        with _com_extrato([self._EMPRESTIMO, self._PRESTAMISTA]):
            achado = TiedSaleDetector()._check_temporal_correlation("u")[0]

        assert "PRÉ-INDÍCIO" in achado.description
        assert "livremente" in achado.recommended_action.split("\n")[0]
        assert "Tema 972" in achado.legal_basis

    def test_conta_diferente_nao_correlaciona(self):
        """Crédito numa conta e seguro em outra não são o mesmo contrato."""
        outra_conta = {
            "account_id": "acc2", "date": dt.date(2026, 6, 12), "amount": -120.0,
            "description": "SEGURO RESIDENCIAL",
        }
        with _com_extrato([self._EMPRESTIMO, outra_conta]):
            assert TiedSaleDetector()._check_temporal_correlation("u") == []

    def test_fora_da_janela_nao_correlaciona(self):
        tardio = {**self._PRESTAMISTA, "date": dt.date(2026, 6, 25)}
        with _com_extrato([self._EMPRESTIMO, tardio]):
            assert TiedSaleDetector()._check_temporal_correlation("u") == []

    def test_seguro_sem_credito_antes_nao_correlaciona(self):
        """Seguro contratado por conta própria não é venda casada."""
        with _com_extrato([self._PRESTAMISTA]):
            assert TiedSaleDetector()._check_temporal_correlation("u") == []

    @pytest.mark.parametrize(
        "descricao_credito",
        ["LIBERACAO EMPRESTIMO PESSOAL", "CREDITO FINANCIAMENTO VEICULAR",
         "LIBERACAO CREDCONSIG", "EMPRESTIMO CONSIGNADO"],
    )
    def test_formas_de_liberacao_de_credito(self, descricao_credito):
        credito = {**self._EMPRESTIMO, "description": descricao_credito}
        with _com_extrato([credito, self._PRESTAMISTA]):
            assert len(TiedSaleDetector()._check_temporal_correlation("u")) == 1

    @pytest.mark.parametrize(
        "descricao_produto",
        ["SEGURO PRESTAMISTA CONTRATO 4471", "TITULO DE CAPITALIZACAO",
         "ASSISTENCIA RESIDENCIAL", "SEGURO PROTECAO FINANCEIRA"],
    )
    def test_formas_de_produto_vinculado(self, descricao_produto):
        produto = {**self._PRESTAMISTA, "description": descricao_produto}
        with _com_extrato([self._EMPRESTIMO, produto]):
            assert len(TiedSaleDetector()._check_temporal_correlation("u")) == 1


class TestPremioDeSeguroSobreviveAoF5:
    """
    O `_FEE_CEILINGS` do F5 tinha teto de R$ 800 para SEGURO_PRESTAMISTA, por
    um comentário que dizia "prêmio mensal" — premissa não confirmada.
    Prestamista costuma ser prêmio ÚNICO proporcional ao principal (1–8%), e
    num empréstimo de R$ 15 mil R$ 890 é normal. O teto descartava o sinal do
    D1 na feature onde falso negativo custa mais caro.
    """

    @pytest.mark.parametrize("valor", [38.90, 890.0, 1_250.0, 3_400.0])
    def test_prestamista_de_qualquer_valor_e_detectado(self, valor):
        from app.costs.fee_detector import FeeDetector
        from app.costs.models import FeeType

        df = pl.DataFrame([{
            "date": dt.date(2026, 3, 10), "amount": -valor,
            "description": "SEGURO PRESTAMISTA CONTRATO 4471",
        }])
        achados = FeeDetector().detect(df)

        assert len(achados) == 1, f"prêmio de R$ {valor} foi descartado"
        assert achados[0].fee_type == FeeType.SEGURO_PRESTAMISTA
        assert achados[0].amount == pytest.approx(valor)

    def test_seguro_embutido_tambem(self):
        from app.costs.fee_detector import FeeDetector

        df = pl.DataFrame([{
            "date": dt.date(2026, 3, 10), "amount": -1_250.0,
            "description": "SEGURO HABITACIONAL MIP DFI",
        }])
        assert len(FeeDetector().detect(df)) == 1

    def test_o_teto_de_tarifa_continua_valendo(self):
        """A remoção foi cirúrgica: só os seguros, que escalam com o principal."""
        from app.costs.fee_detector import FeeDetector

        df = pl.DataFrame([{
            "date": dt.date(2026, 3, 10), "amount": -9_000.0,
            "description": "TARIFA MANUTENCAO CONTA",
        }])
        assert FeeDetector().detect(df) == []


# ── D3 — juros abusivos ──────────────────────────────────────────────────────

class TestD3ReconheceComoOExtratoEscreve:
    """
    O padrão só aceitava o singular. Nenhum banco escreve "JURO" no extrato.
    """

    @pytest.mark.parametrize(
        "descricao",
        [
            "JUROS",
            "JUROS EMPRESTIMO",
            "ENCARGOS",
            "ENCARGOS FATURA CARTAO",
            "JUROS SOBRE SALDO DEVEDOR",
            "JUROS ROTATIVO CARTAO",
            "CHEQUE ESPECIAL",
            "JURO ROTATIVO",           # o singular não pode ter sido perdido
        ],
    )
    def test_casa(self, descricao):
        from app.defense.services.abusive_interest_detector import _normalize

        assert _INTEREST_PATTERN.search(_normalize(descricao)), descricao

    @pytest.mark.parametrize(
        "descricao",
        ["SUPERMERCADO EXTRA", "UBER TRIP", "ALUGUEL APARTAMENTO", "NETFLIX.COM"],
    )
    def test_nao_casa_com_gasto_comum(self, descricao):
        from app.defense.services.abusive_interest_detector import _normalize

        assert not _INTEREST_PATTERN.search(_normalize(descricao)), descricao

    def test_dispara_e_diz_que_precisa_da_taxa_contratada(self):
        """
        Sem a taxa do contrato o detector não pode afirmar abusividade — e ele
        diz isso, em vez de calar ou de exagerar.
        """
        linhas = [
            {"account_id": "acc1", "date": dt.date(2026, 7, 20), "amount": -450.0,
             "description": "JUROS ROTATIVO CARTAO"},
            {"account_id": "acc1", "date": dt.date(2026, 8, 20), "amount": -380.0,
             "description": "ENCARGOS FATURA"},
        ]
        with _com_extrato(linhas):
            achados = AbusiveInterestDetector().detect("u")

        assert achados, "encargos de juros não geraram achado"
        texto = achados[0].description + " ".join(achados[0].evidence_points)
        assert "taxa contratada" in texto.lower()
        assert achados[0].amount_disputed == pytest.approx(830.0, rel=0.01)


class TestVocabularioNaoPrometeOQueNaoPode:
    """
    A regra do produto: "forte indício", "acima da média", "pode contestar" —
    nunca "é ilegal", nunca "você tem direito a R$ X". É o que separa um dossiê
    de uma promessa que só juiz pode fazer.
    """

    _PROIBIDOS = ("é ilegal", "e ilegal", "você tem direito a", "voce tem direito a",
                  "com certeza", "garantido")

    def _todos_os_achados(self):
        linhas = [
            {"account_id": "acc1", "date": dt.date(2026, 6, 10), "amount": 15_000.0,
             "description": "LIBERACAO EMPRESTIMO PESSOAL"},
            {"account_id": "acc1", "date": dt.date(2026, 6, 13), "amount": -890.0,
             "description": "SEGURO PRESTAMISTA CONTRATO 4471"},
            {"account_id": "acc1", "date": dt.date(2026, 7, 20), "amount": -450.0,
             "description": "JUROS ROTATIVO CARTAO"},
        ]
        with _com_extrato(linhas):
            return (
                TiedSaleDetector()._check_temporal_correlation("u")
                + AbusiveInterestDetector().detect("u")
            )

    def test_nenhum_achado_afirma_ilegalidade(self):
        for achado in self._todos_os_achados():
            texto = f"{achado.title} {achado.description}".lower()
            for proibido in self._PROIBIDOS:
                assert proibido not in texto, f"{achado.detector}: {proibido!r}"

    def test_todo_achado_cita_base_legal(self):
        for achado in self._todos_os_achados():
            assert achado.legal_basis, achado.detector
            assert "CDC" in achado.legal_basis or "STJ" in achado.legal_basis

    def test_todo_achado_tem_acao_recomendada(self):
        for achado in self._todos_os_achados():
            assert len(achado.recommended_action) > 40, achado.detector
