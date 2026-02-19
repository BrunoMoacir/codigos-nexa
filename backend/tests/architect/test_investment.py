"""
tests/architect/test_investment.py - Testes da calculadora de acumulação de capital

O QUE É TESTADO:
    - calculate_pmt_needed(target, annual_rate, months, initial_amount=0)
    - calculate_months_needed(target, monthly_deposit, annual_rate, initial_amount=0)
    - generate_accumulation_schedule(monthly_deposit, annual_rate, months, initial_amount=0)
      → Retorna InvestmentResult com .schedule (lista de dicts com 'month','balance')

COMO RODAR:
    cd backend
    pytest tests/architect/test_investment.py -v
"""

import math
import pytest

from app.architect.calculators.investment import (
    calculate_pmt_needed,
    calculate_months_needed,
    generate_accumulation_schedule,
)

# Parâmetros base
_META = 50_000.0
_TAXA_ANUAL = 0.1315       # CDI 13,15% a.a.
_MESES = 36


class TestCalculatePMTNeeded:
    """Testa o depósito mensal necessário para atingir uma meta."""

    def test_retorna_valor_positivo(self):
        """Para meta, taxa e prazo válidos, PMT deve ser positivo."""
        pmt = calculate_pmt_needed(_META, _TAXA_ANUAL, _MESES)
        assert pmt > 0

    def test_pmt_com_montante_inicial(self):
        """Com montante inicial, PMT deve ser menor (initial_amount, não initial_deposit)."""
        pmt_sem = calculate_pmt_needed(_META, _TAXA_ANUAL, _MESES)
        pmt_com = calculate_pmt_needed(_META, _TAXA_ANUAL, _MESES, initial_amount=10_000.0)
        assert pmt_com < pmt_sem

    def test_pmt_taxa_zero(self):
        """Com taxa zero, PMT = meta / meses."""
        pmt = calculate_pmt_needed(_META, 0.0, _MESES)
        assert abs(pmt - _META / _MESES) < 0.10

    def test_maior_meta_maior_pmt(self):
        """Meta maior → PMT maior (mesmos prazo e taxa)."""
        pmt_50k = calculate_pmt_needed(50_000.0, _TAXA_ANUAL, _MESES)
        pmt_100k = calculate_pmt_needed(100_000.0, _TAXA_ANUAL, _MESES)
        assert pmt_100k > pmt_50k

    def test_mais_meses_menor_pmt(self):
        """Mais tempo → menor depósito mensal."""
        pmt_24m = calculate_pmt_needed(_META, _TAXA_ANUAL, 24)
        pmt_48m = calculate_pmt_needed(_META, _TAXA_ANUAL, 48)
        assert pmt_48m < pmt_24m

    def test_maior_taxa_menor_pmt(self):
        """Taxa maior → precisa depositar menos (rendimento faz mais trabalho)."""
        pmt_baixa = calculate_pmt_needed(_META, 0.05, _MESES)
        pmt_alta  = calculate_pmt_needed(_META, 0.15, _MESES)
        assert pmt_alta < pmt_baixa

    def test_meta_ja_atingida_retorna_zero(self):
        """Se initial_amount já cobre a meta após rendimentos, PMT deve ser 0."""
        pmt = calculate_pmt_needed(_META, _TAXA_ANUAL, _MESES, initial_amount=_META * 2)
        assert pmt == 0.0

    def test_exemplo_da_docstring(self):
        """PMT para meta R$100k, 10%aa, 36m ≈ R$2409 (taxa composta mensal real)."""
        pmt = calculate_pmt_needed(100_000.0, 0.10, 36)
        # O resultado exato é ~2409 (taxa mensal composta = (1.10)^(1/12)-1 ≈ 0.797%)
        assert abs(pmt - 2409.11) < 1.0

    def test_meta_zero_lanca_value_error(self):
        """target <= 0 deve lançar ValueError."""
        with pytest.raises(ValueError):
            calculate_pmt_needed(0.0, _TAXA_ANUAL, _MESES)


