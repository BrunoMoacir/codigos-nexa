"""
PF/PJ pela direção do dinheiro.

As regras antigas olhavam só a palavra ("salario" e "aluguel" = PJ) e
qualquer valor acima de R$ 2.000 virava empresa: o salário CLT da persona Ana
aparecia como receita PJ (DAS de R$ 10 mil para quem não é MEI, renda PF
zerada no Optimizer), enquanto a maquininha do Bruno, que é MEI, ficava
UNCERTAIN e o fiscal dele dizia "sem receita".
"""

import polars as pl
import pytest

from app.divider.classifier import PFPJClassifier, PFPJFallbackClassifier

CASOS = [
    # renda de pessoa física
    ("credito salario folha mensal acme ltda", 8500, "PF"),
    ("credito 13 salario folha acme", 8500, "PF"),
    ("restituicao irpf lote", 1840, "PF"),
    ("pix recebido pagamento cliente", 4800, "PF"),
    # receita do negócio
    ("pagbank *venda maquininha", 350, "PJ"),
    ("stone *recebimento", 700, "PJ"),
    ("mercado pago venda", 600, "PJ"),
    ("pix recebido cliente pj nota fiscal", 900, "PJ"),
    ("pix recebido prestacao servico marcenaria", 1200, "PJ"),
    # despesa do negócio
    ("pagamento salario funcionario", -1800, "PJ"),
    ("aluguel sala comercial centro", -1500, "PJ"),
    ("das mei competencia", -75, "PJ"),
    ("pagamento empresa ltda", -500, "PJ"),
    # consumo da família, inclusive o caro
    ("aluguel apartamento imobiliaria", -2100, "PF"),
    ("aluguel kitnet", -1500, "PF"),
    ("pix samsung smartphone galaxy", -4800, "UNCERTAIN"),
    ("uber trip", -30, "PF"),
]


@pytest.mark.parametrize("descricao,valor,esperado", CASOS)
def test_regra_unitaria(descricao, valor, esperado):
    assert PFPJFallbackClassifier().classify({"description": descricao, "amount": valor}) == esperado


def test_lote_vetorizado_igual_a_regra_unitaria():
    df = pl.DataFrame({
        "description": [c[0] for c in CASOS],
        "amount": [float(c[1]) for c in CASOS],
        "category": [None] * len(CASOS),
    })
    out = PFPJClassifier().classify_batch(df)
    assert out["pf_pj_label"].to_list() == [c[2] for c in CASOS]


def test_recebimento_pequeno_de_maquininha_e_receita_e_nao_despesa():
    """Crédito PJ ≤ R$ 500 caía em despesa_outros_pj e virava despesa no fiscal."""
    df = pl.DataFrame({"description": ["pagbank *venda maquininha", "pix recebido cliente pj"],
                       "amount": [180.0, 90.0], "category": [None, None]})
    subs = PFPJClassifier().classify_batch(df)["pj_subcategory"].to_list()
    assert all(s.startswith("receita_") for s in subs), subs


def test_salario_de_credito_e_pf_mesmo_com_categoria_salary():
    df = pl.DataFrame({"description": ["credito salario"], "amount": [5000.0], "category": ["SALARY"]})
    assert PFPJClassifier().classify_batch(df)["pf_pj_label"].to_list() == ["PF"]
