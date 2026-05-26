"""
tests/architect/test_pluggy_normalizers.py

Testa os normalizers Pluggy → OpenFinancePipeline sem precisar de
credenciais reais. Todos os dados são mocks que imitam o schema
real da Pluggy Sandbox.

Questão central validada aqui:
    interestRates[].rate é mensal quando unit="MONTHLY" → (1+r)^12-1 correto.
"""

import pytest

# Importar diretamente as funções (sem levantar o FastAPI inteiro)
from app.architect.router import (
    _aggregate_pluggy_transactions_by_month,
    _normalize_pluggy_financing,
    _normalize_pluggy_investment,
    _normalize_pluggy_loan,
)


# ─────────────────────────────────────────────────────────────────────
# Mocks: estrutura real retornada pela Pluggy Sandbox
# ─────────────────────────────────────────────────────────────────────

MOCK_INVESTMENT_CDB = {
    "id": "inv-001",
    "type": "FIXED_INCOME",
    "name": "CDB Banco XYZ 118% CDI",
    "balance": 10_000.00,
    "amount": 9_500.00,
    "annualRate": 0.1180,
    "date": "2024-01-15",
    "dueDate": "2026-01-15",
    "code": "CDB123",
    "currencyCode": "BRL",
}

MOCK_INVESTMENT_TESOURO = {
    "id": "inv-002",
    "type": "TREASURE",
    "name": "Tesouro IPCA+ 2028",
    "balance": 5_000.00,
    "annualRate": 0.1308,
    "date": "2023-06-01",
    "dueDate": "2028-08-15",
    "currencyCode": "BRL",
}

MOCK_INVESTMENT_FUNDO_ACOES = {
    "id": "inv-003",
    "type": "VARIABLE_INCOME",
    "name": "Fundo Ações Dividendos",
    "balance": 3_200.00,
    "currencyCode": "BRL",
}

MOCK_INVESTMENT_HYBRID = {
    "id": "inv-004",
    "type": "MULTIMARKET",
    "name": "Fundo Multimercado Balanceado",
    "balance": 7_500.00,
    "annualRate": 0.0950,
    "currencyCode": "BRL",
}

MOCK_LOAN_PESSOAL = {
    "id": "loan-001",
    "type": "PERSONAL_CREDIT",
    "monthlyPaymentAmount": 850.00,
    "totalAmount": 15_000.00,
    "interestRates": [
        {
            "rate": 0.0199,
            "type": "NOMINAL",
            "unit": "MONTHLY",
        }
    ],
    "instalments": {
        "paid": 6,
        "missed": 0,
    },
}

MOCK_LOAN_COM_FEES = {
    "id": "loan-002",
    "type": "PERSONAL_CREDIT",
    "monthlyPaymentAmount": 1_200.00,
    "totalAmount": 20_000.00,
    "fees": {
        "monthlyFee": 0.0250,
    },
    "instalments": {
        "paid": 3,
        "missedInstalments": 1,
    },
}

MOCK_LOAN_SEM_TAXA = {
    "id": "loan-003",
    "type": "PERSONAL_CREDIT",
    "monthlyPaymentAmount": 500.00,
    "totalAmount": 5_000.00,
    "interestRates": [
        {
            "rate": 0.2600,
            "type": "ANNUAL",
            "unit": "YEARLY",
        }
    ],
}

MOCK_FINANCING_IMOVEL = {
    "id": "fin-001",
    "type": "HOME_LOAN",
    "subtype": "IMOVEL_RESIDENCIAL",
    "monthlyPaymentAmount": 2_800.00,
    "totalAmount": 450_000.00,
    "interestRates": [
        {
            "rate": 0.0065,
            "type": "EFFECTIVE",
            "unit": "MONTHLY",
        }
    ],
    "instalments": {
        "paid": 24,
        "missed": 0,
    },
}

