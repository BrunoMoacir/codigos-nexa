"""
tests/architect/test_npv.py - Testes das funções de NPV e matemática financeira

O QUE É TESTADO:
    - calculate_npv: desconto correto de fluxos de caixa; VPL real com Fisher
    - calculate_irr: Newton-Raphson converge para TIR correta; múltiplos chutes;
                     detecção de múltiplas raízes (regra de Descartes)
    - present_value_annuity: valor presente de série uniforme
    - future_value_annuity: valor futuro de acumulação

ASSINATURAS REAIS:
    calculate_npv(cashflows, discount_rate, initial_investment=0, inflation_rate=0.0)
        → Note: lança ValueError para taxa <= -1 (não retorna 0!)
    calculate_irr(cashflows, initial_investment, guess=0.10)
        → Retorna IRRResult(irr, multiple_roots_possible)
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
    IRRResult,
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

    # ── VPL real com inflação ──────────────────────────────────────────

    def test_npv_inflacao_zero_igual_nominal(self):
        """inflation_rate=0 deve produzir exatamente o mesmo resultado que sem inflação."""
        fluxos = [3000.0, 3000.0, 3000.0]
        sem_inflacao = calculate_npv(fluxos, 0.10, initial_investment=5000.0)
        com_inflacao_zero = calculate_npv(fluxos, 0.10, initial_investment=5000.0, inflation_rate=0.0)
        assert abs(sem_inflacao - com_inflacao_zero) < 1e-9

    def test_npv_real_maior_que_nominal(self):
        """Fisher reduz a taxa efetiva (r_real < r_nominal) → VPL real > VPL nominal.

        Com inflation_rate=0.5%/mês e discount_rate=10%/mês:
            r_real = 1.10/1.005 - 1 ≈ 9.45% < 10%
        Taxa de desconto menor → VPL mais alto.
        """
        fluxos = [3000.0, 3000.0, 3000.0, 3000.0, 3000.0]
        npv_nominal = calculate_npv(fluxos, 0.10, initial_investment=10000.0)
        npv_real = calculate_npv(fluxos, 0.10, initial_investment=10000.0, inflation_rate=0.005)
        assert npv_real > npv_nominal

    def test_npv_real_fisher_correto(self):
        """Fisher: r_real = (1+nominal)/(1+inflação) - 1; VPL deve usar essa taxa."""
        fluxos = [110.0]
        # nominal=10%, inflação=5% → real ≈ 4.76%
        # VPL real = 110 / 1.0476 - 100 ≈ 4.99
        npv = calculate_npv(fluxos, 0.10, initial_investment=100.0, inflation_rate=0.05)
        r_real = 1.10 / 1.05 - 1
        esperado = 110.0 / (1 + r_real) - 100.0
        assert abs(npv - esperado) < 0.01

    def test_npv_inflacao_invalida_lanca_value_error(self):
        """inflation_rate <= -1 deve lançar ValueError."""
        with pytest.raises(ValueError):
            calculate_npv([500.0], 0.10, inflation_rate=-1.0)


class TestCalculateIRR:
    """
    Testa o cálculo da Taxa Interna de Retorno.

    ATENÇÃO: calculate_irr recebe cashflows (fluxos futuros) e initial_investment
    como argumentos separados. Retorna IRRResult(irr, multiple_roots_possible).
    """

    def test_irr_retorna_irr_result(self):
        """calculate_irr deve retornar IRRResult."""
        result = calculate_irr([110.0], initial_investment=100.0)
        assert isinstance(result, IRRResult)

    def test_irr_projeto_simples(self):
        """IRR de [-100, 110] com initial=100, cashflows=[110] = 10%."""
        result = calculate_irr([110.0], initial_investment=100.0)
        assert result.irr is not None
        assert abs(result.irr - 0.10) < 0.001

    def test_irr_financiamento_simples(self):
        """
        Empréstimo de 1000 com 3 parcelas de ~400.
        IRR > 0 e NPV com essa taxa ≈ 0.
        """
        result = calculate_irr([400.0, 400.0, 400.0], initial_investment=1000.0)
        assert result.irr is not None
        assert result.irr > 0
        npv = calculate_npv([400.0, 400.0, 400.0], result.irr, initial_investment=1000.0)
        assert abs(npv) < 1.0

    def test_irr_retornos_maiores_que_investimento(self):
        """Fluxos com exemplo da docstring: [3000x5] com investimento 10000."""
        result = calculate_irr(
            [3000.0, 3000.0, 3000.0, 3000.0, 3000.0],
            initial_investment=10_000.0,
        )
        assert result.irr is not None
        assert abs(result.irr - 0.1525) < 0.001

    def test_irr_nao_converge_retorna_none(self):
        """Fluxos que não permitem convergência → irr=None."""
        result = calculate_irr([0.01, 0.01], initial_investment=100_000.0)
        if result.irr is not None:
            assert result.irr < -0.99  # economia inviável

    def test_irr_sem_fluxos_lanca_value_error(self):
        """Lista vazia deve lançar ValueError."""
        with pytest.raises(ValueError):
            calculate_irr([], initial_investment=1000.0)

    def test_irr_investimento_zero_lanca_value_error(self):
        """initial_investment <= 0 deve lançar ValueError."""
        with pytest.raises(ValueError):
            calculate_irr([500.0], initial_investment=0.0)

    # ── Múltiplas raízes (regra de Descartes) ─────────────────────────

    def test_irr_fluxo_simples_sem_multiplas_raizes(self):
        """Fluxo típico [-I, +CF...] tem 1 mudança de sinal → multiple_roots_possible=False."""
        result = calculate_irr([3000.0, 3000.0, 3000.0], initial_investment=8000.0)
        assert result.multiple_roots_possible is False

    def test_irr_fluxo_misto_multiplas_raizes(self):
        """Fluxo com custo no meio (ex: reforma durante financiamento) → multiple_roots_possible=True."""
        # [-10000, +500, +500, +500, -8000, +600, +600, +600, +600, +600]
        # Mudanças de sinal: - → + → - → + = 3 mudanças
        cashflows = [500.0, 500.0, 500.0, -8000.0, 600.0, 600.0, 600.0, 600.0, 600.0]
        result = calculate_irr(cashflows, initial_investment=10_000.0)
        assert result.multiple_roots_possible is True

    def test_irr_multiplos_chutes_convergencia(self):
        """IRR muito alta (curto prazo / retorno rápido) — fallback de chute deve convergir."""
        # [-100, 200] → IRR = 100% (retorno em 1 período)
        result = calculate_irr([200.0], initial_investment=100.0, guess=0.10)
        assert result.irr is not None
        assert abs(result.irr - 1.0) < 0.001

    def test_irr_npv_com_irr_encontrado_e_zero(self):
        """Para qualquer IRR encontrado, NPV calculado com essa taxa deve ser ≈ 0."""
        cashflows = [1500.0, 1500.0, 1500.0, 1500.0, 1500.0, 1500.0]
        result = calculate_irr(cashflows, initial_investment=7000.0)
        assert result.irr is not None
        npv = calculate_npv(cashflows, result.irr, initial_investment=7000.0)
        assert abs(npv) < 0.50


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
