"""
F5 — Raio-X de Custos contra extrato como ele chega em produção.

Não existia teste nenhum de `BankFeeAnalyzer` nem de `FeeDetector`: `tests/costs/`
só cobria o conector do Open Finance, e o único teste da rota verificava presença
de chaves, nunca valores (`assert isinstance(data.get("fee_breakdown", []), list)`
é vácuo — `fee_breakdown` nem é campo do modelo). Foi assim que três defeitos
sobreviveram:

  1. o VALOR DA OPERAÇÃO era contado como tarifa — uma TED de R$ 2.500 virava
     "tarifa de R$ 2.500"; num extrato realista o relatório inflava 114x;
  2. `analysis_months` era sempre 1, porque `get_transactions_for_user` entrega a
     coluna `date` e `_calc_period` procurava `transaction_date` — a projeção
     anual saía multiplicada pelo número de meses de histórico;
  3. banco nunca era identificado (`transactions_clean` não tem coluna de
     instituição), então tudo caía num balde comparado contra a média dos
     tradicionais, virando promessa de economia fabricada.

O ponto do arquivo é usar o vocabulário e as descrições REAIS: coluna `date`,
descrições como os bancos escrevem, e transferências/saques no meio.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from app.costs.bank_fee_analyzer import BankFeeAnalyzer
from app.costs.fee_detector import (
    BANCO_NAO_IDENTIFICADO,
    FeeDetector,
    banco_identificado,
    normalizar_extrato,
)
from app.costs.models import FeeType


def _extrato(linhas: list[dict], meses: int = 6, coluna_data: str = "date") -> pl.DataFrame:
    """Repete `linhas` por `meses`, no vocabulário que o banco entrega."""
    out = []
    for m in range(1, meses + 1):
        for i, linha in enumerate(linhas):
            out.append({coluna_data: date(2026, m, 10 + i), **linha})
    return pl.DataFrame(out)


# ── 1. Operação não é tarifa ─────────────────────────────────────────────────

class TestOperacaoNaoEtarifa:
    """
    O defeito de maior magnitude. `\\b(ted|doc)\\b` e `\\bsaque\\b` casavam o TIPO
    DE OPERAÇÃO, e o valor da linha é o dinheiro transferido/sacado — não a
    cobrança. A tarifa de TED no varejo é R$ 5–30; a TED em si, milhares.
    """

    @pytest.mark.parametrize(
        "descricao,valor",
        [
            ("TED ENVIADA JOAO DA SILVA",       2500.00),
            ("DOC PARA MARIA SOUZA",             800.00),
            ("SAQUE CAIXA ELETRONICO",          1200.00),
            ("SAQUE 24H BANCO",                  500.00),
            ("TRANSFERENCIA ENVIADA",           1500.00),
            ("PAGAMENTO JUROS EMPRESTIMO",       350.00),
        ],
    )
    def test_operacao_do_usuario_nao_vira_tarifa(self, descricao, valor):
        df = pl.DataFrame([{"date": date(2026, 3, 10), "amount": -valor,
                            "description": descricao}])
        assert FeeDetector().detect(df) == [], f"{descricao!r} contado como tarifa"

    @pytest.mark.parametrize(
        "descricao,valor,esperado",
        [
            ("TARIFA TED ENVIADA",        11.90, FeeType.TED_DOC),
            ("TAR TED",                   10.00, FeeType.TED_DOC),
            ("TARIFA DOC",                 9.50, FeeType.TED_DOC),
            ("TAR SAQUE REDE 24H",         6.50, FeeType.SAQUE),
            ("TARIFA SAQUE TERMINAL",      7.90, FeeType.SAQUE),
            ("JUROS ROTATIVO CARTAO",     89.00, FeeType.JUROS_ROTATIVO),
            ("ENCARGOS FATURA CARTAO",   120.00, FeeType.JUROS_ROTATIVO),
        ],
    )
    def test_a_cobranca_de_verdade_continua_detectada(self, descricao, valor, esperado):
        """Exigir marcador não pode virar falso negativo na tarifa real."""
        df = pl.DataFrame([{"date": date(2026, 3, 10), "amount": -valor,
                            "description": descricao}])
        fees = FeeDetector().detect(df)
        assert len(fees) == 1, f"{descricao!r} deixou de ser detectada"
        assert fees[0].fee_type == esperado
        assert fees[0].amount == pytest.approx(valor)

    def test_extrato_realista_nao_infla(self):
        """
        Antes: R$ 29.357,40 reportados contra R$ 901,80 reais — 114x.
        """
        df = _extrato([
            {"amount":  -42.90, "description": "TARIFA MANUTENCAO CONTA"},
            {"amount": -2500.00, "description": "TED ENVIADA JOAO DA SILVA"},
            {"amount":  -800.00, "description": "DOC PARA MARIA"},
            {"amount": -1200.00, "description": "SAQUE CAIXA ELETRONICO"},
            {"amount":  -350.00, "description": "PAGAMENTO JUROS EMPRESTIMO"},
            {"amount":   -11.90, "description": "TARIFA TED ENVIADA"},
            {"amount":    -6.50, "description": "TAR SAQUE REDE 24H"},
            {"amount":   -89.00, "description": "JUROS ROTATIVO CARTAO"},
        ])
        report = BankFeeAnalyzer().analyze(df, user_id="u")

        real = (42.90 + 11.90 + 6.50 + 89.00) * 6
        assert report.total_paid == pytest.approx(real, abs=0.01)

    @pytest.mark.parametrize(
        "descricao,valor",
        [
            ("TED ENVIADA JOAO",   100.00),
            ("SAQUE CAIXA",         80.00),
            ("DOC PARA MARIA",     120.00),
            ("TRANSFERENCIA JOAO",  99.00),
        ],
    )
    def test_operacao_PEQUENA_tambem_fica_fora(self, descricao, valor):
        """
        Trava separada do teto, de propósito. Estes valores estão ABAIXO do teto
        de R$ 150 do TED_DOC/SAQUE, então só o marcador explícito pode
        descartá-los. Sem este teste, reverter os padrões para os genéricos
        passava despercebido — o teto sozinho segurava as transferências
        grandes e dava a impressão de que os regex estavam travados.
        """
        df = pl.DataFrame([{"date": date(2026, 3, 10), "amount": -valor,
                            "description": descricao}])
        assert FeeDetector().detect(df) == [], (
            f"{descricao!r} de R$ {valor} passou — o marcador não está sendo exigido"
        )

    def test_teto_de_plausibilidade_descarta_com_log(self, caplog):
        """
        Segunda linha de defesa, para quando a descrição engana o regex.
        Descartar em silêncio seria trocar falso positivo por falso negativo
        invisível — por isso tem que aparecer no log.
        """
        df = pl.DataFrame([{"date": date(2026, 3, 10), "amount": -9_000.00,
                            "description": "TARIFA MANUTENCAO CONTA"}])
        with caplog.at_level("WARNING"):
            fees = FeeDetector().detect(df)

        assert fees == []
        assert any("teto" in r.getMessage() for r in caplog.records)

    def test_pix_continua_fora_do_ted(self):
        df = pl.DataFrame([{"date": date(2026, 3, 10), "amount": -50.00,
                            "description": "TARIFA DOC PIX ENVIADO"}])
        fees = FeeDetector().detect(df)
        assert all(f.fee_type != FeeType.TED_DOC for f in fees)


# ── 2. O período tem que sair do extrato ─────────────────────────────────────

class TestPeriodoAnalisado:
    """
    `get_transactions_for_user` entrega a coluna `date`; `_calc_period` procurava
    `transaction_date` e devolvia 1 mês para qualquer histórico. A projeção anual
    saía multiplicada pelo número de meses de dados — 12x para um ano.
    """

    @pytest.mark.parametrize("meses", [1, 3, 6, 12])
    def test_meses_saem_do_extrato_com_coluna_date(self, meses):
        df = _extrato([{"amount": -42.90, "description": "TARIFA MANUTENCAO CONTA"}],
                      meses=meses)
        report = BankFeeAnalyzer().analyze(df, user_id="u")

        assert report.analysis_months == meses
        assert report.monthly_avg == pytest.approx(42.90, abs=0.01)
        assert report.annual_projection == pytest.approx(42.90 * 12, abs=0.01)

    def test_date_e_transaction_date_dao_o_mesmo_relatorio(self):
        linhas = [{"amount": -42.90, "description": "TARIFA MANUTENCAO CONTA"}]
        por_date = BankFeeAnalyzer().analyze(_extrato(linhas, 6), user_id="u")
        por_tx = BankFeeAnalyzer().analyze(
            _extrato(linhas, 6, coluna_data="transaction_date"), user_id="u"
        )

        assert por_date.analysis_months == por_tx.analysis_months
        assert por_date.annual_projection == pytest.approx(por_tx.annual_projection)

    def test_periodo_nao_volta_nulo(self):
        df = _extrato([{"amount": -42.90, "description": "TARIFA MANUTENCAO CONTA"}], 6)
        report = BankFeeAnalyzer().analyze(df, user_id="u")

        assert report.period_start is not None
        assert report.period_end is not None
        assert report.period_start < report.period_end

    def test_normalizar_extrato_e_idempotente(self):
        df = _extrato([{"amount": -42.90, "description": "TARIFA"}], 2)
        uma = normalizar_extrato(df)
        duas = normalizar_extrato(uma)
        assert uma.columns == duas.columns
        assert uma.height == duas.height


# ── 3. Comparação só com banco identificado ──────────────────────────────────

class TestBenchmarkSoComBancoConhecido:
    """
    `transactions_clean` não tem coluna de instituição e a query não devolve
    nenhuma, então TODA tarifa caía em "Banco desconhecido" — que recebia a média
    dos tradicionais como proxy e virava economia em reais. Um usuário de banco
    digital era aconselhado a migrar para economizar.
    """

    def test_banco_nao_identificado_nao_gera_promessa_de_economia(self):
        df = _extrato([{"amount": -42.90, "description": "TARIFA MANUTENCAO CONTA"}], 6)
        report = BankFeeAnalyzer().analyze(df, user_id="u")

        assert report.by_bank[0].bank_name == BANCO_NAO_IDENTIFICADO
        assert report.savings_opportunity == 0.0

    def test_e_o_relatorio_diz_por_que(self):
        df = _extrato([{"amount": -42.90, "description": "TARIFA MANUTENCAO CONTA"}], 6)
        report = BankFeeAnalyzer().analyze(df, user_id="u")

        assert any("não puderam ser atribuídas" in w for w in report.warnings)

    def test_balde_de_sobra_nao_recebe_benchmark(self):
        df = _extrato([{"amount": -42.90, "description": "TARIFA MANUTENCAO CONTA"}], 6)
        report = BankFeeAnalyzer().analyze(df, user_id="u")

        nomes = {b.bank_name for b in report.market_benchmarks}
        assert BANCO_NAO_IDENTIFICADO not in nomes

    def test_com_institution_id_a_comparacao_volta(self):
        df = _extrato([{"amount": -42.90, "description": "TARIFA MANUTENCAO CONTA",
                        "institution_id": "itau"}], 6)
        report = BankFeeAnalyzer().analyze(df, user_id="u")

        assert report.by_bank[0].bank_name == "Itaú"
        assert "Itaú" in {b.bank_name for b in report.market_benchmarks}

    @pytest.mark.parametrize(
        "nome,identificado",
        [("Itaú", True), ("Nubank", True), ("Banco Inter", True),
         (BANCO_NAO_IDENTIFICADO, False), ("Banco (9999)", False)],
    )
    def test_banco_identificado(self, nome, identificado):
        assert banco_identificado(nome) is identificado

    def test_referencia_digital_continua_presente(self):
        """Decisão de produto: o usuário sempre vê que existe a opção zero."""
        df = _extrato([{"amount": -42.90, "description": "TARIFA MANUTENCAO CONTA",
                        "institution_id": "itau"}], 6)
        report = BankFeeAnalyzer().analyze(df, user_id="u")

        assert any(b.monthly_avg_market == 0.0 for b in report.market_benchmarks)


# ── 4. Os seis padrões sadios, que são o valor da feature ────────────────────

class TestCobrancasQueOUsuarioNaoSabiaQueTinha:
    """
    O output que move o produto não é o total anual — é a lista itemizada, que
    alimenta a Defesa (D1/D2) e o Negociador. Estes seis padrões são sadios por
    construção: quando a descrição diz "anuidade" ou "seguro prestamista", o
    valor da linha É a cobrança.
    """

    @pytest.mark.parametrize(
        "descricao,valor,esperado",
        [
            ("ANUIDADE CARTAO PARC 01/12",       12.00, FeeType.ANUIDADE_CARTAO),
            ("SEGURO PRESTAMISTA CONTRATO 4471", 38.90, FeeType.SEGURO_PRESTAMISTA),
            ("SEGURO RESIDENCIAL VINCULADO",     29.90, FeeType.SEGURO_EMBUTIDO),
            ("SEGURO HABITACIONAL MIP DFI",      54.20, FeeType.SEGURO_EMBUTIDO),
            ("PACOTE DE SERVICOS PREMIUM",       24.90, FeeType.PACOTE_SERVICOS),
            ("IOF OPERACAO CREDITO",              3.42, FeeType.IOF),
            ("TARIFA MANUTENCAO CONTA",          42.90, FeeType.TARIFA_MANUTENCAO),
        ],
    )
    def test_detecta_a_cobranca_e_o_valor(self, descricao, valor, esperado):
        df = pl.DataFrame([{"date": date(2026, 3, 10), "amount": -valor,
                            "description": descricao}])
        fees = FeeDetector().detect(df)

        assert len(fees) == 1
        assert fees[0].fee_type == esperado
        assert fees[0].amount == pytest.approx(valor)

    def test_seguro_embutido_e_o_sinal_de_venda_casada(self):
        """É o insumo do D1 — precisa sobreviver ao relatório inteiro."""
        df = _extrato([
            {"amount": -42.90, "description": "TARIFA MANUTENCAO CONTA"},
            {"amount": -54.20, "description": "SEGURO HABITACIONAL MIP DFI"},
        ], 6)
        report = BankFeeAnalyzer().analyze(df, user_id="u")

        assert FeeType.SEGURO_EMBUTIDO.value in report.by_fee_type
        assert report.by_fee_type[FeeType.SEGURO_EMBUTIDO.value] == pytest.approx(54.20 * 6)

    def test_ordem_de_prioridade_desambigua(self):
        """"seguro prestamista" casaria em TARIFA_MANUTENCAO se a ordem virasse."""
        df = pl.DataFrame([{"date": date(2026, 3, 10), "amount": -38.90,
                            "description": "TARIFA SEGURO PRESTAMISTA"}])
        assert FeeDetector().detect(df)[0].fee_type == FeeType.SEGURO_PRESTAMISTA


# ── 5. Sujeira que o extrato real traz ───────────────────────────────────────

class TestExtratoSujo:

    def test_credito_nunca_e_tarifa(self):
        """Estorno de tarifa é crédito — não pode virar cobrança."""
        df = pl.DataFrame([{"date": date(2026, 3, 10), "amount": 42.90,
                            "description": "ESTORNO TARIFA MANUTENCAO"}])
        assert FeeDetector().detect(df) == []

    def test_descricao_nula_nao_derruba(self):
        df = pl.DataFrame([{"date": date(2026, 3, 10), "amount": -42.90,
                            "description": None}])
        assert FeeDetector().detect(df) == []

    def test_extrato_vazio(self):
        report = BankFeeAnalyzer().analyze(pl.DataFrame(), user_id="u")
        assert report.total_paid == 0.0
        assert report.savings_opportunity == 0.0

    def test_sem_tarifa_nenhuma_avisa(self):
        df = _extrato([{"amount": -3500.00, "description": "ALUGUEL APARTAMENTO"}], 6)
        report = BankFeeAnalyzer().analyze(df, user_id="u")

        assert report.total_paid == 0.0
        assert any("Nenhuma tarifa" in w for w in report.warnings)

    def test_micro_cobranca_isolada_fica_fora(self):
        df = pl.DataFrame([{"date": date(2026, 3, 10), "amount": -0.30,
                            "description": "TARIFA"}])
        assert FeeDetector().detect(df) == []

    def test_acento_e_caixa_nao_importam(self):
        df = pl.DataFrame([{"date": date(2026, 3, 10), "amount": -38.90,
                            "description": "Seguro Prestamista Contrato"}])
        assert FeeDetector().detect(df)[0].fee_type == FeeType.SEGURO_PRESTAMISTA