MOCK_FINANCING_VEICULO = {
    "id": "fin-002",
    "type": "VEHICLE_LOAN",
    "subtype": "VEICULO_AUTOMOVEL",
    "monthlyPaymentAmount": 1_100.00,
    "totalAmount": 60_000.00,
    "interestRates": [
        {
            "rate": 0.0150,
            "type": "NOMINAL",
            "unit": "MONTHLY",
        }
    ],
    "instalments": {
        "paidInstalments": 12,
        "missed": 2,
    },
}

MOCK_FINANCING_OUTROS = {
    "id": "fin-003",
    "type": "RURAL_CREDIT",
    "monthlyPaymentAmount": 400.00,
    "interestRates": [
        {
            "rate": 0.0080,
            "type": "EFFECTIVE",
            "unit": "MONTHLY",
        }
    ],
    "instalments": {},
}

MOCK_FINANCING_SEM_TAXA = {
    "id": "fin-004",
    "type": "HOME_LOAN",
    "monthlyPaymentAmount": 3_000.00,
    "interestRates": [],
}

MOCK_TRANSACTIONS = [
    {"id": "t1", "date": "2025-01-05", "amount": 5_000.00, "description": "Salário"},
    {"id": "t2", "date": "2025-01-10", "amount": -300.00, "description": "Supermercado"},
    {"id": "t3", "date": "2025-01-25", "amount": -1_200.00, "description": "Aluguel"},
    {"id": "t4", "date": "2025-02-05", "amount": 5_000.00, "description": "Salário"},
    {"id": "t5", "date": "2025-02-12", "amount": 200.00, "description": "Freelance"},
    {"id": "t6", "date": "2025-02-20", "amount": -800.00, "description": "Cartão"},
    {"id": "t7", "date": "2025-03-05", "amount": 5_000.00, "description": "Salário"},
    {"id": "t8", "date": "invalid-date", "amount": 100.00, "description": "Data inválida"},
]


# ─────────────────────────────────────────────────────────────────────
# Testes: _normalize_pluggy_investment
# ─────────────────────────────────────────────────────────────────────

class TestNormalizePluggyInvestment:

    def test_cdb_maps_to_fixed_income(self):
        result = _normalize_pluggy_investment(MOCK_INVESTMENT_CDB)
        assert result["type"] == "FIXED_INCOME"

    def test_tesouro_maps_to_fixed_income(self):
        result = _normalize_pluggy_investment(MOCK_INVESTMENT_TESOURO)
        assert result["type"] == "FIXED_INCOME"

    def test_fundo_acoes_maps_to_variable_income(self):
        result = _normalize_pluggy_investment(MOCK_INVESTMENT_FUNDO_ACOES)
        assert result["type"] == "VARIABLE_INCOME"

    def test_multimarket_maps_to_hybrid(self):
        result = _normalize_pluggy_investment(MOCK_INVESTMENT_HYBRID)
        assert result["type"] == "HYBRID"

    def test_amount_brl_uses_balance_first(self):
        result = _normalize_pluggy_investment(MOCK_INVESTMENT_CDB)
        assert result["amount_brl"] == 10_000.00

    def test_amount_brl_falls_back_to_amount(self):
        raw = {**MOCK_INVESTMENT_CDB, "balance": None}
        result = _normalize_pluggy_investment(raw)
        assert result["amount_brl"] == 9_500.00

    def test_annual_rate_captured(self):
        result = _normalize_pluggy_investment(MOCK_INVESTMENT_CDB)
        assert result["rate_annual"] == pytest.approx(0.1180)

    def test_no_annual_rate_omitted(self):
        result = _normalize_pluggy_investment(MOCK_INVESTMENT_FUNDO_ACOES)
        assert "rate_annual" not in result

    def test_duration_years_computed_from_dates(self):
        result = _normalize_pluggy_investment(MOCK_INVESTMENT_CDB)
        # CDB: 2024-01-15 → 2026-01-15 ≈ 2 anos
        assert "duration_years" in result
        assert 1.9 < result["duration_years"] < 2.1

    def test_duration_years_computed_for_long_bond(self):
        result = _normalize_pluggy_investment(MOCK_INVESTMENT_TESOURO)
        # Tesouro: 2023-06-01 → 2028-08-15 ≈ 5.2 anos
        assert "duration_years" in result
        assert 5.0 < result["duration_years"] < 5.5

    def test_no_dates_no_duration(self):
        result = _normalize_pluggy_investment(MOCK_INVESTMENT_FUNDO_ACOES)
        assert "duration_years" not in result


