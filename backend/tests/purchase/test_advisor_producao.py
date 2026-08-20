"""
F7 — Compra Inteligente com o extrato como ele chega em produção.

Não existia teste algum do `PurchaseAdvisor` (872 das 1.910 linhas da feature);
`tests/purchase/` cobria só `post_purchase.py`. E os testes de integração
verificavam presença de chave e tamanho de lista, nunca um valor nem
`data_sources` — foi assim que QUATRO integrações ficaram mortas sem ninguém
ver:

    IncomeProfiler falhou: 'IncomeProfiler' object has no attribute 'analyze'
    safe_to_spend falhou: CashflowProjector.project() got an unexpected
                          keyword argument 'horizon_days'
    OptimizerService falhou: informe safe_to_spend ou monthly_income
    GoalTracker falhou: cannot import name 'get_db_session'

Com o safe-to-spend sempre em zero, TODO usuário lia "esta compra excede sua
margem disponível (R$ 0,00)" e recebia liquidez CRITICAL — inclusive quem tem
folga de sobra. E sem renda resolvida o otimizador recusava, o cashback nunca
entrava, e cartão à vista empatava com PIX até em centavos.

A classe `TestFontesDeContextoVivas` é a que teria pego tudo isso no dia um.
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import polars as pl
import pytest

from app.purchase.models import PaymentMethod, PaymentOption, PurchaseRequest
from app.purchase.opportunity_cost import (
    _cdi_net_monthly,
    _FLOAT_CARTAO_MESES,
    apply_opportunity_cost,
)
from app.purchase.purchase_advisor import PurchaseAdvisor

_CDI = 0.1475


def _extrato(renda=9_000.0, aluguel=2_800.0, saldo=14_000.0, meses=8) -> pl.DataFrame:
    """Extrato no vocabulário que `get_transactions_for_user` devolve: `date`."""
    linhas = []
    for m in range(1, meses + 1):
        linhas += [
            {"date": dt.date(2026, m, 5), "amount": renda,
             "description": "SALARIO EMPRESA XYZ", "category": "Renda", "balance": saldo},
            {"date": dt.date(2026, m, 10), "amount": -aluguel,
             "description": "ALUGUEL", "category": "Moradia", "balance": saldo - aluguel},
            {"date": dt.date(2026, m, 18), "amount": -450.0,
             "description": "IFOOD", "category": "Delivery", "balance": saldo - aluguel - 450},
        ]
    return pl.DataFrame(linhas)


def _analisar(df: pl.DataFrame | None = None, **kw):
    df = _extrato() if df is None else df
    pedido = {"user_id": "u", "amount": 3_000.0, "category": "Eletrônicos",
              "installments": 12, **kw}
    with patch.object(PurchaseAdvisor, "_fetch_transactions", return_value=df):
        return PurchaseAdvisor().analyze(PurchaseRequest(**pedido))


def _opcao(rec, metodo: PaymentMethod) -> PaymentOption:
    return next(o for o in rec.options if o.method == metodo)


# ── 1. As fontes de contexto precisam estar VIVAS ────────────────────────────

class TestFontesDeContextoVivas:
    """
    A feature É o contexto. Uma calculadora de VPL qualquer um faz; o que a
    Nexa promete é a conta com o SEU caixa e o SEU cartão. Se a fonte cai no
    except, a feature deixa de ser o que é — em silêncio, porque cada fetcher
    engole a exceção e devolve None.
    """

    @pytest.mark.parametrize(
        "fonte",
        ["transactions_db", "income_profiler", "f1_safe_to_spend", "optimizer_f2"],
    )
    def test_fonte_esta_viva(self, fonte):
        assert fonte in _analisar().data_sources, (
            f"{fonte} caiu no except — a integração quebrou de novo"
        )

    def test_sem_avisos_de_integracao_quebrada(self):
        rec = _analisar()
        for aviso in rec.warnings:
            assert "indisponível" not in aviso.lower(), aviso
            assert "não foi possível" not in aviso.lower(), aviso

    def test_renda_e_derivada_sem_o_usuario_digitar(self):
        """
        `IncomeProfiler` só tem `build`; a chamada era `.analyze`. Com ela
        morta, a renda vinha None e o usuário PRECISAVA digitá-la — justamente
        no fluxo de checkout, onde ninguém digita.
        """
        rec = _analisar(monthly_income=None)
        assert "income_profiler" in rec.data_sources
        assert _opcao(rec, PaymentMethod.CARTAO_AVISTA).reward_value > 0

    def test_confianca_alta_quando_ha_dado(self):
        assert _analisar().confidence_score >= 0.9


# ── 2. Margem real, não zero permanente ──────────────────────────────────────

class TestMargemDeVerdade:
    """
    `horizon_days` é parâmetro do CONSTRUTOR do CashflowProjector, nunca de
    `project()`. Passá-lo ao método estourava TypeError em toda chamada.
    """

    def test_usuario_folgado_nao_recebe_alarme(self):
        rec = _analisar()
        assert rec.liquidity_impact.safe_to_spend_before > 0
        assert rec.liquidity_impact.risk_level == "LOW"
        assert not any("excede sua margem" in w for w in rec.warnings)
        assert "excede sua margem" not in rec.reasoning

    def test_usuario_apertado_recebe_alarme(self):
        """A trava não pode ter virado 'nunca alerta'."""
        rec = _analisar(_extrato(renda=4_000.0, aluguel=3_200.0, saldo=1_200.0))
        assert rec.liquidity_impact.risk_level in ("CRITICAL", "HIGH")

    def test_margem_cai_pelo_desembolso_mensal(self):
        rec = _analisar()
        li = rec.liquidity_impact
        assert li.safe_to_spend_after < li.safe_to_spend_before

    def test_sem_ancora_de_saldo_avisa_em_vez_de_zerar(self):
        """
        Zerar a margem em silêncio é pior que dizer que não sabe: um zero é
        indistinguível de "você não tem folga nenhuma".
        """
        sem_saldo = _extrato().drop("balance")
        with patch("app.core.db.balances.get_latest_balance", return_value=None):
            rec = _analisar(sem_saldo)
        assert any("Safe-to-spend" in w for w in rec.warnings)


# ── 3. Matemática: tudo no mesmo instante de referência ──────────────────────

class TestValorPresente:

    def _opt(self, metodo, total, n=1, reward=0.0):
        return PaymentOption(
            method=metodo, label="x", total_cost=total,
            monthly_cost=(total / n if n > 1 else None),
            installments=n, reward_value=reward,
        )

    def test_pix_e_a_referencia_do_zero(self):
        """Único desembolso realmente feito hoje — não ganha nem perde tempo."""
        o = apply_opportunity_cost(self._opt(PaymentMethod.PIX_AVISTA, 3_000.0), _CDI)
        assert o.opportunity_cost_gain == 0.0
        assert o.net_cost_real == pytest.approx(3_000.0)

    def test_cartao_a_vista_ganha_o_float_da_fatura(self):
        """
        Antes recebia a MESMA penalidade do PIX, como se saísse do bolso hoje.
        Com cashback zero as duas opções empatavam — quando o cartão é
        estritamente melhor: a fatura vence ~30 dias depois.
        """
        pix = apply_opportunity_cost(self._opt(PaymentMethod.PIX_AVISTA, 3_000.0), _CDI)
        cartao = apply_opportunity_cost(self._opt(PaymentMethod.CARTAO_AVISTA, 3_000.0), _CDI)

        assert cartao.net_cost_real < pix.net_cost_real
        r = _cdi_net_monthly(_CDI, 1)
        esperado = 3_000.0 - 3_000.0 / (1 + r) ** _FLOAT_CARTAO_MESES
        assert cartao.opportunity_cost_gain == pytest.approx(esperado, abs=0.01)

    def test_parcelas_caem_nos_meses_1_a_n(self):
        """
        O expoente era `(n−k)`, que dá à PRIMEIRA parcela o maior rendimento e
        à última nenhum — convenção de pagamento no ato. Parcela de cartão cai
        na fatura seguinte.
        """
        n = 12
        o = apply_opportunity_cost(
            self._opt(PaymentMethod.CARTAO_PARCELADO, 3_000.0, n=n), _CDI
        )
        r = _cdi_net_monthly(_CDI, n)
        vpl = sum((3_000.0 / n) / (1 + r) ** k for k in range(1, n + 1))
        assert o.net_cost_real == pytest.approx(vpl, abs=0.01)

    def test_cdc_entra_na_mesma_regua(self):
        """
        Era medido em reais NOMINAIS somados enquanto as outras opções ganhavam
        crédito de tempo — R$ 222 de inconsistência em R$ 3.000/12x. Descontar
        não apaga os juros do CDC; só permite comparar.
        """
        n = 12
        total = 3_869.34   # PMT 322,44 × 12 a 4,15% a.m.
        o = apply_opportunity_cost(self._opt(PaymentMethod.FINANCIAMENTO, total, n=n), _CDI)

        assert o.opportunity_cost_gain > 0, "CDC ficou sem desconto de tempo"
        assert o.net_cost_real < total
        assert o.net_cost_real > 3_000.0, "o CDC continua sendo a pior opção"

    def test_ordem_economica_com_folga(self):
        """parcelado < cartão à vista < PIX < CDC, para preços iguais."""
        rec = _analisar()
        ordem = [o.method for o in rec.options]
        assert ordem.index(PaymentMethod.CARTAO_PARCELADO) < ordem.index(PaymentMethod.CARTAO_AVISTA)
        assert ordem.index(PaymentMethod.CARTAO_AVISTA) < ordem.index(PaymentMethod.PIX_AVISTA)
        assert ordem[-1] == PaymentMethod.FINANCIAMENTO

    def test_prazo_maior_desconta_mais(self):
        curto = apply_opportunity_cost(self._opt(PaymentMethod.CARTAO_PARCELADO, 3_000.0, n=3), _CDI)
        longo = apply_opportunity_cost(self._opt(PaymentMethod.CARTAO_PARCELADO, 3_000.0, n=24), _CDI)
        assert longo.net_cost_real < curto.net_cost_real


# ── 4. A pergunta de abertura da feature ─────────────────────────────────────

class TestDescontoAVista:
    """
    "Pix com 10% de desconto ou 12x sem juros?" é a pergunta que a doc usa para
    abrir a feature — e não havia onde informar o preço à vista. Com um preço
    só, o PIX perde por construção: carrega custo de oportunidade e nenhum
    ganho.
    """

    def test_sem_desconto_o_cartao_vence(self):
        rec = _analisar(cash_price=None)
        assert rec.recommended_method in (
            PaymentMethod.CARTAO_PARCELADO, PaymentMethod.CARTAO_AVISTA
        )

    def test_desconto_de_10_porcento_vira_o_jogo(self):
        rec = _analisar(cash_price=2_700.0)
        assert rec.recommended_method == PaymentMethod.PIX_AVISTA
        assert _opcao(rec, PaymentMethod.PIX_AVISTA).net_cost_real == pytest.approx(2_700.0)

    @pytest.mark.parametrize("desconto,vencedor_pix", [(0.02, False), (0.15, True)])
    def test_o_ponto_de_virada_depende_do_desconto(self, desconto, vencedor_pix):
        rec = _analisar(cash_price=3_000.0 * (1 - desconto))
        venceu = rec.recommended_method == PaymentMethod.PIX_AVISTA
        assert venceu is vencedor_pix

    def test_desconto_aparece_na_nota_da_opcao(self):
        rec = _analisar(cash_price=2_700.0)
        assert "esconto" in _opcao(rec, PaymentMethod.PIX_AVISTA).notes

    def test_parcelado_com_juros_embutidos(self):
        """
        O "12x sem juros" que embute juros no preço: total maior que o à vista.
        """
        rec = _analisar(installments_total=3_360.0)
        assert _opcao(rec, PaymentMethod.CARTAO_PARCELADO).total_cost == pytest.approx(3_360.0)

    def test_precos_incoerentes_sao_recusados(self):
        with pytest.raises(ValueError):
            PurchaseRequest(user_id="u", amount=3_000.0, category="X", cash_price=3_500.0)
        with pytest.raises(ValueError):
            PurchaseRequest(user_id="u", amount=3_000.0, category="X", installments_total=2_500.0)


# ── 5. Penalidade de ritmo só quando a capacidade acusa ──────────────────────

class TestPenalidadeDeRitmo:
    """
    Burn rate mede RITMO (gastei rápido este mês), não CAPACIDADE. E dispara
    com facilidade — um usuário gastando 12% da renda já sai como WARNING, e
    despesa fixa como aluguel aparece "acima do ritmo" todo dia 10.

    Sem trava, o mesmo relatório dizia "risco LOW, margem de R$ 10.262" e
    encarecia o parcelado em 11%, empurrando-o para trás do à vista — quando
    adiar pagamento com caixa sobrando é exatamente o que faz sentido.
    """

    def test_folga_confortavel_nao_penaliza(self):
        rec = _analisar()
        parcelado = _opcao(rec, PaymentMethod.CARTAO_PARCELADO)
        r = _cdi_net_monthly(_CDI, 12)
        vpl = sum((3_000.0 / 12) / (1 + r) ** k for k in range(1, 13))
        assert parcelado.net_cost_real <= vpl + 0.01

    def test_sem_folga_penaliza(self):
        rec = _analisar(_extrato(renda=4_000.0, aluguel=3_200.0, saldo=1_200.0))
        ordem = [o.method for o in rec.options]
        assert ordem.index(PaymentMethod.CARTAO_AVISTA) < ordem.index(PaymentMethod.CARTAO_PARCELADO)


# ── 6. Extrato sujo ──────────────────────────────────────────────────────────

class TestExtratoSujo:

    def test_sem_historico_nao_derruba(self):
        rec = _analisar(pl.DataFrame())
        assert rec.options
        assert any("Sem histórico" in w for w in rec.warnings)

    def test_coluna_date_e_transaction_date_dao_o_mesmo(self):
        por_date = _analisar(_extrato())
        por_tx = _analisar(_extrato().rename({"date": "transaction_date"}))
        assert por_date.recommended_method == por_tx.recommended_method
        assert por_date.liquidity_impact.safe_to_spend_before == pytest.approx(
            por_tx.liquidity_impact.safe_to_spend_before, abs=0.01
        )

    def test_a_vista_nao_oferece_cdc(self):
        rec = _analisar(installments=1)
        assert PaymentMethod.FINANCIAMENTO not in [o.method for o in rec.options]

    def test_valor_baixo_nao_oferece_cdc(self):
        rec = _analisar(amount=500.0, installments=12)
        assert PaymentMethod.FINANCIAMENTO not in [o.method for o in rec.options]

    def test_nunca_recomenda_opcao_marcada_evitar(self):
        rec = _analisar(_extrato(renda=4_000.0, aluguel=3_200.0, saldo=1_200.0))
        recomendada = _opcao(rec, rec.recommended_method)
        assert recomendada.profile_fit != "EVITAR"


class TestPerguntasEmAberto:
    """
    O que a Nexa não sabe e que mudaria a resposta vira pergunta — com o ponto
    de virada JÁ CALCULADO.

    A disciplina é não perguntar por perguntar. "A loja dá desconto no Pix?"
    perguntado sempre é ruído; perguntado com "a partir de 7,1% o Pix passa à
    frente, hoje ele perde por R$ 213" é a análise continuando por outro meio.
    """

    def _ids(self, rec) -> set[str]:
        return {q.question_id for q in rec.follow_up_questions}

    def test_pergunta_o_desconto_a_vista(self):
        rec = _analisar()
        assert "cash_price" in self._ids(rec)

    def test_nao_repergunta_o_que_ja_foi_informado(self):
        rec = _analisar(cash_price=2_700.0)
        assert "cash_price" not in self._ids(rec)

    def test_o_ponto_de_virada_do_desconto_e_exato(self):
        """
        A pergunta afirma um número. Realimentado, o veredito tem que virar
        exatamente ali — senão é chute com casas decimais.
        """
        rec = _analisar()
        pergunta = next(q for q in rec.follow_up_questions if q.question_id == "cash_price")

        assert pergunta.breakeven is not None
        assert _analisar(cash_price=pergunta.breakeven).recommended_method == PaymentMethod.PIX_AVISTA
        assert _analisar(cash_price=pergunta.breakeven + 15).recommended_method != PaymentMethod.PIX_AVISTA

    def test_o_ponto_de_virada_do_parcelado_e_exato(self):
        rec = _analisar()
        pergunta = next(
            q for q in rec.follow_up_questions if q.question_id == "installments_total"
        )

        assert pergunta.breakeven is not None
        acima = _analisar(installments_total=pergunta.breakeven + 15)
        assert acima.recommended_method != PaymentMethod.CARTAO_PARCELADO

    def test_pergunta_carrega_o_numero_no_texto(self):
        """Pergunta sem número é formulário; com número é análise."""
        rec = _analisar()
        for q in rec.follow_up_questions:
            if q.breakeven is not None:
                assert "R$" in q.question

    def test_pergunta_a_renda_so_quando_nao_da_para_derivar(self):
        com_historico = _analisar()
        assert "monthly_income" not in self._ids(com_historico)

        sem_historico = _analisar(pl.DataFrame())
        assert "monthly_income" in self._ids(sem_historico)

    def test_pergunta_o_saldo_quando_a_margem_falta(self):
        sem_saldo = _extrato().drop("balance")
        with patch("app.core.db.balances.get_latest_balance", return_value=None):
            rec = _analisar(sem_saldo)
        assert "saldo_atual" in self._ids(rec)

    def test_prioridade_reflete_o_impacto(self):
        rec = _analisar()
        por_id = {q.question_id: q for q in rec.follow_up_questions}
        # o desconto vira o veredito; o total do parcelado só ajusta a margem
        assert por_id["cash_price"].priority == "HIGH"
        assert por_id["installments_total"].priority == "MEDIUM"

    def test_campo_apontado_existe_no_request(self):
        """`field_to_populate` tem que ser um campo de verdade, ou o front erra."""
        campos = set(PurchaseRequest.model_fields) | {"current_balance"}
        for q in _analisar().follow_up_questions:
            assert q.field_to_populate in campos, q.field_to_populate

    def test_a_tool_do_agente_expoe_as_perguntas(self):
        from app.agent.tools.get_purchase_recommendation import get_purchase_recommendation

        with patch.object(PurchaseAdvisor, "_fetch_transactions", return_value=_extrato()):
            saida = get_purchase_recommendation.invoke({
                "user_id": "u", "amount": 3_000.0,
                "category": "Eletrônicos", "installments": 12,
            })
        assert "O que eu não sei" in saida
        assert "desconto no Pix" in saida

    def test_a_tool_aceita_a_resposta(self):
        from app.agent.tools.get_purchase_recommendation import get_purchase_recommendation

        with patch.object(PurchaseAdvisor, "_fetch_transactions", return_value=_extrato()):
            saida = get_purchase_recommendation.invoke({
                "user_id": "u", "amount": 3_000.0, "category": "Eletrônicos",
                "installments": 12, "cash_price": 2_700.0,
            })
        assert "PIX à vista" in saida.split("Recomendação:")[1].split("\n")[0]

