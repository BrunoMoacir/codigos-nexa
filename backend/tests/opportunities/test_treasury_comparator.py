# tests/opportunities/test_treasury_comparator.py
"""
OPP.3 — TreasuryComparatorService: Tesouro SELIC vs. melhor CDB de liquidez
diária vs. poupança, em rendimento líquido. Conectores mockados.

Também cobre a inclusão do Tesouro Selic no ranking do BankComparator
(rank(..., selic_annual=...)).
"""
from unittest.mock import patch

import pytest

from app.opportunities.services.bank_comparator import BankComparator
from app.opportunities.services.treasury_comparator import TreasuryComparatorService


def _service_with_mocked_rates(cdi=0.1465, selic=0.15, tr=0.0):
    service = TreasuryComparatorService()
    service._anbima = type("_A", (), {"get_cdi": staticmethod(lambda: cdi)})()
    service._bacen = type(
        "_B",
        (),
        {
            "get_selic": staticmethod(lambda: selic),
            "get_tr_monthly": staticmethod(lambda: tr),
        },
    )()
    return service


class TestComparacaoATres:
    def test_retorna_tres_entradas_ordenadas_por_liquido(self):
        result = _service_with_mocked_rates().compare(amount=10_000, holding_months=12)
        types = {e.investment_type for e in result.entries}
        assert {"TESOURO_SELIC", "POUPANCA"} <= types
        yields = [e.net_yield_brl for e in result.entries]
        assert yields == sorted(yields, reverse=True)

    def test_poupanca_perde_com_selic_alta(self):
        """Com SELIC 15%, qualquer alternativa líquida supera a poupança
        (0,5% a.m.) — a mensagem central do OPP."""
        result = _service_with_mocked_rates().compare(amount=10_000, holding_months=12)
        assert result.winner != "Poupança"
        assert result.winner_vs_savings_brl > 0

    def test_savings_annual_pct_usa_formula_oficial(self):
        # SELIC > 8,5% → 0,5% a.m. + TR → (1.005)^12 − 1 ≈ 6,17% a.a.
        result = _service_with_mocked_rates(tr=0.0).compare(amount=10_000)
        assert result.savings_annual_pct == pytest.approx(6.17, abs=0.01)

    def test_recommendation_quantifica_diferenca_vs_poupanca(self):
        result = _service_with_mocked_rates().compare(amount=10_000, holding_months=12)
        assert "poupança" in result.recommendation.lower()
        assert "R$" in result.recommendation

    def test_fallback_quando_conectores_falham(self):
        service = TreasuryComparatorService()
        service._anbima = type("_A", (), {"get_cdi": staticmethod(
            lambda: (_ for _ in ()).throw(Exception("fora")))})()
        service._bacen = type("_B", (), {
            "get_selic": staticmethod(lambda: (_ for _ in ()).throw(Exception("fora"))),
            "get_tr_monthly": staticmethod(lambda: 0.0),
        })()
        result = service.compare(amount=10_000)
        # cai nos defaults do módulo, sem quebrar
        assert result.selic_annual_pct > 0
        assert len(result.entries) >= 2


class TestTesouroNoRankingDoComparator:
    def test_rank_inclui_tesouro_quando_selic_informada(self):
        ranked = BankComparator().rank(
            amount=10_000, holding_months=12, cdi_annual=0.1465, selic_annual=0.15
        )
        tesouro = [i for i in ranked if i.product_type == "TESOURO_SELIC"]
        assert len(tesouro) == 1
        assert tesouro[0].bank_name == "Tesouro Direto"
        assert tesouro[0].index == "SELIC"
        assert tesouro[0].fgc_covered is False
        assert tesouro[0].steps  # OPP.5 — passos práticos presentes

    def test_rank_sem_selic_nao_inclui_tesouro(self):
        ranked = BankComparator().rank(amount=10_000, holding_months=12, cdi_annual=0.1465)
        assert not any(i.product_type == "TESOURO_SELIC" for i in ranked)

    def test_itens_do_catalogo_tem_steps_e_fgc(self):
        ranked = BankComparator().rank(amount=10_000, holding_months=12, cdi_annual=0.1465)
        assert all(i.steps for i in ranked)
        assert all(i.fgc_covered for i in ranked if i.product_type in ("CDB", "LCI", "LCA"))