# ─────────────────────────────────────────────────────────────────────
# Testes: _normalize_pluggy_loan
# ─────────────────────────────────────────────────────────────────────

class TestNormalizePluggyLoan:

    def test_monthly_rate_converted_to_annual_cet(self):
        result = _normalize_pluggy_loan(MOCK_LOAN_PESSOAL)
        assert result is not None
        # 0.0199 mensal → (1.0199)^12 - 1 ≈ 26.7%
        expected = (1.0 + 0.0199) ** 12 - 1.0
        assert result["cet_annual"] == pytest.approx(expected, rel=1e-3)

    def test_monthly_rate_fees_takes_priority_over_interest_rates(self):
        result = _normalize_pluggy_loan(MOCK_LOAN_COM_FEES)
        assert result is not None
        expected = (1.0 + 0.0250) ** 12 - 1.0
        assert result["cet_annual"] == pytest.approx(expected, rel=1e-3)

    def test_monthly_payment_captured(self):
        result = _normalize_pluggy_loan(MOCK_LOAN_PESSOAL)
        assert result["monthly_payment"] == 850.00

    def test_paid_instalments_captured(self):
        result = _normalize_pluggy_loan(MOCK_LOAN_PESSOAL)
        assert result["paid_instalments"] == 6

    def test_missed_payments_zero_when_absent(self):
        result = _normalize_pluggy_loan(MOCK_LOAN_PESSOAL)
        assert result["missed_payments"] == 0

    def test_missed_instalments_captured_via_alternative_key(self):
        result = _normalize_pluggy_loan(MOCK_LOAN_COM_FEES)
        assert result["missed_payments"] == 1

    def test_only_yearly_unit_returns_none(self):
        # interestRates só tem unit=YEARLY — normalizer não consegue extrair taxa mensal
        result = _normalize_pluggy_loan(MOCK_LOAN_SEM_TAXA)
        assert result is None

    def test_no_interest_rates_and_no_fees_returns_none(self):
        raw = {"type": "PERSONAL_CREDIT", "monthlyPaymentAmount": 500.00}
        result = _normalize_pluggy_loan(raw)
        assert result is None

    def test_rate_value_sanity_personal_loan(self):
        result = _normalize_pluggy_loan(MOCK_LOAN_PESSOAL)
        # Taxa pessoal brasileira: entre 20% e 200% ao ano
        assert 0.20 < result["cet_annual"] < 2.00


# ─────────────────────────────────────────────────────────────────────
# Testes: _normalize_pluggy_financing
# ─────────────────────────────────────────────────────────────────────

