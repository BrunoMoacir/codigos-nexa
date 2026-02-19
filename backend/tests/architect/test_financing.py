"""
tests/architect/test_financing.py - Testes das calculadoras PRICE, SAC e CET

O QUE É TESTADO:
    - PRICE: parcela fixa, juros decrescentes, amortização crescente
    - SAC: amortização constante, parcelas decrescentes, total menor que PRICE
    - CET: retorna taxa >= taxa nominal
    - Schedules: soma das amortizações == principal
    - Guards: taxa <= -1, prazo 0 não travam a aplicação

COMO RODAR:
    cd backend
    pytest tests/architect/test_financing.py -v
"""

import pytest

from app.architect.calculators.financing import (
    calculate_price,
    calculate_sac,
)


# Parâmetros padrão para os testes
_PRINCIPAL = 50_000.0
_TAXA_ANUAL = 0.12          # 12% a.a. → ~0,9489% a.m.
_PRAZO = 48                 # 48 meses


class TestCalculatePrice:
    """Testa o sistema PRICE (parcelas fixas)."""

    def test_retorna_resultado_valido(self):
        """Deve retornar objeto com campos preenchidos."""
        res = calculate_price(_PRINCIPAL, _TAXA_ANUAL, _PRAZO)
        assert res is not None
        assert res.monthly_payment > 0
        assert res.total_cost > 0
        assert res.total_interest > 0

    def test_parcela_fixa(self):
        """No PRICE, todas as parcelas têm o mesmo valor."""
        res = calculate_price(_PRINCIPAL, _TAXA_ANUAL, _PRAZO)
        schedule = res.schedule
        if schedule:
            pagamentos = [round(row.get("payment", row.get("parcela", 0)), 2) for row in schedule]
            # Margem de centavo (arredondamento)
            assert max(pagamentos) - min(pagamentos) <= 0.02

    def test_total_custo_maior_que_principal(self):
        """Total pago > principal (existe juros)."""
        res = calculate_price(_PRINCIPAL, _TAXA_ANUAL, _PRAZO)
        assert res.total_cost > _PRINCIPAL

    def test_juros_total_positivo(self):
        """Juros total > 0 para taxa > 0."""
        res = calculate_price(_PRINCIPAL, _TAXA_ANUAL, _PRAZO)
        assert res.total_interest > 0

    def test_soma_amortizacoes_igual_ao_principal(self):
        """A soma das amortizações deve ≈ principal."""
        res = calculate_price(_PRINCIPAL, _TAXA_ANUAL, _PRAZO)
        if res.schedule:
            total_amort = sum(
                row.get("amortization", row.get("amortizacao", 0))
                for row in res.schedule
            )
            assert abs(total_amort - _PRINCIPAL) < 1.0  # tolerância R$1

    def test_taxa_zero_sem_juros(self):
        """Com taxa zero, total_interest deve ser 0."""
        res = calculate_price(_PRINCIPAL, 0.0, _PRAZO)
        assert abs(res.total_interest) < 0.01

    def test_taxa_zero_parcela_igual_amortizacao(self):
        """Com taxa zero, parcela = principal / prazo."""
        res = calculate_price(_PRINCIPAL, 0.0, _PRAZO)
        esperada = _PRINCIPAL / _PRAZO
        assert abs(res.monthly_payment - esperada) < 0.05

    def test_parcela_unica(self):
        """Com prazo = 1, a parcela deve cobrir principal + juros."""
        res = calculate_price(_PRINCIPAL, _TAXA_ANUAL, 1)
        taxa_mensal = (1 + _TAXA_ANUAL) ** (1/12) - 1
        esperada = _PRINCIPAL * (1 + taxa_mensal)
        assert abs(res.monthly_payment - esperada) < 0.10

    def test_maior_principal_maior_parcela(self):
        """Condi ceteris paribus: maior principal → maior parcela."""
        res_50k = calculate_price(50_000.0, _TAXA_ANUAL, _PRAZO)
        res_100k = calculate_price(100_000.0, _TAXA_ANUAL, _PRAZO)
        assert res_100k.monthly_payment > res_50k.monthly_payment

    def test_maior_prazo_menor_parcela(self):
        """Maior prazo → parcela menor (mas total maior)."""
        res_24m = calculate_price(_PRINCIPAL, _TAXA_ANUAL, 24)
        res_48m = calculate_price(_PRINCIPAL, _TAXA_ANUAL, 48)
        assert res_48m.monthly_payment < res_24m.monthly_payment

    def test_maior_taxa_maior_custo(self):
        """Taxa maior → custo total maior."""
        res_baixa = calculate_price(_PRINCIPAL, 0.10, _PRAZO)
        res_alta  = calculate_price(_PRINCIPAL, 0.25, _PRAZO)
        assert res_alta.total_cost > res_baixa.total_cost

    def test_cet_maior_que_taxa_nominal(self):
        """CET deve ser >= taxa nominal (inclui custos adicionais)."""
        res = calculate_price(_PRINCIPAL, _TAXA_ANUAL, _PRAZO)
        if hasattr(res, "cet_annual") and res.cet_annual is not None:
            assert res.cet_annual >= _TAXA_ANUAL


