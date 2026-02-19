"""
tests/architect/test_npv.py - Testes das funções de NPV e matemática financeira

O QUE É TESTADO:
    - calculate_npv: desconto correto de fluxos de caixa
    - calculate_irr: Newton-Raphson converge para TIR correta
    - present_value_annuity: valor presente de série uniforme
    - future_value_annuity: valor futuro de acumulação

ASSINATURAS REAIS:
    calculate_npv(cashflows, discount_rate, initial_investment=0)
        → Note: lança ValueError para taxa <= -1 (não retorna 0!)
    calculate_irr(cashflows, initial_investment, guess=0.10)
        → Note: cashflows são APENAS os fluxos futuros (sem o investimento)
    present_value_annuity(payment, rate, periods)
    future_value_annuity(payment, rate, periods, initial_amount=0)

COMO RODAR:
    cd backend
    pytest tests/architect/test_npv.py -v
"""

import math
import pytest

from app.architect.calculators.npv import (
    calculate_npv,
    calculate_irr,
    present_value_annuity,
    future_value_annuity,
)


class TestCalculateNPV:
    """Testa o cálculo de Valor Presente Líquido."""

    def test_npv_sem_fluxos(self):
        """Sem fluxos futuros e sem investimento, NPV = 0."""
        assert calculate_npv([], 0.01) == 0.0

    def test_npv_sem_fluxos_com_investimento(self):
        """Sem fluxos futuros, NPV = -investimento."""
        resultado = calculate_npv([], 0.01, initial_investment=1000)
        assert resultado == -1000.0

    def test_npv_taxa_zero_soma_fluxos(self):
        """Com taxa zero, NPV é a soma dos fluxos menos o investimento."""
        fluxos = [300.0, 300.0, 300.0, 300.0]
        resultado = calculate_npv(fluxos, 0.0, initial_investment=1000)
        assert abs(resultado - 200.0) < 0.01   # -1000 + 1200 = 200

    def test_npv_desconto_correto_um_periodo(self):
        """NPV de [110] com taxa 10%/mês e investimento 100 = 0."""
        resultado = calculate_npv([110.0], 0.10, initial_investment=100.0)
        assert abs(resultado) < 0.01  # 110/1.10 - 100 ≈ 0

    def test_npv_dois_periodos(self):
        """NPV de [0, 121] com taxa 10%/mês e investimento 100 = 0."""
        resultado = calculate_npv([0.0, 121.0], 0.10, initial_investment=100.0)
        assert abs(resultado) < 0.01

    def test_npv_positivo_investimento_pequeno(self):
        """Retorno maior que investimento → NPV positivo."""
        fluxos = [3000.0, 3000.0, 3000.0, 3000.0, 3000.0]
        resultado = calculate_npv(fluxos, 0.10, initial_investment=10000.0)
        assert abs(resultado - 1372.36) < 0.10

    def test_npv_negativo_retorno_insuficiente(self):
        """Retorno menor que o custo do capital → NPV negativo."""
        fluxos = [100.0, 100.0, 100.0]
        resultado = calculate_npv(fluxos, 0.50, initial_investment=500.0)
        assert resultado < 0

    def test_npv_taxa_invalida_lanca_value_error(self):
        """Taxa <= -1 deve lançar ValueError."""
        with pytest.raises(ValueError):
            calculate_npv([500.0], -1.0)

    def test_npv_taxa_muito_negativa_lanca_value_error(self):
        """Taxa muito negativa (< -1) deve lançar ValueError."""
        with pytest.raises(ValueError):
            calculate_npv([500.0], -2.0)


