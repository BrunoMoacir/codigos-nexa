"""
O DAS do relatório fiscal — o número que o usuário levaria ao contador.

`FiscalReportService` não tinha um único teste. É o cálculo mais consequente da
área: erra para menos e o usuário recolhe a guia a menor, com multa e juros
depois.

Todo valor esperado vem do CENÁRIO, nunca da saída do próprio serviço.
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import polars as pl
import pytest

from app.fiscal.fiscal_report import FiscalReportService
from app.tax.parametros_fiscais import FATOR_R_LIMITE


def _df(linhas: list[tuple[dt.date, float, str | None]]) -> pl.DataFrame:
    return pl.DataFrame([
        {"date": d, "amount": a, "context_type": "PJ", "pj_subcategory": s}
        for d, a, s in linhas
    ])


def _gerar(linhas, year, month=None):
    with patch("app.fiscal.fiscal_report.get_transactions_for_user", return_value=_df(linhas)):
        return FiscalReportService().generate("u", year, month)


def _receita_mensal(pares: list[tuple[int, int]], valor: float) -> list[tuple]:
    return [(dt.date(y, m, 10), valor, "receita_servicos") for y, m in pares]


_ANO_ANTERIOR = [(2025, m) for m in range(8, 13)] + [(2026, m) for m in range(1, 8)]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# A janela do RBT12
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestJanelaDoRBT12:
    """
    A janela era `data_ref − 330 dias` até o fim do mês de referência:
    começava cinco dias depois do início do 12º mês anterior, INCLUÍA o
    próprio mês de apuração e alcançava os primeiros dias do mês seguinte.
    A LC 123/2006, art. 18, § 1º manda usar os doze meses ANTERIORES.
    """

    def test_o_mes_de_apuracao_nao_entra_no_proprio_RBT12(self):
        linhas = (
            [(dt.date(2025, 6, 10), 5_000.0, "receita_servicos")]
            + _receita_mensal([(2025, m) for m in range(7, 13)]
                              + [(2026, m) for m in range(1, 6)], 15_000.0)
            + [(dt.date(2026, 6, 10), 30_000.0, "receita_servicos")]
        )
        r = _gerar(linhas, 2026, 6)
        # jun/2025 (5.000) + jul/2025..mai/2026 (11 × 15.000)
        assert r.rbt12_anualizado == pytest.approx(5_000 + 11 * 15_000)

    def test_a_faixa_muda_por_causa_disso(self):
        """
        Incluindo junho, o RBT12 ia a R$ 195.000 e a faixa subia da 1 para a 2.
        """
        linhas = (
            [(dt.date(2025, 6, 10), 5_000.0, "receita_servicos")]
            + _receita_mensal([(2025, m) for m in range(7, 13)]
                              + [(2026, m) for m in range(1, 6)], 15_000.0)
            + [(dt.date(2026, 6, 10), 30_000.0, "receita_servicos")]
        )
        r = _gerar(linhas, 2026, 6)
        assert r.das_faixa.startswith("Faixa 1")

    def test_a_janela_cobre_doze_meses_inteiros(self):
        """Com receita constante, o RBT12 é exatamente 12 × a mensal."""
        r = _gerar(_receita_mensal(_ANO_ANTERIOR, 10_000.0)
                   + _receita_mensal([(2026, 8)], 10_000.0), 2026, 8)
        assert r.rbt12_anualizado == pytest.approx(12 * 10_000)

    def test_sem_historico_usa_o_mes_vezes_doze_e_avisa(self):
        r = _gerar(_receita_mensal([(2026, 3)], 10_000.0), 2026, 3)
        assert r.rbt12_anualizado == pytest.approx(120_000.0)
        assert "insuficiente" in r.das_observacao


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Fator R — Anexo III ou V
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestFatorR:
    """
    O relatório assumia Anexo III em silêncio. Serviço só é Anexo III quando a
    folha dos 12 meses anteriores é ≥ 28% da receita do mesmo período; abaixo
    disso é Anexo V, cuja primeira faixa é 15,5% contra 6% — 2,6× mais.
    """

    def _cenario(self, folha_mensal: float):
        linhas = _receita_mensal(_ANO_ANTERIOR, 10_000.0)
        if folha_mensal:
            linhas += [(dt.date(y, m, 5), -folha_mensal, "despesa_pessoal_pj")
                       for y, m in _ANO_ANTERIOR]
        linhas += _receita_mensal([(2026, 8)], 10_000.0)
        return _gerar(linhas, 2026, 8)

    def test_sem_folha_cai_no_anexo_V(self):
        r = self._cenario(0.0)
        assert r.das_anexo == "V"
        assert r.fator_r == 0.0
        assert r.das_aliquota_efetiva == pytest.approx(15.5)
        assert r.das_estimado == pytest.approx(10_000 * 0.155)

    def test_com_folha_acima_do_limite_e_anexo_III(self):
        r = self._cenario(4_000.0)   # 40% da receita
        assert r.das_anexo == "III"
        assert r.fator_r == pytest.approx(0.40)
        assert r.das_aliquota_efetiva == pytest.approx(6.0)
        assert r.das_estimado == pytest.approx(10_000 * 0.06)

    def test_a_diferenca_entre_os_anexos_e_relevante(self):
        sem, com = self._cenario(0.0), self._cenario(4_000.0)
        assert sem.das_estimado > 2.5 * com.das_estimado

    @pytest.mark.parametrize("folha,anexo", [
        (2_799.0, "V"),      # 27,99% — abaixo do limite
        (2_800.0, "III"),    # exatamente 28% — o limite é inclusivo
    ])
    def test_o_limite_de_28_por_cento_e_inclusivo(self, folha, anexo):
        assert FATOR_R_LIMITE == 0.28
        assert self._cenario(folha).das_anexo == anexo

    def test_a_observacao_explica_a_escolha(self):
        r = self._cenario(4_000.0)
        assert "Fator R" in r.das_observacao
        assert "5º-J" in r.das_observacao or "Anexo III" in r.das_observacao


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Receita, despesa e sinal
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestReceitaEDespesa:

    def test_credito_PJ_sem_subcategoria_e_receita(self):
        """
        O default era `despesa_outros_pj` para qualquer lançamento sem
        subcategoria, inclusive crédito: uma receita não reconhecida pelo
        classificador virava despesa. Erro duplo no lucro e DAS a MENOR.
        """
        r = _gerar([(dt.date(2026, 3, 10), 10_000.0, "receita_servicos"),
                    (dt.date(2026, 3, 15), 8_000.0, None)], 2026, 3)
        assert r.total_receita == pytest.approx(18_000.0)
        assert r.total_despesa == pytest.approx(0.0)
        assert r.lucro_estimado == pytest.approx(18_000.0)

    def test_debito_sem_subcategoria_continua_despesa(self):
        r = _gerar([(dt.date(2026, 3, 10), 10_000.0, "receita_servicos"),
                    (dt.date(2026, 3, 15), -2_000.0, None)], 2026, 3)
        assert r.total_receita == pytest.approx(10_000.0)
        assert r.total_despesa == pytest.approx(2_000.0)

    def test_estorno_abate_a_receita(self):
        r = _gerar([(dt.date(2026, 3, 10), 10_000.0, "receita_servicos"),
                    (dt.date(2026, 3, 20), -3_000.0, "receita_servicos")], 2026, 3)
        assert r.total_receita == pytest.approx(7_000.0)

    def test_estorno_maior_que_a_venda_nao_vira_receita(self):
        """
        `abs()` sobre o total do grupo invertia o sinal: um mês com
        R$ 2.000 de venda e R$ 5.000 de estorno virava R$ 3.000 de RECEITA,
        e o DAS era cobrado sobre devoluções.
        """
        r = _gerar([(dt.date(2026, 3, 5), 2_000.0, "receita_servicos"),
                    (dt.date(2026, 3, 20), -5_000.0, "receita_servicos")], 2026, 3)
        assert r.total_receita == pytest.approx(0.0)
        assert r.das_estimado == pytest.approx(0.0)
        assert r.lucro_estimado == pytest.approx(-3_000.0)
        # E a linha que o usuário lê também mostra o líquido, com sinal.
        linha = next(l for l in r.receitas if l.subcategory == "receita_servicos")
        assert linha.total == pytest.approx(-3_000.0)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# O que já estava certo — e precisa continuar
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestOQueJaEstavaCerto:

    def test_o_DAS_incide_sobre_a_receita_do_periodo_nao_sobre_o_RBT12(self):
        """
        O equívoco mais comum em calculadora de Simples. A faixa vem do RBT12;
        a alíquota efetiva incide sobre a receita do mês.
        """
        linhas = (_receita_mensal(_ANO_ANTERIOR, 30_000.0)
                  + [(dt.date(y, m, 5), -12_000.0, "despesa_pessoal_pj") for y, m in _ANO_ANTERIOR]
                  + _receita_mensal([(2026, 8)], 30_000.0))
        r = _gerar(linhas, 2026, 8)
        assert r.rbt12_anualizado == pytest.approx(360_000.0)
        assert r.das_estimado == pytest.approx(
            30_000.0 * r.das_aliquota_efetiva / 100, abs=0.05
        )
        assert r.das_estimado < r.rbt12_anualizado * 0.01 * r.das_aliquota_efetiva

    def test_acima_do_teto_nao_calcula_DAS(self):
        linhas = (_receita_mensal(_ANO_ANTERIOR, 500_000.0)
                  + _receita_mensal([(2026, 8)], 500_000.0))
        r = _gerar(linhas, 2026, 8)
        assert r.das_estimado == 0.0
        assert "Fora do Simples" in r.das_faixa

    def test_sem_receita_nao_ha_DAS(self):
        r = _gerar([(dt.date(2026, 3, 5), -800.0, "despesa_software")], 2026, 3)
        assert r.das_estimado == 0.0
        assert r.das_faixa == "Sem receita"

    def test_o_relatorio_avisa_que_MEI_estrito_paga_valor_fixo(self):
        """
        O cálculo é do Simples Nacional (ME/EPP). O MEI recolhe DAS de valor
        FIXO pelo SIMEI — quem lê "DAS estimado R$ 1.550" precisa saber qual
        regime o descreve.
        """
        r = _gerar(_receita_mensal(_ANO_ANTERIOR, 10_000.0)
                   + _receita_mensal([(2026, 8)], 10_000.0), 2026, 8)
        assert "SIMEI" in r.das_observacao
        assert "FIXO" in r.das_observacao