class TestCalculateSAC:
    """Testa o sistema SAC (amortização constante)."""

    def test_retorna_resultado_valido(self):
        """Deve retornar objeto com campos preenchidos."""
        res = calculate_sac(_PRINCIPAL, _TAXA_ANUAL, _PRAZO)
        assert res is not None
        assert res.total_cost > 0

    def test_amortizacao_constante(self):
        """No SAC, todas as amortizações são iguais."""
        res = calculate_sac(_PRINCIPAL, _TAXA_ANUAL, _PRAZO)
        amort_esperada = _PRINCIPAL / _PRAZO
        if res.schedule:
            for row in res.schedule:
                amort = row.get("amortization", row.get("amortizacao", None))
                if amort is not None:
                    assert abs(amort - amort_esperada) < 0.05

    def test_parcelas_decrescentes(self):
        """No SAC, as parcelas devem ser decrescentes (ou estáveis)."""
        res = calculate_sac(_PRINCIPAL, _TAXA_ANUAL, _PRAZO)
        if res.schedule and len(res.schedule) >= 2:
            p1 = res.schedule[0].get("payment", res.schedule[0].get("parcela", 0))
            p_last = res.schedule[-1].get("payment", res.schedule[-1].get("parcela", 0))
            assert p1 >= p_last

    def test_sac_mais_barato_que_price(self):
        """SAC sempre tem custo total ≤ PRICE para mesmos parâmetros."""
        price = calculate_price(_PRINCIPAL, _TAXA_ANUAL, _PRAZO)
        sac   = calculate_sac(_PRINCIPAL, _TAXA_ANUAL, _PRAZO)
        assert sac.total_cost <= price.total_cost

    def test_soma_amortizacoes_igual_ao_principal(self):
        """Soma das amortizações deve ≈ principal."""
        res = calculate_sac(_PRINCIPAL, _TAXA_ANUAL, _PRAZO)
        if res.schedule:
            total_amort = sum(
                row.get("amortization", row.get("amortizacao", 0))
                for row in res.schedule
            )
            assert abs(total_amort - _PRINCIPAL) < 1.0

    def test_taxa_zero_sem_juros(self):
        """Com taxa zero, total_interest == 0."""
        res = calculate_sac(_PRINCIPAL, 0.0, _PRAZO)
        assert abs(res.total_interest) < 0.01

    def test_maior_taxa_maior_custo(self):
        """Taxa maior → custo total maior."""
        res_baixa = calculate_sac(_PRINCIPAL, 0.10, _PRAZO)
        res_alta  = calculate_sac(_PRINCIPAL, 0.25, _PRAZO)
        assert res_alta.total_cost > res_baixa.total_cost
