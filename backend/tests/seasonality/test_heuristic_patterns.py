"""
Golden tests das heurísticas de retenção, com descrições REAIS extraídas
dos corpora de calibração (data/transactions.duckdb, 12.209 transações, e
transactions_clean do Postgres dev, 2.912 transações).

Se um destes testes quebrar ao "melhorar" um padrão, a mudança regrediu
um caso real medido — rodar scripts/calibrate_retention_heuristics.py
antes de alterar.
"""

import pytest

from app.purchase.post_purchase import (
    _INSTALLMENT_PATTERN,
    _NON_PURCHASE_PATTERNS,
    PostPurchaseAnalyzer,
)
from app.seasonality.profile_probe import MEI_REGEX, SALARY_REGEX


class TestMeiRegex:
    @pytest.mark.parametrize("desc", [
        "IMPOSTO DAS MEI",                    # PG real — 138 ocorrências
        "das 06/2026 simples nacional",
        "pagamento das",
        "guia das mei",
        "PGMEI documento de arrecadacao",
        "DASN SIMEI declaracao",
        "simples nacional das",
    ])
    def test_positivos_reais(self, desc):
        assert MEI_REGEX.search(desc)

    @pytest.mark.parametrize("desc", [
        "casas bahia tv samsung 55 polegadas 2x",   # FP real do LIKE antigo
        "casas bahia tv samsung 55 polegadas 1x",
        "lojas das americanas compra",
        "tv 40 polegadas smart",
        "compra no débito - uber *trip",
        "pedidas delivery",
    ])
    def test_negativos_reais(self, desc):
        assert not MEI_REGEX.search(desc)


class TestSalaryRegex:
    @pytest.mark.parametrize("desc", [
        "salario - empresa xyz ltda",                       # duckdb real
        "pix recebido - empresa tech ltda - salario mensal",
        "SALARIO EMPRESA NEXA",                             # PG real
        "credito folha pagamento",
        "proventos outubro",
        "remuneracao mensal",
        "pro-labore socio",
    ])
    def test_positivos_reais(self, desc):
        assert SALARY_REGEX.search(desc)

    @pytest.mark.parametrize("desc", [
        "pix recebido - maria silva",       # transferência de pessoa física
        "FATURA CLIENTE PJ",                # receita PJ ≠ salário CLT
        "PIX RECEBIDO CLIENTE",
        "rendimento poupanca",
        "ted recebida - joao santos",
    ])
    def test_negativos_reais(self, desc):
        assert not SALARY_REGEX.search(desc)


class TestNonPurchaseFilter:
    @pytest.mark.parametrize("desc", [
        "unimed paulistana plano saude familiar",   # passava como compra
        "CONTA ENERGIA",                            # passava como compra
        "conta de internet fibra",
        "mensalidade escola objetivo ensino fundamental",
        "ted enviada - aluguel apartamento",
        "boleto condominio edificio",
        "JUROS CARTAO ROTATIVO ITAU",
        "ANUIDADE CARTAO PLATINUM",
        "iptu - prefeitura municipal sp parcela",
    ])
    def test_obrigacoes_excluidas(self, desc):
        assert _NON_PURCHASE_PATTERNS.search(desc)

    @pytest.mark.parametrize("desc", [
        "casas bahia tv samsung 55 polegadas",   # compra real
        "magazine luiza notebook dell",
        "passagem aerea - viagem negocios",
        "papelaria empresarial ltda",
        "POSTO COMBUSTIVEL",
        "MERCADO CENTRAL",
    ])
    def test_compras_mantidas(self, desc):
        assert not _NON_PURCHASE_PATTERNS.search(desc)


class TestInstallmentAndPaymentMethod:
    @pytest.mark.parametrize("desc", [
        "compra parcelada 3/12 - magazine luiza",
        "parcela 2/10 - magazine luiza notebook dell",
        "CELULAR PRO MAX 1/12",
        "CURSO ESPECIALIZACAO 3/10",
    ])
    def test_parcelamento_detectado(self, desc):
        assert _INSTALLMENT_PATTERN.search(desc)

    def test_parcelamento_nao_confunde_com_data(self):
        # "das 06/2026" tem dd/dddd — não é marcador n/m de parcela
        assert not _INSTALLMENT_PATTERN.search("pagamento avista loja")

    @pytest.mark.parametrize("desc,expected", [
        ("pagamento pix - mercado livre", "PIX_AVISTA"),
        ("compra cartao - supermercado zona sul", "CARTAO_AVISTA"),
        ("compra no débito - uber *trip abc123", "DEBITO_AVISTA"),
        ("ifood *pedido - restaurante abc", "DEBITO_AVISTA"),
        ("MERCADO CENTRAL", "DEBITO_AVISTA"),
    ])
    def test_meio_de_pagamento_em_descricoes_reais(self, desc, expected):
        method, _ = PostPurchaseAnalyzer._infer_paid_method(desc)
        assert method == expected
