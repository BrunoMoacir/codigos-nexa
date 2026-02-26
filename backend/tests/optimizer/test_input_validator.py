import pytest

from app.optimizer.models import OptimizationRequest
from app.optimizer.validators.input_validator import InputValidator


@pytest.fixture
def validator():
    return InputValidator()


def test_valid_request(validator):
    request = OptimizationRequest(
        user_id="user_123",
        current_cards=[],
        safe_to_spend=1000.0,
        monthly_income=5000.0,
    )
    validator.validate(request)  # Should not raise


from pydantic import ValidationError

def test_user_id_empty(validator):
    with pytest.raises(ValidationError, match="user_id é obrigatório"):
        OptimizationRequest(user_id="", current_cards=[], safe_to_spend=100.0)


def test_user_id_whitespace(validator):
    with pytest.raises(ValidationError, match="user_id é obrigatório"):
        OptimizationRequest(user_id="   ", current_cards=[], safe_to_spend=100.0)


def test_safe_to_spend_negative(validator):
    request = OptimizationRequest(
        user_id="user_123", current_cards=[], safe_to_spend=-10.0
    )
    with pytest.raises(ValueError, match="safe_to_spend não pode ser negativo"):
        validator.validate(request)


def test_monthly_income_zero(validator):
    request = OptimizationRequest(
        user_id="user_123",
        current_cards=[],
        safe_to_spend=100.0,
        monthly_income=0.0,
    )
    with pytest.raises(ValueError, match="renda mensal deve ser positiva"):
        validator.validate(request)


def test_monthly_income_negative(validator):
    request = OptimizationRequest(
        user_id="user_123",
        current_cards=[],
        safe_to_spend=100.0,
        monthly_income=-500.0,
    )
    with pytest.raises(ValueError, match="renda mensal deve ser positiva"):
        validator.validate(request)


def test_missing_both_income_and_safe_spend(validator):
    request = OptimizationRequest(
        user_id="user_123",
        current_cards=[],
        safe_to_spend=None,
        monthly_income=None,
    )
    with pytest.raises(ValueError, match="informe safe_to_spend ou monthly_income"):
        validator.validate(request)


def test_only_safe_to_spend_provided(validator):
    request = OptimizationRequest(
        user_id="user_123",
        current_cards=[],
        safe_to_spend=150.0,
        monthly_income=None,
    )
    validator.validate(request)  # Should not raise


def test_only_monthly_income_provided(validator):
    request = OptimizationRequest(
        user_id="user_123",
        current_cards=[],
        safe_to_spend=None,
        monthly_income=3000.0,
    )
    validator.validate(request)  # Should not raise