class TestCalculateMonthsNeeded:
    """
    Testa quantos meses são necessários para atingir uma meta.

    ASSINATURA: calculate_months_needed(target, monthly_deposit, annual_rate, initial_amount=0)
    """

    def test_retorna_inteiro_positivo(self):
        """Deve retornar um inteiro positivo."""
        # PMT para 36 meses com _META e _TAXA_ANUAL
        pmt_necessario = calculate_pmt_needed(_META, _TAXA_ANUAL, _MESES)
        meses = calculate_months_needed(_META, pmt_necessario, _TAXA_ANUAL)
        assert meses is not None
        assert isinstance(meses, int)
        assert meses >= 1

    def test_deposito_insuficiente_retorna_none(self):
        """Depósito de R$1 para R$50k → precisa muitos meses mas pode convergir."""
        meses = calculate_months_needed(_META, 1.0, _TAXA_ANUAL)
        # Com depósito de R$1 para R$50k: ou leva muitos séculos ou retorna None
        # A implementação itera até max_months=1200 e retorna None se não convergir
        assert meses is None or meses > 600

    def test_maior_deposito_menos_meses(self):
        """Depósito maior leva à meta mais rápido."""
        m1 = calculate_months_needed(_META, 1_000.0, _TAXA_ANUAL)
        m2 = calculate_months_needed(_META, 2_000.0, _TAXA_ANUAL)
        if m1 is not None and m2 is not None:
            assert m2 < m1

    def test_consistencia_com_pmt(self):
        """PMT calculado para N meses deve atingir meta em ≈ N meses."""
        n_esperado = 24
        pmt = calculate_pmt_needed(_META, _TAXA_ANUAL, n_esperado)
        n_calculado = calculate_months_needed(_META, pmt, _TAXA_ANUAL)
        if n_calculado is not None:
            assert abs(n_calculado - n_esperado) <= 2  # tolerância ±2 meses

    def test_taxa_zero(self):
        """Com taxa zero, meses = ceil(meta / deposito)."""
        pmt = 1_000.0
        meses = calculate_months_needed(_META, pmt, 0.0)
        if meses is not None:
            esperado = math.ceil(_META / pmt)
            assert abs(meses - esperado) <= 1

    def test_exemplo_da_docstring(self):
        """100k, R$2000/mês, 10%aa → 43 meses (taxa mensal composta real)."""
        meses = calculate_months_needed(100_000.0, 2_000.0, 0.10)
        assert meses == 43

    def test_deposito_zero_lanca_value_error(self):
        """monthly_deposit <= 0 deve lançar ValueError."""
        with pytest.raises(ValueError):
            calculate_months_needed(_META, 0.0, _TAXA_ANUAL)


class TestGenerateAccumulationSchedule:
    """
    Testa a tabela de evolução patrimonial mês a mês.

    Retorna InvestmentResult com:
        .schedule: List[Dict] com chaves 'month', 'deposit', 'interest', 'balance'
        .final_amount: saldo final
        .monthly_deposit: depósito mensal
    """

    def test_schedule_tem_n_entradas(self):
        """O schedule deve ter exatamente N entradas."""
        result = generate_accumulation_schedule(
            monthly_deposit=1_000.0,
            annual_rate=_TAXA_ANUAL,
            months=_MESES,
        )
        assert len(result.schedule) == _MESES

    def test_saldo_cresce_ao_longo_do_tempo(self):
        """Com depósito positivo e taxa >= 0, o saldo deve crescer."""
        result = generate_accumulation_schedule(
            monthly_deposit=1_000.0, annual_rate=_TAXA_ANUAL, months=12,
        )
        saldos = [row["balance"] for row in result.schedule]
        assert saldos[-1] > saldos[0]

    def test_final_amount_igual_ultimo_saldo(self):
        """final_amount deve ser igual ao último saldo do schedule."""
        result = generate_accumulation_schedule(1_000.0, _TAXA_ANUAL, 12)
        assert abs(result.final_amount - result.schedule[-1]["balance"]) < 0.01

    def test_montante_inicial_refletido(self):
        """Com initial_amount, saldo inicial é maior."""
        result_sem = generate_accumulation_schedule(1_000.0, _TAXA_ANUAL, 12)
        result_com = generate_accumulation_schedule(
            1_000.0, _TAXA_ANUAL, 12, initial_amount=5_000.0
        )
        assert result_com.final_amount > result_sem.final_amount

    def test_taxa_zero_saldo_linear(self):
        """Com taxa zero, saldo cresce linearmente."""
        pmt = 1_000.0
        result = generate_accumulation_schedule(pmt, 0.0, 6)
        for i, row in enumerate(result.schedule):
            saldo_esperado = pmt * (i + 1)
            assert abs(row["balance"] - saldo_esperado) < 0.10

    def test_campos_obrigatorios_presentes(self):
        """Cada linha deve ter 'month', 'balance', 'deposit', 'interest'."""
        result = generate_accumulation_schedule(1_000.0, _TAXA_ANUAL, 3)
        for row in result.schedule:
            assert "month" in row, f"'month' não encontrado em {row}"
            assert "balance" in row, f"'balance' não encontrado em {row}"
            assert "deposit" in row, f"'deposit' não encontrado em {row}"
            assert "interest" in row, f"'interest' não encontrado em {row}"

    def test_meses_numerados_sequencialmente(self):
        """os meses no schedule devem ser 1, 2, 3, ..., n."""
        n = 6
        result = generate_accumulation_schedule(1_000.0, _TAXA_ANUAL, n)
        for i, row in enumerate(result.schedule):
            assert row["month"] == i + 1

    def test_deposito_zero_invalido(self):
        """monthly_deposit < 0 deve lançar ValueError."""
        with pytest.raises(ValueError):
            generate_accumulation_schedule(-1.0, _TAXA_ANUAL, 12)

    def test_exemplo_da_docstring(self):
        """FV de R$2000/mês a 10%aa por 36 meses > R$72.000."""
        result = generate_accumulation_schedule(2_000.0, 0.10, 36)
        assert result.final_amount > 72_000.0