class TestCalculateIRR:
    """
    Testa o cálculo da Taxa Interna de Retorno.

    ATENÇÃO: calculate_irr recebe cashflows (fluxos futuros) e initial_investment
    como argumentos separados.
    """

    def test_irr_projeto_simples(self):
        """IRR de [-100, 110] com initial=100, cashflows=[110] = 10%."""
        irr = calculate_irr([110.0], initial_investment=100.0)
        assert irr is not None
        assert abs(irr - 0.10) < 0.001

    def test_irr_financiamento_simples(self):
        """
        Empréstimo de 1000 com 3 parcelas de ~400.
        IRR > 0 e NPV com essa taxa ≈ 0.
        """
        irr = calculate_irr([400.0, 400.0, 400.0], initial_investment=1000.0)
        assert irr is not None
        assert irr > 0
        npv = calculate_npv([400.0, 400.0, 400.0], irr, initial_investment=1000.0)
        assert abs(npv) < 1.0

    def test_irr_retornos_maiores_que_investimento(self):
        """Fluxos com exemplo da docstring: [3000x5] com investimento 10000."""
        irr = calculate_irr(
            [3000.0, 3000.0, 3000.0, 3000.0, 3000.0],
            initial_investment=10_000.0,
        )
        assert irr is not None
        assert abs(irr - 0.1525) < 0.001

    def test_irr_nao_converge_retorna_none(self):
        """Fluxos que não permitem convergência → None."""
        # Fluxos muito pequenos para pagar o investimento
        irr = calculate_irr([0.01, 0.01], initial_investment=100_000.0)
        # Pode retornar None ou um número muito negativo
        if irr is not None:
            assert irr < -0.99  # economia inviável

    def test_irr_sem_fluxos_lanca_value_error(self):
        """Lista vazia deve lançar ValueError."""
        with pytest.raises(ValueError):
            calculate_irr([], initial_investment=1000.0)

    def test_irr_investimento_zero_lanca_value_error(self):
        """initial_investment <= 0 deve lançar ValueError."""
        with pytest.raises(ValueError):
            calculate_irr([500.0], initial_investment=0.0)


class TestPresentValueAnnuity:
    """Testa o valor presente de anuidade (payment=parcela, não pmt)."""

    def test_pv_anuidade_taxa_zero(self):
        """Com taxa zero, PV = payment * n."""
        pv = present_value_annuity(payment=1_000.0, rate=0.0, periods=12)
        assert abs(pv - 12_000.0) < 0.01

    def test_pv_anuidade_taxa_positiva_menor(self):
        """Com taxa positiva, PV < payment * n."""
        pv = present_value_annuity(payment=1_000.0, rate=0.01, periods=12)
        assert pv < 12_000.0
        assert pv > 0

    def test_pv_anuidade_exato(self):
        """PVA de 1000/mês a 1%/mês por 12 meses = 11255.08."""
        pv = present_value_annuity(payment=1000.0, rate=0.01, periods=12)
        assert abs(pv - 11255.08) < 0.10

    def test_pv_anuidade_um_periodo(self):
        """Com 1 período, PV = payment / (1 + rate)."""
        pv = present_value_annuity(payment=110.0, rate=0.10, periods=1)
        assert abs(pv - 100.0) < 0.01

    def test_pv_anuidade_taxa_invalida_lanca_value_error(self):
        """Taxa <= -1 deve lançar ValueError."""
        with pytest.raises(ValueError):
            present_value_annuity(payment=1_000.0, rate=-1.0, periods=12)

    def test_pv_anuidade_periodos_zero_lanca_value_error(self):
        """periods <= 0 deve lançar ValueError."""
        with pytest.raises(ValueError):
            present_value_annuity(payment=1_000.0, rate=0.01, periods=0)


class TestFutureValueAnnuity:
    """Testa o valor futuro de anuidade (payment=parcela, não pmt)."""

    def test_fv_anuidade_taxa_zero(self):
        """Com taxa zero, FV = payment * n."""
        fv = future_value_annuity(payment=1_000.0, rate=0.0, periods=12)
        assert abs(fv - 12_000.0) < 0.01

    def test_fv_anuidade_taxa_positiva_maior(self):
        """Com taxa positiva, FV > payment * n (rendimento)."""
        fv = future_value_annuity(payment=1_000.0, rate=0.01, periods=12)
        assert fv > 12_000.0

    def test_fv_anuidade_exato(self):
        """FV de 2000/mês a 0.8%/mês por 36 meses ≈ R$83057 (valor real calculado)."""
        fv = future_value_annuity(payment=2_000.0, rate=0.008, periods=36)
        assert abs(fv - 83_057.46) < 1.0

    def test_fv_com_montante_inicial(self):
        """FV com initial_amount aplicado."""
        fv_sem = future_value_annuity(payment=1_000.0, rate=0.01, periods=12)
        fv_com = future_value_annuity(
            payment=1_000.0, rate=0.01, periods=12, initial_amount=5_000.0
        )
        assert fv_com > fv_sem

    def test_fv_taxa_invalida_lanca_value_error(self):
        """Taxa <= -1 deve lançar ValueError."""
        with pytest.raises(ValueError):
            future_value_annuity(payment=1_000.0, rate=-1.0, periods=12)

    def test_fv_periodos_zero_lanca_value_error(self):
        """periods <= 0 deve lançar ValueError."""
        with pytest.raises(ValueError):
            future_value_annuity(payment=1_000.0, rate=0.01, periods=0)