class TestNormalizePluggyFinancing:

    def test_home_loan_type_detected(self):
        result = _normalize_pluggy_financing(MOCK_FINANCING_IMOVEL)
        assert result is not None
        assert result["product_type"] == "HOME_LOAN"

    def test_vehicle_loan_type_detected(self):
        result = _normalize_pluggy_financing(MOCK_FINANCING_VEICULO)
        assert result is not None
        assert result["product_type"] == "VEHICLE_LOAN"

    def test_rural_credit_maps_to_other(self):
        result = _normalize_pluggy_financing(MOCK_FINANCING_OUTROS)
        assert result is not None
        assert result["product_type"] == "OTHER"

    def test_home_loan_cet_annual_computed(self):
        result = _normalize_pluggy_financing(MOCK_FINANCING_IMOVEL)
        # 0.0065 mensal → (1.0065)^12 - 1 ≈ 8.1% a.a. (faixa SFH)
        expected = (1.0 + 0.0065) ** 12 - 1.0
        assert result["cet_annual"] == pytest.approx(expected, rel=1e-3)

    def test_vehicle_loan_cet_annual_higher_than_home(self):
        home = _normalize_pluggy_financing(MOCK_FINANCING_IMOVEL)
        vehicle = _normalize_pluggy_financing(MOCK_FINANCING_VEICULO)
        assert vehicle["cet_annual"] > home["cet_annual"]

    def test_paid_instalments_captured(self):
        result = _normalize_pluggy_financing(MOCK_FINANCING_IMOVEL)
        assert result["paid_instalments"] == 24

    def test_missed_payments_captured(self):
        result = _normalize_pluggy_financing(MOCK_FINANCING_VEICULO)
        # MOCK_FINANCING_VEICULO tem missed=2 (via instalments.missed)
        assert result["missed_payments"] == 2

    def test_empty_instalments_defaults_zero(self):
        result = _normalize_pluggy_financing(MOCK_FINANCING_OUTROS)
        assert result["paid_instalments"] == 0
        assert result["missed_payments"] == 0

    def test_empty_interest_rates_returns_none(self):
        result = _normalize_pluggy_financing(MOCK_FINANCING_SEM_TAXA)
        assert result is None

    def test_home_loan_cet_in_realistic_range(self):
        result = _normalize_pluggy_financing(MOCK_FINANCING_IMOVEL)
        # SFH: entre 6% e 14% a.a.
        assert 0.06 < result["cet_annual"] < 0.14


# ─────────────────────────────────────────────────────────────────────
# Testes: _aggregate_pluggy_transactions_by_month
# ─────────────────────────────────────────────────────────────────────

class TestAggregatePluggyTransactionsByMonth:

    def setup_method(self):
        self.result = _aggregate_pluggy_transactions_by_month(MOCK_TRANSACTIONS)

    def test_invalid_date_skipped(self):
        # 8 transações no mock, mas a de data inválida deve ser ignorada
        months = {(r["year"], r["month"]) for r in self.result}
        assert (0, 0) not in months

    def test_returns_three_months(self):
        assert len(self.result) == 3

    def test_sorted_chronologically(self):
        years_months = [(r["year"], r["month"]) for r in self.result]
        assert years_months == sorted(years_months)

    def test_january_income_only_credits(self):
        jan = next(r for r in self.result if r["year"] == 2025 and r["month"] == 1)
        # Créditos em jan: 5000. Débitos: -300, -1200
        assert jan["income_total"] == pytest.approx(5_000.00)

    def test_january_balance_delta_credits_minus_debits(self):
        jan = next(r for r in self.result if r["year"] == 2025 and r["month"] == 1)
        assert jan["balance_delta"] == pytest.approx(5_000.00 - 300.00 - 1_200.00)

    def test_february_income_includes_freelance(self):
        feb = next(r for r in self.result if r["year"] == 2025 and r["month"] == 2)
        assert feb["income_total"] == pytest.approx(5_000.00 + 200.00)

    def test_february_balance_delta(self):
        feb = next(r for r in self.result if r["year"] == 2025 and r["month"] == 2)
        assert feb["balance_delta"] == pytest.approx(5_000.00 + 200.00 - 800.00)

    def test_march_only_salary(self):
        mar = next(r for r in self.result if r["year"] == 2025 and r["month"] == 3)
        assert mar["income_total"] == pytest.approx(5_000.00)
        assert mar["balance_delta"] == pytest.approx(5_000.00)

    def test_empty_list_returns_empty(self):
        result = _aggregate_pluggy_transactions_by_month([])
        assert result == []

    def test_all_invalid_dates_returns_empty(self):
        bad = [{"date": "bad", "amount": 100}, {"date": "", "amount": 200}]
        result = _aggregate_pluggy_transactions_by_month(bad)
        assert result == []
